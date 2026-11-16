import test from 'node:test';
import assert from 'node:assert/strict';
let geometry;
try{geometry=await import('../wholeboard/web/workbench-geometry.mjs');}catch{}
test('the assembly geometry operations are implemented',()=>assert.ok(geometry,'Native board/enclosure assembly is not implemented'));
test('a native STEP board is placed at the actual enclosure board anchor without altering the source', {skip:!geometry},()=>{
  const enclosure={size:[36,28,20],meshes:[{name:'Base',group:'base',v:[0,0,0,36,28,2],t:[]},{name:'Lid',group:'lid',v:[0,0,18,36,28,20],t:[]},{name:'Board',group:'board',v:[2,3,4,32,25,5.6],t:[]},{name:'Parts (header)',group:'board',v:[4,5,6,7,8,9],t:[]}]};
  const board={size:[32,22,12],origin:[-1,0,-2],meshes:[{name:'J1',group:'parts',v:[0,0,0,5,4,8],t:[0,1,0]}]};
  const result=geometry.combineAssembly(enclosure,board);
  assert.deepEqual(result.meshes.map(m=>m.name),['Base','Lid','J1']);
  assert.deepEqual(result.meshes[2].v,[1,3,2,6,7,10]);
  assert.deepEqual(board.meshes[0].v,[0,0,0,5,4,8]);
  assert.deepEqual(result.size,[36,28,20]);
});
test('native symbol arcs choose the circle and sweep that pass through their middle point',{skip:!geometry},()=>{
  assert.equal(typeof geometry.arcThroughPoints,'function','Native symbol arc geometry is not implemented');
  const half=geometry.arcThroughPoints([1,0],[0,1],[-1,0]);
  assert.ok(Math.abs(half.radius-1)<1e-9);assert.deepEqual(half.center,[0,0]);assert.equal(half.sweep,1);assert.equal(half.large,0);
  assert.equal(geometry.arcThroughPoints([1,0],[-1,0],[0,-1]).large,1);
  assert.equal(geometry.arcThroughPoints([0,0],[1,0],[2,0]),null);
});
