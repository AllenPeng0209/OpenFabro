import test from 'node:test';
import assert from 'node:assert/strict';
import {RoutingUI} from '../wholeboard/web/workbench-routing-ui.mjs';
test('a Shift/free cursor keeps the same precise point when placing a via',()=>{
 const state={boardGrid:.5,canvas:{geo:{bbox:[100,100,145,130]}},spec:{board:{width_mm:45,height_mm:30}},routePointerWorld:[120.13,109.27],routeSession:{point:[8,9.27],free:true}},ui=new RoutingUI({state:()=>state});assert.deepEqual(ui.cursorPoint(),[20.13,9.27]);state.routeSession.free=false;assert.deepEqual(ui.cursorPoint(),[20,9.5]);
});
