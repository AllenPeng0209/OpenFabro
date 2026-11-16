"""Curvature comes from native placed curves, independently of viewport triangles."""
import copy
import hashlib
import json
import math
import pytest
from wholeboard import mechanical, codex_bridge
from test_mechanical_workflow import workspace
from test_mechanical_topology import scene


def cylinder():
    return {'schema': 1, 'name': 'Curve reference', 'units': 'mm', 'parameters': {},
            'features': [{'id': 'body', 'op': 'cylinder', 'radius': 4, 'height': 3}], 'result': 'body'}


def test_native_circle_and_straight_edge_curvature_do_not_use_faceted_mesh_estimates(workspace):
    _, p, _ = workspace
    built = mechanical.rebuild(p, {'path': 'cad/curve.cad.json', 'program': cylinder()})
    data = scene(p, built)
    edges = data['topology']['bodies'][0]['edges']
    for edge in edges:
        assert 'curvature' in edge, 'Native edge curvature is missing'
        c = edge['curvature']
        assert c['available'] and c['units'] == '1/mm' and c['method'] == 'native-parametric'
        assert 2 <= len(c['samples']) <= 65
        for sample in c['samples']:
            assert sample['curvature'] == pytest.approx(.25 if edge['surface'] == 'Circle' else 0, abs=1e-10)
            assert all(math.isfinite(v) for key in ('point', 'normal', 'tangent') for v in sample[key])
            point = [a+b for a,b in zip(sample['point'], data['origin'])]
            if sample['curvature']:
                assert sample['normal'] == pytest.approx([-point[0]/4, -point[1]/4, 0], abs=1e-8)
    assert p.state['workbench']['version'] == 1


def test_native_ellipse_retains_variable_curvature_instead_of_using_an_average_radius(workspace):
    _, p, _ = workspace
    code = {'schema': 1, 'name': 'Ellipse', 'units': 'mm', 'parameters': {}, 'features': [
        {'id': 'profile', 'op': 'sketch', 'geometry': [{'id': 'oval', 'type': 'ellipse', 'center': [0,0], 'major_radius': 8, 'minor_radius': 4}], 'constraints': []},
        {'id': 'body', 'op': 'extrude_shape', 'target': 'profile', 'vector': [0,0,2]}], 'result': 'body'}
    built = mechanical.rebuild(p, {'path': 'cad/ellipse.cad.json', 'program': code})
    edges = [e for e in scene(p, built)['topology']['bodies'][0]['edges'] if e['surface'] == 'Ellipse']
    assert edges
    for edge in edges:
        assert 'curvature' in edge, 'Ellipse curvature is missing'
        assert edge['curvature']['minimum'] == pytest.approx(4/8**2, rel=1e-8)
        assert edge['curvature']['maximum'] == pytest.approx(8/4**2, rel=1e-8)


def test_curve_inspection_is_read_only_hash_pinned_and_uses_rotated_instance_coordinates(workspace):
    _, p, _ = workspace
    mechanical.rebuild(p, {'path': 'cad/curve.cad.json', 'program': cylinder()})
    code = {'schema': 1, 'name': 'Placed curve', 'units': 'mm', 'parameters': {}, 'features': [
        {'id': 'part', 'op': 'component', 'source': {'kind': 'model', 'path': 'cad/curve.cad.json'},
         'translation': [100,200,10], 'rotation': {'axis': [1,0,0], 'angle': 90}},
        {'id': 'product', 'op': 'assembly', 'members': ['part'], 'fixed': ['part']}], 'result': 'product'}
    built = mechanical.rebuild(p, {'path': 'cad/product.cad.json', 'program': code})
    data = scene(p, built)
    edge = next(e for e in data['topology']['bodies'][0]['edges'] if e['surface'] == 'Circle')
    assert 'inspect_mechanical_curvature' in codex_bridge.READ_TOOLS, 'Agent needs bounded native curve evidence'
    before = copy.deepcopy(p.state)
    files = {f['path']: (hashlib.sha256((p.root/f['path']).read_bytes()).hexdigest(), (p.root/f['path']).stat().st_mtime_ns) for f in built['files']}
    args = {'source': 'cad/product.cad.json', 'body_id': 0, 'edge_index': edge['index'], 'limit': 3}
    result = codex_bridge.execute_tool(p, 'inspect_mechanical_curvature', args, 'chat')
    assert result['asset_id'] == built['asset_id'] and result['next_offset'] == 3
    assert result['member_id'] == 'part' and result['origin_mm'] == data['origin']
    assert len(result['samples']) == 3 and result['maximum'] == pytest.approx(.25)
    assert all(abs(v['normal'][1]) < 1e-9 for v in result['samples'])
    with pytest.raises(ValueError, match='changed|SHA|snapshot'):
        codex_bridge.execute_tool(p, 'inspect_mechanical_curvature', {**args, 'expected_scene_sha256': '0'*64}, 'chat')
    assert p.state == before
    for name, proof in files.items():
        path = p.root/name
        assert (hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns) == proof
