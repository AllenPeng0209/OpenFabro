import copy
import hashlib
import json

import pytest
from fastapi.testclient import TestClient
from wholeboard import config, enclosure, project, server
from test_mechanical_parts import engine, program


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    if enclosure.find_freecad() is None:
        pytest.skip('FreeCAD is not installed')
    monkeypatch.setattr(config, 'APP_DIR', tmp_path)
    monkeypatch.setattr(config, 'CONFIG_FILE', tmp_path/'config.json')
    config.update({'projects_dir': str(tmp_path/'projects')})
    monkeypatch.setattr(server, 'manager', project.Manager())
    client = TestClient(server.app)
    made = client.post('/api/workbench/projects', json={'title': 'Mechanical first', 'spec': {'name': 'mechanical_first', 'board': {'width_mm': 40, 'height_mm': 30, 'layers': 2}, 'components': [], 'nets': []}}).json()
    p = server.mgr().get(made['id'])
    source = p.root/'cad/plate.cad.json'
    source.parent.mkdir()
    source.write_text(json.dumps(program(), indent=2))
    return client, p, source


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_rebuild_publishes_new_assets_and_preserves_electronics_and_previous_models(workspace):
    client, p, source = workspace
    before, version = copy.deepcopy(p.state['spec']), p.state['workbench']['version']
    first = engine().rebuild(p, {'path': 'cad/plate.cad.json', 'expected_sha256': digest(source)})
    assert first['source_sha256'] == digest(source) and first['metrics']['size_mm'] == pytest.approx([40,24,4])
    old = {f['path']: (digest(p.root/f['path']), (p.root/f['path']).stat().st_mtime_ns) for f in first['files']}
    cached = engine().rebuild(p, {'path': 'cad/plate.cad.json'})
    assert cached['asset_id'] == first['asset_id']
    changed = json.loads(source.read_text()); changed['parameters']['thickness']['value'] = 6
    source.write_text(json.dumps(changed, indent=2))
    assert engine().listing(p)['parts'][0]['stale']
    second = engine().rebuild(p, {'path': 'cad/plate.cad.json', 'expected_sha256': digest(source)})
    assert second['asset_id'] != first['asset_id'] and second['metrics']['size_mm'] == pytest.approx([40,24,6])
    assert len(engine().listing(p)['parts'][0]['versions']) == 2
    assert all((digest(p.root/name), (p.root/name).stat().st_mtime_ns) == value for name,value in old.items())
    assert p.state['spec'] == before and p.state['workbench']['version'] == version
    assert not p.state.get('workbench_native') and not (p.root/'native').exists()


def test_source_hash_and_source_change_during_native_build_reject_publication(workspace, monkeypatch):
    _, p, source = workspace
    with pytest.raises(Exception, match='changed|hash|SHA'):
        engine().rebuild(p, {'path': 'cad/plate.cad.json', 'expected_sha256': '0'*64})
    assert not p.state.get('workbench_mechanical')
    original = engine().build
    def changed_source(*args, **kwargs):
        result = original(*args, **kwargs)
        source.write_text(source.read_text()+'\n')
        return result
    monkeypatch.setattr(engine(), 'build', changed_source)
    with pytest.raises(Exception, match='changed'):
        engine().rebuild(p, {'path': 'cad/plate.cad.json'})
    assert not p.state.get('workbench_mechanical') and not p.engine_busy


def test_failed_or_canceled_rebuild_preserves_the_last_valid_asset(workspace, monkeypatch):
    _, p, source = workspace
    first = engine().rebuild(p, {'path': 'cad/plate.cad.json'})
    bad = program([{'id':'b','op':'box','size':[10,10,2]}, {'id':'f','op':'fillet','target':'b','radius':100,'edges':'vertical'}])
    source.write_text(json.dumps(bad))
    with pytest.raises(Exception, match='fillet|feature|Feature'):
        engine().rebuild(p, {'path': 'cad/plate.cad.json'})
    assert p.state['workbench_mechanical']['cad/plate.cad.json']['asset_id'] == first['asset_id']
    source.write_text(json.dumps(program(), indent=1))
    original = engine().build
    def canceled(*args, **kwargs):
        result = original(*args, **kwargs); p.cancel.set(); return result
    monkeypatch.setattr(engine(), 'build', canceled)
    with pytest.raises(Exception, match='cancel|stopped'):
        engine().rebuild(p, {'path': 'cad/plate.cad.json'})
    assert p.state['workbench_mechanical']['cad/plate.cad.json']['asset_id'] == first['asset_id'] and not p.engine_busy


def test_mechanical_api_agent_and_generated_files_share_publication_rules(workspace):
    client, p, source = workspace
    from wholeboard import codex_bridge
    with pytest.raises(ValueError, match='Chat mode'):
        codex_bridge.execute_tool(p, 'build_mechanical_part', {'path': 'cad/plate.cad.json'}, 'chat')
    built = client.post(f'/api/workbench/projects/{p.id}/mechanical/build', json={'path':'cad/plate.cad.json','expected_sha256':digest(source)})
    assert built.status_code == 200, built.text
    asset = built.json()
    listing = client.get(f'/api/workbench/projects/{p.id}/mechanical').json()
    assert listing['parts'][0]['asset_id'] == asset['asset_id'] and not listing['parts'][0]['stale']
    readonly = next(f for f in asset['files'] if f['name']=='source.cad.json')
    assert client.put(f'/api/workbench/projects/{p.id}/text/'+readonly['path'], json={'base_sha':readonly['sha256'],'content':'{}'}).status_code == 422
    entries = client.get(f'/api/workbench/projects/{p.id}/files').json()['files']
    assert next(f for f in entries if f['path']==readonly['path'])['text_editable'] is False
    assert client.get(asset['scene_url']).status_code == 200
    evidence = codex_bridge.execute_tool(p, 'inspect_mechanical_parts', {}, 'chat')
    assert evidence['parts'][0]['metrics']['valid'] is True


def test_asset_paths_cannot_read_external_or_generated_source(workspace, tmp_path):
    _, p, source = workspace
    outside = tmp_path/'outside.cad.json';outside.write_text(source.read_text())
    (source.parent/'link.cad.json').symlink_to(outside)
    for name in ['../outside.cad.json', str(outside), 'cad/link.cad.json', 'mechanical/generated/source.cad.json']:
        with pytest.raises((ValueError, RuntimeError)):
            engine().rebuild(p, {'path':name})


def test_agent_creates_and_rebuilds_a_part_from_code_in_one_tool_call(workspace):
    _, p, source = workspace
    from wholeboard import codex_bridge, design_origin, ai_changes
    before = copy.deepcopy(p.state['spec'])
    name = 'cad/bracket.cad.json'
    request_id = 'c'*32
    with design_origin.scope(p, request_id):
        result = codex_bridge.execute_tool(p, 'build_mechanical_part', {'path': name, 'program': program()}, 'agent')
    created = p.root/name
    assert created.is_file() and result['source_sha256'] == digest(created)
    assert p.state['spec'] == before and p.state['workbench']['version'] == 1
    assert request_id in p.state['ai_change_sets']
    evidence = ai_changes.review(p, request_id)
    assert any(f['path'] == name for f in evidence['files'])
    updated = program();updated['parameters']['thickness']['value'] = 7
    with pytest.raises(Exception, match='changed|hash|read|existing|source'):
        engine().rebuild(p, {'path': name, 'program': updated})
    second = engine().rebuild(p, {'path': name, 'program': updated, 'expected_sha256': digest(created)})
    assert second['metrics']['size_mm'][2] == 7 and second['asset_id'] != result['asset_id']
    assert len(engine().listing(p)['parts'][-1]['versions']) == 2


def test_failed_candidate_code_preserves_the_existing_editable_source(workspace):
    _, p, source = workspace
    before = source.read_bytes()
    bad = program([{'id':'b','op':'box','size':[10,10,2]}, {'id':'f','op':'fillet','target':'b','radius':100,'edges':'vertical'}])
    with pytest.raises(Exception, match='fillet|feature|Feature'):
        engine().rebuild(p, {'path': 'cad/plate.cad.json', 'program': bad, 'expected_sha256': digest(source)})
    assert source.read_bytes() == before and not p.state.get('workbench_mechanical')


def test_pattern_expansion_is_rejected_before_creating_excessive_native_geometry(tmp_path):
    if enclosure.find_freecad() is None:
        pytest.skip('FreeCAD is not installed')
    source = program([{'id':'c','op':'cylinder','radius':1,'height':2},
                      {'id':'p','op':'linear_pattern','target':'c','step':[4,0,0],'count':64},
                      {'id':'q','op':'linear_pattern','target':'p','step':[0,4,0],'count':64}])
    with pytest.raises(RuntimeError, match='budget|complex|solids'):
        engine().build(source, tmp_path/'part')


@pytest.mark.parametrize('cached', [False, True])
def test_notification_failure_never_removes_or_rejects_a_committed_asset(workspace, monkeypatch, cached):
    _, p, source = workspace
    if cached:
        engine().rebuild(p, {'path':'cad/plate.cad.json'})
    original = p.emit
    def broken_event(event):
        if event.get('type') == 'mechanical_asset':
            raise OSError('Injected notification failure')
        return original(event)
    monkeypatch.setattr(p, 'emit', broken_event)
    result = engine().rebuild(p, {'path':'cad/plate.cad.json'})
    persisted = json.loads((p.root/'state.json').read_text())
    assert persisted['workbench_mechanical']['cad/plate.cad.json']['asset_id'] == result['asset_id']
    assert all((p.root/f['path']).is_file() for f in result['files']) and not p.engine_busy


def test_case_insensitive_generated_directory_alias_cannot_overwrite_source_copies(workspace):
    _, p, source = workspace
    first = engine().rebuild(p, {'path':'cad/plate.cad.json'})
    protected = p.root/first['source_copy']
    alias = p.root/'Mechanical'/protected.relative_to(p.root/'mechanical')
    if not alias.exists() or not alias.samefile(protected):
        pytest.skip('This filesystem is case-sensitive')
    before = protected.read_bytes()
    changed = program();changed['parameters']['thickness']['value'] = 7
    with pytest.raises(ValueError):
        engine().rebuild(p, {'path':alias.relative_to(p.root).as_posix(),'program':changed,'expected_sha256':digest(protected)})
    assert protected.read_bytes() == before


@pytest.mark.parametrize('field,value', [('op', []), ('target', []), ('result', {})])
def test_malformed_json_fields_have_a_structured_validation_response(workspace, field, value):
    client, p, source = workspace
    candidate = program([{'id':'b','op':'box','size':[10,10,2]},{'id':'m','op':'translate','target':'b','vector':[1,0,0]}])
    if field == 'result':candidate['result'] = value
    else:candidate['features'][-1][field] = value
    result = client.post(f'/api/workbench/projects/{p.id}/mechanical/build',json={'path':'cad/new.cad.json','program':candidate})
    assert result.status_code == 422 and result.json()['detail']
    assert not p.state.get('workbench_mechanical')


def test_initial_status_failure_always_releases_the_engine(workspace, monkeypatch):
    _, p, _ = workspace
    def broken_status(*args):raise OSError('Injected initial status failure')
    monkeypatch.setattr(p, 'set_status', broken_status)
    with pytest.raises(OSError, match='Injected'):
        engine().rebuild(p, {'path':'cad/plate.cad.json'})
    assert not p.engine_busy


@pytest.mark.parametrize('field', ['source_sha256', 'volume_mm3'])
def test_corrupted_cached_manifest_is_rejected_against_the_accepted_record(workspace, field):
    _, p, source = workspace
    first = engine().rebuild(p, {'path':'cad/plate.cad.json'})
    manifest = p.root/'mechanical'/first['asset_id']/'manifest.json'
    data = json.loads(manifest.read_text())
    if field == 'source_sha256':data[field] = '0'*64
    else:data['metrics'][field] += 1
    manifest.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='manifest|asset|source|changed'):
        engine().rebuild(p, {'path':'cad/plate.cad.json'})


@pytest.mark.parametrize('failure', ['history', 'save'])
def test_failed_source_and_registry_commit_compensates_without_touching_old_models(workspace, monkeypatch, failure):
    _, p, source = workspace
    from wholeboard import ai_changes, design_origin
    first = engine().rebuild(p, {'path':'cad/plate.cad.json'})
    before = source.read_bytes()
    old = {f['path']:(digest(p.root/f['path']),(p.root/f['path']).stat().st_mtime_ns) for f in first['files']}
    changed = program();changed['parameters']['thickness']['value'] = 7
    if failure == 'history':
        def bad_history(*args):raise OSError('Injected history failure')
        monkeypatch.setattr(ai_changes,'record_files',bad_history)
    else:
        save = p.save
        def bad_save():
            record = (p.state.get('workbench_mechanical') or {}).get('cad/plate.cad.json',{})
            if record.get('asset_id') not in (None,first['asset_id']):raise OSError('Injected model save failure')
            save()
        monkeypatch.setattr(p,'save',bad_save)
    with design_origin.scope(p,'d'*32),pytest.raises(OSError,match='Injected'):
        engine().rebuild(p,{'path':'cad/plate.cad.json','program':changed,'expected_sha256':digest(source)})
    assert source.read_bytes() == before and p.state['workbench_mechanical']['cad/plate.cad.json']['asset_id'] == first['asset_id']
    assert json.loads((p.root/'state.json').read_text())['workbench_mechanical']['cad/plate.cad.json']['asset_id'] == first['asset_id']
    assert all((digest(p.root/name),(p.root/name).stat().st_mtime_ns)==value for name,value in old.items())
    assert not p.engine_busy


def test_ai_file_undo_returns_its_committed_result_even_if_notification_fails(workspace, monkeypatch):
    _, p, source = workspace
    from wholeboard import ai_changes, design_origin
    before = source.read_bytes();updated = program();updated['parameters']['thickness']['value'] = 6
    request_id = 'e'*32
    with design_origin.scope(p,request_id):
        engine().rebuild(p,{'path':'cad/plate.cad.json','program':updated,'expected_sha256':digest(source)})
    receipt = ai_changes.review(p,request_id);emit = p.emit
    def failed_notice(event):
        if event.get('type')=='ai_change_set':raise OSError('Injected restore notification failure')
        return emit(event)
    monkeypatch.setattr(p,'emit',failed_notice)
    restored = ai_changes.restore(p,request_id,{'direction':'undo','base_version':receipt['current_version'],'receipt_sha256':receipt['receipt_sha256']})
    assert restored['status']=='undone' and source.read_bytes()==before
    assert json.loads((p.root/'state.json').read_text())['ai_change_sets'][request_id]['status']=='undone'
