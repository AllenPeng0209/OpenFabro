"""Selection transforms must agree with actual KiCad pin geometry and connectivity."""
import copy
from pathlib import Path

import pytest

from wholeboard import schematic_view, sexpr
from wholeboard.kicad import schematic, cli
try:
    from wholeboard import transforms
except ImportError:
    transforms=None


def circuit():
    return {'name':'selection_transform','board':{'width_mm':40,'height_mm':30,'layers':2,'ground_pour':None},
      'components':[{'ref':f'J{i}','value':'Header','symbol':'Connector_Generic:Conn_01x03','footprint':'Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical','placement':{'x_mm':10+(i-1)*15,'y_mm':10}} for i in (1,2)],
      'nets':[{'name':f'SIG{i}','pins':[f'J1.{i}',f'J2.{i}']} for i in (1,2,3)],
      'editor':{'positions':{'J1':[100,100],'J2':[400,100]},'connection_guides':[{'id':'joined','from':'J1.1','to':'J2.1'}]}}


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('axis',['x','y'])
def test_native_mirrored_symbol_keeps_real_pin_connections_at_every_right_angle(tmp_path,angle,axis):
    spec=circuit();before=copy.deepcopy(spec['components']);spec['editor'].update(rotations={'J1':angle},mirrors={'J1':axis})
    out=schematic.build(spec,tmp_path);sch=Path(out['sch']);tree=sexpr.parse(sch.read_text())
    inst=next(s for s in sexpr.find_all(tree,'symbol') if any(p[1:3]==['Reference','J1'] for p in sexpr.find_all(s,'property')))
    assert sexpr.find(inst,'mirror') is not None,'The native symbol ignored the saved mirror'
    assert str(sexpr.find(inst,'mirror')[1])==axis
    proof=schematic.netlist_parity(spec,cli.schematic_nets(sch))
    assert proof['ok'],proof
    scene=schematic_view.scene(spec);j1=next(s for s in scene['symbols'] if s['ref']=='J1')
    assert j1['mirror']==axis,'Browser pin coordinates must use the actual native mirror'
    assert spec['components']==before,'Schematic mirroring must preserve physical PCB poses'


def prepared(spec,args,**kwargs):
    assert transforms is not None,'Selection transforms are missing'
    return transforms.prepare(spec,args,**kwargs)


def wired():
    spec=circuit();spec['editor']['rotations']={'J1':0,'J2':0}
    spec['editor']['wire_nodes']={'mid':{'position':[250,80],'sheet':'','net':'SIG1','label':{'kind':'net','rotation':0}}}
    spec['editor']['connection_guides']=[{'id':'a','from':'J1.1','to':'node:mid','fixed_points':[[60,80],[250,80]]},{'id':'b','from':'node:mid','to':'J2.1','fixed_points':[[250,80],[360,80]]}]
    return spec


def test_group_rotation_moves_internal_wire_geometry_and_preserves_electrical_and_physical_data():
    spec=wired();before=copy.deepcopy(spec)
    result=prepared(spec,{'mode':'schematic','keys':['J1','J2'],'action':'rotate','angle':90,'pivot':[250,100]})
    out=result['spec'];assert spec==before
    assert out['editor']['positions']=={'J1':[250,-50],'J2':[250,250]}
    assert out['editor']['rotations']=={'J1':270,'J2':270}
    assert out['editor']['wire_nodes']['mid']['position']==[270,100]
    assert out['editor']['wire_nodes']['mid']['label']['rotation']==270
    assert out['editor']['connection_guides'][0]['fixed_points']==[[270,-90],[270,100]]
    assert out['nets']==before['nets'] and out['components']==before['components']


def test_individual_rotation_does_not_move_the_other_symbol_or_shared_wire_node():
    spec=wired();out=prepared(spec,{'mode':'schematic','keys':['J1'],'action':'rotate','angle':90,'individual':True})['spec']
    assert out['editor']['positions']==spec['editor']['positions']
    assert out['editor']['rotations']=={'J1':270,'J2':0}
    assert out['editor']['wire_nodes']==spec['editor']['wire_nodes']
    assert 'fixed_points' not in out['editor']['connection_guides'][0]
    assert out['editor']['connection_guides'][1]==spec['editor']['connection_guides'][1]


def test_horizontal_flip_uses_native_mirrors_and_preserves_rotated_pin_connections(tmp_path):
    spec=circuit();spec['editor']['rotations']={'J1':90}
    out=prepared(spec,{'mode':'schematic','keys':['J1','J2'],'action':'flip_horizontal','pivot':[250,100]})['spec']
    assert out['editor']['positions']=={'J1':[400,100],'J2':[100,100]}
    native=schematic.build(out,tmp_path)
    assert schematic.netlist_parity(out,cli.schematic_nets(Path(native['sch'])))['ok']
    again=prepared(out,{'mode':'schematic','keys':['J1','J2'],'action':'flip_horizontal','pivot':[250,100]})['spec']
    assert again['editor']['positions']==spec['editor']['positions']
    assert not any(again['editor'].get('mirrors',{}).values())


def routed():
    spec=circuit()
    for c in spec['components']:c['placement'].update(rotation=0,side='top')
    spec['fixed_copper']=[{'net':f'SIG{i}','tracks':[{'id':f'33333333-3333-4333-8333-{i:012d}','a':[10,10+(i-1)*2.54],'b':[25,10+(i-1)*2.54],'w':.25,'layer':'F.Cu'}]} for i in (1,2,3)]
    return spec


def native_geometry(spec,tmp_path):
    from wholeboard.kicad import board,geometry
    return geometry.read(Path(board.build(spec,tmp_path)['pcb']))


def test_layout_group_rotation_preserves_actual_copper_identity_and_shape(tmp_path):
    spec=routed();spec['fixed_copper'][0].update(arcs=[{'id':'44444444-4444-4444-8444-000000000001','a':[12,18],'m':[13,17],'b':[14,18],'w':.25,'layer':'F.Cu'}],vias=[{'id':'44444444-4444-4444-8444-000000000002','p':[12,18],'d':.6,'drill':.3,'layers':['F.Cu','B.Cu']}])
    source=native_geometry(spec,tmp_path);before=copy.deepcopy(spec)
    result=prepared(spec,{'mode':'layout','keys':['J1','J2'],'action':'rotate','angle':90,'pivot':[17.5,15]},native_geometry=source)
    out=result['spec'];assert spec==before and out['nets']==spec['nets']
    assert [(c['placement']['x_mm'],c['placement']['y_mm'],c['placement']['rotation']) for c in out['components']]==[(22.5,7.5,270),(22.5,22.5,270)]
    assert out['fixed_copper'][0]['tracks'][0]['a']==[22.5,7.5] and out['fixed_copper'][0]['tracks'][0]['b']==[22.5,22.5]
    assert out['fixed_copper'][0]['arcs'][0]['m']==[15.5,10.5]
    assert out['fixed_copper'][0]['vias'][0]['p']==[14.5,9.5]
    assert out['fixed_copper'][0]['tracks'][0]['id']==spec['fixed_copper'][0]['tracks'][0]['id']
    assert result['summary']['cleared_nets']==[] and not result['summary']['requires_review']


def test_partial_or_locked_layout_selection_requires_review_before_clearing_boundary_copper(tmp_path):
    spec=routed();spec['components'][1]['placement']['locked']=True;geo=native_geometry(spec,tmp_path)
    result=prepared(spec,{'mode':'layout','keys':['J1','J2'],'action':'rotate','angle':90,'pivot':[17.5,15]},native_geometry=geo)
    assert result['spec']['components'][1]==spec['components'][1]
    assert result['summary']['skipped_locked']==['J2']
    assert result['summary']['requires_review'] and result['summary']['cleared_nets']==['SIG1','SIG2','SIG3']
    assert result['spec']['fixed_copper']==[]


def test_flip_layer_mirrors_each_footprint_without_moving_its_origin(tmp_path):
    spec=routed();spec['components'][0]['placement']['rotation']=90;geo=native_geometry(spec,tmp_path)
    result=prepared(spec,{'mode':'layout','keys':['J1'],'action':'flip_layer'},native_geometry=geo)
    pose=result['spec']['components'][0]['placement']
    assert pose['x_mm']==10 and pose['y_mm']==10 and pose['side']=='bottom' and pose['rotation']==270
    assert result['spec']['components'][1]==spec['components'][1]
    assert not result['summary']['requires_review'] and result['spec']['fixed_copper']==spec['fixed_copper']


def test_rotation_preserves_native_zone_identity_and_all_outline_contours(tmp_path):
    spec=routed();spec['fixed_zones']=[{'net':'SIG3','origin':[100,100],'source':'(zone (net "SIG3") (layer "B.Cu") (uuid "55555555-5555-4555-8555-000000000001") (hatch edge 0.5) (min_thickness 0.25) (fill yes (thermal_gap 0.3) (thermal_bridge_width 0.3)) (polygon (pts (xy 108 108) (xy 127 108) (xy 127 117) (xy 108 117))) (polygon (pts (xy 111 111) (xy 112 111) (xy 112 112) (xy 111 112))))'}]
    out=prepared(spec,{'mode':'layout','keys':['J1','J2'],'action':'rotate','angle':90,'pivot':[17.5,15]},native_geometry=native_geometry(spec,tmp_path))['spec']
    zone=sexpr.parse(out['fixed_zones'][0]['source']);polys=list(sexpr.find_all(zone,'polygon'))
    assert len(polys)==2 and str(sexpr.find(zone,'uuid')[1])=='55555555-5555-4555-8555-000000000001'
    assert [sexpr.num(v) for v in sexpr.find(polys[0],'pts')[1][1:]]==[124.5,105.5]
    assert [sexpr.num(v) for v in sexpr.find(polys[1],'pts')[1][1:]]==[121.5,108.5]


def test_boundary_zone_review_reports_the_actual_native_zone_identity_and_layer(tmp_path):
    spec=routed();spec['fixed_zones']=[{'net':'SIG3','origin':[100,100],'source':'(zone (net "SIG3") (layer "B.Cu") (uuid "55555555-5555-4555-8555-000000000001") (hatch edge 0.5) (min_thickness 0.25) (fill yes) (polygon (pts (xy 108 108) (xy 127 108) (xy 127 117) (xy 108 117))))'}]
    result=prepared(spec,{'mode':'layout','keys':['J1'],'action':'rotate','angle':90,'pivot':[17.5,15]},native_geometry=native_geometry(spec,tmp_path))
    zone=next(item for item in result['summary']['cleared_copper'] if item['kind']=='zones')
    assert zone['id']=='55555555-5555-4555-8555-000000000001' and zone['layer']=='B.Cu'


def test_module_capture_and_instantiation_preserve_symbol_mirrors():
    from wholeboard import modules
    spec=circuit();spec['editor']['mirrors']={'J1':'y'}
    asset=modules.publish(spec,name='Mirrored connector')
    assert asset['design']['editor'].get('mirrors')=={'J1':'y'}
    host={'name':'host','board':{'width_mm':60,'height_mm':40,'layers':2},'components':[],'nets':[],'library':{'modules':{'Mirror':asset}}}
    out=modules.instantiate(host,'Mirror','M1')
    ref=out['editor']['module_instances']['M1']['source_maps']['refs']['J1']
    assert out['editor']['mirrors'][ref]=='y'


def test_published_module_updates_merge_native_mirror_changes():
    from wholeboard import modules,module_updates
    spec=circuit();spec['editor']['mirrors']={'J1':'x'};asset=modules.publish(spec,name='Mirror')
    host={'name':'host','board':{'width_mm':60,'height_mm':40,'layers':2},'components':[],'nets':[],'library':{'modules':{'Mirror':asset}}}
    host=modules.instantiate(host,'Mirror','M1');ref=host['editor']['module_instances']['M1']['source_maps']['refs']['J1']
    changed=copy.deepcopy(spec);changed['editor']['mirrors']['J1']='y'
    host['library']['modules']['Mirror']=module_updates.release(modules.publish(changed,name='Mirror'),previous=asset)
    proposal=module_updates.prepare(host,'M1');assert proposal['spec']['editor']['mirrors'][ref]=='y'


def test_horizontal_flip_also_changes_the_attached_label_direction():
    spec=wired();out=prepared(spec,{'mode':'schematic','keys':['J1','J2'],'action':'flip_horizontal','pivot':[250,100]})['spec']
    assert out['editor']['wire_nodes']['mid']['label']['rotation']==180


def test_copper_impact_only_lists_nets_with_actual_removed_objects(tmp_path):
    spec=routed();spec['fixed_copper']=spec['fixed_copper'][:1]
    result=prepared(spec,{'mode':'layout','keys':['J1'],'action':'rotate','angle':90,'pivot':[17.5,15]},native_geometry=native_geometry(spec,tmp_path))
    assert result['summary']['cleared_nets']==['SIG1']


def test_empty_mirror_metadata_does_not_create_a_false_module_release():
    from wholeboard import modules,module_updates
    previous=modules.publish(circuit(),name='Mirror');previous['design']['editor'].pop('mirrors',None)
    candidate=modules.publish(circuit(),name='Mirror')
    with pytest.raises(ValueError,match='No module changes'):module_updates.release(candidate,previous=previous)


def test_deleting_a_mirrored_terminal_cannot_mirror_a_new_terminal_reusing_its_ref():
    from wholeboard import terminals
    spec=terminals.prepare(circuit(),{'action':'add','name':'OLD'})['spec'];spec['editor']['mirrors']={'TP1':'x'}
    out=terminals.prepare(spec,{'action':'delete','ref':'TP1'})['spec']
    assert 'TP1' not in out['editor']['mirrors']


def test_layer_flip_uses_real_asymmetric_smd_pad_geometry(tmp_path):
    spec={'name':'smd_flip','board':{'width_mm':25,'height_mm':25,'layers':2,'ground_pour':None},'components':[{'ref':'Q1','value':'Q_NPN','symbol':'Transistor_BJT:Q_NPN_BCE','footprint':'Package_TO_SOT_SMD:SOT-23','placement':{'x_mm':10,'y_mm':10,'rotation':90,'side':'top'}}],'nets':[{'name':f'SIG{i}','pins':[f'Q1.{i}']} for i in (1,2,3)]}
    before=native_geometry(spec,tmp_path/'before');out=prepared(spec,{'mode':'layout','keys':['Q1'],'action':'flip_layer'},native_geometry=before)['spec'];after=native_geometry(out,tmp_path/'after')
    assert all(p['back'] and not p['front'] for p in after['pads'])
    for old in before['pads']:
        new=next(p for p in after['pads'] if p['name']==old['name'])
        assert new['x']==old['x'] and new['y']==pytest.approx(220-old['y']) and new['net']==old['net']


def test_layer_flip_retains_routes_on_physically_unchanged_through_pads(tmp_path):
    from wholeboard.kicad.connectivity import airwires
    spec=routed();before=native_geometry(spec,tmp_path/'before')
    result=prepared(spec,{'mode':'layout','keys':['J1','J2'],'action':'flip_layer'},native_geometry=before)
    assert result['summary']['cleared_nets']==['SIG2','SIG3']
    assert [group['net'] for group in result['spec']['fixed_copper']]==['SIG1']
    after=native_geometry(result['spec'],tmp_path/'after')
    sig1={key:[item for item in after.get(key,[]) if item.get('net')=='SIG1'] for key in ('pads','tracks','arcs','vias','zones')};sig1['layers']=after['layers']
    assert airwires(sig1)==[]


@pytest.mark.parametrize('mode',['schematic','layout'])
def test_a_single_object_rotates_about_its_own_origin(tmp_path,mode):
    spec=routed();kwargs={'native_geometry':native_geometry(spec,tmp_path)} if mode=='layout' else {}
    out=prepared(spec,{'mode':mode,'keys':['J1'],'action':'rotate','angle':90},**kwargs)['spec']
    if mode=='schematic':assert out['editor']['positions']['J1']==[100,100]
    else:assert [out['components'][0]['placement'][k] for k in ('x_mm','y_mm')]==[10,10]


@pytest.mark.parametrize('kind',['ground','power'])
def test_group_mirror_preserves_the_actual_power_symbol_transform(tmp_path,kind):
    spec=wired();spec['editor']['wire_nodes']['mid']['label']['kind']=kind
    out=prepared(spec,{'mode':'schematic','keys':['J1','J2'],'action':'flip_horizontal','pivot':[250,100]})['spec']
    native=schematic.build(out,tmp_path);tree=sexpr.parse(Path(native['sch']).read_text())
    power=next(s for s in sexpr.find_all(tree,'symbol') if str(sexpr.find(s,'lib_id')[1]).startswith('power:'))
    assert sexpr.find(power,'mirror') is not None,'A rotation alone turns the mirrored ground/power glyph upside down'
    assert str(sexpr.find(power,'mirror')[1])=='x' and sexpr.num(sexpr.find(power,'at')[3])==180
    assert schematic.netlist_parity(out,cli.schematic_nets(Path(native['sch'])))['ok']


def test_power_annotation_rejects_an_invalid_mirror_axis():
    from wholeboard.net_labels import validate_label
    with pytest.raises(ValueError):validate_label({'kind':'ground','rotation':0,'mirror':'other'})


def test_a_real_multi_unit_symbol_transforms_only_the_selected_unit(tmp_path):
    spec=circuit();spec['components'][0].update(ref='U1',symbol='Amplifier_Operational:LM358',footprint='Package_SO:SOIC-8_3.9x4.9mm_P1.27mm')
    spec['nets']=[{'name':name,'pins':[f'U1.{pin}',f'J2.{i}']} for i,(name,pin) in enumerate([('OUT1',1),('OUT2',7),('PLUS2',5)],1)]
    spec['editor']={'positions':{'U1':[100,100],'U1#2':[350,100],'U1#3':[500,150],'J2':[600,100]}}
    out=prepared(spec,{'mode':'schematic','keys':['U1#2'],'action':'flip_horizontal'})['spec']
    native=schematic.build(out,tmp_path);tree=sexpr.parse(Path(native['sch']).read_text());units=[s for s in sexpr.find_all(tree,'symbol') if any(p[1:3]==['Reference','U1'] for p in sexpr.find_all(s,'property'))]
    assert sexpr.find(next(s for s in units if sexpr.num(sexpr.find(s,'unit')[1])==1),'mirror') is None
    assert sexpr.find(next(s for s in units if sexpr.num(sexpr.find(s,'unit')[1])==2),'mirror') is not None
    assert out['editor']['positions']==spec['editor']['positions'] and out['components']==spec['components']
    assert schematic.netlist_parity(out,cli.schematic_nets(Path(native['sch'])))['ok']


@pytest.mark.parametrize('args',[
 {'mode':'other','keys':['J1'],'action':'rotate','angle':90},
 {'mode':'schematic','keys':['J99'],'action':'rotate','angle':90},
 {'mode':'schematic','keys':['J1'],'action':'rotate','angle':45},
 {'mode':'schematic','keys':['J1'],'action':'rotate','angle':float('nan')},
 {'mode':'schematic','keys':['J1'],'action':'rotate','angle':90,'pivot':[True,0]},
 {'mode':'schematic','keys':['J1'],'action':'flip_layer'},
])
def test_invalid_transform_requests_do_not_enter_a_design(args):
    with pytest.raises(ValueError):prepared(circuit(),args)
