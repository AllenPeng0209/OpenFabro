import test from 'node:test';
import assert from 'node:assert/strict';
import {ToolPaneLayout} from '../wholeboard/web/workbench-pane-dock.mjs';

test('accepted boundary weights survive a resize and the same persisted round trip',()=>{
 const model=new ToolPaneLayout({objects:100,layers:100});model.open('layers');model.open('objects');assert.deepEqual(model.keys,['objects','layers']);model.resize(0,250,1000);const before=model.fractions(),restored=new ToolPaneLayout(JSON.parse(JSON.stringify(model.weights)));restored.open('objects');restored.open('layers');assert.equal(before.objects,.75);assert.equal(before.layers,.25);assert.deepEqual(restored.fractions(),before);
});

test('resizing one adjacent pair preserves the other mounted pane and hidden-pane proportions',()=>{
 const model=new ToolPaneLayout();model.open('checks');model.open('objects');model.open('layers');const original=model.fractions();model.resize(0,100,1000);assert.equal(model.fractions().checks,original.checks);assert.ok(Math.abs(model.fractions().objects+model.fractions().layers-2/3)<1e-12);const before=model.fractions();model.close('layers');model.open('layers');assert.deepEqual(model.fractions(),before);
});
