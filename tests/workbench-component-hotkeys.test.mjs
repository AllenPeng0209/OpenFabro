import test from 'node:test';
import assert from 'node:assert/strict';
import {captureHotkeyComponent,placeHotkeyComponent,ComponentHotkeys} from '../wholeboard/web/workbench-component-hotkeys.mjs';

const fixture=()=>({name:'Source',board:{width_mm:40,height_mm:30,layers:2},components:[{ref:'U1',value:'Amplifier',symbol:'Project:Amp',footprint:'Project:Package',module_instance:'old-module',sheet:'old-sheet',placement:{x_mm:9,y_mm:11,rotation:90,locked:true},pin_properties:{'1':{name:'Input'}},symbol_layout:{sections:[{id:'main',name:'Main'}]} }],nets:[{name:'GND',class:'power',pins:['U1.1']},{name:'IN',pins:['U1.2']}],fixed_copper:[{net:'GND',tracks:[{a:[1,1],b:[2,2],w:.25,layer:'F.Cu'}],vias:[]}],library:{symbols:{Amp:{name:'Amplifier',footprint:'Project:Package',pins:[{number:'1'},{number:'2'}]}},footprints:{Package:{name:'Package',pads:[{name:'1'},{name:'2'}]}}},editor:{positions:{U1:[100,200],'U1#2':[400,300]},rotations:{U1:90,'U1#2':180},mirrors:{'U1#2':'x'},connection_guides:[]}});
const empty=()=>({name:'Destination',board:{width_mm:60,height_mm:40,layers:2},components:[],nets:[]});

test('a hotkey captures a detached part and its project library without source nets or physical pose',()=>{
 const s=fixture(),before=structuredClone(s),t=captureHotkeyComponent(s,'U1');assert.ok(t,'Capturing must produce a reusable component template');
 assert.deepEqual(t.clipboard.nets,[]);assert.deepEqual(t.clipboard.editor.connection_guides,[]);
 assert.equal(t.clipboard.components[0].placement,undefined);assert.equal(t.clipboard.components[0].module_instance,undefined);assert.equal(t.clipboard.components[0].sheet,undefined);
 assert.deepEqual(t.clipboard.library.symbols.Amp,s.library.symbols.Amp);assert.deepEqual(t.clipboard.library.footprints.Package,s.library.footprints.Package);assert.deepEqual(s,before);
});

test('multi-unit parts keep relative positions, rotations and mirrors around the chosen unit',()=>{
 const t=captureHotkeyComponent(fixture(),'U1',{selectedKey:'U1#2'});assert.ok(t);
 assert.deepEqual(t.clipboard.editor.positions,{U1:[-300,-100],'U1#2':[0,0]});
 const placed=placeHotkeyComponent(empty(),t,[800,500],'child');assert.ok(placed);
 assert.deepEqual(placed.spec.editor.positions,{U1:[500,400],'U1#2':[800,500]});assert.deepEqual(placed.spec.editor.rotations,{U1:90,'U1#2':180});assert.equal(placed.spec.editor.mirrors['U1#2'],'x');
 assert.equal(placed.spec.components[0].sheet,'child');assert.deepEqual(placed.spec.components[0].pin_properties,{'1':{name:'Input'}});
});

test('new insertions preserve destination nets/copper and use independent references and library assets',()=>{
 const s=fixture(),before=structuredClone(s),t=captureHotkeyComponent(s,'U1'),p=placeHotkeyComponent(s,t,[400,500],'');assert.ok(p);
 assert.deepEqual(p.refs,['U2']);assert.deepEqual(p.spec.nets,before.nets);assert.deepEqual(p.spec.fixed_copper,before.fixed_copper);assert.deepEqual(p.spec.components[0],before.components[0]);
 assert.equal(p.spec.components[1].placement.locked,false);assert.equal(p.spec.components[1].placement.rotation,undefined);assert.deepEqual(p.spec.editor.positions.U2,[400,500]);assert.deepEqual(s,before);
});

test('conflicting destination library geometry is rejected before it can overwrite an existing asset',()=>{
 const t=captureHotkeyComponent(fixture(),'U1'),s=empty();s.library={symbols:{Amp:{name:'A different amp',pins:[]}}};const before=structuredClone(s);
 assert.throws(()=>placeHotkeyComponent(s,t,[0,0]),/library|dependency|asset/i);assert.deepEqual(s,before);
});

test('capturing a missing project asset fails instead of saving a nonportable template',()=>{
 const s=fixture();delete s.library.footprints.Package;assert.throws(()=>captureHotkeyComponent(s,'U1'),/dependenc|library/i);
});

test('malformed persisted templates cannot smuggle electrical connections or invalid coordinates into insertion',()=>{
 const t=captureHotkeyComponent(fixture(),'U1');assert.ok(t);t.clipboard.nets=[{name:'GND',class:'power',pins:['U1.1']}];assert.throws(()=>placeHotkeyComponent(empty(),t,[10,20]),/template|net|hotkey/i);
 const valid=captureHotkeyComponent(fixture(),'U1');assert.throws(()=>placeHotkeyComponent(empty(),valid,[Infinity,0]),/coordinate|position|finite/i);assert.throws(()=>placeHotkeyComponent(empty(),valid,[1000001,0]),/coordinate|position|limit/i);
});

test('assigned templates are snapshots rather than pointers into a later-edited source design',()=>{
 const s=fixture(),t=captureHotkeyComponent(s,'U1');assert.ok(t);s.components[0].value='Changed';s.library.symbols.Amp.pins[0].number='9';const p=placeHotkeyComponent(empty(),t,[0,0]);assert.ok(p);assert.equal(p.spec.components[0].value,'Amplifier');assert.equal(p.spec.library.symbols.Amp.pins[0].number,'1');
});

test('component slots survive reload for the same user and do not cross account boundaries',()=>{
 const entries=new Map(),storage={getItem:k=>entries.get(k)??null,setItem:(k,v)=>entries.set(k,v)},s={pid:'source',active:'schematic',spec:fixture(),selection:new Set(['U1']),selected:'U1',session:{user:{id:'alice'}},canvas:{options:{nativeScene:{}}}},params={state:()=>s,storage,toast:()=>{},editable:()=>true,busy:()=>false};
 const slots=new ComponentHotkeys(params);assert.equal(slots.assign(3),true);s.spec.components[0].value='Changed';assert.equal(new ComponentHotkeys(params).read()[3].clipboard.components[0].value,'Amplifier');s.session.user.id='bob';assert.equal(slots.read()[3],undefined);s.session.user.id='alice';assert.equal(slots.read()[3].clipboard.components[0].value,'Amplifier');
});

test('a full or unavailable browser store retains explicitly session-scoped hotkeys',()=>{
 const s={pid:'source',active:'schematic',spec:fixture(),selection:new Set(['U1']),selected:'U1',canvas:{options:{nativeScene:{}}}},notices=[];
 const slots=new ComponentHotkeys({state:()=>s,storage:{getItem(){throw Error('Blocked');},setItem(){throw Error('Quota');}},toast:m=>notices.push(m),editable:()=>true,busy:()=>false});
 assert.equal(slots.assign(5),true);assert.ok(slots.read()[5]);assert.ok(notices.some(m=>/session/i.test(m)));assert.equal(slots.assign(6),false);
});

test('assigning without one component never destroys the previously assigned slot',()=>{
 const s={pid:'source',active:'schematic',spec:fixture(),selection:new Set(['U1']),selected:'U1',canvas:{options:{nativeScene:{}}}},slots=new ComponentHotkeys({state:()=>s,storage:{getItem:()=>null,setItem:()=>{}},toast:()=>{},editable:()=>true,busy:()=>false});
 assert.equal(slots.assign(1),true);s.selection.clear();s.selected=null;assert.equal(slots.assign(1),false);assert.equal(slots.read()[1].clipboard.components[0].value,'Amplifier');
});

test('a pending preview cannot remain current after the browser session account changes',()=>{
 const s={pid:'source',active:'schematic',spec:fixture(),projectLoadToken:1,schematicSheet:'',session:{user:{id:'alice'}},canvas:{options:{nativeScene:{}}}},slots=new ComponentHotkeys({state:()=>s,toast:()=>{},editable:()=>true,busy:()=>false});
 const pending={pid:'source',spec:s.spec,load:1,canvas:s.canvas,sheet:'',user:'wb-component-hotkeys:alice'};slots.pending=pending;
 assert.equal(slots.current(pending),true);s.session.user.id='bob';assert.equal(slots.current(pending),false,'A new account must reject the old account template');
});
