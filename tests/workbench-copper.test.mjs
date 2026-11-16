import test from 'node:test';
import assert from 'node:assert/strict';
let copper;
try{copper=await import('../wholeboard/web/workbench-copper.mjs');}catch{}
const ids=['11111111-1111-4111-8111-111111111111','22222222-2222-4222-8222-222222222222','33333333-3333-4333-8333-333333333333'];
const spec=()=>({board:{width_mm:30,height_mm:22,layers:2},components:[{ref:'R1',placement:{x_mm:5,y_mm:5}}],nets:[{name:'SIG',pins:['R1.1']},{name:'GND',pins:['R1.2']}]});
const scene=()=>({bbox:[100,100,130,122],layers:['F.Cu','B.Cu'],tracks:[{id:ids[0],a:[105,105],b:[110,105],w:.25,layer:'F.Cu',net:'SIG'},{id:ids[1],a:[110,105],b:[112,107],w:.25,layer:'F.Cu',net:'SIG'},{id:ids[2],a:[110,105],b:[110,110],w:.5,layer:'F.Cu',net:'GND'}],arcs:[],vias:[],zone_sources:[{net:'GND',origin:[100,100],source:'(zone (net "GND") (layer "F.Cu") (polygon (pts (xy 101 101) (xy 129 101) (xy 129 121))))'}]});

test('automation protection changes preserve copper geometry and require a real boolean',()=>{
 const geo=scene();geo.tracks.forEach(t=>t.locked=true);const next=copper.editCopper(spec(),geo,{kind:'tracks',id:ids[0]},{locked:false}),tracks=next.fixed_copper.find(g=>g.net==='SIG').tracks;
 assert.equal(tracks[0].locked,false);assert.equal(tracks[1].locked,true);assert.deepEqual(tracks[0].a,[5,5]);assert.deepEqual(tracks[0].b,[10,5]);assert.equal(geo.tracks[0].locked,true);
 assert.throws(()=>copper.editCopper(spec(),geo,{kind:'tracks',id:ids[0]},{locked:'false'}),/boolean/i);
});

test('editing routed copper adopts the complete geometry and preserves nets, parts and zones',()=>{
  assert.ok(copper,'Existing native copper cannot yet be edited');
  const before=spec(),geo=scene(),next=copper.editCopper(before,geo,{kind:'tracks',id:ids[0]},{w:.35});
  assert.deepEqual(next.nets,before.nets);assert.deepEqual(next.components,before.components);
  assert.deepEqual(next.fixed_zones,geo.zone_sources);
  assert.equal(next.fixed_copper.find(c=>c.net==='SIG').tracks[0].w,.35);
  assert.deepEqual(next.fixed_copper.find(c=>c.net==='SIG').tracks[1].b,[12,7]);
  assert.equal(next.fixed_copper.find(c=>c.net==='GND').tracks[0].w,.5);
  assert.equal(geo.tracks[0].w,.25);assert.equal(before.fixed_copper,undefined);
});

test('moving a shared vertex keeps same-net neighbors attached without moving foreign nets',()=>{
  assert.ok(copper,'Existing native copper cannot yet be edited');
  const next=copper.editCopper(spec(),scene(),{kind:'tracks',id:ids[0]},{b:[11,6]});
  const signals=next.fixed_copper.find(c=>c.net==='SIG').tracks;
  assert.deepEqual(signals[0].b,[11,6]);assert.deepEqual(signals[1].a,[11,6]);
  assert.deepEqual(next.fixed_copper.find(c=>c.net==='GND').tracks[0].a,[10,5]);
  assert.throws(()=>copper.editCopper(spec(),scene(),{kind:'tracks',id:ids[0]},{layer:'In1.Cu'}),/layer/i);
  assert.throws(()=>copper.editCopper(spec(),scene(),{kind:'tracks',id:ids[0]},{w:NaN}),/finite/i);
});

test('splitting and deleting a segment preserve other native copper',()=>{
  assert.ok(copper,'Existing native copper cannot yet be edited');
  const next=copper.editCopper(spec(),scene(),{kind:'tracks',id:ids[0]},{split:[7.5,5]});
  const tracks=next.fixed_copper.find(c=>c.net==='SIG').tracks;
  assert.equal(tracks.length,3);assert.deepEqual(tracks[0].b,[7.5,5]);assert.deepEqual(tracks[1].a,[7.5,5]);assert.deepEqual(tracks[1].b,[10,5]);
  assert.notEqual(tracks[1].id,ids[0]);
  const deleted=copper.editCopper(spec(),scene(),{kind:'tracks',id:ids[0]},null);
  assert.deepEqual(deleted.fixed_copper.find(c=>c.net==='SIG').tracks.map(t=>t.id),[ids[1]]);
  assert.equal(deleted.fixed_copper.find(c=>c.net==='GND').tracks.length,1);
});

test('translating a whole segment moves each original junction exactly once',()=>{
  assert.ok(copper,'Existing native copper cannot yet be edited');
  const next=copper.editCopper(spec(),scene(),{kind:'tracks',id:ids[0]},{a:[10,5],b:[15,5]});
  const tracks=next.fixed_copper.find(group=>group.net==='SIG').tracks;
  assert.deepEqual(tracks[0].a,[10,5]);assert.deepEqual(tracks[0].b,[15,5]);assert.deepEqual(tracks[1].a,[15,5]);
});

test('moving a through via retains attached copper on both sides',()=>{
  assert.ok(copper,'Existing native copper cannot yet be edited');
  const geo=scene(),id='44444444-4444-4444-8444-444444444444';
  geo.vias.push({id,p:[110,105],d:.8,drill:.4,net:'SIG',layers:['F.Cu','B.Cu']});
  geo.tracks.push({id:'55555555-5555-4555-8555-555555555555',a:[110,105],b:[114,105],w:.25,layer:'B.Cu',net:'SIG'});
  const next=copper.editCopper(spec(),geo,{kind:'vias',id},{p:[11,6]});
  const signal=next.fixed_copper.find(group=>group.net==='SIG');
  assert.deepEqual(signal.vias[0].p,[11,6]);assert.deepEqual(signal.tracks[0].b,[11,6]);assert.deepEqual(signal.tracks[2].a,[11,6]);
});
