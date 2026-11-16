import copy
import json
from pathlib import Path

import pytest

from test_workbench import client
from wholeboard import codex_bridge,server


def make(client):
    spec=json.loads((Path(__file__).parent/'fixtures/route-tuning.json').read_text())
    pid=client.post('/api/workbench/projects',json={'title':'Native route tuning','spec':spec}).json()['id']
    response=client.get(f'/api/workbench/projects/{pid}/layout-geometry');assert response.status_code==200,response.text
    return pid,server.mgr().get(pid),response.json()


@pytest.mark.parametrize('nets,target',[(['CLK'],55),(['DP','DN'],50)])
def test_native_review_proves_pin_membership_length_drc_and_leaves_saved_source_and_cache_exact(client,nets,target):
    pid,p,before=make(client);original=copy.deepcopy(p.state['spec']);frozen={f:(f.read_bytes(),f.stat().st_mtime_ns) for kind in ['native','history'] for f in (p.root/kind).rglob('*') if f.is_file()}
    response=client.post(f'/api/workbench/projects/{pid}/route-tuning/prepare',json={'base_version':1,'nets':nets,'target_mm':target,'tolerance_mm':.01})
    assert response.status_code==200,response.text
    result=response.json();assert result['base_version']==1 and result['native_parity']['ok'] and result['safe_to_apply']
    assert result['drc']['errors']==result['drc']['unconnected']==0
    assert all(abs(row['after_length_mm']-target)<=.01 for row in result['summary']['measurements'])
    assert p.state['spec']==original and p.state['workbench']['version']==1
    assert all((f.read_bytes(),f.stat().st_mtime_ns)==value for f,value in frozen.items())
    for key in ['board','rules','components','nets']:assert result['spec'][key]==original[key]
    untouched={'DP','DN','CLK','REF'}-set(nets)
    for net in untouched:
        for kind in ['tracks','arcs','vias']:assert [v for v in result['geometry'][kind] if v['net']==net]==[v for v in before['geometry'][kind] if v['net']==net]
    assert client.put(f'/api/workbench/projects/{pid}/design',json={'base_version':1,'spec':result['spec']}).status_code==200
    final=client.post(f'/api/workbench/projects/{pid}/native-checks').json();assert final['drc']['errors']==final['drc']['unconnected']==0


def test_preparation_rejects_stale_versions_and_in_flight_source_replacement(client,monkeypatch):
    from wholeboard import route_tuning
    pid,p,_=make(client);body={'base_version':0,'nets':['CLK'],'target_mm':55}
    assert client.post(f'/api/workbench/projects/{pid}/route-tuning/prepare',json=body).status_code==409
    original=route_tuning.prepare
    def replaced(spec,geo,args):
        result=original(spec,geo,args);new=copy.deepcopy(p.state['spec']);new['rules']['track_mm']=.35
        assert client.put(f'/api/workbench/projects/{pid}/design',json={'base_version':1,'spec':new}).status_code==200
        return result
    monkeypatch.setattr(route_tuning,'prepare',replaced);body['base_version']=1
    response=client.post(f'/api/workbench/projects/{pid}/route-tuning/prepare',json=body);assert response.status_code==409,response.text
    assert p.state['workbench']['version']==2 and p.state['spec']['rules']['track_mm']==.35


def test_agent_tuning_preview_is_read_only_chat_is_blocked_and_real_apply_is_one_version(client):
    pid,p,_=make(client);args={'nets':['CLK'],'target_mm':55,'tolerance_mm':.01,'preview_only':True};original=copy.deepcopy(p.state['spec'])
    with pytest.raises(ValueError,match='Chat'):codex_bridge.execute_tool(p,'tune_route_lengths',args,'chat')
    result=codex_bridge.execute_tool(p,'tune_route_lengths',args,'agent');assert result['preview_only'] and result['safe_to_apply'] and p.state['spec']==original and p.state['workbench']['version']==1
    args['preview_only']=False;applied=codex_bridge.execute_tool(p,'tune_route_lengths',args,'agent');assert applied['ok'] and applied['version']==2
    inspected=codex_bridge.execute_tool(p,'inspect_route_lengths',{},'chat');assert inspected.get('pending'),'A pre-edit native cache cannot be presented as current length proof'
    client.get(f'/api/workbench/projects/{pid}/layout-geometry');inspected=codex_bridge.execute_tool(p,'inspect_route_lengths',{},'chat');row=next(r for r in inspected['routes'] if r['net']=='CLK');assert row['length_mm']==pytest.approx(55,abs=.01)


def test_agent_rechecks_native_identity_at_acceptance_after_preparation(client,monkeypatch):
    from wholeboard import route_tuning
    from fastapi import HTTPException
    pid,p,_=make(client);original=route_tuning.project_draft;before=copy.deepcopy(p.state['spec'])
    def replaced(*args):
        result=original(*args);pcb=Path(p.state['workbench_native']['pcb']);pcb.write_bytes(pcb.read_bytes()+b'\n');return result
    monkeypatch.setattr(route_tuning,'project_draft',replaced)
    with pytest.raises(HTTPException) as error:codex_bridge.execute_tool(p,'tune_route_lengths',{'nets':['CLK'],'target_mm':55},'agent')
    assert error.value.status_code==409 and p.state['workbench']['version']==1 and p.state['spec']==before


@pytest.mark.parametrize('interrupt',['cancel','inbox'])
def test_agent_preview_honors_cancellation_that_arrived_during_native_preparation(client,monkeypatch,interrupt):
    from wholeboard import route_tuning
    pid,p,_=make(client);original=route_tuning.project_draft
    def cancelled(*args):
        result=original(*args)
        if interrupt=='cancel':p.cancel.set()
        else:p.inbox.append('New instruction')
        return result
    monkeypatch.setattr(route_tuning,'project_draft',cancelled)
    with pytest.raises(InterruptedError):codex_bridge.execute_tool(p,'tune_route_lengths',{'nets':['CLK'],'target_mm':55,'preview_only':True},'agent')
    assert p.state['workbench']['version']==1


def test_ui_save_guard_rejects_a_native_pcb_changed_since_review(client):
    from wholeboard import design_identity
    pid,p,captured=make(client);body={'base_version':1,'nets':['CLK'],'target_mm':55};review=client.post(f'/api/workbench/projects/{pid}/route-tuning/prepare',json=body).json();before=copy.deepcopy(p.state['spec']);pcb=Path(p.state['workbench_native']['pcb']);pcb.write_bytes(pcb.read_bytes()+b'\n')
    guard={'source_identity':design_identity.fields(before),'source_pcb_sha256':captured['pcb_sha256'],'source_render_inputs_sha256':captured['render_inputs_sha256']}
    response=client.put(f'/api/workbench/projects/{pid}/design',json={'base_version':1,'spec':review['spec'],'native_source':guard})
    assert response.status_code==409,response.text
    assert p.state['spec']==before and p.state['workbench']['version']==1


def test_viewer_can_read_route_lengths_but_cannot_prepare_or_apply(client):
    from fastapi.testclient import TestClient
    pid,p,_=make(client);grant=client.post(f'/api/workbench/projects/{pid}/shares',json={'role':'viewer','days':1}).json();viewer=TestClient(server.app,client=('192.0.2.22',5000));assert viewer.post('/api/workbench/session/share',json={'token':grant['path'].split('=',1)[1]}).status_code==200
    assert viewer.get(f'/api/workbench/projects/{pid}/route-tuning').status_code==200
    assert viewer.post(f'/api/workbench/projects/{pid}/route-tuning/prepare',json={'base_version':1,'nets':['CLK'],'target_mm':55}).status_code==403
    assert viewer.put(f'/api/workbench/projects/{pid}/design',json={'base_version':1,'spec':p.state['spec']}).status_code==403
    assert p.state['workbench']['version']==1


@pytest.mark.parametrize('layer',['F.Cu','B.Cu'])
def test_tuning_preserves_and_refills_existing_foreign_pours_instead_of_blocking_every_board(client,layer):
    spec=json.loads((Path(__file__).parent/'fixtures/route-tuning.json').read_text());spec['fixed_zones']=[{'net':'REF','origin':[100,100],'source':f'(zone (net "REF") (layer "{layer}") (uuid "55555555-5555-4555-8555-000000000001") (hatch edge 0.5) (connect_pads (clearance 0.25)) (min_thickness 0.2) (fill yes (thermal_gap 0.3) (thermal_bridge_width 0.4)) (polygon (pts (xy 100.5 100.5) (xy 159.5 100.5) (xy 159.5 144.5) (xy 100.5 144.5))))'}]
    pid=client.post('/api/workbench/projects',json={'title':'Tuning with preserved pour','spec':spec}).json()['id'];p=server.mgr().get(pid);before=client.get(f'/api/workbench/projects/{pid}/layout-geometry').json()['geometry'];native_files={f:(f.read_bytes(),f.stat().st_mtime_ns) for f in (p.root/'native').rglob('*') if f.is_file()}
    response=client.post(f'/api/workbench/projects/{pid}/route-tuning/prepare',json={'base_version':1,'nets':['CLK'],'target_mm':55,'tolerance_mm':.01});assert response.status_code==200,response.text
    result=response.json();assert result['safe_to_apply'] and result['drc']['errors']==0 and result['drc']['unconnected']==0
    assert result['geometry']['zone_sources']==before['zone_sources']
    assert any(z['net']=='REF' and z['layer']==layer for z in result['geometry']['zones'])
    assert all((f.read_bytes(),f.stat().st_mtime_ns)==value for f,value in native_files.items())


def test_native_rounded_pair_has_consistent_bus_and_route_length_delay_results(client):
    from wholeboard import buses,route_tuning
    pid,p,_=make(client);response=client.post(f'/api/workbench/projects/{pid}/route-tuning/prepare',json={'base_version':1,'nets':['DP','DN'],'target_mm':50,'tolerance_mm':.01});assert response.status_code==200,response.text
    result=response.json();routes={row['net']:row for row in route_tuning.inspect(result['spec'],result['geometry'])['routes']};pair=buses.analyze(result['spec'],result['geometry'])['pairs'][0]
    for net in ['DP','DN']:
        assert pair['delay_ps'][net] is not None,'The bus analyzer incorrectly declares all circular paths unknown'
        assert pair['delay_ps'][net]==pytest.approx(routes[net]['delay_ps'],abs=1e-6)
        assert pair['length_mm'][net]==pytest.approx(routes[net]['length_mm'],abs=1e-6)
    assert pair['timing_status']=='pass' and pair['status']=='unknown','Geometric timing does not resolve controlled impedance'
