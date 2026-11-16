import test from 'node:test';
import assert from 'node:assert/strict';
import {planOwnChanges,changeLabel,changeTable,AIChangeHistory} from '../wholeboard/web/workbench-ai-changes.mjs';

const a='a'.repeat(32),b='b'.repeat(32),owned=new Map([[a,{pid:'p'}],[b,{pid:'p'}]]);
test('contiguous own AI versions form one undo batch per request',()=>{
 const result=planOwnChanges({pid:'p',from:1,to:4,owned,changes:[{from_version:1,version:2,request_id:a},{from_version:2,version:3,request_id:a},{from_version:3,version:4,request_id:b}]});
 assert.equal(result.eligible,true);assert.deepEqual(result.groups.map(g=>[g.request_id,g.from_version,g.version]),[[a,1,3],[b,3,4]]);
});
test('foreign edits, missing versions and another project never become own undo',()=>{
 const valid={pid:'p',from:1,to:2,owned,changes:[{from_version:1,version:2,request_id:a}]};
 assert.equal(planOwnChanges({...valid,pid:'another'}).eligible,false);
 assert.equal(planOwnChanges({...valid,changes:[{from_version:1,version:2,request_id:'c'.repeat(32)}]}).eligible,false);
 assert.equal(planOwnChanges({...valid,to:3}).eligible,false);
 assert.equal(planOwnChanges({...valid,changes:[{from_version:0,version:2,request_id:a}]}).eligible,false);
});
test('mixed file changes cannot be advertised as an undo of the complete AI result',()=>{
 const base={pid:'p',from:1,to:2,owned,changes:[{from_version:1,version:2,request_id:a}]};
 assert.equal(planOwnChanges({...base,changes:[{...base.changes[0],files_changed:['firmware/main.cpp']}]}).eligible,false);
 assert.equal(planOwnChanges({...base,fileChanges:{[a]:['docs/review.md']}}).eligible,false);
});
test('human diff labels retain the actual component, axis and physical-unit distinction',()=>{
 const spec={components:[{ref:'R1'}],editor:{positions:{R1:[700,200]}},board:{width_mm:40}};
 assert.match(changeLabel('/editor/positions/R1/0',spec),/R1.*Schematic.*X/);
 assert.match(changeLabel('/components/0/placement/x_mm',spec),/R1.*PCB.*mm/);
 assert.match(changeLabel('/board/width_mm',spec),/Board.*Width.*mm/);
});
test('late file writes to an earlier own batch invalidate the whole unsafe undo chain once',async()=>{
 const state={pid:'p',version:3,spec:{name:'x'},undo:[{name:'beforeA'},{name:'beforeB'}],redo:[]},history=new AIChangeHistory({state:()=>state,api:async()=>{throw Error('Not needed');}});history.register(a,'p');history.register(b,'p');history.batches.set('p',{request_id:b,version:3});
 const incoming={spec:state.spec,workbench:{version:3},ai_design_changes:[{version:2,from_version:1,request_id:a},{version:3,from_version:2,request_id:b}],ai_file_changes:{[a]:['docs/a.md']}};
 assert.equal(history.invalidateFiles(incoming),true);assert.deepEqual(state.undo,[]);assert.deepEqual(state.redo,[]);
 state.undo=[{name:'a newer local edit'}];const prepared=await history.prepare('p',incoming);assert.deepEqual(prepared.undo,state.undo,'An already handled old file write must not erase future local history forever');
});
test('client-side shortened diff values are explicitly labelled even without server truncation',()=>{
 const html=changeTable({field_changes:[{path:'/summary',kind:'changed',before:'x'.repeat(800),after:'new'}],field_changes_truncated:false});
 assert.match(html,/truncated/i);
});
