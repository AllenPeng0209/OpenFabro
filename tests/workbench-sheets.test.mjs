import test from 'node:test';import assert from 'node:assert/strict';
let sheets;try{sheets=await import('../wholeboard/web/workbench-sheets.mjs');}catch{}
const spec=()=>({board:{width_mm:30,height_mm:22,layers:2},components:[{ref:'R1'},{ref:'R2'},{ref:'C1'}],nets:[{name:'SIG',pins:['R1.1','R2.1','C1.1']}],editor:{positions:{R1:[200,200],R2:[500,200]},connection_guides:[{id:'signal',from:'R1.1',to:'R2.1'}]}});

test('creating a sheet moves a selection without changing circuits or PCB data',()=>{
 assert.ok(sheets,'Schematic sheet authoring is missing');const before=spec(),after=sheets.createSheet(before,'Power',{title:'Power stage',refs:['R1']});
 assert.equal(after.components[0].sheet,'Power');assert.deepEqual(after.nets,before.nets);assert.deepEqual(after.board,before.board);
 assert.deepEqual(after.editor.connection_guides,[]);assert.equal(before.components[0].sheet,undefined);
 assert.equal(after.editor.sheets.Power.title,'Power stage');
});

test('nested sheet metadata renames and moves while preventing hierarchy cycles',()=>{
 assert.ok(sheets,'Schematic sheet authoring is missing');let value=sheets.createSheet(spec(),'Power');value=sheets.createSheet(value,'Bias',{parent:'Power',refs:['C1']});
 const moved=sheets.updateSheet(value,'Power',{title:'Supply',position:[300,100],size:[400,240]});assert.equal(moved.editor.sheets.Power.title,'Supply');assert.deepEqual(moved.editor.sheets.Power.position,[300,100]);
 assert.throws(()=>sheets.updateSheet(moved,'Power',{parent:'Bias'}),/cycle|descendant/i);
 const flattened=sheets.removeSheet(moved,'Power');assert.equal(flattened.components.find(c=>c.ref==='C1').sheet,'');assert.equal(Object.keys(flattened.editor.sheets).length,0);
 assert.deepEqual(flattened.nets,value.nets);
});

test('new sibling sheets occupy separate boundaries so their native pins cannot overlap',()=>{
 let value=sheets.createSheet(spec(),'A');value=sheets.createSheet(value,'B');
 const a=value.editor.sheets.A,b=value.editor.sheets.B;
 assert.ok(a.position[0]+a.size[0]<b.position[0]||a.position[1]+a.size[1]<b.position[1]);
});
