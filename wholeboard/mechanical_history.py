"""Persistent exact CAD-source/model-pointer Undo and Redo.

Native model revisions are immutable; the journal restores references and source
bytes, never regenerates a historical solid or changes an electrical design.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import threading
import time
import uuid

LIMIT = 512
MAX_SOURCE = 2_000_000


def canonical_source(p, name):
    from . import mechanical
    path = mechanical._source_path(p, name)
    root = p.root.resolve()
    cursor = root
    # Respect actual filesystem case while keeping distinct Linux paths distinct.
    for part in path.relative_to(root).parts:
        child = cursor/part
        if child.exists() and cursor.is_dir():
            names = {entry.name:entry for entry in cursor.iterdir()}
            if part not in names:
                child = next((entry for key,entry in names.items() if key.casefold()==part.casefold() and entry.samefile(child)), child)
        cursor = child
    return cursor.relative_to(root).as_posix()


def capture(p, source):
    from . import mechanical
    source = canonical_source(p, source)
    path = mechanical._source_path(p, source)
    if path.exists() and (not path.is_file() or path.stat().st_size>MAX_SOURCE):
        raise ValueError('CAD history needs a regular source file smaller than 2 MB.')
    raw = path.read_bytes() if path.is_file() else None
    if raw is not None and len(raw)>MAX_SOURCE:
        raise ValueError('CAD history source exceeds 2 MB.')
    model = (p.state.get('workbench_mechanical') or {}).get(source) or {}
    return {'source':source, 'raw':raw, 'asset_id':model.get('asset_id'), 'manifest_sha256':model.get('manifest_sha256')}


def _directory(p, create=False):
    root = p.root.resolve()
    path = root
    for name in ('history','mechanical'):
        path = path/name
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise ValueError('The CAD history directory changed.')
        if create:path.mkdir(exist_ok=True)
    return path


def _child(p, kind, name, create=False):
    directory = _directory(p, create)/kind
    if directory.is_symlink():raise ValueError('The CAD history snapshot directory changed.')
    if create:directory.mkdir(exist_ok=True)
    target = directory/name
    if target.is_symlink():raise ValueError('A CAD history snapshot changed.')
    return target


def _index(p):
    value = p.state.get('mechanical_history')
    if value is None:return {'schema':1,'revision':0,'cursor':0,'entries':[],'dropped':0}
    if not isinstance(value,dict) or value.get('schema')!=1 or type(value.get('revision')) is not int or type(value.get('cursor')) is not int or not isinstance(value.get('entries'),list) or not 0<=value['cursor']<=len(value['entries']) or value['revision']<0:
        raise ValueError('The saved CAD history is invalid.')
    return value


def _snapshot(p, value):
    raw = value['raw']
    digest = hashlib.sha256(raw).hexdigest() if raw is not None else None
    if raw is not None:
        file = _child(p,'blobs',digest+'.txt',True)
        if file.exists():
            if file.read_bytes()!=raw:raise ValueError('An immutable CAD source snapshot changed.')
        else:
            with file.open('xb') as stream:stream.write(raw)
    return {'sha256':digest,'asset_id':value['asset_id'],'manifest_sha256':value['manifest_sha256']}


def record(p, before, after, label='Changed CAD'):
    """Caller holds p.lock and a source/state compensation scope; caller saves."""
    if before['source']!=after['source']:raise ValueError('CAD history source identities differ.')
    if all(before[key]==after[key] for key in ('raw','asset_id','manifest_sha256')):return False
    index = _index(p)
    identifier = uuid.uuid4().hex
    from . import design_origin
    origin = design_origin.current(p)
    entry = {'schema':1,'id':identifier,'source':before['source'],'label':label,'created_at':time.time(),
             'origin':'agent' if origin else 'manual','request_id':origin.get('request_id') if origin else None,
             'before':_snapshot(p,before),'after':_snapshot(p,after)}
    raw = json.dumps(entry,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
    target = _child(p,'entries',identifier+'.json',True)
    with target.open('xb') as stream:stream.write(raw)
    item = {key:entry[key] for key in ('id','source','label','created_at','origin','request_id')}
    item['sha256'] = hashlib.sha256(raw).hexdigest()
    entries = [*index['entries'][:index['cursor']],item]
    dropped = max(0,len(entries)-LIMIT)
    entries = entries[-LIMIT:]
    p.state['mechanical_history'] = {'schema':1,'revision':index['revision']+1,'cursor':len(entries),
                                     'entries':entries,'dropped':index.get('dropped',0)+dropped}
    return True


def capture_writes(p, writes):
    return [capture(p,target.relative_to(p.root.resolve()).as_posix()) for target,_ in writes if target.name.endswith('.cad.json')]


def record_writes(p, snapshots, label):
    for before in snapshots:record(p,before,capture(p,before['source']),label)
    return summary(p) if snapshots else None


def _entry(p, item):
    identifier = item.get('id')
    if not isinstance(identifier,str) or not re.fullmatch('[0-9a-f]{32}',identifier):
        raise ValueError('The saved CAD history entry is invalid.')
    path = _child(p,'entries',identifier+'.json')
    if not path.is_file() or path.stat().st_size>20000:raise ValueError('The CAD history entry is missing.')
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=item.get('sha256'):raise ValueError('The CAD history entry changed.')
    value = json.loads(raw)
    if value.get('schema')!=1 or value.get('id')!=identifier or value.get('source')!=item.get('source'):
        raise ValueError('The CAD history entry identity changed.')
    return value


def _bytes(p, digest):
    if digest is None:return None
    if not isinstance(digest,str) or not re.fullmatch('[0-9a-f]{64}',digest):raise ValueError('The CAD source snapshot hash is invalid.')
    path = _child(p,'blobs',digest+'.txt')
    if not path.is_file() or path.stat().st_size>MAX_SOURCE:raise ValueError('The CAD source snapshot is unavailable.')
    data = path.read_bytes()
    if len(data)>MAX_SOURCE or hashlib.sha256(data).hexdigest()!=digest:raise ValueError('The CAD source snapshot changed.')
    return data


def _validate_current(p, source, expected):
    value = capture(p,source)
    if (hashlib.sha256(value['raw']).hexdigest() if value['raw'] is not None else None)!=expected.get('sha256'):
        raise ValueError('The CAD source changed outside this history step. Save or review the current file before restoring.')
    if value['asset_id']!=expected.get('asset_id') or value['manifest_sha256']!=expected.get('manifest_sha256'):
        raise ValueError('The current model changed outside this history step.')


def _target_model(p, source, snapshot):
    identifier = snapshot.get('asset_id')
    if identifier is None:
        if snapshot.get('manifest_sha256') is not None:raise ValueError('Invalid empty CAD model snapshot.')
        return None
    if not isinstance(identifier,str) or not re.fullmatch('[0-9a-f]{64}(?:-[0-9a-f]{12})?',identifier):raise ValueError('The saved CAD asset identity is invalid.')
    if p.state.get('mechanical_asset_receipts',{}).get(identifier)!=snapshot.get('manifest_sha256'):
        raise ValueError('The saved CAD asset integrity receipt changed.')
    from . import mechanical
    result = mechanical._record(p,p.root.resolve()/'mechanical'/identifier)
    if result['source']!=source:raise ValueError('The saved CAD model belongs to a different source.')
    return result


def summary(p):
    with p.lock:
        index = _index(p)
        result = {'schema':1,'revision':index['revision'],'cursor':index['cursor'],'count':len(index['entries']),
                  'dropped':index.get('dropped',0),'undo':None,'redo':None,'can_undo':False,'can_redo':False}
        for direction,at,side in [('undo',index['cursor']-1,'after'),('redo',index['cursor'],'before')]:
            if not 0<=at<len(index['entries']):continue
            item = index['entries'][at]
            result[direction] = {key:item.get(key) for key in ('id','source','label','origin','request_id')}
            try:
                value = _entry(p,item)
                _validate_current(p,value['source'],value[side])
                _bytes(p,value['before' if direction=='undo' else 'after']['sha256'])
                _target_model(p,value['source'],value['before' if direction=='undo' else 'after'])
                result['can_'+direction] = True
            except (ValueError,OSError,KeyError) as error:result[direction+'_blocked_reason'] = str(error)
        return result


def restore(p, body):
    from . import ai_changes,mechanical
    if not isinstance(body,dict) or set(body)-{'direction','revision','entry_id'}:
        raise ValueError('Use direction, revision and entry_id to restore CAD history.')
    direction = body.get('direction')
    if direction not in ('undo','redo') or type(body.get('revision')) is not int:
        raise ValueError('Choose undo or redo with the current history revision.')
    with p.lock:
        if p.engine_busy or p.worker and p.worker.is_alive() and p.worker is not threading.current_thread():
            raise mechanical.MechanicalConflict('Wait for the active run before restoring CAD history.')
        if p.worker is threading.current_thread() and (p.cancel.is_set() or p.inbox):
            raise mechanical.MechanicalConflict('CAD restoration canceled by a pending instruction.')
        index = _index(p)
        if body['revision']!=index['revision']:raise mechanical.MechanicalConflict('The CAD history revision changed. Reload before restoring.')
        at = index['cursor']-1 if direction=='undo' else index['cursor']
        if not 0<=at<len(index['entries']):raise mechanical.MechanicalConflict('There is no CAD change to '+direction+'.')
        item = index['entries'][at]
        if body.get('entry_id')!=item['id']:raise mechanical.MechanicalConflict('The CAD history entry changed.')
        entry = _entry(p,item);old,new = ('after','before') if direction=='undo' else ('before','after')
        _validate_current(p,entry['source'],entry[old])
        raw = _bytes(p,entry[new]['sha256']);asset = _target_model(p,entry['source'],entry[new])
        path = mechanical._source_path(p,entry['source'])
        with ai_changes.rollback_on_error(p,[path]):
            ai_changes._replace(path,raw)
            if asset is None:p.state.setdefault('workbench_mechanical',{}).pop(entry['source'],None)
            else:p.state.setdefault('workbench_mechanical',{})[entry['source']] = asset
            p.state['mechanical_history'] = {**index,'cursor':index['cursor']+(-1 if direction=='undo' else 1),'revision':index['revision']+1}
            next_history = summary(p)
            p.save()
        result = {'history':next_history,'source':entry['source'],'asset':asset,
                  'source_sha256':entry[new]['sha256'],'electrical_version':p.state.get('workbench',{}).get('version',0)}
    mechanical._notify(p,{'type':'mechanical_history_changed','history':result['history']})
    mechanical._notify(p,{'type':'mechanical_asset','source':entry['source'],'asset_id':asset['asset_id'] if asset else None,'removed':asset is None})
    mechanical._notify(p,{'type':'file_saved','path':entry['source']})
    return result
