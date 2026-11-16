import test from 'node:test';
import assert from 'node:assert/strict';
test('custom pad routes start in copper rather than the bounding-box notch',async()=>{
 const {resolve}=await import('../wholeboard/web/workbench-routing.mjs');const s={board:{width_mm:40,height_mm:30,layers:2},nets:[{name:'SIG',pins:['J1.1']}]};const g={bbox:[100,100,140,130],pads:[{id:'custom-pad',ref:'J1',name:'1',net:'SIG',x:120,y:115,routing_anchor:[118.5,115.5],kind:'smd',shape:'custom',layers:['F.Cu']}],layers:['F.Cu','B.Cu']};
 assert.deepEqual(resolve(s,g,{kind:'pad',pin:'J1.1',padId:'custom-pad'}).point,[18.5,15.5]);
});
let routing;
try{routing=await import('../wholeboard/web/workbench-routing.mjs');}catch{}
const spec=()=>({board:{width_mm:30,height_mm:22,layers:2},rules:{track_mm:.25,power_track_mm:.5,via_diameter_mm:.6,via_drill_mm:.3},components:[{ref:'U1'},{ref:'U2'}],nets:[{name:'SIG',pins:['U1.1','U2.1']},{name:'GND',pins:['U1.2']}]});
const rawGeo=()=>({bbox:[100,100,130,122],layers:['F.Cu','B.Cu'],pads:[{ref:'U1',name:'1',x:103,y:105,net:'SIG',front:true,back:false,kind:'smd'},{ref:'U2',name:'1',x:120,y:110,net:'SIG',front:false,back:true,kind:'smd'},{ref:'U1',name:'2',x:105,y:105,net:'GND',front:true,back:false,kind:'smd'}],tracks:[],arcs:[],vias:[],zone_sources:[]});

const geo=()=>{const value=rawGeo();value.pads=value.pads.map(p=>({w:.8,h:.8,shape:'circle',layers:p.front?['F.Cu']:['B.Cu'],...p}));return value;};

test('routing keeps the physical pad identity when a footprint has repeated pin numbers',()=>{
 const geometry=geo();geometry.pads[0].id='physical-a';geometry.pads.push({...geometry.pads[0],id:'physical-b',x:109});
 const session=routing.beginRoute(spec(),geometry,{kind:'pad',pin:'U1.1',padId:'physical-b'},{layer:'F.Cu'});
 assert.deepEqual(session.point,[9,5]);assert.throws(()=>routing.beginRoute(spec(),geometry,{kind:'pad',pin:'U1.1',padId:'deleted-pad'},{layer:'F.Cu'}),/pad/i);
});

test('a route continues through corners and a real through via onto the destination layer',()=>{
  assert.ok(routing,'Continuous multilayer routing is missing');
  const before=spec(),geometry=geo();let session=routing.beginRoute(before,geometry,{kind:'pad',pin:'U1.1'},{layer:'F.Cu'});
  let result=routing.extendRoute(before,geometry,session,{kind:'point',at:[10,8]});
  assert.deepEqual(result.session.point,[10,8]);assert.equal(result.finished,false);
  const changed=routing.changeRouteLayer(result.spec,geometry,result.session,[12,9],'B.Cu');
  assert.equal(changed.session.layer,'B.Cu');assert.deepEqual(changed.session.point,[12,9]);
  const via=changed.spec.fixed_copper.find(c=>c.net==='SIG').vias[0];
  assert.deepEqual(via.p,[12,9]);assert.deepEqual(via.layers,['F.Cu','B.Cu']);assert.equal(via.drill,.3);
  const completed=routing.extendRoute(changed.spec,geometry,changed.session,{kind:'pad',pin:'U2.1'});
  assert.equal(completed.finished,true);
  assert.deepEqual(new Set(completed.spec.fixed_copper[0].tracks.map(t=>t.layer)),new Set(['F.Cu','B.Cu']));
  assert.deepEqual(completed.spec.components,before.components);assert.deepEqual(completed.spec.nets,before.nets);
  assert.equal(before.fixed_copper,undefined);
});

test('routing rejects foreign nets and inaccessible SMD layers without discarding a session',()=>{
  assert.ok(routing,'Continuous multilayer routing is missing');
  const before=spec(),geometry=geo(),session=routing.beginRoute(before,geometry,{kind:'pad',pin:'U1.1'},{layer:'F.Cu'});
  assert.throws(()=>routing.extendRoute(before,geometry,session,{kind:'pad',pin:'U1.2'}),/same net/i);
  assert.throws(()=>routing.extendRoute(before,geometry,session,{kind:'pad',pin:'U2.1'}),/via|layer/i);
  assert.throws(()=>routing.changeRouteLayer(before,geometry,session,[8,8],'In1.Cu'),/layer/i);
  assert.deepEqual(session.point,[3,5]);assert.equal(before.fixed_copper,undefined);
});

test('the preview and committed trace share flipped elbows and free-angle geometry',()=>{
  assert.ok(routing,'Continuous multilayer routing is missing');
  assert.deepEqual(routing.routePoints([0,0],[8,3]),[[0,0],[5,0],[8,3]]);
  assert.deepEqual(routing.routePoints([0,0],[8,3],{flip:true}),[[0,0],[3,3],[8,3]]);
  assert.deepEqual(routing.routePoints([0,0],[8,3],{free:true}),[[0,0],[8,3]]);
  assert.deepEqual(routing.routePoints([2,2],[2,2]),[[2,2]]);
});

test('branching from an unprotected native trace splits the original and preserves other copper',()=>{
  assert.ok(routing,'Continuous multilayer routing is missing');
  const before=spec(),geometry=geo(),id='11111111-1111-4111-8111-111111111111';
  geometry.tracks=[{id,net:'SIG',a:[103,105],b:[113,105],w:.25,layer:'F.Cu',locked:false}];
  const session=routing.beginRoute(before,geometry,{kind:'tracks',id,at:[108,105]},{layer:'F.Cu'});
  const result=routing.extendRoute(before,geometry,session,{kind:'point',at:[8,9]});
  const tracks=result.spec.fixed_copper[0].tracks;
  assert.equal(tracks.length,3);assert.equal(tracks[0].id,id);assert.deepEqual(tracks[0].b,[8,5]);assert.deepEqual(tracks[1].a,[8,5]);
  assert.deepEqual(tracks[2].b,[8,9]);
});

test('a layer change at an existing via reuses its real copper and keeps undo state',()=>{
  assert.ok(routing,'Continuous multilayer routing is missing');
  const before=spec(),geometry=geo(),id='22222222-2222-4222-8222-222222222222';
  geometry.vias=[{id,net:'SIG',p:[110,108],d:.8,drill:.4,layers:['F.Cu','B.Cu']}];
  const session=routing.beginRoute(before,geometry,{kind:'via',id},{layer:'F.Cu'});
  const result=routing.changeRouteLayer(before,geometry,session,[10,8],'B.Cu');
  assert.equal(result.spec.fixed_copper[0].vias.length,1);assert.equal(result.spec.fixed_copper[0].vias[0].id,id);
  assert.equal(result.session.history.at(-1).layer,'F.Cu');assert.deepEqual(result.session.history.at(-1).point,[10,8]);
});
test('single trace previews reject the same foreign-net and inaccessible-layer targets as commit',()=>{
 const before=spec(),geometry=geo(),session=routing.beginRoute(before,geometry,{kind:'pad',pin:'U1.1'},{layer:'F.Cu'});assert.throws(()=>routing.previewRoute(before,geometry,session,{kind:'pad',pin:'U1.2'}),/same net/i);assert.throws(()=>routing.previewRoute(before,geometry,session,{kind:'pad',pin:'U2.1'}),/layer|via/i);
});
