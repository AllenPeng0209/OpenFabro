import {LayerKeys,LayerPreferences,COPPER_FEATURES,APERTURE_LAYERS,LAYER_COLORS,layerDisplayContext} from './workbench-layers.mjs';
import {compileNativeLayer,paintNativeLayer} from './workbench-native-layers.mjs';
import {esc,icon} from './workbench-icons.mjs';

const names={mechanical:'Mechanical layers',top:'Top Layer',bottom:'Bottom Layer','F.Cu':'Top Copper','B.Cu':'Bottom Copper','F.SilkS':'Top Silkscreen','B.SilkS':'Bottom Silkscreen','F.Mask':'Top Solder Mask','B.Mask':'Bottom Solder Mask','F.Paste':'Top Solder Paste','B.Paste':'Bottom Solder Paste',refs:'Labels',ratsnest:'Airwires',zoneOutlines:'Polygon & Zone Outlines',outline:'Board outline',courtyards:'Courtyards',grid:'Grid',pads:'Pads',vias:'Vias',zones:'Copper fills','F.Fab':'Front fabrication','B.Fab':'Back fabrication',fills:'Fills',polygons:'Polygons',traces:'Traces'};
const label=key=>names[key]||(/^In(\d+)\.Cu$/.test(key)?'Mid-Layer '+/^In(\d+)\.Cu$/.exec(key)[1]:key);
const attribute=layer=>'data-native-layer-'+layer.toLowerCase().replace('.','-');

export class LayersUI{
 constructor({state,api,toast,interacting=()=>false,changed=()=>{},visibilityToken=()=>null,openLayout=()=>{}}){
  Object.assign(this,{state,api,toast,interacting,onChanged:changed,visibilityToken,openLayout});this.preferences=new LayerPreferences({toast});this.cache=new Map();this.frame=null;
  this.keys=new LayerKeys({model:()=>this.frame.model,scope:()=>this.scope(),ready:()=>this.ready(),changed:()=>this.changed(),prefix:mode=>this.prefix(mode)});
  document.addEventListener('pointerdown',event=>{this.keys.cancel();this.pointerActive=!!this.state().canvas?.host?.contains(event.target);},true);
  for(const name of ['pointerup','pointercancel'])document.addEventListener(name,()=>{this.pointerActive=false;queueMicrotask(()=>this.resume());},true);
  document.addEventListener('keyup',event=>{if(event.code==='Space'||event.code==='ShiftLeft'||event.code==='ShiftRight')queueMicrotask(()=>this.resume());});
  window.addEventListener('blur',()=>{this.pointerActive=false;this.keys.cancel();});
  window.addEventListener('focus',()=>queueMicrotask(()=>this.resume()));
 }
 user(){return this.state().session?.user?.id||'device';}
 scope(){const s=this.state();return JSON.stringify([this.user(),s.pid,s.projectLoadToken,s.viewToken,s.version,s.generation,s.canvas?.nativeIdentity?.render_inputs_sha256]);}
 ready(){const s=this.state(),f=this.frame;return!!(f&&s.canvas===f.canvas&&s.active==='layout'&&!s.starting&&!s.openingProject&&!s.nativePending&&f.canvas.nativeIdentity?.source_version===s.version&&!this.pointerActive&&!this.interacting());}
 key(event){if(this.state().active!=='layout'){this.keys.cancel();return false;}return this.keys.key(event);}
 cancelPrefix(){this.keys.cancel();}
 detach(){clearTimeout(this.prefixTimer);this.keys.cancel();if(this.frame)for(const request of this.frame.pending.values())request.abort();this.frame=null;}
 attach(canvas,identity){
  this.detach();const s=this.state();canvas.nativeIdentity=identity;
  const model=this.preferences.load(this.user(),s.pid,canvas.geo,{grid:s.grid,ratsnest:canvas.baseRatsnest});
  const hidden=this.hiddenObjects(canvas);this.frame={canvas,model,user:this.user(),pid:s.pid,scope:this.scope(),pending:new Map(),errors:new Map(),deferred:new Set(),metadata:new Map(),hidden,visibility:JSON.stringify(hidden),maskSource:this.visibilityToken()};canvas.layerRules=model;canvas.layerColors=LAYER_COLORS;canvas.nativeLayerPaths=new Map();canvas.opts.paintNativeLayer=paintNativeLayer;this.sync();
 }
 capture(canvas){
  const f=this.frame;if(!f||canvas!==f.canvas||!this.valid(f))throw Error('The PCB view changed. Refresh Layout and start Markup again.');
  return layerDisplayContext(f.model,{pid:f.pid,version:this.state().version,native:canvas.nativeIdentity,hidden:f.hidden,paths:canvas.nativeLayerPaths,metadata:f.metadata,pending:f.pending,deferred:f.deferred,errors:f.errors});
 }
 hiddenObjects(canvas){const hidden={};for(const kind of ['footprints','pads','vias','tracks','arcs','drawings','outline','zone_definitions'].sort()){const ids=(canvas.geo[kind]||[]).filter(item=>canvas.opts.isVisible?.(kind,item)===false).map(item=>item.id).filter(id=>typeof id==='string');if(ids.length)hidden[kind]=[...new Set(ids)].sort();}return hidden;}
 visibilityChanged(){
  const f=this.frame;if(!f||this.state().canvas!==f.canvas)return;const token=this.visibilityToken();if(token&&token===f.maskSource)return;f.maskSource=token;
  const hidden=this.hiddenObjects(f.canvas),signature=JSON.stringify(hidden);if(signature===f.visibility)return;
  this.keys.cancel();for(const request of f.pending.values())request.abort();f.pending.clear();f.errors.clear();f.deferred.clear();f.metadata.clear();f.canvas.nativeLayerPaths.clear();f.hidden=hidden;f.visibility=signature;this.sync();
 }
 sync(){
  const f=this.frame;if(!f)return;const s=this.state(),m=f.model;
  f.canvas.layers=new Set([...m.ids].filter(k=>!k.includes('/')&&!m.groups[k]&&m.isVisible(k)));f.canvas.showGrid=m.isVisible('grid');s.grid=f.canvas.showGrid;
  s.hiddenLayers=new Set(m.hidden);s.layerOverrides=new Map([...m.ids].filter(k=>!k.includes('/')&&!m.groups[k]).map(k=>[k,m.isVisible(k)]));
  f.canvas.host.dataset.focusLayer=m.focused||'';f.canvas.draw();
  this.renderTree();if(this.ready())for(const layer of APERTURE_LAYERS){if(m.isVisible(layer))this.loadNative(layer);else{f.pending.get(layer)?.abort();f.pending.delete(layer);f.canvas.host.setAttribute(attribute(layer),'hidden');}}
 }
 changed(){if(!this.ready())return false;const f=this.frame;this.preferences.save(f.user,f.pid,f.model);this.sync();this.onChanged(f.model,f.canvas);return true;}
 act(action){if(!this.ready()){this.toast('Wait for the current PCB view to finish loading.');this.renderTree();return;}action(this.frame.model);this.changed();}
 valid(frame){const s=this.state();return this.frame===frame&&s.canvas===frame.canvas&&this.scope()===frame.scope&&s.active==='layout'&&!s.starting&&!s.openingProject&&!s.nativePending&&frame.canvas.nativeIdentity?.source_version===s.version;}
 resume(){if(this.frame?.deferred.size&&this.ready())this.sync();}
 async loadNative(layer,retry=false){
  const f=this.frame;if(!f||!this.valid(f)||!this.ready()||!f.model.isVisible(layer)||f.pending.has(layer))return;
  if(retry){f.errors.delete(layer);f.metadata.delete(layer);f.canvas.nativeLayerPaths.delete(layer);}
  if(f.canvas.nativeLayerPaths.has(layer)){const paths=f.canvas.nativeLayerPaths.get(layer);f.canvas.host.setAttribute(attribute(layer),'ready');f.canvas.host.setAttribute(attribute(layer)+'-paths',String(paths.length));return;}
  if(f.errors.has(layer))return;
  const identity=f.canvas.nativeIdentity,visibility=f.visibility,hidden=f.hidden,key=f.user+':'+f.pid+':'+identity.render_inputs_sha256+':'+layer+':'+visibility;
  if(this.cache.has(key)){const {paths,meta}=this.cache.get(key);f.deferred.delete(layer);f.canvas.nativeLayerPaths.set(layer,paths);f.metadata.set(layer,meta);f.canvas.host.setAttribute(attribute(layer),'ready');f.canvas.host.setAttribute(attribute(layer)+'-paths',String(paths.length));f.canvas.draw();return;}
  const controller=new AbortController();f.pending.set(layer,controller);f.canvas.host.setAttribute(attribute(layer),'loading');this.renderTree();
  try{
   const visibilityHash=[...new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(visibility)))].map(v=>v.toString(16).padStart(2,'0')).join('');
   if(!this.valid(f)||controller.signal.aborted||f.visibility!==visibility)return;
   const meta=await this.api(`/api/workbench/projects/${f.pid}/layer-preview`,{method:'POST',body:{layer,hidden},signal:controller.signal});
   if(meta.source_version!==identity.source_version||meta.pcb_sha256!==identity.pcb_sha256||meta.render_inputs_sha256!==identity.render_inputs_sha256||meta.visibility_sha256!==visibilityHash||meta.coordinate_space!=='pcb-mm')throw Error('This layer no longer matches the displayed PCB or visible objects. Refresh Layout.');
   const text=await this.api(meta.url,{signal:controller.signal});if(!this.valid(f)||controller.signal.aborted||!f.model.isVisible(layer)||f.visibility!==visibility)return;
   const digest=[...new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(text)))].map(v=>v.toString(16).padStart(2,'0')).join('');
   if(!this.valid(f)||controller.signal.aborted||!f.model.isVisible(layer)||f.visibility!==visibility)return;
   if(digest!==meta.svg_sha256)throw Error('The native layer file changed after it was selected. Refresh or retry.');
   const paths=compileNativeLayer(text);this.cache.set(key,{paths,meta});while(this.cache.size>8)this.cache.delete(this.cache.keys().next().value);
   if(!this.ready()){f.deferred.add(layer);f.canvas.host.setAttribute(attribute(layer),'waiting');return;}
   f.deferred.delete(layer);
   f.canvas.nativeLayerPaths.set(layer,paths);f.metadata.set(layer,meta);f.canvas.host.setAttribute(attribute(layer),'ready');f.canvas.host.setAttribute(attribute(layer)+'-paths',String(paths.length));f.canvas.draw();
  }catch(error){if(error.name!=='AbortError'&&this.valid(f)&&!controller.signal.aborted){f.errors.set(layer,error.message);f.canvas.host.setAttribute(attribute(layer),'error');this.toast(error.message,true);}}
  finally{if(f.pending.get(layer)===controller)f.pending.delete(layer);if(this.frame===f)this.renderTree();}
 }
 prefix(mode){clearTimeout(this.prefixTimer);this.prefixMode=mode;const hint=document.querySelector('#layerKeyHint');if(hint){hint.hidden=!mode;hint.textContent=mode?`${mode==='focus'?'Focus':'Show / hide'}: D L A Z O P M · copper number${mode==='toggle'?' · F fills':''}`:'';}if(mode)this.prefixTimer=setTimeout(()=>this.keys.cancel(),1450);}
 panel(){
  if(this.state().active!=='layout')return'<p class="drawer-description">Open Layout to view the PCB layers.</p><button class="secondary-button" data-open-layer-layout>Open Layout</button>';
  if(!this.frame)return'<p class="drawer-description" role="status">Loading the current PCB layers…</p>';
  return `<div class="pcb-layer-toolbar"><strong>Layers</strong><button class="icon-button" data-layer-action="fills" aria-label="Toggle all copper fills" title="Toggle all copper fills (H, F)">${icon('droplet')}</button><button class="icon-button" data-layer-action="show" aria-label="Show all PCB layers" title="Show all layers">${icon('eye')}</button></div><small id="layerKeyHint" class="layer-key-hint" hidden></small><div id="pcbLayerTree"></div>`;
 }
 mount(host){
  host.querySelector('[data-open-layer-layout]')?.addEventListener('click',()=>this.openLayout());
  host.onkeydown=event=>{if(event.target.closest('[data-layer-action]')&&[' ','Enter'].includes(event.key))event.stopPropagation();};
  host.querySelector('[data-layer-action="fills"]')?.addEventListener('click',()=>this.act(m=>m.toggleAllFills()));
  host.querySelector('[data-layer-action="show"]')?.addEventListener('click',()=>this.act(m=>{for(const key of m.ids)if(!m.groups[key]&&!key.includes('/'))m.setVisible(key,true);}));this.renderTree();
 }
 renderTree(){
  const tree=document.querySelector('#pcbLayerTree'),f=this.frame;if(!tree||!f||this.state().active!=='layout')return;const m=f.model,disabled=!this.ready();
  const row=(key,depth=0)=>{
   const state=m.state(key),split=m.split(key),text=split?label(split[1]):label(key),expand=!!m.groups[key]||m.copper.includes(key),color=LAYER_COLORS[split?.[0]||key]||'#809c8d';
   const title=split?label(split[0])+' '+text:text;
   let html=`<div class="pcb-layer-row${m.focused===key?' focused':''}${state==='hidden'?' hidden-layer':''}" data-layer-row="${esc(key)}" data-layer-row-visibility="${state}" style="--layer-depth:${depth};--layer-color:${color}"><button class="pcb-layer-name" data-focus-layer="${esc(key)}" aria-label="Focus ${esc(title)}" aria-pressed="${m.focused===key}" ${disabled?'disabled':''}><span class="pcb-layer-dot">${m.groups[key]?icon(key==='mechanical'?'settings':'layers'):''}</span><span>${esc(text)}</span></button><label class="pcb-layer-eye ${state==='hidden'?'off':''}" title="${state==='hidden'?'Show':'Hide'} ${esc(title)}"><input type="checkbox" data-layer="${esc(key)}" ${split?`data-layer-feature="${esc(split[1])}" data-feature-layer="${esc(split[0])}"`:''} aria-label="Show ${esc(title)}" ${state!=='hidden'?'checked':''} ${disabled?'disabled':''}>${icon('eye')}</label>${expand?`<button class="icon-button pcb-layer-expand" data-expand-layer="${esc(key)}" aria-label="${m.expanded.has(key)?'Collapse':'Expand'} ${esc(text)}" aria-expanded="${m.expanded.has(key)}">${icon(m.expanded.has(key)?'chevronDown':'chevronRight')}</button>`:'<span class="pcb-layer-expand-space"></span>'}</div>`;
   if(expand&&m.expanded.has(key))html+=(m.groups[key]||COPPER_FEATURES.map(feature=>key+'/'+feature)).map(child=>row(child,depth+1)).join('');
   if(f.errors.has(key))html+=`<div class="pcb-layer-message"><span>${esc(f.errors.get(key))}</span><button class="secondary-button" data-layer-retry="${esc(key)}">Retry</button></div>`;
   else if(f.pending.has(key))html+='<div class="pcb-layer-message" role="status">Loading native apertures…</div>';
   else if(f.deferred.has(key))html+='<div class="pcb-layer-message" role="status">Finish the current gesture to display this layer.</div>';
   return html;
  };
  const active=document.activeElement?.closest('[data-layer],[data-focus-layer],[data-expand-layer]'),restore=active&&tree.contains(active)?{type:active.hasAttribute('data-layer')?'data-layer':active.hasAttribute('data-focus-layer')?'data-focus-layer':'data-expand-layer',key:active.getAttribute(active.hasAttribute('data-layer')?'data-layer':active.hasAttribute('data-focus-layer')?'data-focus-layer':'data-expand-layer')}:null;
  tree.innerHTML=row('mechanical')+'<div class="pcb-layer-divider"></div>'+row('top')+m.copper.filter(l=>/^In/.test(l)).map(l=>row(l,1)).join('')+'<div class="pcb-layer-divider"></div>'+row('bottom')+'<div class="pcb-layer-heading">Display</div>'+['ratsnest','refs','zoneOutlines','grid'].map(k=>row(k)).join('')+`<details class="pcb-layer-extra" ${m.expanded.has('filters')?'open':''}><summary>Geometry filters</summary>`+['pads','vias','zones'].map(k=>row(k)).join('')+'</details>';
  for(const input of tree.querySelectorAll('[data-layer]')){input.indeterminate=m.state(input.dataset.layer)==='mixed';input.onchange=()=>this.act(model=>model.toggle(input.dataset.layer));}
  for(const button of tree.querySelectorAll('[data-focus-layer]'))button.onclick=()=>this.act(model=>model.focus(button.dataset.focusLayer));
  for(const button of tree.querySelectorAll('[data-expand-layer]'))button.onclick=()=>{const key=button.dataset.expandLayer;m.expanded.has(key)?m.expanded.delete(key):m.expanded.add(key);this.preferences.save(f.user,f.pid,m);this.renderTree();};
  for(const button of tree.querySelectorAll('[data-layer-retry]'))button.onclick=()=>this.loadNative(button.dataset.layerRetry,true);
  tree.querySelector('.pcb-layer-extra').ontoggle=event=>{if(!event.currentTarget.isConnected)return;event.currentTarget.open?m.expanded.add('filters'):m.expanded.delete('filters');this.preferences.save(f.user,f.pid,m);};
  tree.onkeydown=event=>{if(event.target.closest('button')&&[' ','Enter'].includes(event.key))event.stopPropagation();};
  if(restore)for(const el of tree.querySelectorAll('['+restore.type+']'))if(el.getAttribute(restore.type)===restore.key){el.focus({preventScroll:true});break;}
 }
}
