#!/usr/bin/env python3
"""Isolated browser fixture. Never a real model, credential, or visual-recognition receipt."""
import json
import re
import sys
import time
from pathlib import Path

args=sys.argv[1:]
if args[:2]==['login','status']:
    print('Fixture authentication only; no account used.');sys.exit(0)
if args==['--version']:
    print('codex deterministic test fixture');sys.exit(0)
if not args or args[0]!='exec':sys.exit(1)
prompt=sys.stdin.read();context=json.loads(prompt.split('PROJECT CONTEXT (reference data):\n',1)[1].split('\n\nUSER REQUEST:',1)[0]);request=prompt.split('\n\nUSER REQUEST:',1)[1];spec=context['design'];turn=int(re.search(r'Review tool turn (\d+)',prompt)[1]);result={'message':'Deterministic CLI fixture; no model or vision acceptance.','design_json':None,'files':[],'review':[],'tools':[]}
if 'TEST_DELAY' in request:time.sleep(.5)
if 'TEST_AI_MOVE_R1' in request or 'TEST_AI_MOVE_TWICE' in request or 'TEST_AI_MIXED_FILES' in request:
    spec['editor']['positions']['R1'][0]+=50 if 'TEST_AI_MOVE_TWICE' in request else 100;result['design_json']=json.dumps(spec)
    if 'TEST_AI_MOVE_TWICE' in request and turn==1:result['tools']=[{'name':'validate_design','arguments_json':'{}'}]
    if 'TEST_AI_MIXED_FILES' in request:result['files']=[{'path':'docs/fixture-note.md','content':'Fixture-only AI file change.\n'}]
if 'TEST_AI_FILE_BUNDLE' in request or 'TEST_AI_FILES_ONLY' in request:
    if 'TEST_AI_FILE_BUNDLE' in request:
        spec['editor']['positions']['R1'][0]+=100;result['design_json']=json.dumps(spec)
    result['files']=[{'path':'docs/notes.md','content':'# Notes\nReviewed text\n<img src=x onerror="window.aiDiffInjected=true">\n'},
                     {'path':'firmware/main.c','content':'int main(void) { return 0; }\n'}]
output=Path(args[args.index('--output-last-message')+1]);output.write_text(json.dumps(result));print(json.dumps({'type':'item.completed','item':{'type':'agent_message','text':json.dumps(result)}}))
