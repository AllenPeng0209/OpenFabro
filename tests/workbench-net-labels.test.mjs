import test from 'node:test';import assert from 'node:assert/strict';
import {copySelection,pasteSelection} from '../wholeboard/web/workbench-model.mjs';
import {moveWireNode,removeWireDrawing} from '../wholeboard/web/workbench-wires.mjs';
const spec=()=>({board:{width_mm:40,height_mm:24,layers:2},components:[{ref:'R1',value:'1k'},{ref:'R2',value:'1k'}],nets:[{name:'SIG',pins:['R1.1']},{name:'GND',class:'power',pins:['R1.2','R2.2']}],
 editor:{positions:{R1:[100,100],R2:[400,100]},wire_nodes:{tag:{position:[100,50],sheet:'',net:'SIG',label:{kind:'net',rotation:90}},free:{position:[900,900],sheet:'',net:'SIG'}},connection_guides:[{id:'tail',from:'R1.1',to:'node:tag'}]}});
test('removing the final drawing retains explicit labels while pruning unused bare nodes',()=>{
 const out=removeWireDrawing(spec(),0);assert.deepEqual(Object.keys(out.editor.wire_nodes),['tag']);assert.equal(out.editor.wire_nodes.tag.label.kind,'net');assert.deepEqual(out.nets[0].pins,['R1.1']);
});
test('moving and copying a connected label preserves its type and maps its new signal net',()=>{
 const moved=moveWireNode(spec(),'tag',[200,50]);assert.equal(moved.editor.wire_nodes.tag.label.rotation,90);
 const {spec:out}=pasteSelection(moved,copySelection(moved,['R1']),{schematicOffset:[60,60]});const nodes=Object.entries(out.editor.wire_nodes).filter(([id])=>!['tag','free'].includes(id));assert.equal(nodes.length,1);assert.deepEqual(nodes[0][1].label,{kind:'net',rotation:90});assert.deepEqual(nodes[0][1].position,[260,110]);assert.notEqual(nodes[0][1].net,'SIG');assert(out.nets.find(n=>n.name===nodes[0][1].net).pins.includes('R3.1'));
});
