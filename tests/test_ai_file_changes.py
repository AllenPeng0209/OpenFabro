"""AI file review/undo preserves exact bytes and refuses newer project changes."""
import copy
import hashlib
import json
import threading

import pytest

from wholeboard import codex_bridge, design_origin, server
from test_workbench import client
from test_parametric_symbols import fixture


REQUEST = 'e' * 32


def setup_change(client, *, design=True):
    pid = client.post('/api/workbench/projects', json={'title': 'AI file changes', 'spec': fixture()}).json()['id']
    p = server.mgr().get(pid)
    old = p.root / 'docs/notes.md'
    old.parent.mkdir(parents=True, exist_ok=True)
    old.write_bytes(b'# Notes\r\nOriginal text\r\n')
    before = copy.deepcopy(p.state['spec'])
    after = copy.deepcopy(before)
    after['editor']['positions']['R1'][0] += 100
    with design_origin.scope(p, REQUEST):
        codex_bridge.apply_result(p, {'message': 'Changed two files',
            'design_json': json.dumps(after) if design else None,
            'files': [{'path': 'docs/notes.md', 'content': '# Notes\nReviewed text\n'},
                      {'path': 'firmware/main.c', 'content': 'int main(void) { return 0; }\n'}]}, 'agent', 1)
    return pid, p, before, after


def review(client, pid):
    response = client.get(f'/api/workbench/projects/{pid}/ai-changes/{REQUEST}')
    assert response.status_code == 200, response.text
    return response.json()


def action(client, pid, data, direction, version):
    return client.post(f'/api/workbench/projects/{pid}/ai-changes/{REQUEST}/restore', json={
        'direction': direction, 'base_version': version, 'receipt_sha256': data['receipt_sha256']})


def test_mixed_ai_change_reviews_and_reverses_design_and_exact_file_bytes(client):
    pid, p, before, after = setup_change(client)
    unrelated = p.root / 'docs/unrelated.txt'
    unrelated.write_text('Keep later unrelated work')
    data = review(client, pid)
    assert sorted(f['path'] for f in data['files']) == ['docs/notes.md', 'firmware/main.c']
    assert data['design']['field_change_count'] == 1
    assert data['design']['field_changes'][0]['path'] == '/editor/positions/R1/0'
    details = client.get(f'/api/workbench/projects/{pid}/ai-changes/{REQUEST}/file', params={'path': 'docs/notes.md'}).json()
    assert '-Original text' in details['diff'] and '+Reviewed text' in details['diff']
    undo = action(client, pid, data, 'undo', 2)
    assert undo.status_code == 200, undo.text
    assert p.state['spec'] == before and p.state['workbench']['version'] == 3
    assert (p.root / 'docs/notes.md').read_bytes() == b'# Notes\r\nOriginal text\r\n'
    assert not (p.root / 'firmware/main.c').exists()
    assert unrelated.read_text() == 'Keep later unrelated work'
    restored = review(client, pid)
    assert restored['status'] == 'undone' and restored['receipt_sha256'] == data['receipt_sha256']
    redo = action(client, pid, restored, 'redo', 3)
    assert redo.status_code == 200, redo.text
    assert p.state['spec'] == after and p.state['workbench']['version'] == 4
    assert (p.root / 'firmware/main.c').read_text() == 'int main(void) { return 0; }\n'


def test_newer_file_content_blocks_the_whole_restore_without_partial_writes(client):
    pid, p, _, after = setup_change(client)
    data = review(client, pid)
    (p.root / 'firmware/main.c').write_text('A collaborator changed this file')
    response = action(client, pid, data, 'undo', 2)
    assert response.status_code == 409, response.text
    assert p.state['spec'] == after and p.state['workbench']['version'] == 2
    assert (p.root / 'docs/notes.md').read_text() == '# Notes\nReviewed text\n'
    assert (p.root / 'firmware/main.c').read_text() == 'A collaborator changed this file'
    assert not review(client, pid)['can_restore']


def test_file_only_undo_redo_does_not_create_a_hardware_design_version(client):
    pid, p, before, _ = setup_change(client, design=False)
    data = review(client, pid)
    assert data['design']['field_change_count'] == 0
    assert action(client, pid, data, 'undo', 1).status_code == 200
    assert action(client, pid, data, 'undo', 1).status_code == 409
    assert action(client, pid, data, 'redo', 1).status_code == 200
    assert p.state['spec'] == before and p.state['workbench']['version'] == 1


def test_stale_design_run_or_receipt_cannot_restore_files(client):
    pid, p, _, _ = setup_change(client)
    data = review(client, pid)
    for body in [dict(direction='undo', base_version=1, receipt_sha256=data['receipt_sha256']),
                 dict(direction='undo', base_version=2, receipt_sha256='0' * 64)]:
        assert client.post(f'/api/workbench/projects/{pid}/ai-changes/{REQUEST}/restore', json=body).status_code == 409
    p.engine_busy = True
    assert action(client, pid, data, 'undo', 2).status_code == 409
    p.engine_busy = False
    newer = copy.deepcopy(p.state['spec'])
    newer['board']['width_mm'] = 42
    assert client.put(f'/api/workbench/projects/{pid}/design', json={'base_version': 2, 'spec': newer}).status_code == 200
    assert action(client, pid, data, 'undo', 3).status_code == 409
    assert (p.root / 'firmware/main.c').exists()


def test_one_request_keeps_its_original_files_across_several_agent_turns(client):
    pid, p, before, _ = setup_change(client)
    with design_origin.scope(p, REQUEST):
        codex_bridge.apply_result(p, {'message': 'Refine', 'files': [
            {'path': 'docs/notes.md', 'content': '# Notes\nFinal text\n'}]}, 'agent', 2)
    data = review(client, pid)
    assert len(data['files']) == 2
    assert action(client, pid, data, 'undo', 2).status_code == 200
    assert p.state['spec'] == before
    assert (p.root / 'docs/notes.md').read_bytes() == b'# Notes\r\nOriginal text\r\n'


def test_historical_file_snapshots_are_hash_pinned_and_not_editable(client):
    pid, p, _, _ = setup_change(client)
    data = review(client, pid)
    detail = client.get(f'/api/workbench/projects/{pid}/ai-changes/{REQUEST}/file', params={'path': 'docs/notes.md'}).json()
    before = client.get(detail['before_url'])
    assert before.content == b'# Notes\r\nOriginal text\r\n'
    rel = detail['before_url'].split('/files/')[1].split('?')[0]
    assert client.put(f'/api/workbench/projects/{pid}/text/{rel}', json={'content': 'Tamper', 'base_sha': hashlib.sha256(before.content).hexdigest()}).status_code == 422
    snapshot = p.root / rel
    snapshot.write_bytes(b'Tampered historical bytes')
    assert action(client, pid, data, 'undo', 2).status_code == 409
    assert (p.root / 'docs/notes.md').read_text() == '# Notes\nReviewed text\n'


def test_active_agent_can_extend_its_own_file_change_but_cannot_restore_it(client):
    pid, p, _, _ = setup_change(client)
    p.worker = threading.current_thread()
    with design_origin.scope(p, REQUEST):
        codex_bridge.apply_result(p, {'message': 'Later turn', 'files': [
            {'path': 'docs/notes.md', 'content': 'Final active agent turn\n'}]}, 'agent', 2)
    assert (p.root / 'docs/notes.md').read_text() == 'Final active agent turn\n'
    data = review(client, pid)
    assert not data['can_restore']
    assert action(client, pid, data, 'undo', 2).status_code == 409
    p.worker = None
    assert action(client, pid, data, 'undo', 2).status_code == 200


def test_later_design_tool_turn_is_included_with_the_original_file_changes(client):
    pid, p, before, _ = setup_change(client, design=False)
    moved = copy.deepcopy(before)
    moved['editor']['positions']['R1'][0] += 100
    with design_origin.scope(p, REQUEST):
        codex_bridge.apply_result(p, {'message': 'Tool-like later design save', 'design_json': json.dumps(moved), 'files': []}, 'agent', 1)
    data = review(client, pid)
    assert data['design']['field_change_count'] == 1
    assert action(client, pid, data, 'undo', 2).status_code == 200
    assert p.state['spec'] == before and not (p.root / 'firmware/main.c').exists()


def test_failed_second_restore_write_rolls_back_the_first_file(client, monkeypatch):
    from wholeboard import ai_changes
    pid, p, _, after = setup_change(client)
    data = review(client, pid)
    replace = ai_changes._replace
    count = 0
    def fail_second(target, content):
        nonlocal count
        count += 1
        if count == 2:
            raise OSError('Injected single write failure')
        return replace(target, content)
    monkeypatch.setattr(ai_changes, '_replace', fail_second)
    with pytest.raises(OSError, match='Injected single write failure'):
        action(client, pid, data, 'undo', 2)
    assert p.state['spec'] == after and p.state['workbench']['version'] == 2
    assert (p.root / 'docs/notes.md').read_bytes() == b'# Notes\nReviewed text\n'
    assert (p.root / 'firmware/main.c').is_file()
    assert review(client, pid)['status'] == 'applied'


def test_replaced_file_alias_cannot_redirect_restore_to_another_project_file(client):
    pid, p, _, _ = setup_change(client)
    data = review(client, pid)
    target = p.root / 'docs/notes.md'
    private = p.root / 'docs/.private.txt'
    private.write_bytes(target.read_bytes())
    target.unlink()
    target.symlink_to(private)
    assert action(client, pid, data, 'undo', 2).status_code == 409
    assert private.read_bytes() == b'# Notes\nReviewed text\n'
    assert target.is_symlink() and p.state['workbench']['version'] == 2


def test_duplicate_file_outputs_are_rejected_before_any_part_of_the_proposal_is_written(client):
    pid, p, _, _ = setup_change(client)
    original = (p.root / 'docs/notes.md').read_bytes()
    with pytest.raises(ValueError, match='[Dd]uplicate'):
        with design_origin.scope(p, 'f' * 32):
            codex_bridge.apply_result(p, {'message': 'Conflicting file outputs', 'files': [
                {'path': 'docs/notes.md', 'content': 'First output'},
                {'path': 'docs/notes.md', 'content': 'Second output'}]}, 'agent', 2)
    assert (p.root / 'docs/notes.md').read_bytes() == original
    assert p.state['workbench']['version'] == 2


def test_failed_design_save_does_not_leave_a_partially_undone_file_bundle(client, monkeypatch):
    from wholeboard import workbench
    pid, p, _, after = setup_change(client)
    data = review(client, pid)
    original_design = (p.root / 'design.json').read_bytes()
    def fail_save(project):
        (project.root / 'design.json').write_bytes(b'Interrupted design save')
        raise OSError('Injected design publication failure')
    monkeypatch.setattr(workbench, '_write_spec', fail_save)
    with pytest.raises(OSError, match='Injected design publication failure'):
        action(client, pid, data, 'undo', 2)
    assert p.state['spec'] == after and p.state['workbench']['version'] == 2
    assert (p.root / 'docs/notes.md').read_bytes() == b'# Notes\nReviewed text\n'
    assert (p.root / 'firmware/main.c').is_file()
    assert (p.root / 'design.json').read_bytes() == original_design
    assert review(client, pid)['status'] == 'applied'


def test_crlf_text_editor_uses_the_raw_file_hash_as_its_save_token(client):
    pid, p, _, _ = setup_change(client, design=False)
    original = b'# CRLF\r\nOriginal text\r\n'
    (p.root / 'docs/notes.md').write_bytes(original)
    loaded = client.get(f'/api/workbench/projects/{pid}/text/docs/notes.md').json()
    assert loaded['sha'] == hashlib.sha256(original).hexdigest()
    assert loaded['content'] == original.decode()
    saved = client.put(f'/api/workbench/projects/{pid}/text/docs/notes.md', json={
        'base_sha': loaded['sha'], 'content': '# CRLF\nEdited text\n'})
    assert saved.status_code == 200, saved.text
    assert (p.root / 'docs/notes.md').read_bytes() == b'# CRLF\nEdited text\n'
    assert p.state['workbench']['version'] == 1


@pytest.mark.parametrize('failure', ['second_file', 'design', 'state'])
def test_failed_initial_ai_proposal_restores_its_files_state_and_design(client, monkeypatch, failure):
    from wholeboard import workbench
    pid, p, _, _ = setup_change(client)
    before_state = copy.deepcopy(p.state)
    baseline = {path: path.read_bytes() for path in [p.root / 'docs/notes.md', p.root / 'design.json', p.root / 'state.json']}
    history = {path: path.read_bytes() for path in (p.root / 'history').rglob('*') if path.is_file()}
    changed = copy.deepcopy(p.state['spec'])
    changed['board']['width_mm'] = 42
    if failure == 'second_file':
        atomic = workbench._atomic_text
        count = 0
        def failing_write(target, content):
            nonlocal count
            count += 1
            if count == 2:
                raise OSError('Injected initial second-file failure')
            return atomic(target, content)
        monkeypatch.setattr(workbench, '_atomic_text', failing_write)
    elif failure == 'design':
        write = workbench._write_spec
        def failing_design(project):
            write(project)
            raise OSError('Injected initial design publication failure')
        monkeypatch.setattr(workbench, '_write_spec', failing_design)
    else:
        save = p.save
        def failing_state():
            save()
            raise OSError('Injected initial state publication failure')
        monkeypatch.setattr(p, 'save', failing_state)
    with pytest.raises(OSError, match='Injected initial'):
        with design_origin.scope(p, 'a' * 32):
            codex_bridge.apply_result(p, {'message': 'A proposal interrupted during application',
                'design_json': json.dumps(changed), 'files': [
                    {'path': 'docs/notes.md', 'content': 'New notes'},
                    {'path': 'docs/new-file.md', 'content': 'New file'}]}, 'agent', 2)
    assert p.state == before_state
    for path, data in baseline.items():
        assert path.read_bytes() == data, str(path)
    for path, data in history.items():
        assert path.read_bytes() == data, str(path)
    assert not (p.root / 'docs/new-file.md').exists()
    assert not (p.root / 'history/design-v3.json').exists()
