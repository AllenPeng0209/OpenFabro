"""The workbench must preserve edits, reject lost updates, and never call AI for drafts."""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from wholeboard import config, project, server


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "APP_DIR", tmp_path)
    monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.json")
    config.update({"projects_dir": str(tmp_path / "projects")})
    monkeypatch.setattr(server, "manager", project.Manager())
    return TestClient(server.app)


def draft(client):
    response = client.post("/api/workbench/projects", json={"title": "Power board", "example": True})
    assert response.status_code == 201
    return response.json()


def test_legacy_geometry_cache_refresh_preserves_native_files_and_saved_design(client):
    import hashlib
    from wholeboard import codex_bridge
    spec={'name':'drill_cache','board':{'width_mm':25,'height_mm':20,'layers':2,'ground_pour':None},
      'components':[{'ref':'J1','value':'Header','symbol':'Connector_Generic:Conn_01x02','footprint':'Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical','placement':{'x_mm':10,'y_mm':10}}],
      'nets':[{'name':'SIG','pins':['J1.1']},{'name':'GND','class':'power','pins':['J1.2']}]}
    made=client.post('/api/workbench/projects',json={'title':'Legacy geometry cache','spec':spec}).json();pid=made['id'];p=server.mgr().get(pid)
    native=client.post(f'/api/workbench/projects/{pid}/native').json();pcb=Path(native['pcb']);sch=Path(native['sch']);old=pcb.parent/'geometry.json'
    legacy=json.loads(old.read_text());legacy.pop('schema',None)
    for pad in legacy['pads']:
        pad['drill']=0
        for key in ('drill_shape','drill_size','drill_offset'):pad.pop(key,None)
    old.write_text(json.dumps(legacy));p.state['workbench_native']={k:v for k,v in native.items() if k not in ('geometry_schema','geometry_file')};p.save()
    hashes={f:hashlib.sha256(f.read_bytes()).hexdigest() for f in (pcb,sch,old)}
    response=client.post(f'/api/workbench/projects/{pid}/native');assert response.status_code==200,response.text
    refreshed=response.json()
    display=client.get(f'/api/workbench/projects/{pid}/layout-geometry').json()['geometry'];assert [pad['drill'] for pad in display['pads']]==[1,1]
    assert refreshed.get('geometry_schema')==display.get('schema') and display.get('schema',0)>1,'The old zero-drill cache was reused'
    assert refreshed['pcb']==native['pcb'] and refreshed['sch']==native['sch']
    assert all(hashlib.sha256(f.read_bytes()).hexdigest()==digest for f,digest in hashes.items()),'Reading geometry must not rewrite immutable native snapshots'
    assert Path(refreshed['geometry_file']).name!='geometry.json'
    sidecar=Path(refreshed['geometry_file']);stamp=sidecar.stat().st_mtime_ns
    assert client.post(f'/api/workbench/projects/{pid}/native').json()['geometry_file']==str(sidecar) and sidecar.stat().st_mtime_ns==stamp
    evidence=codex_bridge.execute_tool(p,'read_file',{'path':sidecar.relative_to(p.root).as_posix(),'limit':20000},'chat')
    assert [pad['drill'] for pad in evidence['native_geometry']['pads']]==[1,1]
    prompt=codex_bridge.prompt_for(p,'Review the current drill data','chat').split('PROJECT CONTEXT (reference data):\n',1)[1].split('\n\nUSER REQUEST:',1)[0]
    assert [pad['drill'] for pad in json.loads(prompt)['engineering_evidence']['native_geometry']['pads']]==[1,1]
    assert p.state['workbench']['version']==1 and p.state['spec']==spec


def test_terminal_authoring_is_version_guarded_and_does_not_save_its_proposal(client):
    created=draft(client);pid=created['id']
    result=client.post(f'/api/workbench/projects/{pid}/terminals/prepare',json={'base_version':1,'action':'add','name':'VIN','sheet':''})
    assert result.status_code==200,result.text
    proposed=result.json();assert proposed['ref']=='TP1'
    assert proposed['spec']['components'][-1]['terminal']['exclude_from_pcb'] is False
    assert server.mgr().get(pid).state['workbench']['version']==1
    assert server.mgr().get(pid).state['spec']==created['spec']
    assert client.put(f'/api/workbench/projects/{pid}/design',json={'base_version':1,'spec':proposed['spec']}).status_code==200
    stale=client.post(f'/api/workbench/projects/{pid}/terminals/prepare',json={'base_version':1,'action':'update','ref':'TP1','patch':{'name':'OLD'}})
    assert stale.status_code==409
    update=client.post(f'/api/workbench/projects/{pid}/terminals/prepare',json={'base_version':2,'action':'update','ref':'TP1','patch':{'name':'VINPUT','exclude_from_pcb':True,'diameter_mm':2.1}})
    assert update.status_code==200,update.text
    assert update.json()['spec']['components'][-1]['value']=='VINPUT'
    assert server.mgr().get(pid).state['workbench']['version']==2


def test_electrical_wire_cut_proposal_is_native_checked_and_version_guarded(client):
    from test_wire_cuts import example
    from wholeboard import schematic_view
    spec,_=example();created=client.post('/api/workbench/projects',json={'title':'Electrical cut','spec':spec}).json();pid=created['id']
    scene=schematic_view.scene(spec);route=next(r for r in scene['routes'] if r['id']=='trunk');a,b=max(zip(route['points'],route['points'][1:]),key=lambda p:sum(abs(p[0][i]-p[1][i]) for i in range(2)))
    body={'base_version':1,'wire':'trunk','point':[(a[i]+b[i])/2 for i in range(2)],'sheet':''}
    result=client.post(f'/api/workbench/projects/{pid}/wire-cuts/prepare',json=body)
    assert result.status_code==200,result.text
    proposal=result.json();assert proposal['native_parity']['ok'];assert proposal['summary']['changed_pins']==['R2.1','R3.1']
    p=server.mgr().get(pid);assert p.state['spec']==spec and p.state['workbench']['version']==1
    p.engine_busy=True
    assert client.post(f'/api/workbench/projects/{pid}/wire-cuts/prepare',json=body).status_code==409
    p.engine_busy=False
    assert client.put(f'/api/workbench/projects/{pid}/design',json={'base_version':1,'spec':proposal['spec']}).status_code==200
    assert client.post(f'/api/workbench/projects/{pid}/wire-cuts/prepare',json=body).status_code==409
    assert client.post(f'/api/workbench/projects/{pid}/wire-cuts/prepare',json=[]).status_code==422


def test_published_module_updates_cross_projects_without_overwriting_local_edits(client):
    from test_module_updates import source,target
    src=client.post('/api/workbench/projects',json={'title':'Version source','spec':source()}).json();sid=src['id']
    first=client.post(f'/api/workbench/projects/{sid}/modules/releases/publish',json={'base_version':1,'module':'Supply','name':'Supply','ports':{'OUT':'SIG','GND':'GND'},'expected_version':0})
    assert first.status_code==200,first.text
    asset=first.json()['module'];assert asset['version']==1
    host=target(two=True);host['components'][1]['value']='3k';host['components'][1]['description']='Keep board note'
    made=client.post('/api/workbench/projects',json={'title':'Version target','spec':host}).json();pid=made['id']
    install=client.post(f'/api/workbench/projects/{pid}/modules/catalog/install',json={'base_version':1,'catalog_id':asset['origin']['catalog_id'],'module':'Supply'})
    assert install.status_code==200,install.text
    assert server.mgr().get(pid).state['workbench']['version']==1
    assert client.put(f'/api/workbench/projects/{pid}/design',json={'base_version':1,'spec':install.json()['spec']}).status_code==200
    changed=source();changed['components'][0]['value']='2k';changed['components'][1]['value']='2k'
    assert client.put(f'/api/workbench/projects/{sid}/design',json={'base_version':1,'spec':changed}).status_code==200
    published=client.post(f'/api/workbench/projects/{sid}/modules/releases/publish',json={'base_version':2,'module':'Supply','name':'Supply','ports':{'OUT':'SIG','GND':'GND'},'expected_version':1})
    assert published.status_code==200,published.text
    notices=client.get(f'/api/workbench/projects/{pid}/modules/updates').json()['updates'];assert {row['instance'] for row in notices if row['available']}=={'M1','M2'}
    body={'base_version':2,'instances':['M1'],'sources':{'M1':{'catalog_id':asset['origin']['catalog_id'],'version':2}}}
    pending=client.post(f'/api/workbench/projects/{pid}/modules/updates/prepare',json=body);assert pending.status_code==200,pending.text
    assert pending.json()['spec'] is None;key=pending.json()['plans'][0]['conflicts'][0]['id']
    complete=client.post(f'/api/workbench/projects/{pid}/modules/updates/prepare',json={**body,'resolutions':{'M1':{key:'local'}}});assert complete.status_code==200,complete.text
    result=complete.json();assert result['native_parity']['ok'];parts={c['ref']:c for c in result['spec']['components']};assert parts['R1']['value']=='3k' and parts['R2']['value']=='2k' and parts['R3']['value']=='1k'
    assert server.mgr().get(pid).state['workbench']['version']==2
    assert client.put(f'/api/workbench/projects/{pid}/design',json={'base_version':2,'spec':result['spec']}).status_code==200
    assert client.post(f'/api/workbench/projects/{pid}/modules/updates/prepare',json=body).status_code==409


def test_portable_module_update_can_pin_an_intermediate_release(client):
    from test_module_updates import source,target,published
    from wholeboard import module_updates
    host=target();v1=host['library']['modules']['Supply'];changed=source();changed['components'][1]['value']='2k'
    v2=module_updates.release(published(changed),previous=v1);changed['components'][1]['value']='4k'
    host['library']['modules']['Supply']=module_updates.release(published(changed),previous=v2)
    made=client.post('/api/workbench/projects',json={'title':'Portable revision pin','spec':host}).json();pid=made['id']
    response=client.post(f'/api/workbench/projects/{pid}/modules/updates/prepare',json={'base_version':1,'instances':['M1'],'sources':{'M1':{'version':2}}})
    assert response.status_code==200,response.text
    spec=response.json()['spec'];assert spec['editor']['module_instances']['M1']['version']==2
    assert next(c for c in spec['components'] if c['ref']=='R2')['value']=='2k'
    assert spec['library']['modules']['Supply']['version']==3


def test_portable_module_can_create_and_reopen_an_editable_source_without_saving_the_target(client):
    from test_module_updates import target
    made=client.post('/api/workbench/projects',json={'title':'Module source fork','spec':target()}).json();pid=made['id']
    response=client.post(f'/api/workbench/projects/{pid}/modules/source',json={'base_version':1,'module':'Supply'})
    assert response.status_code==200,response.text
    result=response.json();sid=result['source_project'];assert sid!=pid
    p=server.mgr().get(pid);source=server.mgr().get(sid)
    assert p.state['workbench']['version']==1 and not p.state['spec']['library']['modules']['Supply'].get('origin')
    assert [c['ref'] for c in source.state['spec']['components']]==['R1','R2']
    assert source.state['spec']['library']['modules']['Supply']['origin']['project_id']==sid
    assert client.put(f'/api/workbench/projects/{pid}/design',json={'base_version':1,'spec':result['spec']}).status_code==200
    reopened=client.post(f'/api/workbench/projects/{pid}/modules/source',json={'base_version':2,'module':'Supply'})
    assert reopened.status_code==200 and reopened.json()['source_project']==sid
    published=client.post(f'/api/workbench/projects/{sid}/modules/releases/publish',json={'base_version':1,'module':'Supply','name':'Supply','ports':{'OUT':'SIG','GND':'GND'},'expected_version':0})
    assert published.status_code==200,published.text
    assert published.json()['module']['version']==1


def test_net_label_proposals_are_native_checked_without_saving_and_reject_stale_edits(client):
    from test_net_labels import example
    made=client.post('/api/workbench/projects',json={'title':'Named net labels','spec':example()}).json();pid=made['id']
    body={'base_version':1,'action':'add','anchor':'R4.1','net':'SIG','position':[1100,180]}
    response=client.post(f'/api/workbench/projects/{pid}/net-labels/prepare',json=body)
    assert response.status_code==200,response.text
    result=response.json();assert result['native_parity']['ok'];assert server.mgr().get(pid).state['workbench']['version']==1
    assert client.put(f'/api/workbench/projects/{pid}/design',json={'base_version':1,'spec':result['spec']}).status_code==200
    assert client.post(f'/api/workbench/projects/{pid}/net-labels/prepare',json=body).status_code==409
    assert client.post(f'/api/workbench/projects/{pid}/net-labels/prepare',json=[]).status_code==422

def test_bus_property_drafts_preserve_design_and_copper_and_reject_stale_saves(client):
    from test_buses import example
    made=client.post('/api/workbench/projects',json={'title':'Bus properties','spec':example()}).json();pid=made['id']
    body={'base_version':1,'action':'pins','pins':['J1.1','J1.2'],'patch':{'bus_group':'USB_1','bus_type':'USB 2.0','pair':'DATA','impedance_ohms':90,'pn_skew_ps':10,'max_length_mm':5}}
    response=client.post(f'/api/workbench/projects/{pid}/buses/prepare',json=body);assert response.status_code==200,response.text
    proposal=response.json();assert proposal['native_parity']['ok'] and server.mgr().get(pid).state['workbench']['version']==1
    assert proposal['spec']['nets']==example()['nets'];assert client.put(f'/api/workbench/projects/{pid}/design',json={'base_version':1,'spec':proposal['spec']}).status_code==200
    current=client.get(f'/api/workbench/projects/{pid}/buses');assert current.status_code==200,current.text;assert current.json()['analysis']['pairs'][0]['status']=='fail'
    assert client.post(f'/api/workbench/projects/{pid}/buses/prepare',json=body).status_code==409
    assert client.post(f'/api/workbench/projects/{pid}/buses/prepare',json=[]).status_code==422


def test_selection_transform_preview_is_native_proven_version_guarded_and_does_not_save(client):
    from test_transforms import routed
    spec=routed();made=client.post('/api/workbench/projects',json={'title':'Selection transforms','spec':spec}).json();pid=made['id']
    body={'base_version':1,'mode':'layout','keys':['J1','J2'],'action':'rotate','angle':90,'pivot':[17.5,15]}
    response=client.post(f'/api/workbench/projects/{pid}/transforms/prepare',json=body)
    assert response.status_code==200,response.text
    result=response.json();p=server.mgr().get(pid)
    assert result['native_parity']['ok'] and result['drc']['unconnected']==0 and p.state['spec']==spec and p.state['workbench']['version']==1
    assert result['summary']['transformed_copper']['tracks']==3
    assert client.put(f'/api/workbench/projects/{pid}/design',json={'base_version':1,'spec':result['spec']}).status_code==200
    assert client.post(f'/api/workbench/projects/{pid}/transforms/prepare',json=body).status_code==409
    assert client.post(f'/api/workbench/projects/{pid}/transforms/prepare',json=[]).status_code==422


def test_in_app_agent_transform_requires_authorization_to_clear_copper_and_chat_cannot_edit(client):
    from test_transforms import routed
    from wholeboard import codex_bridge
    made=client.post('/api/workbench/projects',json={'title':'Agent selection transforms','spec':routed()}).json();p=server.mgr().get(made['id'])
    args={'mode':'layout','keys':['J1'],'action':'rotate','angle':90}
    pending=codex_bridge.execute_tool(p,'transform_selection',args,'agent')
    assert pending['requires_review'] and p.state['workbench']['version']==1
    allowed=codex_bridge.execute_tool(p,'transform_selection',{**args,'confirm_clear':True},'agent')
    assert allowed['version']==2 and [group['net'] for group in p.state['spec']['fixed_copper']]==['SIG1']
    with pytest.raises(ValueError,match='Chat mode'):codex_bridge.execute_tool(p,'transform_selection',args,'chat')
    p.cancel.set()
    with pytest.raises(InterruptedError):codex_bridge.execute_tool(p,'transform_selection',args,'agent')


def test_schematic_transform_preview_proves_internal_wire_paths_and_keeps_physical_state(client):
    from test_transforms import wired
    spec=wired();made=client.post('/api/workbench/projects',json={'title':'Schematic affine transform','spec':spec}).json();pid=made['id']
    result=client.post(f'/api/workbench/projects/{pid}/transforms/prepare',json={'base_version':1,'mode':'schematic','keys':['J1','J2'],'action':'flip_horizontal','pivot':[250,100]})
    assert result.status_code==200,result.text
    proposal=result.json();assert proposal['native_parity']['ok'] and len(proposal['summary']['preserved_wire_paths'])==2
    assert proposal['spec']['components']==spec['components'] and proposal['spec']['nets']==spec['nets']
    assert server.mgr().get(pid).state['spec']==spec

def test_in_app_bus_tools_separate_inspection_from_guarded_edits(client):
    from wholeboard import codex_bridge
    from test_buses import example
    made=client.post('/api/workbench/projects',json={'title':'Agent bus constraints','spec':example()}).json();p=server.mgr().get(made['id'])
    args={'action':'pins','pins':['J1.1','J1.2'],'patch':{'bus_group':'USB_1','pair':'DATA','pn_skew_ps':10,'impedance_ohms':90}}
    with pytest.raises(ValueError,match='Chat mode'):codex_bridge.execute_tool(p,'edit_bus_properties',args,'chat')
    result=codex_bridge.execute_tool(p,'edit_bus_properties',args,'agent');assert result['version']==2
    codex_bridge.execute_tool(p,'generate_native',{},'agent');inspection=codex_bridge.execute_tool(p,'inspect_buses',{},'chat');assert inspection['groups'][0]['nets']==['USB1_DP','USB1_DN'] and p.state['workbench']['version']==2
    p.cancel.set()
    with pytest.raises(InterruptedError):codex_bridge.execute_tool(p,'edit_bus_properties',args,'agent')


def test_in_app_agent_can_edit_named_labels_but_chat_and_cancellation_cannot(client):
    from wholeboard import codex_bridge
    from test_net_labels import example
    made=client.post('/api/workbench/projects',json={'title':'Agent named labels','spec':example()}).json();p=server.mgr().get(made['id'])
    args={'action':'add','anchor':'R4.1','net':'SIG','position':[1100,180]}
    result=codex_bridge.execute_tool(p,'edit_net_label',args,'agent')
    assert result['version']==2 and p.state['spec']['editor']['wire_nodes'][result['id']]['label']['kind']=='auto'
    with pytest.raises(ValueError,match='Chat mode'):codex_bridge.execute_tool(p,'edit_net_label',{'action':'delete','id':result['id']},'chat')
    p.cancel.set()
    with pytest.raises(InterruptedError):codex_bridge.execute_tool(p,'edit_net_label',{'action':'delete','id':result['id']},'agent')
    assert p.state['workbench']['version']==2


def test_in_app_agent_can_edit_terminals_through_the_same_guarded_engine_and_chat_cannot(client):
    from wholeboard import codex_bridge
    created=draft(client);p=server.mgr().get(created['id'])
    result=codex_bridge.execute_tool(p,'edit_terminal',{'action':'add','name':'AGENT_IN','exclude_from_pcb':True},'agent')
    assert result['ref']=='TP1' and p.state['workbench']['version']==2
    assert p.state['spec']['components'][-1]['value']=='AGENT_IN'
    with pytest.raises(ValueError,match='Chat mode'):codex_bridge.execute_tool(p,'edit_terminal',{'action':'delete','ref':'TP1'},'chat')
    assert p.state['workbench']['version']==2
    p.cancel.set()
    with pytest.raises(InterruptedError):codex_bridge.execute_tool(p,'edit_terminal',{'action':'delete','ref':'TP1'},'agent')
    assert p.state['workbench']['version']==2


@pytest.mark.parametrize('sheets',[
    {'Power':{'parent':'Missing'}},
    {'Power':{'parent':'Bias'},'Bias':{'parent':'Power'}},
    {'Power':{'size':[10,200]}},
    {'Power':{'ports':{'OUT':{'net':'Missing'}}}},
    {'../Power':{}},
    {'Power':{'title':'\n'}},
])
def test_invalid_sheet_hierarchy_cannot_replace_saved_design(client,sheets):
    created=draft(client);spec=created['spec'];spec['editor']['sheets']=sheets
    response=client.put(f"/api/workbench/projects/{created['id']}/design",json={'base_version':1,'spec':spec})
    assert response.status_code==422,response.text
    assert server.mgr().get(created['id']).state['workbench']['version']==1


def test_module_publish_and_insert_are_reviewable_drafts_with_version_guards(client):
    created=draft(client);pid=created['id']
    published=client.post(f'/api/workbench/projects/{pid}/modules/publish',json={'base_version':1,'name':'Supply','ports':{'IN':'VBUS','GND':'GND'}})
    assert published.status_code==200,published.text
    asset=published.json()['module'];assert len(asset['design']['components'])==9
    assert server.mgr().get(pid).state['workbench']['version']==1
    spec=created['spec'];spec['board']['width_mm']=80;spec['library']={'modules':{'Supply':asset}}
    assert client.put(f'/api/workbench/projects/{pid}/design',json={'base_version':1,'spec':spec}).status_code==200
    stale=client.post(f'/api/workbench/projects/{pid}/modules/instantiate',json={'base_version':1,'module':'Supply','instance':'M1'})
    assert stale.status_code==409
    result=client.post(f'/api/workbench/projects/{pid}/modules/instantiate',json={'base_version':2,'module':'Supply','instance':'M1','offset':[35,0],'connections':{'GND':'GND'}})
    assert result.status_code==200,result.text
    assert len(result.json()['spec']['components'])==18
    assert server.mgr().get(pid).state['workbench']['version']==2
    saved=client.put(f'/api/workbench/projects/{pid}/design',json={'base_version':2,'spec':result.json()['spec']})
    assert saved.status_code==200,saved.text


def test_selection_conversion_returns_a_native_preview_and_never_saves_before_confirmation(client):
    created=draft(client);pid=created['id'];before=created['spec']
    response=client.post(f'/api/workbench/projects/{pid}/modules/convert',json={'base_version':1,'refs':['R1','R2'],'module':'CC','instance':'M1','name':'USB CC resistors'})
    assert response.status_code==200,response.text
    result=response.json();assert {c['ref'] for c in result['capture_geometry']['footprints']}=={'R1','R2'}
    assert result['capture']['bounds']
    assert server.mgr().get(pid).state['workbench']['version']==1
    assert server.mgr().get(pid).state['spec']==before
    saved=client.put(f'/api/workbench/projects/{pid}/design',json={'base_version':1,'spec':result['spec']})
    assert saved.status_code==200,saved.text
    stale=client.post(f'/api/workbench/projects/{pid}/modules/convert',json={'base_version':1,'refs':['R1'],'module':'Other','instance':'M2','name':'Other'})
    assert stale.status_code==409


def test_selection_conversion_native_preview_refills_the_captured_zone_geometry(client):
    from wholeboard import sexpr
    from wholeboard.kicad import board,cli
    if not cli.find_kicad_cli():pytest.skip('KiCad is needed to verify the actual preview fill')
    created=draft(client);pid=created['id'];spec=created['spec']
    spec['fixed_zones']=[{'net':'GND','origin':[100,100],'source':sexpr.dumps(board.zone('GND','F.Cu',30,22,.5,.25))}]
    assert client.put(f'/api/workbench/projects/{pid}/design',json={'base_version':1,'spec':spec}).status_code==200
    result=client.post(f'/api/workbench/projects/{pid}/modules/convert',json={'base_version':2,'refs':['R1','R2'],'module':'CC','instance':'M1','name':'CC'})
    assert result.status_code==200,result.text
    assert result.json()['capture_geometry']['zone_sources']
    assert result.json()['capture_geometry']['zones'],'The prepared module displays missing copper pours'


@pytest.mark.parametrize('refs',[[],['MISSING'],['R1',42]])
def test_invalid_module_conversion_selection_is_rejected(client,refs):
    created=draft(client)
    response=client.post(f"/api/workbench/projects/{created['id']}/modules/convert",json={'base_version':1,'refs':refs,'module':'CC','instance':'M1','name':'CC'})
    assert response.status_code==422,response.text


def test_overlapping_sheet_ports_cannot_publish_a_shorted_native_preview(client):
    from wholeboard.kicad import cli
    if not cli.find_kicad_cli():pytest.skip('KiCad is required to verify native pin groups')
    created=draft(client);spec=created['spec']
    spec['editor']['sheets']={key:{'position':[850,140]} for key in ('Power','Bias')}
    for component in spec['components']:
        if component['ref']=='R1':component['sheet']='Power'
        elif component['ref']=='R2':component['sheet']='Bias'
    response=client.put(f"/api/workbench/projects/{created['id']}/design",json={'base_version':1,'spec':spec});assert response.status_code==200
    native=client.post(f"/api/workbench/projects/{created['id']}/native")
    assert native.status_code==422,native.text
    assert 'schematic' in native.text.lower()


@pytest.mark.parametrize('mutation',['missing','cycle','offset','duplicate'])
def test_invalid_wire_junction_dependencies_cannot_replace_the_design(client,mutation):
    created=draft(client);spec=created['spec'];guides=[{'id':'trunk','from':'R1.2','to':'R2.2'},{'id':'branch','from':'D1.1','to':'R1.2','to_join':{'wire':'trunk','offset':.5}}]
    if mutation=='missing':guides[1]['to_join']['wire']='missing'
    elif mutation=='cycle':guides[0]['from_join']={'wire':'branch','offset':.5}
    elif mutation=='offset':guides[1]['to_join']['offset']=-1
    elif mutation=='duplicate':guides[1]['id']='trunk'
    spec['editor']['connection_guides']=guides
    response=client.put(f"/api/workbench/projects/{created['id']}/design",json={'base_version':1,'spec':spec})
    assert response.status_code==422
    assert server.mgr().get(created['id']).state['workbench']['version']==1


@pytest.mark.parametrize('source',[
    '(footprint "invalid")',
    '(zone (net "GND") (layer "F.Mask") (polygon (pts (xy 0 0) (xy 1 0) (xy 1 1))))',
    '(zone (net "GND") (layer "F.Cu") (polygon (pts (xy 0 0) (xy 1 0) (xy 1 nan))))',
])
def test_invalid_native_zone_sources_cannot_be_saved(client,source):
    result=draft(client);spec=result['spec']
    spec['fixed_zones']=[{'net':'GND','origin':[100,100],'source':source}]
    response=client.put(f"/api/workbench/projects/{result['id']}/design",json={'base_version':1,'spec':spec})
    assert response.status_code==422
    assert server.mgr().get(result['id']).state['workbench']['version']==1


def test_draft_is_persisted_without_starting_an_agent(client):
    result = draft(client)
    p = server.mgr().get(result["id"])
    assert p.worker is None
    assert p.state["status"] == "idle"
    assert p.state["spec"]["components"][0]["ref"] == "J1"
    assert json.loads((p.root / "design.json").read_text())["board"]["width_mm"] == 30
    assert project.Manager().get(p.id).state["workbench"]["version"] == 1


def test_save_roundtrips_and_rejects_a_stale_editor(client):
    result = draft(client)
    pid = result["id"]
    spec = result["spec"]
    spec["components"][1]["value"] = "4.7k"
    url = f"/api/workbench/projects/{pid}/design"
    saved = client.put(url, json={"base_version": 1, "spec": spec})
    assert saved.status_code == 200
    assert saved.json()["version"] == 2
    persisted = project.Manager().get(pid)
    assert persisted.state["spec"]["components"][1]["value"] == "4.7k"
    assert persisted.state["workbench"]["checks_stale"] is True
    old = client.put(url, json={"base_version": 1, "spec": result["spec"]})
    assert old.status_code == 409
    assert "another" in old.json()["detail"].lower()
    assert project.Manager().get(pid).state["workbench"]["version"] == 2


@pytest.mark.parametrize("mutation", ["duplicate", "dangling", "negative", "nonfinite"])
def test_invalid_design_cannot_replace_the_saved_board(client, mutation):
    result = draft(client)
    spec = result["spec"]
    if mutation == "duplicate":
        spec["components"][1]["ref"] = "J1"
    elif mutation == "dangling":
        spec["nets"][0]["pins"].append("U99.1")
    else:
        spec["board"]["width_mm"] = -1 if mutation == "negative" else "NaN"
    response = client.put(f"/api/workbench/projects/{result['id']}/design",
                          json={"base_version": 1, "spec": spec})
    assert response.status_code == 422
    assert server.mgr().get(result["id"]).state["workbench"]["version"] == 1


def test_csv_export_uses_saved_values_and_escapes_formulas(client):
    result = draft(client)
    spec = result["spec"]
    spec["components"][1]["value"] = "=HYPERLINK(\"bad\")"
    client.put(f"/api/workbench/projects/{result['id']}/design", json={"base_version": 1, "spec": spec})
    response = client.get(f"/api/workbench/projects/{result['id']}/bom.csv")
    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    assert "'=" in response.text
    assert "C23186" in response.text


def test_checks_distinguish_missing_tools_from_a_pass(client, monkeypatch):
    result = draft(client)
    monkeypatch.setattr(server.cli, "find_kicad_cli", lambda *_: None)
    response = client.post(f"/api/workbench/projects/{result['id']}/checks")
    assert response.status_code == 200
    report = response.json()
    assert report["manufacturing_ready"] is False
    assert next(c for c in report["checks"] if c["id"] == "erc")["status"] == "unavailable"
    assert next(c for c in report["checks"] if c["id"] == "drc")["status"] == "unavailable"


def test_attachment_is_saved_with_safe_path_and_text_context(client):
    import base64
    result = draft(client)
    response = client.post(f"/api/workbench/projects/{result['id']}/attachments", json={
        "name": "../datasheet.txt", "data": base64.b64encode(b"Operating voltage: 3.3 V").decode()})
    assert response.status_code == 201
    assert response.json()["name"] == "datasheet.txt"
    assert response.json()["text"] == "Operating voltage: 3.3 V"
    assert client.get(response.json()["url"]).content == b"Operating voltage: 3.3 V"


def test_codex_chat_cannot_apply_design_changes(client):
    import importlib.util
    assert importlib.util.find_spec("wholeboard.codex_bridge"), "The in-workbench Codex bridge is not implemented"
    from wholeboard import codex_bridge
    result = draft(client)
    p = server.mgr().get(result["id"])
    changed = json.loads(json.dumps(p.state["spec"]))
    changed["board"]["width_mm"] = 40
    codex_bridge.apply_result(p, {"message": "Review ready", "design_json": json.dumps(changed),
        "files": [{"path": "review.md", "content": "Review"}], "review": []}, "chat", 1)
    assert p.state["spec"]["board"]["width_mm"] == 30
    assert not (p.root / "review.md").exists()


def test_codex_agent_applies_versioned_design_and_rejects_escaping_files(client):
    import importlib.util
    assert importlib.util.find_spec("wholeboard.codex_bridge"), "The in-workbench Codex bridge is not implemented"
    from wholeboard import codex_bridge
    result = draft(client)
    p = server.mgr().get(result["id"])
    changed = json.loads(json.dumps(p.state["spec"]))
    changed["board"]["width_mm"] = 40
    response = {"message": "Updated", "design_json": json.dumps(changed),
                "files": [{"path": "docs/review.md", "content": "Needs measured power data."}],
                "review": [{"requirement": "72 h standby", "status": "unknown", "evidence": "No measurement yet"}]}
    codex_bridge.apply_result(p, response, "agent", 1)
    assert p.state["spec"]["board"]["width_mm"] == 40
    assert p.state["workbench"]["version"] == 2
    assert (p.root / "docs/review.md").read_text() == "Needs measured power data."
    assert p.state["workbench_review"][0]["status"] == "unknown"
    with pytest.raises(ValueError, match="path"):
        codex_bridge.apply_result(p, {**response, "files": [{"path": "../escape.md", "content": "bad"}]}, "agent", 2)
    assert not (p.root.parent / "escape.md").exists()
    assert p.state["workbench"]["version"] == 2


def test_native_preview_explains_missing_libraries(client, monkeypatch):
    result = draft(client)
    monkeypatch.setattr(server.libs, "locate", lambda *_: None)
    response = client.post(f"/api/workbench/projects/{result['id']}/native")
    assert response.status_code == 503
    assert "KiCad" in response.json()["detail"]


def test_restoring_an_edit_creates_a_new_version_without_losing_history(client):
    result = draft(client)
    spec = result["spec"]
    spec["board"]["width_mm"] = 42
    url = f"/api/workbench/projects/{result['id']}"
    client.put(url + "/design", json={"base_version": 1, "spec": spec})
    history = client.get(url + "/history")
    assert history.status_code == 200
    assert [r["version"] for r in history.json()["versions"]] == [2, 1]
    restored = client.post(url + "/history/1/restore", json={"base_version": 2})
    assert restored.status_code == 200
    assert restored.json()["version"] == 3
    assert server.mgr().get(result["id"]).state["spec"]["board"]["width_mm"] == 30
    old = client.get(url + "/history/2").json()
    assert old["spec"]["board"]["width_mm"] == 42


def test_project_text_files_are_editable_with_conflict_and_reserved_path_guards(client):
    result = draft(client)
    url = f"/api/workbench/projects/{result['id']}/text/docs/requirements.md"
    created = client.put(url, json={"content": "# Requirements\n", "base_sha": None})
    assert created.status_code == 200
    sha = created.json()["sha"]
    assert client.get(url).json()["content"] == "# Requirements\n"
    assert client.put(url, json={"content": "new", "base_sha": "stale"}).status_code == 409
    assert client.put(url, json={"content": "# Updated\n", "base_sha": sha}).status_code == 200
    reserved = f"/api/workbench/projects/{result['id']}/text/state.json"
    assert client.put(reserved, json={"content": "{}", "base_sha": None}).status_code == 422


def test_protected_project_state_cannot_be_reached_through_a_symlink(client):
    result = draft(client)
    p = server.mgr().get(result["id"])
    (p.root / "notes.md").symlink_to(p.root / "state.json")
    url = f"/api/workbench/projects/{p.id}/text/notes.md"
    response = client.put(url, json={"content": "bad", "base_sha": None})
    assert response.status_code == 422
    assert json.loads((p.root / "state.json").read_text())["id"] == p.id


def test_simulation_reports_missing_engine_without_a_fake_pass(client, monkeypatch):
    from wholeboard import ngspice
    result = draft(client)
    monkeypatch.setattr(ngspice, "find", lambda *_: None)
    response = client.post(f"/api/workbench/projects/{result['id']}/simulate", json={})
    assert response.status_code == 503
    assert "ngspice" in response.json()["detail"]


def test_design_cannot_be_overwritten_during_an_engine_operation(client):
    result = draft(client)
    p = server.mgr().get(result["id"])
    p.engine_busy = True
    response = client.put(f"/api/workbench/projects/{p.id}/design", json={"base_version": 1, "spec": result["spec"]})
    assert response.status_code == 409
    assert p.state["workbench"]["version"] == 1


def test_native_build_invalidates_an_old_editor_version(client):
    import time
    from wholeboard import pipeline
    result = draft(client)
    p = server.mgr().get(result["id"])
    pipeline._record(p, {"ok": False, "stage": "drc", "by": "test"}, time.time())
    assert p.state["workbench"]["version"] == 2
    assert p.state["workbench"]["checks_stale"] is True
    assert (p.root / "history/design-v2.json").is_file()
    stale = client.put(f"/api/workbench/projects/{p.id}/design", json={"base_version": 1, "spec": result["spec"]})
    assert stale.status_code == 409


@pytest.mark.skipif(server.libs.locate("footprints") is None, reason="KiCad libraries are needed")
def test_pin_table_uses_real_footprint_pins_and_current_netlist(client):
    result = draft(client)
    response = client.get(f"/api/workbench/projects/{result['id']}/pins")
    assert response.status_code == 200
    pins = {p["id"]: p for p in response.json()["pins"]}
    assert pins["U1.1"]["net"] == "GND"
    assert pins["R1.1"]["net"] == "CC1"
    assert pins["J2.3"]["no_connect"] is True


def test_codex_tool_loop_applies_design_checks_it_and_returns_for_review(client, monkeypatch):
    from wholeboard import codex_bridge
    assert hasattr(codex_bridge, "request_once"), "Codex native-tool loop is not implemented"
    result = draft(client)
    p = server.mgr().get(result["id"])
    spec = result["spec"]
    spec["board"]["width_mm"] = 40
    turns = iter([
        {"message": "Checking the updated board.", "design_json": json.dumps(spec), "files": [], "review": [],
         "tools": [{"name": "validate_design", "arguments_json": "{}"}]},
        {"message": "Design checked; physical measurements remain pending.", "design_json": None, "files": [],
         "review": [{"requirement": "Physical acceptance", "status": "unknown", "evidence": "Not physically tested"}], "tools": []},
    ])
    # Only the external inference boundary is replaced; project edits and native validation stay real.
    monkeypatch.setattr(codex_bridge, "request_once", lambda *args: next(turns))
    codex_bridge.run(p, "Update and check the board", "agent")
    assert p.state["status"] == "idle"
    assert p.state["spec"]["board"]["width_mm"] == 40
    assert p.state["workbench"]["version"] == 2
    report = p.state["codex_tool_results"][-1]
    assert report["name"] == "validate_design"
    assert "errors" in report["result"]
    assert p.state["workbench_review"][0]["status"] == "unknown"
    assert [e["text"] for e in p.events if e.get("role") == "assistant"][-1].startswith("Design checked")


def test_codex_chat_cannot_call_mutating_engineering_tools(client):
    from wholeboard import codex_bridge
    assert hasattr(codex_bridge, "execute_tool"), "Codex tool policy is not implemented"
    result = draft(client)
    p = server.mgr().get(result["id"])
    with pytest.raises(ValueError, match="Chat"):
        codex_bridge.execute_tool(p, "build_project", {}, "chat")
    assert p.state["workbench"]["version"] == 1


def test_codex_history_compares_real_copper_edits_without_mutating_the_project(client):
    from wholeboard import codex_bridge
    assert 'design_history' in codex_bridge.TOOL_DESCRIPTIONS,'The reviewer cannot access design-version evidence'
    created=draft(client);pid=created['id'];spec=created['spec'];url=f'/api/workbench/projects/{pid}/design'
    spec['fixed_copper']=[{'net':'CC1','tracks':[{'a':[2,18],'b':[10,18],'w':.25,'layer':'F.Cu'}]}]
    assert client.put(url,json={'base_version':1,'spec':spec}).status_code==200
    spec['fixed_copper'][0]['tracks'][0]['w']=.24
    assert client.put(url,json={'base_version':2,'spec':spec}).status_code==200
    p=server.mgr().get(pid)
    report=codex_bridge.execute_tool(p,'design_history',{'from_version':2},'chat')
    assert report['from_version']==2 and report['to_version']==3
    assert report['field_change_count']==1
    assert report['field_changes']==[{'path':'/fixed_copper/0/tracks/0/w','kind':'changed','before':.25,'after':.24}]
    assert set(report['unchanged_sections'])>={'board','components','nets'}
    assert report['field_changes_truncated'] is False
    assert p.state['workbench']['version']==3
    assert client.get(f'/api/workbench/projects/{pid}/history/2/compare').json()['field_change_count']==1
    with pytest.raises(ValueError):codex_bridge.execute_tool(p,'design_history',{'from_version':'../../private'},'chat')


def test_native_board_3d_explains_missing_cad_engine(client, monkeypatch):
    from wholeboard import enclosure
    result = draft(client)
    monkeypatch.setattr(enclosure, "find_freecad", lambda *_: None)
    response = client.post(f"/api/workbench/projects/{result['id']}/engineering/board3d", json={})
    assert response.status_code == 503
    assert "FreeCAD" in response.json()["detail"]


def test_project_clone_copies_design_and_docs_without_private_run_history(client):
    result = draft(client)
    p = server.mgr().get(result["id"])
    (p.root / "docs").mkdir()
    (p.root / "docs/brief.md").write_text("# Reference brief")
    (p.root / ".codex-runs").mkdir()
    (p.root / ".codex-runs/private.log").write_text("Private runner details")
    p.chat("user", "Private conversation")
    p.state["enclosure_spec"] = {"wall_mm": 3.4, "lid_mm": 1.8}
    p.state["prompt"] = "Keep the USB-C port on the left and use 3.4 mm walls."
    response = client.post(f"/api/workbench/projects/{p.id}/clone", json={"title": "Power board copy"})
    assert response.status_code == 201
    clone = server.mgr().get(response.json()["id"])
    assert clone.state["spec"]["nets"] == p.state["spec"]["nets"]
    assert (clone.root / "docs/brief.md").read_text() == "# Reference brief"
    assert not (clone.root / ".codex-runs").exists()
    assert not any(e.get("text") == "Private conversation" for e in clone.events)
    assert clone.state["workbench"]["version"] == 1
    assert clone.state["enclosure_spec"] == {"wall_mm": 3.4, "lid_mm": 1.8}
    assert clone.state["prompt"] == p.state["prompt"]


def test_project_favorite_and_tags_are_persisted(client):
    result = draft(client)
    response = client.patch(f"/api/workbench/projects/{result['id']}/metadata", json={"starred": True, "tags": ["sensor", "template"]})
    assert response.status_code == 200
    row = next(p for p in client.get("/api/projects").json() if p["id"] == result["id"])
    assert row["starred"] is True
    assert row["tags"] == ["sensor", "template"]


def test_project_cannot_be_deleted_during_a_native_operation(client):
    result = draft(client)
    p = server.mgr().get(result["id"])
    p.engine_busy = True
    assert client.delete(f"/api/projects/{p.id}").status_code == 409
    assert (p.root / "state.json").exists()


def test_invalid_metadata_patch_has_no_partial_side_effect(client):
    result = draft(client)
    response = client.patch(f"/api/workbench/projects/{result['id']}/metadata", json={"starred": True, "tags": "bad"})
    assert response.status_code == 422
    assert not server.mgr().get(result["id"]).state.get("starred")


def test_kicad_models_are_found_in_user_app_installation(client, tmp_path, monkeypatch):
    from wholeboard import models3d
    home = tmp_path / "user-home"
    relative = "WorkbenchTest.3dshapes/Example.step"
    model = home / "Applications/KiCad/KiCad.app/Contents/SharedSupport/3dmodels" / relative
    model.parent.mkdir(parents=True)
    model.write_text("ISO-10303-21;")
    monkeypatch.setattr(models3d.Path, "home", lambda: home)
    monkeypatch.setattr(models3d.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(models3d, "CACHE", tmp_path / "model-cache")
    assert models3d.local(relative) == model


@pytest.mark.skipif(server.libs.locate("symbols") is None, reason="KiCad symbols are needed")
def test_schematic_editor_pose_and_rotation_survive_native_export(client, tmp_path):
    from wholeboard import sexpr
    from wholeboard.kicad import schematic
    result = draft(client)
    spec = result["spec"]
    spec["editor"] = {"positions": {"R1": [200, 300]}, "rotations": {"R1": 90}}
    folder = tmp_path / "schematic"
    folder.mkdir()
    output = schematic.build(spec, folder)
    tree = sexpr.parse(Path(output["sch"]).read_text())
    instances = sexpr.find_all(tree, "symbol")
    instance = next(n for n in instances if any(p[1] == "Reference" and p[2] == "R1" for p in sexpr.find_all(n, "property")))
    at = sexpr.find(instance, "at")
    assert [sexpr.num(n) for n in at[1:]] == pytest.approx([45.72, 58.42, 90])
    labels = [n for n in tree if isinstance(n, list) and sexpr.tag(n) in ("label", "global_label") and n[1] == "CC1"]
    assert any([sexpr.num(v) for v in sexpr.find(n, "at")[1:3]] == pytest.approx([41.91, 58.42]) for n in labels)
    assert output["extent"][0] < 41.91 < output["extent"][2]
    from wholeboard.kicad import cli
    if cli.find_kicad_cli():
        assert cli.erc(Path(output["sch"]))["clean"] is True


@pytest.mark.skipif(server.libs.locate("symbols") is None, reason="KiCad symbols are needed")
def test_schematic_view_returns_actual_library_symbol_graphics(client):
    result = draft(client)
    response = client.post("/api/workbench/schematic-view", json=result["spec"])
    assert response.status_code == 200
    data = response.json()
    resistor = next(s for s in data["symbols"] if s["ref"] == "R1" and s["unit"] == 1)
    definition = data["definitions"][resistor["definition"]]
    assert definition["lib_id"] == "Device:R"
    assert {p["number"] for p in definition["pins"]} == {"1", "2"}
    assert next(p for p in definition["pins"] if p["number"] == "1")["y"] == pytest.approx(3.81)
    assert any(g["kind"] == "rectangle" for g in definition["graphics"])


@pytest.mark.parametrize("editor", [{"positions": {"R1": ["NaN", 0]}}, {"rotations": {"R1": 45}}])
def test_editor_poses_require_finite_coordinates_and_quarter_turns(client, editor):
    result = draft(client)
    spec = result["spec"]
    spec["editor"] = editor
    response = client.put(f"/api/workbench/projects/{result['id']}/design", json={"base_version": 1, "spec": spec})
    assert response.status_code == 422


def test_browser_assets_use_a_revisioned_module_graph_and_revalidate(client, tmp_path, monkeypatch):
    import re
    original = server.WEB
    web = tmp_path / "web"
    web.mkdir()
    (web / "workbench.html").write_text((original / "workbench.html").read_text())
    module = web / "workbench-canvas.mjs"
    module.write_text("export const revision = 1;")
    monkeypatch.setattr(server, "WEB", web)
    html = client.get("/").text
    first = re.search(r'src="([^"]*workbench\.mjs[^"]*)"', html)[1]
    assert first.startswith("/assets/")
    module.write_text("export const revision = 200;")
    updated = client.get("/").text
    second = re.search(r'src="([^"]*workbench\.mjs[^"]*)"', updated)[1]
    assert first != second
    resource = client.get(second)
    assert resource.status_code == 200
    assert resource.headers["cache-control"] == "no-cache"


@pytest.mark.skipif(server.libs.locate("symbols") is None, reason="KiCad symbols are needed")
def test_schematic_view_preserves_native_hierarchical_sheets_and_ports(client):
    result = draft(client)
    spec = result["spec"]
    for component in spec["components"]:
        if component["ref"] in ("R1", "R2"):
            component["sheet"] = "Power"
    response = client.post("/api/workbench/schematic-view", json=spec)
    assert response.status_code == 200
    data = response.json()
    assert {s["name"] for s in data["sheets"]} == {"", "Power"}
    module = next(s for s in data["sheet_nodes"] if s["target"] == "Power")
    assert module["sheet"] == ""
    assert {p["net"] for p in module["ports"]} == {"CC1", "CC2", "GND"}
    assert next(s for s in data["symbols"] if s["ref"] == "R1")["sheet"] == "Power"


def test_codex_steering_is_queued_and_logged_for_the_active_worker(client):
    import threading
    result = draft(client)
    p = server.mgr().get(result["id"])
    finished = threading.Event()
    p.worker = threading.Thread(target=lambda: finished.wait(3))
    p.worker.start()
    p.set_status("running")
    try:
        response = client.post(f"/api/workbench/projects/{p.id}/steer", json={"text": "Keep the board dimensions"})
        assert response.status_code == 200
        assert p.inbox == ["Keep the board dimensions"]
        assert any(e.get("role") == "user" and e.get("text") == "Keep the board dimensions" for e in p.events)
    finally:
        finished.set()
        p.worker.join()


def test_codex_does_not_apply_a_proposal_superseded_by_new_user_steering(client, monkeypatch):
    from wholeboard import codex_bridge
    result = draft(client)
    p = server.mgr().get(result["id"])
    proposed = json.loads(json.dumps(p.state["spec"]))
    proposed["board"]["width_mm"] = 40
    turns = iter([
        {"message": "Old proposal", "design_json": json.dumps(proposed), "files": [], "review": [], "tools": []},
        {"message": "Kept the original dimensions", "design_json": None, "files": [], "review": [], "tools": []},
    ])
    def inference(*args):
        response = next(turns)
        if response["message"] == "Old proposal":
            p.inbox.append("Keep the width at 30 mm")
        return response
    monkeypatch.setattr(codex_bridge, "request_once", inference)
    codex_bridge.run(p, "Review the board", "agent")
    assert p.state["spec"]["board"]["width_mm"] == 30
    assert p.state["workbench"]["version"] == 1
    assert p.state["status"] == "idle"
    assert [e["text"] for e in p.events if e.get("role") == "assistant"][-1] == "Kept the original dimensions"


def test_codex_large_file_evidence_stays_valid_json_and_survives_later_tool_turns(client,monkeypatch):
    from wholeboard import codex_bridge
    created=draft(client);p=server.mgr().get(created['id']);path=p.root/'large.txt';path.write_text('Native evidence '+('0123456789'*15000))
    turns=[]
    def inference(project,prompt,*args):
        turns.append(prompt);empty={'message':'Reviewing','design_json':None,'files':[],'review':[],'tools':[]}
        if len(turns)==1:return {**empty,'tools':[{'name':'read_file','arguments_json':json.dumps({'path':'large.txt'})}]}
        evidence=json.loads(prompt.rsplit('\n',1)[-1])
        file=next(row['result'] for row in evidence if row['name']=='read_file')
        assert file['truncated'] is True and file['next_offset']<150016 and len(file['sha256'])==64
        if len(turns)==2:return {**empty,'tools':[{'name':'validate_design','arguments_json':'{}'}]}
        assert {row['name'] for row in evidence}>={'read_file','validate_design'}
        return {**empty,'files':[{'path':'docs/large-file-review.md','content':'Read the partial evidence; uninspected regions remain unknown.'}]}
    monkeypatch.setattr(codex_bridge,'request_once',inference);codex_bridge.run(p,'Review this file','agent')
    assert (p.root/'docs/large-file-review.md').is_file()
    assert p.state['workbench']['version']==1


def test_codex_file_chunks_can_be_reassembled_with_stable_hashes(client):
    from wholeboard import codex_bridge
    p=server.mgr().get(draft(client)['id']);(p.root/'sample.txt').write_text('alpha beta gamma')
    first=codex_bridge.execute_tool(p,'read_file',{'path':'sample.txt','offset':0,'limit':6},'chat')
    second=codex_bridge.execute_tool(p,'read_file',{'path':'sample.txt','offset':first['next_offset'],'limit':30},'chat')
    assert first['content']+second['content']=='alpha beta gamma'
    assert first['sha256']==second['sha256']
    assert first['truncated'] is True and second['truncated'] is False


def test_a_draft_can_get_a_real_manufacturing_estimate_without_a_prior_native_build(client):
    response = client.post("/api/workbench/projects", json={"title": "Unpopulated PCB estimate"})
    pid = response.json()["id"]
    http = TestClient(server.app, raise_server_exceptions=False)
    quote = http.post(f"/api/projects/{pid}/quote", json={"quantity": 5, "assembly": False})
    assert quote.status_code == 200, quote.text
    assert quote.json()["total"] > 0
    p = server.mgr().get(pid)
    assert p.state["quote"]["source_version"] == 1
    assert p.state["quote"]["quoted_at"] > 0
    assert (p.root / "rev0" / "quote.json").is_file()
    assert p.state["status"] == "idle"
    assert not p.engine_busy


def test_estimating_cannot_overlap_an_engine_operation_or_invalid_quantities(client):
    pid = client.post("/api/workbench/projects", json={"title": "Quote busy guard"}).json()["id"]
    p = server.mgr().get(pid)
    p.engine_busy = True
    http = TestClient(server.app, raise_server_exceptions=False)
    assert http.post(f"/api/projects/{pid}/quote", json={"assembly": False}).status_code == 409
    p.engine_busy = False
    assert http.post(f"/api/projects/{pid}/quote", json={"quantity": -1}).status_code == 422


@pytest.mark.parametrize("copper", [
    [{"net": "MISSING", "tracks": []}],
    [{"net": "GND", "tracks": [{"a": [0, 0], "b": [1, 2], "w": 0, "layer": "F.Cu"}]}],
    [{"net": "GND", "tracks": [{"a": ["NaN", 0], "b": [1, 2], "w": .25, "layer": "F.Cu"}]}],
    [{"net": "GND", "tracks": [{"a": [0, 0], "b": [1, 2], "w": .25, "layer": "In4.Cu"}]}],
    [{"net": "GND", "vias": [{"p": [10, 10], "d": .3, "drill": .6}]}],
])
def test_invalid_manual_copper_cannot_replace_the_saved_design(client, copper):
    result = draft(client)
    spec = result["spec"]
    spec["fixed_copper"] = copper
    response = client.put(f"/api/workbench/projects/{result['id']}/design", json={"base_version": 1, "spec": spec})
    assert response.status_code == 422
    assert server.mgr().get(result["id"]).state["workbench"]["version"] == 1


@pytest.mark.skipif(server.libs.locate("symbols") is None, reason="KiCad symbols are needed")
def test_native_checks_expose_the_unfiltered_erc_findings(client):
    result = draft(client)
    response = client.post(f"/api/workbench/projects/{result['id']}/native-checks")
    assert response.status_code == 200
    erc = response.json()["erc"]
    assert "ignored_list" in erc, "Filtered ERC evidence must remain available for review"
    assert sum(erc["ignored_by_type"].values()) == erc["ignored"]
    assert isinstance(erc["raw_clean"], bool)
    assert erc["raw_error_count"] >= len(erc["errors"])


@pytest.mark.skipif(server.libs.locate("symbols") is None, reason="KiCad symbols are needed")
def test_checks_use_the_same_final_native_pcb_shown_in_layout_and_preserve_its_artifacts(client):
    import hashlib
    from wholeboard.kicad import board
    result = draft(client)
    p = server.mgr().get(result["id"])
    actual = json.loads(json.dumps(p.state["spec"]))
    next(c for c in actual["components"] if c["ref"] == "C1")["placement"]["x_mm"] = 0
    folder = p.root / "rev1"
    folder.mkdir()
    built = board.build(actual, folder)
    pcb = Path(built["pcb"])
    p.state["artifacts"] = {"pcb": str(pcb)}
    p.state["workbench"]["checks_stale"] = False
    before = hashlib.sha256(pcb.read_bytes()).hexdigest()
    displayed = client.get(f"/api/workbench/projects/{p.id}/layout-geometry").json()
    assert displayed["source"] == "routed"
    report = client.post(f"/api/workbench/projects/{p.id}/native-checks").json()
    assert report.get("pcb_source") == "routed", "Checks regenerated a different PCB instead of checking the visible native artifact"
    assert any("edge" in finding["type"] for finding in report["drc"]["error_list"] + report["drc"]["warning_list"]), report["drc"]
    assert hashlib.sha256(pcb.read_bytes()).hexdigest() == before
    assert not pcb.with_suffix(".drc.json").exists(), "Checking must not overwrite a build's original report"


def test_ai_review_receives_mechanical_assumptions_and_manufacturing_estimate_scope(client):
    from wholeboard.codex_bridge import prompt_for
    result = draft(client)
    p = server.mgr().get(result["id"])
    p.state["workbench_board3d"] = {"version": 1, "size": [30, 22, 11.54], "unmatched_components": []}
    p.state["workbench_enclosure"] = {"version": 1, "summary": {"notes": ["J2 height is estimated; physical fit remains unverified."]}}
    p.state["quote"] = {"total": 25.89, "currency": "USD", "assumptions": ["Fee table estimate, not a confirmed manufacturer quote."]}
    prompt = prompt_for(p, "Review all current evidence", "chat")
    assert "J2 height is estimated; physical fit remains unverified." in prompt
    assert "Fee table estimate, not a confirmed manufacturer quote." in prompt
    assert "11.54" in prompt


def test_ai_file_proposal_cannot_overwrite_a_document_saved_during_inference(client, monkeypatch):
    from wholeboard import codex_bridge
    result = draft(client)
    p = server.mgr().get(result["id"])
    path = p.root / "docs" / "requirements.md"
    path.parent.mkdir()
    path.write_text("Original requirements")
    turns = []
    def inference(project, prompt, *args):
        turns.append(prompt)
        if len(turns) == 1:
            path.write_text("New human requirements")  # An external editor is outside the project's API lock.
            return {"message": "Old edit", "design_json": None, "files": [{"path": "docs/requirements.md", "content": "Outdated AI replacement"}], "review": [], "tools": []}
        return {"message": "Preserved the human edit", "design_json": None, "files": [], "review": [], "tools": []}
    monkeypatch.setattr(codex_bridge, "request_once", inference)
    codex_bridge.run(p, "Review the brief", "agent")
    assert path.read_text() == "New human requirements"
    assert len(turns) == 2
    assert p.state["status"] == "idle"


@pytest.mark.parametrize("extension", ["svg", "html"])
def test_active_project_documents_do_not_inherit_workspace_browser_authority(client, extension):
    result = draft(client)
    p = server.mgr().get(result["id"])
    (p.root / f"diagram.{extension}").write_text("<svg xmlns='http://www.w3.org/2000/svg'></svg>" if extension == "svg" else "<p>report</p>")
    response = client.get(f"/api/projects/{p.id}/files/diagram.{extension}")
    policy = response.headers.get("content-security-policy", "")
    assert policy.startswith("sandbox")
    assert "allow-same-origin" not in policy
    assert "default-src 'none'" in policy
    assert response.headers.get("x-content-type-options") == "nosniff"


@pytest.mark.skipif(server.libs.locate("symbols") is None, reason="KiCad symbols are needed")
def test_native_wire_preview_proves_exported_schematic_netlist_parity(client):
    result = draft(client)
    spec = result["spec"]
    spec["editor"]["connection_guides"] = [{"from": "R1.1", "to": "J1.A5"}]
    saved = client.put(f"/api/workbench/projects/{result['id']}/design", json={"base_version": 1, "spec": spec})
    assert saved.status_code == 200
    preview = client.post(f"/api/workbench/projects/{result['id']}/native")
    assert preview.status_code == 200
    assert preview.json().get("schematic_parity", {}).get("ok") is True
