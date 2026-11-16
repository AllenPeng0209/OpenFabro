"""Every asynchronous check report identifies the design it actually inspected."""
import copy
import threading
from wholeboard import server, workbench_native
from test_workbench import client
from test_parametric_symbols import fixture


def test_native_checks_return_source_and_commit_design_versions(client):
    pid=client.post('/api/workbench/projects',json={'title':'Check versions','spec':fixture()}).json()['id']
    response=client.post(f'/api/workbench/projects/{pid}/native-checks')
    assert response.status_code==200
    assert response.json()['source_version']==1 and response.json()['design_version']==1


def test_numeric_only_save_during_checks_retains_source_version_and_reports_commit_version(client,monkeypatch):
    spec=fixture();spec['board']['width_mm']=40.0
    pid=client.post('/api/workbench/projects',json={'title':'Check numeric versions','spec':spec}).json()['id'];p=server.mgr().get(pid)
    monkeypatch.setattr(workbench_native.cli,'erc',lambda path:{'errors':[]})
    def drc(*args,**kwargs):
        changed=copy.deepcopy(spec);changed['board']['width_mm']=40
        assert client.put(f'/api/workbench/projects/{pid}/design',json={'base_version':1,'spec':changed}).status_code==200
        return {'errors':[]}
    monkeypatch.setattr(workbench_native.cli,'drc',drc)
    report=workbench_native.check(p)
    assert report['source_version']==1 and report['design_version']==2
    assert p.state['workbench_checks']==report


def test_generic_checks_version_belongs_to_captured_source_during_concurrent_save(client,monkeypatch):
    from wholeboard import design
    spec=fixture();pid=client.post('/api/workbench/projects',json={'title':'Generic check snapshot','spec':spec}).json()['id']
    entered=threading.Event();release=threading.Event();results=[];validate=design.validate
    def delayed(source):
        entered.set();assert release.wait(5);return validate(source)
    monkeypatch.setattr(design,'validate',delayed)
    thread=threading.Thread(target=lambda:results.append(client.post(f'/api/workbench/projects/{pid}/checks')));thread.start()
    try:
        assert entered.wait(5);changed=copy.deepcopy(spec);changed['components'].pop();changed['nets']=[{**net,'pins':[pin for pin in net['pins'] if not pin.startswith('R1.')]} for net in changed['nets']]
        changed['editor']['positions'].pop('R1')
        assert client.put(f'/api/workbench/projects/{pid}/design',json={'base_version':1,'spec':changed}).status_code==200
    finally:release.set();thread.join(5)
    assert not thread.is_alive() and results[0].status_code==200
    report=results[0].json();assert report['version']==1,'Old design checks were labelled with the later saved version'
    assert report['checks'][0]['detail'].startswith('2 unique components')
