"""Visible project Markdown inventory and bounded, identifiable text snapshots."""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

READ_FILE_MAX_BYTES=2_000_000
DOCUMENT_CHARS=12_000
AUTOMATIC_DOCUMENTS=12
OMITTED_PATHS=100


def verify_hash(expected,actual,subject='file'):
    if expected is None:return
    if not isinstance(expected,str) or not re.fullmatch(r'[0-9a-fA-F]{64}',expected):
        raise ValueError('Expected SHA-256 must be a64-character hexadecimal digest.')
    if expected.lower()!=actual:
        raise ValueError(f'The {subject} changed since the earlier evidence. Start again from offset0 with the current snapshot.')


def catalog(root):
    root=Path(root).resolve();paths=[];errors=[]
    def error(exc):
        try:rel=Path(exc.filename).relative_to(root).as_posix()
        except (TypeError,ValueError):rel='project root'
        errors.append({'path':rel,'error':type(exc).__name__})
    for directory,dirs,files in os.walk(root,topdown=True,onerror=error,followlinks=False):
        folder=Path(directory);dirs[:]=sorted(name for name in dirs if not name.startswith('.') and not (folder/name).is_symlink())
        for name in sorted(files):
            path=folder/name
            if name.startswith('.') or path.suffix.lower() not in ('.md','.markdown') or path.is_symlink():continue
            try:
                if path.is_file() and path.resolve().is_relative_to(root):paths.append(path)
            except OSError as exc:error(exc)
    paths.sort(key=lambda p:(p.relative_to(root).as_posix().casefold(),p.relative_to(root).as_posix()))
    names=[p.relative_to(root).as_posix() for p in paths]
    digest=hashlib.sha256(json.dumps(names,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
    return {'paths':paths,'names':names,'index_sha256':digest,'scan_errors':errors[:100],'scan_errors_count':len(errors),'scan_errors_truncated':len(errors)>100}


def snapshot(path):
    result={'content':'','bytes':None,'characters':None,'sha256':None,'read_error':None}
    try:
        result['bytes']=path.stat().st_size
        if result['bytes']>READ_FILE_MAX_BYTES:
            result['read_error']='Use a project text file under2 MB.';return result
        with path.open('rb') as stream:data=stream.read(READ_FILE_MAX_BYTES+1)
        if len(data)>READ_FILE_MAX_BYTES:
            result['read_error']='Use a project text file under2 MB.';return result
        result.update(bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
        try:text=data.decode('utf-8')
        except UnicodeDecodeError:
            result['read_error']='The project document is not valid UTF-8 text.';return result
        result.update(content=text,characters=len(text))
    except OSError as error:result['read_error']=f'Cannot read this project document ({type(error).__name__}).'
    return result


def automatic(root):
    root=Path(root).resolve();index=catalog(root);documents=[]
    for path in index['paths'][:AUTOMATIC_DOCUMENTS]:
        row=snapshot(path);content=row['content'];end=min(len(content),DOCUMENT_CHARS)
        row.update(path=path.relative_to(root).as_posix(),content=content[:end],offset=0,next_offset=None if row['read_error'] else end,truncated=not row['read_error'] and end<len(content))
        documents.append(row)
    omitted=index['names'][len(documents):];preview=omitted[:OMITTED_PATHS]
    coverage={'scope':'Visible regular project Markdown (.md/.markdown); hidden and symlinked files/directories excluded.','total':len(index['paths']),'included':len(documents),'omitted':len(omitted),'omitted_paths':preview,'omitted_paths_truncated':len(preview)<len(omitted),'omitted_next_offset':len(documents)+len(preview),'index_sha256':index['index_sha256'],'failed':sum(bool(d['read_error']) for d in documents),'truncated_documents':sum(bool(d['truncated']) for d in documents),'content_complete':not omitted and not index['scan_errors_count'] and all(not d['truncated'] and not d['read_error'] for d in documents),'per_document_character_limit':DOCUMENT_CHARS,'read_file_byte_limit':READ_FILE_MAX_BYTES,**{key:index[key] for key in ('scan_errors','scan_errors_count','scan_errors_truncated')}}
    return documents,coverage


def listing(root,args):
    root=Path(root).resolve();index=catalog(root);offset=args.get('offset',0);limit=args.get('limit',100)
    if type(offset) is not int or type(limit) is not int or not 0<=offset<=len(index['paths']) or not 1<=limit<=100:
        raise ValueError('Choose a valid document offset and a limit from1 to100.')
    verify_hash(args.get('expected_index_sha256'),index['index_sha256'],'document index')
    rows=[];end=min(len(index['paths']),offset+limit)
    for path in index['paths'][offset:end]:
        row={'path':path.relative_to(root).as_posix(),'metadata_only':True}
        try:
            size=path.stat().st_size;row.update(bytes=size,within_read_limit=size<=READ_FILE_MAX_BYTES)
        except OSError as error:row.update(bytes=None,within_read_limit=False,read_error=type(error).__name__)
        rows.append(row)
    return {'documents':rows,'total':len(index['paths']),'offset':offset,'next_offset':end,'truncated':end<len(index['paths']),'index_sha256':index['index_sha256'],**{key:index[key] for key in ('scan_errors','scan_errors_count','scan_errors_truncated')}}
