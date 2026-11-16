import test from 'node:test';
import assert from 'node:assert/strict';
import {CADPreferences,prepareCADData} from '../wholeboard/web/workbench-cad-model.mjs';

test('native curve event markers use saved event locations and keep inflections separate from jumps',async()=>{
 const {curvatureEvents}=await import('../wholeboard/web/workbench-curve-analysis.mjs');
 const data={topology:{bodies:[{body_id:3,member_id:'part',edges:[{index:1,curve_events:{available:true,complete:true,events:[{kind:'inflection',parameter:.5,point:[6,0,2]},{kind:'curvature_jump',parameter:.7,point:[8,0,2]},{kind:'tangent_break',parameter:.9,point:[10,0,2]}]}}]}]}};
 const a=curvatureEvents(data,{inflections:true,jumps:false});assert.equal(a.markers.length,1);assert.deepEqual(a.markers[0].point,[6,0,2]);assert.equal(a.markers[0].bodyId,3);
 const b=curvatureEvents(data,{inflections:false,jumps:true});assert.equal(b.markers.length,1);assert.equal(b.markers[0].kind,'curvature_jump');
 assert.equal(curvatureEvents({topology:{bodies:[{body_id:0,edges:[{index:0}]}]}},{inflections:true,jumps:true}).available,false);
});

test('curve event visibility preferences survive reload and do not leak to other projects',()=>{
 const values=new Map(),storage={getItem:k=>values.get(k),setItem:(k,v)=>values.set(k,v)},a=new CADPreferences({storage});
 a.save('alice','events',{comb:true,combInflections:true,combJumps:false});const b=new CADPreferences({storage});
 assert.equal(b.load('alice','events').combInflections,true);assert.equal(b.load('alice','events').combJumps,false);assert.equal(b.load('alice','other').combInflections,false);
 assert.equal(b.save('alice','events',{combInflections:'true',combJumps:1}).combInflections,false);
});

test('surface display uses native signed principal curvatures and keeps missing samples unknown',async()=>{
 const {surfaceAttributes,surfaceMetric}=await import('../wholeboard/web/workbench-surface-analysis.mjs');
 const mesh={v:[0,0,0,4,0,1,1,1,1],surface_samples:[{face_index:0,normal:[1,0,0],principal:[-.25,0]},null,{face_index:1,normal:[0,0,1],principal:[-.5,.25]}]};
 const a=surfaceAttributes(mesh,'gaussian');assert.deepEqual(Array.from(a.valid),[1,0,1]);
 assert.deepEqual(Array.from(a.values),[0,0,-.125]);assert.deepEqual(Array.from(a.normals),[1,0,0,0,0,1,0,0,1]);
 assert.equal(surfaceMetric([-.5,.25],'mean'),-.125);assert.equal(surfaceMetric([-.5,.25],'max_abs'),.5);
 assert.equal(surfaceMetric([-.5,.25],'min'),-.5);assert.equal(surfaceMetric([-.5,.25],'max'),.25);
 assert.equal(surfaceAttributes({v:[0,0,0]},'mean').available,false);
});

test('surface analysis preferences survive reload and reject invalid modes or nonfinite display scales',()=>{
 const values=new Map(),storage={getItem:k=>values.get(k),setItem:(k,v)=>values.set(k,v)},a=new CADPreferences({storage});
 a.save('alice','surface',{surfaceMode:'zebra',surfaceMetric:'gaussian',zebraDensity:18,zebraAngle:45,surfaceRange:.5});
 const b=new CADPreferences({storage});assert.equal(b.load('alice','surface').surfaceMode,'zebra');assert.equal(b.load('alice','surface').surfaceRange,.5);
 assert.equal(b.load('alice','other').surfaceMode,'off');assert.equal(b.load('bob','surface').surfaceMode,'off');
 const invalid=b.save('alice','surface',{surfaceMode:'x',surfaceMetric:'x',zebraDensity:Infinity,zebraAngle:NaN,surfaceRange:0});
 assert.equal(invalid.surfaceMode,'off');assert.equal(invalid.surfaceMetric,'max_abs');assert.equal(invalid.zebraDensity,12);assert.equal(invalid.zebraAngle,0);assert.equal(invalid.surfaceRange,.001);
});

test('curvature combs retain native coordinates, signed normals and visible-body ownership',async()=>{
 const {curvatureComb}=await import('../wholeboard/web/workbench-curve-analysis.mjs');
 const data={topology:{bodies:[{body_id:2,member_id:'shaft',edges:[{index:4,curvature:{available:true,samples:[{point:[1,2,3],normal:[-1,0,0],curvature:.25},{point:[4,5,6],normal:[0,1,0],curvature:.5}]}}]}]}};
 const result=curvatureComb(data,{gain:8,density:1});
 assert.deepEqual(result.bodies[0].positions,[1,2,3,-1,2,3,4,5,6,4,9,6]);
 assert.equal(result.bodies[0].bodyId,2);assert.equal(result.bodies[0].memberId,'shaft');
 assert.equal(result.teeth,2);assert.deepEqual(curvatureComb(data,{gain:8,density:2}).bodies[0].positions,[1,2,3,-1,2,3]);
 assert.equal(curvatureComb(data,{gain:0,density:1}).bodies.length,0);
 assert.equal(curvatureComb({meshes:[]},{gain:8,density:1}).available,false);
});

test('curvature view preferences are finite, bounded and isolated by project',()=>{
 const prefs=new CADPreferences({storage:{getItem:()=>null,setItem:()=>{}}});
 const saved=prefs.save('alice','curve',{comb:true,combGain:25,combDensity:4});
 assert.equal(saved.comb,true);assert.equal(saved.combGain,25);assert.equal(saved.combDensity,4);
 assert.equal(prefs.load('alice','other').comb,false);
 const invalid=prefs.save('alice','curve',{comb:'true',combGain:Infinity,combDensity:-5});
 assert.equal(invalid.comb,false);assert.equal(invalid.combGain,20);assert.equal(invalid.combDensity,1);
});

test('3D visibility maps exact native references to saved board sides and preserves source meshes',()=>{
 const source={size:[30,20,8],meshes:[{name:'PCB',group:'board'},{name:'J1',group:'parts'},{name:'R2 pad',group:'board'},{name:'R20',group:'parts'},{name:'Unresolved STEP body',group:'parts'}]},copy=structuredClone(source);
 const data=prepareCADData(source,{components:[{ref:'J1',placement:{side:'back'}},{ref:'R2',placement:{side:'front'}}]});
 assert.deepEqual(data.meshes.map(m=>[m.name,m.group,m.side||null]),[['PCB','board',null],['J1','parts','bottom'],['R2 pad','parts','top'],['R20','parts',null],['Unresolved STEP body','parts',null]]);
 assert.deepEqual(source,copy);
});

test('3D preferences survive reload without leaking to a different project or account',()=>{
 const values=new Map(),storage={getItem:k=>values.get(k),setItem:(k,v)=>values.set(k,v)};
 const a=new CADPreferences({storage});a.save('alice','board-a',{style:'xray',projection:'orthographic',top:false,grid:false,sectionAxis:'z',sectionRatio:.25});
 const b=new CADPreferences({storage});assert.equal(b.load('alice','board-a').top,false);assert.equal(b.load('alice','board-a').sectionRatio,.25);assert.equal(b.load('alice','board-b').top,true);assert.equal(b.load('bob','board-a').top,true);assert.equal(b.load('alice','board-b').style,'realistic');assert.equal(b.load('alice','board-b').projection,'perspective');
 const mutable=b.load('alice','board-a');mutable.top=true;assert.equal(b.load('alice','board-a').top,false);
});

test('untrusted 3D preferences cannot supply render enums, truthy strings or nonfinite clipping',()=>{
 const p=new CADPreferences({storage:{getItem:()=>null,setItem:()=>{}}});
 const value=p.save('u','p',{style:'<svg>',projection:'unknown',top:'false',grid:0,sectionAxis:'w',sectionRatio:Infinity});
 assert.equal(value.style,'realistic');assert.equal(value.projection,'perspective');assert.equal(value.top,true);assert.equal(value.grid,true);assert.equal(value.sectionAxis,'none');assert.equal(value.sectionRatio,.5);
 assert.equal(p.save('u','p',{sectionRatio:-5}).sectionRatio,0);assert.equal(p.save('u','p',{sectionRatio:5}).sectionRatio,1);
});

test('storage denial retains recent 3D settings and notices once for the same owner',()=>{
 const notices=[],p=new CADPreferences({storage:{getItem:()=>null,setItem:()=>{throw Error('denied')}},toast:m=>notices.push(m)});
 p.save('alice','a',{bottom:false});p.save('alice','a',{bottom:false,grid:false});assert.equal(p.load('alice','a').bottom,false);assert.equal(p.load('alice','a').grid,false);assert.equal(notices.length,1);
 for(let i=0;i<140;i++)p.save('alice','p'+i,{top:false});assert.ok(p.memory.size<=128);assert.ok(p.warned.size<=128);
});
