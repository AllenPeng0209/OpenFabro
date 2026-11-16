"""Native PCB display must retain actual footprint graphics and their transforms."""
from wholeboard.kicad import geometry
from wholeboard.kicad import cli
import pytest
import subprocess


def test_pad_drill_geometry_retains_numeric_atoms_slots_and_local_offsets(tmp_path):
    pcb=tmp_path/'pad-drills.kicad_pcb'
    pcb.write_text('''(kicad_pcb (version 20241229) (generator pcbnew)
      (gr_rect (start 0 0) (end 30 20) (layer "Edge.Cuts"))
      (footprint "Fixture:Holes" (layer "F.Cu") (at 10 10)
        (property "Reference" "J1")
        (pad "1" thru_hole circle (at 0 0) (size 1.7 1.7) (drill 1) (layers "*.Cu" "*.Mask"))
        (pad "2" np_thru_hole oval (at 4 0 90) (size 1.2 2.4) (drill oval 0.8 1.8 (offset 0.15 -0.2)) (layers "*.Cu" "*.Mask"))
        (pad "3" smd rect (at 8 0) (size 1 1) (layers "F.Cu" "F.Mask"))))''')
    pads=geometry.read(pcb)['pads']
    assert [p['drill'] for p in pads]==[1,.8,0], 'Textual KiCad numeric drill atoms must not become zero'
    assert pads[0]['drill_shape']=='circle' and pads[0]['drill_size']==[1,1] and pads[0]['drill_offset']==[0,0]
    # KiCad's offset moves copper relative to the hole anchor. Browser coordinates use
    # the copper center and the opposite local hole offset (verified by native plots).
    assert pads[1]['drill_shape']=='oval' and pads[1]['drill_size']==[.8,1.8] and pads[1]['drill_offset']==[-.15,.2]
    assert [pads[1]['x'],pads[1]['y']]==[13.8,9.85]
    assert [pads[1]['x']+pads[1]['drill_offset'][1],pads[1]['y']-pads[1]['drill_offset'][0]]==[14,10]
    assert pads[2]['drill_size']==[0,0]


def test_board_display_preserves_rotated_silkscreen_shapes_and_text(tmp_path):
    pcb = tmp_path / "display.kicad_pcb"
    pcb.write_text('''(kicad_pcb (version 20241229) (generator wholeboard)
      (layers (0 "F.Cu" signal) (2 "B.Cu" signal) (37 "F.SilkS" user))
      (gr_rect (start 0 0) (end 30 22) (layer "Edge.Cuts"))
      (footprint "Test:Part" (layer "F.Cu") (at 10 20 90)
        (property "Reference" "U1" (at 0 -2 90) (layer "F.SilkS") (effects (font (size 1 1))))
        (fp_line (start 0 0) (end 1 0) (stroke (width 0.12) (type solid)) (layer "F.SilkS"))
        (fp_rect (start 0 0) (end 1 2) (stroke (width 0.1) (type solid)) (fill none) (layer "F.Fab"))
        (fp_circle (center 0 0) (end 1 0) (stroke (width 0.1) (type solid)) (fill none) (layer "F.SilkS"))
      ))''')
    scene = geometry.read(pcb)
    assert "drawings" in scene, "Native footprint outlines are absent from the board geometry"
    line = next(g for g in scene["drawings"] if g["kind"] == "line")
    assert line["start"] == [10, 20]
    assert line["end"] == [10, 19]
    assert line["layer"] == "F.SilkS"
    assert line["ref"] == "U1"
    rect = next(g for g in scene["drawings"] if g["kind"] == "poly")
    assert [12, 19] in rect["points"]
    text = next(g for g in scene["drawings"] if g["kind"] == "text")
    assert text["text"] == "U1"
    assert text["at"] == [8, 20]
    assert text["angle"] == 90


def test_board_display_resolves_legacy_net_numbers_and_retains_blind_via_layers(tmp_path):
    pcb = tmp_path / "legacy.kicad_pcb"
    pcb.write_text('''(kicad_pcb (version 20221018) (generator pcbnew)
      (layers (0 "F.Cu" signal) (1 "In1.Cu" signal) (31 "B.Cu" signal))
      (net 1 "GND")
      (segment (start 10 10) (end 12 10) (width 0.3) (layer "F.Cu") (net 1))
      (via blind (at 12 10) (size 0.6) (drill 0.3) (layers "F.Cu" "In1.Cu") (net 1)))''')
    scene = geometry.read(pcb)
    assert scene["tracks"][0]["net"] == "GND"
    assert scene["vias"][0]["net"] == "GND"
    assert scene["vias"][0]["layers"] == ["F.Cu", "In1.Cu"]
    assert scene["vias"][0]["type"] == "blind"


@pytest.mark.parametrize("kind", ["erc", "drc"])
def test_failed_kicad_invocation_cannot_return_an_old_success_report(tmp_path, monkeypatch, kind):
    source = tmp_path / ("source.kicad_sch" if kind == "erc" else "source.kicad_pcb")
    source.write_text("unreadable source")
    source.with_suffix(f".{kind}.json").write_text('{"violations": [], "unconnected_items": [], "sheets": []}')
    monkeypatch.setattr(cli, "run", lambda args, **kw: subprocess.CompletedProcess(args, 2, stdout="", stderr="parse failed"))
    with pytest.raises(cli.KiCadError, match="failed"):
        getattr(cli, kind)(source)
