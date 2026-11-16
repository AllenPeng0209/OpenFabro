import test from 'node:test';import assert from 'node:assert/strict';
import * as model from '../wholeboard/web/workbench-model.mjs';
import {connectWireEndpoints,disconnectPin} from '../wholeboard/web/workbench-wires.mjs';
let interfaces;try{interfaces=await import('../wholeboard/web/workbench-interfaces.mjs');}catch{}
const spec=()=>({board:{width_mm:30,height_mm:22,layers:2},components:[{ref:'R1'},{ref:'R2'},{ref:'TP1',value:'OUT',sheet:'Power',footprint:'Project:Pad',terminal:{number:'1',exclude_from_pcb:true}}],nets:[{name:'SIG',pins:['R1.1','R2.1']},{name:'PORT_TP1',pins:['TP1.1'],placeholder_ref:'TP1'}],editor:{sheets:{Power:{}},connection_guides:[]},fixed_copper:[{net:'SIG',tracks:[{a:[1,1],b:[4,1],w:.25,layer:'F.Cu'}]}],library:{footprints:{Pad:{name:'Terminal pad',pads:[]},Private:{name:'Unrelated private asset',pads:[]}}}});

test('wiring a fresh isolated terminal joins the target net without asking to short two established nets',()=>{
 const before=spec(),after=connectWireEndpoints(before,{pin:'TP1.1'},{pin:'R1.1'});
 assert.equal(after.nets.length,1);assert.deepEqual(after.nets[0].pins,['R1.1','R2.1','TP1.1']);assert.deepEqual(after.fixed_copper,before.fixed_copper);
 const established=spec();delete established.nets[1].placeholder_ref;assert.throws(()=>connectWireEndpoints(established,{pin:'TP1.1'},{pin:'R1.1'}),/review|merge|different nets/i);
});

test('disconnecting or deleting a schematic-only terminal preserves copper between the physical parts',()=>{
 const before=spec();before.nets=[{name:'SIG',pins:['R1.1','R2.1','TP1.1']}];
 const detached=disconnectPin(before,'TP1.1');assert.deepEqual(detached.fixed_copper,before.fixed_copper);assert.ok(detached.nets.some(net=>net.placeholder_ref==='TP1'&&net.pins.includes('TP1.1')));
 const removed=model.removeComponent(before,'TP1');assert.deepEqual(removed.fixed_copper,before.fixed_copper);assert.deepEqual(removed.nets[0].pins,['R1.1','R2.1']);
});

test('renaming a terminal keeps outside wire anchors and canonical net bindings consistent',()=>{
 const before=spec();before.editor.connection_guides=[{id:'external',from:'R1.1',to:'sheet:Power.OUT'}];
 assert.equal(model.electricalPin(before,'sheet:Power.OUT'),'TP1.1');
 const after=model.updateComponent(before,'TP1',{value:'VOUT'});assert.equal(after.editor.connection_guides[0].to,'sheet:Power.VOUT');assert.deepEqual(after.nets,before.nets);
 const wired=connectWireEndpoints(spec(),{pin:'R1.1'},{pin:'TP1.1',anchor:'sheet:Power.OUT'});
 assert.equal(wired.editor.sheets.Power.ports.OUT.terminal_ref,'TP1');
});

test('terminal duplication gives independent designators and pin numbers and copies only needed pad assets',()=>{
 const before=spec(),clipboard=model.copySelection(before,['TP1']);
 const duplicated=model.pasteSelection(before,clipboard).spec,added=duplicated.components.at(-1);
 assert.notEqual(added.value,'OUT');assert.notEqual(added.terminal.number,'1');assert.ok(duplicated.nets.some(net=>net.placeholder_ref===added.ref));
 const empty={board:before.board,components:[],nets:[]},pasted=model.pasteSelection(empty,clipboard).spec;
 assert.ok(pasted.library.footprints.Pad);assert.equal(pasted.library.footprints.Private,undefined);assert.equal(empty.components.length,0);
});

test('module publishing and conversion show every selected terminal even when they share a net',()=>{
 assert.ok(interfaces,'Module terminal rows are missing');const source=spec();source.components[2].sheet='';source.components.push({ref:'TP2',value:'RETURN',sheet:'',terminal:{number:'2'}});source.nets=[{name:'SIG',pins:['R1.1','R2.1','TP1.1','TP2.1']}];
 const rows=interfaces.interfaceRows(source,{refs:['TP1','TP2']});assert.deepEqual(rows.map(row=>row.label),['OUT','RETURN']);assert.ok(rows.every(row=>row.required));
 assert.deepEqual(interfaces.interfaceRows(source,{publish:true}).map(row=>row.label),['OUT','RETURN']);
});
