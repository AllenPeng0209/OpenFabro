"""Terminal bus properties drive real constraints without joining electrical nets."""
import copy
from pathlib import Path
import pytest
from wholeboard import sexpr,design,modules
from wholeboard.kicad import board,geometry,cli
try:
    from wholeboard import buses
except ImportError:
    buses=None

def example():
    return {'name':'bus_constraints','board':{'width_mm':25,'height_mm':20,'layers':2,'ground_pour':None,'timing':{'track_ps_per_mm':{'F.Cu':7},'via_ps_per_mm':0}},
      'components':[{'ref':f'J{i}','value':'Header','symbol':'Connector_Generic:Conn_01x04','footprint':'Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical','placement':{'x_mm':5+(i-1)*10,'y_mm':5,'rotation':0}} for i in (1,2)],
      'nets':[{'name':name,'class':'signal','pins':[f'J1.{i}',f'J2.{i}']} for i,name in enumerate(['USB1_DP','USB1_DN','USB2_DP','USB2_DN'],1)],
      'fixed_copper':[{'net':name,'tracks':[{'id':f'11111111-1111-4111-8111-{i:012d}','a':[5,5+(i-1)*2.54],'b':[15,5+(i-1)*2.54],'w':.25,'layer':'F.Cu'}]} for i,name in enumerate(['USB1_DP','USB1_DN','USB2_DP','USB2_DN'],1)]}

def prepare(spec,args):
    assert buses is not None,'Terminal Bus Group/Bus Type authoring is missing'
    return buses.prepare(spec,args)

def pair(spec,pins=('J1.1','J1.2'),group='USB_1',**extra):
    return prepare(spec,{'action':'pins','pins':list(pins),'patch':{'bus_group':group,'bus_type':'USB 2.0','pair':'DATA','pair_role':'Data','impedance_ohms':90,'pn_skew_ps':10,'max_length_mm':5,**extra}})['spec']

def test_bus_group_edits_do_not_join_nets_move_parts_or_clear_copper():
    spec=example();before=copy.deepcopy(spec);out=pair(spec)
    assert spec==before and out['nets']==before['nets'] and out['fixed_copper']==before['fixed_copper']
    assert [c['placement'] for c in out['components']]==[c['placement'] for c in before['components']]
    assert out['components'][0]['pin_properties']['1']['bus_group']=='USB_1'

def test_two_interfaces_with_the_same_type_keep_separate_pair_identities():
    spec=pair(example());spec=pair(spec,('J1.3','J1.4'),'USB_2')
    result=buses.compile(spec);pairs=[g for g in result['groups'] if g['kind']=='diff']
    assert {tuple(g['nets']) for g in pairs}=={('USB1_DP','USB1_DN'),('USB2_DP','USB2_DN')}
    assert len({g['bus_id'] for g in pairs})==2

def test_unconnected_bus_members_remain_pending_instead_of_inventing_connections():
    spec=example();spec['nets'][0]['pins'].remove('J1.1');before=copy.deepcopy(spec);out=pair(spec)
    assert out['nets']==before['nets']
    result=buses.compile(out);assert result['issues'] and not result['groups']

@pytest.mark.parametrize('args',[
 {'action':'pins','pins':['J1.99'],'patch':{'bus_group':'USB'}},
 {'action':'pins','pins':['J1.1'],'patch':{'pn_skew_ps':-1}},
 {'action':'pins','pins':['J1.1'],'patch':{'pin_delay_ps':True}},
 {'action':'pins','pins':['J1.1'],'patch':{'pin_delay_ps':2200}},
 {'action':'pins','pins':['J1.1'],'patch':{'impedance_ohms':float('nan')}},
 {'action':'pins','pins':['J1.1'],'patch':{'bus_group':'bad\nname'}},
 {'action':'pins','pins':['J1.1'],'patch':{'unknown_property':1}},
])
def test_invalid_terminal_properties_cannot_enter_a_design(args):
    with pytest.raises(ValueError):prepare(example(),args)

def test_native_export_keeps_pad_delay_and_enforces_a_bus_length_limit(tmp_path):
    spec=pair(example());spec=prepare(spec,{'action':'pins','pins':['J1.1'],'patch':{'pin_delay_ps':10}})['spec']
    out=board.build(spec,tmp_path);tree=sexpr.parse(Path(out['pcb']).read_text());j1=next(f for f in sexpr.find_all(tree,'footprint') if any(p[1]=='Reference' and p[2]=='J1' for p in sexpr.find_all(f,'property')));pad=next(p for p in sexpr.find_all(j1,'pad') if str(p[1])=='1')
    assert sexpr.num(sexpr.find(pad,'die_delay')[1])==10,'PCB text stores picoseconds; KiCad scales this to internal attoseconds'
    check=cli.drc(Path(out['pcb']),refill=False,save=False)
    assert any('length' in row['type'] and 'BUS' in row.get('description','') for row in check['error_list']+check['warning_list']),check

def test_bus_delay_check_uses_explicit_layer_model_and_pin_delays_and_marks_unrouted_unknown(tmp_path):
    spec=pair(example());spec=prepare(spec,{'action':'pins','pins':['J1.1'],'patch':{'pin_delay_ps':10}})['spec'];spec=prepare(spec,{'action':'pins','pins':['J1.2'],'patch':{'pin_delay_ps':30}})['spec'];spec=prepare(spec,{'action':'pins','pins':['J2.1','J2.2'],'patch':{'pin_delay_ps':5}})['spec']
    geo=geometry.read(Path(board.build(spec,tmp_path)['pcb']));result=buses.analyze(spec,geo);row=next(p for p in result['pairs'] if p['nets']==['USB1_DP','USB1_DN'])
    assert row['delay_ps']=={'USB1_DP':73.1,'USB1_DN':93.1} and row['skew_ps']==20 and row['status']=='fail'
    assert row['length_mm']=={'USB1_DP':8.3,'USB1_DN':8.3},'Exclude the0.85mm inside each endpoint pad'
    geo['tracks']=[t for t in geo['tracks'] if t['net']!='USB1_DN'];row=buses.analyze(spec,geo)['pairs'][0];assert row['timing_status']=='unknown' and row['skew_ps'] is None and row['status']!='pass'

def test_published_bus_metadata_keeps_instance_nets_private(tmp_path):
    spec=pair(example());asset=modules.publish(spec,name='USB bus');host={'name':'bus_instances','board':{'width_mm':60,'height_mm':30,'layers':2,'ground_pour':None},'components':[],'nets':[],'library':{'modules':{'USB':asset}}}
    out=modules.instantiate(host,'USB','M1');out=modules.instantiate(out,'USB','M2',offset=[30,0]);pairs=[g for g in buses.compile(out)['groups'] if g['kind']=='diff']
    assert {tuple(g['nets']) for g in pairs}=={('M1_USB1_DP','M1_USB1_DN'),('M2_USB1_DP','M2_USB1_DN')}

def test_distinct_module_terminal_objects_share_their_sheet_bus_scope():
    from wholeboard import terminals
    spec=example()
    spec=terminals.prepare(spec,{'action':'add','name':'DP','net':'USB1_DP','exclude_from_pcb':True})['spec'];spec=terminals.prepare(spec,{'action':'add','name':'DN','net':'USB1_DN','exclude_from_pcb':True})['spec']
    spec=pair(spec,('TP1.1','TP2.1'));groups=buses.compile(spec)['groups'];assert len(groups)==1 and groups[0]['nets']==['USB1_DP','USB1_DN']
    asset=modules.publish(spec,name='Module interface');host={'name':'terminal_bus_instances','board':{'width_mm':60,'height_mm':30,'layers':2},'components':[],'nets':[],'library':{'modules':{'USB':asset}}};out=modules.instantiate(host,'USB','M1');out=modules.instantiate(out,'USB','M2',offset=[30,0])
    assert {tuple(g['nets']) for g in buses.compile(out)['groups']}=={('M1_USB1_DP','M1_USB1_DN'),('M2_USB1_DP','M2_USB1_DN')}

def test_native_time_skew_uses_the_exported_layer_propagation_model(tmp_path):
    spec=pair(example(),max_length_mm=100,pn_skew_ps=5)
    # Put the1mm detour outside the pads: KiCad correctly excludes copper inside pads.
    spec['fixed_copper'][1]['tracks']=[{'id':f'22222222-2222-4222-8222-{i:012d}','a':a,'b':b,'w':.25,'layer':'F.Cu'} for i,(a,b) in enumerate([([5,7.54],[10,7.54]),([10,7.54],[10,8.04]),([10,8.04],[11,8.04]),([11,8.04],[11,7.54]),([11,7.54],[15,7.54])])]
    seen=[]
    for unit in (1,10):
        spec['board']['timing']['track_ps_per_mm']['F.Cu']=unit
        result=board.build(spec,tmp_path/str(unit));report=cli.drc(Path(result['pcb']),refill=False,save=False)
        seen.append(any('skew' in row['type'] for row in report['error_list']+report['warning_list']))
    assert seen==[False,True],'The same1mm mismatch must pass a1ps/mm model and fail a10ps/mm model at5ps'

def test_native_time_skew_includes_package_delays(tmp_path):
    spec=pair(example(),max_length_mm=100)
    spec=prepare(spec,{'action':'pins','pins':['J1.1'],'patch':{'pin_delay_ps':10}})['spec']
    spec=prepare(spec,{'action':'pins','pins':['J1.2'],'patch':{'pin_delay_ps':30}})['spec']
    out=board.build(spec,tmp_path);report=cli.drc(Path(out['pcb']),refill=False,save=False)
    assert any('skew' in row['type'] for row in report['error_list']+report['warning_list']),'Identical routes with20ps package mismatch must fail the10ps native rule'

def test_pair_to_pair_skew_compares_lane_mean_delays_in_the_same_bus(tmp_path):
    spec=pair(example(),group='LINK',pair='D0',max_length_mm=100,pair_skew_ps=20)
    spec=pair(spec,('J1.3','J1.4'),'LINK',pair='D1',max_length_mm=100,pair_skew_ps=20)
    spec=prepare(spec,{'action':'pins','pins':['J1.1','J1.2'],'patch':{'pin_delay_ps':30}})['spec']
    geo=geometry.read(Path(board.build(spec,tmp_path)['pcb']));matches=buses.analyze(spec,geo)['bus_matching']
    assert len(matches)==1 and matches[0]['skew_ps']==30 and matches[0]['status']=='fail'

def test_controlled_impedance_tolerance_is_checked_as_a_labelled_stackup_estimate(tmp_path):
    spec=pair(example(),max_length_mm=100,impedance_tolerance_pct=7.5);geo=geometry.read(Path(board.build(spec,tmp_path)['pcb']));row=buses.analyze(spec,geo)['pairs'][0]
    assert row['impedance']['target_ohms']==90 and row['impedance']['tolerance_pct']==7.5 and row['impedance']['status']=='fail'
    assert row['impedance']['estimate_ohms']>100 and row['status']=='fail'

def test_single_ended_bus_targets_generate_per_net_impedance_groups():
    spec=prepare(example(),{'action':'pins','pins':['J1.1','J1.2'],'patch':{'bus_group':'DATA','bus_type':'SPI','impedance_ohms':50,'impedance_tolerance_pct':10}})['spec']
    groups=buses.compile(spec)['groups'];assert {tuple(g['nets']) for g in groups if g['kind']=='single'}=={('USB1_DP',),('USB1_DN',)}
    assert len([g for g in groups if g['kind']=='bus'])==1

def test_manual_and_terminal_impedance_targets_cannot_silently_disagree():
    spec=pair(example());spec['impedance']=[{'kind':'diff','nets':['USB1_DP','USB1_DN'],'ohms':100}]
    result=buses.compile(spec);assert any(i['severity']=='error' and 'manual' in i['message'].lower() for i in result['issues'])

@pytest.mark.parametrize('with_pair',[False,True])
def test_pair_to_pair_limit_cannot_pass_without_two_complete_pairs(tmp_path,with_pair):
    spec=pair(example(),pair='DATA' if with_pair else None,impedance_ohms=None,pn_skew_ps=None,max_length_mm=100,pair_skew_ps=20)
    result=buses.compile(spec)
    assert any(i['severity']=='pending' and 'pair-to-pair' in i['message'].lower() for i in result['issues'])
    geo=geometry.read(Path(board.build(spec,tmp_path)['pcb']));analysis=buses.analyze(spec,geo)
    rows=analysis['pairs']+analysis['buses']
    assert rows and all(row['status']=='unknown' for row in rows),'A configured constraint needs evidence before it can pass'

def test_unpaired_bus_members_are_not_silently_omitted_from_a_paired_bus():
    spec=pair(example(),group='LINK',max_length_mm=100)
    spec=prepare(spec,{'action':'pins','pins':['J1.3'],'patch':{'bus_group':'LINK','max_length_mm':5}})['spec']
    result=buses.compile(spec)
    assert any(i['severity']=='pending' and 'J1.3' in i['message'] for i in result['issues']),'Unsupported mixed pair/single-ended constraints must remain visibly pending'


def test_ambiguous_arc_path_keeps_bus_lengths_unknown_with_configured_length_limits():
    from test_route_tuning import fixture
    spec,geo=fixture();spec['components'][0]['pin_properties']['1']['max_length_mm']=100
    geo['arcs']=[{'id':'arc-stub','net':'DP','a':[120,108],'m':[121,109],'b':[122,108],'w':.25,'layer':'F.Cu'}]
    row=buses.analyze(spec,geo)['pairs'][0]
    assert row['length_mm']['DP'] is None and row['delay_ps']['DP'] is None and row['timing_status']=='unknown'
    assert row['status']=='unknown' and any('branched' in reason or 'ambiguous' in reason for reason in row['unknown'])


def test_line_only_bus_stub_uses_the_same_unknown_topology_as_route_inspection():
    from test_route_tuning import fixture
    from wholeboard import route_tuning
    spec,geo=fixture();geo['tracks'].append({'id':'line-stub','net':'DP','a':[120,108],'b':[120,115],'w':.25,'layer':'F.Cu'})
    measured=route_tuning._route(spec,geo,'DP');row=buses.analyze(spec,geo)['pairs'][0]
    assert not measured['ready'] and row['length_mm']['DP'] is None and row['delay_ps']['DP'] is None
    assert row['timing_status']=='unknown'
