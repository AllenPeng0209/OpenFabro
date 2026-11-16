import copy,hashlib,json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from wholeboard import config,enclosure,project,server,mechanical
from test_mechanical_parts import program

try:
    from wholeboard import mechanical_history as history
except ImportError:
    history=None

def journal():
    assert history is not None,'Mechanical source/model Undo/Redo is missing'
    return history

@pytest.fixture
def workspace(tmp_path,monkeypatch):
    if not enclosure.find_freecad():pytest.skip('FreeCAD is not installed')
    monkeypatch.setattr(config,'APP_DIR',tmp_path);monkeypatch.setattr(config,'CONFIG_FILE',tmp_path/'config.json')
    config.update({'projects_dir':str(tmp_path/'projects')});monkeypatch.setattr(server,'manager',project.Manager());client=TestClient(server.app)
    made=client.post('/api/workbench/projects',json={'title':'Mechanical history','spec':{'name':'mechanical_history','board':{'width_mm':40,'height_mm':30,'layers':2},'components':[],'nets':[]}}).json();p=server.mgr().get(made['id']);return client,p

def current(p):
    target=p.root/'cad/plate.cad.json'
    return target.read_bytes() if target.exists() else None,(p.state.get('workbench_mechanical') or {}).get('cad/plate.cad.json',{}).get('asset_id')

def build(p,thickness):
    value=program();value['parameters']['thickness']['value']=thickness;before=current(p)[0]
    return mechanical.rebuild(p,{'path':'cad/plate.cad.json','program':value,**({'expected_sha256':hashlib.sha256(before).hexdigest()} if before is not None else {})})

def restore(p,direction='undo',summary=None):
    state=summary or journal().summary(p)
    return journal().restore(p,{'direction':direction,'revision':state['revision'],'entry_id':state[direction]['id']})

def test_parameter_undo_restores_exact_source_and_asset_without_native_rebuild(workspace,monkeypatch):
    _,p=workspace;spec=copy.deepcopy(p.state['spec']);first=build(p,4);before=current(p);second=build(p,6);after=current(p)
    assert journal().summary(p)['count']==2
    def no_native(*args,**kwargs):raise AssertionError('Undo must reuse the verified immutable native asset')
    monkeypatch.setattr(mechanical,'build',no_native)
    result=restore(p);assert current(p)==before and result['asset']['asset_id']==first['asset_id']
    restore(p,'redo');assert current(p)==after and after[1]==second['asset_id']
    assert p.state['spec']==spec and p.state['workbench']['version']==1 and not(p.root/'native').exists()

def test_source_save_and_rebuild_undo_restore_the_intermediate_stale_state(workspace):
    client,p=workspace;build(p,4);before=current(p);source=json.loads(before[0]);source['parameters']['thickness']['value']=8
    saved=client.put(f'/api/workbench/projects/{p.id}/text/cad/plate.cad.json',json={'content':json.dumps(source,indent=2),'base_sha':hashlib.sha256(before[0]).hexdigest()});assert saved.status_code==200
    stale=current(p);assert mechanical.listing(p)['parts'][0]['stale']
    rebuilt=mechanical.rebuild(p,{'path':'cad/plate.cad.json'});assert rebuilt['metrics']['size_mm'][2]==8
    restore(p);assert current(p)==stale and mechanical.listing(p)['parts'][0]['stale']
    restore(p);assert current(p)==before and not mechanical.listing(p)['parts'][0]['stale']
    restore(p,'redo');assert current(p)==stale
    restore(p,'redo');assert current(p)[1]==rebuilt['asset_id'] and not mechanical.listing(p)['parts'][0]['stale']

def test_creation_undo_removes_source_and_pointer_but_keeps_all_native_exports(workspace):
    _,p=workspace;asset=build(p,4);saved=current(p);files={f['path']:(hashlib.sha256((p.root/f['path']).read_bytes()).hexdigest(),(p.root/f['path']).stat().st_mtime_ns) for f in asset['files']}
    restore(p);assert current(p)==(None,None) and journal().summary(p)['can_redo']
    assert all((hashlib.sha256((p.root/name).read_bytes()).hexdigest(),(p.root/name).stat().st_mtime_ns)==value for name,value in files.items())
    restore(p,'redo');assert current(p)==saved

def test_history_survives_project_reload_and_new_edits_invalidate_only_redo(workspace):
    _,p=workspace;build(p,4);second=build(p,6);restore(p)
    disk=json.loads((p.root/'state.json').read_text());reloaded=project.Project(p.root,disk)
    assert journal().summary(reloaded)['can_redo']
    third=build(reloaded,8);assert third['asset_id']!=second['asset_id'] and not journal().summary(reloaded)['can_redo']
    assert (p.root/'mechanical'/second['asset_id']/'part.step').is_file()
    restore(reloaded);assert json.loads(current(reloaded)[0])['parameters']['thickness']['value']==4

def test_stale_revision_and_external_source_changes_never_get_overwritten(workspace):
    _,p=workspace;build(p,4);old=journal().summary(p);build(p,6)
    with pytest.raises(ValueError,match='changed|history|revision'):restore(p,summary=old)
    source=p.root/'cad/plate.cad.json';source.write_bytes(source.read_bytes()+b'\n');snapshot=current(p)
    state=journal().summary(p);assert not state['can_undo']
    with pytest.raises(ValueError,match='changed|source'):restore(p,summary=state)
    assert current(p)==snapshot

def test_corrupt_target_asset_blocks_restore_without_rewriting_source(workspace):
    _,p=workspace;first=build(p,4);build(p,6);snapshot=current(p);(p.root/'mechanical'/first['asset_id']/'part.step').write_bytes(b'corrupt')
    with pytest.raises(ValueError,match='changed|asset|integrity'):restore(p)
    assert current(p)==snapshot

def test_restore_failure_rolls_back_source_pointer_cursor_and_disk_state(workspace,monkeypatch):
    _,p=workspace;build(p,4);build(p,6);before=current(p);state=copy.deepcopy(p.state);original=p.save
    def fail_save():
        if current(p)!=before:raise OSError('Injected journal restore persistence failure')
        return original()
    monkeypatch.setattr(p,'save',fail_save)
    with pytest.raises(OSError,match='Injected'):restore(p)
    assert current(p)==before and p.state==state and json.loads((p.root/'state.json').read_text())['mechanical_history']==state['mechanical_history']

def test_mechanical_history_api_restores_code_and_model_and_rejects_busy_runs(workspace):
    client,p=workspace;build(p,4);state=client.get(f'/api/workbench/projects/{p.id}/mechanical/history');assert state.status_code==200
    info=state.json();body={'direction':'undo','revision':info['revision'],'entry_id':info['undo']['id']}
    p.engine_busy=True;assert client.post(f'/api/workbench/projects/{p.id}/mechanical/history/restore',json=body).status_code==409;p.engine_busy=False
    response=client.post(f'/api/workbench/projects/{p.id}/mechanical/history/restore',json=body);assert response.status_code==200,response.text
    assert current(p)==(None,None) and response.json()['history']['can_redo']


def test_direct_agent_cad_file_edit_and_file_restore_stay_in_the_cad_journal(workspace):
    _,p=workspace;build(p,4);before=current(p)
    from wholeboard import ai_changes,codex_bridge,design_origin
    value=program();value['parameters']['thickness']['value']=8;request_id='b'*32
    with design_origin.scope(p,request_id):
        codex_bridge.apply_result(p,{'message':'','design_json':None,'tools':[],'review':[],'files':[{'path':'cad/plate.cad.json','content':json.dumps(value,indent=2)}]},'agent',1,codex_bridge.file_versions(p))
    assert journal().summary(p)['count']==2 and mechanical.listing(p)['parts'][0]['stale']
    receipt=ai_changes.review(p,request_id)
    ai_changes.restore(p,request_id,{'direction':'undo','base_version':receipt['current_version'],'receipt_sha256':receipt['receipt_sha256']})
    assert journal().summary(p)['count']==3 and current(p)==before
    restore(p);assert json.loads(current(p)[0])['parameters']['thickness']['value']==8 and current(p)[1]==before[1]


def test_corrupt_source_snapshot_and_notification_failure_do_not_erase_changes(workspace,monkeypatch):
    _,p=workspace;build(p,4);build(p,6);state=journal().summary(p)
    emit=p.emit
    def broken(event):
        if event.get('type') in ('mechanical_asset','mechanical_history_changed','file_saved'):raise OSError('Injected restore notification failure')
        return emit(event)
    monkeypatch.setattr(p,'emit',broken);result=restore(p);assert result['asset']['metrics']['size_mm'][2]==4 and result['history']['can_redo']
    entry=p.state['mechanical_history']['entries'][1];data=json.loads((p.root/'history/mechanical/entries'/(entry['id']+'.json')).read_text());blob=p.root/'history/mechanical/blobs'/(data['after']['sha256']+'.txt');blob.write_bytes(b'corrupt')
    with pytest.raises(ValueError,match='snapshot|source|changed'):restore(p,'redo')


def test_agent_history_tools_share_the_manual_restoration_guards(workspace):
    _,p=workspace;build(p,4)
    from wholeboard import codex_bridge
    state=codex_bridge.execute_tool(p,'inspect_mechanical_history',{},'chat')
    body={'direction':'undo','revision':state['revision'],'entry_id':state['undo']['id']}
    with pytest.raises(ValueError,match='Chat mode'):codex_bridge.execute_tool(p,'restore_mechanical_change',body,'chat')
    codex_bridge.execute_tool(p,'restore_mechanical_change',body,'agent')
    assert current(p)==(None,None)
