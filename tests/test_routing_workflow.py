import copy

import pytest

from test_workbench import client
from test_selective_routing import fixture,native_router
from wholeboard import codex_bridge,server


def make(client,name='selective-routing'):
    pid=client.post('/api/workbench/projects',json={'title':'Selected routing workflow','spec':fixture(name)}).json()['id'];native=client.get(f'/api/workbench/projects/{pid}/layout-geometry');assert native.status_code==200,native.text
    return pid,server.mgr().get(pid),native.json()


def review(client,pid,**options):
    response=client.post(f'/api/workbench/projects/{pid}/routing/prepare',json={'base_version':1,'nets':['SIGNAL'],'seconds':3,'work':500000,**options});assert response.status_code==200,response.text;return response.json()


def body(proposal,**accept):return {'base_version':proposal['base_version'],'spec':proposal['spec'],'native_source':proposal['native_source'],'routing_proposal':{'id':proposal['id'],'sha256':proposal['proposal_sha256'],**accept}}


def test_native_review_keeps_saved_state_and_existing_files_then_applies_exact_selected_routes(client,native_router):
    pid,p,initial=make(client);spec=copy.deepcopy(p.state['spec']);frozen={f:(f.read_bytes(),f.stat().st_mtime_ns) for kind in ['native','history'] for f in (p.root/kind).rglob('*') if f.is_file()};result=review(client,pid)
    assert result['summary']['selected_complete'] and result['summary']['after_global_open']==2
    assert not result['summary']['requires_changes_approval'] and result['safe_to_apply'] and result['native_parity']['ok']
    assert result['summary']['changes']['added_count']>0 and result['summary']['changes']['removed_count']==result['summary']['changes']['modified_count']==0
    assert p.state['spec']==spec and p.state['workbench']['version']==1
    assert all((f.read_bytes(),f.stat().st_mtime_ns)==value for f,value in frozen.items())
    assert result['geometry']['pads']==initial['geometry']['pads']
    for kind in ['tracks','arcs','vias']:assert [t for t in result['geometry'][kind] if t['net']=='KEEP']==[t for t in initial['geometry'][kind] if t['net']=='KEEP']
    saved=client.put(f'/api/workbench/projects/{pid}/design',json=body(result));assert saved.status_code==200,saved.text
    assert p.state['workbench']['version']==2


def test_existing_repair_requires_explicit_acceptance_of_the_same_prepared_proposal(client,native_router):
    pid,p,_=make(client,'selective-routing-repair');result=review(client,pid,repair_nets=['BLOCKER'])
    assert result['summary']['selected_complete'] and result['summary']['requires_changes_approval'] and result['safe_to_apply']
    assert result['summary']['changes']['removed_count']>0 or result['summary']['changes']['modified_count']>0
    denied=client.put(f'/api/workbench/projects/{pid}/design',json=body(result));assert denied.status_code==409,denied.text;assert p.state['workbench']['version']==1
    accepted=client.put(f'/api/workbench/projects/{pid}/design',json=body(result,confirm_changes=True));assert accepted.status_code==200,accepted.text;assert p.state['workbench']['version']==2


def test_an_edited_candidate_or_changed_native_pcb_cannot_reuse_route_approval(client,native_router):
    from pathlib import Path
    pid,p,_=make(client);result=review(client,pid);tampered=body(result);tampered['spec']=copy.deepcopy(result['spec']);tampered['spec']['rules']['track_mm']=.35
    assert client.put(f'/api/workbench/projects/{pid}/design',json=tampered).status_code==409
    pcb=Path(p.state['workbench_native']['pcb']);pcb.write_bytes(pcb.read_bytes()+b'\n')
    assert client.put(f'/api/workbench/projects/{pid}/design',json=body(result)).status_code==409 and p.state['workbench']['version']==1


def test_agent_routes_requested_additions_but_chat_cannot_mutate(client,native_router):
    pid,p,_=make(client);args={'nets':['SIGNAL'],'seconds':3,'work':500000}
    with pytest.raises(ValueError,match='Chat'):codex_bridge.execute_tool(p,'route_selected_nets',args,'chat')
    result=codex_bridge.execute_tool(p,'route_selected_nets',args,'agent');assert result['ok'] and result['version']==2 and p.state['workbench']['version']==2
    assert any(g['net']=='SIGNAL' and g['tracks'] for g in p.state['spec']['fixed_copper'])


def test_agent_repair_returns_concrete_approval_without_mutating_then_applies_by_id(client,native_router):
    pid,p,_=make(client,'selective-routing-repair');result=codex_bridge.execute_tool(p,'route_selected_nets',{'nets':['SIGNAL'],'repair_nets':['BLOCKER'],'seconds':3,'work':500000},'agent')
    assert result['requires_review'] and p.state['workbench']['version']==1
    applied=codex_bridge.execute_tool(p,'apply_route_proposal',{'id':result['id'],'sha256':result['proposal_sha256'],'base_version':1,'confirm_changes':True},'agent')
    assert applied['ok'] and applied['version']==2 and p.state['workbench']['version']==2


def test_declared_pair_defaults_to_native_coupled_routing_without_net_renaming(client,native_router):
    spec=fixture();spec['board']['timing']={'track_ps_per_mm':{'F.Cu':7,'In1.Cu':7,'In2.Cu':7,'B.Cu':7},'via_ps_per_mm':0};pid=client.post('/api/workbench/projects',json={'title':'Coupled selected routing','spec':spec}).json()['id']
    client.get(f'/api/workbench/projects/{pid}/layout-geometry');result=review(client,pid,nets=['USB_DP','USB_DN'])
    assert result['summary']['coupled_pairs']==[['USB_DP','USB_DN']] and result['summary']['native_coupled_routes']>0
    assert result['safe_to_apply'] and result['summary']['selected_complete'] and result['drc']['unconnected']==1
    assert result['spec']['nets']==server.mgr().get(pid).state['spec']['nets']


def test_a_single_declared_pair_member_requires_an_explicit_independent_choice(client,native_router):
    pid,p,_=make(client);response=client.post(f'/api/workbench/projects/{pid}/routing/prepare',json={'base_version':1,'nets':['USB_DP'],'seconds':1,'work':100000})
    assert response.status_code==422 and 'both' in response.json()['detail']
    assert p.state['workbench']['version']==1


def test_routing_inventory_reads_native_open_connections_and_protection_without_writes(client,native_router):
    pid,p,_=make(client);frozen={f:(f.read_bytes(),f.stat().st_mtime_ns) for f in (p.root/'native').rglob('*') if f.is_file()};response=client.get(f'/api/workbench/projects/{pid}/routing');assert response.status_code==200,response.text
    data=response.json();nets={n['name']:n for n in data['nets']};assert data['source_version']==1 and nets['SIGNAL']['open_connections']==1 and nets['KEEP']['open_connections']==0
    assert nets['KEEP']['protected_copper']==5 and nets['KEEP']['unprotected_copper']==0
    assert all((f.read_bytes(),f.stat().st_mtime_ns)==value for f,value in frozen.items())


def test_a_second_native_route_cannot_reuse_an_earlier_generated_copper_identity(client,native_router):
    from wholeboard import workbench_native
    from wholeboard.kicad import geometry
    from pathlib import Path
    pid,p,_=make(client);codex_bridge.execute_tool(p,'route_selected_nets',{'nets':['SIGNAL'],'seconds':3,'work':500000},'agent');before=geometry.read(Path(workbench_native.generate(p)['pcb']))
    result=review(client,pid,nets=['USB_DP','USB_DN'],base_version=2)
    ids=[t['id'] for kind in ['tracks','arcs','vias'] for t in result['geometry'][kind]]
    assert len(ids)==len(set(ids)),'A later native job recycled a previously saved native UUID'
    assert result['safe_to_apply'] and result['summary']['selected_complete'] and result['drc']['errors']==result['drc']['unconnected']==0
    for kind in ['tracks','arcs','vias']:assert [t for t in result['geometry'][kind] if t['net'] in ['KEEP','SIGNAL']]==[t for t in before[kind] if t['net'] in ['KEEP','SIGNAL']]


def test_native_unsupported_pad_is_explicitly_unknown_before_a_routing_job_starts(client,native_router,monkeypatch):
    from pathlib import Path
    from wholeboard import selective_routing,sexpr
    pid,p,_=make(client);pcb=Path(p.state['workbench_native']['pcb']);tree=sexpr.parse(pcb.read_text());pad=next(sexpr.find_all(next(sexpr.find_all(tree,'footprint')),'pad'));pad[3]=sexpr.Sym('trapezoid');pad.append(sexpr.S(sexpr.Sym('rect_delta'),1.8,0));pcb.write_text(sexpr.dumps(tree));original=copy.deepcopy(p.state['spec'])
    def forbidden(*args,**kwargs):raise AssertionError('Unknown pad geometry reached the native routing process')
    monkeypatch.setattr(selective_routing,'route_native',forbidden)
    info=client.get(f'/api/workbench/projects/{pid}/routing');assert info.status_code==422 and 'pad' in info.json()['detail'],info.text
    response=client.post(f'/api/workbench/projects/{pid}/routing/prepare',json={'base_version':1,'nets':['SIGNAL']});assert response.status_code==422 and 'pad' in response.json()['detail'],response.text
    assert p.state['spec']==original and p.state['workbench']['version']==1


def arc_counterexample(client):
    import math
    from test_interactive_routing_native import fixture as interactive_fixture
    spec=interactive_fixture();g=spec['fixed_copper'][0];line=g['tracks'].pop(0);g['arcs']=[{'id':line['id'],'a':[20,5],'m':[25,12.5],'b':[20,20],'w':.4,'layer':'F.Cu','locked':True}];g['tracks'][0].update(a=[24,15],b=[16.875+math.sqrt(8.125**2-2.5**2),15]);pid=client.post('/api/workbench/projects',json={'title':'Native connectivity counterexample','spec':spec}).json()['id'];client.get(f'/api/workbench/projects/{pid}/layout-geometry');return pid,server.mgr().get(pid)


def test_global_routing_opens_follow_actual_native_drc_even_when_the_pad_model_disagrees(client,native_router):
    pid,p=arc_counterexample(client);result=review(client,pid,nets=['SIG'])
    assert result['drc']['unconnected']==1,'The fixture must retain its original native foreign-net open'
    assert result['summary']['after_global_open']==result['drc']['unconnected'],'A modeled zero must not erase an actual native open'


def test_an_unchanged_partial_engine_result_cannot_claim_the_selected_native_arc_net_complete(client,native_router,monkeypatch):
    import shutil
    from pathlib import Path
    from wholeboard import selective_routing
    pid,p=arc_counterexample(client)
    def unchanged(source,target,**options):
        Path(target).parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target);return {'pcb':str(target),'summary':{},'returncode':3,'stuck':{},'coupled_routes':None}
    monkeypatch.setattr(selective_routing,'route_native',unchanged);result=review(client,pid,nets=['N'])
    assert result['drc']['unconnected']==2
    assert not result['summary']['selected_complete'] and result['summary']['after_selected_open']['N']>=1,'The selected native N open was hidden by approximate arc contact'


def test_a_proposal_using_the_older_modeled_only_completion_policy_must_be_reviewed_again(client,native_router):
    import hashlib,json
    pid,p,_=make(client);result=review(client,pid);path=p.root/'.routing-proposals'/result['id']/'manifest.json';data=json.loads(path.read_text());data['schema']=1;raw=json.dumps(data,ensure_ascii=False,sort_keys=True).encode();path.write_bytes(raw);request=body(result);request['routing_proposal']['sha256']=hashlib.sha256(raw).hexdigest()
    response=client.put(f'/api/workbench/projects/{pid}/design',json=request);assert response.status_code==409,response.text;assert p.state['workbench']['version']==1
