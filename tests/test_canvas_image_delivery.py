"""Image payload delivery and queued-reference ownership without remote model calls."""
import base64
import threading
import pytest
from wholeboard import canvas_references, codex_bridge, config, server
from wholeboard.ai.providers import AnthropicSession,OpenAISession,AIError
from test_workbench import client
from test_canvas_references import make,body,png
from test_collaboration import workspace,account,login


@pytest.mark.parametrize('session_type',[AnthropicSession,OpenAISession])
def test_provider_user_message_contains_real_image_bytes(session_type):
    session=object.__new__(session_type);session.messages=[]
    image={'media_type':'image/png','data':base64.b64encode(png()).decode(),'label':'Marked schematic v1'}
    session.add_user('What is circled?',images=[image]);message=session.messages[-1]
    assert message['role']=='user' and isinstance(message['content'],list)
    parts=message['content'];assert any(part.get('text')=='What is circled?' for part in parts)
    if session_type is AnthropicSession:assert next(p for p in parts if p['type']=='image')['source']['data']==image['data']
    else:assert next(p for p in parts if p['type']=='image_url')['image_url']['url']=='data:image/png;base64,'+image['data']


def test_openai_compatible_fallback_cannot_pretend_an_unseen_user_image_was_read():
    session=object.__new__(OpenAISession);session.messages=[];session.vision_failed=False
    session.add_user('Read this mark',images=[{'media_type':'image/png','data':base64.b64encode(png()).decode(),'label':'User reference'}])
    with pytest.raises(AIError,match='image'):session._drop_images()
    # A successful assistant turn establishes delivery; later history shrinking may explicitly omit it.
    session.messages.append({'role':'assistant','content':'I received the marked reference.'})
    assert session._drop_images()
    assert 'Read this mark' in session.messages[0]['content'],'Removing an old image must retain the actual user request'


def test_shortening_old_visual_history_keeps_the_user_question():
    session=object.__new__(OpenAISession);session.messages=[]
    session.add_user('Explain the capacitor I circled',images=[{'media_type':'image/png','data':base64.b64encode(png()).decode(),'label':'Marked saved-v1 reference'}])
    message=session.messages[0];session._shorten(message)
    assert 'Explain the capacitor I circled' in message['content'] and 'removed' in message['content']


def test_codex_start_binds_reference_to_run_and_visible_user_message(client,monkeypatch):
    _,p=make(client);ref=canvas_references.create(p,body());received=[];done=threading.Event()
    monkeypatch.setattr(codex_bridge,'status',lambda:{'ready':True})
    def run(project,text,mode,canvas_reference=None):received.append((text,mode,canvas_reference));done.set()
    monkeypatch.setattr(codex_bridge,'run',run)
    codex_bridge.start(p,'Explain the circle','chat',canvas_reference=ref);assert done.wait(3);p.worker.join(3)
    assert received[0][2]['sha256']==ref['sha256']
    event=next(event for event in p.events if event.get('role')=='user');assert event['canvas_reference']['id']==ref['id'] and 'data' not in event['canvas_reference']
    assert p.state['workbench']['version']==1


def test_vision_off_rejects_before_starting_or_queueing_a_model_job(client,monkeypatch):
    pid,p=make(client);ref=canvas_references.create(p,body());cfg=config.load();cfg['ai']['vision']='off'
    monkeypatch.setattr(config,'load',lambda:cfg);monkeypatch.setattr(codex_bridge,'status',lambda:{'ready':True})
    response=client.post(f'/api/workbench/projects/{pid}/codex',json={'text':'Read this image','mode':'chat','canvas_ref':ref['id']})
    assert response.status_code==409 and 'image' in response.text.lower() and p.worker is None


def test_queued_markup_stays_with_its_message_and_plain_messages_stay_compatible(client):
    pid,p=make(client);ref=canvas_references.create(p,body())
    class Working:
        def is_alive(self):return True
    p.worker=Working();p.state['status']='running'
    try:
        response=client.post(f'/api/workbench/projects/{pid}/steer',json={'text':'Use this new mark','canvas_ref':ref['id']});assert response.status_code==200,response.text
        assert p.inbox[0]['text']=='Use this new mark' and p.inbox[0]['canvas_reference']['sha256']==ref['sha256']
        assert client.post(f'/api/workbench/projects/{pid}/steer',json={'text':'Also explain the connector'}).status_code==200
        assert p.inbox[1]=='Also explain the connector'
    finally:p.worker=None


def test_generic_agent_initial_message_receives_the_actual_image(client,monkeypatch):
    from wholeboard.ai.agent import Agent
    _,p=make(client);ref=canvas_references.create(p,body());messages=[]
    class Session:
        label='Image delivery probe'
        def add_user(self,text,**kwargs):messages.append((text,kwargs))
    agent=Agent(p);monkeypatch.setattr(agent,'_new_session',lambda:Session());monkeypatch.setattr(agent,'_loop',lambda:None)
    agent._run('Explain this mark',canvas_reference=ref)
    assert messages[-1][1]['images'][0]['data']==base64.b64encode(png()).decode()
    assert p.state['workbench']['version']==1


def test_image_answer_reaches_generic_tool_result_and_is_not_reduced_to_text(client):
    from wholeboard.ai.agent import Agent
    pid,p=make(client);ref=canvas_references.create(p,body());ready=threading.Event();results=[]
    p.listeners.append(lambda event:ready.set() if event.get('type')=='status' and event.get('status')=='waiting' else None)
    thread=threading.Thread(target=lambda:results.append(Agent(p)._ask('Which component?',[])));thread.start()
    assert ready.wait(3);question=next(e for e in p.events if e.get('type')=='question')
    try:
        response=client.post(f'/api/projects/{pid}/answer',json={'id':question['id'],'text':'This circled one','canvas_ref':ref['id'],'request_id':'c'*32});assert response.status_code==200,response.text
    finally:
        p.cancel.set()
        with p.answer_ready:p.answer_ready.notify_all()
        thread.join(3)
    assert results[0]['images'][0]['data']==base64.b64encode(png()).decode() and results[0]['require_images'] is True


def test_shared_viewer_can_read_but_cannot_create_or_submit_canvas_references(workspace):
    from fastapi.testclient import TestClient
    owner,_,project=workspace;remote=TestClient(server.app,client=('192.0.2.77',5000));member=account(owner);owner.put(f'/api/workbench/projects/{project["id"]}/members/{member["id"]}',json={'role':'viewer'});login(remote)
    ref=owner.post(f'/api/workbench/projects/{project["id"]}/canvas-reference',json=body()).json()
    assert remote.get(ref['url']).status_code==200
    assert remote.post(f'/api/workbench/projects/{project["id"]}/canvas-reference',json=body()).status_code==403
    assert remote.post(f'/api/workbench/projects/{project["id"]}/codex',json={'text':'Read image','canvas_ref':ref['id']}).status_code==403


def test_queued_chat_mode_is_enforced_before_applying_an_agent_proposal(client,monkeypatch):
    import copy,json
    _,p=make(client);ref=canvas_references.create(p,body());before=copy.deepcopy(p.state['spec']);changed=copy.deepcopy(before);changed['board']['width_mm']=41
    p.inbox=[{'text':'Discuss this image only','mode':'chat','canvas_reference':ref}];prompts=[]
    def request(project,prompt,job,deadline,**kwargs):
        prompts.append(prompt);assert kwargs['canvas_references'][0]['sha256']==ref['sha256']
        return {'message':'Review only','design_json':json.dumps(changed),'files':[{'path':'must-not-write.md','content':'No'}],'review':[],'tools':[]}
    monkeypatch.setattr(codex_bridge,'request_once',request);codex_bridge.run(p,'Earlier editing request','agent')
    assert 'CHAT MODE:' in prompts[0] and p.state['spec']==before and p.state['workbench']['version']==1 and not (p.root/'must-not-write.md').exists()


def test_provider_chat_mode_blocks_mutating_tools_before_they_run(client,monkeypatch):
    from wholeboard.ai.agent import Agent
    from wholeboard import pipeline
    calls=[];monkeypatch.setattr(pipeline,'build',lambda *args,**kwargs:calls.append('build') or {'ok':False})
    _,p=make(client);agent=Agent(p);agent.mode='chat'
    for name,args in [('submit_design',{'spec':p.state['spec']}),('build_enclosure',{}),('simulate',{'spec':p.state['spec']})]:
        with pytest.raises(ValueError,match='Chat'):agent._execute(name,args)
    assert p.state['workbench']['version']==1
    assert calls==[]
