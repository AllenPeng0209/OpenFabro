"""Parametric symbols must change native presentation without changing physical pins."""
import copy
import json
import pytest
from wholeboard import server, sexpr, schematic_view
from wholeboard.kicad import schematic, cli
from test_workbench import client


def fixture():
    return {'name': 'parametric_fixture', 'board': {'width_mm': 40, 'height_mm': 30, 'layers': 2, 'ground_pour': None},
        'components': [
            {'ref': 'J1', 'value': 'Interface', 'symbol': 'Connector_Generic:Conn_01x04',
             'footprint': 'Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical', 'placement': {'x_mm': 8, 'y_mm': 8}},
            {'ref': 'R1', 'value': '1k', 'symbol': 'Device:R', 'footprint': 'Resistor_SMD:R_0603_1608Metric', 'placement': {'x_mm': 25, 'y_mm': 15}}],
        'nets': [{'name': 'CLK', 'pins': ['J1.1', 'R1.1']}, {'name': 'DATA', 'pins': ['J1.2', 'R1.2']},
                 {'name': 'VCC', 'class': 'power', 'pins': ['J1.3']}, {'name': 'GND', 'class': 'power', 'pins': ['J1.4']}],
        'editor': {'positions': {'J1': [200, 200], 'R1': [700, 200]}}}


def layout():
    return {'style': 'parametric', 'units': [''], 'sections': ['Power', 'Data'], 'pins': {
        '1': {'side': 'left', 'section': 'Data', 'group': 'SPI', 'order': 0, 'name': 'CLOCK'},
        '2': {'side': 'right', 'section': 'Data', 'group': 'SPI', 'order': 1},
        '3': {'side': 'top', 'section': 'Power', 'group': 'Supply', 'order': 0},
        '4': {'side': 'bottom', 'section': 'Power', 'group': 'Supply', 'order': 1}}}


def test_native_parametric_symbol_has_real_sections_groups_four_sides_and_unchanged_pin_numbers(tmp_path):
    spec = fixture();spec['components'][0]['symbol_layout'] = layout()
    scene = schematic_view.scene(spec);symbol = next(s for s in scene['symbols'] if s['ref'] == 'J1')
    definition = scene['definitions'][symbol['definition']]
    assert definition.get('parametric'), 'The native schematic still ignores parametric pin layout'
    pins = {p['number']: p for p in definition['pins']}
    assert set(pins) == {'1', '2', '3', '4'}
    assert {n: p['angle'] for n, p in pins.items()} == {'1': 0, '2': 180, '3': 270, '4': 90}
    assert pins['1']['name'] == 'CLOCK' and all(p['type'] == 'passive' for p in pins.values())
    labels = {g['text'] for g in definition['graphics'] if g['kind'] == 'text'}
    assert {'Power', 'Data', 'SPI', 'Supply'} <= labels
    sizes = {g['text']:g.get('size') for g in definition['graphics'] if g['kind']=='text'}
    assert sizes['Supply']==1.0 and sizes['Power']==1.27, 'Web geometry lost native label font sizes'
    built = schematic.build(spec, tmp_path)
    assert schematic.netlist_parity(spec, cli.schematic_nets(tmp_path / (spec['name'] + '.kicad_sch')))['ok']


@pytest.mark.parametrize('bad', ['style', 'unknown_pin', 'side', 'order', 'number', 'units', 'section_order', 'name'])
def test_invalid_symbol_layout_is_rejected_without_saving(client, bad):
    spec = fixture();made = client.post('/api/workbench/projects', json={'title': 'Symbol validation', 'spec': spec}).json();pid = made['id']
    original = copy.deepcopy(server.mgr().get(pid).state['spec']);cfg = layout()
    if bad == 'style': cfg['style'] = 'guessed'
    elif bad == 'unknown_pin': cfg['pins']['99'] = {'side': 'left'}
    elif bad == 'side': cfg['pins']['1']['side'] = 'diagonal'
    elif bad == 'order': cfg['pins']['1']['order'] = True
    elif bad == 'number': cfg['pins']['1']['number'] = '2'
    elif bad == 'units': cfg['units'] = ['A', 'A']
    elif bad == 'section_order': cfg['sections'] = ['Data', 'Data']
    elif bad == 'name': cfg['pins']['1']['name'] = 'x' * 101
    spec['components'][0]['symbol_layout'] = cfg
    response = client.put(f'/api/workbench/projects/{pid}/design', json={'base_version': 1, 'spec': spec})
    assert response.status_code == 422, f'Invalid {bad} symbol presentation was accepted'
    assert server.mgr().get(pid).state['spec'] == original and server.mgr().get(pid).state['workbench']['version'] == 1


def test_symbol_prepare_returns_a_native_proven_unsaved_proposal_and_preserves_pcb(client):
    spec = fixture();pid = client.post('/api/workbench/projects', json={'title': 'Symbol prepare', 'spec': spec}).json()['id']
    response = client.post(f'/api/workbench/projects/{pid}/symbols/prepare', json={
        'base_version': 1, 'ref': 'J1', 'action': 'pins', 'pins': ['1', '2'],
        'patch': {'side': 'right', 'section': 'Data', 'group': 'SPI', 'order': 1}})
    assert response.status_code == 200, response.text
    proposal = response.json();assert proposal['native_parity']['ok']
    assert proposal['spec']['nets'] == spec['nets'] and proposal['spec']['board'] == spec['board']
    assert [{k: v for k, v in c.items() if k != 'symbol_layout'} for c in proposal['spec']['components']] == spec['components']
    assert server.mgr().get(pid).state['workbench']['version'] == 1
    saved = client.put(f'/api/workbench/projects/{pid}/design', json={'base_version': 1, 'spec': proposal['spec']})
    assert saved.status_code == 200
    assert client.post(f'/api/workbench/projects/{pid}/symbols/prepare', json={'base_version': 1, 'ref': 'J1', 'action': 'style', 'style': 'native'}).status_code == 409


def test_split_subsymbol_rebinds_real_wire_anchor_and_native_pin_groups(client):
    spec = fixture();spec['editor']['connection_guides'] = [{'id': 'clock-wire', 'from': 'J1.1', 'to': 'R1.1'}]
    before = schematic_view.scene(spec);route = before['routes'][0]
    assert route['status'] == 'routed'
    spec['editor']['connection_guides'][0]['fixed_points'] = route['points']
    pid = client.post('/api/workbench/projects', json={'title': 'Split symbol', 'spec': spec}).json()['id']
    response = client.post(f'/api/workbench/projects/{pid}/symbols/prepare', json={'base_version': 1, 'ref': 'J1', 'action': 'pins', 'pins': ['1'], 'patch': {'subsymbol': 'Clock', 'side': 'right'}})
    assert response.status_code == 200, response.text
    result = response.json();assert result['native_parity']['ok']
    assert result['spec']['editor']['connection_guides'][0]['from'] == 'J1#2.1'
    assert 'clock-wire' in result['summary']['rerouted_guides']
    symbols = [s for s in result['scene']['symbols'] if s['ref'] == 'J1']
    assert {s['unit'] for s in symbols} == {1, 2}
    assert result['spec']['nets'] == spec['nets']
    for symbol in before['symbols']:
        if symbol['ref'] != 'J1':
            after = next(s for s in result['scene']['symbols'] if s['key'] == symbol['key'])
            assert after['position'] == symbol['position'] and after['rotation'] == symbol['rotation']


def test_native_style_restores_original_multiunit_pin_ownership():
    from wholeboard import parametric_symbols
    spec = fixture();component = spec['components'][0]
    component['symbol'] = 'Amplifier_Operational:LM358'
    component['symbol_layout'] = {'style': 'native', 'units': ['Merged'], 'pins': {'1': {'subsymbol': 'Merged'}}}
    info = parametric_symbols.settings(component, spec)
    assert info['units'] == ['A', 'B', 'C']
    assert {p['number']: p['unit'] for p in info['pins']} == {'1': 1, '2': 1, '3': 1, '4': 3, '5': 2, '6': 2, '7': 2, '8': 3}


def test_deleting_empty_subsymbol_preserves_other_unit_poses_and_group_identity():
    from wholeboard import parametric_symbols
    spec = fixture();spec['components'][0]['symbol_layout'] = {'style': 'parametric', 'units': ['', 'Empty', 'Clock'], 'pins': {'1': {'subsymbol': 'Clock'}}}
    spec['editor']['positions'].update({'J1#2': [400, 300], 'J1#3': [600, 300]})
    spec['editor']['object_tree'] = {'schematic': {'groups': {'user-group:clock': {'name': 'Clock unit', 'parent': 'component:J1'}}, 'parents': {'symbol:J1#3': 'user-group:clock'}, 'order': {'user-group:clock': ['symbol:J1#3']}}}
    result = parametric_symbols.prepare(spec, {'ref': 'J1', 'action': 'remove_unit', 'suffix': 'Empty'})
    after = result['spec']
    assert after['components'][0]['symbol_layout']['units'] == ['', 'Clock']
    assert after['editor']['positions']['J1#2'] == [600, 300] and 'J1#3' not in after['editor']['positions']
    assert after['editor']['object_tree']['schematic']['parents'] == {'symbol:J1#2': 'user-group:clock'}
    with pytest.raises(ValueError, match='empty|pins'):
        parametric_symbols.prepare(spec, {'ref': 'J1', 'action': 'remove_unit', 'suffix': 'Clock'})


def test_agent_symbol_tool_uses_native_proof_and_preserves_physical_design(client):
    from wholeboard import codex_bridge
    spec = fixture();pid = client.post('/api/workbench/projects', json={'title': 'Symbol agent tool', 'spec': spec}).json()['id'];p = server.mgr().get(pid)
    result = codex_bridge.execute_tool(p, 'edit_symbol_layout', {'ref': 'J1', 'action': 'pins', 'pins': ['1', '2'], 'patch': {'side': 'right', 'group': 'SPI', 'section': 'Data'}}, 'agent')
    assert result['version'] == 2 and result['native_parity']['ok']
    assert p.state['spec']['nets'] == spec['nets'] and p.state['spec']['components'][0]['placement'] == spec['components'][0]['placement']
    inspected = codex_bridge.execute_tool(p, 'inspect_symbol_layout', {'ref': 'J1'}, 'chat')
    assert inspected['style'] == 'parametric'
    assert {pin['number']: pin['side'] for pin in inspected['pins']}['1'] == 'right'
    assert p.state['workbench']['version'] == 2
    with pytest.raises(ValueError):
        codex_bridge.execute_tool(p, 'edit_symbol_layout', {'ref': 'J1', 'action': 'style', 'style': 'native'}, 'chat')


def test_parametric_mode_preserves_electrical_type_and_clock_pin_shape():
    spec = fixture();spec['library'] = {'symbols': {'Clocked': {'name': 'Clocked', 'graphics': [], 'pins': [
        {'number': str(i), 'name': 'Pin'+str(i), 'type': 'input' if i == 1 else 'passive', 'shape': 'clock' if i == 1 else 'line', 'x': -5.08, 'y': (i-2)*2.54, 'angle': 0, 'unit': 1} for i in range(1, 5)]}}}
    spec['components'][0].update(symbol='Project:Clocked', symbol_layout={'style': 'parametric'})
    scene = schematic_view.scene(spec);symbol = next(s for s in scene['symbols'] if s['ref'] == 'J1');pin = next(p for p in scene['definitions'][symbol['definition']]['pins'] if p['number'] == '1')
    assert pin['type'] == 'input' and pin['shape'] == 'clock', 'Parametric rendering discarded the verified source pin shape/type'


def test_moving_pins_reorders_one_group_without_renumbering_physical_pins():
    from wholeboard import parametric_symbols
    spec = fixture();spec['components'][0]['symbol_layout'] = {'style': 'parametric', 'units': [''], 'pins': {str(i): {'side': 'left', 'section': 'IO', 'group': 'Port', 'order': i} for i in range(1,5)}}
    result = parametric_symbols.prepare(spec, {'ref': 'J1', 'action': 'move', 'pins': ['4'], 'side': 'left', 'section': 'IO', 'group': 'Port', 'subsymbol': '', 'before': '2'})
    layout = result['spec']['components'][0]['symbol_layout'];order = sorted(layout['pins'], key=lambda p:layout['pins'][p]['order'])
    assert order == ['1','4','2','3'] and result['spec']['nets'] == spec['nets']


def test_vertical_pin_names_have_space_before_group_and_section_labels():
    spec = fixture();spec['components'][0]['symbol_layout'] = {'style': 'parametric', 'pins': {'1': {'name': 'CLOCKINPUT', 'side': 'top', 'group': 'Supply', 'section': 'Power'}}}
    scene = schematic_view.scene(spec);symbol = next(s for s in scene['symbols'] if s['ref']=='J1');definition = scene['definitions'][symbol['definition']];meta = definition['parametric'];pin = next(p for p in definition['pins'] if p['number']=='1')
    group = next(label for label in meta['labels'] if label['kind']=='group' and label['group']=='Supply');section = next(label for label in meta['labels'] if label['kind']=='section' and label['section']=='Power')
    assert group['position'][1] < pin['y']-pin['length']-5, 'Vertical pin name and group label overlap'
    assert section['position'][1] < group['position'][1]


def test_removing_first_empty_unit_does_not_reassign_default_native_unit_pins():
    from wholeboard import parametric_symbols
    spec=fixture();component=spec['components'][0];component.update(symbol='Amplifier_Operational:LM358',footprint='Package_DIP:DIP-8_W7.62mm',symbol_layout={'style':'parametric','units':['A','B','C'],'pins':{n:{'subsymbol':'B'} for n in ['1','2','3']}})
    result=parametric_symbols.prepare(spec,{'ref':'J1','action':'remove_unit','suffix':'A'});info=parametric_symbols.settings(result['spec']['components'][0],result['spec']);pins={p['number']:p for p in info['pins']}
    assert pins['5']['subsymbol']=='B' and pins['5']['unit']==1, 'Compacting units changed default amplifier pin ownership'
    assert pins['4']['subsymbol']=='C' and pins['4']['unit']==2


def test_inspection_reports_missing_explicit_layout_properties_separately_from_native_validity():
    from wholeboard import parametric_symbols
    spec=fixture();spec['components'][0]['symbol_layout']={'style':'parametric','pins':{'1':{'side':'left','group':'SPI','section':'Data'}}}
    info=parametric_symbols.settings(spec['components'][0],spec)
    assert {item['number'] for item in info.get('issues',[])}=={'2','3','4'}, 'Missing parametric properties are not exposed for review'
    assert all(item['missing']==['side','group','section'] for item in info['issues'])


def test_project_pins_table_exposes_symbol_properties_without_overloading_bus_constraints(client):
    spec=fixture();spec['components'][0]['symbol_layout']=layout();pid=client.post('/api/workbench/projects',json={'title':'Symbol pin table','spec':spec}).json()['id']
    rows=client.get(f'/api/workbench/projects/{pid}/pins').json()['pins'];pin=next(p for p in rows if p['id']=='J1.2')
    assert pin.get('symbol_properties',{}).get('side')=='right'
    assert pin['symbol_properties']['group']=='SPI' and pin['symbol_properties']['section']=='Data'
    assert 'group' not in pin['properties'] and 'section' not in pin['properties']


def test_display_only_rename_preserves_a_still_valid_exact_schematic_path(client):
    from wholeboard import parametric_symbols
    spec=fixture();spec['components'][0]['symbol_layout']={'style':'parametric','units':[''],'pins':{str(i):{'side':'left','group':'SPI','section':'Data','order':i} for i in range(1,5)}};spec['editor']['connection_guides']=[{'id':'clock-wire','from':'J1.1','to':'R1.1'}]
    before=schematic_view.scene(spec);assert before['routes'][0]['status']=='routed';points=before['routes'][0]['points'];spec['editor']['connection_guides'][0]['fixed_points']=points
    pid=client.post('/api/workbench/projects',json={'title':'Preserve exact path','spec':spec}).json()['id'];result=parametric_symbols.project_draft(server.mgr().get(pid),{'ref':'J1','action':'pins','pins':['1'],'patch':{'name':'CLOCK'}})
    assert not result['summary']['requires_route_review'], 'A display-only edit unnecessarily discards an exact route'
    assert result['spec']['editor']['connection_guides'][0]['fixed_points']==points
    assert result['scene']['routes'][0]['fixed_path']


def test_symbol_growth_cannot_silently_remove_a_previously_routed_drawing(client):
    from wholeboard import parametric_symbols
    spec=fixture();spec['components'][0]['symbol_layout']={'style':'parametric','units':[''],'pins':{str(i):{'side':'left','group':'SPI','section':'Data','order':i} for i in range(1,5)}};spec['editor']['connection_guides']=[{'id':'clock-wire','from':'J1.1','to':'R1.1'}]
    assert schematic_view.scene(spec)['routes'][0]['status']=='routed'
    pid=client.post('/api/workbench/projects',json={'title':'Route growth','spec':spec}).json()['id'];p=server.mgr().get(pid)
    with pytest.raises(ValueError, match='route|drawing|overlap'):
        parametric_symbols.project_draft(p,{'ref':'J1','action':'pins','pins':['1'],'patch':{'name':'X'*100}})
    assert p.state['spec']==spec and p.state['workbench']['version']==1


def test_agent_exact_route_release_requires_concrete_confirmation(client):
    from wholeboard import codex_bridge
    spec=fixture();spec['editor']['connection_guides']=[{'id':'clock-wire','from':'J1.1','to':'R1.1'}];spec['editor']['connection_guides'][0]['fixed_points']=schematic_view.scene(spec)['routes'][0]['points']
    pid=client.post('/api/workbench/projects',json={'title':'Exact route review','spec':spec}).json()['id'];p=server.mgr().get(pid);args={'ref':'J1','action':'pins','pins':['1'],'patch':{'side':'right','group':'SPI','section':'Data'}}
    review=codex_bridge.execute_tool(p,'edit_symbol_layout',args,'agent');assert review['requires_route_review'] and review['summary']['released_exact_routes']==['clock-wire'];assert p.state['spec']==spec and p.state['workbench']['version']==1
    applied=codex_bridge.execute_tool(p,'edit_symbol_layout',{**args,'confirm_route_changes':True},'agent');assert applied['version']==2 and applied['native_parity']['ok'];assert p.state['spec']['nets']==spec['nets']


def test_native_style_respects_kicad_nested_hide_flags_for_pin_names():
    scene=schematic_view.scene(fixture());symbol=next(s for s in scene['symbols'] if s['ref']=='J1');definition=scene['definitions'][symbol['definition']]
    assert definition['show_pin_names'] is False, 'Native mode ignored the source symbol pin_names/hide yes flag'
