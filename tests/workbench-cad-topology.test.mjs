import test from 'node:test';
import assert from 'node:assert/strict';

async function api(){try{return await import('../wholeboard/web/workbench-cad-topology.mjs');}catch(error){assert.fail('Native face mapping and mate construction are missing: '+error.message);}}
const base={member_id:'base',body_id:0,source_body_index:0,faces:[{index:0,selector:{kind:'plane',normal:[0,0,1],index:0,body_index:0,reference:{schema:1,entity:'face',surface:'Plane'}}},{index:1,selector:{kind:'plane',normal:[0,0,-1],index:1,body_index:0,reference:{schema:1,entity:'face',surface:'Plane'}}}],edges:[{index:0,selector:{kind:'edge',normal:[1,0,0],index:0,body_index:0,reference:{schema:1,entity:'edge',surface:'Line'}},v:[0,0,0,10,0,0]}]},data={topology:{schema:1,bodies:[base]}},mesh={body_id:0,face_ranges:[[0,0,2],[1,2,4]]};

test('triangle hit identifies its native face across material groups without inventing references for legacy meshes',async()=>{
 const {nativeFace}=await api();assert.equal(nativeFace(data,mesh,0).index,0);assert.equal(nativeFace(data,mesh,5).index,1);assert.equal(nativeFace(data,mesh,6),null);assert.equal(nativeFace({},mesh,0),null);assert.equal(nativeFace(data,{body_id:7,face_ranges:mesh.face_ranges},0),null);
});

test('edge hit keeps source-local selector identity and a distinct element kind',async()=>{
 const {nativeEdge}=await api(),pick=nativeEdge(data,0,0);assert.equal(pick.member_id,'base');assert.equal(pick.entity,'edge');assert.deepEqual(pick.selector.normal,[1,0,0]);pick.selector.normal[0]=9;assert.equal(base.edges[0].selector.normal[0],1);assert.equal(nativeEdge(data,0,9),null);
});

test('a picked mate preserves the feature graph and existing parameters while reserving a new dimension',async()=>{
 const {appendPickedMate,nativeFace}=await api(),program={schema:1,units:'mm',name:'Product',parameters:{mate_offset_1:{value:7,unit:'mm'}},features:[{id:'base',op:'component'},{id:'cap',op:'component'},{id:'product',op:'assembly',members:['base','cap'],fixed:['base'],mates:[]}],result:'product'},before=structuredClone(program),fixed=nativeFace(data,mesh,0),moving={...nativeFace(data,mesh,2),member_id:'cap'};
 const next=appendPickedMate(program,{type:'coincident',moving,reference:fixed,offset:1,flip:true});assert.deepEqual(program,before);assert.deepEqual(next.parameters.mate_offset_1,{value:7,unit:'mm'});assert.equal(next.parameters.mate_offset_2.value,1);assert.deepEqual(next.features.slice(0,2),program.features.slice(0,2));const mate=next.features.at(-1).mates[0];assert.equal(mate.offset,'mate_offset_2');assert.equal(mate.target,'cap');assert.equal(mate.reference,'base');assert.deepEqual(mate.target_anchor,moving.selector);
 assert.throws(()=>appendPickedMate(program,{type:'coincident',moving:fixed,reference:moving,offset:0}),/fixed|moving/);assert.throws(()=>appendPickedMate(program,{type:'concentric',moving,reference:fixed,offset:0}),/axis|circular|cylinder/);
});

test('screen-space edge picking interpolates depth and ignores segments beyond the click tolerance',async()=>{
 const {nearestSegment}=await api();assert.deepEqual(nearestSegment([5,3],[0,0,2,10,0,6],4),{distance:3,depth:4,point:[5,0]});assert.equal(nearestSegment([5,5],[0,0,2,10,0,6],4),null);
});
