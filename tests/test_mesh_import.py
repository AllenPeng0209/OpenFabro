"""Mesh assets keep physical scale, instances, paint, resources and editable geometry."""
import base64
import copy
import importlib
import json
import math
from pathlib import Path

import pytest
from wholeboard import mechanical,mechanical_assets
from test_mechanical_workflow import workspace

FIXTURES=Path(__file__).parent/'fixtures/mesh-import'


def importer():
    try:return importlib.import_module('wholeboard.mesh_assets')
    except ModuleNotFoundError:pytest.fail('Mesh asset geometry and material import is missing')


def raw(name):return (FIXTURES/name).read_bytes()


def test_glb_and_gltf_apply_meters_y_up_nested_instances_and_linear_paint():
    module=importer()
    for name,resources in [('assembly.glb',{}),('embedded.gltf',{}),('assembly.gltf',{'geometry.bin':raw('geometry.bin')})]:
        value=module.convert(name,raw(name),resources=resources)
        assert value['schema']==1 and value['units']=='mm' and value['geometry_kind']=='triangle-mesh'
        bodies=value['bodies'];assert [b['name'] for b in bodies]==['Bracket A','Bracket B']
        assert bodies[0]['origin_mm']==pytest.approx([7,9,2],abs=1e-5)
        assert bodies[0]['size_mm']==pytest.approx([20,14,4],abs=1e-5)
        assert bodies[1]['origin_mm']==pytest.approx([23,9,2],abs=1e-5)
        assert bodies[1]['size_mm']==pytest.approx([14,10,4],abs=1e-5)
        assert [b['volume_mm3'] for b in bodies]==pytest.approx([1120,560],rel=1e-6)
        assert all(b['watertight'] and b['winding_consistent'] and b['can_make_solid'] for b in bodies)
        assert bodies[0]['preview_meshes'][0]['color']=='#5995e7'


@pytest.mark.parametrize('name',['bracket.stl','bracket_binary.stl'])
def test_ascii_and_binary_stl_are_welded_for_topology_and_have_explicit_units(name):
    value=importer().convert(name,raw(name),units='mm')
    body=value['bodies'][0]
    assert body['watertight'] and body['volume_mm3']==pytest.approx(1120)
    assert body['size_mm']==pytest.approx([20,14,4])
    assert value['source_units']=='mm' and value['units_assumed']
    inches=importer().convert(name,raw(name),units='in')['bodies'][0]
    assert inches['size_mm']==pytest.approx([508,355.6,101.6])


def test_obj_material_texture_and_open_surface_keep_their_distinct_meaning():
    module=importer()
    plain=module.convert('bracket.obj',raw('bracket.obj'),resources={'colors.mtl':raw('colors.mtl')})
    assert plain['bodies'][0]['name']=='Blue bracket' and plain['bodies'][0]['watertight']
    assert plain['bodies'][0]['preview_meshes'][0]['color']=='#1a4dcc'
    textured=module.convert('textured.obj',raw('textured.obj'),resources={n:raw(n) for n in ['texture.mtl','checker.png']})
    mesh=textured['bodies'][0]['preview_meshes'][0]
    assert mesh['texture'].startswith('data:image/png;base64,') and len(mesh['uv'])==len(mesh['v'])//3*2
    seams={}
    for index in range(len(mesh['v'])//3):seams.setdefault(tuple(mesh['v'][index*3:index*3+3]),set()).add(tuple(mesh['uv'][index*2:index*2+2]))
    assert any(len(uvs)>1 for uvs in seams.values()),'OBJ UV seams collapsed onto one texture coordinate'
    assert textured['appearance']['textures_preserved'] and textured['appearance']['native_edit_appearance']=='per-face approximation'
    opened=module.convert('open.obj',raw('open.obj'))['bodies'][0]
    assert not opened['watertight'] and not opened['can_make_solid'] and opened['volume_mm3'] is None


def test_missing_or_external_companion_resources_fail_explicitly_without_disk_or_network_reads(monkeypatch):
    module=importer()
    for uri in ['https://example.invalid/stolen.bin','file:///etc/passwd','../outside.bin']:
        source=json.loads(raw('assembly.gltf'));source['buffers'][0]['uri']=uri
        with pytest.raises(ValueError,match='resource|relative|external|path'):
            module.convert('model.gltf',json.dumps(source).encode())
    for name in ['assembly.gltf','bracket.obj','textured.obj']:
        with pytest.raises(ValueError,match='resource|missing|Missing'):
            module.convert(name,raw(name))


def test_percent_encoded_gltf_and_nested_obj_texture_paths_preserve_resource_pixels():
    module=importer();gltf=json.loads(raw('assembly.gltf'));gltf['buffers'][0]['uri']='geometry%20file.bin'
    assert module.convert('model.gltf',json.dumps(gltf).encode(),resources={'geometry file.bin':raw('geometry.bin')})['bodies'][0]['watertight']
    obj=raw('textured.obj').replace(b'texture.mtl',b'materials/texture.mtl')
    mtl=raw('texture.mtl').replace(b'checker.png',b'textures/checker.png')
    value=module.convert('model.obj',obj,resources={'materials/texture.mtl':mtl,'materials/textures/checker.png':raw('checker.png')})
    assert value['bodies'][0]['preview_meshes'][0].get('texture'),'Nested material texture silently disappeared'


def test_obj_vertex_colors_remain_in_the_preview_and_native_face_approximation():
    obj=raw('bracket.obj').decode().replace('mtllib colors.mtl\n','').replace('usemtl blue\n','')
    lines=[]
    for line in obj.splitlines():lines.append(line+' 1 0 0' if line.startswith('v ') else line)
    value=importer().convert('painted.obj','\n'.join(lines).encode())
    body=value['bodies'][0];preview=body['preview_meshes'][0]
    assert preview['c'] and len(preview['c'])==len(preview['v'])
    assert all(color[:3]==[1,0,0] for color in body['face_colors'])


def test_malformed_gltf_accessor_counts_reject_before_allocating_mesh_buffers(monkeypatch):
    module=importer();tree=json.loads(raw('embedded.gltf'));tree['accessors'][0]['count']=2_000_001;tree['accessors'][0].pop('bufferView')
    original=module.np.zeros
    def bounded(shape,*args,**kwargs):
        if isinstance(shape,(int,module.np.integer)) and shape>5_000_000:raise AssertionError('Attempted forbidden large allocation')
        return original(shape,*args,**kwargs)
    monkeypatch.setattr(module.np,'zeros',bounded)
    with pytest.raises(ValueError,match='accessor|budget|count|buffer'):
        module.convert('oversized.gltf',json.dumps(tree).encode())


def test_mesh_asset_retains_companions_and_native_edit_is_marked_as_faceted(workspace):
    client,p,_=workspace
    body={'name':'bracket.obj','data':base64.b64encode(raw('bracket.obj')).decode(),
          'resources':{'colors.mtl':base64.b64encode(raw('colors.mtl')).decode()},'units':'mm'}
    result=client.post(f'/api/workbench/projects/{p.id}/mechanical/assets',json=body)
    assert result.status_code==200,result.text
    asset=result.json();assert asset['geometry_kind']=='triangle-mesh'
    assert client.get(asset['original']['url']).content==raw('bracket.obj')
    assert client.get(asset['resources'][0]['url']).content==raw('colors.mtl')
    record=mechanical_assets.create_part(p,{'asset_id':asset['asset_id'],'path':'cad/mesh.cad.json','name':'Imported mesh bracket'})
    source=p.root/'cad/mesh.cad.json';program=json.loads(source.read_text());program['features'].append({'id':'hole','op':'hole','target':program['result'],'diameter':3.2,'depth':6,'origin':[10,7,-1]});program['result']='hole'
    import hashlib
    second=mechanical.rebuild(p,{'path':'cad/mesh.cad.json','program':program,'expected_sha256':hashlib.sha256(source.read_bytes()).hexdigest()})
    assert second['metrics']['volume_mm3']==pytest.approx(1120-math.pi*1.6**2*4,rel=1e-6)
    assert second['metrics']['geometry_provenance']=='faceted-mesh-input'
    assert second['metrics']['step_roundtrip']['valid'] and second['metrics']['step_face_colors_verified']
    assert p.state['workbench']['version']==1 and not (p.root/'native').exists()
    assert len(mechanical.listing(p)['parts'][0]['versions'])==2


def test_embedded_gltf_upload_publishes_two_instances_at_the_correct_millimeter_positions(workspace):
    client,p,_=workspace
    response=client.post(f'/api/workbench/projects/{p.id}/mechanical/assets',json={'name':'assembly.glb','data':base64.b64encode(raw('assembly.glb')).decode()})
    assert response.status_code==200,response.text
    asset=response.json();assert asset['bodies'][0]['origin_mm']==pytest.approx([7,9,2],abs=1e-5)
    built=mechanical_assets.create_part(p,{'asset_id':asset['asset_id'],'path':'cad/assembly.cad.json'})
    assert built['metrics']['solids']==2 and built['metrics']['volume_mm3']==pytest.approx(1680,rel=1e-6)
    assert [b['name'] for b in built['metrics']['bodies']]==['Bracket A','Bracket B']


def test_native_textured_mesh_keeps_original_uv_preview_and_explicit_step_color_approximation(workspace):
    _,p,_=workspace
    asset=mechanical_assets.ingest(p,{'name':'textured.obj','data':base64.b64encode(raw('textured.obj')).decode(),
        'resources':{name:base64.b64encode(raw(name)).decode() for name in ['texture.mtl','checker.png']}})
    result=mechanical_assets.create_part(p,{'asset_id':asset['asset_id'],'path':'cad/textured.cad.json','name':'Textured bracket'})
    assert result['metrics']['solids']==1 and result['metrics']['volume_mm3']==pytest.approx(1120)
    assert result['metrics']['step_face_colors_verified'] and result['metrics']['geometry_provenance']=='faceted-mesh-input'
    scene=json.loads((p.root/next(f['path'] for f in result['files'] if f['name']=='scene.json')).read_text())
    assert any(m.get('texture') and m.get('uv') for m in scene['meshes'])


def test_two_closed_shells_that_only_touch_at_one_vertex_stay_separate_bodies():
    vertices=[];faces=[]
    for line in raw('bracket.obj').decode().splitlines():
        if line.startswith('v '):vertices.append([float(v) for v in line.split()[1:]])
        if line.startswith('f '):faces.append([int(v) for v in line.split()[1:]])
    shifted=[[x+20,y+14,z+4] for x,y,z in vertices]
    source='o Touching shells\n'+'\n'.join('v '+' '.join(map(str,v)) for v in vertices+shifted)+'\n'+'\n'.join('f '+' '.join(str(i+offset) for i in face) for offset in [0,8] for face in faces)
    value=importer().convert('touch.obj',source.encode())
    assert len(value['bodies'])==2 and all(b['can_make_solid'] for b in value['bodies'])


def test_invalid_mesh_structure_is_a_user_error_and_never_publishes_a_model(workspace):
    client,p,_=workspace;tree=json.loads(raw('embedded.gltf'));tree['asset']=None
    response=client.post(f'/api/workbench/projects/{p.id}/mechanical/assets',json={'name':'bad.gltf','data':base64.b64encode(json.dumps(tree).encode()).decode()})
    assert response.status_code==422 and not p.engine_busy and not mechanical_assets.listing(p)['assets']


def test_gltf_default_material_and_alpha_modes_follow_the_declared_format():
    module=importer();tree=json.loads(raw('embedded.gltf'));tree.pop('materials');tree['meshes'][0]['primitives'][0].pop('material')
    material=module.convert('default.gltf',json.dumps(tree).encode())['bodies'][0]['preview_meshes'][0]
    assert material['color']=='#ffffff' and material['roughness']==1 and material['metalness']==1
    for mode,opacity,cutoff,blend in [('OPAQUE',1,0,False),('BLEND',.4,0,True),('MASK',.4,.5,False)]:
        tree=json.loads(raw('embedded.gltf'));tree['materials'][0]['alphaMode']=mode;tree['materials'][0]['pbrMetallicRoughness']['baseColorFactor'][3]=.4
        material=module.convert('alpha.gltf',json.dumps(tree).encode())['bodies'][0]['preview_meshes'][0]
        assert material['opacity']==opacity and material.get('alpha_test',0)==cutoff and material['transparent']==blend
