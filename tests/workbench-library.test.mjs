import test from 'node:test';
import assert from 'node:assert/strict';

let library;
try{library=await import('../wholeboard/web/workbench-library-model.mjs');}catch{}
const spec=()=>({components:[{ref:'U1',symbol:'Project:Chip',footprint:'Project:Package'}],nets:[{name:'IN',pins:['U1.1']}],library:{symbols:{Chip:{pins:[{number:'1'}],footprint:'Project:Package'}},footprints:{Package:{pads:[{name:'1'}]}},parts:{Part:{symbol:'Project:Chip',footprint:'Project:Package'}}}});

test('renaming a library asset preserves every component and reusable-part link',()=>{
  assert.ok(library,'The project library editing model is missing');
  const before=spec(),after=library.writeAsset(before,'footprints','Package',before.library.footprints.Package,'Package_v2');
  assert.equal(before.components[0].footprint,'Project:Package');
  assert.equal(after.components[0].footprint,'Project:Package_v2');
  assert.equal(after.library.symbols.Chip.footprint,'Project:Package_v2');
  assert.equal(after.library.parts.Part.footprint,'Project:Package_v2');
  assert.equal(after.library.footprints.Package,undefined);
});

test('library edits cannot silently remove a connected pin or a used asset',()=>{
  assert.ok(library,'The project library editing model is missing');
  assert.throws(()=>library.writeAsset(spec(),'symbols','Chip',{pins:[]}),/connected/i);
  assert.throws(()=>library.writeAsset(spec(),'footprints','Package',null),/used/i);
  const disconnected=spec();disconnected.nets=[];
  assert.deepEqual(library.writeAsset(disconnected,'symbols','Chip',{pins:[]}).library.symbols.Chip.pins,[]);
});

test('editing a slotted hole keeps its minimum drill consistent and clears hole data for SMD',()=>{
  const pad={kind:'thru_hole',shape:'rect',w:4,h:3,x:-2,y:0,drill:.8,drill_shape:'oval',drill_size:[.8,1.6],drill_offset:[.3,-.2]};
  const next=library.editPadField(pad,'drill_size.0',1);
  assert.deepEqual(next.drill_size,[1,1.6]);assert.equal(next.drill,1);assert.deepEqual(next.drill_offset,[.3,-.2]);assert.deepEqual([next.x,next.y],[-2,0]);assert.equal(pad.drill,.8);
  const smd=library.editPadField(next,'kind','smd');assert.equal(smd.drill,0);assert.deepEqual(library.padHole(smd).size,[0,0]);assert.deepEqual(library.padHole(smd).offset,[0,0]);
});

test('hole containment checks the rounded pad outline and rejects invalid two-axis sizes',()=>{
  const pad={kind:'thru_hole',shape:'circle',w:2,h:2,drill:.2,drill_offset:[.7,.7]};
  assert.throws(()=>library.validatePad(pad),/fit|inside/i);
  assert.throws(()=>library.validatePad({...pad,drill_offset:[0,0],drill_size:[.2,1],drill_shape:'circle'}),/equal|circular/i);
  assert.doesNotThrow(()=>library.validatePad({...pad,drill_offset:[.2,.2]}));
});
test('changing an all-layer drilled pad to an edge connector makes it a single-sided pad',()=>{
 const next=library.editPadField({kind:'thru_hole',shape:'rect',w:4,h:3,drill:1,layer:'*.Cu'},'kind','connect');
 assert.equal(next.layer,'F.Cu');assert.equal(next.drill,0);
});
