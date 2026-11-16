import test from 'node:test';
import assert from 'node:assert/strict';
import {pairedPaths} from '../wholeboard/web/workbench-diff-pair.mjs';
const options={width:.25,gap:.25,start:[[0,0],[0,2]]};
test('paired paths connect physical source and destination pads around a common straight corridor',()=>{
 const r=pairedPaths([[0,1],[10,1]],{...options,end:[[10,0],[10,2]]});assert.deepEqual(r.legs,[[[0,0],[0,.75],[10,.75],[10,0]],[[0,2],[0,1.25],[10,1.25],[10,2]]]);
});
test('both offsets meet at coherent mitered corners without disconnecting their prior segments',()=>{
 const r=pairedPaths([[0,1],[5,1],[5,6]],options);assert.deepEqual(r.legs,[[[0,0],[0,.75],[5.25,.75],[5.25,6]],[[0,2],[0,1.25],[4.75,1.25],[4.75,6]]]);
});
test('45degree pair bends use parallel offsets rather than translating the same elbow',()=>{
 const r=pairedPaths([[0,1],[5,1],[10,6]],options);assert.deepEqual(r.legs[0],[[0,0],[0,.75],[5.1036,.75],[10.1768,5.8232]]);assert.deepEqual(r.legs[1],[[0,2],[0,1.25],[4.8964,1.25],[9.8232,6.1768]]);
});
test('direct reversals, crossed fanouts and invalid gaps cannot become paired copper',()=>{
 assert.throws(()=>pairedPaths([[0,1],[5,1],[0,1]],options),/reverse|turn|cross/i);assert.throws(()=>pairedPaths([[0,1],[10,1]],{...options,end:[[10,2],[10,0]]}),/cross|gap|spacing/i);assert.throws(()=>pairedPaths([[0,1],[10,1]],{...options,gap:0}),/gap/i);
});
test('a width change uses a narrow connector before entering the wider paired corridor',()=>{
 const r=pairedPaths([[0,1],[10,1]],{width:.35,gap:.2,startWidth:.15,start:[[0,.775],[0,1.225]]});assert.deepEqual(r.widths,[[.15,.35],[.15,.35]]);assert.deepEqual(r.legs[0],[[0,.775],[0,.725],[10,.725]]);assert.deepEqual(r.legs[1],[[0,1.225],[0,1.275],[10,1.275]]);
});
