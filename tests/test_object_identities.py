"""Object selection must identify native objects independently of list positions."""
from pathlib import Path
import hashlib
import json
import copy

from wholeboard import sexpr
from wholeboard.kicad import geometry
from wholeboard import server
from test_workbench import client, draft
from test_project_library import custom_spec
from wholeboard.kicad import board


PCB = '''(kicad_pcb (version 20241229) (generator pcbnew)
 (layers (0 "F.Cu" signal) (2 "B.Cu" signal))
 (gr_rect (start 0 0) (end 30 20) (layer "Edge.Cuts") (uuid "outline-id"))
 (footprint "Fixture:Connector" (layer "F.Cu") (at 10 10) (uuid "footprint-id")
  (property "Reference" "J1" (at 0 -2) (layer "F.SilkS") (effects (font (size 1 1))) (uuid "reference-id"))
  (fp_line (start -1 -1) (end 3 -1) (stroke (width 0.1)) (layer "F.SilkS") (uuid "line-id"))
  (pad "1" smd rect (at 0 0) (size 1 1) (layers "F.Cu") (net "SIG") (uuid "pad-a"))
  (pad "1" smd rect (at 2 0) (size 1 1) (layers "F.Cu") (net "SIG") (uuid "pad-b")))
 (segment (start 10 10) (end 12 10) (width 0.25) (layer "F.Cu") (net "SIG") (uuid "trace-id"))
 (zone (net "SIG") (layer "F.Cu") (uuid "zone-id")
  (polygon (pts (xy 2 2) (xy 28 2) (xy 28 18) (xy 2 18)))
  (filled_polygon (layer "F.Cu") (pts (xy 2 2) (xy 8 2) (xy 8 8) (xy 2 8)))
  (filled_polygon (layer "F.Cu") (pts (xy 20 12) (xy 28 12) (xy 28 18) (xy 20 18))))
 (zone (net "") (layer "B.Cu") (uuid "keepout-id") (keepout (tracks not_allowed))
  (polygon (pts (xy 3 3) (xy 5 3) (xy 5 5) (xy 3 5)))))'''


def read(tmp_path: Path, source=PCB):
    path = tmp_path / "objects.kicad_pcb"
    path.write_text(source)
    return geometry.read(path)


def test_native_object_ids_retain_duplicate_numbered_pad_identities(tmp_path):
    scene = read(tmp_path)
    assert scene["footprints"][0].get("id") == "footprint-id"
    assert [p["name"] for p in scene["pads"]] == ["1", "1"]
    assert {p.get("id") for p in scene["pads"]} == {"pad-a", "pad-b"}
    assert {p.get("id") for p in scene["drawings"]} == {"reference-id", "line-id"}
    assert scene["outline"][0].get("id") == "outline-id"
    assert scene["tracks"][0]["id"] == "trace-id"


def test_zones_retain_one_definition_and_distinct_filled_islands(tmp_path):
    scene = read(tmp_path)
    definitions = {item["id"]: item for item in scene.get("zone_definitions", [])}
    assert set(definitions) == {"zone-id", "keepout-id"}, "Unfilled zones must remain selectable"
    assert definitions["zone-id"]["net"] == "SIG"
    assert definitions["zone-id"]["layers"] == ["F.Cu"]
    assert definitions["keepout-id"]["keepout"] is True
    assert definitions["zone-id"]["polygons"][0][0] == [2, 2]
    assert {item.get("zone_id") for item in scene["zones"]} == {"zone-id"}
    assert len({item.get("id") for item in scene["zones"]}) == 2


def test_reordering_source_objects_preserves_the_object_id_map(tmp_path):
    before = read(tmp_path)
    tree = sexpr.parse(PCB)
    for item in tree:
        if sexpr.tag(item) == "footprint":
            item[2:] = reversed(item[2:])
        if sexpr.tag(item) == "zone":
            item[1:] = reversed(item[1:])
    tree[1:] = reversed(tree[1:])
    after = read(tmp_path, sexpr.dumps(tree))
    for collection in ("pads", "footprints", "tracks", "drawings", "outline", "zones", "zone_definitions"):
        assert all(item.get("id") for item in before[collection]), collection
        assert {item["id"]: item for item in before[collection]} == {item["id"]: item for item in after[collection]}


def test_legacy_identity_is_stable_across_whitespace_and_parent_translation(tmp_path):
    tree = sexpr.parse(PCB)
    for node in sexpr.walk(tree):
        if isinstance(node, list):
            node[:] = [value for value in node if sexpr.tag(value) != "uuid"]
    first = read(tmp_path, sexpr.dumps(tree))
    fp = next(item for item in tree if sexpr.tag(item) == "footprint")
    sexpr.find(fp, "at")[1:3] = [sexpr.Sym("12"), sexpr.Sym("14")]
    fp[2:] = reversed(fp[2:])
    moved = read(tmp_path, sexpr.dumps(tree).replace(")", ")\n"))
    for collection in ("pads", "drawings"):
        assert all(item.get("id") for item in first[collection]), "UUID-less objects need deterministic identities"
        assert {item["id"] for item in first[collection]} == {item["id"] for item in moved[collection]}
    assert [p["x"] for p in moved["pads"]] != [p["x"] for p in first["pads"]]


def test_legacy_copper_tstamp_is_stable_when_geometry_changes(tmp_path):
    source = PCB.replace('(uuid "trace-id")', '(tstamp "1234abcd")')
    before = read(tmp_path, source)["tracks"][0]
    after = read(tmp_path, source.replace('(end 12 10) (width 0.25)', '(end 14 10) (width 0.25)'))["tracks"][0]
    assert before.get("id"), "Legacy tstamp must not collapse every track to a null identity"
    assert before["id"] == after["id"]
    assert before["b"] != after["b"]


def test_schema_three_geometry_upgrade_adds_ids_without_rewriting_native_snapshots(client):
    made = draft(client)
    pid = made["id"]
    native = client.post(f"/api/workbench/projects/{pid}/native").json()
    project = server.mgr().get(pid)
    old = Path(native["geometry_file"])
    legacy = json.loads(old.read_text())
    legacy["schema"] = 3
    legacy.pop("zone_definitions", None)
    for collection in ("pads", "footprints", "drawings", "outline", "zones"):
        for item in legacy[collection]:
            item.pop("id", None)
            item.pop("zone_id", None)
    old.write_text(json.dumps(legacy))
    project.state["workbench_native"] = {**native, "geometry_schema": 3}
    project.save()
    files = [Path(native["pcb"]), Path(native["sch"]), old]
    hashes = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in files}
    response = client.post(f"/api/workbench/projects/{pid}/native")
    assert response.status_code == 200, response.text
    refreshed = response.json()
    current = json.loads(Path(refreshed["geometry_file"]).read_text())
    assert current["schema"] > 3
    for collection in ("pads", "footprints", "drawings", "outline"):
        assert current[collection] and all(item.get("id") for item in current[collection])
    assert Path(refreshed["geometry_file"]) != old
    assert all(hashlib.sha256(path.read_bytes()).hexdigest() == digest for path, digest in hashes.items())
    assert project.state["spec"] == made["spec"] and project.state["workbench"]["version"] == 1
    stamp = Path(refreshed["geometry_file"]).stat().st_mtime_ns
    assert client.post(f"/api/workbench/projects/{pid}/native").json()["geometry_file"] == refreshed["geometry_file"]
    assert Path(refreshed["geometry_file"]).stat().st_mtime_ns == stamp


def test_airwire_records_retain_net_membership_and_the_same_island_connections(tmp_path):
    tree = sexpr.parse(PCB)
    tree[:] = [item for item in tree if sexpr.tag(item) not in ("segment", "zone")]
    fp = next(item for item in tree if sexpr.tag(item) == "footprint")
    for number, x in (("3", 0), ("4", 4)):
        fp.append(sexpr.parse(f'(pad "{number}" smd rect (at {x} 8) (size 1 1) (layers "F.Cu") (net "GND"))'))
    result = read(tmp_path, sexpr.dumps(tree))
    records = result.get("airwire_objects", [])
    assert {item["net"] for item in records} == {"SIG", "GND"}
    assert [[item["a"], item["b"]] for item in records] == result["ratsnest"]


def test_regenerated_native_object_ids_survive_other_edits_placement_and_component_order(tmp_path):
    spec = custom_spec()
    spec["board"]["ground_pour"] = "GND"
    spec["board"]["planes"] = {"B.Cu": "GND"}
    second = copy.deepcopy(spec["components"][0])
    second.update(ref="U2", placement={"x_mm": 6, "y_mm": 6})
    spec["components"].append(second)
    spec["nets"][0]["pins"].append("U2.1")
    spec["nets"][1]["pins"].append("U2.2")
    duplicate = copy.deepcopy(spec["library"]["footprints"]["DemoFP"]["pads"][0])
    duplicate.update(x=0, y=2)
    spec["library"]["footprints"]["DemoFP"]["pads"].append(duplicate)
    spec["fixed_copper"] = [{"net": "SIGNAL", "tracks": [{"id": "12345678-1234-4234-8234-123456789abc", "a": [8, 11], "b": [20, 11], "w": .25, "layer": "F.Cu"}]}]
    before = geometry.read(Path(board.build(spec, tmp_path / "a")["pcb"]))
    changed = copy.deepcopy(spec)
    changed["fixed_copper"][0]["tracks"][0]["w"] = .4
    changed["components"][0]["value"] = "New display value"
    changed["components"][0]["placement"].update(x_mm=17, rotation=90, side="bottom")
    changed["components"].reverse()
    after = geometry.read(Path(board.build(changed, tmp_path / "b")["pcb"]))
    for collection in ("footprints", "pads", "drawings", "outline", "zone_definitions"):
        assert before[collection], collection
        assert {item["id"] for item in before[collection]} == {item["id"] for item in after[collection]}, collection
        assert len({item["id"] for item in before[collection]}) == len(before[collection]), collection
    assert before["tracks"][0]["id"] == after["tracks"][0]["id"] == "12345678-1234-4234-8234-123456789abc"
    assert before["tracks"][0]["w"] != after["tracks"][0]["w"]


def test_uuidless_fixed_copper_gets_distinct_repeatable_native_ids(tmp_path):
    spec = custom_spec()
    track = {"a": [2, 18], "b": [8, 18], "w": .25, "layer": "F.Cu"}
    spec["fixed_copper"] = [{"net": "SIGNAL", "tracks": [copy.deepcopy(track), copy.deepcopy(track)], "arcs": [{"a": [12, 18], "m": [13, 19], "b": [14, 18], "w": .25, "layer": "F.Cu"}], "vias": [{"p": [8, 18], "d": .8, "drill": .4}]}]
    before = geometry.read(Path(board.build(spec, tmp_path / "a")["pcb"]))
    spec["summary"] = "An unrelated metadata edit"
    after = geometry.read(Path(board.build(spec, tmp_path / "b")["pcb"]))
    for kind in ("tracks", "arcs", "vias"):
        assert {item["id"] for item in before[kind]} == {item["id"] for item in after[kind]}, kind
        assert len({item["id"] for item in before[kind]}) == len(before[kind]), kind


def test_returning_to_a_prior_design_never_rewrites_its_native_snapshot(client):
    made = draft(client)
    pid = made["id"]
    original = client.post(f"/api/workbench/projects/{pid}/native").json()
    files = [Path(original[key]) for key in ("pcb", "sch", "geometry_file")]
    before = {str(path): (hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns) for path in files}
    geometry_before = json.loads(Path(original["geometry_file"]).read_text())
    edited = copy.deepcopy(made["spec"])
    edited["summary"] = "An intermediate saved revision"
    response = client.put(f"/api/workbench/projects/{pid}/design", json={"base_version": 1, "spec": edited})
    assert response.status_code == 200, response.text
    assert client.post(f"/api/workbench/projects/{pid}/native").status_code == 200
    assert client.put(f"/api/workbench/projects/{pid}/design", json={"base_version": 2, "spec": made["spec"]}).status_code == 200
    response = client.post(f"/api/workbench/projects/{pid}/native")
    assert response.status_code == 200, response.text
    after = {str(path): (hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns) for path in files}
    assert after == before, "A historical native snapshot was overwritten while regenerating the restored spec"
    current = response.json()
    assert json.loads(Path(current["geometry_file"]).read_text()) == geometry_before
    stamp = Path(current["geometry_file"]).stat().st_mtime_ns
    assert client.post(f"/api/workbench/projects/{pid}/native").json()["geometry_file"] == current["geometry_file"]
    assert Path(current["geometry_file"]).stat().st_mtime_ns == stamp
