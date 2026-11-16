"""Reusable modules retain real routed geometry without colliding instance identities."""
import copy
import json
from pathlib import Path
import pytest
from wholeboard import project_library,sexpr
from wholeboard.kicad import board,cli,geometry,schematic


def source():
    spec=json.loads((Path(__file__).parents[1]/'wholeboard/web/workbench-example.json').read_text())
    spec['fixed_copper']=[{'net':'CC1','tracks':[{'id':'11111111-1111-4111-8111-111111111111','a':[12,12],'b':[14,12],'w':.35,'layer':'F.Cu'}],'vias':[{'p':[14,12],'d':.6,'drill':.3}]}]
    zone=board.zone('GND','F.Cu',30,22,.5,.25,priority=3)
    spec['fixed_zones']=[{'net':'GND','origin':[100,100],'source':sexpr.dumps(zone)}]
    spec['library']={'symbols':{},'footprints':{},'parts':{}}
    return spec


def test_two_module_instances_keep_routed_layout_and_isolate_net_and_native_identities(tmp_path):
    from wholeboard import modules
    original=source();before=copy.deepcopy(original);asset=modules.publish(original,name='USB supply',ports={'IN':'VBUS','GND':'GND'})
    target={'name':'module_acceptance','board':{'width_mm':100,'height_mm':60,'layers':2},'components':[],'nets':[],'library':{'modules':{'Supply':asset}}}
    first=modules.instantiate(target,'Supply','M1',offset=[5,4])
    result=modules.instantiate(first,'Supply','M2',offset=[45,4])
    assert len(result['components'])==18
    assert len({c['ref'] for c in result['components']})==18
    assert result['components'][0]['placement']['x_mm']==9.5
    assert result['components'][9]['placement']['x_mm']==49.5
    assert {c['sheet'] for c in result['components']}=={'M1','M2'}
    assert {net['name'] for net in result['nets']}=={f'{instance}_{name}' for instance in ('M1','M2') for name in ('VBUS','GND','CC1','CC2','+3V3','LED_K')}
    assert result['fixed_copper'][0]['tracks'][0]['a']==[17,16]
    assert result['fixed_copper'][1]['tracks'][0]['a']==[57,16]
    assert result['fixed_copper'][0]['tracks'][0]['id']!=result['fixed_copper'][1]['tracks'][0]['id']
    pcb=Path(board.build(result,tmp_path/'pcb')['pcb']);geo=geometry.read(pcb)
    assert len({t['id'] for t in geo['tracks']})==2
    zones=list(sexpr.find_all(sexpr.parse(pcb.read_text()),'zone'))
    assert len(zones)==2 and len({str(sexpr.find(z,'uuid')[1]) for z in zones})==2
    assert {z['net'] for z in geo['zone_sources']}=={'M1_GND','M2_GND'}
    assert original==before,'Publishing mutated the source'
    sch=schematic.build(result,tmp_path/'sch')
    if cli.find_kicad_cli():assert schematic.netlist_parity(result,cli.schematic_nets(Path(sch['sch'])))['ok']
    from wholeboard import schematic_view
    node=next(n for n in schematic_view.scene(result)['sheet_nodes'] if n['target']=='M1')
    assert next(p for p in node['ports'] if p.get('label')=='IN')['net']=='M1_VBUS'


def test_module_external_ports_are_explicit_and_keep_internal_copper():
    from wholeboard import modules
    asset=modules.publish(source(),name='Supply',ports={'IN':'VBUS','GND':'GND'})
    target={'board':{'width_mm':100,'height_mm':60,'layers':2},'components':[{'ref':'J1'}],'nets':[{'name':'COMMON','pins':['J1.1']}],'library':{'modules':{'Supply':asset}}}
    result=modules.instantiate(target,'Supply','M1',connections={'GND':'COMMON'})
    assert 'J1.1' in next(n for n in result['nets'] if n['name']=='COMMON')['pins']
    assert next(c for c in result['components'] if c.get('sheet')=='M1')['ref']=='J2'
    assert result['fixed_zones'][0]['net']=='COMMON'
    assert result['editor']['sheets']['M1']['ports']['GND']['net']=='COMMON'
    assert result['fixed_copper'][0]['net']=='M1_CC1'
    with pytest.raises(ValueError,match='port|terminal'):modules.instantiate(target,'Supply','M2',connections={'MISSING':'COMMON'})
    with pytest.raises(ValueError,match='layer|stackup'):modules.instantiate({**target,'board':{**target['board'],'layers':1}},'Supply','M3')


def test_native_copper_metadata_uses_the_instantiated_net_name():
    from wholeboard import modules
    original=source();original['fixed_copper'][0]['tracks'][0]['net']='CC1'
    asset=modules.publish(original,name='Supply')
    target={'board':{'width_mm':100,'height_mm':60,'layers':2},'components':[],'nets':[],'library':{'modules':{'Supply':asset}}}
    result=modules.instantiate(target,'Supply','M1')
    assert result['fixed_copper'][0]['tracks'][0]['net']=='M1_CC1'


def test_portable_module_assets_reject_recursive_templates_and_missing_pins():
    from wholeboard import modules
    asset=modules.publish(source(),name='Supply',ports={'IN':'VBUS'})
    bad=copy.deepcopy(asset);bad['design']['library']['modules']={'Recursive':asset}
    with pytest.raises(ValueError,match='nested|recursive'):project_library.validate({'library':{'modules':{'Invalid':bad}}})
    bad=copy.deepcopy(asset);bad['design']['nets'][0]['pins'].append('MISSING.1')
    with pytest.raises(ValueError,match='component|pin'):project_library.validate({'library':{'modules':{'Invalid':bad}}})


@pytest.mark.parametrize('field,value',[('library',[]),('editor','invalid'),('fixed_copper','invalid')])
def test_malformed_portable_templates_fail_with_a_validation_error(field,value):
    from wholeboard import modules
    asset=modules.publish(source(),name='Supply');asset['design'][field]=value
    with pytest.raises(ValueError):project_library.validate({'library':{'modules':{'Invalid':asset}}})
