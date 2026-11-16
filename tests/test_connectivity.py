"""Airwires reflect physical copper islands; native DRC remains authoritative."""
import json
from pathlib import Path

from wholeboard.kicad.geometry import ratsnest


def pad(ref, x, y, *, layer="F.Cu", **kwargs):
    return {"ref": ref, "name": "1", "net": "NET", "x": x, "y": y, "w": 1, "h": 1,
            "shape": "rect", "kind": "smd", "rot": 0, "front": layer == "F.Cu", "back": layer == "B.Cu", **kwargs}


def scene(pads, tracks=None, vias=None, zones=None, arcs=None):
    return {"layers": ["F.Cu", "B.Cu"], "pads": pads, "tracks": tracks or [], "vias": vias or [], "zones": zones or [], "arcs": arcs or []}


def track(a, b, layer="F.Cu", w=.25):
    return {"net": "NET", "a": a, "b": b, "w": w, "layer": layer}


def test_connected_pads_are_one_island_and_only_the_remaining_gap_has_an_airwire():
    geometry = scene([pad("P1", 0, 0), pad("P2", 5, 0), pad("P3", 10, 0)], [track([0, 0], [5, 0])])
    lines = ratsnest(geometry)
    assert len(lines) == 1
    assert {tuple(p) for p in lines[0]} == {(5, 0), (10, 0)}


def test_crossing_layers_stay_separate_until_through_vias_connect_them():
    geometry = scene([pad("P1", 0, 0), pad("P2", 5, 0)], [track([0, 0], [5, 0], "B.Cu")])
    assert ratsnest(geometry)
    geometry["vias"] = [{"net": "NET", "p": [x, 0], "d": .6, "drill": .3, "layers": ["F.Cu", "B.Cu"]} for x in (0, 5)]
    assert ratsnest(geometry) == []


def test_actual_same_layer_track_intersections_connect_without_matching_endpoints():
    geometry = scene([pad("P1", 0, -5), pad("P2", 5, 0)], [track([0, -5], [0, 5]), track([-5, 0], [5, 0])])
    assert ratsnest(geometry) == []


def test_filled_copper_connects_only_its_own_net():
    zone = {"net": "NET", "layer": "F.Cu", "pts": [[-1, -1], [11, -1], [11, 1], [-1, 1]]}
    geometry = scene([pad("P1", 0, 0), pad("P2", 10, 0)], zones=[zone])
    assert ratsnest(geometry) == []
    zone["net"] = "OTHER"
    assert len(ratsnest(geometry)) == 1


def test_track_contact_uses_the_rotated_pad_shape_not_just_its_center():
    geometry = scene([pad("P1", 0, 0, w=4, h=1, rot=90), pad("P2", 5, 0)], [track([0, 1.5], [5, 0])])
    assert ratsnest(geometry) == []


def test_a_round_pad_corner_does_not_join_copper_outside_its_shape():
    geometry = scene([pad("P1", 0, 0, w=2, h=2, shape="roundrect", rratio=.5), pad("P2", 5, 0)], [track([.9, .9], [5, 0], w=.1)])
    assert ratsnest(geometry)


def test_arc_copper_connects_pads_at_its_endpoints_and_middle():
    geometry = scene([pad("P1", 0, 0), pad("P2", 10, 0), pad("P3", 5, 5)],
                     arcs=[{"net": "NET", "layer": "F.Cu", "a": [0, 0], "m": [5, 5], "b": [10, 0], "w": .25}])
    assert ratsnest(geometry) == []


def test_real_routed_board_has_no_airwires_when_its_native_drc_has_no_unconnected_items():
    fixture = json.loads((Path(__file__).parent / "fixtures/routed-usb-c-geometry.json").read_text())
    assert fixture["expected_unconnected"] == 0
    assert ratsnest(fixture["geometry"]) == []
