import test from 'node:test';
import assert from 'node:assert/strict';

// Dynamic loading lets the first run fail on a missing feature, with a clear assertion.
let model;
try { model = await import('../wholeboard/web/workbench-model.mjs'); } catch {}
test('the editor exposes design operations', () => assert.ok(model, 'The workbench design model is not implemented'));

test('mirrored unit poses survive rename, copy/paste and deletion without stale keys',()=>{
  const before=spec();before.editor={positions:{R1:[100,100],'U1#2':[200,100]},mirrors:{R1:'x','U1#2':'y'}};
  const renamed=model.updateComponent(before,'R1',{ref:'R7'});
  assert.equal(renamed.editor.mirrors.R7,'x');assert.equal(renamed.editor.mirrors.R1,undefined);
  const copied=model.copySelection(before,['R1','U1']);const pasted=model.pasteSelection(before,copied);
  assert.equal(pasted.spec.editor.mirrors.R3,'x');assert.equal(pasted.spec.editor.mirrors['U2#2'],'y');
  const removed=model.removeComponent(before,'U1');assert.deepEqual(removed.editor.mirrors,{R1:'x'});
  const invalid=structuredClone(copied);invalid.editor.mirrors.R1='other';
  assert.throws(()=>model.pasteSelection(before,invalid),/mirror/i);
});

const spec = () => ({
  board: { width_mm: 30, height_mm: 22 },
  components: [{ ref: 'R1', value: '5.1k' }, { ref: 'R2', value: '5.1k' }, { ref: 'U1', value: 'LDO', no_connect: ['2'] }],
  nets: [{ name: 'GND', pins: ['R1.2', 'R2.2', 'U1.1'] }, { name: 'CC1', pins: ['R1.1'] }],
});

test('renaming a part rewrites every connection without mutating history', { skip: !model }, () => {
  const before = spec();
  const after = model.updateComponent(before, 'R1', { ref: 'R8', value: '10k' });
  assert.equal(before.components[0].ref, 'R1');
  assert.equal(after.components[0].value, '10k');
  assert.deepEqual(after.nets[0].pins, ['R8.2', 'R2.2', 'U1.1']);
  assert.deepEqual(after.nets[1].pins, ['R8.1']);
  assert.throws(() => model.updateComponent(before, 'R1', { ref: 'R2' }), /already/i);
});

test('deleting a component removes dangling pins and empty nets', { skip: !model }, () => {
  const before=spec();before.fixed_zones=[{net:'GND',source:'ground zone'},{net:'CC1',source:'signal zone'}];
  const after = model.removeComponent(before, 'R1');
  assert.equal(after.components.length, 2);
  assert.deepEqual(after.nets, [{ name: 'GND', pins: ['R2.2', 'U1.1'] }]);
  assert.deepEqual(after.fixed_zones,[{net:'GND',source:'ground zone'}]);
});

test('placement edits preserve electrical connections and reject invalid coordinates', { skip: !model }, () => {
  const before = spec();
  const after = model.updateComponent(before, 'R1', { placement: { x_mm: 12, y_mm: 7, rotation: 90 } });
  assert.deepEqual(after.nets, before.nets);
  assert.equal(after.components[0].placement.x_mm, 12);
  assert.throws(() => model.updateComponent(before, 'R1', { placement: { x_mm: NaN } }), /finite/i);
});

test('adding a library part allocates the next free designator', { skip: !model }, () => {
  const after = model.addComponent(spec(), { ref: 'R1', value: '10k', footprint: 'Resistor_SMD:R_0603_1608Metric' });
  assert.equal(after.components[3].ref, 'R3');
  assert.deepEqual(after.nets, spec().nets);
});

test('the pin index is derived from actual net membership', { skip: !model }, () => {
  assert.equal(model.pinIndex(spec())['R1.2'], 'GND');
  assert.deepEqual(model.componentPins(spec(), 'R1'), [{ pin: '2', net: 'GND' }, { pin: '1', net: 'CC1' }]);
});

test('net edits reject shorting a pin into two nets and preserve other connections', { skip: !model }, () => {
  assert.equal(typeof model.upsertNet, 'function', 'Net editing is not implemented');
  const after = model.upsertNet(spec(), { name: 'SENSOR', class: 'signal', pins: ['R1.1', 'U1.2'] }, 'CC1');
  assert.deepEqual(after.nets[0].pins, ['R1.2', 'R2.2', 'U1.1']);
  assert.deepEqual(after.nets[1].pins, ['R1.1', 'U1.2']);
  assert.deepEqual(after.components[2].no_connect, []);
  assert.throws(() => model.upsertNet(spec(), { name: 'BAD', pins: ['R1.2', 'U1.2'] }), /already.*GND/i);
  assert.throws(() => model.upsertNet(spec(), { name: 'BAD', pins: ['U99.1'] }), /missing/i);
});

test('manual routes connect actual same-net pads in board-local coordinates', { skip: !model }, () => {
  assert.equal(typeof model.addRoute, 'function', 'Native trace editing is not implemented');
  const geo = { bbox: [100,100,130,122], pads: [
    {ref:'R1',name:'2',x:102,y:103,net:'GND'}, {ref:'U1',name:'1',x:107,y:106,net:'GND'},
    {ref:'R1',name:'1',x:102,y:101,net:'CC1'} ] };
  const after = model.addRoute(spec(), geo, 'R1.2', 'U1.1', 'F.Cu');
  assert.equal(after.fixed_copper[0].net, 'GND');
  assert.deepEqual(after.fixed_copper[0].tracks[0].a, [2,3]);
  assert.deepEqual(after.fixed_copper[0].tracks.at(-1).b, [7,6]);
  assert.throws(() => model.addRoute(spec(), geo, 'R1.1', 'U1.1', 'F.Cu'), /same net/i);
  assert.equal(spec().fixed_copper, undefined);
});

test('moving or deleting parts invalidates only copper on affected nets', { skip: !model }, () => {
  const before=spec();before.fixed_copper=[{net:'GND',tracks:[{a:[1,1],b:[2,1]}]},{net:'CC1',tracks:[]},{net:'OTHER',tracks:[]}];
  const moved=model.updateComponent(before,'R1',{placement:{x_mm:12,y_mm:7,rotation:0}});
  assert.deepEqual(moved.fixed_copper.map(c=>c.net),['OTHER']);
  const deleted=model.removeComponent(before,'R1');
  assert.deepEqual(deleted.fixed_copper.map(c=>c.net),['OTHER']);
  assert.equal(model.updateComponent(before,'R1',{value:'10k'}).fixed_copper.length,3);
  assert.equal(model.updateComponent(before,'R1',{placement:{locked:true}}).fixed_copper.length,3);
});

test('direct pin wiring extends a real net and requires explicit merging of different nets', {skip:!model},()=>{
  assert.equal(typeof model.connectPins,'function','Direct schematic wiring is not implemented');
  const connected=model.connectPins(spec(),'R1.1','U1.2');
  assert.deepEqual(connected.nets.find(n=>n.name==='CC1').pins,['R1.1','U1.2']);
  assert.deepEqual(connected.components[2].no_connect,[]);
  assert.throws(()=>model.connectPins(spec(),'R1.1','R2.2'),/different nets/i);
  const merged=model.connectPins(spec(),'R1.1','R2.2',true);
  assert.equal(merged.nets.length,1);
  assert.equal(merged.nets[0].name,'GND');
  assert.ok(merged.nets[0].pins.includes('R1.1'));
});

test('renaming a net updates planes, simulation probes and impedance references', {skip:!model},()=>{
  const before=spec();before.board.ground_pour='GND';before.board.planes={'In1.Cu':'GND'};before.simulation={sources:[{net:'GND'}],probes:['GND','CC1'],expect:[{net:'GND'}]};before.impedance=[{nets:['GND','CC1']}];
  before.fixed_zones=[{net:'GND',source:'preserved native zone'}];
  const after=model.upsertNet(before,{name:'AGND',pins:['R1.2','R2.2','U1.1'],class:'power'},'GND');
  assert.equal(after.board.ground_pour,'AGND');assert.equal(after.board.planes['In1.Cu'],'AGND');
  assert.equal(after.simulation.sources[0].net,'AGND');assert.deepEqual(after.simulation.probes,['AGND','CC1']);assert.deepEqual(after.impedance[0].nets,['AGND','CC1']);
  assert.equal(after.fixed_zones[0].net,'AGND');
});

test('renaming or removing a multi-unit part preserves or removes its schematic poses', {skip:!model},()=>{
  const before=spec();before.editor={positions:{U1:[500,250],'U1#2':[650,250],R1:[100,100]},rotations:{'U1#2':90,R1:180},connection_guides:[{from:'U1#2.2',to:'R1.1'}]};
  const renamed=model.updateComponent(before,'U1',{ref:'U8'});
  assert.deepEqual(renamed.editor.positions.U8,[500,250]);assert.deepEqual(renamed.editor.positions['U8#2'],[650,250]);assert.equal(renamed.editor.rotations['U8#2'],90);assert.equal(renamed.editor.positions.U1,undefined);
  assert.equal(renamed.editor.connection_guides[0].from,'U8#2.2');
  const removed=model.removeComponent(before,'U1');
  assert.deepEqual(Object.keys(removed.editor.positions),['R1']);assert.deepEqual(removed.editor.rotations,{R1:180});
  assert.deepEqual(removed.editor.connection_guides,[]);
});
test('chat control answers a waiting question and queues steering without cancelling a running job',{skip:!model},()=>{
  assert.equal(typeof model.messageAction,'function','Message steering controls are not implemented');
  assert.equal(model.messageAction('waiting','3.3 V','q1'),'answer');
  assert.equal(model.messageAction('running','Keep the board size',null),'queue');
  assert.equal(model.messageAction('idle','Continue','old-question'),'message');
  assert.equal(model.messageAction('waiting','', 'q1'),'none');
});

test('copy and paste allocate designators, clone internal signal nets, and retain shared power nets',()=>{
  assert.equal(typeof model.copySelection,'function','Selection copy is not implemented');
  const source=spec();source.editor={positions:{R1:[100,100],R2:[200,100]},rotations:{R1:90},connection_guides:[{from:'R1.2',to:'R2.2'}]};
  source.nets.push({name:'SENSE',pins:['R1.3','R2.3','U1.3']});
  const clip=model.copySelection(source,['R1','R2']);
  const pasted=model.pasteSelection(source,clip,{schematicOffset:[40,50],boardOffset:[1,2]});
  assert.deepEqual(pasted.refs,['R3','R4']);
  assert.equal(source.components.length,3);
  assert.equal(pasted.spec.components.length,5);
  assert.ok(pasted.spec.nets.find(n=>n.name==='GND').pins.includes('R3.2'));
  assert.ok(!pasted.spec.nets.find(n=>n.name==='SENSE').pins.includes('R3.3'));
  assert.deepEqual(pasted.spec.nets.find(n=>n.name==='SENSE_copy').pins,['R3.3','R4.3']);
  assert.deepEqual(pasted.spec.editor.positions.R3,[140,150]);
  assert.equal(pasted.spec.editor.rotations.R3,90);
  assert.ok(pasted.spec.editor.connection_guides.some(g=>g.from==='R3.2'&&g.to==='R4.2'));
  const twice=model.pasteSelection(pasted.spec,clip);
  assert.ok(twice.spec.nets.find(n=>n.name==='SENSE_copy2'));
  assert.throws(()=>model.pasteSelection(source,{}),/clipboard|copied/i);
});

test('batch movement preserves multi-unit schematic geometry and rejects invalid moves without touching locked parts',()=>{
  assert.equal(typeof model.moveSelection,'function','Batch movement is not implemented');
  const source=spec();source.components[0].placement={x_mm:3,y_mm:5};source.components[1].placement={x_mm:8,y_mm:5,locked:true};
  source.fixed_copper=[{net:'GND',tracks:[]},{net:'CC1',tracks:[]},{net:'OTHER',tracks:[]}];
  const pcb=model.moveSelection(source,[{key:'R1',x:4,y:6},{key:'R2',x:9,y:6}],'layout');
  assert.deepEqual(pcb.components[0].placement,{x_mm:4,y_mm:6});
  assert.equal(pcb.components[1].placement.x_mm,8);
  assert.deepEqual(pcb.fixed_copper,[{net:'OTHER',tracks:[]}]);
  assert.equal(source.components[0].placement.x_mm,3);
  const sheet=model.moveSelection(source,[{key:'U1#2',x:200,y:300},{key:'R1',x:100,y:100}],'schematic');
  assert.deepEqual(sheet.editor.positions['U1#2'],[200,300]);
  assert.deepEqual(sheet.components[0].placement,source.components[0].placement);
  assert.throws(()=>model.moveSelection(source,[{key:'R1',x:NaN,y:3}],'layout'),/finite/i);
  assert.throws(()=>model.moveSelection(source,[{key:'MISSING',x:1,y:3}],'layout'),/component|found/i);
});

test('manual vias become real copper and routing respects pad layers and the chosen width',()=>{
  assert.equal(typeof model.addVia,'function','Manual vias are not implemented');
  const s=spec(),withVia=model.addVia(s,'GND',[10,12],{diameter:.6,drill:.3});
  assert.deepEqual(withVia.fixed_copper[0].vias,[{p:[10,12],d:.6,drill:.3}]);
  assert.throws(()=>model.addVia(s,'MISSING',[10,12],{diameter:.6,drill:.3}),/net/i);
  assert.throws(()=>model.addVia(s,'GND',[10,12],{diameter:.3,drill:.6}),/drill|diameter/i);
  const geo={bbox:[100,100,130,122],layers:['F.Cu','B.Cu'],pads:[{ref:'R1',name:'2',x:104,y:105,net:'GND',front:true,back:false}],vias:[{p:[110,112],d:.6,drill:.3,net:'GND',layers:['F.Cu','B.Cu']}]};
  const route=model.addRoute(withVia,geo,'R1.2','via:0','F.Cu',.35);
  assert.ok(route.fixed_copper[0].tracks.every(t=>t.w===.35));
  assert.throws(()=>model.addRoute(withVia,geo,'R1.2','via:0','B.Cu'),/layer/i);
});

test('editing schematic wire bends changes only the drawing and preserves electrical and PCB data',()=>{
  assert.equal(typeof model.editWireRoute,'function','Native wire bend editing is not implemented');
  const before=spec();before.editor={connection_guides:[{from:'R1.2',to:'R2.2'}]};before.fixed_copper=[{net:'GND',tracks:[]}];
  const next=model.editWireRoute(before,0,[[100,200],[300,200]]);
  assert.deepEqual(next.editor.connection_guides[0].waypoints,[[100,200],[300,200]]);
  assert.deepEqual(next.nets,before.nets);assert.deepEqual(next.components,before.components);assert.deepEqual(next.fixed_copper,before.fixed_copper);
  assert.equal(before.editor.connection_guides[0].waypoints,undefined);
  assert.throws(()=>model.editWireRoute(before,0,[[NaN,0]]),/finite/i);
});

test('adding a new net pin keeps routed copper, while removing a pin invalidates it',()=>{
 const spec={components:[{ref:'R1'},{ref:'R2'},{ref:'R3'}],nets:[{name:'SIG',pins:['R1.1','R2.1']}],fixed_copper:[{net:'SIG',tracks:[{a:[0,0],b:[3,0],w:.25,layer:'F.Cu'}]}]};
 const extended=model.upsertNet(spec,{name:'SIG',pins:['R1.1','R2.1','R3.1']},'SIG');assert.deepEqual(extended.fixed_copper,spec.fixed_copper);
 const reduced=model.upsertNet(extended,{name:'SIG',pins:['R1.1','R3.1']},'SIG');assert.deepEqual(reduced.fixed_copper,[]);
});
