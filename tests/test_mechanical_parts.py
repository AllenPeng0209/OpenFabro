"""Editable mechanical programs must produce exact native solids, not concept meshes."""
import copy
import json
import math
from pathlib import Path

import pytest
from wholeboard import enclosure

try:
    from wholeboard import mechanical
except ImportError:
    mechanical = None


def engine():
    assert mechanical is not None, 'General editable mechanical CAD programs are missing'
    return mechanical


def program(features=None, parameters=None):
    return {'schema': 1, 'name': 'Mounting plate', 'units': 'mm',
            'parameters': parameters or {'width': {'value': 40, 'unit': 'mm'}, 'depth': {'value': 24, 'unit': 'mm'}, 'thickness': {'value': 4, 'unit': 'mm'}},
            'features': features or [{'id': 'plate', 'op': 'extrude', 'profile': {'kind': 'rectangle', 'width': 'width', 'height': 'depth'}, 'vector': [0, 0, 'thickness']}],
            'result': (features or [{'id': 'plate'}])[-1]['id']}


def test_editable_parameter_expressions_resolve_without_mutating_source():
    source = program()
    source['features'][0]['vector'][2] = 'thickness + width / 20'
    before = copy.deepcopy(source)
    resolved = engine().resolve(source)
    assert source == before
    assert resolved['features'][0]['vector'] == [0, 0, 6]
    assert resolved['features'][0]['profile']['width'] == 40
    assert resolved['parameters']['width'] == 40


@pytest.mark.parametrize('value', ['__import__("os").getcwd()', 'width.__class__', 'width[0]', 'missing + 1', '1/0', '10**10000', True, float('nan')])
def test_invalid_or_executable_dimension_expressions_are_rejected(value):
    source = program()
    source['features'][0]['vector'][2] = value
    with pytest.raises(ValueError):
        engine().resolve(source)


def test_forward_references_duplicate_ids_and_unknown_operations_are_rejected():
    for features in [[{'id': 'a', 'op': 'cut', 'target': 'future', 'tool': 'future'}],
                     [{'id': 'same', 'op': 'box', 'size': [10, 10, 2]}, {'id': 'same', 'op': 'box', 'size': [4, 4, 1]}],
                     [{'id': 'm', 'op': 'run_python', 'code': 'raise Exception()'}]]:
        with pytest.raises(ValueError):
            engine().resolve(program(features))


def test_actual_agent_profile_field_mismatch_explains_the_canonical_keys():
    source = program()
    source['features'][0]['profile'] = {'type':'rectangle','width':'width','height':'depth','origin3D':[0,0,0],'normal3D':[0,0,1]}
    with pytest.raises(ValueError) as error:
        engine().resolve(source)
    assert all(key in str(error.value) for key in ['kind', 'origin', 'normal']), str(error.value)


def native(source, folder):
    command = enclosure.find_freecad()
    if not command:
        pytest.skip('FreeCAD is not installed')
    result = engine().build(source, folder.resolve(), command=command)
    assert result['ok'] and result['valid'] and result['solids'] > 0 and result['volume_mm3'] > 0
    for name in ['part.step', 'part.stl', 'part.FCStd', 'scene.json', 'report.json', 'source.cad.json']:
        assert (folder / name).is_file() and (folder / name).stat().st_size > 20, name
    scene = json.loads((folder / 'scene.json').read_text())
    assert scene['source'] == 'native-freecad-mechanical' and scene['meshes'] and result['triangles'] > 0
    assert result['step_roundtrip']['valid'] and result['step_roundtrip']['solids'] == result['solids']
    assert result['step_roundtrip']['volume_mm3'] == pytest.approx(result['volume_mm3'], rel=1e-6)
    assert json.loads((folder / 'source.cad.json').read_text()) == source
    return result


def test_native_parametric_plate_rebuild_changes_dimensions_and_keeps_old_outputs(tmp_path):
    source = program()
    source['features'].append({'id': 'hole', 'op': 'hole', 'target': 'plate', 'diameter': 3.2, 'depth': 'thickness+2', 'origin': ['width/2', 'depth/2', -1]})
    source['result'] = 'hole'
    first = native(source, tmp_path / 'first')
    old_step = (tmp_path / 'first/part.step').read_bytes()
    assert first['size_mm'] == pytest.approx([40, 24, 4])
    assert first['volume_mm3'] == pytest.approx(40*24*4-math.pi*1.6**2*4, rel=1e-6)
    source['parameters']['thickness']['value'] = 6
    second = native(source, tmp_path / 'second')
    assert second['size_mm'] == pytest.approx([40, 24, 6])
    assert second['volume_mm3'] == pytest.approx(first['volume_mm3'] * 1.5, rel=1e-6)
    assert (tmp_path / 'first/part.step').read_bytes() == old_step


@pytest.mark.parametrize('features,solids', [
    ([{'id': 'r', 'op': 'revolve', 'profile': {'kind': 'rectangle', 'width': 4, 'height': 6, 'normal': [0, -1, 0]}, 'axis': [0, 0, 1], 'angle': 360}], 1),
    ([{'id': 'l', 'op': 'loft', 'profiles': [{'kind': 'rectangle', 'width': 12, 'height': 8}, {'kind': 'rectangle', 'width': 6, 'height': 4, 'origin': [0, 0, 10]}]}], 1),
    ([{'id': 's', 'op': 'sweep', 'profile': {'kind': 'circle', 'radius': 1}, 'path': [[0, 0, 0], [0, 0, 10], [8, 0, 10]]}], 1),
    ([{'id': 'b', 'op': 'box', 'size': [20, 16, 6]}, {'id': 's', 'op': 'shell', 'target': 'b', 'faces': 'top', 'thickness': 1}], 1),
    ([{'id': 'b', 'op': 'box', 'size': [20, 16, 6]}, {'id': 'f', 'op': 'fillet', 'target': 'b', 'edges': 'vertical', 'radius': 1}], 1),
    ([{'id': 'b', 'op': 'box', 'size': [20, 16, 6]}, {'id': 'c', 'op': 'chamfer', 'target': 'b', 'edges': 'vertical', 'distance': .5}], 1),
    ([{'id': 'c', 'op': 'cylinder', 'radius': 1, 'height': 4}, {'id': 'p', 'op': 'linear_pattern', 'target': 'c', 'count': 3, 'step': [5, 0, 0]}], 3),
    ([{'id': 'c', 'op': 'cylinder', 'radius': 1, 'height': 4, 'origin': [5, 0, 0]}, {'id': 'p', 'op': 'circular_pattern', 'target': 'c', 'count': 4, 'axis': [0, 0, 1], 'step_angle': 90}], 4),
])
def test_exact_native_modeling_operations(tmp_path, features, solids):
    result = native(program(features), tmp_path / 'model')
    assert result['solids'] == solids
    assert len(result['features']) == len(features)
    if features[0]['op'] == 'sweep':
        assert result['volume_mm3'] == pytest.approx(18*math.pi, rel=1e-6)


def test_failed_native_feature_does_not_silently_export_the_unmodified_shape(tmp_path):
    command = enclosure.find_freecad()
    if not command:
        pytest.skip('FreeCAD is not installed')
    source = program([{'id': 'b', 'op': 'box', 'size': [10, 10, 2]}, {'id': 'f', 'op': 'fillet', 'target': 'b', 'edges': 'vertical', 'radius': 100}])
    with pytest.raises((ValueError, RuntimeError), match='fillet|feature|radius|Failed|failed'):
        engine().build(source, (tmp_path/'bad').resolve(), command=command)
    assert not (tmp_path/'bad/part.step').exists()


def test_a_hole_outside_its_target_reports_no_material_removal(tmp_path):
    command = enclosure.find_freecad()
    if not command:
        pytest.skip('FreeCAD is not installed')
    source = program([{'id':'b','op':'box','size':[10,10,2]}, {'id':'h','op':'hole','target':'b','diameter':2,'depth':2,'origin':[20,20,0]}])
    with pytest.raises(RuntimeError, match='material|intersect|Hole'):
        engine().build(source, tmp_path/'missed_hole', command=command)
