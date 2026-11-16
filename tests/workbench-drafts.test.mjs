import test from 'node:test';
import assert from 'node:assert/strict';
const scope={owner:'alice',pid:'board-1'};
const memory=()=>{const values=new Map();return{values,get length(){return values.size;},key:i=>[...values.keys()][i]??null,getItem:k=>values.get(k)??null,setItem:(k,v)=>values.set(k,String(v)),removeItem:k=>values.delete(k)};};
const api=()=>import('../wholeboard/web/workbench-drafts.mjs');

test('durable file drafts preserve exact local/base text across reload and isolate account/project ownership',async()=>{
 const {DraftJournal}=await api(),storage=memory(),a=new DraftJournal({storage});
 a.put(scope,'docs/外壳.md',{content:'新内容\r\n尾行',base_content:'旧内容\r\n',sha:'a'.repeat(64),base_version:3});
 const b=new DraftJournal({storage}),rows=b.list(scope);assert.equal(rows.length,1);assert.equal(rows[0].content,'新内容\r\n尾行');assert.equal(rows[0].base_content,'旧内容\r\n');
 assert.equal(b.list({...scope,owner:'bob'}).length,0);assert.equal(b.list({...scope,pid:'board-2'}).length,0);
});

test('dismissal and older save completion cannot erase a newer draft from another tab',async()=>{
 const {DraftJournal}=await api(),storage=memory(),a=new DraftJournal({storage}),b=new DraftJournal({storage});
 const first=a.put(scope,'docs/a.md',{content:'first',base_content:'base',sha:null,base_version:1});b.dismiss(first);
 const next=a.put(scope,'docs/a.md',{content:'newer',base_content:'base',sha:null,base_version:1},first);
 assert.ok(next.rev>first.rev);assert.equal(b.list(scope)[0].content,'newer');assert.equal(a.remove(first),false);assert.equal(a.list(scope)[0].content,'newer');
 const copy=b.put(scope,'docs/a.md',{...next,content:'recovered'},next);assert.notEqual(copy.id,next.id);assert.equal(a.list(scope).length,2);
});

test('storage failure retains this tab buffer and reports that durable recovery was not written',async()=>{
 const {DraftJournal}=await api(),notices=[],storage={get length(){throw Error('denied');},getItem:()=>{throw Error('denied');},setItem:()=>{throw Error('quota');}};
 const a=new DraftJournal({storage,onError:e=>notices.push(e)}),draft=a.put(scope,'docs/a.md',{content:'keep me',base_content:'base',sha:null,base_version:1});
 assert.equal(draft.persisted,false);assert.equal(a.list(scope)[0].persisted,false);assert.equal(a.list(scope)[0].content,'keep me');assert.ok(notices.length>0);
 assert.throws(()=>a.put(scope,'native/model.json',{content:'x',base_content:'',sha:null}),/path|protected/i);
 assert.throws(()=>a.put(scope,'../outside.md',{content:'x',base_content:'',sha:null}),/path|protected/i);
});

test('three-way recovery merges nonoverlapping line edits without normalizing CRLF or final newline',async()=>{
 const {mergeText,resolveMerge}=await api();const base='alpha\r\nbeta\r\ngamma',local='ALPHA\r\nbeta\r\ngamma',remote='alpha\r\nbeta\r\nGAMMA';
 const plan=mergeText(base,local,remote);assert.equal(plan.conflicts.length,0);assert.equal(resolveMerge(plan,{}),'ALPHA\r\nbeta\r\nGAMMA');
});

test('overlapping recovery edits stay unresolved until a local/saved/custom choice is made',async()=>{
 const {mergeText,resolveMerge}=await api(),plan=mergeText('one\ntwo\n','one\nlocal\n','one\nsaved\n');
 assert.equal(plan.conflicts.length,1);assert.throws(()=>resolveMerge(plan,{}),/resolve|choose|conflict/i);
 const id=plan.conflicts[0].id;assert.equal(resolveMerge(plan,{[id]:'local'}),'one\nlocal\n');assert.equal(resolveMerge(plan,{[id]:'remote'}),'one\nsaved\n');assert.equal(resolveMerge(plan,{[id]:{text:'both\n'}}),'one\nboth\n');
 assert.equal(resolveMerge(mergeText('base','same','same'),{}),'same');
});

test('merge keeps insertion/deletion/EOF changes and never truncates text when diff budget is exceeded',async()=>{
 const {mergeText,resolveMerge}=await api();assert.equal(resolveMerge(mergeText('a\nb\nc\n','a\nc\n','a\nb\nc\nextra'),{}),'a\nc\nextra');
 const base='a\nb\nc\nd\n',local='A\nb\nc\nD\n',remote='one\ntwo\nthree\nfour\n';const plan=mergeText(base,local,remote,{maxCells:1});assert.equal(plan.coarse,true);assert.ok(plan.conflicts.length);const choices=Object.fromEntries(plan.conflicts.map(c=>[c.id,'local']));assert.equal(resolveMerge(plan,choices),local);
});

test('editor serialization preserves saved newline conventions and untouched mixed-ending lines',async()=>{
 const {editorText}=await api();assert.equal(editorText('a\nb\n','a\r\nb\r\n'),'a\r\nb\r\n');assert.equal(editorText('A\nb\n','a\r\nb\r\n'),'A\r\nb\r\n');
 assert.equal(editorText('a\nb\nc','a\r\nb\nc'),'a\r\nb\nc');assert.equal(editorText('A\nb\nc','a\r\nb\nc'),'A\r\nb\nc');
});

test('saving a quota-failed newer revision clears its older durable copy without resurrecting it',async()=>{
 const {DraftJournal}=await api(),storage=memory(),a=new DraftJournal({storage});
 const first=a.put(scope,'docs/a.md',{content:'durable first edit',base_content:'saved base',sha:null,base_version:1});
 const original=storage.setItem;storage.setItem=()=>{throw Error('quota');};
 const newer=a.put(scope,'docs/a.md',{...first,content:'newer accepted text'},first);assert.equal(newer.persisted,false);
 assert.equal(a.remove(newer),true);storage.setItem=original;assert.equal(new DraftJournal({storage}).list(scope).length,0);
});

test('draft initialization supports browser crypto without the secure-context UUID helper',async()=>{
 const {DraftJournal}=await api(),prior=Object.getOwnPropertyDescriptor(globalThis.crypto,'randomUUID');
 Object.defineProperty(globalThis.crypto,'randomUUID',{value:undefined,configurable:true});
 try{const journal=new DraftJournal({storage:memory()});const record=journal.put(scope,'docs/a.md',{content:'local',base_content:'saved',sha:null});assert.match(record.id,/^[a-f0-9]{32}$/);assert.match(record.writer,/^[a-f0-9]{32}$/);assert.notEqual(record.id,record.writer);}
 finally{if(prior)Object.defineProperty(globalThis.crypto,'randomUUID',prior);else delete globalThis.crypto.randomUUID;}
});
