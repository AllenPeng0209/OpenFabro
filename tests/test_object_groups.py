"""Persist organizational groups without permitting malformed editor graphs."""
import copy
import pytest
from wholeboard import server, codex_bridge
from test_workbench import client, draft


def organization():
    return {'layout': {'groups': {'user-group:power': {'name': '电源', 'parent': 'components'}},
        'parents': {'component:R1': 'user-group:power'},
        'order': {'components': ['user-group:power'], 'user-group:power': ['component:R1']}}}


@pytest.mark.parametrize('change', [
    'cycle', 'missing_parent', 'missing_group', 'duplicate_order', 'bad_name',
    'native_parent', 'invalid_member', 'unknown_view', 'not_object', 'too_many_groups',
])
def test_api_rejects_invalid_group_metadata_without_saving(client, change):
    pid = draft(client)['id']
    spec = copy.deepcopy(server.mgr().get(pid).state['spec'])
    original = copy.deepcopy(spec)
    groups = organization()
    state = groups['layout']
    if change == 'cycle':
        state['groups']['user-group:power']['parent'] = 'user-group:power'
    elif change == 'missing_parent':
        state['groups']['user-group:power']['parent'] = 'user-group:missing'
    elif change == 'missing_group':
        state['parents']['component:R1'] = 'user-group:missing'
    elif change == 'duplicate_order':
        state['order']['components'] = ['user-group:power', 'user-group:power']
    elif change == 'bad_name':
        state['groups']['user-group:power']['name'] = ' '
    elif change == 'native_parent':
        state['groups']['user-group:power']['parent'] = 'pad:R1:one'
    elif change == 'invalid_member':
        state['parents'] = {'root': 'user-group:power'}
    elif change == 'unknown_view':
        groups['unknown'] = state
    elif change == 'not_object':
        groups = []
    elif change == 'too_many_groups':
        state['groups'] = {f'user-group:g{i}': {'name': 'Group', 'parent': 'components'} for i in range(1001)}
    spec.setdefault('editor', {})['object_tree'] = groups
    response = client.put(f'/api/workbench/projects/{pid}/design', json={'base_version': 1, 'spec': spec})
    assert response.status_code == 422, f'Invalid {change} group metadata reached the saved design: {response.text[:200]}'
    p = server.mgr().get(pid)
    assert p.state['workbench']['version'] == 1
    assert p.state['spec'] == original


def test_groups_roundtrip_with_native_identities_and_stale_members_without_electrical_edits(client):
    pid = draft(client)['id']
    spec = copy.deepcopy(server.mgr().get(pid).state['spec'])
    original = copy.deepcopy(spec)
    groups = organization()
    state = groups['layout']
    state['groups']['user-group:pads'] = {'name': 'Same-number pads', 'parent': 'pads:J1'}
    state['parents'].update({'pad:J1:uuid-a': 'user-group:pads', 'pad:J1:uuid-b': 'user-group:pads',
                            'component:deleted': 'user-group:power'})
    groups['schematic'] = {'groups': {'user-group:control': {'name': '控制', 'parent': 'components:'}},
                          'parents': {'component:R1': 'user-group:control'}, 'order': {}}
    spec.setdefault('editor', {})['object_tree'] = groups
    response = client.put(f'/api/workbench/projects/{pid}/design', json={'base_version': 1, 'spec': spec})
    assert response.status_code == 200, response.text
    saved = client.get(f'/api/projects/{pid}').json()['state']
    assert saved['spec'] == spec and saved['workbench']['version'] == 2
    assert saved['spec']['components'] == original['components'] and saved['spec']['nets'] == original['nets']
    stale = client.put(f'/api/workbench/projects/{pid}/design', json={'base_version': 1, 'spec': original})
    assert stale.status_code == 409


def test_agent_rejects_a_cyclic_group_design_without_mutating_saved_state(client):
    pid = draft(client)['id']
    spec = copy.deepcopy(server.mgr().get(pid).state['spec'])
    p = server.mgr().get(pid)
    original = copy.deepcopy(p.state['spec'])
    groups = organization()
    groups['layout']['groups']['user-group:power']['parent'] = 'user-group:power'
    spec.setdefault('editor', {})['object_tree'] = groups
    import json
    with pytest.raises(Exception, match='group|cycle'):
        codex_bridge.apply_result(p, {'message': 'Create group', 'design_json': json.dumps(spec), 'files': [], 'tools': []}, 'agent', 1)
    assert p.state['spec'] == original and p.state['workbench']['version'] == 1


def test_agent_net_rename_rebases_group_membership_and_native_category():
    from wholeboard import net_labels
    spec = {'board': {'width_mm': 30, 'height_mm': 22, 'layers': 2}, 'components': [], 'nets': [], 'editor': {'object_tree': {'layout': {
        'groups': {'user-group:signals': {'name': 'Signals', 'parent': 'nets'},
                   'user-group:traces': {'name': 'Traces', 'parent': 'net:SIG'}},
        'parents': {'net:SIG': 'user-group:signals'},
        'order': {'user-group:signals': ['net:SIG'], 'net:SIG': ['user-group:traces']}}}}}
    net_labels.rename_references(spec, 'SIG', 'SENSE')
    state = spec['editor']['object_tree']['layout']
    assert state['parents'] == {'net:SENSE': 'user-group:signals'}
    assert state['groups']['user-group:traces']['parent'] == 'net:SENSE'
    assert state['order']['user-group:signals'] == ['net:SENSE']
    assert state['order']['net:SENSE'] == ['user-group:traces']
