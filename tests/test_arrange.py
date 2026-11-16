"""Arrange actual symbol/footprint bounds without changing electrical membership."""
import copy
from pathlib import Path

import pytest

from wholeboard import transforms, schematic_view
from wholeboard.kicad import schematic, cli
from test_transforms import circuit, wired, routed, native_geometry
from test_workbench import client


def heterogeneous():
    spec=circuit()
    spec['components'][1].update(ref='R1',symbol='Device:R',footprint='Resistor_SMD:R_0603_1608Metric')
    spec['nets']=[]
    spec['editor']={'positions':{'J1':[100,100],'R1':[400,200]},'rotations':{'R1':90}}
    return spec


@pytest.mark.parametrize('axis,edge,want',[
    ('x','min',{'J1':[100,100],'R1':[90,200]}),
    ('x','max',{'J1':[420,100],'R1':[400,200]}),
    ('x','center',{'J1':[260,100],'R1':[245,200]}),
    ('y','min',{'J1':[100,100],'R1':[400,78]}),
    ('y','max',{'J1':[100,178],'R1':[400,200]}),
    ('y','center',{'J1':[100,139],'R1':[400,139]}),
])
def test_six_alignment_commands_use_rotated_native_extents_not_origins(axis,edge,want):
    # Native J1 bounds relative to its origin: [-40,-30,10,30] editor units.
    # The native 90-degree resistor has bounds [-30,-8,30,8]. Text is excluded.
    spec=heterogeneous();before=copy.deepcopy(spec)
    result=transforms.prepare(spec,{'mode':'schematic','keys':['J1','R1'],'action':'align','axis':axis,'edge':edge})
    assert result['spec']['editor']['positions']==want
    assert result['spec']['components']==before['components'] and result['spec']['nets']==before['nets']
    assert result['spec']['editor']['rotations']==before['editor']['rotations']
    assert spec==before


def test_native_mirror_changes_the_alignment_extent():
    spec=heterogeneous();spec['editor']['mirrors']={'J1':'y'}
    result=transforms.prepare(spec,{'mode':'schematic','keys':['J1','R1'],'action':'align','axis':'x','edge':'min'})
    assert result['spec']['editor']['positions']=={'J1':[100,100],'R1':[120,200]}
    assert result['spec']['editor']['mirrors']=={'J1':'y'}


def test_equal_edge_gaps_keep_end_objects_and_account_for_unequal_widths():
    spec=heterogeneous();third=copy.deepcopy(spec['components'][0]);third['ref']='J2';spec['components'].append(third);spec['editor']['positions']['J2']=[900,500]
    result=transforms.prepare(spec,{'mode':'schematic','keys':['J2','R1','J1'],'action':'distribute','axis':'x'})
    assert result['spec']['editor']['positions']=={'J1':[100,100],'R1':[485,200],'J2':[900,500]}
    assert result['summary']['gap']==345
    origins=transforms.prepare(spec,{'mode':'schematic','keys':['J2','R1','J1'],'action':'distribute','axis':'x','basis':'origins'})
    assert origins['spec']['editor']['positions']['R1']==[500,200]


def test_uniform_nudge_moves_closed_wire_nodes_and_exact_paths_together():
    spec=wired();before=copy.deepcopy(spec)
    result=transforms.prepare(spec,{'mode':'schematic','keys':['J1','J2'],'action':'translate','delta':[20,10]})
    out=result['spec']
    assert out['editor']['positions']=={'J1':[120,110],'J2':[420,110]}
    assert out['editor']['wire_nodes']['mid']['position']==[270,90]
    assert out['editor']['connection_guides'][0]['fixed_points']==[[80,90],[270,90]]
    assert out['editor']['connection_guides'][1]['fixed_points']==[[270,90],[380,90]]
    assert out['nets']==spec['nets'] and out['components']==spec['components'] and spec==before


def test_nonrigid_alignment_keeps_shared_nodes_and_unmoved_wire_but_reroutes_moved_end():
    spec=wired();spec['editor']['positions']['J2']=[400,200]
    spec['editor']['connection_guides'][1]['fixed_points']=[[250,80],[360,80],[360,180]]
    result=transforms.prepare(spec,{'mode':'schematic','keys':['J1','J2'],'action':'align','axis':'y','edge':'min'})
    out=result['spec']
    assert out['editor']['positions']['J2']==[400,100]
    assert out['editor']['wire_nodes']==spec['editor']['wire_nodes']
    assert out['editor']['connection_guides'][0]==spec['editor']['connection_guides'][0]
    assert 'fixed_points' not in out['editor']['connection_guides'][1]
    assert result['summary']['rerouted_wires']==['b']


def test_nudge_a_later_unit_reroutes_its_logical_pin_without_moving_other_units(tmp_path):
    spec=circuit();spec['components'][1].update(ref='U1',symbol='Amplifier_Operational:LM358',footprint='Package_DIP:DIP-8_W7.62mm')
    spec['editor']={'positions':{'J1':[100,100],'U1':[100,500],'U1#2':[400,100],'U1#3':[700,500]},
                    'connection_guides':[{'id':'unit-two','from':'J1.1','to':'U1.7'}]}
    spec['nets']=[{'name':'SECOND_OUTPUT','pins':['J1.1','U1.7']}]
    result=transforms.prepare(spec,{'mode':'schematic','keys':['U1#2'],'action':'translate','delta':[10,20]})
    out=result['spec']
    assert out['editor']['positions']=={'J1':[100,100],'U1':[100,500],'U1#2':[410,120],'U1#3':[700,500]}
    native=schematic.build(out,tmp_path)
    assert schematic.netlist_parity(out,cli.schematic_nets(Path(native['sch'])))['ok']


def test_rigid_pcb_nudge_preserves_copper_ids_and_translates_native_endpoints(tmp_path):
    spec=routed();geometry=native_geometry(spec,tmp_path)
    result=transforms.prepare(spec,{'mode':'layout','keys':['J1','J2'],'action':'translate','delta':[1,2]},native_geometry=geometry)
    out=result['spec']
    assert [(c['placement']['x_mm'],c['placement']['y_mm']) for c in out['components']]==[(11,12),(26,12)]
    assert out['fixed_copper'][0]['tracks']==[{'id':'33333333-3333-4333-8333-000000000001','a':[11,12],'b':[26,12],'w':.25,'layer':'F.Cu'}]
    assert not result['summary']['requires_review'] and result['summary']['cleared_copper']==[]
    assert result['summary']['transformed_copper']['tracks']==3


def test_locked_unselected_pads_make_a_net_nonrigid_and_require_concrete_copper_review(tmp_path):
    spec=routed();spec['components'][1]['placement']['locked']=True
    result=transforms.prepare(spec,{'mode':'layout','keys':['J1','J2'],'action':'translate','delta':[1,2]},native_geometry=native_geometry(spec,tmp_path))
    assert result['spec']['components'][1]==spec['components'][1]
    assert result['summary']['skipped_locked']==['J2']
    assert result['summary']['requires_review'] and result['summary']['cleared_copper_count']==3
    assert {c['id'] for c in result['summary']['cleared_copper']}=={f'33333333-3333-4333-8333-{i:012d}' for i in (1,2,3)}
    assert result['spec']['fixed_copper']==[]


def test_noop_alignment_never_removes_fixed_copper(tmp_path):
    spec=routed()
    result=transforms.prepare(spec,{'mode':'layout','keys':['J1','J2'],'action':'align','axis':'y','edge':'min'},native_geometry=native_geometry(spec,tmp_path))
    assert result['spec']==spec and not result['summary']['changed']


def test_pcb_arrangement_rejects_out_of_board_origins_without_mutating_the_input(tmp_path):
    spec=routed();before=copy.deepcopy(spec)
    with pytest.raises(ValueError,match='board'):
        transforms.prepare(spec,{'mode':'layout','keys':['J1'],'action':'translate','delta':[-11,0]},native_geometry=native_geometry(spec,tmp_path))
    assert spec==before


def test_pcb_nudge_translates_zone_contours_without_changing_its_identity(tmp_path):
    from wholeboard import sexpr
    spec=routed();spec['fixed_zones']=[{'net':'SIG3','origin':[100,100],'source':'(zone (net "SIG3") (layer "B.Cu") (uuid "77777777-7777-4777-8777-000000000001") (hatch edge 0.5) (min_thickness 0.25) (fill yes) (polygon (pts (xy 108 108) (xy 127 108) (xy 127 117) (xy 108 117))))'}]
    result=transforms.prepare(spec,{'mode':'layout','keys':['J1','J2'],'action':'translate','delta':[1,2]},native_geometry=native_geometry(spec,tmp_path))
    zone=sexpr.parse(result['spec']['fixed_zones'][0]['source'])
    point=sexpr.find(sexpr.find(zone,'polygon'),'pts')[1]
    assert [float(value) for value in point[1:]]==[109,110]
    assert str(sexpr.find(zone,'uuid')[1])=='77777777-7777-4777-8777-000000000001'
    assert result['summary']['transformed_copper']['zones']==1


@pytest.mark.parametrize('options',[{'action':'align','axis':'z','edge':'min'},
    {'action':'align','axis':'x','edge':'wrong'}, {'action':'translate','delta':[float('nan'),0]},
    {'action':'distribute','axis':'x','basis':'unknown'}])
def test_invalid_arrange_options_never_change_the_input(options):
    spec=circuit();before=copy.deepcopy(spec)
    with pytest.raises(ValueError):transforms.prepare(spec,{'mode':'schematic','keys':['J1','J2'],**options})
    assert spec==before


@pytest.mark.parametrize('graphic,want',[
    ({'kind':'circle','center':[0,0],'radius':2.54},[80,80,120,120]),
    ({'kind':'arc','start':[2.54,0],'mid':[0,2.54],'end':[-2.54,0]},[80,80,120,100]),
    ({'kind':'bezier','points':[[0,0],[0,10.16],[10.16,10.16],[10.16,0]]},[100,40,180,100]),
])
def test_curved_symbol_bounds_use_real_extrema_not_centers_or_control_polygons(graphic,want):
    try:from wholeboard import arrange
    except ImportError:arrange=None
    assert arrange is not None,'Native-aware arrangement is missing'
    actual=arrange.symbol_bounds({'position':[100,100],'rotation':0,'mirror':''},{'graphics':[graphic],'pins':[]})
    assert actual==pytest.approx(want)


def test_a_full_board_zone_cannot_silently_move_beyond_the_board(tmp_path):
    spec=routed();spec['fixed_zones']=[{'net':'SIG3','origin':[100,100],'source':'(zone (net "SIG3") (layer "B.Cu") (uuid "77777777-7777-4777-8777-000000000001") (hatch edge 0.5) (min_thickness 0.25) (fill yes) (polygon (pts (xy 100 100) (xy 140 100) (xy 140 130) (xy 100 130))))'}]
    result=transforms.prepare(spec,{'mode':'layout','keys':['J1','J2'],'action':'translate','delta':[-1,0]},native_geometry=native_geometry(spec,tmp_path))
    assert result['summary']['requires_review']
    assert result['summary']['outside_copper'][0]['id']=='77777777-7777-4777-8777-000000000001'
    assert result['spec']['fixed_zones'],'An outlying candidate must be reviewed, not silently deleted'


def test_truncated_copper_rows_still_name_every_network_that_would_be_cleared(tmp_path):
    spec=routed();track=spec['fixed_copper'][0]['tracks'][0]
    spec['fixed_copper'][0]['tracks']=[{**track,'id':f'88888888-8888-4888-8888-{i:012d}'} for i in range(1001)]
    result=transforms.prepare(spec,{'mode':'layout','keys':['J1'],'action':'translate','delta':[1,0]},native_geometry=native_geometry(spec,tmp_path))
    assert result['summary']['cleared_copper_count']==1003
    assert len(result['summary']['cleared_copper'])==1000 and result['summary']['cleared_copper_truncated']
    assert result['summary']['cleared_nets']==['SIG1','SIG2','SIG3']


def test_ai_can_preview_a_real_arrangement_without_saving_it(client):
    from wholeboard import codex_bridge,server
    pid=client.post('/api/workbench/projects',json={'title':'Preview arrange','spec':routed()}).json()['id'];p=server.mgr().get(pid);before=copy.deepcopy(p.state['spec'])
    result=codex_bridge.execute_tool(p,'transform_selection',{'mode':'schematic','keys':['J1','J2'],'action':'translate','delta':[20,0],'base_version':1,'preview_only':True},'agent')
    assert result['preview_only'] and result['summary']['changed'] and result['native_parity']['ok']
    assert p.state['spec']==before and p.state['workbench']['version']==1


def test_curved_native_courtyard_uses_its_full_outline_instead_of_coarse_cached_extents(tmp_path):
    from wholeboard import sexpr
    from wholeboard.kicad import board,geometry
    spec=routed();path=Path(board.build(spec,tmp_path)['pcb']);tree=sexpr.parse(path.read_text())
    for footprint in sexpr.find_all(tree,'footprint'):
        ref=next(p[2] for p in sexpr.find_all(footprint,'property') if p[1]=='Reference');radius=3 if ref=='J1' else 1
        footprint[:]=[part for part in footprint if not isinstance(part,list) or not (sexpr.find(part,'layer') and str(sexpr.find(part,'layer')[1]) in ('F.CrtYd','B.CrtYd'))]
        footprint.append(sexpr.parse(f'(fp_circle (center 0 0) (end {radius} 0) (stroke (width 0.05) (type default)) (fill none) (layer "F.CrtYd"))'))
    path.write_text(sexpr.dumps(tree));actual=geometry.read(path)
    result=transforms.prepare(spec,{'mode':'layout','keys':['J1','J2'],'action':'align','axis':'x','edge':'min'},native_geometry=actual)
    assert [c['placement']['x_mm'] for c in result['spec']['components']]==[10,8]


def test_ai_layout_arrangement_requires_review_for_native_drc_errors_even_without_cleared_copper(client):
    from wholeboard import codex_bridge,server
    spec=circuit();spec['components'][1]['placement'].update(y_mm=15.08,rotation=180)
    pid=client.post('/api/workbench/projects',json={'title':'DRC arrange review','spec':spec}).json()['id'];p=server.mgr().get(pid);before=copy.deepcopy(p.state['spec'])
    result=codex_bridge.execute_tool(p,'transform_selection',{'mode':'layout','keys':['J1','J2'],'action':'align','axis':'x','edge':'min','basis':'origins','base_version':1},'agent')
    assert result.get('requires_review') and result['drc']['errors']>0
    assert result['summary']['cleared_copper_count']==0
    assert p.state['spec']==before and p.state['workbench']['version']==1
