import test from 'node:test';
import assert from 'node:assert/strict';
import {nativeSymbol} from '../wholeboard/web/workbench-symbol.mjs';
let model={};try{model=await import('../wholeboard/web/workbench-parametric-model.mjs');}catch{}

const scene=()=>({mm_per_unit:.127,origin_mm:20.32,symbols:[
 {ref:'U1',key:'U1',unit:1,definition:'part#1',position:[300,200],rotation:90,mirror:'x',fields:[{name:'Reference',value:'U1',position_mm:[58.42,42]}]},
 {ref:'U1',key:'U1#2',unit:2,definition:'part#2',position:[700,200],rotation:0,fields:[]},
 {ref:'R1',key:'R1',unit:1,definition:'resistor',position:[0,0],fields:[]}],definitions:{'part#1':{bbox:[-5,-5,5,5],pins:[{number:'1',x:-5,y:0,angle:0}],parametric:{suffix:'A',sections:[{name:'IO',bounds:[-3,-3,3,3]}]}},'part#2':{bbox:[-5,-5,5,5],pins:[{number:'2',x:5,y:0,angle:180}],parametric:{suffix:'Power',sections:[{name:'Supply',bounds:[-3,-3,3,3]}]}}}});

test('symbol preview arranges actual sub-symbol geometry without moving the project schematic',()=>{
 const input=scene(),before=JSON.stringify(input),preview=model.symbolPreview?.(input,'U1');
 assert.deepEqual(preview?.symbols?.map(s=>s.key),['U1','U1#2'],'Symbol preview is not implemented');
 assert.equal(preview.symbols[0].rotation,0);assert.equal(preview.symbols[0].mirror,'');assert.ok(preview.symbols[1].position[0]>preview.symbols[0].position[0]+70);
 assert.equal(preview.definitions['part#1'],input.definitions['part#1']);assert.equal(JSON.stringify(input),before);
});

test('pin drag chooses the nearest native side and its actual section/sub-symbol',()=>{
 const layout={symbols:[{unit:1,position:[100,100],definition:'part#1'}],definitions:{'part#1':{bbox:[-5,-5,5,5],parametric:{suffix:'A',sections:[{name:'IO',bounds:[-3,-3,3,3]}]},pins:[]}},mm_per_unit:1};
 assert.equal(model.pinDrop?.(layout,[94,100])?.side,'left','Pin drop orientation is not implemented');
 for(const[point,side]of [[[106,100],'right'],[[100,94],'top'],[[100,106],'bottom']])assert.equal(model.pinDrop(layout,point).side,side);
 assert.equal(model.pinDrop(layout,[94,100]).section,'IO');assert.equal(model.pinDrop(layout,[94,100]).subsymbol,'A');assert.equal(model.pinDrop(layout,[500,500]),null);
});

test('pin drag uses the chosen section edge inside a multi-section symbol',()=>{
 const preview={mm_per_unit:1,symbols:[{unit:1,position:[100,100],definition:'box'}],definitions:{box:{bbox:[-5,-25,5,5],pins:[],parametric:{suffix:'A',sections:[{name:'IO',bounds:[-3,-3,3,3]},{name:'Power',bounds:[-3,-23,3,-17]}]}}}};
 assert.equal(model.pinDrop(preview,[100,118]).section,'Power');assert.equal(model.pinDrop(preview,[100,118]).side,'top','The drop is being classified against the whole symbol instead of its section');
});

test('multi-pin property values distinguish common values and mixed untouched fields',()=>{
 const pins=[{number:'1',side:'left',group:'SPI',order:0},{number:'2',side:'right',group:'SPI',order:1}];
 assert.deepEqual(model.sharedPinValues?.(pins),{side:null,group:'SPI',section:'',order:null,subsymbol:'',name:null},'Mixed pin values are not preserved');
});

test('pin selection keeps physical identities through toggle and visible range selection',()=>{
 const current=new Set(['1']),visible=['1','2','3','4'];const result=model.selectSymbolPins?.(current,'3',visible,{range:true,anchor:'1'});
 assert.deepEqual(result?.selected&&[...result.selected],['1','2','3'],'Symbol pin range selection is not implemented');
 const toggled=model.selectSymbolPins(result.selected,'2',visible,{additive:true});assert.deepEqual([...toggled.selected],['1','3']);assert.deepEqual([...current],['1']);
});

test('an explicitly named single sub-symbol displays its suffix without changing physical reference',()=>{
 const definition={bbox:[-2,-2,2,2],pins:[],graphics:[],unit_count:1,parametric:{suffix:'Logic'}};
 const html=nativeSymbol({ref:'J1',key:'J1',unit:1,position:[0,0],fields:[{name:'Reference',value:'J1',position_mm:[0,0]}]},definition,{components:[{ref:'J1'}]},{},1,0,null);
 assert.ok(html.includes('>J1.Logic</text>'),'A named single sub-symbol lost its visible suffix');assert.ok(html.includes('data-ref="J1"'));
});
