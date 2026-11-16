import test from 'node:test';
import assert from 'node:assert/strict';
import {editWireRoute,copySelection,pasteSelection} from '../wholeboard/web/workbench-model.mjs';
import {splitWireDrawing} from '../wholeboard/web/workbench-wires.mjs';
const spec=()=>({board:{width_mm:30,height_mm:20},components:[{ref:'R1'},{ref:'R2'}],nets:[{name:'SIG',pins:['R1.1','R2.1']}],editor:{connection_guides:[{id:'exact',from:'R1.1',to:'R2.1',fixed_points:[[100,100],[300,100],[300,300]]}]}});
test('reshaping an exact cut span switches it back to editable bend routing',()=>{
 const out=editWireRoute(spec(),0,[[200,100]]);assert.equal(out.editor.connection_guides[0].fixed_points,undefined);
});
test('copying exact spans translates their geometry with their symbols',()=>{
 const before=spec(),out=pasteSelection(before,copySelection(before,['R1','R2']),{schematicOffset:[80,60]}).spec;
 assert.deepEqual(out.editor.connection_guides.at(-1).fixed_points,[[180,160],[380,160],[380,360]]);
 assert.deepEqual(before.editor.connection_guides[0].fixed_points,[[100,100],[300,100],[300,300]]);
});
test('splitting an exact span keeps two exact subpaths rather than stale full paths',()=>{
 const before=spec(),route={...before.editor.connection_guides[0],index:0,status:'routed',net:'SIG',points:[[100,100],[300,100],[300,300]]};
 const out=splitWireDrawing(before,route,[300,100]).spec;
 assert.deepEqual(out.editor.connection_guides.map(g=>g.fixed_points),[[[100,100],[300,100]],[[300,100],[300,300]]]);
});
