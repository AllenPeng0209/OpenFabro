"""Marked viewport images are immutable project/version-owned AI input, never design edits."""
import base64
import copy
import hashlib
import io
import json
import time
from pathlib import Path
import pytest
from PIL import Image
from wholeboard import server, codex_bridge
from test_workbench import client
from test_parametric_symbols import fixture


def png(width=64,height=48):
    image=Image.new('RGBA',(width,height),'#101010');image.putpixel((10,10),(255,90,90,255));stream=io.BytesIO();image.save(stream,format='PNG');return stream.getvalue()


def body(**patch):
    return {'base_version':1,'view':'schematic','sheet':'','width':64,'height':48,'strokes':1,'data':base64.b64encode(png()).decode(),**patch}


def make(client,title='Canvas reference'):
    spec=fixture();pid=client.post('/api/workbench/projects',json={'title':title,'spec':spec}).json()['id'];return pid,server.mgr().get(pid)


def test_upload_is_real_png_with_frozen_provenance_and_no_design_mutation(client):
    pid,p=make(client);before=copy.deepcopy(p.state['spec']);snapshot=p.root/'history/design-v1.json';identity=(snapshot.read_bytes(),snapshot.stat().st_mtime_ns)
    response=client.post(f'/api/workbench/projects/{pid}/canvas-reference',json=body());assert response.status_code==201,response.text
    ref=response.json();assert ref['project_id']==pid and ref['design_version']==1 and ref['view']=='schematic';assert ref['width']==64 and ref['height']==48 and ref['strokes']==1
    assert ref['sha256']==hashlib.sha256(png()).hexdigest();assert client.get(ref['url']).content==png()
    assert p.state['spec']==before and p.state['workbench']['version']==1 and (snapshot.read_bytes(),snapshot.stat().st_mtime_ns)==identity
    assert client.put(f'/api/workbench/projects/{pid}/text/references/canvas/{ref["id"]}.json',json={'content':'{}'}).status_code==422
    with pytest.raises(ValueError):codex_bridge.apply_result(p,{'message':'','files':[{'path':f'references/canvas/{ref["id"]}.json','content':'{}'}]},'agent',1)


@pytest.mark.parametrize('patch',[{'view':'files'},{'base_version':True},{'width':65},{'height':0},{'strokes':-1},{'strokes':501},{'sheet':'x'*301},{'data':'https://invalid/image.png'},{'data':base64.b64encode(png()[:-12]).decode()},{'data':base64.b64encode(b'<svg/>').decode()}])
def test_invalid_capture_is_rejected_without_artifacts_or_spec_changes(client,patch):
    pid,p=make(client);before=copy.deepcopy(p.state['spec']);response=client.post(f'/api/workbench/projects/{pid}/canvas-reference',json=body(**patch));assert response.status_code==422,response.text
    assert p.state['spec']==before and p.state['workbench']['version']==1
    assert not list((p.root/'references').rglob('*.png'))


def test_stale_capture_and_cross_project_reference_cannot_be_sent(client,monkeypatch):
    a,p=make(client);b,_=make(client,'Other capture owner');ref=client.post(f'/api/workbench/projects/{a}/canvas-reference',json=body()).json();calls=[]
    monkeypatch.setattr(codex_bridge,'start',lambda *args,**kwargs:calls.append((args,kwargs)))
    assert client.post(f'/api/workbench/projects/{b}/codex',json={'text':'Review','mode':'chat','canvas_ref':ref['id']}).status_code==409
    changed=copy.deepcopy(p.state['spec']);changed['board']['width_mm']=41;client.put(f'/api/workbench/projects/{a}/design',json={'base_version':1,'spec':changed})
    assert client.post(f'/api/workbench/projects/{a}/canvas-reference',json=body()).status_code==409
    assert client.post(f'/api/workbench/projects/{a}/codex',json={'text':'Review','mode':'chat','canvas_ref':ref['id']}).status_code==409
    assert calls==[]


def test_send_resolves_real_reference_and_rejects_modified_image(client,monkeypatch):
    pid,p=make(client);ref=client.post(f'/api/workbench/projects/{pid}/canvas-reference',json=body()).json();calls=[]
    monkeypatch.setattr(codex_bridge,'start',lambda *args,**kwargs:calls.append((args,kwargs)))
    response=client.post(f'/api/workbench/projects/{pid}/codex',json={'text':'What is circled?','mode':'chat','canvas_ref':ref['id']});assert response.status_code==200,response.text
    assert calls[0][1]['canvas_reference']['sha256']==ref['sha256']
    (p.root/ref['path']).write_bytes(png()+b'changed')
    assert client.post(f'/api/workbench/projects/{pid}/codex',json={'text':'Read changed file','canvas_ref':ref['id']}).status_code==409
    assert len(calls)==1 and p.state['workbench']['version']==1


def test_codex_cli_receives_a_staged_verified_png_not_only_text(client,monkeypatch,tmp_path):
    from wholeboard import canvas_references
    pid,p=make(client);ref=canvas_references.create(p,body());commands=[]
    result={'message':'Saw the reference','design_json':None,'files':[],'review':[],'tools':[]}
    class Input(io.StringIO):
        def close(self):self.sent=self.getvalue()
    class Process:
        pid=123456
        def __init__(self,command,**kwargs):commands.append(command);self.stdin=Input();self.stdout=io.StringIO(json.dumps({'type':'item.completed','item':{'type':'agent_message','text':json.dumps(result)}})+'\n')
        def poll(self):return 0
        def wait(self,**kwargs):return 0
    monkeypatch.setattr(codex_bridge,'command_for',lambda job,root:['codex','exec','-'])
    monkeypatch.setattr(codex_bridge.subprocess,'Popen',Process)
    job=p.root/'.codex-runs'/'image-test'/'1'
    assert codex_bridge.request_once(p,'Review the marked viewport',job,time.monotonic()+5,canvas_references=[ref])==result
    paths=[Path(commands[0][i+1]) for i,value in enumerate(commands[0]) if value=='--image'];assert len(paths)==1 and paths[0].is_relative_to(job)
    assert paths[0].read_bytes()==png();manifest=json.loads((job/'canvas-images.json').read_text());assert manifest[0]['sha256']==ref['sha256'] and manifest[0]['design_version']==1
    assert p.state['workbench']['version']==1


def test_reference_metadata_is_image_context_not_current_engineering_proof(client):
    from wholeboard import canvas_references
    _,p=make(client);ref=canvas_references.create(p,body());prompt=codex_bridge.prompt_for(p,'Explain my mark','chat',canvas_references=[ref])
    assert ref['sha256'] in prompt and 'canvas_references' in prompt and 'pixel' in prompt.lower()
    assert 'reference' in prompt.lower() and p.state['workbench']['version']==1


def test_retried_visual_send_is_idempotent_and_changed_payload_is_rejected(client,monkeypatch):
    pid,p=make(client);ref=client.post(f'/api/workbench/projects/{pid}/canvas-reference',json=body()).json();calls=[]
    monkeypatch.setattr(codex_bridge,'start',lambda *args,**kwargs:calls.append((args,kwargs)))
    payload={'text':'Explain this mark','mode':'chat','canvas_ref':ref['id'],'request_id':'a'*32}
    first=client.post(f'/api/workbench/projects/{pid}/codex',json=payload);second=client.post(f'/api/workbench/projects/{pid}/codex',json=payload)
    assert first.status_code==second.status_code==200 and second.json()['replayed'] is True
    assert len(calls)==1
    assert client.post(f'/api/workbench/projects/{pid}/codex',json={**payload,'text':'A different message'}).status_code==409
    assert len(calls)==1


def test_provider_delivery_rejects_changed_metadata_and_bytes_after_acceptance(client):
    from wholeboard import canvas_references
    _,p=make(client);ref=canvas_references.create(p,body());other=io.BytesIO();Image.new('RGBA',(64,48),'blue').save(other,format='PNG');data=other.getvalue()
    (p.root/ref['path']).write_bytes(data);meta_path=p.root/'references/canvas'/f'{ref["id"]}.json';meta=json.loads(meta_path.read_text());meta['sha256']=hashlib.sha256(data).hexdigest();meta['bytes']=len(data);meta_path.write_text(json.dumps(meta))
    with pytest.raises(ValueError):canvas_references.provider_image(p,ref)


def test_capture_retry_reuses_the_same_immutable_image_id(client):
    pid,p=make(client);payload=body(capture_id='b'*32)
    first=client.post(f'/api/workbench/projects/{pid}/canvas-reference',json=payload).json();second=client.post(f'/api/workbench/projects/{pid}/canvas-reference',json=payload).json()
    assert first['id']==second['id']=='b'*32 and first['sha256']==second['sha256']
    assert len(list((p.root/'references/canvas').glob('*.png')))==1


def test_recent_cli_image_history_is_bounded_and_never_crosses_projects(client,monkeypatch):
    from wholeboard import canvas_references,config
    _,p=make(client);refs=[]
    for _ in range(7):
        ref=canvas_references.create(p,body());refs.append(ref);p.chat('user','Read this image',canvas_reference=ref)
    _,other=make(client,'Other image history');p.chat('user','Foreign event must not become an image input',canvas_reference=canvas_references.create(other,body()))
    assert [r['id'] for r in canvas_references.recent(p)]==[r['id'] for r in refs[-5:]]
    cfg=config.load();cfg['ai']['vision']='off';monkeypatch.setattr(config,'load',lambda:cfg)
    assert canvas_references.recent(p)==[]


def test_capture_retry_recovers_png_written_before_metadata_failure(client,monkeypatch):
    from wholeboard import canvas_references
    _,p=make(client);payload=body(capture_id='d'*32);original=Path.open
    def fail_metadata(path,*args,**kwargs):
        if path.name=='d'*32+'.json' and args and args[0]=='x':raise OSError('Injected metadata write failure')
        return original(path,*args,**kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(Path,'open',fail_metadata)
        with pytest.raises(OSError):canvas_references.create(p,payload)
    image=p.root/'references/canvas'/('d'*32+'.png');mtime=image.stat().st_mtime_ns
    recovered=canvas_references.create(p,payload)
    assert recovered['sha256']==hashlib.sha256(png()).hexdigest() and image.stat().st_mtime_ns==mtime
    assert p.state['workbench']['version']==1


def test_send_failure_after_observable_effect_is_not_automatically_replayed(client,monkeypatch):
    pid,p=make(client);ref=client.post(f'/api/workbench/projects/{pid}/canvas-reference',json=body()).json();calls=[]
    def partial_start(*args,**kwargs):calls.append('observable effect');raise OSError('Injected failure after start boundary')
    monkeypatch.setattr(codex_bridge,'start',partial_start);payload={'text':'Read this image','mode':'chat','canvas_ref':ref['id'],'request_id':'e'*32}
    with pytest.raises(OSError):client.post(f'/api/workbench/projects/{pid}/codex',json=payload)
    monkeypatch.setattr(codex_bridge,'start',lambda *args,**kwargs:calls.append('duplicate effect'))
    response=client.post(f'/api/workbench/projects/{pid}/codex',json=payload)
    assert response.status_code==409 and 'interrupted' in response.text and calls==['observable effect']
