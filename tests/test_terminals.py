"""Terminals are real single-pin interfaces, with optional PCB test pads."""
from pathlib import Path
import pytest
from fastapi import HTTPException
from wholeboard import design,sexpr,schematic_view,modules
from wholeboard.kicad import board,cli,geometry,schematic
from wholeboard.jlc import quote
from wholeboard.workbench import validate_draft


def specimen(excluded=False):
    return {'name':'terminal_acceptance','board':{'width_mm':30,'height_mm':22,'layers':2,'ground_pour':None},
     'components':[{'ref':'R1','value':'10k','symbol':'Device:R','footprint':'Resistor_SMD:R_0603_1608Metric','placement':{'x_mm':6,'y_mm':10}},
                   {'ref':'R2','value':'10k','symbol':'Device:R','footprint':'Resistor_SMD:R_0603_1608Metric','sheet':'Power','placement':{'x_mm':16,'y_mm':10}},
                   {'ref':'TP1','value':'OUT','symbol':'Connector:TestPoint','footprint':'Project:TerminalPad','sheet':'Power','terminal':{'direction':'output','number':'1','side':'right','order':0,'exclude_from_pcb':excluded,'diameter_mm':1.8},'placement':{'x_mm':25,'y_mm':10}}],
     'nets':[{'name':'SIG','pins':['R1.1','R2.1','TP1.1']}],
     'editor':{'positions':{'R1':[250,200],'R2':[650,200],'TP1':[300,200]},'sheets':{'Power':{'position':[900,100],'size':[400,220]}}},
     'library':{'footprints':{'TerminalPad':{'name':'Terminal pad','mount':'smd','height_mm':.035,'courtyard':[-1.15,-1.15,1.15,1.15],'graphics':[],'pads':[{'name':'1','kind':'smd','shape':'circle','x':0,'y':0,'w':1.8,'h':1.8,'layer':'F.Cu','paste':False}]}}}}


def test_terminal_exports_a_typed_module_interface_and_a_real_unassembled_pcb_test_pad(tmp_path):
    spec=specimen();validate_draft(spec);native=schematic.build(spec,tmp_path/'sch');scene=schematic_view.scene(spec)
    module=next(node for node in scene['sheet_nodes'] if node['target']=='Power')
    port=next((p for p in module['ports'] if p['label']=='OUT'),None)
    assert port and port['net']=='SIG','Terminal does not expose its actual canonical connection'
    assert port['position'][0]==1300 and port['angle']==0
    tree=sexpr.parse(Path(native['sch']).read_text());pin=next(p for node in sexpr.find_all(tree,'sheet') for p in sexpr.find_all(node,'pin') if p[1]=='OUT')
    assert str(pin[2])=='output'
    if cli.find_kicad_cli():assert schematic.netlist_parity(spec,cli.schematic_nets(Path(native['sch'])))['ok']
    pcb=Path(board.build(spec,tmp_path/'pcb')['pcb']);geo=geometry.read(pcb)
    pad=next(p for p in geo['pads'] if p['ref']=='TP1');assert pad['w']==pad['h']==1.8
    footprint=next(node for node in sexpr.find_all(sexpr.parse(pcb.read_text()),'footprint') if any(p[1]=='Reference' and p[2]=='TP1' for p in sexpr.find_all(node,'property')))
    assert 'exclude_from_pos_files' in list(sexpr.find(footprint,'attr'))
    assert not any(str(layer).endswith('Paste') for node in sexpr.find_all(footprint,'pad') for layer in sexpr.find(node,'layers')[1:])
    assert not any('TP1' in row['refs'] for row in quote.bom_rows(spec))


def test_excluding_a_terminal_from_pcb_keeps_its_native_schematic_connection(tmp_path):
    spec=specimen(True);spec['components'][-1]['placement']={'x_mm':-200,'y_mm':500}
    assert design.validate(spec).ok,'A schematic-only terminal must not fail PCB placement validation'
    pcb=Path(board.build(spec,tmp_path/'pcb')['pcb']);assert {p['ref'] for p in geometry.read(pcb)['footprints']}=={'R1','R2'}
    sch=schematic.build(spec,tmp_path/'sch')
    if cli.find_kicad_cli():assert schematic.netlist_parity(spec,cli.schematic_nets(Path(sch['sch'])))['ok']


@pytest.mark.parametrize('patch',[{'direction':'voltage'},{'side':'diagonal'},{'exclude_from_pcb':'yes'},{'diameter_mm':0},{'number':''}])
def test_invalid_terminal_properties_cannot_be_saved(patch):
    spec=specimen();spec['components'][-1]['terminal'].update(patch)
    with pytest.raises(HTTPException) as error:validate_draft(spec)
    assert error.value.status_code==422


def test_selection_conversion_keeps_a_schematic_only_terminal_and_its_interface(tmp_path):
    spec=specimen(True);spec['components'][-1]['sheet']='';spec['components'][1]['sheet']=''
    geo=geometry.read(Path(board.build(spec,tmp_path/'pcb')['pcb']))
    result=modules.convert_selection(spec,['R1','TP1'],'PortBlock','M1',name='Port block',native_geometry=geo)
    asset=result['spec']['library']['modules']['PortBlock']
    assert asset['ports']['OUT']['net']=='SIG'
    assert {c['ref'] for c in asset['design']['components']}=={'R1','TP1'}
    assert {c['ref'] for c in geometry.read(Path(board.build(asset['design'],tmp_path/'module')['pcb']))['footprints']}=={'R1'}


def test_terminal_draft_operations_rename_and_rebind_one_pin_without_overwriting_other_design_data():
    from wholeboard import terminals
    spec=specimen();spec['components'].pop();spec['nets'][0]['pins'].remove('TP1.1');spec['fixed_copper']=[{'net':'SIG','tracks':[{'a':[2,5],'b':[20,5],'w':.25,'layer':'F.Cu'}]}]
    assert hasattr(terminals,'prepare'),'Terminal authoring operations are missing'
    created=terminals.prepare(spec,{'action':'add','sheet':'Power','name':'OUT','net':'SIG','exclude_from_pcb':True})
    out=created['spec'];ref=created['ref'];assert ref=='TP1' and out['nets'][0]['pins'][-1]=='TP1.1'
    assert len(spec['components'])==2 and out['fixed_copper']==spec['fixed_copper']
    out['editor']['connection_guides']=[{'id':'external','from':'R1.1','to':'sheet:Power.OUT'}]
    renamed=terminals.prepare(out,{'action':'update','ref':ref,'patch':{'name':'VOUT','number':'3','side':'bottom'}})['spec']
    assert renamed['editor']['connection_guides'][0]['to']=='sheet:Power.VOUT'
    assert renamed['fixed_copper']==spec['fixed_copper']
    isolated=terminals.prepare(renamed,{'action':'update','ref':ref,'patch':{'net':None}})['spec']
    assert isolated['nets'][0]['pins']==['R1.1','R2.1'] and isolated['fixed_copper']==spec['fixed_copper']
    assert any(net.get('placeholder_ref')=='TP1' for net in isolated['nets'])


def test_reselecting_an_isolated_terminals_current_net_is_idempotent():
    from wholeboard import terminals
    spec=specimen();spec['components'].pop();spec['nets'][0]['pins'].remove('TP1.1')
    result=terminals.prepare(spec,{'action':'add','name':'OUT'})
    net=next(net['name'] for net in result['spec']['nets'] if 'TP1.1' in net['pins'])
    again=terminals.prepare(result['spec'],{'action':'update','ref':'TP1','patch':{'net':net}})
    assert again['spec']==result['spec']


def test_new_terminal_pin_numbers_respect_existing_declared_interface_numbers():
    from wholeboard import terminals
    spec=specimen();spec['components'].pop();spec['nets'][0]['pins'].remove('TP1.1');spec['editor']['sheets']['Power']['ports']={'EXISTING':{'net':'SIG','number':'1'}}
    result=terminals.prepare(spec,{'action':'add','sheet':'Power','name':'NEXT','net':'SIG'})
    assert result['spec']['components'][-1]['terminal']['number']=='2'


def test_module_instances_remap_isolated_terminal_placeholder_references():
    from wholeboard import terminals
    empty={'name':'one_port','board':{'width_mm':30,'height_mm':22,'layers':2},'components':[],'nets':[]}
    source=terminals.prepare(empty,{'action':'add','name':'OUT'})['spec'];asset=modules.publish(source,name='Port')
    target=terminals.prepare(empty,{'action':'add','name':'OTHER'})['spec'];target['library']['modules']={'Port':asset}
    result=modules.instantiate(target,'Port','M1')
    placeholder=next(net for net in result['nets'] if net['name']=='M1_PORT_TP1')
    assert placeholder['placeholder_ref']=='TP2' and placeholder['pins']==['TP2.1']


def test_terminal_marker_cannot_hide_a_multi_pin_device_as_a_bare_test_pad():
    spec=specimen();spec['components'][-1]['symbol']='Device:R'
    with pytest.raises(HTTPException):validate_draft(spec)


def test_module_ground_terminal_does_not_implicitly_join_a_different_root_ground(tmp_path):
    spec=specimen(True);spec['components'][-1]['value']='GND'
    spec['nets']=[{'name':'SIG','pins':['R1.1','R2.1']},{'name':'GND','class':'power','pins':['R1.2']},{'name':'ISOLATED_GND','class':'power','pins':['R2.2','TP1.1']}]
    native=schematic.build(spec,tmp_path)
    if cli.find_kicad_cli():
        actual=cli.schematic_nets(Path(native['sch']));assert schematic.netlist_parity(spec,actual)['ok']
        assert next(group for group in actual.values() if 'R1.2' in group)=={'R1.2'}


def test_legacy_declared_port_direction_reaches_native_hierarchical_labels(tmp_path):
    spec=specimen();spec['components'].pop();spec['nets'][0]['pins'].remove('TP1.1');spec['editor']['sheets']['Power']['ports']={'OUT':{'net':'SIG','direction':'output'}}
    result=schematic.build(spec,tmp_path);child=sexpr.parse((tmp_path/'terminal_acceptance-Power.kicad_sch').read_text())
    labels=[node for node in sexpr.find_all(child,'hierarchical_label') if node[1]=='OUT']
    assert labels and all(str(sexpr.find(label,'shape')[1])=='output' for label in labels)


def test_terminal_pad_native_library_roundtrip_does_not_add_solder_paste(tmp_path):
    from wholeboard import project_library
    spec=specimen();project_library.export(spec,tmp_path)
    text=(tmp_path/'library/Project.pretty/TerminalPad.kicad_mod').read_text()
    imported=project_library.import_native('footprints',text)
    assert imported['TerminalPad']['pads'][0]['paste'] is False
    tree=project_library.footprint_node({'library':{'footprints':imported}},'Project:TerminalPad')
    assert all(not str(layer).endswith('Paste') for pad in sexpr.find_all(tree,'pad') for layer in sexpr.find(pad,'layers')[1:])


def test_terminal_hierarchy_does_not_add_dangling_or_duplicate_alias_findings(tmp_path):
    if not cli.find_kicad_cli():pytest.skip('KiCad is required for original ERC findings')
    spec=specimen(True);spec['components'][0]['sheet']='Power';native=schematic.build(spec,tmp_path);report=cli.erc(Path(native['sch']))
    findings=report['errors']+report['warnings']+report.get('ignored_list',[])
    assert not any(item['type']=='label_dangling' for item in findings),findings
    assert not any(item['type']=='multiple_net_names' for item in findings),findings
