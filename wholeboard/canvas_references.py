"""Immutable, project-owned viewport PNG inputs. These are references, not design geometry."""
from __future__ import annotations

import base64
import hashlib
import io
import json
import re
import time
import uuid
import warnings
from pathlib import Path
from PIL import Image
from . import design_identity,config,canvas_layer_context

MAX_BYTES=8_000_000
MAX_PIXELS=8_000_000
PREFIX=Path('references/canvas')
MAX_CONTEXT_IMAGES=5


class StaleCanvasReference(ValueError):
    pass


def _png(data,width,height):
    if not data.startswith(b'\x89PNG\r\n\x1a\n') or len(data)>MAX_BYTES:
        raise ValueError('Use a PNG viewport capture smaller than8MB.')
    if type(width) is not int or type(height) is not int or not 1<=width<=4096 or not 1<=height<=4096 or width*height>MAX_PIXELS:
        raise ValueError('Use a viewport capture within4096px and8million pixels.')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error',Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data),formats=['PNG']) as image:
                if image.size!=(width,height) or getattr(image,'n_frames',1)!=1:
                    raise ValueError('The captured PNG dimensions do not match, or the image is animated.')
                image.verify()
            with Image.open(io.BytesIO(data),formats=['PNG']) as image:image.load()
    except (OSError,SyntaxError,Image.DecompressionBombWarning,Image.DecompressionBombError) as error:
        raise ValueError('The viewport PNG is damaged or too large.') from error


def _folder(p):
    folder=p.root/PREFIX
    if any(part.is_symlink() for part in (p.root/'references',folder)) or not folder.resolve().is_relative_to(p.root.resolve()):
        raise ValueError('The canvas reference folder must belong to this project.')
    return folder


def _public(p,metadata):
    return {**metadata,'path':(PREFIX/(metadata['id']+'.png')).as_posix(),'url':p.file_url(_folder(p)/(metadata['id']+'.png'))}


def create(p,body):
    if not isinstance(body,dict):raise ValueError('Use a viewport capture object.')
    version=body.get('base_version');view=body.get('view');strokes=body.get('strokes');sheet=body.get('sheet','')
    if type(version) is not int or version<0:raise ValueError('Use the saved design version for this capture.')
    if view not in ('schematic','layout','3d'):raise ValueError('Markup is available in Schematic, Layout and3D views.')
    if type(strokes) is not int or not 0<=strokes<=500:raise ValueError('Use up to500 markup strokes.')
    if not isinstance(sheet,str) or len(sheet)>300:raise ValueError('Use a valid schematic page identifier.')
    encoded=body.get('data')
    if not isinstance(encoded,str) or len(encoded)>MAX_BYTES*4//3+8:raise ValueError('Use a PNG viewport capture smaller than8MB.')
    try:data=base64.b64decode(encoded,validate=True)
    except (ValueError,TypeError) as error:raise ValueError('The viewport capture must be base64 PNG data.') from error
    width,height=body.get('width'),body.get('height');_png(data,width,height)
    with p.lock:
        if (p.state.get('workbench') or {}).get('version',0)!=version:
            raise StaleCanvasReference('The saved design changed. Start Markup again on the current design.')
        context=body.get('display_context')
        if context is not None:context=canvas_layer_context.validate(p,context,version,view,current=True)
        context_sha=canvas_layer_context.digest(context) if context is not None else None
        identifier=body.get('capture_id',uuid.uuid4().hex)
        if not isinstance(identifier,str) or not re.fullmatch(r'[0-9a-f]{32}',identifier):raise ValueError('Use a valid canvas capture identifier.')
        if (_folder(p)/(identifier+'.json')).exists():
            previous=resolve(p,identifier)
            if any(previous.get(key)!=value for key,value in {'sha256':hashlib.sha256(data).hexdigest(),'view':view,'sheet':sheet,'width':width,'height':height,'strokes':strokes,'display_context_sha256':context_sha}.items()):
                raise ValueError('The capture identifier was reused for a different image.')
            return previous
        metadata={'schema':1,'id':identifier,'project_id':p.id,'design_version':version,'design_sha256':design_identity.legacy_fingerprint(p.state.get('spec')),
                  'view':view,'sheet':sheet,'width':width,'height':height,'strokes':strokes,'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data),'created_at':time.time()}
        if context is not None:metadata.update(display_context=context,display_context_sha256=context_sha)
        folder=_folder(p);folder.mkdir(parents=True,exist_ok=True)
        image=folder/(identifier+'.png')
        if image.exists():
            if image.is_symlink() or not image.is_file() or image.stat().st_size!=len(data) or hashlib.sha256(image.read_bytes()).hexdigest()!=metadata['sha256']:
                raise ValueError('An incomplete capture with this identifier has different image bytes. Start Markup again.')
        else:
            with image.open('xb') as target:target.write(data)
        with (folder/(identifier+'.json')).open('x',encoding='utf-8') as target:json.dump(metadata,target,ensure_ascii=False)
    return _public(p,metadata)


def resolve(p,identifier,*,current=True):
    if not isinstance(identifier,str) or not re.fullmatch(r'[0-9a-f]{32}',identifier):raise ValueError('Choose a canvas reference from this project.')
    folder=_folder(p);path=folder/(identifier+'.json');image=folder/(identifier+'.png')
    if any(not f.is_file() or f.is_symlink() for f in (path,image)) or path.stat().st_size>32_000:
        raise ValueError('Canvas reference not found in this project.')
    try:metadata=json.loads(path.read_text(encoding='utf-8'))
    except (OSError,ValueError) as error:raise ValueError('The canvas reference metadata is damaged.') from error
    if metadata.get('schema')!=1 or metadata.get('id')!=identifier or metadata.get('project_id')!=p.id:
        raise ValueError('This canvas reference belongs to a different project or format.')
    if 'display_context' in metadata:
        context=canvas_layer_context.validate(p,metadata['display_context'],metadata['design_version'],metadata['view'])
        if canvas_layer_context.digest(context)!=metadata.get('display_context_sha256'):raise ValueError('The frozen layer context changed after capture. Start Markup again.')
    elif metadata.get('display_context_sha256') is not None:raise ValueError('The frozen layer context is missing.')
    if image.stat().st_size>MAX_BYTES:raise ValueError('The canvas reference image is too large.')
    data=image.read_bytes()
    if hashlib.sha256(data).hexdigest()!=metadata.get('sha256') or len(data)!=metadata.get('bytes'):
        raise ValueError('The canvas reference image changed after capture. Start Markup again.')
    _png(data,metadata.get('width'),metadata.get('height'))
    with p.lock:
        if current and ((p.state.get('workbench') or {}).get('version',0)!=metadata.get('design_version') or design_identity.legacy_fingerprint(p.state.get('spec'))!=metadata.get('design_sha256')):
            raise StaleCanvasReference('The saved design changed. Start Markup again on the current design.')
    return _public(p,metadata)


def validate_for_send(p,reference):
    if reference is None:return None
    if config.load()['ai'].get('vision','auto')=='off':raise ValueError('Enable image input before sending a marked canvas.')
    actual=resolve(p,reference['id'] if isinstance(reference,dict) else reference)
    if isinstance(reference,dict):_same_reference(actual,reference)
    return actual


def recent(p,primary=None):
    """Keep actual recent image history in the CLI's otherwise ephemeral conversation."""
    references={}
    if config.load()['ai'].get('vision','auto')!='off':
        for event in getattr(p,'events',[]):
            ref=event.get('canvas_reference')
            if isinstance(ref,dict) and ref.get('project_id')==p.id:
                references.pop(ref['id'],None);references[ref['id']]=ref
    if primary:references.pop(primary['id'],None);references[primary['id']]=primary
    return list(references.values())[-MAX_CONTEXT_IMAGES:]


def stage(p,references,job):
    """Revalidate bytes and materialize exact CLI image inputs, even after Agent design edits."""
    rows=[]
    for reference in references:
        actual=resolve(p,reference['id'],current=False)
        _same_reference(actual,reference)
        data=(p.root/actual['path']).read_bytes()
        if hashlib.sha256(data).hexdigest()!=actual['sha256']:raise ValueError('The canvas reference changed while it was read.')
        target=job/f'canvas-{actual["id"]}-{actual["sha256"][:12]}.png';target.write_bytes(data)
        rows.append({**actual,'input_path':str(target)})
    (job/'canvas-images.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2))
    return rows


def provider_image(p,reference):
    actual=resolve(p,reference['id'],current=False)
    _same_reference(actual,reference)
    data=(p.root/actual['path']).read_bytes()
    if hashlib.sha256(data).hexdigest()!=actual['sha256']:raise ValueError('The canvas reference changed while it was read.')
    label=f'User-marked {actual["view"]} pixel reference, saved design v{actual["design_version"]}; SHA256 {actual["sha256"]}. Not current engineering proof.\n'+canvas_layer_context.label(actual)
    return {'media_type':'image/png','data':base64.b64encode(data).decode(),'label':label}


def _same_reference(actual,reference):
    if any(actual.get(key)!=reference.get(key) for key in ('sha256','display_context_sha256')):raise ValueError('The canvas reference identity or frozen layer context changed.')


def submit_once(p,request_id,payload,submit):
    """At-most-once acceptance for a retried send; interrupted receipts are never auto-replayed."""
    if request_id is None:return submit()
    if not isinstance(request_id,str) or not re.fullmatch(r'[0-9a-f]{32}',request_id):raise ValueError('Use a valid message request identifier.')
    encoded=json.dumps(payload,sort_keys=True,ensure_ascii=False,allow_nan=False).encode()
    if len(encoded)>1_000_000:raise ValueError('This message request is too large.')
    fingerprint=hashlib.sha256(encoded).hexdigest()
    with p.lock:
        folder=_folder(p)/'submissions'
        if folder.is_symlink() or not folder.resolve().is_relative_to(p.root.resolve()):raise ValueError('The message receipt folder must belong to this project.')
        folder.mkdir(parents=True,exist_ok=True);path=folder/(request_id+'.json')
        if path.exists():
            if path.is_symlink() or path.stat().st_size>16_000:raise ValueError('The previous message receipt is invalid.')
            try:record=json.loads(path.read_text())
            except (OSError,ValueError) as error:raise ValueError('The previous send was interrupted. Check the conversation before explicitly sending again.') from error
            if record.get('fingerprint')!=fingerprint:raise ValueError('This message identifier was already used for a different request.')
            if record.get('state')!='accepted':raise ValueError('The previous send was interrupted. Check the conversation before explicitly sending again.')
            return {**record['result'],'replayed':True}
        record={'fingerprint':fingerprint,'state':'pending'}
        with path.open('x') as output:json.dump(record,output)
        effects_started=False
        def mark_started():
            nonlocal effects_started
            effects_started=True
        try:result=submit(mark_started)
        except Exception:
            if not effects_started:path.unlink(missing_ok=True)
            raise
        record.update(state='accepted',result={**result,'request_id':request_id})
        from .workbench import _atomic_text
        _atomic_text(path,json.dumps(record))
        return {**record['result'],'replayed':False}
