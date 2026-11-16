import test from 'node:test';
import assert from 'node:assert/strict';
import {DisplayPreferences} from '../wholeboard/web/workbench-display.mjs';
import {nativeSymbol} from '../wholeboard/web/workbench-symbol.mjs';

const defaults={pinLabels:false,comments:true,cursors:true,shortcutBar:true};
const fixture=()=>{const values=new Map();return{values,storage:{getItem:key=>values.get(key)??null,setItem:(key,value)=>values.set(key,value)}};};

test('display preferences retain native defaults and accept only declared boolean flags',()=>{
 const f=fixture(),prefs=new DisplayPreferences(f);assert.deepEqual(prefs.load('a','p'),defaults);prefs.save('a','p',{pinLabels:true,comments:'false',cursors:false,shortcutBar:0,unknown:true});assert.deepEqual(prefs.load('a','p'),{pinLabels:true,comments:true,cursors:false,shortcutBar:true});
});
test('stored preferences survive a fresh controller and cannot cross account or project keys',()=>{
 const f=fixture(),first=new DisplayPreferences(f);first.save('a','p',{...defaults,pinLabels:true,comments:false});const next=new DisplayPreferences(f);assert.deepEqual(next.load('a','p'),{pinLabels:true,comments:false,cursors:true,shortcutBar:true});assert.deepEqual(next.load('b','p'),defaults);assert.deepEqual(next.load('a','q'),defaults);
});
test('malformed, oversized or obsolete storage cannot hide comments or cursor overlays',()=>{
 for(const raw of ['{broken',JSON.stringify({schema:99,flags:{comments:false}}),'x'.repeat(2049)]){const f=fixture(),prefs=new DisplayPreferences(f);f.values.set(prefs.key('a','p'),raw);assert.deepEqual(prefs.load('a','p'),defaults);}
});
test('callers cannot mutate the cached view state through returned objects',()=>{
 const prefs=new DisplayPreferences(fixture()),a=prefs.load('a','p');a.comments=false;assert.equal(prefs.load('a','p').comments,true);const saved=prefs.save('a','p',{...defaults,pinLabels:true});saved.pinLabels=false;assert.equal(prefs.load('a','p').pinLabels,true);
});
test('storage denial retains current-session preferences and gives one useful notice',()=>{
 const messages=[],prefs=new DisplayPreferences({storage:{getItem(){throw Error('denied');},setItem(){throw Error('denied');}},toast:text=>messages.push(text)});prefs.save('a','p',{...defaults,pinLabels:true});assert.equal(prefs.load('a','p').pinLabels,true);prefs.save('a','p',{...defaults,comments:false});assert.equal(prefs.load('a','p').comments,false);assert.equal(messages.length,1);assert.match(messages[0],/session/);
});

test('semantically hidden pins emit no net text, crosses, endpoint dots or pin hit targets',()=>{
 const definition={bbox:[-3,-3,3,3],graphics:[],show_pin_names:true,show_pin_numbers:true,pins:[{number:'1',name:'HIDDEN_SUPPLY',hidden:true,x:-5,y:0,angle:0,length:2,type:'power_in'},{number:'2',name:'HIDDEN_UNUSED',hidden:true,x:5,y:0,angle:180,length:2,type:'input'},{number:'3',name:'VISIBLE_IO',hidden:false,x:0,y:5,angle:270,length:2,type:'input'}]},instance={position:[100,100],ref:'U1',key:'U1',fields:[]},spec={components:[{ref:'U1',value:'Hidden-pin check'}],editor:{}};
 const markup=nativeSymbol(instance,definition,spec,{'U1.1':'HIDDEN_POWER_NET','U1.3':'VISIBLE_NET'},.1,100,null);assert.doesNotMatch(markup,/HIDDEN_POWER_NET|HIDDEN_SUPPLY|HIDDEN_UNUSED|data-pinref="U1\.[12]"/);assert.match(markup,/data-pinref="U1\.3"/);assert.match(markup,/VISIBLE_IO/);
});

test('visiting many scopes or denied saves cannot grow preference bookkeeping without a bound',()=>{
 const prefs=new DisplayPreferences({storage:{getItem:()=>null,setItem(){throw Error('quota');}},toast:()=>{}});for(let i=0;i<2000;i++){prefs.load('a','read-'+i);prefs.save('a','write-'+i,defaults);}assert.ok(prefs.memory.size<1000,'Preference memory grew with every visited scope');assert.ok(prefs.warned.size<1000,'Warning bookkeeping grew with every failed scope');
 const reads=new DisplayPreferences({storage:{getItem:()=>null,setItem:()=>{}}});for(let i=0;i<2000;i++)reads.load('a','p'+i);assert.ok(reads.memory.size<1000,'Read-only visits bypassed the cache bound');
});
