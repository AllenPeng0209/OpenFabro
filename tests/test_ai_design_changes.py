"""AI design changes retain immutable provenance for own-tab review and undo."""
import copy
import json
import pytest
from wholeboard import server,codex_bridge
from test_workbench import client
from test_parametric_symbols import fixture


def make(client):
    made=client.post('/api/workbench/projects',json={'title':'AI edit provenance','spec':fixture()}).json();return made['id'],server.mgr().get(made['id'])


def test_ai_proposal_records_own_request_and_preserves_earlier_snapshot(client):
    from wholeboard import design_origin
    _,p=make(client);old=p.root/'history/design-v1.json';identity=(old.read_bytes(),old.stat().st_mtime_ns);changed=copy.deepcopy(p.state['spec']);changed['editor']['positions']['R1'][0]+=100
    with design_origin.scope(p,'a'*32):codex_bridge.apply_result(p,{'message':'Move','design_json':json.dumps(changed),'files':[]},'agent',1)
    snapshot=json.loads((p.root/'history/design-v2.json').read_text());assert snapshot['origin']['request_id']=='a'*32 and snapshot['origin']['provider']=='codex'
    change=p.state['ai_design_changes'][-1];assert change['from_version']==1 and change['version']==2 and change['request_id']=='a'*32
    assert any(e.get('type')=='design_saved' and e.get('request_id')=='a'*32 and e.get('version')==2 for e in p.events)
    assert (old.read_bytes(),old.stat().st_mtime_ns)==identity


def test_noop_and_chat_do_not_create_design_changes(client):
    from wholeboard import design_origin
    _,p=make(client)
    with design_origin.scope(p,'a'*32):
        codex_bridge.apply_result(p,{'message':'No change','design_json':json.dumps(p.state['spec']),'files':[]},'agent',1)
        codex_bridge.apply_result(p,{'message':'Discuss','design_json':json.dumps(p.state['spec']),'files':[]},'chat',1)
    assert not p.state.get('ai_design_changes') and p.state['workbench']['version']==1


def test_queued_instruction_is_attributed_to_its_own_request(client,monkeypatch):
    _,p=make(client);changed=copy.deepcopy(p.state['spec']);changed['editor']['positions']['R1'][0]+=100;p.inbox=[{'text':'Move','mode':'agent','source_request_id':'b'*32}]
    monkeypatch.setattr(codex_bridge,'request_once',lambda *args,**kwargs:{'message':'Moved','design_json':json.dumps(changed),'files':[],'tools':[],'review':[]})
    codex_bridge.run(p,'Earlier request','agent',source_request_id='a'*32)
    assert p.state['ai_design_changes'][-1]['request_id']=='b'*32


def test_design_history_compares_two_frozen_versions_after_newer_saves(client):
    pid,p=make(client);second=copy.deepcopy(p.state['spec']);second['editor']['positions']['R1'][0]+=100
    client.put(f'/api/workbench/projects/{pid}/design',json={'base_version':1,'spec':second});third=copy.deepcopy(second);third['board']['width_mm']=41;client.put(f'/api/workbench/projects/{pid}/design',json={'base_version':2,'spec':third})
    result=client.get(f'/api/workbench/projects/{pid}/history/1/compare?to_version=2').json()
    assert result['to_version']==2 and result['field_change_count']==1 and result['field_changes'][0]['path']=='/editor/positions/R1/0'
    assert p.state['workbench']['version']==3
