import test from 'node:test';
import assert from 'node:assert/strict';
import {ViewportSlots} from '../wholeboard/web/workbench-viewports.mjs';

function setup(){
 const entries=new Map(),storage={getItem:key=>entries.get(key)??null,setItem:(key,value)=>entries.set(key,value)};
 let camera={kind:'schematic',center:[500,250],scale:1.5};const spec={name:'Unchanged'},state={pid:'project-a',active:'schematic',schematicSheet:'',version:7,spec,undo:[{name:'Prior'}],canvas:{options:{nativeScene:{}},getCamera:()=>structuredClone(camera),setCamera:value=>camera=structuredClone(value)}};
 const notices=[],slots=new ViewportSlots({state:()=>state,storage,toast:message=>notices.push(message)});
 return{state,spec,storage,entries,slots,notices,setCamera:value=>camera=value,camera:()=>camera};
}

test('view slots persist camera center and scale without changing design or undo',()=>{
 const x=setup();assert.equal(x.slots.save(6),true);x.setCamera({kind:'schematic',center:[900,700],scale:3});
 const reloaded=new ViewportSlots({state:()=>x.state,storage:x.storage,toast:()=>{}});
 assert.equal(reloaded.recall(6),true);assert.deepEqual(x.camera(),{kind:'schematic',center:[500,250],scale:1.5});
 assert.equal(x.state.spec,x.spec);assert.equal(x.state.version,7);assert.deepEqual(x.state.undo,[{name:'Prior'}]);
});

test('identical slot numbers remain isolated by project and sheet',()=>{
 const x=setup();x.slots.save(6);x.state.schematicSheet='child';x.setCamera({kind:'schematic',center:[40,50],scale:2});x.slots.save(6);
 x.state.pid='project-b';assert.equal(x.slots.recall(6),false);x.state.pid='project-a';x.state.schematicSheet='';x.slots.recall(6);assert.deepEqual(x.camera().center,[500,250]);
 x.state.schematicSheet='child';x.slots.recall(6);assert.deepEqual(x.camera().center,[40,50]);
});

test('invalid persisted cameras never reach the canvas',()=>{
 const x=setup();x.slots.save(6);const key=[...x.entries.keys()][0],stored=JSON.parse(x.entries.get(key));stored.slots['6']={kind:'schematic',center:[1,2],scale:-1};x.entries.set(key,JSON.stringify(stored));
 const reloaded=new ViewportSlots({state:()=>x.state,storage:x.storage,toast:()=>{}});x.setCamera({kind:'schematic',center:[9,9],scale:1});assert.equal(reloaded.recall(6),false);assert.deepEqual(x.camera().center,[9,9]);
});

test('unavailable browser storage falls back to this session and reports its scope',()=>{
 const x=setup(),notices=[],slots=new ViewportSlots({state:()=>x.state,storage:{getItem(){throw Error('Denied');},setItem(){throw Error('Quota');}},toast:m=>notices.push(m)});
 assert.equal(slots.save(8),true);x.setCamera({kind:'schematic',center:[2,3],scale:1});assert.equal(slots.recall(8),true);assert.deepEqual(x.camera().center,[500,250]);assert.ok(notices.some(n=>/session/i.test(n)));
});

test('an active canvas gesture prevents saving or recalling a viewport',()=>{
 const x=setup();x.slots.save(6);x.setCamera({kind:'schematic',center:[9,9],scale:2});
 const blocked=new ViewportSlots({state:()=>x.state,storage:x.storage,toast:()=>{},interacting:()=>true});
 assert.equal(blocked.recall(6),false);assert.deepEqual(x.camera().center,[9,9]);
 assert.equal(blocked.save(7),false);
});
