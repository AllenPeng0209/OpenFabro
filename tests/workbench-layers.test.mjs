import test from 'node:test';
import assert from 'node:assert/strict';
import {LayerState,LayerKeys,LayerPreferences} from '../wholeboard/web/workbench-layers.mjs';
import * as layerExports from '../wholeboard/web/workbench-layers.mjs';

const geometry=()=>({layers:['F.Cu','In1.Cu','In2.Cu','B.Cu'],drawing_layers:['F.SilkS','B.SilkS','Dwgs.User'],pads:[{ref:'R1',id:'front',front:true,back:false,layers:['F.Cu'],kind:'smd'},{ref:'J1',id:'through',front:true,back:true,layers:['*.Cu'],kind:'thru_hole'}],drawings:[],footprints:[],vias:[],tracks:[],zones:[],outline:[]});
const event=(code,options={})=>({code,key:code.startsWith('Key')?code.slice(3).toLowerCase():code.startsWith('Digit')?code.slice(5):code,preventDefault(){},...options});
function keys(){let scope='project-a:v1',now=1000;const model=new LayerState(geometry()),controller=new LayerKeys({model:()=>model,scope:()=>scope,ready:()=>true,clock:()=>now,changed:()=>{}});return{model,controller,setScope:s=>scope=s,setTime:n=>now=n};}

test('copper layer numbers come from the actual native stackup',()=>{
 const m=new LayerState(geometry());assert.deepEqual(m.copper,['F.Cu','In1.Cu','In2.Cu','B.Cu']);assert.equal(m.number(4),'B.Cu');assert.equal(m.number(5),null);
});
test('focusing a hidden layer shows it and keeps every other visibility preference',()=>{
 const m=new LayerState(geometry());m.setVisible('F.SilkS',false);m.setVisible('B.Cu',false);assert.equal(m.focus('F.SilkS'),true);assert.equal(m.isVisible('F.SilkS'),true);assert.equal(m.isVisible('B.Cu'),false);assert.equal(m.focused,'F.SilkS');
});
test('focus fades other layers without hiding them and the same target clears focus',()=>{
 const m=new LayerState(geometry());m.focus('F.Cu');assert.equal(m.visible('tracks',{layer:'B.Cu'}),true);assert.equal(m.opacity('tracks',{layer:'F.Cu'}),1);assert.ok(m.opacity('tracks',{layer:'B.Cu'})<.5);m.focus('F.Cu');assert.equal(m.focused,null);assert.equal(m.opacity('tracks',{layer:'B.Cu'}),1);
});
test('a hidden copper layer removes its surface pads, traces and arcs from display and picking',()=>{
 const g=geometry(),m=new LayerState(g);m.setVisible('F.Cu',false);assert.equal(m.visible('pads',g.pads[0]),false);assert.equal(m.visible('tracks',{layer:'F.Cu'}),false);assert.equal(m.visible('arcs',{layer:'F.Cu'}),false);assert.equal(m.visible('pads',g.pads[1]),true);
});
test('blind and through vias are visible only on their native copper spans',()=>{
 const m=new LayerState(geometry());for(const layer of ['In1.Cu','In2.Cu','B.Cu'])m.setVisible(layer,false);assert.equal(m.visible('vias',{layers:['In1.Cu','B.Cu']}),false);assert.equal(m.visible('vias',{layers:['F.Cu','B.Cu']}),true);m.setVisible('F.Cu',false);assert.equal(m.visible('vias',{layers:['F.Cu','B.Cu']}),false);
});
test('per-layer trace visibility does not hide pads, fills or traces on another layer',()=>{
 const m=new LayerState(geometry());m.setFeature('F.Cu','traces',false);assert.equal(m.visible('tracks',{layer:'F.Cu'}),false);assert.equal(m.visible('arcs',{layer:'F.Cu'}),false);assert.equal(m.visible('pads',geometry().pads[0]),true);assert.equal(m.visible('zones',{layer:'F.Cu'}),true);assert.equal(m.visible('tracks',{layer:'B.Cu'}),true);assert.equal(m.state('F.Cu'),'mixed');
});
test('all-fill toggling keeps traces and independent polygon outlines',()=>{
 const m=new LayerState(geometry());m.setVisible('zoneOutlines',true);m.toggleAllFills();assert.equal(m.visible('zones',{layer:'F.Cu'}),false);assert.equal(m.visible('tracks',{layer:'F.Cu'}),true);assert.equal(m.visible('zone_definitions',{layers:['F.Cu']}),true);m.toggleAllFills();assert.equal(m.visible('zones',{layer:'F.Cu'}),true);
});
test('a polygon child toggle hides only that copper layer outline',()=>{
 const m=new LayerState(geometry());m.setVisible('zoneOutlines',true);m.setFeature('F.Cu','polygons',false);assert.equal(m.visible('zone_definitions',{layers:['F.Cu']}),false);assert.equal(m.visible('zone_definitions',{layers:['B.Cu']}),true);assert.equal(m.visible('zones',{layer:'F.Cu'}),true);
});
test('label visibility covers reference drawings while preserving independent silkscreen art',()=>{
 const m=new LayerState(geometry());m.setVisible('refs',false);assert.equal(m.visible('drawings',{layer:'F.SilkS',role:'reference'}),false);assert.equal(m.visible('drawings',{layer:'F.SilkS',kind:'line'}),true);
});
test('H/O and H/Shift-O control distinct real silkscreen layers',()=>{
 const x=keys();x.controller.key(event('KeyH'));assert.equal(x.controller.key(event('KeyO')),true);assert.equal(x.model.isVisible('F.SilkS'),false);assert.equal(x.model.isVisible('B.SilkS'),true);x.controller.key(event('KeyH'));x.controller.key(event('KeyO',{shiftKey:true}));assert.equal(x.model.isVisible('B.SilkS'),false);
});
test('the physical Shift key event does not discard an H or L layer prefix',()=>{
 const x=keys();x.controller.key(event('KeyH'));x.controller.key(event('ShiftLeft',{key:'Shift',shiftKey:true}));x.controller.key(event('KeyO',{shiftKey:true}));assert.equal(x.model.isVisible('B.SilkS'),false);
 x.controller.key(event('KeyL'));x.controller.key(event('ShiftRight',{key:'Shift',shiftKey:true}));x.controller.key(event('KeyM',{shiftKey:true}));assert.equal(x.model.focused,'B.Mask');
});
test('plain copper digits and L sequences focus instead of navigating or changing a routing layer',()=>{
 const x=keys();x.controller.key(event('Digit3'));assert.equal(x.model.focused,'In2.Cu');x.controller.key(event('KeyL'));x.controller.key(event('Digit4'));assert.equal(x.model.focused,'B.Cu');x.controller.key(event('Digit9'));assert.equal(x.model.focused,'B.Cu');
});
test('H/F changes fill rendering without changing layer visibility',()=>{
 const x=keys();x.controller.key(event('KeyH'));x.controller.key(event('KeyF'));assert.equal(x.model.feature('F.Cu','fills'),false);assert.equal(x.model.isVisible('F.Cu'),true);
});
test('typing or modified shortcuts cancel a prefix without stealing their keys',()=>{
 const x=keys();x.controller.key(event('KeyH'));assert.equal(x.controller.key(event('KeyO',{target:{closest:()=>true}})),false);assert.equal(x.controller.key(event('KeyO')),false);assert.equal(x.model.isVisible('F.SilkS'),true);x.controller.key(event('KeyH'));assert.equal(x.controller.key(event('KeyO',{ctrlKey:true})),false);assert.equal(x.model.isVisible('F.SilkS'),true);
});
test('stale project prefixes, expired sequences and repeat events cannot flip layers',()=>{
 const x=keys();x.controller.key(event('KeyH'));x.setScope('project-b:v1');x.controller.key(event('KeyO'));assert.equal(x.model.isVisible('F.SilkS'),true);x.controller.key(event('KeyH'));x.setTime(3000);x.controller.key(event('KeyO'));assert.equal(x.model.isVisible('F.SilkS'),true);x.controller.key(event('Digit1'));x.controller.key(event('Digit1',{repeat:true}));assert.equal(x.model.focused,'F.Cu');
});
test('an invalid layer chord is consumed instead of falling through to a board flip',()=>{
 const x=keys();x.controller.key(event('KeyL'));assert.equal(x.controller.key(event('KeyF')),true);assert.equal(x.model.focused,null);
});
test('layer settings reload for one account/project and cannot leak into another',()=>{
 const entries=new Map(),store=new LayerPreferences({storage:{getItem:k=>entries.get(k)??null,setItem:(k,v)=>entries.set(k,v)},toast:()=>{}}),m=new LayerState(geometry());m.setVisible('F.Cu',false);m.focus('B.Cu');assert.equal(store.save('alice','a',m),true);const reloaded=new LayerPreferences({storage:{getItem:k=>entries.get(k)??null,setItem:()=>{}},toast:()=>{}});assert.equal(reloaded.load('alice','a',geometry()).isVisible('F.Cu'),false);assert.equal(reloaded.load('alice','b',geometry()).isVisible('F.Cu'),true);assert.equal(reloaded.load('bob','a',geometry()).focused,null);
});
test('invalid saved layer IDs cannot dim a changed stackup and input geometry remains unchanged',()=>{
 const g=geometry(),before=structuredClone(g),m=new LayerState(g,{schema:1,focus:'In9.Cu',hidden:['Fake.Layer'],features:{'Fake.Layer':['traces']}});assert.equal(m.focused,null);assert.equal(m.visible('tracks',{layer:'F.Cu'}),true);m.focus('F.Cu');m.setFeature('F.Cu','fills',false);assert.deepEqual(g,before);
});

test('a frozen image records real layer feature visibility and only committed aperture provenance',()=>{
 const model=new LayerState(geometry());model.focus('F.Mask');model.setFeature('B.Cu','traces',false);model.setVisible('B.Paste',true);
 const native={source_version:3,pcb_sha256:'a'.repeat(64),render_inputs_sha256:'b'.repeat(64)},hidden={footprints:['native-r2']},paths=new Map([['F.Mask',[{},{}]]]),metadata=new Map([['F.Mask',{svg_sha256:'c'.repeat(64),visibility_sha256:'d'.repeat(64)}]]);
 const frozen=layerExports.layerDisplayContext?.(model,{pid:'project-a',version:3,native,hidden,paths,metadata,pending:new Map([['B.Paste',{}]]),deferred:new Set(),errors:new Map()});
 assert.equal(frozen?.focus,'F.Mask');assert.equal(frozen.layers['B.Cu'].features.traces,false);assert.equal(frozen.layers['F.Cu'].visible,true);
 assert.deepEqual(frozen.apertures.find(a=>a.layer==='F.Mask'),{layer:'F.Mask',status:'ready',client_path_count:2,svg_sha256:'c'.repeat(64),visibility_sha256:'d'.repeat(64)});
 assert.deepEqual(frozen.apertures.find(a=>a.layer==='B.Paste'),{layer:'B.Paste',status:'loading'});
 hidden.footprints.push('later-hidden');model.focus('B.Cu');metadata.get('F.Mask').svg_sha256='e'.repeat(64);
 assert.equal(frozen.focus,'F.Mask');assert.deepEqual(frozen.hidden_objects.footprints,['native-r2']);assert.equal(frozen.apertures[0].svg_sha256,'c'.repeat(64));
});

test('deferred, failed and hidden aperture layers cannot borrow ready geometry from a cache',()=>{
 const model=new LayerState(geometry());model.setVisible('F.Mask',true);model.setVisible('B.Mask',true);model.setVisible('F.Paste',true);
 const frozen=layerExports.layerDisplayContext?.(model,{pid:'p',version:1,native:{source_version:1},hidden:{},paths:new Map([['B.Paste',[{}]]]),metadata:new Map([['B.Paste',{svg_sha256:'f'.repeat(64)}]]),pending:new Map(),deferred:new Set(['F.Mask']),errors:new Map([['B.Mask','Failed']])});
 assert.deepEqual(frozen?.apertures,[{layer:'F.Mask',status:'waiting'},{layer:'B.Mask',status:'error'},{layer:'F.Paste',status:'unavailable'},{layer:'B.Paste',status:'hidden'}]);
});

test('global pad, via and fill focus highlights its own category independently of copper layer focus',()=>{
 const m=new LayerState(geometry()),pad={layers:['F.Cu'],kind:'smd'},via={layers:['F.Cu','B.Cu']},zone={layer:'F.Cu'};
 m.focus('pads');assert.equal(m.opacity('pads',pad),1);assert.equal(m.opacity('tracks',{layer:'F.Cu'}),.2);
 m.focus('vias');assert.equal(m.opacity('vias',via),1);assert.equal(m.opacity('pads',pad),.2);
 m.focus('zones');assert.equal(m.opacity('zones',zone),1);assert.equal(m.opacity('tracks',{layer:'F.Cu'}),.2);
 m.focus('F.Cu/pads');assert.equal(m.opacity('pads',pad,'F.Cu'),1);assert.equal(m.opacity('pads',{layers:['B.Cu'],kind:'smd'},'B.Cu'),.2);
});

test('courtyard focus includes native courtyard drawings in the mechanical category',()=>{
 const m=new LayerState(geometry()),court={layer:'F.CrtYd'};m.focus('courtyards');assert.equal(m.opacity('drawings',court),1);assert.equal(m.opacity('drawings',{layer:'F.SilkS'}),.2);
 m.focus('mechanical');assert.equal(m.opacity('drawings',court),1);
});
test('a plated drilled opening remains mechanical when every annular copper layer is hidden',()=>{
 const g=geometry(),p={...g.pads[1],drill:.8,layers:['F.Cu','In1.Cu']},m=new LayerState(g);m.setVisible('F.Cu',false);m.setVisible('In1.Cu',false);assert.equal(m.visible('pads',p),true);assert.equal(m.visible('pads',p,'B.Cu'),false);m.setVisible('pads',false);assert.equal(m.visible('pads',p),false);
});
