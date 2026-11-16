"""The visible schematic wires are native KiCad wires with unchanged net topology."""
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import pytest

from wholeboard import sexpr
from wholeboard import schematic_view
from wholeboard.kicad import cli, libs, schematic

pytestmark = pytest.mark.skipif(libs.locate("symbols") is None, reason="KiCad symbol libraries needed")


def example():
    return json.loads((Path(__file__).parents[1] / "wholeboard/web/workbench-example.json").read_text())


def assert_native_nets(spec, sch):
    output = sch.with_suffix(".net.xml")
    result = cli.run(["sch", "export", "netlist", "--format", "kicadxml", "-o", str(output), str(sch)])
    assert result.returncode == 0, result.stderr
    nodes = {}
    for net in ET.parse(output).findall("./nets/net"):
        for node in net.findall("node"):
            nodes[f"{node.get('ref')}.{node.get('pin')}"] = net.get("name")
    desired = {pin: net["name"] for net in spec["nets"] for pin in net["pins"]}
    for pin, name in desired.items():
        assert pin in nodes, f"Native netlist lost {pin}"
        for other, other_name in desired.items():
            assert (nodes[pin] == nodes[other]) == (name == other_name), f"Native wire changed connectivity: {pin}, {other}"


def test_saved_pin_connection_emits_native_wire_segments_and_preserves_all_nets(tmp_path):
    spec = example()
    spec["editor"]["connection_guides"] = [{"from": "R1.1", "to": "J1.A5"}]
    result = schematic.build(spec, tmp_path)
    sch = Path(result["sch"])
    tree = sexpr.parse(sch.read_text())
    assert list(sexpr.find_all(tree, "wire")), "A saved connection is still only a logical dashed guide"
    assert_native_nets(spec, sch)


def test_rotated_pin_routes_escape_the_symbol_without_shorting_its_other_pin(tmp_path):
    spec = example()
    spec["editor"]["rotations"] = {"R1": 90}
    spec["editor"]["connection_guides"] = [{"from": "R1.1", "to": "J1.A5"}]
    result = schematic.build(spec, tmp_path)
    sch = Path(result["sch"])
    assert list(sexpr.find_all(sexpr.parse(sch.read_text()), "wire"))
    assert_native_nets(spec, sch)


def test_shared_wire_branches_export_native_junctions(tmp_path):
    spec = example()
    spec["editor"]["connection_guides"] = [{"from": "R1.2", "to": "R2.2"}, {"from": "R1.2", "to": "D1.1"}]
    result = schematic.build(spec, tmp_path)
    sch = Path(result["sch"])
    tree = sexpr.parse(sch.read_text())
    assert list(sexpr.find_all(tree, "junction")), "Shared branches are missing a native junction"
    assert_native_nets(spec, sch)


def test_schematic_scene_uses_the_emitted_wire_and_junction_geometry():
    spec = example()
    spec["editor"]["connection_guides"] = [{"from": "R1.2", "to": "R2.2"}, {"from": "R1.2", "to": "D1.1"}]
    scene = schematic_view.scene(spec)
    assert scene["wires"]
    assert scene["junctions"]
    assert all(wire["net"] == "GND" for wire in scene["wires"])
    assert all(route["status"] == "routed" for route in scene["routes"])


def test_native_netlist_proof_detects_an_actual_short_in_the_emitted_file(tmp_path):
    spec = example()
    result = schematic.build(spec, tmp_path)
    sch = Path(result["sch"])
    tree = sexpr.parse(sch.read_text())
    scene = schematic_view.scene(spec)
    instance = next(i for i in scene["symbols"] if i["ref"] == "R1")
    definition = scene["definitions"][instance["definition"]]
    x,y = [schematic.EDITOR_ORIGIN_MM+v*schematic.EDITOR_MM_PER_UNIT for v in instance["position"]]
    pins = [schematic._symbol_point(x,y,p["x"],p["y"],instance["rotation"]) for p in definition["pins"]]
    tree.append([sexpr.Sym("wire"),[sexpr.Sym("pts"),sexpr.S(sexpr.Sym("xy"),*pins[0]),sexpr.S(sexpr.Sym("xy"),*pins[1])],
                 [sexpr.Sym("stroke"),sexpr.S(sexpr.Sym("width"),.1778),sexpr.S(sexpr.Sym("type"),sexpr.Sym("default"))],
                 [sexpr.Sym("uuid"),schematic.uid()]])
    sch.write_text(sexpr.dumps(tree))
    proof = schematic.netlist_parity(spec,cli.schematic_nets(sch))
    assert proof["ok"] is False
    assert any(conflict["unexpected"] for conflict in proof["conflicts"])


def test_an_unsafe_locked_bend_is_reported_without_exporting_a_false_wire(tmp_path):
    spec = example()
    spec["editor"]["connection_guides"]=[{"from":"R1.1","to":"J1.A5","waypoints":[[625,275]]}]
    result=schematic.build(spec,tmp_path)
    route=result["pages"][0]["wiring"]["routes"][0]
    assert route["status"]=="unroutable"
    assert result["notes"]
    assert not list(sexpr.find_all(sexpr.parse(Path(result["sch"]).read_text()),"wire"))
    assert_native_nets(spec,Path(result["sch"]))


def test_manual_wire_preview_uses_native_pin_exits_without_leaving_a_dangling_tail(tmp_path):
    spec={"name":"native_wire_exit","board":{"width_mm":30,"height_mm":22,"layers":2},
        "components":[{"ref":f"R{i}","value":"1k","symbol":"Device:R","footprint":"Resistor_SMD:R_0603_1608Metric","placement":{"x_mm":i*10,"y_mm":10}} for i in (1,2)],
        "nets":[{"name":"SIG","pins":["R1.1","R2.1"]},{"name":"GND","pins":["R1.2","R2.2"]}],
        "editor":{"positions":{"R1":[200,200],"R2":[600,200]}}}
    anchors={a['anchor']:a for a in schematic_view.scene(spec)['anchors']}
    assert anchors['R1.1']['position']==pytest.approx([200,170])
    assert anchors['R1.1']['escape']==pytest.approx([200,160])
    spec['editor']['connection_guides']=[{'from':'R1.1','to':'R2.1','waypoints':[
        anchors['R1.1']['escape'],[300,160],[300,100],[600,100],anchors['R2.1']['escape']]}]
    output=schematic.build(spec,tmp_path)
    assert output['pages'][0]['wiring']['routes'][0]['status']=='routed'
    sch=Path(output['sch']);assert_native_nets(spec,sch)
    checked=cli.erc(sch)
    assert not any(row['type']=='unconnected_wire_endpoint' for row in [*checked['errors'],*checked['warnings']])
