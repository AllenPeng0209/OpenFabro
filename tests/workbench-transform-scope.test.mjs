import test from 'node:test';
import assert from 'node:assert/strict';
import {SelectionTransformsUI} from '../wholeboard/web/workbench-transforms.mjs';

test('a prepared arrangement cannot commit on another schematic sheet with the same selection',async()=>{
 const initial={name:'Original'},state={pid:'p',active:'schematic',schematicSheet:'Child',selection:new Set(['J1']),version:1,spec:initial};
 const ui=new SelectionTransformsUI({state:()=>state,editable:()=>true,busy:()=>false,commit:spec=>{state.spec=spec;},save:async()=>{},toast:()=>{}});
 const proposal={scope:{pid:'p',mode:'schematic',sheet:'',keys:['J1'],epoch:0},version:1,snapshot:JSON.stringify(initial),result:{spec:{name:'Old sheet edit'},summary:{action:'align',skipped_locked:[]}}};
 await assert.rejects(ui.apply(proposal),/changed/i);
 assert.equal(state.spec,initial);
});
