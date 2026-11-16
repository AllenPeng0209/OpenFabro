"""Imported exact geometry remains editable without rewriting its original asset."""
import base64
import copy
import gzip
import hashlib
import importlib
import io
import json
import math
from pathlib import Path
import zipfile

import pytest
from wholeboard import mechanical, mechanical_history, codex_bridge
from test_mechanical_workflow import workspace

FIXTURES = Path(__file__).parent/'fixtures/mechanical-import'


def assets():
    try:
        return importlib.import_module('wholeboard.mechanical_assets')
    except ModuleNotFoundError:
        pytest.fail('Native CAD asset import and editable import recipes are missing')


def upload(client, p, name='colored_assembly.step', data=None):
    response = client.post(f'/api/workbench/projects/{p.id}/mechanical/assets', json={
        'name': name, 'data': base64.b64encode(data if data is not None else (FIXTURES/name).read_bytes()).decode()})
    assert response.status_code == 200, response.text
    return response.json()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_exact_assembly_import_retains_original_names_colors_world_positions_and_reload(workspace):
    client, p, _ = workspace
    before, version = copy.deepcopy(p.state['spec']), p.state['workbench']['version']
    asset = assets().ingest(p, {'name':'colored_assembly.step', 'data':base64.b64encode((FIXTURES/'colored_assembly.step').read_bytes()).decode()})
    assert asset['metrics']['solids'] == 3
    assert asset['metrics']['volume_mm3'] == pytest.approx(1120+108*math.pi)
    assert asset['metrics']['origin_mm'] == pytest.approx([7,6,2])
    assert asset['metrics']['size_mm'] == pytest.approx([31,21,6])
    bodies = asset['bodies']
    assert [b['name'] for b in bodies] == ['Blue bracket','Red spacer A','Red spacer B']
    assert [b['color'] for b in bodies] == ['#1a4dcc','#cc331a','#cc331a']
    assert [b['origin_mm'] for b in bodies] == [[7,9,2],[32,6,2],[32,21,2]]
    original = p.root/asset['original']['path']
    assert original.read_bytes() == (FIXTURES/'colored_assembly.step').read_bytes()
    accepted = {f['path']:(sha(p.root/f['path']),(p.root/f['path']).stat().st_mtime_ns) for f in asset['files']}
    same = upload(client,p)
    assert same['asset_id'] == asset['asset_id']
    assert all((sha(p.root/n),(p.root/n).stat().st_mtime_ns)==v for n,v in accepted.items())
    inventory = client.get(f'/api/workbench/projects/{p.id}/mechanical/assets').json()
    assert inventory['assets'][0]['asset_id'] == asset['asset_id']
    scene = client.get(asset['scene_url']).json()
    assert len({m['body_id'] for m in scene['meshes']}) == 3
    assert {m['color'] for m in scene['meshes']} == {'#1a4dcc','#cc331a'}
    p.save(); reloaded = type(p)(p.root,json.loads((p.root/'state.json').read_text()))
    assert assets().listing(reloaded)['assets'][0]['asset_id'] == asset['asset_id']
    assert p.state['spec'] == before and p.state['workbench']['version'] == version
    assert not (p.root/'native').exists() and not p.state.get('workbench_mechanical')


@pytest.mark.parametrize('name,solids,volume,size',[
    ('bracket.brep',1,1120,[20,14,4]),('bracket.iges',1,1120,[20,14,4]),
    ('surface.brep',0,0,[12,10,0]),('surface.iges',0,0,[12,10,0])])
def test_exact_formats_distinguish_open_faces_from_solids(workspace,name,solids,volume,size):
    client,p,_=workspace
    value=upload(client,p,name)
    assert value['metrics']['valid'] and value['metrics']['solids']==solids
    assert value['metrics']['volume_mm3']==pytest.approx(volume)
    assert value['metrics']['size_mm']==pytest.approx(size)
    assert value['bodies'][0]['kind']==('solid' if solids else 'surface')


def test_imported_assembly_can_be_drilled_exported_and_undone_without_touching_original(workspace):
    client,p,_=workspace
    asset=upload(client,p)
    original=p.root/asset['original']['path']; original_before=(sha(original),original.stat().st_mtime_ns)
    result=client.post(f'/api/workbench/projects/{p.id}/mechanical/assets/part',json={
        'asset_id':asset['asset_id'],'path':'cad/imported.cad.json','name':'Imported assembly'})
    assert result.status_code==200,result.text
    first=result.json(); source=p.root/'cad/imported.cad.json'
    code=json.loads(source.read_text())
    assert code['features'][0]['op']=='import' and code['features'][0]['asset_id']==asset['asset_id']
    code['parameters']['hole_diameter']={'value':3.2,'unit':'mm'}
    code['features'].append({'id':'drilled','op':'hole','target':code['result'],'diameter':'hole_diameter','depth':6,'origin':[17,16,1]})
    code['result']='drilled'
    second=mechanical.rebuild(p,{'path':'cad/imported.cad.json','expected_sha256':sha(source),'program':code})
    assert second['metrics']['solids']==3
    assert second['metrics']['volume_mm3']==pytest.approx(1120+108*math.pi-math.pi*1.6**2*4,rel=1e-7)
    assert [b['name'] for b in second['metrics']['bodies']]==['Blue bracket','Red spacer A','Red spacer B']
    assert [b['color'] for b in second['metrics']['bodies']]==['#1a4dcc','#cc331a','#cc331a']
    assert [b['origin_mm'] for b in second['metrics']['bodies']]==[[7,9,2],[32,6,2],[32,21,2]]
    assert second['metrics']['step_roundtrip']['solids']==3
    assert second['metrics']['step_metadata_verified'] is True
    history=mechanical_history.summary(p)
    mechanical_history.restore(p,{'direction':'undo','revision':history['revision'],'entry_id':history['undo']['id']})
    assert p.state['workbench_mechanical']['cad/imported.cad.json']['asset_id']==first['asset_id']
    assert (sha(original),original.stat().st_mtime_ns)==original_before
    assert not (p.root/'native').exists()


def test_selected_imported_face_extrudes_into_an_editable_native_solid(workspace):
    client,p,_=workspace
    asset=upload(client,p,'surface.iges')
    program={'schema':1,'name':'Extruded imported face','units':'mm','parameters':{'height':{'value':3,'unit':'mm'}},
      'features':[{'id':'surface','op':'import','asset_id':asset['asset_id'],'bodies':[0]},
                  {'id':'solid','op':'extrude_shape','target':'surface','vector':[0,0,'height']}],'result':'solid'}
    result=mechanical.rebuild(p,{'path':'cad/surface.cad.json','program':program})
    assert result['metrics']['solids']==1 and result['metrics']['volume_mm3']==pytest.approx(360)
    assert result['metrics']['size_mm']==pytest.approx([12,10,3])


def test_compressed_step_preserves_original_and_limits_archive_payload(workspace):
    client,p,_=workspace
    raw=(FIXTURES/'colored_assembly.step').read_bytes()
    packed=gzip.compress(raw)
    asset=upload(client,p,'assembly.stpz',packed)
    assert asset['metrics']['solids']==3 and client.get(asset['original']['url']).content==packed
    buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,'w') as z:z.writestr('ISO10303.p21',raw)
    assert upload(client,p,'assembly_zip.stpz',buffer.getvalue())['metrics']['solids']==3
    buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,'w') as z:z.writestr('../outside.step',raw)
    response=client.post(f'/api/workbench/projects/{p.id}/mechanical/assets',json={'name':'bad.stpz','data':base64.b64encode(buffer.getvalue()).decode()})
    assert response.status_code==422


def test_corrupt_import_dependency_cannot_reuse_cached_model_or_change_source(workspace):
    client,p,_=workspace
    asset=upload(client,p)
    made=assets().create_part(p,{'asset_id':asset['asset_id'],'path':'cad/guarded.cad.json','name':'Guarded'})
    source=p.root/'cad/guarded.cad.json';before=source.read_bytes()
    (p.root/asset['original']['path']).write_bytes(b'corrupt')
    with pytest.raises((ValueError,RuntimeError),match='changed|integrity|hash|corrupt'):
        mechanical.rebuild(p,{'path':'cad/guarded.cad.json'})
    assert source.read_bytes()==before and p.state['workbench_mechanical']['cad/guarded.cad.json']['asset_id']==made['asset_id']
    assert not p.engine_busy


def test_invalid_or_canceled_import_publishes_no_assets_and_chat_is_read_only(workspace,monkeypatch):
    client,p,_=workspace
    module=assets()
    for body in [{'name':'../outside.step','data':'YQ=='},{'name':'x.f3d','data':'YQ=='},{'name':'x.step','data':'%%%'}]:
        assert client.post(f'/api/workbench/projects/{p.id}/mechanical/assets',json=body).status_code==422
    assert not module.listing(p)['assets']
    original=module.inspect_native
    def canceled(*args,**kwargs):
        result=original(*args,**kwargs);p.cancel.set();return result
    monkeypatch.setattr(module,'inspect_native',canceled)
    with pytest.raises((ValueError,RuntimeError),match='cancel'):
        module.ingest(p,{'name':'x.step','data':base64.b64encode((FIXTURES/'colored_assembly.step').read_bytes()).decode()})
    assert not module.listing(p)['assets'] and not p.engine_busy
    p.cancel.clear()
    with pytest.raises(ValueError,match='Chat mode'):
        codex_bridge.execute_tool(p,'create_part_from_asset',{'asset_id':'0'*64,'path':'cad/a.cad.json'},'chat')
    assert codex_bridge.execute_tool(p,'inspect_mechanical_assets',{},'chat')['assets']==[]


def test_uniform_face_color_and_repeated_step_instances_keep_native_geometry(workspace):
    client,p,_=workspace
    first_face=upload(client,p,'first_face_color.step')
    assert {m['color'] for m in client.get(first_face['scene_url']).json()['meshes']}=={'#1a4dcc','#cccccc'}
    repeated=upload(client,p,'nested.step')
    assert repeated['metrics']['solids']==2 and repeated['metrics']['volume_mm3']==pytest.approx(1600)
    assert [b['origin_mm'] for b in repeated['bodies']]==[[10,20,3],[30,20,3]]
    assert [b['size_mm'] for b in repeated['bodies']]==[[20,10,4],[20,10,4]]
    assert {m['color'] for m in client.get(repeated['scene_url']).json()['meshes']}=={'#cccccc'}


def test_per_face_color_survives_a_native_edit_and_step_roundtrip(workspace):
    client,p,_=workspace;asset=upload(client,p,'face_colors.step')
    program={'schema':1,'name':'Painted edit','units':'mm','parameters':{},'features':[
        {'id':'original','op':'import','asset_id':asset['asset_id']},
        {'id':'drilled','op':'hole','target':'original','origin':[10,7,-1],'diameter':3.2,'depth':6}],'result':'drilled'}
    result=mechanical.rebuild(p,{'path':'cad/painted.cad.json','program':program})
    assert result['metrics']['step_metadata_verified']
    assert {m['color'] for m in client.get(result['scene_url']).json()['meshes']}=={'#1a4dcc','#cc331a'}
    scene=client.get(result['scene_url']).json()
    top_colors=[]
    for mesh in scene['meshes']:
        for start in range(0,len(mesh['t']),3):
            if all(abs(mesh['v'][mesh['t'][start+i]*3+2]-4)<1e-6 for i in range(3)):
                top_colors.append(mesh['color'])
    assert top_colors and set(top_colors)=={'#1a4dcc'},'Drilling repainted the surviving blue top face'
    assert result['metrics']['bodies'][0]['name']=='Painted box'
    assert result['metrics']['volume_mm3']==pytest.approx(1120-math.pi*1.6**2*4)


def test_dependency_bytes_are_verified_after_the_receipt_read(workspace,monkeypatch):
    client,p,_=workspace;asset=upload(client,p)
    module=assets();native=p.root/asset['native']['path'];original=Path.read_bytes;reads=0
    def swapped(path):
        nonlocal reads
        raw=original(path)
        if path==native:
            reads+=1
            if reads==2:return (FIXTURES/'bracket.brep').read_bytes()
        return raw
    monkeypatch.setattr(Path,'read_bytes',swapped)
    with pytest.raises((ValueError,RuntimeError),match='changed|hash|integrity'):
        module.dependencies(p,{'features':[{'op':'import','asset_id':asset['asset_id']}]})


def test_agent_context_identifies_imported_assets_without_confusing_electrical_versions(workspace):
    client,p,_=workspace;asset=upload(client,p)
    prompt=codex_bridge.prompt_for(p,'Edit the imported blue bracket','agent')
    context=json.loads(prompt.split('PROJECT CONTEXT (reference data):\n',1)[1].split('\n\nUSER REQUEST:',1)[0])
    inventory=context['engineering_evidence'].get('mechanical_imports',{})
    assert inventory.get('total')==1 and inventory['assets'][0]['asset_id']==asset['asset_id']
    assert inventory['assets'][0]['body_names']==['Blue bracket','Red spacer A','Red spacer B']
