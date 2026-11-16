import test from 'node:test';
import assert from 'node:assert/strict';
async function api(){try{return await import('../wholeboard/web/workbench-material-model.mjs');}catch(error){assert.fail('Part material rendering is missing: '+error.message);}}

test('native material texture coordinates use millimeters and face orientation without stretching the pattern',async()=>{
 const{materialUV}=await api();const result=materialUV([0,0,0,10,20,0,0,0,0,0,10,20],[0,0,1,0,0,1,1,0,0,1,0,0],10,[100,200,300]);assert.deepEqual([...result],[10,20,11,22,20,30,21,32]);
});

test('material changes preserve the declared grade and do not add engineering properties',async()=>{
 const{editMaterial}=await api(),program={features:[{id:'body',op:'box',material:{preset:'brass',grade:'C260'}}]},next=editMaterial(program,'body',{preset:'copper'});assert.equal(next.features[0].material.preset,'copper');assert.equal(next.features[0].material.grade,'C260');assert.equal(program.features[0].material.preset,'brass');assert.equal(next.features[0].material.density,undefined);const cleared=editMaterial(next,'body',null);assert.equal(cleared.features[0].material,undefined);
});
