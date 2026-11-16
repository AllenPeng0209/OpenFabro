export function prepareCADData(data,spec){
 const refs=new Map((spec?.components||[]).map(c=>[c.ref,c]));
 return{...data,meshes:data.meshes.map(mesh=>{
  const component=refs.get(mesh.name)||refs.get(mesh.name.endsWith(' pad')?mesh.name.slice(0,-4):null);
  return{...mesh,group:component||mesh.group==='board'&&mesh.name.startsWith('Parts')?'parts':mesh.group,side:component?(component.placement?.side==='back'?'bottom':'top'):null};
 })};
}
export const CAD_DEFAULTS=Object.freeze({style:'realistic',projection:'perspective',top:true,bottom:true,grid:true,shortcutBar:true,board:true,parts:true,base:true,lid:true,sectionAxis:'none',sectionRatio:.5,comb:false,combGain:20,combDensity:1,combInflections:false,combJumps:false,surfaceMode:'off',surfaceMetric:'max_abs',surfaceRange:.25,zebraDensity:12,zebraAngle:0});
function normalize(value){return Object.fromEntries(Object.entries(CAD_DEFAULTS).map(([key,initial])=>[key,
 typeof initial==='boolean'?typeof value?.[key]==='boolean'?value[key]:initial:
 key==='combGain'?Number.isFinite(value?.[key])?Math.max(0,Math.min(200,value[key])):initial:
 key==='combDensity'?Number.isFinite(value?.[key])?Math.max(1,Math.min(16,Math.round(value[key]))):initial:
 key==='surfaceRange'?Number.isFinite(value?.[key])?Math.max(.001,Math.min(10000,value[key])):initial:
 key==='zebraDensity'?Number.isFinite(value?.[key])?Math.max(2,Math.min(64,value[key])):initial:
 key==='zebraAngle'?Number.isFinite(value?.[key])?Math.max(-180,Math.min(180,value[key])):initial:
 key==='sectionRatio'?Number.isFinite(value?.[key])?Math.max(0,Math.min(1,value[key])):initial:
 ({style:['blueprint','xray','solid','realistic'],projection:['perspective','orthographic'],sectionAxis:['none','x','y','z'],surfaceMode:['off','zebra','curvature'],surfaceMetric:['max_abs','mean','gaussian','min','max']}[key]||[]).includes(value?.[key])?value[key]:initial]));}
export class CADPreferences{
 constructor({storage,toast=()=>{}}={}){this.memory=new Map();this.warned=new Set();this.toast=toast;if(storage)this.storage=storage;else try{this.storage=globalThis.localStorage;}catch{}}
 key(user,pid){return'wb-cad-view:'+encodeURIComponent(user||'device')+':'+encodeURIComponent(pid||'reference');}
 cache(key,value){this.memory.delete(key);this.memory.set(key,value);while(this.memory.size>128)this.memory.delete(this.memory.keys().next().value);}
 load(user,pid){const key=this.key(user,pid);if(this.memory.has(key)){const value=this.memory.get(key);this.cache(key,value);return{...value};}let settings={};try{const raw=this.storage?.getItem(key);if(raw&&raw.length<=2048){const value=JSON.parse(raw);if(value?.schema===1)settings=value.settings;}}catch{}const value=normalize(settings);this.cache(key,value);return{...value};}
 save(user,pid,settings){const key=this.key(user,pid),value=normalize(settings);this.cache(key,value);try{if(!this.storage)throw Error('Storage unavailable');this.storage.setItem(key,JSON.stringify({schema:1,settings:value}));}catch{if(!this.warned.has(key)){this.warned.add(key);while(this.warned.size>128)this.warned.delete(this.warned.values().next().value);this.toast('3D settings are kept for recent views in this session; browser storage is unavailable.');}}return{...value};}
}
