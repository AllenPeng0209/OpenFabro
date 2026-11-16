"""Private workspace module releases, visible through live source-project access."""
from __future__ import annotations
import copy
import hashlib
import json
import re
import threading
import time
import uuid
from pathlib import Path
from fastapi import HTTPException
from . import config,collaboration,module_updates,modules,project_library

_locks={}

def workspace_id():
    with collaboration.database() as db:
        db.execute('INSERT OR IGNORE INTO workspace(key,value) VALUES(?,?)',('module_workspace_id',uuid.uuid4().hex))
        return db.execute('SELECT value FROM workspace WHERE key=?',('module_workspace_id',)).fetchone()['value']

def identifier(project_id,module_id):return hashlib.sha256((workspace_id()+'\0'+project_id+'\0'+module_id).encode()).hexdigest()[:32]
def _directory():return config.APP_DIR/'module-catalog'
def _path(uid):
    if not isinstance(uid,str) or not re.fullmatch(r'[0-9a-f]{32}',uid):raise HTTPException(404,'Module source is unavailable.')
    return _directory()/(uid+'.json')

def _read(uid):
    try:row=json.loads(_path(uid).read_text())
    except (OSError,ValueError):raise HTTPException(404,'Module source is unavailable.') from None
    if row.get('id')!=uid or identifier(row.get('source_project',''),row.get('module_id',''))!=uid:raise HTTPException(422,'The module catalog record has invalid provenance.')
    modules.validate_asset(row['module_id'],row['asset']);return row

def publish(source,module_id,candidate,*,base_version,expected_version=0,note=''):
    if not project_library.identifier(module_id):raise ValueError('Choose a valid module library ID.')
    if isinstance(expected_version,bool) or not isinstance(expected_version,int) or expected_version<0:raise ValueError('Choose a nonnegative published module version.')
    uid=identifier(source.id,module_id);file=_path(uid)
    with _locks.setdefault(str(file),threading.RLock()),source.lock:
        if source.state.get('workbench',{}).get('version',0)!=base_version:raise HTTPException(409,'The source design changed before publishing.')
        if source.worker and source.worker.is_alive() or getattr(source,'engine_busy',False):raise HTTPException(409,'Wait for the source project run before publishing.')
        previous=_read(uid) if file.exists() else None;head=previous['asset'] if previous else None
        if expected_version!=(module_updates.version(head) if head else 0):raise HTTPException(409,'The published module changed. Refresh its release before publishing.')
        if head is not None:asset=module_updates.release(candidate,previous=head,note=note)
        else:
            local=source.state.get('spec',{}).get('library',{}).get('modules',{}).get(module_id)
            if local and module_updates.content_digest(local)==module_updates.content_digest(candidate):asset=copy.deepcopy(local);asset.setdefault('version',1);asset.setdefault('history',[]);asset['release_note']=note
            else:asset=module_updates.release(candidate,previous=local,note=note)
        asset['origin']={'catalog_id':uid,'workspace':workspace_id(),'project_id':source.id,'module_id':module_id,'source_version':base_version}
        modules.validate_asset(module_id,asset)
        row={'id':uid,'source_project':source.id,'module_id':module_id,'asset':asset,'published':time.time()}
        file.parent.mkdir(parents=True,exist_ok=True);temporary=file.with_suffix('.tmp');temporary.write_text(json.dumps(row,ensure_ascii=False,indent=2));temporary.replace(file)
    source.emit({'type':'module_catalog_changed'});return copy.deepcopy(asset)

def resolve(manager,actor,uid,*,version=None):
    row=_read(uid);source=manager.get(row['source_project'])
    if source is None or collaboration.ROLES.get(collaboration.project_role(actor,source),0)<10:raise HTTPException(404,'Module source is unavailable.')
    head=row['asset']
    if version is not None and (isinstance(version,bool) or not isinstance(version,int)):raise ValueError('Choose an integer module revision.')
    if version is None or version==module_updates.version(head):return copy.deepcopy(head)
    release=next((r for r in head.get('history',[]) if r['version']==version),None)
    if release is None:raise HTTPException(404,'The published module revision is unavailable.')
    return module_updates.revision(head,version)

def listing(manager,actor):
    result=[]
    for file in sorted(_directory().glob('*.json')):
        try:
            asset=resolve(manager,actor,file.stem);source=manager.get(asset['origin']['project_id'])
            result.append({'id':file.stem,'module':asset['origin']['module_id'],'name':asset['name'],'description':asset.get('description',''),'version':module_updates.version(asset),'source_project':source.id,'source_title':source.display_title(),'components':len(asset['design']['components']),'ports':list(asset['ports'])})
        except (HTTPException,ValueError,KeyError):continue
    return result

def updates(manager,actor,spec):
    result=[]
    for instance,meta in spec.get('editor',{}).get('module_instances',{}).items():
        local=spec.get('library',{}).get('modules',{}).get(meta.get('module'));head=local
        if local is None:continue
        uid=local.get('origin',{}).get('catalog_id') if local.get('origin',{}).get('workspace') in (None,workspace_id()) else None
        source_available=True
        if uid:
            try:head=resolve(manager,actor,uid)
            except HTTPException:
                head=local;uid=None;source_available=False
            if module_updates.version(head)<module_updates.version(local):head=local;uid=None
        if module_updates.version(head)>meta.get('version',1):
            result.append({'instance':instance,'module':meta['module'],'name':head['name'],'available':True,'source_available':source_available,'current_version':meta.get('version',1),'version':module_updates.version(head),'versions':sorted([r['version'] for r in head.get('history',[])]+[module_updates.version(head)]),'catalog_id':uid,'fingerprint':module_updates.digest(head)})
        elif not source_available:result.append({'instance':instance,'module':meta['module'],'available':False,'current_version':meta.get('version',1)})
    return result
