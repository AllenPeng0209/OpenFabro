"""Saved AI text-file changes with immutable byte snapshots and guarded restore."""
from __future__ import annotations

import copy
from contextlib import contextmanager
import difflib
import hashlib
import json
import logging
import re
import tempfile
import time
import uuid
from pathlib import Path

from . import design_identity, project_paths, revisions
from .file_catalog import TEXT_SUFFIXES


class ChangeConflict(ValueError):
    pass


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _directory(p, request_id):
    if not isinstance(request_id, str) or not re.fullmatch('[0-9a-f]{32}', request_id):
        raise ValueError('Use a valid AI request identifier.')
    return p.root / 'history/ai-changes' / request_id


def _target(p, path):
    root = p.root.resolve()
    rel = Path(path)
    target = (root / rel).resolve()
    if (not rel.parts or rel.is_absolute() or any(part.startswith('.') for part in rel.parts)
        or any((root.joinpath(*rel.parts[:i + 1])).is_symlink() for i in range(len(rel.parts)))
        or project_paths.protected_output(root, target, {'state.json', 'events.jsonl', 'design.json', 'config.json'})
        or target.suffix.lower() not in TEXT_SUFFIXES):
        raise ChangeConflict('A saved change refers to a protected project path.')
    return target


def _bytes(target):
    if target.exists():
        if not target.is_file() or target.stat().st_size > 4_000_000:
            raise ChangeConflict('A changed path is no longer a bounded project text file.')
        return target.read_bytes()
    return None


def _snapshot(directory, data):
    if data is None:
        return None
    digest = _sha(data)
    path = directory / 'blobs' / (digest + '.txt')
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != data:
            raise ChangeConflict('A historical file snapshot changed. Restore was stopped.')
    else:
        path.write_bytes(data)
    return digest


def _blob(p, request_id, digest):
    if digest is None:
        return None
    if not isinstance(digest, str) or not re.fullmatch('[0-9a-f]{64}', digest):
        raise ChangeConflict('The file snapshot identifier is invalid.')
    path = _directory(p, request_id) / 'blobs' / (digest + '.txt')
    if not path.is_file() or path.stat().st_size > 4_000_000:
        raise ChangeConflict('A historical file snapshot is unavailable.')
    data = path.read_bytes()
    if _sha(data) != digest:
        raise ChangeConflict('A historical file snapshot changed. Restore was stopped.')
    return data


def _load(p, request_id):
    directory = _directory(p, request_id)
    index = (p.state.get('ai_change_sets') or {}).get(request_id)
    if not index:
        raise FileNotFoundError('No saved file changes for this AI request.')
    name = index.get('manifest', '')
    if not re.fullmatch(r'[0-9a-f]{32}\.json', name):
        raise ChangeConflict('The saved change receipt is invalid.')
    path = directory / name
    if not path.is_file() or path.stat().st_size > 20_000_000:
        raise ChangeConflict('The saved change receipt is unavailable.')
    raw = path.read_bytes()
    if _sha(raw) != index.get('receipt_sha256'):
        raise ChangeConflict('The saved change receipt changed. Restore was stopped.')
    value = json.loads(raw)
    if value.get('project_id') != p.id or value.get('request_id') != request_id:
        raise ChangeConflict('The saved changes belong to another project or request.')
    return index, value


def _publish(p, request_id, value):
    directory = _directory(p, request_id)
    directory.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    name = uuid.uuid4().hex + '.json'
    (directory / name).write_bytes(raw)
    index = {'manifest': name, 'receipt_sha256': _sha(raw), 'status': 'applied',
             'version': p.state.get('workbench', {}).get('version', 0), 'files': len(value['files'])}
    rows = p.state.setdefault('ai_change_sets', {})
    rows[request_id] = index
    while len(rows) > 128:
        rows.pop(next(iter(rows)))


def prepare_files(p, request_id, writes):
    """Capture before bytes before the first write; subsequent turns retain the original baseline."""
    if not request_id or not writes:
        return None
    directory = _directory(p, request_id)
    changed = [(target, content.encode()) for target, content in writes if _bytes(target) != content.encode()]
    if not changed:
        return None
    if request_id in (p.state.get('ai_change_sets') or {}):
        index, value = _load(p, request_id)
        if index['status'] != 'applied':
            raise ChangeConflict('Use a new AI request after undoing a saved change.')
        _check(p, request_id, index, value, restoring=False)
        value = copy.deepcopy(value)
    else:
        version = p.state.get('workbench', {}).get('version', 0)
        before_version = version
        for row in reversed(p.state.get('ai_design_changes') or []):
            if row['version'] == before_version and row.get('request_id') == request_id:
                before_version = row['from_version']
            elif row['version'] <= before_version:
                break
        before = copy.deepcopy(p.state['spec'])
        if before_version != version:
            snapshot = p.root / 'history' / f'design-v{before_version}.json'
            if not snapshot.is_file():
                raise ChangeConflict('The initial design snapshot is unavailable.')
            before = json.loads(snapshot.read_text())['spec']
        value = {'schema': 1, 'project_id': p.id, 'request_id': request_id, 'from_version': before_version,
                 'to_version': version, 'before_spec': before, 'after_spec': copy.deepcopy(p.state['spec']), 'files': []}
    bypath = {row['path']: row for row in value['files']}
    for target, after in changed:
        path = target.relative_to(p.root.resolve()).as_posix()
        row = bypath.setdefault(path, {'path': path, 'before_sha256': _snapshot(directory, _bytes(target))})
        row['after_sha256'] = _snapshot(directory, after)
    value['files'] = sorted(bypath.values(), key=lambda row: row['path'])
    return value


def record_files(p, request_id, value):
    if value is None:
        return
    value['to_version'] = p.state.get('workbench', {}).get('version', 0)
    value['after_spec'] = copy.deepcopy(p.state['spec'])
    _publish(p, request_id, value)


def finish_design(p, request_id):
    """Include later design-tool turns from an already file-changing request."""
    if not request_id or request_id not in (p.state.get('ai_change_sets') or {}):
        return
    with p.lock:
        index, value = _load(p, request_id)
        version = p.state.get('workbench', {}).get('version', 0)
        if index['status'] != 'applied' or version == value['to_version']:
            return
        value['to_version'] = version
        value['after_spec'] = copy.deepcopy(p.state['spec'])
        _publish(p, request_id, value)
        p.save()
    p.emit({'type': 'ai_change_set', 'request_id': request_id, 'files': len(value['files']), 'version': version})


def _check(p, request_id, index, value, *, restoring=True):
    if restoring and ((p.worker and p.worker.is_alive()) or getattr(p, 'engine_busy', False)):
        raise ChangeConflict('Wait for the active run before restoring these changes.')
    side = 'after' if index['status'] == 'applied' else 'before'
    if p.state.get('workbench', {}).get('version', 0) != index['version'] or not design_identity.equal(p.state['spec'], value[side + '_spec']):
        raise ChangeConflict('The design changed after this AI request. Review the current project before restoring.')
    for row in value['files']:
        for key in ['before_sha256', 'after_sha256']:
            _blob(p, request_id, row[key])
        data = _bytes(_target(p, row['path']))
        if (None if data is None else _sha(data)) != row[side + '_sha256']:
            raise ChangeConflict(f"{row['path']} changed after this AI request. Its newer contents were preserved.")


def review(p, request_id):
    with p.lock:
        index, value = _load(p, request_id)
        reason = None
        try:
            _check(p, request_id, index, value)
        except ChangeConflict as error:
            reason = str(error)
        return {'request_id': request_id, 'receipt_sha256': index['receipt_sha256'], 'status': index['status'],
                'from_version': value['from_version'], 'to_version': value['to_version'],
                'current_version': p.state.get('workbench', {}).get('version', 0), 'files': value['files'],
                'design': revisions.compare(value['before_spec'], value['after_spec']),
                'can_restore': reason is None, 'blocked_reason': reason}


def file_diff(p, request_id, path):
    with p.lock:
        index, value = _load(p, request_id)
        row = next((row for row in value['files'] if row['path'] == path), None)
        if not row:
            raise FileNotFoundError('This file is not part of the saved AI change.')
        values = [_blob(p, request_id, row[key]) for key in ['before_sha256', 'after_sha256']]
        texts = [(data or b'').decode('utf-8', 'replace') for data in values]
        lines = list(difflib.unified_diff(texts[0].splitlines(), texts[1].splitlines(), fromfile='Before/' + path, tofile='After/' + path, lineterm=''))
        diff = '\n'.join(lines[:1500])
        shortened = len(diff) > 120_000
        diff = diff[:120_000]
        urls = [p.file_url(_directory(p, request_id) / 'blobs' / (digest + '.txt')) if digest else None
                for digest in [row['before_sha256'], row['after_sha256']]]
        return {**row, 'receipt_sha256': index['receipt_sha256'], 'diff': diff, 'truncated': len(lines) > 1500 or shortened,
                'before_url': urls[0], 'after_url': urls[1], 'before_bytes': len(values[0]) if values[0] is not None else None,
                'after_bytes': len(values[1]) if values[1] is not None else None,
                'line_endings_changed': ('\r\n' in texts[0]) != ('\r\n' in texts[1]),
                'encoding_replaced': any(data is not None and text.encode() != data for data, text in zip(values, texts))}


def _replace(target, data):
    if data is None:
        target.unlink(missing_ok=True)
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=target.parent, prefix='.wholeboard-', delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(data)
    try:
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def rollback_on_error(p, targets):
    """Compensate a failed in-process write while the caller holds the project lock."""
    saved_state = copy.deepcopy(p.state)
    next_version = p.state.get('workbench', {}).get('version', 0) + 1
    internal = [p.root / 'design.json', p.root / 'state.json', p.root / 'history' / f'design-v{next_version}.json']
    backups = [(target, target.read_bytes() if target.is_file() else None)
               for target in dict.fromkeys([*targets, *internal])]
    try:
        yield
    except Exception:
        p.state.clear()
        p.state.update(saved_state)
        for target, data in backups:
            current = target.read_bytes() if target.is_file() else None
            if current != data:
                _replace(target, data)
        raise


def _notify_committed(p, event):
    try:
        p.emit(event)
    except Exception as error:
        # A notification failure cannot turn a persisted Undo/Redo into a failed write.
        logging.getLogger(__name__).warning('AI file restore committed; notification failed: %s', error)


def restore(p, request_id, body):
    from .workbench import _write_spec
    with p.lock:
        index, value = _load(p, request_id)
        direction = body.get('direction')
        if direction not in ('undo', 'redo'):
            raise ValueError('Choose undo or redo.')
        if (body.get('receipt_sha256') != index['receipt_sha256'] or body.get('base_version') != index['version']
            or index['status'] != ('applied' if direction == 'undo' else 'undone')):
            raise ChangeConflict('These saved changes or the project version changed. Reload the review before restoring.')
        _check(p, request_id, index, value)
        side = 'before' if direction == 'undo' else 'after'
        writes = [(_target(p, row['path']), _blob(p, request_id, row[side + '_sha256'])) for row in value['files']]
        from . import mechanical_history
        cad_before = mechanical_history.capture_writes(p,writes)
        design_changed = not design_identity.equal(p.state['spec'], value[side + '_spec'])
        with rollback_on_error(p, [target for target, _ in writes]):
            for target, data in writes:
                _replace(target, data)
            if design_changed:
                current = index['version']
                p.state['spec'] = copy.deepcopy(value[side + '_spec'])
                p.state['workbench'] = {'version': current + 1, 'checks_stale': True, 'saved_at': time.time()}
                _write_spec(p)
            index['status'] = 'undone' if direction == 'undo' else 'applied'
            index['version'] = p.state.get('workbench', {}).get('version', 0)
            cad_history = mechanical_history.record_writes(p,cad_before,'Restored AI CAD source')
            p.save()
        version = index['version']
    _notify_committed(p, {'type': 'ai_change_set', 'request_id': request_id, 'files': len(value['files']), 'version': version})
    if design_changed:
        _notify_committed(p, {'type': 'design_saved', 'version': version, 'source': 'ai_restore'})
    for row in value['files']:
        _notify_committed(p, {'type': 'file_saved', 'path': row['path']})
    if cad_history is not None:_notify_committed(p,{'type':'mechanical_history_changed','history':cad_history})
    return {'ok': True, 'version': version, 'status': index['status'], 'spec': p.state['spec'],
            'workbench': dict(p.state['workbench'])}
