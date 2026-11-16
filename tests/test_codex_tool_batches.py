"""The in-app agent must execute every accepted action, or explicitly reject the batch."""
import copy
import json

from wholeboard import codex_bridge,server
from test_workbench import client


def proposal(tools=(),**fields):
 return {'message':'Reviewing actual files','design_json':None,'files':[],'review':[],'tools':list(tools),**fields}


def test_eight_requested_file_reads_all_execute_and_reach_the_next_model_turn(client,monkeypatch):
 pid=client.post('/api/workbench/projects',json={'title':'Complete agent batch'}).json()['id'];p=server.mgr().get(pid);docs=p.root/'docs';docs.mkdir()
 calls=[]
 for i in range(8):
  (docs/f'part-{i}.txt').write_text(f'Unique actual evidence {i}')
  calls.append({'name':'read_file','arguments_json':json.dumps({'path':f'docs/part-{i}.txt'})})
 prompts=[]
 def infer(project,prompt,*args,**kwargs):
  prompts.append(prompt);return proposal(calls) if len(prompts)==1 else proposal()
 monkeypatch.setattr(codex_bridge,'request_once',infer);codex_bridge.run(p,'Read all eight evidence chunks','agent')
 records=p.state.get('codex_tool_results',[]);assert len(records)==8,'A tool proposal was silently truncated'
 assert all(f'Unique actual evidence {i}' in prompts[-1] for i in range(8))
 assert p.state['workbench']['version']==1


def test_oversize_tool_batch_is_rejected_before_any_files_or_design_are_applied(client,monkeypatch):
 pid=client.post('/api/workbench/projects',json={'title':'Bounded agent batch'}).json()['id'];p=server.mgr().get(pid);before=copy.deepcopy(p.state['spec']);changed=copy.deepcopy(before);changed['summary']='Should not apply'
 calls=[{'name':'read_file','arguments_json':json.dumps({'path':'design.json'})} for _ in range(17)];prompts=[]
 def infer(project,prompt,*args,**kwargs):
  prompts.append(prompt)
  return proposal(calls,design_json=json.dumps(changed),files=[{'path':'docs/should-not-exist.md','content':'Wrong partial apply'}]) if len(prompts)==1 else proposal()
 monkeypatch.setattr(codex_bridge,'request_once',infer);codex_bridge.run(p,'Review a bounded action batch','agent')
 assert p.state['spec']==before and p.state['workbench']['version']==1
 assert not (p.root/'docs/should-not-exist.md').exists()
 assert '16' in prompts[-1] and 'tool_batch_limit' in prompts[-1]


def test_repeated_inspections_retain_before_after_values_and_actual_call_multiplicity():
 reports=[{'name':'inspect_route_lengths','arguments':{},'result':{'source_version':1,'routes':[{'net':'CLK','length_mm':40.3}]}},{'name':'inspect_route_lengths','arguments':{},'result':{'source_version':3,'routes':[{'net':'CLK','length_mm':55.000266}]}}]
 packed=json.loads(codex_bridge.evidence_context(reports))
 assert [r['result']['source_version'] for r in packed]==[1,3],'The same arguments erased the earlier saved-state evidence'
 reports.append(copy.deepcopy(reports[-1]));packed=json.loads(codex_bridge.evidence_context(reports))
 assert len(packed)==3,'Collapsing identical returns hid an actual repeated call'


def test_bounded_tool_evidence_names_older_executions_that_are_omitted():
 reports=[{'name':'inspect_route_lengths','arguments':{},'result':{'source_version':i}} for i in range(1,101)];packed=json.loads(codex_bridge.evidence_context(reports));coverage=packed[0]['evidence_coverage'];actual=packed[1:]
 assert coverage['total_calls']==100 and coverage['included_calls']==len(actual)
 assert coverage['earlier_calls_omitted']>0 and coverage['earlier_calls_omitted']+len(actual)==100
 assert actual[-1]['result']['source_version']==100


def test_large_native_evidence_retains_model_identity_and_report_for_followup_reads():
 first={'asset_id':'a'*64,'source':'cad/product.cad.json','source_sha256':'b'*64,'files':[{'name':'report.json','path':'mechanical/'+('a'*64)+'/report.json','sha256':'c'*64}],
        'metrics':{'solids':73,'assembly':{'fit':{'complete':True,'pass':False,'pairs':[{'a':'base','b':'lid','overlap_mm3':188.3392,'distance_mm':0}]}},'bodies':[{'face_colors':['#444444']*20000}]*4}}
 reports=[{'name':'build_mechanical_part','result':first},{'name':'read_file','result':{'content':'x'*90000}}]
 before=copy.deepcopy(reports);packed=json.loads(codex_bridge.evidence_context(reports));value=packed[0]['result']
 assert value['details_omitted'] and value['asset_id']==first['asset_id'] and value['source_sha256']==first['source_sha256']
 assert value['native_summary']['fit']['pairs'][0]['overlap_mm3']==188.3392 and value['report']['sha256']=='c'*64
 assert reports==before
