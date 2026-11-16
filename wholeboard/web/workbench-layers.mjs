export const COPPER_FEATURES=['fills','polygons','pads','traces','vias'];
export const APERTURE_LAYERS=['F.Mask','B.Mask','F.Paste','B.Paste'];
export const LAYER_COLORS={'F.Cu':'#ff0000','B.Cu':'#3939ff','In1.Cu':'#ffce00','In2.Cu':'#00bdff','In3.Cu':'#c45ad6','In4.Cu':'#5ad6d0','F.SilkS':'#00ffff','B.SilkS':'#ff00ff','F.Mask':'#1dbc6c','B.Mask':'#90f490','F.Paste':'#e39ce5','B.Paste':'#98cbe8',mechanical:'#4caf50',top:'#ff0000',bottom:'#3939ff'};
const surface=['F.SilkS','F.Paste','F.Mask','B.Mask','B.Paste','B.SilkS'];
const common=['outline','courtyards','refs','ratsnest','grid','pads','vias','zones','zoneOutlines','F.Fab','B.Fab'];
const defaults=['F.Fab','B.Fab','courtyards',...APERTURE_LAYERS,'grid'];
const displayKeys=['grid','ratsnest','refs','zoneOutlines','pads','vias','zones','outline','courtyards'];

export function layerDisplayContext(model,{pid,version,native,hidden,paths,metadata,pending,deferred,errors}){
 const layers={};for(const layer of model.ids){if(layer.includes('/')||model.groups[layer]||displayKeys.includes(layer)||layer==='filters')continue;layers[layer]={visible:model.isVisible(layer),...(model.copper.includes(layer)?{features:Object.fromEntries(COPPER_FEATURES.map(f=>[f,model.feature(layer,f)]))}:{})};}
 const apertures=APERTURE_LAYERS.map(layer=>{
  const status=!model.isVisible(layer)?'hidden':errors.has(layer)?'error':deferred.has(layer)?'waiting':paths.has(layer)&&metadata.has(layer)?'ready':pending.has(layer)?'loading':'unavailable';
  const meta=metadata.get(layer);return{layer,status,...(status==='ready'?{client_path_count:paths.get(layer).length,svg_sha256:meta.svg_sha256,visibility_sha256:meta.visibility_sha256}:{})};
 });
 return structuredClone({schema:1,project_id:pid,design_version:version,view:'layout',native:Object.fromEntries(['source_version','pcb_sha256','render_inputs_sha256'].map(k=>[k,native[k]])),focus:model.focused,dim_opacity:.2,layers,display:Object.fromEntries(displayKeys.map(k=>[k,model.isVisible(k)])),hidden_objects:hidden,apertures});
}

export class LayerState{
 constructor(geo,prefs={},initial={}){
  this.geo=geo;this.copper=(geo.layers||[]).filter(l=>/^(F|B|In\d+)\.Cu$/.test(l));
  this.groups={top:['F.SilkS','F.Paste','F.Mask','F.Cu'].filter(l=>l!=='F.Cu'||this.copper.includes(l)),bottom:['B.Cu','B.Mask','B.Paste','B.SilkS'].filter(l=>l!=='B.Cu'||this.copper.includes(l)),mechanical:[...new Set(['outline','courtyards','F.Fab','B.Fab',...(geo.drawing_layers||[]).filter(l=>!this.copper.includes(l)&&!surface.includes(l))])]};
  this.ids=new Set([...this.copper,...surface,...common,'filters',...(geo.drawing_layers||[]),...Object.keys(this.groups),...this.copper.flatMap(l=>COPPER_FEATURES.map(f=>l+'/'+f))]);
  this.hidden=new Set((prefs.schema===1&&Array.isArray(prefs.hidden)?prefs.hidden:defaults).filter(k=>typeof k==='string'&&this.ids.has(k)));
  if(prefs.schema!==1){if(initial.grid)this.hidden.delete('grid');if(initial.ratsnest===false)this.hidden.add('ratsnest');}
  this.disabled=new Map(this.copper.map(l=>[l,new Set((Array.isArray(prefs.features?.[l])?prefs.features[l]:[]).filter(f=>COPPER_FEATURES.includes(f)))]));
  this.focused=typeof prefs.focus==='string'&&this.ids.has(prefs.focus)?prefs.focus:null;
  this.expanded=new Set((Array.isArray(prefs.expanded)?prefs.expanded:['top','bottom','filters']).filter(k=>this.ids.has(k)));
 }
 number(n){return Number.isInteger(Number(n))?this.copper[Number(n)-1]||null:null;}
 members(key){return this.groups[key]||[key];}
 split(key){const at=key.indexOf('/');return at<0?null:[key.slice(0,at),key.slice(at+1)];}
 feature(layer,name){return this.copper.includes(layer)&&COPPER_FEATURES.includes(name)&&!this.disabled.get(layer).has(name);}
 state(key){
  if(!this.ids.has(key))return'hidden';
  if(this.groups[key]){const values=this.groups[key].map(k=>this.state(k));return values.every(v=>v==='hidden')?'hidden':values.every(v=>v==='visible')?'visible':'mixed';}
  const feature=this.split(key);if(feature)return !this.hidden.has(feature[0])&&this.feature(...feature)?'visible':'hidden';
  if(this.hidden.has(key))return'hidden';
  if(this.copper.includes(key)){const count=COPPER_FEATURES.filter(f=>this.feature(key,f)).length;return count===0?'hidden':count===5?'visible':'mixed';}
  return'visible';
 }
 isVisible(key){return this.state(key)!=='hidden';}
 setVisible(key,on){
  if(!this.ids.has(key))return false;
  if(this.groups[key]){for(const k of this.groups[key])this.setVisible(k,on);return true;}
  const feature=this.split(key);if(feature)return this.setFeature(...feature,on);
  if(on){this.hidden.delete(key);if(this.copper.includes(key)&&COPPER_FEATURES.every(f=>!this.feature(key,f)))this.disabled.set(key,new Set());}
  else this.hidden.add(key);return true;
 }
 toggle(key){return this.setVisible(key,!this.isVisible(key));}
 setFeature(layer,name,on){if(!this.copper.includes(layer)||!COPPER_FEATURES.includes(name))return false;on?this.disabled.get(layer).delete(name):this.disabled.get(layer).add(name);if(on)this.hidden.delete(layer);return true;}
 toggleAllFills(){const on=!this.copper.every(l=>this.feature(l,'fills'));for(const l of this.copper)on?this.disabled.get(l).delete('fills'):this.disabled.get(l).add('fills');return true;}
 focus(key){if(!this.ids.has(key))return false;if(this.focused===key)this.focused=null;else{this.setVisible(key,true);this.focused=key;}return true;}
 padLayers(p){return this.copper.filter(l=>p.layers?.includes('*.Cu')||p.layers?.includes(l)||!p.layers?.length&&(l==='F.Cu'&&p.front||l==='B.Cu'&&p.back));}
 viaLayers(v){if(!v.layers?.length)return this.copper;const indices=v.layers.map(l=>this.copper.indexOf(l)).filter(i=>i>=0);return indices.length?this.copper.slice(Math.min(...indices),Math.max(...indices)+1):[];}
 enabled(layer,feature){return this.isVisible(layer)&&this.feature(layer,feature);}
 visible(kind,item={},layer){
  if(kind==='board')return true;
  if(kind==='pads'){if(this.hidden.has('pads'))return false;if(item.kind==='np_thru_hole'||!layer&&item.kind==='thru_hole'&&item.drill>0)return true;return this.padLayers(item).filter(l=>!layer||l===layer).some(l=>this.enabled(l,'pads'));}
  if(kind==='vias')return !this.hidden.has('vias')&&this.viaLayers(item).filter(l=>!layer||l===layer).some(l=>this.enabled(l,'vias'));
  if(kind==='tracks'||kind==='arcs')return this.enabled(layer||item.layer,'traces');
  if(kind==='zones')return !this.hidden.has('zones')&&this.enabled(layer||item.layer,'fills');
  if(kind==='zone_definitions')return !this.hidden.has('zoneOutlines')&&(layer?[layer]:item.layers||[]).some(l=>this.enabled(l,'polygons'));
  if(kind==='drawings'){
   if(item.role==='reference'&&this.hidden.has('refs'))return false;
   if(/\.CrtYd$/.test(item.layer))return !this.hidden.has('courtyards');
   return this.isVisible(item.layer)&&(!this.copper.includes(item.layer)||this.feature(item.layer,'polygons'));
  }
  if(kind==='footprints')return (this.geo.pads||[]).some(p=>p.ref===item.ref&&this.visible('pads',p))||(this.geo.drawings||[]).some(d=>d.ref===item.ref&&this.visible('drawings',d))||!!item.court&&!this.hidden.has('courtyards')||!this.hidden.has('refs')&&!(this.geo.drawings||[]).some(d=>d.ref===item.ref&&d.role==='reference');
  const key={outline:'outline',nets:'ratsnest',labels:'refs',grid:'grid',courtyards:'courtyards',apertures:layer||item.layer}[kind];return key?this.isVisible(key):true;
 }
 domains(kind,item={},layer){
  if(kind==='pads')return ['pads',...(item.kind==='np_thru_hole'?['outline']:this.padLayers(item).filter(l=>this.enabled(l,'pads')).flatMap(l=>[l,l+'/pads']))];
  if(kind==='vias')return ['vias',...this.viaLayers(item).filter(l=>this.enabled(l,'vias')).flatMap(l=>[l,l+'/vias'])];
  if(kind==='zone_definitions')return(layer?[layer]:item.layers||[]).flatMap(l=>[l,l+'/polygons','zoneOutlines']);
  const l=layer||item.layer;
  if(l)return[l,...(kind==='tracks'||kind==='arcs'?[l+'/traces']:kind==='zones'?[l+'/fills','zones']:[]),...(item.role==='reference'?['refs']:[]),...(kind==='drawings'&&/\.CrtYd$/.test(l)?['courtyards']:[])];
  return[{labels:'refs',nets:'ratsnest' }[kind]||kind];
 }
 opacity(kind,item,layer){if(!this.focused||kind==='board')return 1;const wanted=this.members(this.focused);return this.domains(kind,item,layer).some(k=>wanted.includes(k))?1:.2;}
 serialize(){return{schema:1,hidden:[...this.hidden],features:Object.fromEntries([...this.disabled].map(([l,values])=>[l,[...values]])),focus:this.focused,expanded:[...this.expanded]};}
}

export class LayerKeys{
 constructor({model,scope,ready,changed,prefix=()=>{},clock=()=>Date.now()}){Object.assign(this,{model,scope,ready,changed,prefix,clock});this.pending=null;}
 cancel(){this.pending=null;this.prefix(null);}
 key(event){
  if(event.ctrlKey||event.metaKey||event.altKey||event.isComposing||event.target?.closest?.('input:not([type=checkbox]),textarea,select,[contenteditable=true],[role=menu],[role=treeitem]')){this.cancel();return false;}
  if(!this.ready()){this.cancel();return false;}
  if(event.code==='ShiftLeft'||event.code==='ShiftRight')return false;
  if(this.pending&&(this.pending.scope!==this.scope()||this.pending.until<this.clock())){this.cancel();return true;}
  if(event.repeat)return !!this.pending||/^(Digit|Numpad)[1-9]$/.test(event.code);
  const digit=/^(?:Digit|Numpad)([1-9])$/.exec(event.code),letter=/^Key([A-Z])$/.exec(event.code)?.[1],m=this.model();
  if(this.pending){
   event.preventDefault();const mode=this.pending.mode;this.cancel();if(event.key==='Escape')return true;
   if(letter==='F'&&mode==='toggle'){m.toggleAllFills();this.changed();return true;}
   const key=digit&&!event.shiftKey?m.number(Number(digit[1])):({D:'mechanical',L:'refs',A:'ratsnest',Z:'zoneOutlines',O:event.shiftKey?'B.SilkS':'F.SilkS',P:event.shiftKey?'B.Paste':'F.Paste',M:event.shiftKey?'B.Mask':'F.Mask'})[letter];
   if(key){mode==='focus'?m.focus(key):m.toggle(key);this.changed();}return true;
  }
  if(!event.shiftKey&&(letter==='L'||letter==='H')){event.preventDefault();this.pending={mode:letter==='L'?'focus':'toggle',scope:this.scope(),until:this.clock()+1400};this.prefix(this.pending.mode);return true;}
  if(digit&&!event.shiftKey){event.preventDefault();const key=m.number(Number(digit[1]));if(key){m.focus(key);this.changed();}return true;}
  return false;
 }
}

export class LayerPreferences{
 constructor({storage,toast=()=>{}}={}){this.toast=toast;this.memory=new Map();this.warned=new Set();if(storage)this.storage=storage;else try{this.storage=globalThis.localStorage;}catch{}}
 key(user,pid){return'wb-layer-view:'+encodeURIComponent(user||'device')+':'+encodeURIComponent(pid);}
 load(user,pid,geo,initial={}){
  const key=this.key(user,pid);let prefs=this.memory.get(key);
  if(!prefs)try{const raw=this.storage?.getItem(key);if(raw&&raw.length<=64000)prefs=JSON.parse(raw);}catch{}
  return new LayerState(geo,prefs&&typeof prefs==='object'?prefs:{},initial);
 }
 save(user,pid,model){
  const key=this.key(user,pid),prefs=model.serialize(),raw=JSON.stringify(prefs);if(raw.length>64000)return false;
  this.memory.set(key,prefs);while(this.memory.size>64)this.memory.delete(this.memory.keys().next().value);
  try{if(!this.storage)throw Error('Storage unavailable');this.storage.setItem(key,raw);}catch{if(!this.warned.has(key)){this.warned.add(key);this.toast('Layer settings are kept for this session; browser storage is unavailable.');}}
  return true;
 }
}
