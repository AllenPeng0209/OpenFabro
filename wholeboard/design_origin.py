"""Thread-local provenance for new saved AI design versions; earlier snapshots stay immutable."""
from __future__ import annotations
from contextlib import contextmanager
from contextvars import ContextVar
import hashlib
import json
import re
from . import design_identity

_origin=ContextVar('openfabro_design_origin',default=None)


@contextmanager
def scope(p,request_id=None,provider='codex'):
    if request_id is not None and (not isinstance(request_id,str) or not re.fullmatch('[0-9a-f]{32}',request_id)):
        raise ValueError('Use a valid originating AI request identifier.')
    with p.lock:before=(p.state.get('workbench') or {}).get('version',0)
    origin={'project_id':p.id,'request_id':request_id,'provider':provider,'files_changed':[],'committed':False,'before_version':before};token=_origin.set(origin)
    try:yield
    finally:
        _origin.reset(token)
        with p.lock:version=(p.state.get('workbench') or {}).get('version',0)
        if origin['committed'] and version>before:
            from . import ai_changes
            ai_changes.finish_design(p,request_id)
            p.emit({'type':'design_saved','from_version':before,'version':version,'source':'ai','request_id':request_id,'provider':provider})


def current(p):
    value=_origin.get()
    return value if value and value['project_id']==p.id else None


def note_files(p,paths):
    value=current(p)
    if value:
        value['files_changed']=list(paths)
        if paths and value['request_id']:
            records=p.state.setdefault('ai_file_changes',{});records[value['request_id']]=sorted(set(records.get(value['request_id'],[]))|set(paths))
            while len(records)>128:records.pop(next(iter(records)))


def metadata(p,version):
    value=current(p)
    if not value or version<=value['before_version']:return None
    return {'provider':value['provider'],'request_id':value['request_id'],'from_version':max(0,version-1),'version':version,'files_changed':value['files_changed']}


def committed(p,origin,snapshot):
    if not origin:return
    previous=p.root/'history'/f'design-v{origin["from_version"]}.json'
    record={**origin,'snapshot_sha256':hashlib.sha256(snapshot.read_bytes()).hexdigest(),'spec_sha256':design_identity.fingerprint(p.state.get('spec')),
            'previous_snapshot_sha256':hashlib.sha256(previous.read_bytes()).hexdigest() if previous.is_file() else None}
    rows=p.state.setdefault('ai_design_changes',[])
    if not any(row['version']==record['version'] for row in rows):rows.append(record)
    p.state['ai_design_changes']=rows[-128:]
    value=current(p)
    if value:value['committed']=True
