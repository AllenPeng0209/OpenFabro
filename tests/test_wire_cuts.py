"""Electrical cuts change canonical pin groups and preserve the rest of the project."""
import copy
from pathlib import Path
import pytest
from wholeboard import schematic_view,sexpr
from wholeboard.kicad import cli,schematic
try:
    from wholeboard import wire_cuts
except ImportError:
    wire_cuts=None

def example():
    spec={'name':'electrical_cut','board':{'width_mm':40,'height_mm':24,'layers':2,'ground_pour':None},
      'components':[{'ref':f'R{i}','value':'1k','symbol':'Device:R','footprint':'Resistor_SMD:R_0603_1608Metric','placement':{'x_mm':5+(i-1)*8,'y_mm':10}} for i in (1,2,3,4)],
      'nets':[{'name':'SIG','class':'signal','pins':['R1.1','R2.1','R3.1','R4.1']},{'name':'GND','class':'power','pins':['R1.2','R2.2','R3.2','R4.2']}],
      'editor':{'positions':{'R1':[200,200],'R2':[600,200],'R3':[600,500],'R4':[900,500]},'connection_guides':[{'id':'trunk','from':'R1.1','to':'R2.1'},{'id':'branch','from':'R3.1','to':'R1.1','to_join':{'wire':'trunk','offset':.75}}]},
      'fixed_copper':[{'net':'SIG','tracks':[{'a':[2,4],'b':[20,4],'w':.25,'layer':'F.Cu'}]},{'net':'GND','tracks':[{'a':[2,15],'b':[20,15],'w':.3,'layer':'B.Cu'}]}],
      'library':{'symbols':{},'footprints':{},'parts':{}}}
    scene={'mm_per_unit':.127,'origin_mm':20.32,'anchors':[{'anchor':f'R{i}.1','sheet':'','position':p} for i,p in [(1,[100,100]),(2,[600,100]),(3,[500,400]),(4,[900,400])]],
      'routes':[{'id':'trunk','index':0,'sheet':'','from':'R1.1','to':'R2.1','net':'SIG','status':'routed','points':[[100,100],[600,100]]},{'id':'branch','index':1,'sheet':'','from':'R3.1','to':'R1.1','net':'SIG','status':'routed','points':[[500,400],[500,100]],'joins':{'to':{'wire':'trunk','offset':.8,'point':[500,100]}}}],
      'wires':[{'sheet':'','net':'SIG','points':[[100,100],[600,100]]},{'sheet':'','net':'SIG','points':[[500,400],[500,100]]}], 'sheet_nodes':[]}
    return spec,scene

def prepare(spec,scene,**options):
    assert wire_cuts is not None,'Electrical schematic wire cuts are missing'
    return wire_cuts.prepare(spec,{'wire':'trunk','sheet':'','point':[350,100],**options},scene_data=scene)

def test_cut_repartitions_real_pins_nodes_and_copper_without_touching_other_design_data():
    spec,scene=example();before=copy.deepcopy(spec);result=prepare(spec,scene);out=result['spec'];groups={n['name']:n['pins'] for n in out['nets']}
    assert groups['SIG']==['R1.1','R4.1'];assert set(groups['SIG_CUT'])=={'R2.1','R3.1'}
    assert out['components']==spec['components'] and out['library']==spec['library']
    assert out['fixed_copper']==[spec['fixed_copper'][1]]
    assert result['summary']['unrouted_pins']==['R4.1']
    assert result['summary']['changed_pins']==['R2.1','R3.1']
    assert all(not g.get('from_join') and not g.get('to_join') for g in out['editor']['connection_guides'])
    assert all(g.get('fixed_points') for g in out['editor']['connection_guides'])
    assert spec==before

def test_alternative_drawn_path_keeps_the_net_connected_and_preserves_copper():
    spec,scene=example();spec['editor']['connection_guides'].append({'id':'bypass','from':'R1.1','to':'R2.1'})
    path=[[100,100],[100,50],[600,50],[600,100]];scene['routes'].append({'id':'bypass','index':2,'sheet':'','from':'R1.1','to':'R2.1','net':'SIG','status':'routed','points':path});scene['wires']+=[{'sheet':'','net':'SIG','points':path}]
    result=prepare(spec,scene);assert result['spec']['nets']==spec['nets'];assert result['spec']['fixed_copper']==spec['fixed_copper'];assert result['summary']['changed_pins']==[]

def test_cut_through_a_branch_retains_the_branch_as_its_own_electrical_group():
    spec,scene=example();result=prepare(spec,scene,point=[500,100]);out=result['spec']
    groups=[set(n['pins']) for n in out['nets'] if n['name']!='GND'];assert {'R3.1'} in groups and {'R2.1'} in groups
    assert sum(len(n) for n in groups)==4

def test_removing_an_entire_native_segment_keeps_isolated_real_pins_as_separate_nets():
    spec,scene=example();result=prepare(spec,scene,mode='segment');groups=[set(n['pins']) for n in result['spec']['nets'] if n['name']!='GND']
    assert {'R2.1'} in groups and {'R3.1'} in groups and {'R1.1','R4.1'} in groups

@pytest.mark.parametrize('options',[{'wire':'missing'},{'point':[float('nan'),0]},{'gap_units':0},{'point':[10000,10000]}])
def test_bad_or_stale_cut_requests_cannot_produce_a_draft(options):
    spec,scene=example()
    with pytest.raises(ValueError):prepare(spec,scene,**options)

def test_parent_page_cut_moves_the_whole_child_port_domain_and_keeps_template_assets_frozen():
    spec,scene=example();spec['components'][2]['sheet']='M';spec['editor']['sheets']={'M':{'ports':{'OUT':{'net':'SIG'}}}}
    spec['editor']['connection_guides'][1]={'id':'branch','from':'R2.1','to':'sheet:M.OUT'}
    scene['anchors'][2]={'anchor':'sheet:M.OUT','sheet':'','position':[600,200]};scene['routes'][1].update(**{'from':'R2.1','to':'sheet:M.OUT','points':[[600,100],[600,200]],'joins':{}});scene['wires'][1]['points']=[[600,100],[600,200]]
    scene['sheet_nodes']=[{'target':'M','sheet':'','ports':[{'label':'OUT','net':'SIG','position':[600,200]}]}]
    result=prepare(spec,scene);out=result['spec'];assert 'R3.1' in next(n for n in out['nets'] if n['name']=='SIG_CUT')['pins'];assert out['editor']['sheets']['M']['ports']['OUT']['net']=='SIG_CUT';assert out['library']==spec['library']

def test_legacy_upward_port_requires_a_concrete_binding_instead_of_guessing_the_external_side():
    spec,scene=example()
    for c in spec['components'][:3]:c['sheet']='M'
    spec['editor']['sheets']={'M':{'ports':{'OUT':{'net':'SIG'}}}}
    for collection in ('anchors','routes','wires'):
        for value in scene[collection]:value['sheet']='M'
    result=prepare(spec,scene,sheet='M');assert result['spec'] is None and result['required_bindings'][0]['id']=='M.OUT'
    complete=prepare(spec,scene,sheet='M',port_bindings={'M.OUT':result['groups'][-1]['id']});assert complete['spec'] is not None

def test_native_cut_changes_kicad_pin_groups_and_does_not_reroute_across_the_gap(tmp_path):
    spec,_=example();spec['nets'][0]['pins'].remove('R4.1');spec['nets'][1]['pins'].remove('R4.2');spec['components'].pop();scene=schematic_view.scene(spec)
    route=next(r for r in scene['routes'] if r['id']=='trunk');a,b=max(zip(route['points'],route['points'][1:]),key=lambda pair:sum(abs(pair[0][i]-pair[1][i]) for i in range(2)))
    point=[(a[i]+b[i])/2 for i in range(2)];result=prepare(spec,scene,point=point);out=result['spec'];native=schematic.build(out,tmp_path)
    assert schematic.netlist_parity(out,cli.schematic_nets(Path(native['sch'])))['ok']
    assert all(r['status']=='routed' for page in native['pages'] for r in page['wiring']['routes'])
    assert len({n['name'] for n in out['nets']})==3

def test_exact_native_spans_do_not_add_a_pin_escape_backtrack(tmp_path):
    spec,_=example();spec['editor']['wire_nodes']={'end':{'net':'SIG','sheet':'','position':[200,165]}}
    spec['editor']['connection_guides']=[{'id':'short','from':'R1.1','to':'node:end','fixed_points':[[200,170],[200,165]]}]
    native=schematic.build(spec,tmp_path);route=native['pages'][0]['wiring']['routes'][0]
    assert route['status']=='routed' and route['points']==[(45.72,41.91),(45.72,41.275)]

@pytest.mark.parametrize('points',[[[True,0],[1,1]],[[0,0]],[[0,0],[float('inf'),1]]])
def test_invalid_exact_wire_spans_cannot_be_saved(points):
    from wholeboard.workbench import validate_draft
    from fastapi import HTTPException
    spec,_=example();spec['editor']['connection_guides'][0]['fixed_points']=points
    with pytest.raises(HTTPException):validate_draft(spec)

def test_exact_native_span_cannot_short_a_foreign_pin(tmp_path):
    spec,_=example();spec['editor']['connection_guides']=[{'id':'unsafe','from':'R1.1','to':'R2.1','fixed_points':[[200,170],[200,230],[600,230],[600,170]]}]
    native=schematic.build(spec,tmp_path);assert native['pages'][0]['wiring']['routes'][0]['status']=='unroutable'
    assert schematic.netlist_parity(spec,cli.schematic_nets(Path(native['sch'])))['ok']

def test_hierarchical_port_names_and_native_pin_groups_survive_a_parent_cut(tmp_path):
    spec,_=example();spec['components'][2]['sheet']='M';spec['editor']['sheets']={'M':{'position':[1100,100],'size':[300,200],'ports':{'OUT':{'net':'SIG'}}}}
    spec['editor']['connection_guides'][1]={'id':'branch','from':'R2.1','to':'sheet:M.OUT'}
    scene=schematic_view.scene(spec);result=prepare(spec,scene,point=[400,160]);out=result['spec']
    native=schematic.build(out,tmp_path);assert schematic.netlist_parity(out,cli.schematic_nets(Path(native['sch'])))['ok']
    assert out['editor']['sheets']['M']['ports']['OUT']['net']=='SIG_CUT'
    assert all(r['status']=='routed' for page in native['pages'] for r in page['wiring']['routes'])

def test_native_child_cut_resolves_legacy_upward_port_to_the_chosen_group(tmp_path):
    spec,_=example()
    for c in spec['components'][:3]:c['sheet']='M'
    spec['editor']['sheets']={'M':{'position':[1100,100],'size':[300,200],'ports':{'OUT':{'net':'SIG'}}}}
    scene=schematic_view.scene(spec);result=prepare(spec,scene,sheet='M',point=[400,160]);assert result['spec'] is None
    selected=next(g['id'] for g in result['groups'] if 'R2.1' in g['pins'])
    out=prepare(spec,scene,sheet='M',point=[400,160],port_bindings={'M.OUT':selected})['spec'];native=schematic.build(out,tmp_path)
    assert schematic.netlist_parity(out,cli.schematic_nets(Path(native['sch'])))['ok']
    assert next(n for n in out['nets'] if n['name']=='SIG')['pins']==['R2.1','R3.1','R4.1']

def test_an_odd_gap_stays_on_the_native_connection_grid():
    spec,scene=example();result=prepare(spec,scene,gap_units=10)
    assert all(abs(v/10-round(v/10))<1e-6 for p in result['summary']['cut'] for v in p)

def test_cut_clears_only_affected_pours_and_marks_a_locally_split_module():
    from wholeboard.kicad import board
    spec,scene=example();spec['board'].update(ground_pour='SIG',planes={'F.Cu':'SIG','B.Cu':'GND'})
    spec['fixed_zones']=[{'net':name,'origin':[100,100],'source':sexpr.dumps(board.zone(name,layer,40,24,.5,.25))} for name,layer in [('SIG','F.Cu'),('GND','B.Cu')]]
    spec['editor']['module_instances']={'M':{'refs':['R1','R2'],'nets':{'internal':'SIG'}}}
    out=prepare(spec,scene)['spec'];assert out['board']['ground_pour'] is None and out['board']['planes']=={'B.Cu':'GND'};assert out['fixed_zones']==[spec['fixed_zones'][1]]
    assert out['editor']['module_instances']['M']['modified'];assert out['editor']['module_instances']['M']['net_splits']['internal']==['SIG','SIG_CUT']

def test_removing_the_last_standalone_span_prunes_its_auto_net_and_nodes():
    spec,scene=example();spec['components']=[];spec['nets']=[{'name':'SIG','pins':[],'wire_only':True}];spec['fixed_copper']=[]
    spec['editor']['wire_nodes']={key:{'position':p,'sheet':'','net':'SIG'} for key,p in [('a',[100,100]),('b',[600,100])]};spec['editor']['connection_guides']=[{'id':'trunk','from':'node:a','to':'node:b'}]
    scene['routes']=scene['routes'][:1];scene['routes'][0].update(**{'from':'node:a','to':'node:b'});scene['wires']=scene['wires'][:1];scene['anchors']=[{'anchor':'node:'+key,'sheet':'','position':node['position']} for key,node in spec['editor']['wire_nodes'].items()]
    out=prepare(spec,scene,mode='segment')['spec'];assert out['nets']==[] and out['editor']['wire_nodes']=={} and out['editor']['connection_guides']==[]

def test_shared_external_interfaces_can_keep_a_cut_network_connected():
    spec,scene=example()
    for c in spec['components'][:3]:c['sheet']='M'
    spec['editor']['sheets']={'M':{'ports':{'A':{'net':'SIG'},'B':{'net':'SIG'}}}}
    for collection in ('anchors','routes','wires'):
        for value in scene[collection]:value['sheet']='M'
    pending=prepare(spec,scene,sheet='M');assert len(pending['required_bindings'])==2
    result=prepare(spec,scene,sheet='M',port_bindings={'M.A':'g0','M.B':'g1'})
    assert not result['summary']['electrically_split'] and result['spec']['nets']==spec['nets']
    assert len(result['binding_groups'])==2 and len(result['groups'])==1

def test_repeated_occurrences_of_one_physical_pin_remain_electrically_linked():
    spec,scene=example();spec['editor']['connection_guides'].append({'id':'common_pin_path','from':'R1#2.1','to':'R2.1'})
    scene['anchors'].append({'anchor':'R1#2.1','sheet':'','position':[100,50]});path=[[100,50],[600,50],[600,100]]
    scene['routes'].append({'id':'common_pin_path','index':2,'sheet':'','from':'R1#2.1','to':'R2.1','net':'SIG','status':'routed','points':path});scene['wires'].append({'sheet':'','net':'SIG','points':path})
    result=prepare(spec,scene);assert result['spec']['nets']==spec['nets'] and result['summary']['changed_pins']==[]
