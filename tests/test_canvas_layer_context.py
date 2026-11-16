"""A marked PCB image keeps capture-time layer semantics through every AI delivery path."""
import copy
import hashlib
import json
from pathlib import Path

import pytest

from wholeboard import canvas_references, codex_bridge
from wholeboard.ai.providers import AnthropicSession, OpenAISession
from test_workbench import client
from test_canvas_references import make, body, png


def context(client, pid):
    response=client.get(f'/api/workbench/projects/{pid}/layout-geometry')
    assert response.status_code==200,response.text
    native=response.json()
    return {'schema':1,'project_id':pid,'design_version':1,'view':'layout',
            'native':{key:native[key] for key in ('source_version','pcb_sha256','render_inputs_sha256')},
            'focus':'F.Mask','dim_opacity':0.2,
            'layers':{'F.Cu':{'visible':True,'features':{'fills':True,'polygons':True,'pads':True,'traces':False,'vias':True}},
                      'B.Cu':{'visible':True,'features':{'fills':True,'polygons':True,'pads':True,'traces':True,'vias':True}},
                      'F.Mask':{'visible':True},'B.Mask':{'visible':False},'F.Paste':{'visible':False},'B.Paste':{'visible':False}},
            'display':{'grid':False,'ratsnest':True,'refs':True,'zoneOutlines':True,'pads':True,'vias':True,'zones':True,'outline':True,'courtyards':False},
            'hidden_objects':{},
            'apertures':[{'layer':layer,'status':'loading' if layer=='F.Mask' else 'hidden'}
                         for layer in ('F.Mask','B.Mask','F.Paste','B.Paste')]}


def test_real_native_aperture_context_is_immutable_and_delivered_with_the_exact_png(client,tmp_path):
    pid,p=make(client);frozen=context(client,pid)
    preview=client.post(f'/api/workbench/projects/{pid}/layer-preview',json={'layer':'F.Mask'}).json()
    frozen['apertures'][0]={'layer':'F.Mask','status':'ready','client_path_count':2,
                          **{key:preview[key] for key in ('svg_sha256','visibility_sha256')}}
    original=copy.deepcopy(frozen);before=copy.deepcopy(p.state['spec'])
    ref=canvas_references.create(p,body(view='layout',display_context=frozen,capture_id='1'*32))
    assert ref.get('display_context')==original,'The upload discarded capture-time native layer semantics'
    frozen['focus']='B.Cu';frozen['apertures'][0]['status']='hidden'
    p.chat('user','Explain the marked image',canvas_reference=ref)
    stored=canvas_references.resolve(p,ref['id']);assert stored['display_context']==original
    assert len(stored['display_context_sha256'])==64
    job=tmp_path/'delivery';job.mkdir();staged=canvas_references.stage(p,canvas_references.recent(p),job)
    assert staged[0]['display_context']==original and Path(staged[0]['input_path']).read_bytes()==png()
    assert json.loads((job/'canvas-images.json').read_text())[0]['display_context']==original
    image=canvas_references.provider_image(p,ref)
    for session_type in (AnthropicSession,OpenAISession):
        session=object.__new__(session_type);session.messages=[];session.add_user('Explain my mark',images=[image])
        text='\n'.join(part.get('text','') for part in session.messages[-1]['content'])
        assert 'F.Mask' in text and original['native']['pcb_sha256'] in text and preview['svg_sha256'] in text
    prompt=codex_bridge.prompt_for(p,'Review','chat',canvas_references=[stored])
    assert 'display_context' in prompt and preview['svg_sha256'] in prompt
    assert p.state['spec']==before and p.state['workbench']['version']==1


def test_same_png_capture_id_cannot_be_relabelled_with_different_layers(client):
    pid,p=make(client);frozen=context(client,pid);payload=body(view='layout',display_context=frozen,capture_id='2'*32)
    first=canvas_references.create(p,payload);original=(p.root/'references/canvas'/('2'*32+'.json')).read_bytes()
    assert canvas_references.create(p,payload)['id']==first['id']
    changed=copy.deepcopy(payload);changed['display_context']['focus']='B.Cu'
    with pytest.raises(ValueError):canvas_references.create(p,changed)
    assert (p.root/'references/canvas'/('2'*32+'.json')).read_bytes()==original


@pytest.mark.parametrize('change',[
    lambda c:c.update(project_id='foreign-project'),
    lambda c:c.update(design_version=2),
    lambda c:c.update(view='schematic'),
    lambda c:c['native'].update(pcb_sha256='0'*64),
    lambda c:c['native'].update(render_inputs_sha256='0'*64),
    lambda c:c.update(focus='a'*129),
    lambda c:c['layers']['F.Cu']['features'].update(traces='yes'),
    lambda c:c['layers']['F.Mask'].update(visible='yes'),
    lambda c:c['apertures'][0].update(status='ready'),
    lambda c:c['apertures'][0].update(status='waiting',svg_sha256='a'*64),
    lambda c:c.update(hidden_objects={'footprints':['id'+str(n) for n in range(1000)]}),
    lambda c:c.update(instructions='x'*40000),
])
def test_invalid_or_stale_display_context_creates_no_capture_artifacts(client,change):
    pid,p=make(client);frozen=context(client,pid);change(frozen)
    response=client.post(f'/api/workbench/projects/{pid}/canvas-reference',json=body(view='layout',display_context=frozen))
    assert response.status_code in (409,422),response.text
    assert not list((p.root/'references/canvas').glob('*.png'))
    assert p.state['workbench']['version']==1


def test_loading_aperture_stays_unknown_after_a_later_native_export(client,tmp_path):
    pid,p=make(client);frozen=context(client,pid);ref=canvas_references.create(p,body(view='layout',display_context=frozen))
    assert ref.get('display_context',{}).get('apertures',[{}])[0].get('status')=='loading'
    assert client.post(f'/api/workbench/projects/{pid}/layer-preview',json={'layer':'F.Mask'}).status_code==200
    job=tmp_path/'later';job.mkdir();row=canvas_references.stage(p,[ref],job)[0]
    assert row['display_context']['apertures'][0]=={'layer':'F.Mask','status':'loading'}
    assert 'loading' in canvas_references.provider_image(p,ref)['label']


def test_changed_context_metadata_is_rejected_even_when_png_bytes_are_identical(client,tmp_path):
    pid,p=make(client);ref=canvas_references.create(p,body(view='layout',display_context=context(client,pid)))
    assert 'display_context' in ref
    path=p.root/'references/canvas'/f'{ref["id"]}.json';metadata=json.loads(path.read_text())
    metadata['display_context']['focus']='B.Cu';path.write_text(json.dumps(metadata))
    with pytest.raises(ValueError):canvas_references.resolve(p,ref['id'])
    # Recomputing the on-disk checksum still cannot change an already accepted reference.
    metadata['display_context_sha256']=hashlib.sha256(json.dumps(metadata['display_context'],sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
    path.write_text(json.dumps(metadata));job=tmp_path/'changed';job.mkdir()
    with pytest.raises(ValueError):canvas_references.provider_image(p,ref)
    with pytest.raises(ValueError):canvas_references.stage(p,[ref],job)


def test_older_layout_references_remain_readable_without_invented_layer_evidence(client):
    _,p=make(client);ref=canvas_references.create(p,body(view='layout'))
    assert canvas_references.resolve(p,ref['id'])['sha256']==ref['sha256']
    assert 'display_context' not in ref
    assert 'layer context unavailable' in canvas_references.provider_image(p,ref)['label'].lower()


def test_a_ready_aperture_cannot_claim_an_svg_that_the_native_exporter_never_produced(client):
    pid,p=make(client);frozen=context(client,pid)
    frozen['apertures'][0]={'layer':'F.Mask','status':'ready','client_path_count':2,'svg_sha256':'a'*64,
                          'visibility_sha256':'44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a'}
    with pytest.raises(ValueError):canvas_references.create(p,body(view='layout',display_context=frozen))
    assert not list((p.root/'references/canvas').glob('*.png'))


def test_hidden_objects_must_exist_in_the_displayed_native_pcb(client):
    pid,p=make(client);frozen=context(client,pid);frozen['hidden_objects']={'footprints':['nonexistent-native-id']}
    with pytest.raises(ValueError):canvas_references.create(p,body(view='layout',display_context=frozen))


def test_changed_native_rules_cannot_reuse_the_previous_capture_input_identity(client):
    pid,p=make(client);frozen=context(client,pid);pcb=Path(p.state['workbench_native']['pcb']);pcb.with_suffix('.kicad_dru').write_text('(version 1)\n')
    with pytest.raises(ValueError):canvas_references.create(p,body(view='layout',display_context=frozen))
    assert not list((p.root/'references/canvas').glob('*.png'))


def test_damaged_native_preview_metadata_rejects_capture_without_an_internal_error(client):
    pid,p=make(client);frozen=context(client,pid);preview=client.post(f'/api/workbench/projects/{pid}/layer-preview',json={'layer':'F.Mask'}).json()
    frozen['apertures'][0]={'layer':'F.Mask','status':'ready','client_path_count':2,
                          **{key:preview[key] for key in ('svg_sha256','visibility_sha256')}}
    metadata=next((Path(p.state['workbench_native']['pcb']).parent/'display-layers').rglob('metadata.json'));metadata.write_text('[]')
    response=client.post(f'/api/workbench/projects/{pid}/canvas-reference',json=body(view='layout',display_context=frozen))
    assert response.status_code==422,response.text
    assert not list((p.root/'references/canvas').glob('*.png'))


def test_compiled_drawable_count_is_explicitly_client_reported_not_an_authenticated_native_count(client):
    pid,p=make(client);frozen=context(client,pid);preview=client.post(f'/api/workbench/projects/{pid}/layer-preview',json={'layer':'F.Mask'}).json()
    frozen['apertures'][0]={'layer':'F.Mask','status':'ready','client_path_count':999,
                          **{key:preview[key] for key in ('svg_sha256','visibility_sha256')}}
    ref=canvas_references.create(p,body(view='layout',display_context=frozen))
    label=canvas_references.provider_image(p,ref)['label'].lower()
    assert 'client-reported' in label and 'not an authenticated native object count' in label


def test_legacy_ready_path_count_context_preserves_original_digest_and_bytes(client,tmp_path):
    pid,p=make(client);frozen=context(client,pid);preview=client.post(f'/api/workbench/projects/{pid}/layer-preview',json={'layer':'F.Mask'}).json()
    frozen['apertures'][0]={'layer':'F.Mask','status':'ready','path_count':2,**{key:preview[key] for key in ('svg_sha256','visibility_sha256')}}
    ref=canvas_references.create(p,body(view='layout'));meta_path=p.root/'references/canvas'/f'{ref["id"]}.json';meta=json.loads(meta_path.read_text());meta.update(display_context=frozen,display_context_sha256=hashlib.sha256(json.dumps(frozen,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest());meta_path.write_text(json.dumps(meta));before=(meta_path.read_bytes(),meta_path.stat().st_mtime_ns)
    actual=canvas_references.resolve(p,ref['id']);assert actual['display_context']==frozen and actual['display_context_sha256']==meta['display_context_sha256']
    job=tmp_path/'legacy';job.mkdir();assert canvas_references.stage(p,[actual],job)[0]['display_context']==frozen
    assert 'legacy path_count' in canvas_references.provider_image(p,actual)['label']
    assert (meta_path.read_bytes(),meta_path.stat().st_mtime_ns)==before
    assert canvas_references.create(p,body(view='layout',capture_id=ref['id'],display_context=frozen))['display_context_sha256']==meta['display_context_sha256']
    changed=copy.deepcopy(frozen);changed['apertures'][0]['client_path_count']=changed['apertures'][0].pop('path_count')
    with pytest.raises(ValueError):canvas_references.create(p,body(view='layout',capture_id=ref['id'],display_context=changed))


@pytest.mark.parametrize('target',['folder','svg'])
def test_export_cleanup_race_rejects_capture_without_a_server_error(client,monkeypatch,target):
    pid,p=make(client);frozen=context(client,pid);preview=client.post(f'/api/workbench/projects/{pid}/layer-preview',json={'layer':'F.Mask'}).json()
    frozen['apertures'][0]={'layer':'F.Mask','status':'ready','client_path_count':2,**{key:preview[key] for key in ('svg_sha256','visibility_sha256')}}
    svg=next((Path(p.state['workbench_native']['pcb']).parent/'display-layers').rglob('layer.svg'));victim=svg if target=='svg' else svg.parent;original=Path.stat
    def removed(path,*args,**kwargs):
        if path==victim:raise OSError('Injected concurrent preview-cache cleanup')
        return original(path,*args,**kwargs)
    monkeypatch.setattr(Path,'stat',removed)
    response=client.post(f'/api/workbench/projects/{pid}/canvas-reference',json=body(view='layout',display_context=frozen));assert response.status_code==422,response.text
