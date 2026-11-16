import test from 'node:test';
import assert from 'node:assert/strict';
import {RoutingUI} from '../wholeboard/web/workbench-routing-ui.mjs';

test('an exhausted design undo stack cannot rewind the live routing anchor',()=>{
  const state={generation:100,undo:[],nativePending:false,canvas:{geo:{}},routeSession:{net:'SIG',point:[12,8],layer:'B.Cu',initialized:true,history:[{net:'SIG',point:[10,8],layer:'F.Cu',initialized:true,designChanged:true}]}};
  const controller=new RoutingUI({state:()=>state,editable:()=>true,busy:()=>false,toast:()=>{},undoDesign:()=>{}});
  controller.owner=controller.scope();controller.expectedGeneration=state.generation;
  // Rendering is independent of this state transition; the real controller decides whether to rewind.
  controller.sync=()=>{};
  controller.undo();
  assert.deepEqual(state.routeSession.point,[12,8]);
  assert.equal(state.routeSession.layer,'B.Cu');
  assert.equal(state.routeSession.history.length,1);
});
