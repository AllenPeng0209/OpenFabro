import assert from 'node:assert/strict';
import test from 'node:test';
import {ManufacturingUI} from '../wholeboard/web/workbench-manufacturing.mjs';

test('production workspace handoff uses the selected project and URL encodes its identity',()=>{
  const ui=new ManufacturingUI({state:()=>({pid:'project&one',project:{},config:{}})});
  assert.match(ui.markup(),/href="\/production\?project=project%26one"/);
});

test('opening production first saves a reference draft and uses its newly allocated project ID',async()=>{
  const state={pid:null};
  const ui=new ManufacturingUI({state:()=>state,save:async()=>{state.pid='new-project';return state.pid;}});
  assert.equal(await ui.productionUrl(),'/production?project=new-project');
});

test('a late save cannot send a different newly opened project to production',async()=>{
  const state={pid:'first'};
  const ui=new ManufacturingUI({state:()=>state,save:async()=>{state.pid='second';return'first';}});
  assert.equal(await ui.productionUrl(),null);
});
