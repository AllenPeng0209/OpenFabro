import copy
from pathlib import Path
import pytest
from fastapi import HTTPException
from wholeboard import schematic_view,sexpr,workbench
from wholeboard.kicad import cli,libs,schematic

def example():
    return {'name':'free_wire_native','board':{'width_mm':30,'height_mm':22,'layers':2},
        'components':[{'ref':f'R{i}','value':'1k','symbol':'Device:R','footprint':'Resistor_SMD:R_0603_1608Metric','placement':{'x_mm':i*10,'y_mm':10}} for i in (1,2)],
        'nets':[{'name':'SIG','pins':['R1.1','R2.1']},{'name':'GND','pins':['R1.2','R2.2']}],
        'editor':{'positions':{'R1':[200,200],'R2':[600,200]},'wire_nodes':{'tip':{'position':[350,100],'sheet':'','net':'SIG'}},
            'connection_guides':[{'id':'tail','from':'R1.1','to':'node:tip'}]}}

@pytest.mark.skipif(libs.locate('symbols') is None,reason='KiCad libraries required')
def test_free_wire_end_is_native_geometry_with_no_extra_part_and_real_erc_dangling_warning(tmp_path):
    spec=example();out=schematic.build(spec,tmp_path);sch=Path(out['sch']);tree=sexpr.parse(sch.read_text())
    route=out['pages'][0]['wiring']['routes'];assert len(route)==1,'Free-end wires were silently omitted'
    assert route[0]['status']=='routed';assert route[0]['points'][-1]==pytest.approx([64.77,33.02])
    assert len(list(sexpr.find_all(tree,'symbol')))==2
    assert schematic.netlist_parity(spec,cli.schematic_nets(sch))['ok']
    checked=cli.erc(sch);assert any(row['type']=='unconnected_wire_endpoint' for row in checked['warnings'])
    scene=schematic_view.scene(spec);assert scene['wire_nodes'][0]['id']=='tip'

@pytest.mark.parametrize('change',[
    lambda s:s['editor']['wire_nodes']['tip'].update(position=[True,100]),
    lambda s:s['editor']['wire_nodes']['tip'].update(net='missing'),
    lambda s:s['editor']['wire_nodes']['tip'].update(sheet='missing'),
    lambda s:s['editor']['connection_guides'][0].update(to='node:missing'),
    lambda s:s['editor'].update(wire_nodes=[]),
])
def test_drafts_reject_invalid_free_node_metadata(change):
    spec=example();change(spec)
    with pytest.raises(HTTPException,match='wire|Wire|node|Node|sheet|net'):
        workbench.validate_draft(spec)

@pytest.mark.skipif(libs.locate('symbols') is None,reason='KiCad libraries required')
def test_standalone_wire_can_exist_without_a_fake_component_or_pin(tmp_path):
    spec=example();spec['components']=[];spec['nets']=[{'name':'Net_1','pins':[],'wire_only':True}]
    spec['editor']['wire_nodes']={'a':{'position':[100,100],'sheet':'','net':'Net_1'},'b':{'position':[300,200],'sheet':'','net':'Net_1'}}
    spec['editor']['connection_guides']=[{'id':'free','from':'node:a','to':'node:b','waypoints':[[300,100]]}]
    out=schematic.build(spec,tmp_path);tree=sexpr.parse(Path(out['sch']).read_text())
    assert not list(sexpr.find_all(tree,'symbol'));assert list(sexpr.find_all(tree,'wire'))
    assert out['pages'][0]['extent'] is not None
    assert any(str(label[1])=='Net_1' for kind in ('label','global_label') for label in sexpr.find_all(tree,kind)), 'Floating wire islands lose their canonical net name in the native file'

def test_module_publish_and_instantiation_keep_private_wire_nodes_and_native_connectivity(tmp_path):
    from wholeboard import modules,wire_nodes
    source=example();asset=modules.publish(source,name='Free tail')
    target={'name':'tail_instances','board':{'width_mm':70,'height_mm':30,'layers':2},'components':[],'nets':[],'library':{'modules':{'Tail':asset}}}
    out=modules.instantiate(target,'Tail','M1',offset=[0,0]);out=modules.instantiate(out,'Tail','M2',offset=[30,0])
    nodes=out['editor'].get('wire_nodes',{});assert len(nodes)==2,'Publishing omitted the free wire endpoints'
    assert {n['net'] for n in nodes.values()}=={'M1_SIG','M2_SIG'}
    assert {n['sheet'] for n in nodes.values()}=={'M1','M2'};wire_nodes.validate(out)
    sch=schematic.build(out,tmp_path);assert schematic.netlist_parity(out,cli.schematic_nets(Path(sch['sch'])))['ok']

def test_selection_conversion_moves_attached_nodes_into_the_new_page(tmp_path):
    from wholeboard import modules,wire_nodes
    from wholeboard.kicad import board,geometry
    source=example();geo=geometry.read(Path(board.build(source,tmp_path/'pcb')['pcb']))
    out=modules.convert_selection(source,['R1'],'Tail','M1',name='Tail',native_geometry=geo)['spec']
    assert out['editor']['wire_nodes']['tip']['sheet']=='M1'
    assert out['library']['modules']['Tail']['design']['editor']['wire_nodes']['tip']['sheet']==''
    wire_nodes.validate(out);sch=schematic.build(out,tmp_path/'sch');assert schematic.netlist_parity(out,cli.schematic_nets(Path(sch['sch'])))['ok']
