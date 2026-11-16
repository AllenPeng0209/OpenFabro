import test from 'node:test';
import assert from 'node:assert/strict';
import * as wires from '../wholeboard/web/workbench-wires.mjs';
import {wireMergeNeedsReview,upsertNet,copySelection,pasteSelection,removeComponent} from '../wholeboard/web/workbench-model.mjs';
import {createSheet,assignSheet,removeSheet} from '../wholeboard/web/workbench-sheets.mjs';
const spec=()=>({board:{width_mm:30,height_mm:22},components:['R1','R2','R3'].map(ref=>({ref})),nets:[{name:'SIG',pins:['R1.1','R2.1']},{name:'GND',pins:['R1.2','R2.2']}],editor:{connection_guides:[]},fixed_copper:[{net:'SIG',tracks:[{a:[1,1],b:[2,1],w:.25}]}]});
const point=position=>({point:position,sheet:''});

test('free canvas wires persist real nodes and a zero-pin net without inventing components',()=>{
  const before=spec(),out=wires.connectWireEndpoints(before,point([102,98]),point([300,200]),{waypoints:[[300,100]]});
  assert.equal(out.components.length,before.components.length);
  assert.equal(Object.keys(out.editor.wire_nodes||{}).length,2);
  const net=out.nets.find(n=>n.wire_only);assert.deepEqual(net.pins,[]);
  assert.deepEqual(Object.values(out.editor.wire_nodes).map(n=>n.position),[[100,100],[300,200]]);
  assert.ok(Object.values(out.editor.wire_nodes).every(n=>n.net===net.name));
  assert.deepEqual(out.fixed_copper,before.fixed_copper);assert.equal(before.editor.wire_nodes,undefined);
});

test('a free-wire network binds to actual pins and merges into a named net without invalidating its copper',()=>{
  let out=wires.connectWireEndpoints(spec(),point([100,100]),point([300,100]));
  const guide=out.editor.connection_guides[0],node=guide.to.slice(5);
  out=wires.connectWireEndpoints(out,{node},{pin:'R3.1'});
  assert.equal(wireMergeNeedsReview(out,guide.from,'R1.1'),false);
  const saved=wires.connectWireEndpoints(out,{node:guide.from.slice(5)},{pin:'R1.1'});
  assert.deepEqual(saved.nets.find(n=>n.name==='SIG').pins,['R1.1','R2.1','R3.1']);
  assert.ok(Object.values(saved.editor.wire_nodes).every(n=>n.net==='SIG'));
  assert.equal(saved.nets.length,2);assert.deepEqual(saved.fixed_copper,spec().fixed_copper);
});

test('pin-to-free and wire-to-free gestures retain canonical connectivity and real parent joins',()=>{
  let out=wires.connectWireEndpoints(spec(),{pin:'R1.1'},point([300,100]));
  const g=out.editor.connection_guides[0],route={...g,index:0,status:'routed',net:'SIG',points:[[100,100],[300,100]]};
  out=wires.connectWireEndpoints(out,{route,at:[200,100]},point([200,300]));
  assert.equal(out.editor.connection_guides[1].from_join.wire,g.id);
  assert.ok(Object.values(out.editor.wire_nodes).every(n=>n.net==='SIG'));
  const renamed=upsertNet(out,{name:'SIGNAL',pins:['R1.1','R2.1']},'SIG');
  assert.ok(Object.values(renamed.editor.wire_nodes).every(n=>n.net==='SIGNAL'));
});

test('free endpoints move independently and removing their final wire prunes private nodes and empty auto nets',()=>{
  assert.equal(typeof wires.moveWireNode,'function','Editable free wire endpoints are missing');
  const out=wires.connectWireEndpoints(spec(),point([100,100]),point([300,100])),id=out.editor.connection_guides[0].to.slice(5);
  const moved=wires.moveWireNode(out,id,[352,228]);assert.deepEqual(moved.editor.wire_nodes[id].position,[350,230]);
  assert.deepEqual(moved.nets,out.nets);assert.deepEqual(moved.components,out.components);assert.deepEqual(moved.fixed_copper,out.fixed_copper);
  assert.throws(()=>wires.moveWireNode(out,id,[NaN,0]),/finite/i);
  const deleted=wires.removeWireDrawing(moved,0);assert.deepEqual(deleted.editor.wire_nodes,{});assert.equal(deleted.nets.length,2);
});

test('splitting a native wire creates two attached routes and rebases dependent junction fractions',()=>{
  assert.equal(typeof wires.splitWireDrawing,'function','Splitting schematic wires at a native point is missing');
  const before=spec();before.editor.connection_guides=[{id:'trunk',from:'R1.1',to:'R2.1'},{id:'branch',from:'R3.1',to:'R1.1',to_join:{wire:'trunk',offset:.75}}];before.nets[0].pins.push('R3.1');
  const route={...before.editor.connection_guides[0],index:0,status:'routed',net:'SIG',points:[[100,100],[500,100]]};
  const {spec:out,node}=wires.splitWireDrawing(before,route,[260,100]);
  const left=out.editor.connection_guides[0],right=out.editor.connection_guides[1],branch=out.editor.connection_guides[2];
  assert.equal(left.id,'trunk');assert.equal(left.to,'node:'+node);assert.equal(right.from,left.to);assert.equal(right.to,'R2.1');
  assert.equal(branch.to_join.wire,right.id);assert.ok(Math.abs(branch.to_join.offset-(.75-.4)/.6)<1e-9);
  assert.equal(branch.to,right.from,'A rebased branch must not retain the old opposite endpoint as its representative');
  assert.deepEqual(out.nets,before.nets);assert.deepEqual(out.fixed_copper,before.fixed_copper);
  assert.throws(()=>wires.splitWireDrawing(before,route,[100,100]),/end|interior/i);
});

test('component clipboard carries attached wire nodes with remapped identities and coordinates',()=>{
  const out=wires.connectWireEndpoints(spec(),{pin:'R1.1'},point([300,100]));
  const copied=copySelection(out,['R1']),pasted=pasteSelection(out,copied,{schematicOffset:[80,60]}).spec;
  const original=out.editor.connection_guides[0],last=pasted.editor.connection_guides.at(-1);
  assert.notEqual(last.to,original.to);assert.equal(last.from,'R4.1');
  assert.deepEqual(pasted.editor.wire_nodes[last.to.slice(5)].position,[380,160]);
  assert.equal(pasted.editor.wire_nodes[last.to.slice(5)].net,'SIG_copy');
  const deleted=removeComponent(out,'R1');assert.deepEqual(deleted.editor.wire_nodes,{});
});

test('disconnecting the only real pin leaves the remaining free wire network without dangling pin references',()=>{
  let out=wires.connectWireEndpoints(spec(),{pin:'R3.1'},point([300,100]));const id=out.editor.connection_guides[0].to.slice(5);
  out=wires.connectWireEndpoints(out,{node:id},point([500,100]));out=wires.disconnectPin(out,'R3.1');
  assert.equal(out.editor.connection_guides.length,1);assert.equal(Object.keys(out.editor.wire_nodes).length,2);
  const name=Object.values(out.editor.wire_nodes)[0].net;assert.deepEqual(out.nets.find(n=>n.name===name).pins,[]);
});

test('splitting exactly at a bend cannot pin the shared node twice in the new routes',()=>{
  const before=spec();before.editor.connection_guides=[{id:'bent',from:'R1.1',to:'R2.1'}];
  const route={...before.editor.connection_guides[0],index:0,status:'routed',net:'SIG',points:[[100,100],[300,100],[300,300]]};
  const out=wires.splitWireDrawing(before,route,[300,100]).spec;
  assert.deepEqual(out.editor.connection_guides.map(g=>g.waypoints),[[],[]]);
});

test('removing a free endpoint removes its attached drawings while retaining named pin memberships and copper',()=>{
  assert.equal(typeof wires.removeWireNode,'function','Removing free wire endpoints is missing');
  const out=wires.connectWireEndpoints(spec(),{pin:'R1.1'},point([300,100])),node=out.editor.connection_guides[0].to.slice(5);
  const removed=wires.removeWireNode(out,node);assert.deepEqual(removed.editor.wire_nodes,{});assert.deepEqual(removed.editor.connection_guides,[]);
  assert.deepEqual(removed.nets,out.nets);assert.deepEqual(removed.fixed_copper,out.fixed_copper);
});

test('page moves prune cross-page drawings and flattening a page retains free nodes',()=>{
  let out=wires.connectWireEndpoints(spec(),{pin:'R1.1'},point([300,100]));out=createSheet(out,'M');
  const moved=assignSheet(out,['R1'],'M');assert.deepEqual(moved.editor.wire_nodes,{});assert.deepEqual(moved.editor.connection_guides,[]);
  out.components.find(c=>c.ref==='R1').sheet='M';Object.values(out.editor.wire_nodes)[0].sheet='M';
  const flat=removeSheet(out,'M');assert.equal(Object.values(flat.editor.wire_nodes)[0].sheet,'');assert.equal(flat.editor.connection_guides.length,1);
});
