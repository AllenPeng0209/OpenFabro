"""Instance pad edits must survive native regeneration without changing a shared library."""
import copy,json,hashlib
from pathlib import Path
import pytest
from wholeboard import server,sexpr,workbench_native,design_identity
from wholeboard.kicad import board,geometry,cli
from test_project_library import custom_spec
from test_workbench import client


def fixture():
    spec=custom_spec();spec['components'].append({**copy.deepcopy(spec['components'][0]),'ref':'U2','placement':{'x_mm':25,'y_mm':11,'rotation':0,'locked':True}})
    spec['nets'][0]['pins'].append('U2.1');spec['nets'][1]['pins'].append('U2.2')
    return spec


def create(client,spec=None):
    pid=client.post('/api/workbench/projects',json={'title':'Instance pad QA','spec':spec or fixture()}).json()['id'];native=client.post(f'/api/workbench/projects/{pid}/native').json();pad=next(p for p in json.load(open(native['geometry_file']))['pads'] if p['ref']=='U1' and p['name']=='1');return pid,native,pad


def prepare(client,pid,pad,patch):
    response=client.post(f'/api/workbench/projects/{pid}/pads/prepare',json={'base_version':1,'ref':'U1','pad_id':pad['id'],'patch':patch});assert response.status_code==200,response.text;return response.json()


def test_layout_size_preview_is_private_and_only_the_selected_instance_changes(client):
    spec=fixture();pid,native,pad=create(client,spec);root=Path(native['pcb']).parent;before={p:(p.read_bytes(),p.stat().st_mtime_ns) for p in root.rglob('*') if p.is_file()};result=prepare(client,pid,pad,{'w':1.4,'h':1.8})
    assert result['native_parity']['ok'] and result['pad_report']['native_probe']['ok'] and result['native_source']
    assert server.mgr().get(pid).state['workbench']['version']==1 and server.mgr().get(pid).state['spec']==spec
    assert result['spec']['library']==spec['library'] and result['spec']['nets']==spec['nets']
    actual={ (p['ref'],p['name']):p for p in result['geometry']['pads']};assert [actual['U1','1']['w'],actual['U1','1']['h']]==[1.4,1.8]
    assert actual['U1','1']['id']==pad['id'] and [actual['U2','1']['w'],actual['U2','1']['h']]==[1,1.5]
    assert all((p.read_bytes(),p.stat().st_mtime_ns)==value for p,value in before.items())
    response=client.put(f'/api/workbench/projects/{pid}/design',json={'base_version':1,'spec':result['spec'],'native_source':result['native_source']});assert response.status_code==200,response.text
    saved=client.post(f'/api/workbench/projects/{pid}/native').json();again=next(p for p in json.load(open(saved['geometry_file']))['pads'] if p['id']==pad['id']);assert again['w']==1.4 and again['h']==1.8


def test_duplicate_numbered_pads_are_not_edited_as_one_logical_pin(client):
    spec=fixture();pads=spec['library']['footprints']['DemoFP']['pads'];pads.append({**copy.deepcopy(pads[0]),'x':0,'y':4})
    pid,native,pad=create(client,spec);same=[p for p in json.load(open(native['geometry_file']))['pads'] if p['ref']=='U1' and p['name']=='1'];assert len(same)==2
    result=prepare(client,pid,same[1],{'w':1.7});by={p['id']:p for p in result['geometry']['pads']};assert by[same[1]['id']]['w']==1.7 and by[same[0]['id']]['w']==1


def test_bottom_rotated_pad_uses_board_coordinates_and_retains_uuid(client):
    spec=fixture();spec['components'][0]['placement'].update(rotation=37,side='bottom');pid,native,pad=create(client,spec)
    result=prepare(client,pid,pad,{'position':[12,9],'rotation':90});actual=next(p for p in result['geometry']['pads'] if p['id']==pad['id'])
    assert [actual['x'],actual['y']]==pytest.approx([112,109],abs=.0001) and actual['rot']==pytest.approx(90) and actual['back'] and not actual['front']
    assert result['spec']['components'][0]['placement']==spec['components'][0]['placement']


def test_local_mask_paste_and_clearance_are_consumed_by_native_kicad(client,tmp_path):
    pid,native,pad=create(client);result=prepare(client,pid,pad,{'mask_margin_mm':.1,'paste_margin_mm':-.03,'paste_ratio_pct':-10,'clearance_mm':.25})
    out=board.build(result['spec'],tmp_path);tree=sexpr.parse(Path(out['pcb']).read_text());fp=next(f for f in sexpr.find_all(tree,'footprint') if any(c[1:3]==['Reference','U1'] for c in f if sexpr.tag(c)=='property'));item=next(p for p in sexpr.find_all(fp,'pad') if sexpr.find(p,'uuid')[1]==pad['id'])
    for field,value in [('solder_mask_margin',.1),('solder_paste_margin',-.03),('solder_paste_margin_ratio',-.1),('clearance',.25)]:assert sexpr.num(sexpr.find(item,field)[1])==pytest.approx(value)
    target=tmp_path/'native.svg';res=cli.run(['pcb','export','svg','--mode-single','--page-size-mode','0','--exclude-drawing-sheet','-l','F.Mask','-o',str(target),out['pcb']]);assert res.returncode==0 and target.is_file()


@pytest.mark.parametrize('patch',[
    {'w':0},{'h':True},{'position':[1,float('nan')]},{'rotation':float('inf')},
    {'kind':'unknown'},{'connected_layers':['Nonexistent.Cu']},{'paste_ratio_pct':-101},
    {'drill_size':[0,1]},{'clearance_mm':-1},{'net':'ChangedWithoutConnectivityReview'},
])
def test_invalid_pad_edits_never_save(client,patch):
    pid,native,pad=create(client);response=client.post(f'/api/workbench/projects/{pid}/pads/prepare',json={'base_version':1,'ref':'U1','pad_id':pad['id'],'patch':patch}) if not any(isinstance(v,float) and not __import__('math').isfinite(v) for v in patch.values()) and 'position' not in patch else client.post(f'/api/workbench/projects/{pid}/pads/prepare',content=json.dumps({'base_version':1,'ref':'U1','pad_id':pad['id'],'patch':patch}),headers={'Content-Type':'application/json'})
    assert response.status_code in (400,422) and server.mgr().get(pid).state['workbench']['version']==1


def test_changing_surface_copper_side_also_moves_mask_and_paste(client):
    pid,native,pad=create(client);result=prepare(client,pid,pad,{'connected_layers':['B.Cu']});actual=next(p for p in result['geometry']['pads'] if p['id']==pad['id'])
    assert actual['back'] and not actual['front'] and actual['layers']==['B.Cu','B.Paste','B.Mask']


def test_reset_restores_base_and_cloned_components_keep_instance_geometry(client,tmp_path):
    pid,native,pad=create(client);result=prepare(client,pid,pad,{'w':1.4});assert client.put(f'/api/workbench/projects/{pid}/design',json={'base_version':1,'spec':result['spec'],'native_source':result['native_source']}).status_code==200
    client.post(f'/api/workbench/projects/{pid}/native');reset=client.post(f'/api/workbench/projects/{pid}/pads/prepare',json={'base_version':2,'ref':'U1','pad_id':pad['id'],'patch':{'reset':True}});assert reset.status_code==200,reset.text
    assert not reset.json()['spec']['components'][0].get('pad_overrides')
    cloned=copy.deepcopy(result['spec']);cloned['components'][1]['pad_overrides']=copy.deepcopy(cloned['components'][0]['pad_overrides']);pcb=Path(board.build(cloned,tmp_path)['pcb']);actual=geometry.read(pcb)
    assert [p['w'] for p in actual['pads'] if p['name']=='1']==[1.4,1.4]


def test_changed_base_does_not_rebind_an_override_to_a_different_physical_pad(client,tmp_path):
    pid,native,pad=create(client);result=prepare(client,pid,pad,{'w':1.4});changed=copy.deepcopy(result['spec']);changed['library']['footprints']['DemoFP']['pads'][0]['x']-=1
    with pytest.raises(ValueError,match='no longer matches'):board.build(changed,tmp_path)


def test_source_pcb_change_after_review_blocks_acceptance(client):
    pid,native,pad=create(client);result=prepare(client,pid,pad,{'w':1.4});pcb=Path(native['pcb']);pcb.write_text(pcb.read_text()+'\n');response=client.put(f'/api/workbench/projects/{pid}/design',json={'base_version':1,'spec':result['spec'],'native_source':result['native_source']})
    assert response.status_code==409 and server.mgr().get(pid).state['workbench']['version']==1


def test_readonly_inspection_and_agent_instance_edits_share_review_guards(client):
    from wholeboard import codex_bridge
    pid,native,pad=create(client);p=server.mgr().get(pid);args={'base_version':1,'ref':'U1','pad_id':pad['id'],'patch':{'w':1.4}}
    before={q:(q.read_bytes(),q.stat().st_mtime_ns) for q in p.root.rglob('*') if q.is_file()};read=codex_bridge.execute_tool(p,'inspect_layout_pad',{'ref':'U1','pad_id':pad['id']},'chat')
    assert read['properties']['w']==1 and read['properties']['position']==[13,11] and read['copper_layers']==['F.Cu','B.Cu']
    assert all((q.read_bytes(),q.stat().st_mtime_ns)==value for q,value in before.items())
    with pytest.raises(ValueError):codex_bridge.execute_tool(p,'edit_layout_pad',args,'chat')
    preview=codex_bridge.execute_tool(p,'edit_layout_pad',{**args,'preview_only':True},'agent');assert preview['preview_only'] and preview['pad_report']['native_probe']['ok'] and p.state['workbench']['version']==1
    blocked=codex_bridge.execute_tool(p,'edit_layout_pad',args,'agent');assert blocked['requires_review'] and p.state['workbench']['version']==1
    applied=codex_bridge.execute_tool(p,'edit_layout_pad',{**args,'accept_findings':True},'agent');assert applied['ok'] and p.state['workbench']['version']==2


def test_instance_edit_retains_routed_copper_and_reports_new_native_errors(client):
    spec=fixture();spec['fixed_copper']=[{'net':'SIGNAL','tracks':[{'id':'66666666-6666-4666-8666-000000000101','a':[13,11],'b':[23,11],'w':.25,'layer':'F.Cu','locked':True}],'arcs':[{'id':'66666666-6666-4666-8666-000000000102','a':[23,11],'m':[24,12],'b':[25,11],'w':.25,'layer':'F.Cu'}],'vias':[{'id':'66666666-6666-4666-8666-000000000103','p':[23,11],'d':.6,'drill':.3,'layers':['F.Cu','B.Cu']}]}]
    pid,native,pad=create(client,spec);before=geometry.read(Path(native['pcb']));result=prepare(client,pid,pad,{'w':10})
    for kind in ('tracks','arcs','vias'):assert result['geometry'][kind]==before[kind]
    assert result['pad_report']['needs_review'] and result['pad_report']['native_probe']['after_drc']['errors']>result['pad_report']['native_probe']['before_drc']['errors']
    assert result['spec']['nets']==spec['nets']


def test_custom_instance_resize_keeps_void_and_uses_actual_copper_anchor(client):
    from shapely.geometry import Polygon,Point
    from shapely import union_all
    spec=fixture();spec['library']['footprints']['DemoFP']['pads'][0].update(shape='custom',w=4,h=4,custom_shape={'path':'M -2 -2 L 2 -2 L 2 -1 L -1 -1 L -1 2 L -2 2 Z','units':'mm'})
    pid,native,pad=create(client,spec);result=prepare(client,pid,pad,{'w':2,'h':2});actual=next(p for p in result['geometry']['pads'] if p['id']==pad['id']);shape=union_all([Polygon(points) for points in actual['copper_polygons']]);assert shape.area==pytest.approx(1.75,abs=.001) and not shape.covers(Point(0,0));assert shape.covers(Point(actual['routing_anchor'][0]-actual['x'],actual['routing_anchor'][1]-actual['y']))


def test_rule_only_edit_preserves_existing_physical_layers_and_unsupported_padstack(client,tmp_path):
    pid,native,pad=create(client);first=prepare(client,pid,pad,{'connected_layers':['B.Cu']});assert client.put(f'/api/workbench/projects/{pid}/design',json={'base_version':1,'spec':first['spec'],'native_source':first['native_source']}).status_code==200
    client.post(f'/api/workbench/projects/{pid}/native');response=client.post(f'/api/workbench/projects/{pid}/pads/prepare',json={'base_version':2,'ref':'U1','pad_id':pad['id'],'patch':{'clearance_mm':.3}});assert response.status_code==200,response.text
    actual=next(p for p in response.json()['geometry']['pads'] if p['id']==pad['id']);assert actual['back'] and not actual['front'] and actual['layers']==['B.Cu','B.Paste','B.Mask']


def test_selective_plated_annuli_match_actual_native_layers(client,tmp_path):
    spec=fixture();spec['board']['layers']=4;spec['library']['footprints']['DemoFP']['pads'][0].update(kind='thru_hole',shape='circle',w=2,h=2,drill=.8)
    pid,native,pad=create(client,spec);result=prepare(client,pid,pad,{'connected_layers':['F.Cu','In1.Cu']});actual=next(p for p in result['geometry']['pads'] if p['id']==pad['id']);assert actual['kind']=='thru_hole' and 'In1.Cu' in actual['layers'] and 'B.Cu' not in actual['layers']
    pcb=Path(board.build(result['spec'],tmp_path)['pcb']);out=cli.drc(pcb,refill=False,save=False);assert not any('layer' in e['type'] or 'padstack' in e['type'] for e in out['error_list']); saved=client.put(f'/api/workbench/projects/{pid}/design',json={'base_version':1,'spec':result['spec'],'native_source':result['native_source']});assert saved.status_code==200;client.post(f'/api/workbench/projects/{pid}/native');again=client.post(f'/api/workbench/projects/{pid}/pads/prepare',json={'base_version':2,'ref':'U1','pad_id':pad['id'],'patch':{'clearance_mm':.3}});assert again.status_code==200,again.text;selected=next(p for p in again.json()['geometry']['pads'] if p['id']==pad['id']);assert selected['layers']==actual['layers'],'A rule-only change silently reconnects every plated-pad annulus'
    for layer in ('F.Cu','In1.Cu','B.Cu'):
        target=tmp_path/(layer+'.svg');res=cli.run(['pcb','export','svg','--mode-single','--page-size-mode','0','--exclude-drawing-sheet','--drill-shape-opt','0','-l',layer,'-o',str(target),str(pcb)]);assert res.returncode==0 and target.is_file(),res.stderr


def test_stackup_remaps_instance_annuli_and_rejects_silent_layer_loss(client):
    from wholeboard import stackup
    spec=fixture();spec['board']['layers']=4;spec['library']['footprints']['DemoFP']['pads'][0].update(kind='thru_hole',shape='circle',w=2,h=2,drill=.8)
    pid,native,pad=create(client,spec);edited=prepare(client,pid,pad,{'connected_layers':['F.Cu','In1.Cu']})['spec']
    result=stackup.prepare(edited,{'template':'standard-2'});assert result['spec'] is None and any(row['layer']=='In1.Cu' for row in result['stackup_report']['conflicts'])
    mapped=stackup.prepare(edited,{'template':'standard-2','layer_map':{'In1.Cu':'B.Cu'}});assert mapped['spec'] is not None
    node=sexpr.parse(next(iter(mapped['spec']['components'][0]['pad_overrides'].values()))['source']);assert sexpr.find(node,'layers')[1:]==['F.Cu','B.Cu','*.Mask']


def test_inactive_physical_layer_cannot_be_injected_through_saved_instance_source(client):
    pid,native,pad=create(client);result=prepare(client,pid,pad,{'w':1.4});entry=next(iter(result['spec']['components'][0]['pad_overrides'].values()));node=sexpr.parse(entry['source']);sexpr.find(node,'layers')[1]='In7.Cu';entry['source']=sexpr.dumps(node)
    r=client.put(f'/api/workbench/projects/{pid}/design',json={'base_version':1,'spec':result['spec']});assert r.status_code==422 and server.mgr().get(pid).state['workbench']['version']==1


def test_native_override_policy_rebuilds_ignored_historical_instances_without_touching_them(client):
    pid,native,pad=create(client);result=prepare(client,pid,pad,{'w':1.4});assert client.put(f'/api/workbench/projects/{pid}/design',json={'base_version':1,'spec':result['spec'],'native_source':result['native_source']}).status_code==200
    p=server.mgr().get(pid);current=workbench_native.generate(p);current.pop('pad_instance_policy',None);p.state['workbench_native']=current
    frozen={q:(q.read_bytes(),q.stat().st_mtime_ns) for q in Path(current['pcb']).parent.rglob('*') if q.is_file()};new=workbench_native.generate(p)
    assert new.get('pad_instance_policy')=='native-pad-instances-v1' and new['pcb']!=current['pcb']
    assert all((q.read_bytes(),q.stat().st_mtime_ns)==value for q,value in frozen.items())


def test_selective_annulus_barrel_contact_is_not_claimed_as_automatic_route_proof(client):
    from wholeboard.kicad import connectivity
    spec=fixture();spec['board']['layers']=4;spec['library']['footprints']['DemoFP']['pads'][0].update(kind='thru_hole',shape='circle',w=2,h=2,drill=.8)
    pid,native,pad=create(client,spec);result=prepare(client,pid,pad,{'connected_layers':['F.Cu','In1.Cu']});actual=next(p for p in result['geometry']['pads'] if p['id']==pad['id']);assert actual.get('padstack_continuity_unknown') is True
    with pytest.raises(ValueError,match='per-layer|barrel'):connectivity.validate_pad_models(result['geometry'])


def test_native_local_thermal_and_zone_properties_are_real_supported_pad_tokens(client):
    pid,native,pad=create(client);result=prepare(client,pid,pad,{'zone_connect':2,'thermal_gap_mm':.4,'thermal_spoke_mm':.35});assert result['pad_report']['native_probe']['ok']
    node=sexpr.parse(next(iter(result['spec']['components'][0]['pad_overrides'].values()))['source']);assert sexpr.num(sexpr.find(node,'thermal_bridge_width')[1])==pytest.approx(.35)


def test_editing_one_pad_does_not_rewrite_sibling_placement_defaults(client):
    spec=fixture();spec['components'][1]['placement']['rotation']=270
    pid,native,pad=create(client,spec);result=prepare(client,pid,pad,{'w':1.4})
    assert result['spec']['components'][1]==spec['components'][1], 'Unchanged sibling placement defaults/rotation must retain its source representation'
    assert result['spec']['components'][0]['placement']==spec['components'][0]['placement']


def test_actual_external_native_placement_is_still_adopted_when_editing_another_pad(client):
    pid,native,pad=create(client);pcb=Path(native['pcb']);tree=sexpr.parse(pcb.read_text());fp=next(f for f in sexpr.find_all(tree,'footprint') if any(row[1:3]==['Reference','U2'] for row in sexpr.find_all(f,'property')));sexpr.find(fp,'at')[1]=sexpr.fmt(126);pcb.write_text(sexpr.dumps(tree))
    result=prepare(client,pid,pad,{'w':1.4});u2=next(c for c in result['spec']['components'] if c['ref']=='U2');assert u2['placement']['x_mm']==26 and u2['placement']['y_mm']==11
    assert next(f for f in result['geometry']['footprints'] if f['ref']=='U2')['x']==126


def test_pad_edit_preserves_exact_existing_source_copper_and_missing_optional_fields(client):
    spec=fixture();spec['board']['ground_pour']=None;spec['fixed_copper']=[{'net':'SIGNAL','tracks':[{'id':'66666666-6666-4666-8666-000000000301','a':[13,11],'b':[23,11],'w':.25,'layer':'F.Cu','locked':True}]}]
    pid,native,pad=create(client,spec);result=prepare(client,pid,pad,{'w':1.4})
    assert json.dumps(result['spec']['fixed_copper'],sort_keys=True)==json.dumps(spec['fixed_copper'],sort_keys=True),'Unchanged source copper must not acquire redundant nets, empty arrays or number rewriting'
    assert 'fixed_zones' not in result['spec']


def test_pad_edit_preserves_authored_zone_source_after_native_refill(client):
    from wholeboard.kicad.copper import capture_zone
    spec=fixture();spec['board']['ground_pour']=None;spec['fixed_zones']=[capture_zone(board.zone('GND','F.Cu',30,22,1,.2),'GND',[100,100])]
    pid,native,pad=create(client,spec);result=prepare(client,pid,pad,{'w':1.4})
    assert json.dumps(result['spec']['fixed_zones'],sort_keys=True)==json.dumps(spec['fixed_zones'],sort_keys=True),'Native refill serialization must not rewrite an unchanged authored zone when editing a pad'


def test_actual_external_native_zone_change_is_adopted_when_editing_a_pad(client):
    from wholeboard.kicad.copper import capture_zone
    spec=fixture();spec['board']['ground_pour']=None;spec['fixed_zones']=[capture_zone(board.zone('GND','F.Cu',30,22,1,.2),'GND',[100,100])]
    pid,native,pad=create(client,spec);pcb=Path(native['pcb']);tree=sexpr.parse(pcb.read_text());zone=next(sexpr.find_all(tree,'zone'));points=sexpr.find(sexpr.find(zone,'polygon'),'pts');points[1][1]=sexpr.fmt(102);pcb.write_text(sexpr.dumps(tree));result=prepare(client,pid,pad,{'w':1.4})
    assert result['spec']['fixed_zones']!=spec['fixed_zones'] and result['geometry']['zone_definitions'][0]['polygons'][0][0]==[102,101]
