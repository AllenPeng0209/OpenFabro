"""Native references must identify the selected source geometry after assembly placement."""
import copy,hashlib,json
from pathlib import Path
import pytest
from wholeboard import mechanical,codex_bridge
from test_mechanical_workflow import workspace
from test_assemblies import make_box


def scene(p,model):
    return json.loads((p.root/next(f['path'] for f in model['files'] if f['name']=='scene.json')).read_text())


def product():
    return {'schema':1,'units':'mm','name':'Picked assembly','parameters':{},'features':[
      {'id':'base','op':'component','label':'Base','source':{'kind':'model','path':'cad/base.cad.json'},'translation':[100,200,10]},
      {'id':'cap','op':'component','label':'Cap','source':{'kind':'model','path':'cad/cap.cad.json'},'translation':[110,204,30],'rotation':{'axis':[0,0,1],'angle':90}},
      {'id':'product','op':'assembly','members':['base','cap'],'fixed':['base'],'clearance_mm':.4}], 'result':'product'}


def prepare(p):
    make_box(p,'cad/base.cad.json','Base',[20,16,3]);make_box(p,'cad/cap.cad.json','Cap',[8,6,2])
    return mechanical.rebuild(p,{'path':'cad/product.cad.json','program':product()})


def body(data,member):
    assert 'topology' in data,'Native previews must expose source face/edge references'
    return next(b for b in data['topology']['bodies'] if b['member_id']==member)


def face(data,member,normal):
    return next(f for f in body(data,member)['faces'] if f.get('selector',{}).get('normal')==normal)


def test_native_pick_map_connects_rendered_triangles_to_source_local_faces(workspace):
    _,p,_=workspace;built=prepare(p);data=scene(p,built)
    top=face(data,'base',[0,0,1]);cap=face(data,'cap',[0,0,-1])
    assert top['point']==pytest.approx([110,208,13])
    assert cap['point']==pytest.approx([107,208,30])
    assert top['selector']['point']==pytest.approx([10,8,3]) and cap['selector']['point']==pytest.approx([4,3,0])
    assert top['selector']['body_index']==0 and top['selector']['reference']['surface']=='Plane'
    assert top['selector'].get('body_instance'),'Selected bodies must retain physical instance identity, including repeated definitions'
    assert len(body(data,'base')['edges'])==12
    for mesh in data['meshes']:
        covered=sum(row[2] for row in mesh['face_ranges']);assert covered==len(mesh['t'])//3
        refs=next(b for b in data['topology']['bodies'] if b['body_id']==mesh['body_id'])
        assert all(row[0]<len(refs['faces']) for row in mesh['face_ranges'])


def test_selected_face_pair_solves_and_tracks_a_plate_thickness_change(workspace):
    _,p,_=workspace;built=prepare(p);data=scene(p,built);code=product();code['features'][-1]['mates']=[{'id':'picked','type':'coincident','target':'cap','reference':'base','target_anchor':face(data,'cap',[0,0,-1])['selector'],'reference_anchor':face(data,'base',[0,0,1])['selector'],'offset':1}]
    source=p.root/'cad/product.cad.json';first=mechanical.rebuild(p,{'path':'cad/product.cad.json','program':code,'expected_sha256':hashlib.sha256(source.read_bytes()).hexdigest()})
    assert first['metrics']['assembly']['members'][1]['origin_mm'][2]==pytest.approx(14)
    base=p.root/'cad/base.cad.json';changed=json.loads(base.read_text());changed['features'][0]['size'][2]=5
    mechanical.rebuild(p,{'path':'cad/base.cad.json','program':changed,'expected_sha256':hashlib.sha256(base.read_bytes()).hexdigest()})
    second=mechanical.rebuild(p,{'path':'cad/product.cad.json'});assert second['metrics']['assembly']['members'][1]['origin_mm'][2]==pytest.approx(16)
    assert second['metrics']['assembly']['fit']['pairs'][0]['distance_mm']==pytest.approx(1)


def test_changed_reference_signature_fails_without_publishing_a_wrong_mate(workspace):
    _,p,_=workspace;built=prepare(p);data=scene(p,built);code=product();selected=copy.deepcopy(face(data,'base',[0,0,1])['selector']);selected['reference']['position']=[.5,.5,0]
    code['features'][-1]['mates']=[{'id':'wrong','type':'coincident','target':'cap','reference':'base','target_anchor':face(data,'cap',[0,0,-1])['selector'],'reference_anchor':selected}]
    source=p.root/'cad/product.cad.json';before=source.read_bytes()
    with pytest.raises((ValueError,RuntimeError),match='reference|selected|topology'):
        mechanical.rebuild(p,{'path':'cad/product.cad.json','program':code,'expected_sha256':hashlib.sha256(before).hexdigest()})
    assert source.read_bytes()==before and p.state['workbench_mechanical']['cad/product.cad.json']['asset_id']==built['asset_id']


def test_changed_physical_instance_cannot_bind_a_pick_to_an_identical_definition(workspace):
    _,p,_=workspace;built=prepare(p);data=scene(p,built);code=product();selected=copy.deepcopy(face(data,'base',[0,0,1])['selector']);assert selected.get('body_instance'),'Physical instance identity is missing';selected['body_instance']='another-instance-of-the-same-part'
    code['features'][-1]['mates']=[{'id':'wrong_instance','type':'coincident','target':'cap','reference':'base','target_anchor':face(data,'cap',[0,0,-1])['selector'],'reference_anchor':selected}]
    source=p.root/'cad/product.cad.json';before=source.read_bytes()
    with pytest.raises((ValueError,RuntimeError),match='instance'):
        mechanical.rebuild(p,{'path':'cad/product.cad.json','program':code,'expected_sha256':hashlib.sha256(before).hexdigest()})
    assert source.read_bytes()==before and p.state['workbench_mechanical']['cad/product.cad.json']['asset_id']==built['asset_id']


def test_mate_dispatch_rejects_a_preview_with_changed_dependencies(workspace):
    _,p,_=workspace;built=prepare(p);data=scene(p,built);base=p.root/'cad/base.cad.json';code=json.loads(base.read_text());code['features'][0]['size'][2]=5
    mechanical.rebuild(p,{'path':'cad/base.cad.json','program':code,'expected_sha256':hashlib.sha256(base.read_bytes()).hexdigest()})
    source=p.root/'cad/product.cad.json';before=source.read_bytes()
    with pytest.raises(mechanical.MechanicalConflict,match='preview|source.*changed|rebuild.*before'):
        mechanical.rebuild(p,{'path':'cad/product.cad.json','program':product(),'expected_sha256':hashlib.sha256(before).hexdigest(),'expected_asset_id':built['asset_id']})
    assert source.read_bytes()==before and p.state['workbench_mechanical']['cad/product.cad.json']['asset_id']==built['asset_id']


def test_circular_edge_selection_provides_a_native_concentric_axis(workspace):
    _,p,_=workspace
    ring={'schema':1,'units':'mm','name':'Ring','parameters':{},'features':[{'id':'outer','op':'cylinder','radius':5,'height':3},{'id':'hole','op':'cylinder','radius':2,'height':3},{'id':'ring','op':'cut','target':'outer','tool':'hole'}],'result':'ring'}
    shaft={'schema':1,'units':'mm','name':'Shaft','parameters':{},'features':[{'id':'shaft','op':'cylinder','radius':1.5,'height':3}],'result':'shaft'}
    mechanical.rebuild(p,{'path':'cad/ring.cad.json','program':ring});mechanical.rebuild(p,{'path':'cad/shaft.cad.json','program':shaft})
    code={'schema':1,'units':'mm','name':'Circular references','parameters':{},'features':[{'id':'ring','op':'component','source':{'kind':'model','path':'cad/ring.cad.json'}},{'id':'shaft','op':'component','source':{'kind':'model','path':'cad/shaft.cad.json'},'translation':[7,4,0]},{'id':'product','op':'assembly','members':['ring','shaft'],'fixed':['ring'],'clearance_mm':.2}],'result':'product'}
    initial=mechanical.rebuild(p,{'path':'cad/axis.cad.json','program':code});data=scene(p,initial)
    assert all('radius_mm' in edge for edge in body(data,'ring')['edges'] if edge['surface']=='Circle'),'Circular references need native radii, not display-curve estimates'
    def circular(member,radius):
        return next(e for e in body(data,member)['edges'] if e['surface']=='Circle' and e['selector']['reference']['position'][2]<.01 and e['radius_mm']==radius)
    moving=circular('shaft',1.5)['selector'];fixed=circular('ring',2)['selector'];assert moving['kind']==fixed['kind']=='axis'
    code['features'][-1]['mates']=[{'id':'picked_axis','type':'concentric','target':'shaft','reference':'ring','target_anchor':moving,'reference_anchor':fixed}]
    source=p.root/'cad/axis.cad.json';final=mechanical.rebuild(p,{'path':'cad/axis.cad.json','program':code,'expected_sha256':hashlib.sha256(source.read_bytes()).hexdigest()})
    assert final['metrics']['assembly']['fit']['pairs'][0]['distance_mm']==pytest.approx(.5,abs=1e-6)
    assert final['metrics']['assembly']['solver']['mates'][0]['target_anchor']['signature_verified']


def test_read_only_agent_inspects_hash_pinned_native_elements_without_mesh_payloads(workspace):
    _,p,_=workspace;built=prepare(p);assert 'inspect_mechanical_topology' in codex_bridge.READ_TOOLS,'The Agent needs bounded access to real source references'
    args={'source':'cad/product.cad.json','member_id':'cap','entity':'face','limit':1};first=codex_bridge.execute_tool(p,'inspect_mechanical_topology',args,'chat')
    assert first['asset_id']==built['asset_id'] and first['total']==6 and len(first['elements'])==1 and first['next_offset']==1
    ref=first['elements'][0];assert ref['member_id']=='cap' and 'v' not in ref and ref['selector']['body_index']==0
    second=codex_bridge.execute_tool(p,'inspect_mechanical_topology',{**args,'offset':1,'expected_scene_sha256':first['scene_sha256']},'chat');assert second['elements'][0]['index']!=ref['index']
    with pytest.raises(ValueError,match='changed|SHA|snapshot'):
        codex_bridge.execute_tool(p,'inspect_mechanical_topology',{**args,'expected_scene_sha256':'0'*64},'chat')
    assert p.state['workbench']['version']==1 and not p.engine_busy
