import test from 'node:test';
import assert from 'node:assert/strict';
import {MechanicalPartsUI} from '../wholeboard/web/workbench-mechanical-parts.mjs';
import {MechanicalAssemblyUI} from '../wholeboard/web/workbench-mechanical-assembly.mjs';

test('assembly form capture preserves expressions and a saved non-Z rotation axis',()=>{
 const fields={'[data-component-label]':{value:'Board'},'[data-component-source]':{value:'0'},'[data-component-fixed]':{checked:false},'[data-component-angle]':{value:'angle'}},row={dataset:{assemblyRow:'board'},querySelector:key=>fields[key],querySelectorAll:()=>['width/2','0','rise'].map(value=>({value}))};
 const session={members:[{id:'board',rotation:{axis:[0,1,0],angle:'angle',origin:[1,2,3]}}],sources:[{source:{kind:'model',path:'cad/board.cad.json'}}],element:{querySelectorAll:key=>key==='[data-assembly-row]'?[row]:[]}};
 MechanicalAssemblyUI.prototype.capture(session);
 assert.deepEqual(session.members[0].translation,['width/2',0,'rise']);assert.equal(session.members[0].rotation.angle,'angle');assert.deepEqual(session.members[0].rotation.axis,[0,1,0]);assert.deepEqual(session.members[0].rotation.origin,[1,2,3]);
});

test('a linked source publication refreshes the selected assembly without switching to the source part',()=>{
 const state={pid:'a',projectLoadToken:1,viewToken:1,active:'3d'},ui=new MechanicalPartsUI({state:()=>state,interacting:()=>false,render:()=>{}});
 ui.selection.set('a',{source:'cad/product.cad.json',assetId:'assembly'});
 ui.inventory={parts:[{source:'cad/product.cad.json',asset_id:'assembly',versions:[{asset_id:'assembly',metrics:{assembly:{}}}]}]};
 ui.published({source:'cad/base.cad.json',asset_id:'new-base'});
 assert.equal(ui.current().source,'cad/product.cad.json');
 ui.published({source:'cad/product.cad.json',asset_id:'new-assembly'});
 assert.equal(ui.current().assetId,'new-assembly');
});

test('CAD model selection survives reload with separate account and project scopes',()=>{
 const values=new Map(),storage={getItem:key=>values.get(key),setItem:(key,value)=>values.set(key,value)},state={pid:'a',session:{user:{id:'one'}}};
 const first=new MechanicalPartsUI({state:()=>state,storage});assert.equal(typeof first.setSelection,'function');first.setSelection('a',{source:'cad/product.cad.json'});
 const next=new MechanicalPartsUI({state:()=>state,storage});assert.equal(next.current().source,'cad/product.cad.json');state.pid='b';assert.equal(next.current(),undefined);state.pid='a';state.session.user.id='two';assert.equal(next.current(),undefined);
 state.session.user.id='one';assert.equal(next.current().source,'cad/product.cad.json');
});

test('CAD upload claims ownership before save and cancels undispatched files after a project switch',async()=>{
 const state={pid:'a',projectLoadToken:1,viewToken:1,active:'3d',spec:{components:[]}};
 let release,arrive,posted=0;const gate=new Promise(resolve=>release=resolve),started=new Promise(resolve=>arrive=resolve);
 const ui=new MechanicalPartsUI({state:()=>state,editable:()=>true,busy:()=>false,interacting:()=>false,host:{querySelectorAll:()=>[],querySelector:()=>null},save:()=>{arrive();return gate;},toast:()=>{},api:async()=>{posted++;return{};}});
 assert.equal(typeof ui.importFiles,'function','CAD files cannot yet be imported into the workbench');
 const file=new File(['native geometry'],'part.step'),first=ui.importFiles(ui.context(),[file]);await started;
 await assert.rejects(()=>ui.importFiles(ui.context(),[file]),/Wait/);
 state.pid='b';state.projectLoadToken++;release();await first;
 assert.equal(posted,0);assert.equal(ui.running.size,0);
});

test('CAD upload keeps an accepted original in its project and stops remaining files after an editor change',async()=>{
 const state={pid:'a',projectLoadToken:1,viewToken:1,active:'3d',spec:{components:[]}};
 let release,arrive,posts=0,received=[];const gate=new Promise(resolve=>release=resolve),started=new Promise(resolve=>arrive=resolve);
 const ui=new MechanicalPartsUI({state:()=>state,editable:()=>true,busy:()=>false,interacting:()=>false,host:{querySelectorAll:()=>[],querySelector:()=>null},save:async()=>{},toast:()=>{},api:async()=>{posts++;arrive();return gate;}});
 assert.equal(typeof ui.importFiles,'function','CAD files cannot yet be imported into the workbench');
 const pending=ui.importFiles(ui.context(),[new File(['one'],'one.step'),new File(['two'],'two.step')],asset=>received.push(asset));await started;
 state.active='files';ui.onViewChange();state.active='3d';ui.onViewChange();release({asset_id:'saved-in-a'});
 await pending;assert.equal(posts,1);assert.deepEqual(received,[]);assert.equal(ui.running.size,0);
});

test('mesh uploads send referenced companion files with the model in one request',async()=>{
 const state={pid:'mesh',projectLoadToken:1,viewToken:1,active:'3d',spec:{components:[]}},bodies=[];
 const ui=new MechanicalPartsUI({state:()=>state,editable:()=>true,busy:()=>false,interacting:()=>false,host:{querySelectorAll:()=>[],querySelector:()=>null},save:async()=>{},toast:()=>{},api:async(path,options)=>{bodies.push(options.body);return{asset_id:'mesh-import'};}});
 const result=await ui.importFiles(ui.context(),[new File([JSON.stringify({asset:{version:'2.0'},buffers:[{uri:'data.bin'}]})],'assembly.gltf'),new File(['binary buffer'],'data.bin')]);
 assert.equal(result.filter(v=>v.ok).length,1);assert.equal(bodies.length,1);assert.equal(bodies[0].name,'assembly.gltf');assert.equal(atob(bodies[0].resources['data.bin']),'binary buffer');
});

test('drawing upload keeps document units and SVG region choice separate from mesh units',async()=>{
 const state={pid:'drawing',projectLoadToken:1,viewToken:1,active:'3d',spec:{components:[]}},bodies=[];
 const ui=new MechanicalPartsUI({state:()=>state,editable:()=>true,busy:()=>false,interacting:()=>false,host:{querySelectorAll:()=>[],querySelector:()=>null},save:async()=>{},toast:()=>{},api:async(path,options)=>{bodies.push(options.body);return{asset_id:'drawing'};}});
 const result=await ui.importFiles(ui.context(),[new File(['svg'],'outline.svg'),new File(['dxf'],'outline.dxf')],()=>{},{units:'in',drawingUnits:'auto',drawingMode:'outline',drawingLayers:'CUT, HOLES'});
 assert.equal(result.filter(v=>v.ok).length,2);assert.equal(bodies[0].units,'auto');assert.equal(bodies[0].drawing_mode,'outline');assert.equal(bodies[1].units,'auto');assert.deepEqual(bodies[1].layers,['CUT','HOLES']);
});

test('rebuild claims one operation before an asynchronous save and retains ownership until its response',async()=>{
 const state={pid:'mechanical',projectLoadToken:1,viewToken:1,active:'3d',spec:{components:[]}};
 let saveDone,buildDone,posts=0;
 const saving=new Promise(resolve=>saveDone=resolve),building=new Promise(resolve=>buildDone=resolve);
 const ui=new MechanicalPartsUI({state:()=>state,editable:()=>true,busy:()=>false,interacting:()=>false,
  host:{querySelectorAll:()=>[],querySelector:()=>null},save:()=>saving,toast:()=>{},render:()=>{},adopt:()=>{},
  api:async(path,options)=>{if(options?.method==='POST'){posts++;if(posts>1)throw Error('Server rejected duplicate native operation');return building;}return{state};}});
 const context=ui.context(),first=ui.build(context,{path:'cad/plate.cad.json'}),second=ui.build(context,{path:'cad/plate.cad.json'}).catch(error=>error);
 saveDone();await new Promise(resolve=>setImmediate(resolve));
 try{assert.equal(posts,1,'One pending save must not allow duplicate native submissions');assert.equal(ui.canWrite(),false,'A rejected duplicate must not release the first operation');}
 finally{buildDone({asset_id:'native-asset',source:'cad/plate.cad.json'});await Promise.all([first,second]);}
 assert.equal(ui.canWrite(),true);
});

for(const waitAt of ['save','history'])test(`CAD restoration rechecks drafts after awaiting ${waitAt}`,async()=>{
 const state={pid:'mechanical',projectLoadToken:1,viewToken:1,active:'3d',spec:{components:[]},project:{mechanical_history:{entries:[{id:'history-entry'}]}},fileDrafts:new Map()},info={schema:1,revision:2,count:1,can_undo:true,undo:{id:'history-entry'}};
 let release,arrive,posts=0;const gate=new Promise(resolve=>release=resolve),entered=new Promise(resolve=>arrive=resolve);
 const ui=new MechanicalPartsUI({state:()=>state,editable:()=>true,busy:()=>false,interacting:()=>false,host:{querySelectorAll:()=>[],querySelector:()=>null},
  save:()=>waitAt==='save'?(arrive(),gate):Promise.resolve(),toast:()=>{},render:()=>{},adopt:()=>{},api:async(path,options)=>{
   if(path.endsWith('/mechanical/history')){arrive();await gate;return info;}
   if(options?.method==='POST'){posts++;return{history:{...info,revision:3},source:'cad/plate.cad.json',asset:{asset_id:'old-asset'}};}
   return{state};}});
 if(waitAt==='save')ui.rememberHistory(state.pid,info);
 const pending=ui.restoreHistory(false).catch(error=>error);await entered;state.fileDrafts.set(state.pid+':cad/plate.cad.json',{content:'new unsaved CAD'});release();const result=await pending;
 assert.equal(posts,0,'A draft created during preparation must prevent the restore POST');assert.ok(result instanceof Error&&/draft/i.test(result.message));assert.equal(state.fileDrafts.size,1);
});

test('CAD restore prepared in one editor is canceled before dispatch after switching editors',async()=>{
 const state={pid:'a',projectLoadToken:1,viewToken:1,active:'3d',spec:{components:[]},project:{mechanical_history:{entries:[{}]}}};let release,arrive,posts=0;
 const gate=new Promise(resolve=>release=resolve),started=new Promise(resolve=>arrive=resolve),ui=new MechanicalPartsUI({state:()=>state,editable:()=>true,busy:()=>false,interacting:()=>false,host:{querySelectorAll:()=>[],querySelector:()=>null},save:()=>{arrive();return gate;},toast:()=>{},render:()=>{},adopt:()=>{},api:async()=>{posts++;return{};}});
 ui.rememberHistory('a',{schema:1,revision:1,count:1,can_undo:true,undo:{id:'entry'}});const pending=ui.restoreHistory();await started;state.active='schematic';release();await pending;assert.equal(posts,0);
});

test('an accepted old-project restore cannot adopt its response or dispatch queued work in the new project',async()=>{
 const state={pid:'a',projectLoadToken:1,viewToken:1,active:'3d',spec:{components:[]},project:{mechanical_history:{entries:[{}]}}};let release,arrive,posts=0,adopts=0,renders=0;
 const gate=new Promise(resolve=>release=resolve),started=new Promise(resolve=>arrive=resolve),ui=new MechanicalPartsUI({state:()=>state,editable:()=>true,busy:()=>false,interacting:()=>false,host:{querySelectorAll:()=>[],querySelector:()=>null},save:async()=>{},toast:()=>{},render:()=>renders++,adopt:()=>adopts++,api:async(path,options)=>{if(options?.method==='POST'){posts++;arrive();return gate;}throw Error('Old response caused an unexpected new read');}});
 ui.rememberHistory('a',{schema:1,revision:1,count:1,can_undo:true,undo:{id:'entry'}});const first=ui.restoreHistory();await started;const second=ui.restoreHistory();state.pid='b';state.projectLoadToken=2;release({history:{schema:1,revision:2},source:'cad/a.cad.json',asset:null});await Promise.all([first,second]);assert.equal(posts,1);assert.equal(adopts,0);assert.equal(renders,0);assert.equal(ui.selection.has('b'),false);
});

test('leaving and returning to the same editor cancels a restore still preparing its save',async()=>{
 const state={pid:'a',projectLoadToken:1,viewToken:1,active:'3d',spec:{components:[]},project:{mechanical_history:{entries:[{}]}}};let release,arrive,posts=0;
 const gate=new Promise(resolve=>release=resolve),started=new Promise(resolve=>arrive=resolve),ui=new MechanicalPartsUI({state:()=>state,editable:()=>true,busy:()=>false,interacting:()=>false,host:{querySelectorAll:()=>[],querySelector:()=>null},save:()=>{arrive();return gate;},toast:()=>{},render:()=>{},adopt:()=>{},api:async(path,options)=>{if(options?.method==='POST'){posts++;return{history:{schema:1,revision:2},source:'cad/a.cad.json',asset:null};}return{state};}});
 ui.rememberHistory('a',{schema:1,revision:1,count:1,can_undo:true,undo:{id:'entry'}});const pending=ui.restoreHistory();await started;state.active='schematic';state.viewToken++;ui.onViewChange();state.active='3d';state.viewToken++;ui.onViewChange();release();await pending;assert.equal(posts,0);
});

test('editor leave-and-return cancels queued intents without reversing an accepted restore',async()=>{
 const state={pid:'a',projectLoadToken:1,viewToken:1,active:'3d',spec:{components:[]},project:{mechanical_history:{entries:[{}]}}};let release,arrive,posts=0,adopts=0;
 const gate=new Promise(resolve=>release=resolve),started=new Promise(resolve=>arrive=resolve),ui=new MechanicalPartsUI({state:()=>state,editable:()=>true,busy:()=>false,interacting:()=>false,host:{querySelectorAll:()=>[],querySelector:()=>null},save:async()=>{},toast:()=>{},render:()=>{},adopt:()=>adopts++,api:async(path,options)=>{if(options?.method==='POST'){posts++;if(posts===1){arrive();return gate;}return{history:{schema:1,revision:3,count:1,can_undo:false},source:'cad/a.cad.json',asset:null};}return{state};}});
 ui.rememberHistory('a',{schema:1,revision:1,count:1,can_undo:true,undo:{id:'entry'}});const first=ui.restoreHistory();await started;const second=ui.restoreHistory();state.active='schematic';state.viewToken++;ui.onViewChange();state.active='3d';state.viewToken++;ui.onViewChange();release({history:{schema:1,revision:2,count:1,can_undo:true,undo:{id:'entry'}},source:'cad/a.cad.json',asset:null});await Promise.all([first,second]);assert.equal(posts,1);assert.equal(adopts,1);
});
