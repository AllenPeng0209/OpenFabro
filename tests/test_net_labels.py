"""Net labels connect named project nets without inventing physical parts."""
import copy
from pathlib import Path
import pytest
from fastapi import HTTPException
from wholeboard import schematic_view,sexpr,workbench,modules
from wholeboard.kicad import schematic,cli,board,geometry
try:
    from wholeboard import net_labels
except ImportError:
    net_labels=None

def example():
    return {'name':'named_labels','board':{'width_mm':50,'height_mm':24,'layers':2,'ground_pour':None},
      'components':[{'ref':f'R{i}','value':'1k','symbol':'Device:R','footprint':'Resistor_SMD:R_0603_1608Metric','placement':{'x_mm':5+(i-1)*8,'y_mm':10}} for i in range(1,5)],
      'nets':[{'name':'SIG','class':'signal','pins':['R1.1','R2.1']},{'name':'AUX','class':'signal','pins':['R3.1']},{'name':'GND','class':'power','pins':['R1.2','R2.2','R3.2','R4.2']}],
      'editor':{'positions':{f'R{i}':[200+(i-1)*300,300] for i in range(1,5)}},
      'fixed_copper':[{'net':'SIG','tracks':[{'id':'11111111-1111-4111-8111-111111111111','a':[4.175,10],'b':[12.175,10],'w':.25,'layer':'F.Cu'}]},
                      {'net':'GND','tracks':[{'id':'22222222-2222-4222-8222-222222222222','a':[5.825,10],'b':[29.825,10],'w':.3,'layer':'B.Cu'}]}]}

def prepare(spec,args):
    assert net_labels is not None,'Net label authoring is missing'
    return net_labels.prepare(spec,args)

def test_named_label_binds_an_unconnected_pin_and_keeps_real_copper_and_parts(tmp_path):
    spec=example();before=copy.deepcopy(spec);result=prepare(spec,{'action':'add','anchor':'R4.1','net':'SIG','position':[1100,180]});out=result['spec']
    assert out['components']==before['components'] and out['fixed_copper']==before['fixed_copper'] and spec==before
    assert next(n for n in out['nets'] if n['name']=='SIG')['pins']==['R1.1','R2.1','R4.1']
    node=out['editor']['wire_nodes'][result['id']];assert node['net']=='SIG' and node['label']['kind']=='auto'
    sch=schematic.build(out,tmp_path);assert schematic.netlist_parity(out,cli.schematic_nets(Path(sch['sch'])))['ok']

def test_native_signal_and_power_labels_add_no_physical_parts_or_exported_power_pins(tmp_path):
    spec=prepare(example(),{'action':'add','anchor':'R1.1','net':'SIG','kind':'net','position':[200,160]})['spec']
    result=prepare(spec,{'action':'add','anchor':'R1.2','kind':'ground','position':[200,440]});spec=result['spec']
    out=schematic.build(spec,tmp_path/'sch');tree=sexpr.parse(Path(out['sch']).read_text());actual=cli.schematic_nets(Path(out['sch']))
    assert any(str(n[1])=='SIG' for n in sexpr.find_all(tree,'global_label'))
    assert any(str(sexpr.find(n,'lib_id')[1])=='power:GND' for n in sexpr.find_all(tree,'symbol'))
    assert not any(pin.startswith('#') for pins in actual.values() for pin in pins)
    assert schematic.netlist_parity(spec,actual)['ok']
    scene=schematic_view.scene(spec);assert {c['ref'] for c in scene['symbols']}=={'R1','R2','R3','R4'}
    geo=geometry.read(Path(board.build(spec,tmp_path/'pcb')['pcb']));assert len(geo['footprints'])==4 and len(geo['pads'])==8

def test_merging_established_nets_requires_a_review_and_clears_only_affected_copper():
    before=example();pending=prepare(before,{'action':'add','anchor':'R3.1','net':'SIG','position':[800,160]})
    assert pending['spec'] is None and pending['merge']['from']=='AUX' and pending['merge']['to']=='SIG'
    out=prepare(before,{'action':'add','anchor':'R3.1','net':'SIG','position':[800,160],'confirm_merge':True})['spec']
    assert {n['name'] for n in out['nets']}=={'SIG','GND'}
    assert next(n for n in out['nets'] if n['name']=='SIG')['pins']==['R1.1','R2.1','R3.1']
    assert out['fixed_copper']==[before['fixed_copper'][1]]

def test_renaming_a_label_renames_the_project_net_and_all_references_without_discarding_copper():
    result=prepare(example(),{'action':'add','anchor':'R1.1','net':'SIG','position':[200,160]});spec=result['spec'];spec['simulation']={'probes':['SIG']};spec['impedance']=[{'nets':['SIG','AUX']}]
    out=prepare(spec,{'action':'update','id':result['id'],'patch':{'net':'DATA','rotation':90}})['spec']
    assert 'SIG' not in {n['name'] for n in out['nets']} and out['simulation']['probes']==['DATA']
    assert out['fixed_copper'][0]['net']=='DATA' and out['fixed_copper'][0]['tracks']==spec['fixed_copper'][0]['tracks']
    assert all(n['net']!='SIG' for n in out['editor']['wire_nodes'].values())
    assert out['editor']['wire_nodes'][result['id']]['label']['rotation']==90
    assert out['impedance'][0]['nets']==['DATA','AUX']

def test_removing_a_label_keeps_its_connected_wire_endpoint_and_named_net():
    result=prepare(example(),{'action':'add','anchor':'R1.1','net':'SIG','position':[200,160]});before=result['spec']
    out=prepare(before,{'action':'delete','id':result['id']})['spec']
    assert 'label' not in out['editor']['wire_nodes'][result['id']]
    assert out['editor']['connection_guides']==before['editor']['connection_guides'] and out['nets']==before['nets'] and out['fixed_copper']==before['fixed_copper']

def test_published_instances_keep_private_label_identity_and_names(tmp_path):
    spec=prepare(example(),{'action':'add','anchor':'R1.1','net':'SIG','position':[200,160]})['spec'];spec=prepare(spec,{'action':'add','anchor':'R1.2','kind':'ground','position':[200,440]})['spec'];asset=modules.publish(spec,name='Labeled circuit')
    host={'name':'label_instances','board':{'width_mm':110,'height_mm':30,'layers':2,'ground_pour':None},'components':[],'nets':[],'library':{'modules':{'Labeled':asset}}}
    out=modules.instantiate(host,'Labeled','M1');out=modules.instantiate(out,'Labeled','M2',offset=[50,0])
    labels=[n for n in out['editor']['wire_nodes'].values() if n.get('label')];assert {n['net'] for n in labels}=={'M1_SIG','M2_SIG','M1_GND','M2_GND'} and {n['sheet'] for n in labels}=={'M1','M2'}
    ground=next(key for key,n in out['editor']['wire_nodes'].items() if n.get('label',{}).get('kind')=='ground' and n['sheet']=='M1')
    rotated=prepare(out,{'action':'update','id':ground,'patch':{'rotation':90}})['spec'];assert rotated['nets']==out['nets'],'Rotating a private ground symbol must not rename or merge its module net'
    native=schematic.build(out,tmp_path);assert schematic.netlist_parity(out,cli.schematic_nets(Path(native['sch'])))['ok']

def test_module_labels_use_the_mapped_project_net_even_with_different_interface_names(tmp_path):
    spec=prepare(example(),{'action':'add','anchor':'R1.1','net':'SIG','position':[200,160]})['spec'];spec=prepare(spec,{'action':'add','anchor':'R1.2','kind':'ground','position':[200,440]})['spec']
    asset=modules.publish(spec,name='Labeled circuit',ports={'OUT':'SIG','PGND':'GND'})
    host={'name':'label_boundaries','board':{'width_mm':110,'height_mm':30,'layers':2,'ground_pour':None},'components':[],'nets':[{'name':'BUS','pins':[]},{'name':'RETURN','class':'power','pins':[]}],'library':{'modules':{'Labeled':asset}}}
    out=modules.instantiate(host,'Labeled','M1',connections={'OUT':'BUS','PGND':'RETURN'});out=modules.instantiate(out,'Labeled','M2',offset=[50,0],connections={'OUT':'BUS','PGND':'RETURN'})
    native=schematic.build(out,tmp_path);assert schematic.netlist_parity(out,cli.schematic_nets(Path(native['sch'])))['ok']

def test_a_named_connection_clears_the_selected_pins_explicit_no_connect_mark():
    spec=example();spec['components'][-1]['no_connect']=['1'];out=prepare(spec,{'action':'add','anchor':'R4.1','net':'SIG','position':[1100,180]})['spec']
    assert out['components'][-1]['no_connect']==[] and spec['components'][-1]['no_connect']==['1']

def test_naming_a_temporary_free_wire_binds_the_project_net_without_discarding_its_copper(tmp_path):
    spec=example();spec['nets'].append({'name':'Net_1','class':'signal','pins':[],'wire_only':True});spec['editor']['wire_nodes']={'a':{'position':[200,140],'sheet':'','net':'Net_1'},'b':{'position':[400,140],'sheet':'','net':'Net_1'}};spec['editor']['connection_guides']=[{'id':'free','from':'node:a','to':'node:b'}]
    result=prepare(spec,{'action':'add','id':'a','net':'SIG'});assert result['spec'] is not None,'An unnamed free wire is a binding, not a merge of two established nets'
    out=result['spec'];assert out['fixed_copper']==spec['fixed_copper'] and 'Net_1' not in {n['name'] for n in out['nets']}
    native=schematic.build(out,tmp_path);assert schematic.netlist_parity(out,cli.schematic_nets(Path(native['sch'])))['ok']

@pytest.mark.parametrize('both',[True,False])
def test_cutting_a_wire_keeps_explicit_named_label_links_and_retains_the_labeled_net(tmp_path,both):
    from wholeboard import wire_cuts
    spec=example();spec['editor']['connection_guides']=[{'id':'trunk','from':'R1.1','to':'R2.1'}]
    if both:spec=prepare(spec,{'action':'add','anchor':'R1.1','net':'SIG','position':[200,160]})['spec']
    spec=prepare(spec,{'action':'add','anchor':'R2.1','net':'SIG','position':[500,160]})['spec'];scene=schematic_view.scene(spec)
    route=next(r for r in scene['routes'] if r['id']=='trunk');a,b=max(zip(route['points'],route['points'][1:]),key=lambda p:sum(abs(p[0][i]-p[1][i]) for i in range(2)))
    result=wire_cuts.prepare(spec,{'wire':'trunk','point':[(a[i]+b[i])/2 for i in range(2)]},scene_data=scene);out=result['spec']
    signal=next(n for n in out['nets'] if n['name']=='SIG')['pins'];assert 'R2.1' in signal
    assert ('R1.1' in signal)==both
    assert all(n['net']=='SIG' for n in out['editor']['wire_nodes'].values() if n.get('label'))
    assert result['summary']['electrically_split'] is (not both)
    if both:assert out['fixed_copper']==spec['fixed_copper']
    native=schematic.build(out,tmp_path);assert schematic.netlist_parity(out,cli.schematic_nets(Path(native['sch'])))['ok']

def test_custom_power_label_uses_the_project_net_instead_of_the_library_default(tmp_path):
    spec=prepare(example(),{'action':'add','anchor':'R1.1','net':'+3V3','kind':'power','position':[200,160]})['spec']
    native=schematic.build(spec,tmp_path);actual=cli.schematic_nets(Path(native['sch']))
    assert actual['+3V3']=={'R1.1','R2.1'} and 'VCC' not in actual

def test_label_on_a_native_wire_preserves_the_drawn_geometry_and_dependent_junctions(tmp_path):
    from shapely.geometry import LineString
    from shapely.ops import unary_union
    spec=example();spec['editor']['connection_guides']=[{'id':'trunk','from':'R1.1','to':'R2.1'},
      {'id':'branch','from':'R1.1','to':'R4.1','from_join':{'wire':'trunk','offset':.75}}]
    spec['nets'][0]['pins'].append('R4.1');before=schematic_view.scene(spec);route=next(r for r in before['routes'] if r['id']=='trunk')
    result=prepare(spec,{'action':'add','wire':'trunk','sheet':'','position':[(route['points'][0][i]+route['points'][-1][i])/2 for i in range(2)]});out=result['spec']
    assert out['nets']==spec['nets'] and out['editor']['wire_nodes'][result['id']]['net']=='SIG'
    assert len(out['editor']['connection_guides'])==3
    after=schematic_view.scene(out)
    shape=lambda scene:unary_union([LineString(w['points']) for w in scene['wires'] if w['net']=='SIG'])
    assert shape(before).symmetric_difference(shape(after)).length<.0001
    native=schematic.build(out,tmp_path);assert schematic.netlist_parity(out,cli.schematic_nets(Path(native['sch'])))['ok']

@pytest.mark.parametrize('label',[{'kind':'unknown'},{'kind':'auto','rotation':45},{'kind':'net','rotation':True},'SIG'])
def test_invalid_label_metadata_cannot_enter_a_saved_draft(label):
    spec=example();spec['editor']['wire_nodes']={'bad':{'net':'SIG','sheet':'','position':[100,100],'label':label}}
    with pytest.raises(HTTPException,match='[Ll]abel|rotation'):workbench.validate_draft(spec)
