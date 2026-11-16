import copy
import pytest
from wholeboard import server,stackup,codex_bridge
from test_workbench import client
from test_buses import example
from test_stackup import recipe


def create(client,spec=None):
    r=client.post('/api/workbench/projects',json={'title':'Physical stackup review','spec':spec or example()});assert r.status_code==201,r.text
    return r.json()['id']


def test_stackup_inventory_and_templates_are_read_only(client):
    pid=create(client);p=server.mgr().get(pid);before=copy.deepcopy(p.state['spec'])
    response=client.get(f'/api/workbench/projects/{pid}/stackup');assert response.status_code==200
    result=response.json();assert result['inferred'] is True and result['stackup']['name']=='Standard 2 Layer'
    names={x['name'] for x in result['templates']};assert {'Standard 1 Layer','Standard 12 Layer','JLC04161H-7628','JLC04161H-3313'}<=names
    assert p.state['spec']==before and p.state['workbench']['version']==1


def test_stackup_private_preview_preserves_copper_and_saves_only_when_requested(client):
    pid=create(client);p=server.mgr().get(pid);before=copy.deepcopy(p.state['spec']);r=client.post(f'/api/workbench/projects/{pid}/stackup/prepare',json={'base_version':1,'stackup':recipe()});assert r.status_code==200,r.text
    result=r.json();assert result['spec']['board']['layers']==4 and result['spec']['board']['thickness_mm']==1.6 and result['native_parity']['ok']
    assert result['spec']['nets']==before['nets']
    signature=lambda spec:sorted([(g['net'],t['id'],[round(v,6) for v in t['a']],[round(v,6) for v in t['b']],t['w'],t['layer'],t.get('locked',True)) for g in spec['fixed_copper'] for t in g.get('tracks',[])],key=lambda r:r[1])
    assert signature(result['spec'])==signature(before)
    assert result['stackup_report']['ready'] and result['stackup_report']['copper_count']==4
    assert p.state['spec']==before and p.state['workbench']['version']==1
    saved=client.put(f'/api/workbench/projects/{pid}/design',json={'base_version':1,'spec':result['spec']});assert saved.status_code==200
    assert p.state['workbench']['version']==2 and p.state['spec']['board']['stackup']['layers'][2]['epsilon_r']==4.1


def test_used_removed_layer_requires_explicit_mapping_or_removal(client):
    spec=example();spec['board'].update(layers=4,thickness_mm=1.6,stackup=recipe());spec['fixed_copper'][0]['tracks'][0]['layer']='In1.Cu';pid=create(client,spec)
    body={'base_version':1,'template':'standard-2'};unresolved=client.post(f'/api/workbench/projects/{pid}/stackup/prepare',json=body);assert unresolved.status_code==200,unresolved.text
    assert unresolved.json()['spec'] is None and any(c['layer']=='In1.Cu' for c in unresolved.json()['stackup_report']['conflicts'])
    mapped=client.post(f'/api/workbench/projects/{pid}/stackup/prepare',json={**body,'layer_map':{'In1.Cu':'F.Cu'}});assert mapped.status_code==200,mapped.text
    track=mapped.json()['spec']['fixed_copper'][0]['tracks'][0];assert track['layer']=='F.Cu' and track['id']=='11111111-1111-4111-8111-000000000001'
    dropped=client.post(f'/api/workbench/projects/{pid}/stackup/prepare',json={**body,'layer_map':{'In1.Cu':None}});assert dropped.status_code==200,dropped.text
    assert dropped.json()['stackup_report']['removed_copper']['tracks']==1
    assert not any(t['id']=='11111111-1111-4111-8111-000000000001' for g in dropped.json()['spec']['fixed_copper'] for t in g.get('tracks',[]))


def test_reordered_inner_foil_keeps_copper_identity(client):
    spec=example();spec['board'].update(layers=4,thickness_mm=1.6,stackup=recipe());spec['fixed_copper'][0]['tracks'][0]['layer']='In1.Cu';pid=create(client,spec);changed=recipe();changed['layers'][3],changed['layers'][5]=changed['layers'][5],changed['layers'][3]
    r=client.post(f'/api/workbench/projects/{pid}/stackup/prepare',json={'base_version':1,'stackup':changed});assert r.status_code==200,r.text
    track=r.json()['spec']['fixed_copper'][0]['tracks'][0];assert track['layer']=='In2.Cu' and track['id']=='11111111-1111-4111-8111-000000000001'


def test_via_endpoints_cannot_collapse_while_mapping_layers(client):
    spec=example();spec['fixed_copper'][0]['vias']=[{'id':'22222222-2222-4222-8222-000000000001','p':[9,5],'d':.6,'drill':.3,'layers':['F.Cu','B.Cu'],'type':'through'}];pid=create(client,spec)
    r=client.post(f'/api/workbench/projects/{pid}/stackup/prepare',json={'base_version':1,'template':'standard-1','layer_map':{'B.Cu':'F.Cu'}});assert r.status_code==200,r.text
    assert r.json()['spec'] is None and r.json()['stackup_report']['issues']


def test_agent_does_not_apply_unresolved_stackup_layer_loss(client):
    spec=example();spec['board'].update(layers=4,thickness_mm=1.6,stackup=recipe());spec['fixed_copper'][0]['tracks'][0]['layer']='In1.Cu';pid=create(client,spec);p=server.mgr().get(pid)
    result=codex_bridge.execute_tool(p,'edit_stackup',{'template':'standard-2'},'agent')
    assert result['ok'] is False and result['needs_stackup_review'] and p.state['workbench']['version']==1


def test_project_stackup_preset_is_portable_source_not_a_global_secret(client):
    pid=create(client);p=server.mgr().get(pid);r=client.post(f'/api/workbench/projects/{pid}/stackup/prepare',json={'base_version':1,'stackup':recipe(),'save_preset':'My four layer'})
    assert r.status_code==200,r.text
    assert r.json()['spec']['library']['stackups']['My four layer']['name']=='Asymmetric four layer'
    assert 'stackups' not in p.state['spec'].get('library',{})


def test_stale_stackup_preview_never_overwrites_saved_source(client):
    pid=create(client);p=server.mgr().get(pid);r=client.post(f'/api/workbench/projects/{pid}/stackup/prepare',json={'base_version':0,'stackup':recipe()})
    assert r.status_code==409 and p.state['workbench']['version']==1


@pytest.mark.parametrize('presets',['invalid',{'Bad':{'schema':1,'name':'Bad','layers':[]}},{'constructor':recipe()}])
def test_malformed_project_constructions_cannot_be_saved(client,presets):
    spec=example();spec['library']={'symbols':{},'footprints':{},'parts':{},'stackups':presets}
    assert client.post('/api/workbench/projects',json={'title':'Invalid preset','spec':spec}).status_code==422


def test_changing_generated_plane_net_rebuilds_that_plane_but_keeps_manual_copper(client):
    spec=example();spec['board'].update(layers=4,thickness_mm=1.6,stackup=recipe(),planes={'In1.Cu':'GND'});spec['board']['stackup']['layers'][3]['net']='GND';spec['nets'] += [{'name':'GND','pins':[]},{'name':'VCC','pins':[]}];pid=create(client,spec);changed=recipe();changed['layers'][3]['net']='VCC'
    r=client.post(f'/api/workbench/projects/{pid}/stackup/prepare',json={'base_version':1,'stackup':changed});assert r.status_code==200,r.text
    value=r.json();assert value['spec']['board']['planes']['In1.Cu']=='VCC'
    assert not any(z['net']=='GND' and 'In1.Cu' in z.get('layers',[]) for z in value['spec']['fixed_zones'])
    assert any(z['net']=='VCC' and 'In1.Cu' in z.get('layers',[]) for z in value['geometry']['zone_definitions'])


def test_manual_zone_migration_changes_native_source_layer_too(client):
    from wholeboard.kicad import board,copper
    spec=example();spec['board'].update(layers=4,thickness_mm=1.6,stackup=recipe());zone=board.zone('USB1_DP','In1.Cu',25,20,.3,.2)
    from wholeboard import sexpr
    sexpr.find(zone,'uuid')[1]='33333333-3333-4333-8333-000000000001';spec['fixed_zones']=[copper.capture_zone(zone,'USB1_DP',board.ORIGIN)];pid=create(client,spec)
    r=client.post(f'/api/workbench/projects/{pid}/stackup/prepare',json={'base_version':1,'template':'standard-2','layer_map':{'In1.Cu':'F.Cu'}});assert r.status_code==200,r.text
    value=r.json();saved=sexpr.parse(value['spec']['fixed_zones'][0]['source']);assert str(sexpr.find(saved,'layer')[1])=='F.Cu'
    assert any(z['net']=='USB1_DP' and 'F.Cu' in z.get('layers',[]) for z in value['geometry']['zone_definitions'])


def test_through_via_defaults_are_part_of_the_same_reviewed_operation(client):
    pid=create(client);r=client.post(f'/api/workbench/projects/{pid}/stackup/prepare',json={'base_version':1,'template':'standard-4','via':{'diameter_mm':.8,'drill_mm':.4}})
    assert r.status_code==200,r.text
    assert r.json()['spec']['rules']['via_diameter_mm']==.8 and r.json()['spec']['rules']['via_drill_mm']==.4
    bad=client.post(f'/api/workbench/projects/{pid}/stackup/prepare',json={'base_version':1,'template':'standard-4','via':{'diameter_mm':.3,'drill_mm':.4}})
    assert bad.status_code==422


def test_reviewed_copper_digest_is_enforced_when_applying_stackup(client):
    from pathlib import Path
    pid=create(client);p=server.mgr().get(pid);r=client.post(f'/api/workbench/projects/{pid}/stackup/prepare',json={'base_version':1,'stackup':recipe()});assert r.status_code==200,r.text
    value=r.json();assert isinstance(value.get('native_source'),dict),'Stackup review is not bound to the current copper bytes'
    pcb=Path(p.state['workbench_native']['pcb']);pcb.write_text(pcb.read_text()+'\n; controlled native revision\n')
    rejected=client.put(f'/api/workbench/projects/{pid}/design',json={'base_version':1,'spec':value['spec'],'native_source':value['native_source']})
    assert rejected.status_code==409 and p.state['workbench']['version']==1


def test_agent_rechecks_copper_after_private_stackup_review(client,monkeypatch):
    from pathlib import Path
    from wholeboard import buses
    pid=create(client);p=server.mgr().get(pid);actual=buses.project_draft
    def changed(project,args):
        result=actual(project,args);pcb=Path(project.state['workbench_native']['pcb']);pcb.write_text(pcb.read_text()+'\n; controlled race\n');return result
    monkeypatch.setattr(buses,'project_draft',changed)
    with pytest.raises(Exception) as raised:codex_bridge.execute_tool(p,'edit_stackup',{'template':'standard-4'},'agent')
    assert getattr(raised.value,'status_code',None)==409 and p.state['workbench']['version']==1
