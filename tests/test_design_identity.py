"""JSON number representation must not look like a hardware edit or rebuild native files."""
import copy
import hashlib
import json
import math
import subprocess
from pathlib import Path
import pytest
from wholeboard import revisions, server, workbench_native
from test_workbench import client
from test_parametric_symbols import fixture


def browser_roundtrip(value):
    result = subprocess.run(['node', '-e', 'let s="";process.stdin.on("data",x=>s+=x);process.stdin.on("end",()=>process.stdout.write(JSON.stringify(JSON.parse(s))));'], input=json.dumps(value), capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def test_history_distinguishes_design_changes_from_numeric_representation():
    a={'editor':{'positions':{'J1':[480.0,100.0]}},'fixed_copper':[{'w':1.0}],'flag':False}
    b=browser_roundtrip(a);original=copy.deepcopy(a);report=revisions.field_comparison(a,b)
    assert report['field_change_count']==0, 'A browser numeric roundtrip is still reported as a design edit'
    assert report['representation_change_count']==3
    assert report['representation_changes'][0]['path']=='/editor/positions/J1/0'
    assert report['representation_changes'][0]['before_json']=='480.0'
    assert report['representation_changes'][0]['after_json']=='480'
    assert report['before_sha256']!=report['after_sha256'], 'Raw serialized identities were hidden'
    assert report['before_semantic_sha256']==report['after_semantic_sha256']
    assert set(report['unchanged_sections'])=={'editor','fixed_copper','flag'}
    assert report['serialization_changed_sections']==['editor','fixed_copper']
    assert a==original and type(a['editor']['positions']['J1'][0]) is float


@pytest.mark.parametrize(('before','after'),[(1,True),(0,False),(1,'1'),([1,2],[2,1]),(.25,.250000000001),(2**53,float(2**53)),(10**30,float(10**30))])
def test_semantic_comparison_never_hides_real_changes_or_unsafe_integer_types(before,after):
    report=revisions.field_comparison({'value':before},{'value':after})
    assert report['field_change_count']>=1
    assert report.get('before_semantic_sha256')!=report.get('after_semantic_sha256'), 'No safe numeric identity distinguishes these values'


def test_immutable_snapshot_files_are_not_normalized_when_comparing(client):
    spec=fixture();spec['editor']['positions']['J1']=[480.0,100.0]
    pid=client.post('/api/workbench/projects',json={'title':'Numeric history','spec':spec}).json()['id'];p=server.mgr().get(pid)
    old=p.root/'history/design-v1.json';before_bytes=old.read_bytes();before_mtime=old.stat().st_mtime_ns
    assert client.put(f'/api/workbench/projects/{pid}/design',json={'base_version':1,'spec':browser_roundtrip(spec)}).status_code==200
    report=client.get(f'/api/workbench/projects/{pid}/history/1/compare').json()
    assert client.get(f'/api/workbench/projects/{pid}/history').json()['current_version']==2
    assert report['from_version']==1 and report['to_version']==2
    assert report['field_change_count']==0 and report['representation_change_count']==2
    assert old.read_bytes()==before_bytes and old.stat().st_mtime_ns==before_mtime
    assert report['from_snapshot_sha256']==hashlib.sha256(before_bytes).hexdigest()
    assert p.state['workbench']['version']==2


def test_native_cache_and_catalog_reuse_equivalent_numbers_but_invalidate_real_geometry(client):
    spec=fixture();spec['board']['width_mm']=40.0;spec['editor']['positions']['J1']=[200.0,200.0]
    pid=client.post('/api/workbench/projects',json={'title':'Numeric cache','spec':spec}).json()['id'];p=server.mgr().get(pid)
    first=workbench_native.generate(p);paths={name:Path(first[name]) for name in ('pcb','sch','geometry_file')};identities={name:(path.read_bytes(),path.stat().st_mtime_ns) for name,path in paths.items()}
    assert client.put(f'/api/workbench/projects/{pid}/design',json={'base_version':1,'spec':browser_roundtrip(spec)}).status_code==200
    catalog=client.get(f'/api/workbench/projects/{pid}/files').json();assert catalog['native']['status']=='current','Numeric-only save marked the valid native output stale'
    second=workbench_native.generate(p);assert second['pcb']==first['pcb'],'Numeric representation alone regenerated the PCB'
    assert second.get('semantic_fingerprint') and second.get('semantic_fingerprint_policy')
    for name,path in paths.items():assert (path.read_bytes(),path.stat().st_mtime_ns)==identities[name]
    changed=copy.deepcopy(p.state['spec']);changed['board']['width_mm']=41
    assert client.put(f'/api/workbench/projects/{pid}/design',json={'base_version':2,'spec':changed}).status_code==200
    assert client.get(f'/api/workbench/projects/{pid}/files').json()['native']['status']=='stale'
    assert workbench_native.generate(p)['pcb']!=first['pcb']


def test_unknown_nonfinite_values_are_rejected_before_design_persistence(client):
    spec=fixture();pid=client.post('/api/workbench/projects',json={'title':'Finite values','spec':spec}).json()['id']
    bad=copy.deepcopy(spec);bad['metadata']={'value':math.nan}
    response=client.put(f'/api/workbench/projects/{pid}/design',content=json.dumps({'base_version':1,'spec':bad}),headers={'Content-Type':'application/json'})
    assert response.status_code==422
    assert server.mgr().get(pid).state['workbench']['version']==1


def test_production_native_lookup_understands_design_identity_without_changing_audit_hashes(client):
    from wholeboard.production import service
    spec=fixture();spec['board']['width_mm']=40.0
    pid=client.post('/api/workbench/projects',json={'title':'Native production identity','spec':spec}).json()['id'];p=server.mgr().get(pid);native=workbench_native.generate(p)
    assert client.put(f'/api/workbench/projects/{pid}/design',json={'base_version':1,'spec':browser_roundtrip(spec)}).status_code==200
    assert service.native_source(p)==Path(native['pcb']), 'Production rejected the numerically equivalent current native design'
    assert service.digest({'value':1.0})!=service.digest({'value':1}), 'Frozen audit/idempotency digest semantics were silently changed'


def test_legacy_exact_native_metadata_is_upgraded_without_overwriting_outputs(client):
    spec=fixture();pid=client.post('/api/workbench/projects',json={'title':'Legacy native identity','spec':spec}).json()['id'];p=server.mgr().get(pid);first=workbench_native.generate(p);pcb=Path(first['pcb']);before=(pcb.read_bytes(),pcb.stat().st_mtime_ns)
    p.state['workbench_native'].pop('semantic_fingerprint');p.state['workbench_native'].pop('semantic_fingerprint_policy');p.save()
    result=workbench_native.generate(p)
    assert result['pcb']==first['pcb'] and result['semantic_fingerprint']
    assert (pcb.read_bytes(),pcb.stat().st_mtime_ns)==before


def test_numeric_only_save_retains_valid_routed_artifact_freshness(client):
    spec=fixture();spec['board']['width_mm']=40.0;pid=client.post('/api/workbench/projects',json={'title':'Routed identity freshness','spec':spec}).json()['id'];p=server.mgr().get(pid);native=workbench_native.generate(p)
    p.state['artifacts']={'pcb':native['pcb']};p.state['workbench']['checks_stale']=False;p.save()
    same=browser_roundtrip(spec);response=client.put(f'/api/workbench/projects/{pid}/design',json={'base_version':1,'spec':same})
    assert response.status_code==200 and response.json()['checks_stale'] is False, 'Numeric formatting invalidated a verified routed source'
    assert workbench_native.final_pcb(p)==Path(native['pcb'])
    same['board']['width_mm']=41
    assert client.put(f'/api/workbench/projects/{pid}/design',json={'base_version':2,'spec':same}).json()['checks_stale'] is True
    assert workbench_native.final_pcb(p) is None


def test_agent_numeric_only_proposal_is_noop_but_boolean_change_is_not(client):
    from wholeboard import codex_bridge
    spec=fixture();spec['editor']['positions']['J1']=[480.0,100.0];spec['metadata']={'flag':True}
    pid=client.post('/api/workbench/projects',json={'title':'Agent semantic identity','spec':spec}).json()['id'];p=server.mgr().get(pid)
    codex_bridge.apply_result(p,{'message':'Keep values','design_json':json.dumps(browser_roundtrip(spec)),'files':[]},'agent',1)
    assert p.state['workbench']['version']==1 and type(p.state['spec']['editor']['positions']['J1'][0]) is float
    changed=copy.deepcopy(spec);changed['metadata']['flag']=1
    codex_bridge.apply_result(p,{'message':'Change JSON type','design_json':json.dumps(changed),'files':[]},'agent',1)
    assert p.state['workbench']['version']==2 and type(p.state['spec']['metadata']['flag']) is int


def test_schematic_cache_reuses_numeric_identity_without_merging_real_edits():
    from wholeboard import schematic_view
    spec=fixture();spec['editor']['positions']['J1']=[480.0,100.0]
    first=schematic_view.scene(spec)
    assert schematic_view.scene(browser_roundtrip(spec)) is first
    changed=browser_roundtrip(spec);changed['editor']['positions']['J1'][0]=481
    assert schematic_view.scene(changed)['fingerprint']!=first['fingerprint']


def test_unknown_identity_policy_falls_back_to_exact_legacy_evidence():
    from wholeboard import design_identity
    original={'x':40.0};metadata={'fingerprint':design_identity.legacy_fingerprint(original),'semantic_fingerprint_policy':'future-policy','semantic_fingerprint':design_identity.fingerprint(original)}
    assert design_identity.matches(metadata,original)
    assert not design_identity.matches(metadata,{'x':40})


def test_numeric_only_restore_retains_check_freshness_and_returns_metadata(client):
    spec=fixture();spec['board']['width_mm']=40.0
    pid=client.post('/api/workbench/projects',json={'title':'Numeric restore','spec':spec}).json()['id'];p=server.mgr().get(pid)
    client.put(f'/api/workbench/projects/{pid}/design',json={'base_version':1,'spec':browser_roundtrip(spec)})
    p.state['workbench']['checks_stale']=False;p.save()
    response=client.post(f'/api/workbench/projects/{pid}/history/1/restore',json={'base_version':2})
    assert response.status_code==200
    assert response.json()['workbench']['version']==3 and response.json()['workbench']['checks_stale'] is False


def test_safe_range_negative_zero_and_bounded_representation_evidence():
    from wholeboard import design_identity
    assert design_identity.equal({'x':-0.0},{'x':0})
    assert design_identity.equal({'x':float(2**53-1)},{'x':2**53-1})
    assert not design_identity.equal({'x':float(2**53)},{'x':2**53})
    report=revisions.field_comparison({'x':[1.0]*5},{'x':[1]*5},limit=2)
    assert report['field_change_count']==0 and report['representation_change_count']==5
    assert len(report['representation_changes'])==2 and report['representation_changes_truncated']
    assert not report['field_changes_truncated']


def test_cached_native_fast_path_rechecks_design_after_source_snapshot(client,monkeypatch):
    import threading
    from fastapi import HTTPException
    spec=fixture();pid=client.post('/api/workbench/projects',json={'title':'Cached native race','spec':spec}).json()['id'];p=server.mgr().get(pid);native=workbench_native.generate(p)
    entered=threading.Event();release=threading.Event();results=[];refresh=workbench_native._refresh_geometry
    def delayed(project,metadata):
        entered.set();assert release.wait(5);return refresh(project,metadata)
    monkeypatch.setattr(workbench_native,'_refresh_geometry',delayed)
    def generate():
        try:results.append(workbench_native.generate(p))
        except Exception as error:results.append(error)
    thread=threading.Thread(target=generate);thread.start()
    try:
        assert entered.wait(5);changed=copy.deepcopy(spec);changed['board']['width_mm']=41
        assert client.put(f'/api/workbench/projects/{pid}/design',json={'base_version':1,'spec':changed}).status_code==200
    finally:release.set();thread.join(5)
    assert not thread.is_alive()
    assert isinstance(results[0],HTTPException) and results[0].status_code==409,'Cached native fast path returned the old design after a concurrent save'
    assert p.state['workbench']['version']==2 and p.state['workbench_native']['pcb']==native['pcb']


def test_check_commit_cannot_bind_old_checks_to_a_new_design_identity(client,monkeypatch):
    import threading
    from wholeboard import design_identity
    spec=fixture();pid=client.post('/api/workbench/projects',json={'title':'Check commit race','spec':spec}).json()['id'];p=server.mgr().get(pid);workbench_native.generate(p)
    entered=threading.Event();release=threading.Event();saving=threading.Event();saved=threading.Event();inspection=threading.Event();results=[];responses=[];matches=design_identity.matches
    monkeypatch.setattr(workbench_native.cli,'erc',lambda path:{'errors':[]})
    def drc(*args,**kwargs):inspection.set();return {'errors':[]}
    monkeypatch.setattr(workbench_native.cli,'drc',drc)
    def gated_match(metadata,current):
        result=matches(metadata,current)
        if inspection.is_set() and threading.current_thread().name=='identity-check-race':
            entered.set();assert release.wait(5)
        return result
    monkeypatch.setattr(design_identity,'matches',gated_match)
    def check():
        try:results.append(workbench_native.check(p))
        except Exception as error:results.append(error)
    def save():
        saving.set();changed=copy.deepcopy(spec);changed['board']['width_mm']=41
        responses.append(client.put(f'/api/workbench/projects/{pid}/design',json={'base_version':1,'spec':changed}));saved.set()
    check_thread=threading.Thread(target=check,name='identity-check-race');check_thread.start();save_thread=None
    try:
        assert entered.wait(5);save_thread=threading.Thread(target=save);save_thread.start();assert saving.wait(5)
        saved.wait(.2) # The unfixed commit lets this save finish inside its check/publication window.
    finally:
        release.set();check_thread.join(5)
        if save_thread:save_thread.join(5)
    assert not check_thread.is_alive() and save_thread and not save_thread.is_alive()
    assert responses[0].status_code==200
    report=results[0];assert isinstance(report,dict),report
    assert report['semantic_fingerprint']==design_identity.fingerprint(spec),'Old checks were assigned the concurrently saved new design identity'
    assert not matches(p.state['workbench_checks'],p.state['spec'])
    assert p.state['workbench']['checks_stale'] is True


def test_edit_during_drc_is_allowed_but_obsolete_checks_are_not_published(client,monkeypatch):
    from fastapi import HTTPException
    spec=fixture();pid=client.post('/api/workbench/projects',json={'title':'Edit during native checks','spec':spec}).json()['id'];p=server.mgr().get(pid);workbench_native.generate(p)
    monkeypatch.setattr(workbench_native.cli,'erc',lambda path:{'errors':[]})
    def drc(*args,**kwargs):
        changed=copy.deepcopy(spec);changed['board']['width_mm']=41
        assert client.put(f'/api/workbench/projects/{pid}/design',json={'base_version':1,'spec':changed}).status_code==200
        return {'errors':[]}
    monkeypatch.setattr(workbench_native.cli,'drc',drc)
    with pytest.raises(HTTPException) as error:workbench_native.check(p)
    assert error.value.status_code==409 and not p.state.get('workbench_checks')
    assert p.state['workbench']['version']==2 and p.state['workbench']['checks_stale'] is True
