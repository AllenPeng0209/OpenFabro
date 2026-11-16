"""Authoring hierarchy must preserve actual KiCad electrical connectivity."""
from pathlib import Path
import json

from wholeboard import schematic_view,sexpr
from wholeboard.kicad import schematic,cli


def example():return json.loads((Path(__file__).parents[1]/'wholeboard/web/workbench-example.json').read_text())


def test_declared_empty_and_nested_sheets_are_exported_with_their_own_bounds(tmp_path):
    spec=example();spec['editor']['sheets']={'Power':{'title':'Power stage','parent':'','position':[900,100],'size':[400,240]},'Bias':{'title':'Bias','parent':'Power','position':[700,180],'size':[300,200]},'Empty':{'title':'Empty','parent':'','position':[900,500],'size':[300,180]}}
    for component in spec['components']:
        if component['ref']=='R1':component['sheet']='Bias'
        elif component['ref']=='R2':component['sheet']='Power'
    out=schematic.build(spec,tmp_path);assert {page['name'] for page in out['pages']}=={'','Power','Bias','Empty'}
    root=sexpr.parse(Path(out['sch']).read_text());power=sexpr.parse((tmp_path/'usb_led_3v3-Power.kicad_sch').read_text())
    assert len(list(sexpr.find_all(root,'sheet')))==2
    assert len(list(sexpr.find_all(power,'sheet')))==1
    scene=schematic_view.scene(spec);node=next(sheet for sheet in scene['sheet_nodes'] if sheet['target']=='Power')
    assert node['name']=='Power stage';assert node['position']==[900,100];assert node['size']==[400,240]
    nested=next(sheet for sheet in scene['sheet_nodes'] if sheet['target']=='Bias');assert nested['sheet']=='Power'
    if cli.find_kicad_cli():
        proof=schematic.netlist_parity(spec,cli.schematic_nets(Path(out['sch'])));assert proof['ok'],proof


def test_sheet_membership_can_override_a_legacy_block_and_return_to_main():
    spec=example();spec['components'][0].update(block='Legacy',sheet='')
    root=schematic.sheets(spec)[0];assert 'J1' in root['refs']


def test_stable_sheet_port_anchor_routes_to_its_aliased_native_terminal(tmp_path):
    spec=example();spec['editor']['sheets']={'Power':{'position':[850,140],'ports':{'SENSE':{'net':'CC1'}}}}
    spec['components'][1]['sheet']='Power' # R1 is inside; J1 remains on Main.
    spec['editor']['connection_guides']=[{'id':'port-wire','from':'J1.A5','to':'sheet:Power.SENSE'}]
    out=schematic.build(spec,tmp_path);root=out['pages'][0]
    assert root['wiring']['routes'][0]['status']=='routed',root['wiring']['routes']
    scene=schematic_view.scene(spec);port=next(p for s in scene['sheet_nodes'] if s['target']=='Power' for p in s['ports'] if p['label']=='SENSE')
    assert port['net']=='CC1' and port['pin']=='R1.1'
    if cli.find_kicad_cli():assert schematic.netlist_parity(spec,cli.schematic_nets(Path(out['sch'])))['ok']


def test_declared_ancestor_terminal_reaches_an_isolated_nested_subcircuit(tmp_path):
    spec={'name':'nested_ports','board':{'width_mm':30,'height_mm':20,'layers':2},'components':[{'ref':ref,'value':'10k','symbol':'Device:R','footprint':'Resistor_SMD:R_0603_1608Metric','sheet':'Inner'} for ref in ('R1','R2')],'nets':[{'name':'SIG','pins':['R1.1','R2.1']}],'editor':{'sheets':{'Outer':{'ports':{'OUT':{'net':'SIG'}}},'Inner':{'parent':'Outer'}}}}
    scene=schematic_view.scene(spec);inner=next(node for node in scene['sheet_nodes'] if node['target']=='Inner')
    assert {p['net'] for p in inner['ports']}=={'SIG'},'The ancestor terminal is electrically dangling'
    outer=next(node for node in scene['sheet_nodes'] if node['target']=='Outer')
    assert [p['label'] for p in outer['ports']]==['OUT'],'Declared aliases should not produce duplicate automatic terminals'
    out=schematic.build(spec,tmp_path)
    if cli.find_kicad_cli():assert cli.schematic_nets(Path(out['sch']))['/SIG']=={'R1.1','R2.1'}


def test_nested_footprints_link_to_the_complete_sheet_name_path():
    spec=example();spec['components'][1]['sheet']='Inner';spec['editor']['sheets']={'Outer':{'title':'Power stage'},'Inner':{'parent':'Outer','title':'Bias'}}
    path,name,file=schematic.board_links(spec)['R1']
    assert name=='/Power stage/Bias/'
    assert path.count('/')==3 and file.endswith('-Inner.kicad_sch')
