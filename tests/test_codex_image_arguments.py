"""Exercise the actual installed CLI's offline image parser with request_once's argv."""
import io
import json
import subprocess
import time

import pytest

from wholeboard import canvas_references,codex_bridge
from test_workbench import client
from test_canvas_references import make,body,png


@pytest.mark.parametrize('user_images,build_images',[(1,0),(0,2),(2,2),(0,0)])
def test_stdin_prompt_is_not_consumed_as_an_extra_image(client,monkeypatch,tmp_path,user_images,build_images):
    cli=codex_bridge.find_cli()
    if not cli:pytest.skip('Offline Codex parser is not installed.')
    _,p=make(client);refs=[canvas_references.create(p,body()) for _ in range(user_images)]
    if build_images:
        folder=p.root/'rev0';folder.mkdir();(folder/'render-iso.png').write_bytes(png());(folder/'render-top.png').write_bytes(png())
    commands=[];result={'message':'Parser probe only','design_json':None,'files':[],'tools':[],'review':[]}
    class Input(io.StringIO):
        def close(self):self.sent=self.getvalue()
    class Process:
        pid=123456
        def __init__(self,command,**kwargs):commands.append(command);self.stdin=Input();self.stdout=io.StringIO(json.dumps({'type':'item.completed','item':{'type':'agent_message','text':json.dumps(result)}})+'\n')
        def poll(self):return 0
        def wait(self,**kwargs):return 0
    with monkeypatch.context() as patch:
        patch.setattr(codex_bridge,'command_for',lambda job,root:[cli,'exec','-'])
        patch.setattr(codex_bridge.subprocess,'Popen',Process)
        codex_bridge.request_once(p,'Offline input probe',tmp_path/'job',time.monotonic()+5,canvas_references=refs)
    command=commands[0];tail=command[command.index('--image'):] if '--image' in command else ['-']
    parsed=subprocess.run([cli,'debug','prompt-input',*tail],cwd=tmp_path,capture_output=True,text=True,timeout=30)
    assert parsed.returncode==0,parsed.stderr[-500:]
    data=json.loads(parsed.stdout);images=[];diagnostics=[]
    def walk(value):
        if isinstance(value,dict):
            if value.get('type')=='input_image':images.append(value)
            if isinstance(value.get('text'),str) and 'could not read the local image' in value['text']:diagnostics.append(value['text'])
            for v in value.values():walk(v)
        elif isinstance(value,list):
            for v in value:walk(v)
    walk(data)
    assert len(images)==user_images+build_images
    assert not diagnostics,diagnostics
