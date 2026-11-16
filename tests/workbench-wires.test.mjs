import test from 'node:test';
import assert from 'node:assert/strict';
import {removeComponent,copySelection,pasteSelection,upsertNet} from '../wholeboard/web/workbench-model.mjs';
let wires;try{wires=await import('../wholeboard/web/workbench-wires.mjs');}catch{}
const spec=()=>({board:{width_mm:30,height_mm:22},components:['A','B','C','D','E'].map(ref=>({ref:ref+'1'})),nets:[{name:'SIG',pins:['A1.1','B1.1']},{name:'OTHER',pins:['D1.1','E1.1']}],editor:{connection_guides:[{id:'trunk',from:'A1.1',to:'B1.1'},{id:'other',from:'D1.1',to:'E1.1'}]},fixed_copper:[{net:'SIG',tracks:[]},{net:'OTHER',tracks:[]}]});
const route=(index=0)=>({index,id:index?'other':'trunk',status:'routed',net:index?'OTHER':'SIG',points:[[100,100],[200,100],[200,300]]});

test('manually drawn bends are saved with their native route and independent alternate drawings',()=>{
  const before=spec(),waypoints=[[100,50],[300,50]],after=wires.connectWireEndpoints(before,{pin:'A1.1'},{pin:'B1.1'},{waypoints});
  assert.deepEqual(after.editor.connection_guides.at(-1).waypoints,waypoints);
  waypoints[0][0]=999;assert.equal(after.editor.connection_guides.at(-1).waypoints[0][0],100);
  assert.equal(after.editor.connection_guides.length,3);assert.equal(before.editor.connection_guides.length,2);
  assert.throws(()=>wires.connectWireEndpoints(before,{pin:'A1.1'},{pin:'B1.1'},{waypoints:[[Infinity,0]]}),/finite/i);
  assert.throws(()=>wires.connectWireEndpoints(before,{pin:'A1.1'},{pin:'B1.1'},{waypoints:Array(101).fill([0,0])}),/100|bend/i);
});

test('clicked junctions snap along the wire to the schematic connection grid',()=>{
  assert.ok(wires,'Native schematic wire branching is missing');
  const result=wires.projectWirePoint([[100,100],[300,100]],[182.2,101]);
  assert.deepEqual(result.point,[180,100]);assert.equal(result.offset,.4);
});

test('a pin joins the clicked point of an existing wire without changing other nets',()=>{
  assert.ok(wires,'Native schematic wire branching is missing');
  const before=spec(),after=wires.connectWireEndpoints(before,{pin:'C1.1'},{route:route(),at:[200,180]});
  assert.deepEqual(after.nets.find(n=>n.name==='SIG').pins,['A1.1','B1.1','C1.1']);
  assert.deepEqual(after.nets.find(n=>n.name==='OTHER'),before.nets[1]);
  const branch=after.editor.connection_guides.at(-1);
  assert.equal(branch.from,'C1.1');assert.equal(branch.to,'A1.1');assert.deepEqual(branch.to_join,{wire:'trunk',offset:.6});
  assert.equal(before.editor.connection_guides.length,2);assert.deepEqual(after.fixed_copper,before.fixed_copper);
});

test('wire-origin and wire-to-wire gestures retain endpoint attachments and require reviewed net merging',()=>{
  assert.ok(wires,'Native schematic wire branching is missing');
  const reverse=wires.connectWireEndpoints(spec(),{route:route(),at:[150,100]},{pin:'C1.1'});
  assert.deepEqual(reverse.editor.connection_guides.at(-1).from_join,{wire:'trunk',offset:1/6});
  assert.throws(()=>wires.connectWireEndpoints(spec(),{route:route(),at:[150,100]},{route:route(1),at:[200,200]}),/merge|different nets/i);
  const joined=wires.connectWireEndpoints(spec(),{route:route(),at:[150,100]},{route:route(1),at:[200,200]},{allowMerge:true});
  assert.equal(joined.nets.length,1);assert.equal(joined.nets[0].pins.length,4);
  assert.equal(joined.editor.connection_guides.at(-1).from_join.wire,'trunk');assert.equal(joined.editor.connection_guides.at(-1).to_join.wire,'other');
  const replaced=spec();replaced.editor.connection_guides[0].id='replacement';
  assert.throws(()=>wires.connectWireEndpoints(replaced,{pin:'C1.1'},{route:route(),at:[150,100]}),/wire changed/i);
});

test('disconnecting one pin removes its electrical membership and orphaned drawing branches',()=>{
  assert.ok(wires,'Native schematic wire branching is missing');
  let before=wires.connectWireEndpoints(spec(),{pin:'C1.1'},{route:route(),at:[150,100]});
  const after=wires.disconnectPin(before,'C1.1');
  assert.deepEqual(after.nets.find(n=>n.name==='SIG').pins,['A1.1','B1.1']);
  assert.equal(after.editor.connection_guides.length,2);assert.deepEqual(after.components,before.components);
  assert.deepEqual(before.nets.find(n=>n.name==='SIG').pins,['A1.1','B1.1','C1.1']);
});

test('removing a wire drawing prunes its dependent joins and preserves labeled electrical nets',()=>{
  assert.ok(wires,'Native schematic wire branching is missing');
  const before=wires.connectWireEndpoints(spec(),{pin:'C1.1'},{route:route(),at:[150,100]});
  const after=wires.removeWireDrawing(before,0);
  assert.deepEqual(after.nets,before.nets);assert.deepEqual(after.fixed_copper,before.fixed_copper);
  assert.deepEqual(after.editor.connection_guides.map(g=>g.id),['other']);
});

test('deleting a component or editing net membership cannot leave orphaned junction dependencies',()=>{
  assert.ok(wires,'Native schematic wire branching is missing');
  const before=wires.connectWireEndpoints(spec(),{pin:'C1.1'},{route:route(),at:[150,100]});
  before.editor.connection_guides.push({id:'grandchild',from:'B1.1',to:'C1.1',to_join:{wire:before.editor.connection_guides.at(-1).id,offset:.5}});
  const removed=removeComponent(before,'A1');
  assert.deepEqual(removed.editor.connection_guides.map(g=>g.id),['other']);
  const edited=upsertNet(before,{name:'SIG',pins:['B1.1','C1.1']},'SIG');
  assert.deepEqual(edited.editor.connection_guides.map(g=>g.id),['other']);
});

test('copying connected symbols remaps wire identities and keeps copied junctions attached',()=>{
  assert.ok(wires,'Native schematic wire branching is missing');
  const before=wires.connectWireEndpoints(spec(),{pin:'C1.1'},{route:route(),at:[150,100]});
  const clipboard=copySelection(before,['A1','B1','C1']);
  const pasted=pasteSelection(before,clipboard,{schematicOffset:[80,60]}).spec;
  const copied=pasted.editor.connection_guides.slice(before.editor.connection_guides.length);
  assert.equal(copied.length,2);assert.ok(copied[0].id);
  assert.notEqual(copied[0].id,'trunk');assert.equal(copied[1].to_join.wire,copied[0].id);
  assert.equal(copied[1].to_join.offset,1/6);
});

test('wire gestures preserve stable module terminal anchors through a net rename',()=>{
 const before=spec();before.components[0].sheet='Power';before.editor.sheets={Power:{ports:{SENSE:{net:'SIG'}}}};
 const wired=wires.connectWireEndpoints(before,{pin:'C1.1'},{pin:'A1.1',anchor:'sheet:Power.SENSE'});
 assert.equal(wired.editor.connection_guides.at(-1).to,'sheet:Power.SENSE');
 assert.equal(wires.endpointPin(wired,{route:{index:2}}),'C1.1');
 const renamed=upsertNet(wired,{name:'SIGNAL',pins:['A1.1','B1.1','C1.1']},'SIG');
 assert.equal(renamed.editor.sheets.Power.ports.SENSE.net,'SIGNAL');
 assert.equal(renamed.editor.connection_guides.at(-1).to,'sheet:Power.SENSE');
});

test('removing the last pin of a declared terminal prunes its empty net and drawing',()=>{
 const before=spec();before.nets[0].pins=['A1.1'];before.editor.sheets={Power:{ports:{OUT:{net:'SIG'}}}};
 before.editor.connection_guides=[{id:'port',from:'A1.1',to:'sheet:Power.OUT'}];
 const after=removeComponent(before,'A1');assert.deepEqual(after.editor.sheets.Power.ports,{});assert.deepEqual(after.editor.connection_guides,[]);
 const disconnected=wires.disconnectPin(before,'A1.1');assert.deepEqual(disconnected.editor.sheets.Power.ports,{});
});
