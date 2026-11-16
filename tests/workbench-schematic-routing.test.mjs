import test from 'node:test';
import assert from 'node:assert/strict';
let Draft;try{({SchematicWireDraft:Draft}=await import('../wholeboard/web/workbench-schematic-routing.mjs'));}catch{}

test('wire previews snap the cursor, keep exact pin coordinates and flip the elbow',()=>{
  assert.ok(Draft,'Continuous schematic wire drafting is missing');
  const wire=new Draft([105,105]);
  assert.deepEqual(wire.move([197,164]),[[105,105],[200,105],[200,160]]);
  assert.deepEqual(wire.flip(),[[105,105],[105,160],[200,160]]);
  assert.deepEqual(wire.finish([205,175]),[[105,175]]);
});

test('each bend is reversible as one click without changing earlier route geometry',()=>{
  assert.ok(Draft,'Continuous schematic wire drafting is missing');
  const wire=new Draft([100,100]);
  wire.bend([200,180]);wire.bend([310,250]);
  assert.deepEqual(wire.points,[[100,100],[200,100],[200,180],[310,180],[310,250]]);
  assert.equal(wire.undo(),true);assert.deepEqual(wire.points,[[100,100],[200,100],[200,180]]);
  assert.equal(wire.undo(),true);assert.deepEqual(wire.points,[[100,100]]);assert.equal(wire.undo(),false);
});

test('duplicate clicks do not add steps and finishing does not mutate the pending draft',()=>{
  assert.ok(Draft,'Continuous schematic wire drafting is missing');
  const wire=new Draft([100,100]);assert.equal(wire.bend([101,99]),false);
  wire.bend([200,100]);const before=structuredClone(wire.points),finished=wire.finish([300,200]);
  assert.deepEqual(finished,[[300,100]]);assert.deepEqual(wire.points,before);
  const exposed=wire.points;exposed[0][0]=999;assert.deepEqual(wire.points,before);
});

test('invalid and excessive drafts cannot replace a valid pending route',()=>{
  assert.ok(Draft,'Continuous schematic wire drafting is missing');
  assert.throws(()=>new Draft([NaN,0]),/finite/i);
  const wire=new Draft([100,100]);assert.throws(()=>wire.bend([Infinity,0]),/finite/i);
  for(let i=1;i<50;i++)wire.bend([100+i*20,100+i*20]);
  const before=wire.points;
  assert.throws(()=>wire.bend([2000,2000]),/100|bend/i);
  assert.deepEqual(wire.points,before);
});

test('SVG matrix roundoff cannot lock a false bend at the source pin',()=>{
  assert.ok(Draft,'Continuous schematic wire drafting is missing');
  const wire=new Draft([400.0000305175781,490]);
  assert.deepEqual(wire.finish([400,160]),[]);
  assert.equal(wire.bend([400,490]),false);
});

test('a plain endpoint gesture can retain automatic obstacle routing until the user chooses a bend or elbow',()=>{
  assert.ok(Draft,'Continuous schematic wire drafting is missing');
  const wire=new Draft([100,100]);assert.equal(wire.manual,false);
  wire.flip();assert.equal(wire.manual,true);wire.flip();assert.equal(wire.manual,false);
  wire.bend([200,180]);assert.equal(wire.manual,true);wire.undo();assert.equal(wire.manual,false);
});

test('manual paths leave and enter the same native pin exits as the exporter',()=>{
  const wire=new Draft([200,170],{escape:[200,160]});wire.bend([300,100]);
  assert.deepEqual(wire.points,[[200,170],[200,160],[300,160],[300,100]]);
  assert.deepEqual(wire.finish([600,170],{escape:[600,160]}),[[200,160],[300,160],[300,100],[600,100]]);
  wire.undo();assert.deepEqual(wire.points,[[200,170],[200,160]]);
});
