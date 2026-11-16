import {esc,icon} from './workbench-icons.mjs';
import {constrainedPlate} from './workbench-sketch-model.mjs';
import {isModelFile,meshResources,fileData} from './workbench-mesh-files.mjs';

export function mountingPlate(name='Mounting plate'){
 return{schema:1,name,units:'mm',parameters:{width:{value:40,unit:'mm'},depth:{value:24,unit:'mm'},thickness:{value:4,unit:'mm'},hole_diameter:{value:3.2,unit:'mm'},corner_radius:{value:1,unit:'mm'}},features:[
  {id:'plate',op:'extrude',profile:{kind:'rectangle',width:'width',height:'depth'},vector:[0,0,'thickness']},
  {id:'hole1',op:'hole',target:'plate',origin:['width/4','depth/2',-1],diameter:'hole_diameter',depth:'thickness+2'},
  {id:'hole2',op:'hole',target:'hole1',origin:['width*3/4','depth/2',-1],diameter:'hole_diameter',depth:'thickness+2'},
  {id:'corners',op:'fillet',target:'hole2',radius:'corner_radius',edges:'vertical'}],result:'corners'};
}

const encoded=path=>path.split('/').map(encodeURIComponent).join('/');
const dimensions=asset=>asset.metrics.size_mm.map(n=>Number(n).toFixed(2)).join(' × ')+' mm';

export class MechanicalPartsUI{
 constructor(options){Object.assign(this,options);this.selection=new Map();this.selectionOwners=new Map();this.running=new Map();this.sequence=0;this.histories=new Map();this.historyReads=new Map();this.historyQueues=new Map();this.cadScope=new Set();this.intentGeneration=0;this.editorIdentity=null;}
 selectionKey(pid){const s=this.state();return 'wb-cad-model:'+encodeURIComponent(s.session?.user?.id||s.project?.access?.user?.id||'device')+':'+encodeURIComponent(pid);}
 current(){const pid=this.state().pid,key=this.selectionKey(pid);if(this.selectionOwners.has(pid)&&this.selectionOwners.get(pid)!==key)this.selection.delete(pid);this.selectionOwners.set(pid,key);if(!this.selection.has(pid))try{const raw=(this.storage||globalThis.localStorage)?.getItem(key);if(raw&&raw.length<1024){const saved=JSON.parse(raw),v=saved.value;if(saved.schema===1&&(v===null||v&&typeof v.source==='string'&&v.source.length<=240&&v.source.endsWith('.cad.json')&&(!v.assetId||/^[0-9a-f]{64}(?:-[0-9a-f]{12})?$/.test(v.assetId)))){this.selection.set(pid,v);if(v)this.cadScope.add(pid);}}}catch{}return this.selection.get(pid);}
 setSelection(pid,value){this.selection.set(pid,value);const key=this.selectionKey(pid);this.selectionOwners.set(pid,key);try{(this.storage||globalThis.localStorage)?.setItem(key,JSON.stringify({schema:1,value}));}catch{}}

 observeEditor(){const s=this.state(),key=JSON.stringify([s.pid,s.projectLoadToken,s.active]);if(this.editorIdentity!==null&&this.editorIdentity!==key)this.intentGeneration++;this.editorIdentity=key;}
 context(){this.observeEditor();const s=this.state();return{pid:s.pid,load:s.projectLoadToken,view:s.viewToken,active:s.active,intentGeneration:this.intentGeneration};}
 historyIntentCurrent(context){this.observeEditor();return this.same(context)&&context.intentGeneration===this.intentGeneration&&this.state().active===context.active;}
 same(c,view=false){const s=this.state();return s.pid===c.pid&&s.projectLoadToken===c.load&&!s.openingProject&&(!view||s.active==='3d'&&s.viewToken===c.view);}
 canWrite(){const s=this.state();return !this.picker?.active&&!this.picker?.opening&&this.editable()&&!this.busy()&&!this.running.has(s.pid)&&!this.interacting();}
 published(event){const s=this.state(),chosen=this.current(),part=this.inventory?.parts.find(p=>p.source===chosen?.source),assembly=part?.versions?.find(v=>v.asset_id===(chosen?.assetId||part.asset_id))?.metrics?.assembly;if(event.removed){if(chosen?.source===event.source)this.setSelection(s.pid,null);}else if(!chosen?.pinned&&(!assembly||chosen.source===event.source)){this.setSelection(s.pid,{source:event.source,assetId:event.asset_id});this.cadScope.add(s.pid);}this.pending=this.context();this.flush();}
 rememberHistory(pid,value){if(!value||!Number.isSafeInteger(value.revision))return;const old=this.histories.get(pid);if(!old||value.revision>=old.revision)this.histories.set(pid,value);if(this.state().pid===pid)this.sync();}
 historyChanged(event){this.rememberHistory(this.state().pid,event.history);if(this.current()){this.pending=this.context();this.flush();}}
 async refreshHistory(){const c=this.context(),key=c.pid+':'+c.load;if(this.historyReads.has(key))return this.historyReads.get(key);const pending=this.api(`/api/workbench/projects/${c.pid}/mechanical/history`).then(value=>{if(this.same(c))this.rememberHistory(c.pid,value);return value;}).finally(()=>this.historyReads.delete(key));this.historyReads.set(key,pending);return pending;}
 historyDomain(){const s=this.state();return s.active==='files'&&(s.currentFile?.path||s.openFilePath||'').endsWith('.cad.json')||s.active==='3d'&&(!!this.current()||this.cadScope.has(s.pid)||!s.spec.components.length&&((this.histories.get(s.pid)?.count||0)>0||(s.project?.mechanical_history?.entries?.length||0)>0));}
 handleUndo(redo=false){if(!this.historyDomain())return false;this.restoreHistory(redo).catch(error=>this.toast(error.message,true));return true;}
 hasCADdraft(){const s=this.state();return[...(s.fileDrafts?.keys()||[])].some(key=>key.startsWith(s.pid+':')&&key.endsWith('.cad.json'));}
 restoreHistory(redo=false){const context=this.context(),key=context.pid+':'+context.load,previous=this.historyQueues.get(key)||Promise.resolve();let pending;pending=previous.then(()=>this.historyIntentCurrent(context)&&this.historyDomain()?this.restoreHistoryStep(redo,context):undefined).finally(()=>{if(this.historyQueues.get(key)===pending)this.historyQueues.delete(key);});this.historyQueues.set(key,pending);return pending;}
 async restoreHistoryStep(redo,context){
  if(!this.canWrite()||this.modal||this.openingParameters)throw Error('Wait for the current editing action before restoring CAD history.');if(this.hasCADdraft())throw Error('Save or discard the CAD source draft before restoring its saved history.');
  const operation={};this.running.set(context.pid,operation);this.sync();
  try{
   await this.save();if(!this.same(context))return;
   const history=this.histories.get(context.pid)||await this.refreshHistory();if(!this.historyIntentCurrent(context)||!this.historyDomain())return;
   if(this.hasCADdraft())throw Error('Save or discard the CAD source draft before restoring its saved history.');
   if(this.running.get(context.pid)!==operation||!this.editable()||this.busy()||this.modal||this.openingParameters||this.interacting())throw Error('The editing state changed before CAD restoration. Try again when it is ready.');
   const direction=redo?'redo':'undo';
   if(!history['can_'+direction]){this.toast(history[direction+'_blocked_reason']||(redo?'Nothing to redo in CAD':'Nothing to undo in CAD'),!!history[direction+'_blocked_reason']);return;}
   const result=await this.api(`/api/workbench/projects/${context.pid}/mechanical/history/restore`,{method:'POST',body:{direction,revision:history.revision,entry_id:history[direction].id}});if(!this.same(context))return result;
   this.rememberHistory(context.pid,result.history);this.cadScope.add(context.pid);
   if(result.asset)this.setSelection(context.pid,{source:result.source,assetId:result.asset.asset_id});else if(this.current()?.source===result.source)this.setSelection(context.pid,null);
   const current=await this.api('/api/projects/'+context.pid);if(!this.same(context))return result;this.adopt(current.state);this.render();this.toast(redo?'CAD change restored':'CAD change undone');return result;
  }finally{if(this.running.get(context.pid)===operation)this.running.delete(context.pid);if(this.same(context))this.sync();}
 }
 deferRefresh(){if(this.current()&&this.state().active==='3d'&&this.interacting()){this.pending=this.context();return true;}return false;}
 flush(){if(!this.pending)return;if(!this.same(this.pending)){this.pending=null;return;}if(this.state().active!=='3d'||this.interacting()||this.modal)return;this.pending=null;this.render();}
 onViewChange(){this.observeEditor();this.picker?.onViewChange();this.features?.onViewChange();if(this.openingParameters&&(!this.same(this.openingParameters.context)||this.state().active!=='3d'))this.openingParameters=null;if(this.modal&&(!this.same(this.modal.context)||this.state().active!=='3d')){this.modal.element.close();this.modal=null;}}
 mount(host){
  this.onViewChange();const context=this.context(),sequence=++this.sequence;
  const bar=document.createElement('div');bar.className='mechanical-part-tools';bar.innerHTML='<span role="status">Loading mechanical parts…</span>';host.append(bar);
  const valid=()=>this.same(context,true)&&sequence===this.sequence&&bar.isConnected;
  this.api(`/api/workbench/projects/${context.pid}/mechanical`).then(data=>{
   if(!valid())return;
   this.inventory=data;
   this.rememberHistory(context.pid,data.history);
   const selected=this.current();
   if(selected){const current=data.parts.find(part=>part.source===selected.source);if(!current){this.setSelection(context.pid,null);this.render();return;}if(!selected.pinned&&selected.assetId!==current.asset_id)this.setSelection(context.pid,{...selected,assetId:current.asset_id});}
   if(!this.selection.has(context.pid)&&!this.state().spec.components.length&&data.parts.length){this.setSelection(context.pid,{source:data.parts[0].source});this.render();return;}
   this.paint(bar,data,context,valid);
  }).catch(error=>{if(valid()){bar.textContent=error.message;bar.setAttribute('role','alert');}});
 }
 paint(bar,data,context,valid){
  const chosen=this.current(),part=data.parts.find(p=>p.source===chosen?.source),versions=part?.versions||[],asset=chosen?.assetId?versions.find(v=>v.asset_id===chosen.assetId):versions.find(v=>v.asset_id===part.asset_id),historical=asset&&asset.asset_id!==part?.asset_id;
  bar.innerHTML=`${data.parts.length?`<select id="mechanicalModelSelect" aria-label="Mechanical model"><option value="">Board / enclosure</option>${data.parts.map(p=>`<option value="${esc(p.source)}" ${p===part?'selected':''}>${esc(p.name)}</option>`).join('')}</select>`:''}<button type="button" class="secondary-button" data-cad-history="undo" aria-label="Undo CAD change" title="Undo CAD change">${icon('undo')}</button><button type="button" class="secondary-button" data-cad-history="redo" aria-label="Redo CAD change" title="Redo CAD change">${icon('redo')}</button><button type="button" class="secondary-button" id="newMechanicalPart" aria-label="New mechanical part" data-mechanical-write>${icon('plus')}New part</button><button type="button" class="secondary-button" id="importMechanicalAsset">${icon('upload')}Import CAD</button>`+
   (part?`<select id="mechanicalVersionSelect" aria-label="Model version">${versions.map((v,i)=>`<option value="${esc(v.asset_id)}" ${v===asset?'selected':''}>Version ${i+1}${v.asset_id===part.asset_id?' · Current':''}</option>`).join('')}</select><button type="button" class="secondary-button" id="mechanicalCode">Edit CAD code</button><button type="button" class="secondary-button" id="mechanicalParameters" data-mechanical-write ${historical?'data-historical="true"':''}>Parameters</button><button type="button" class="secondary-button" id="mechanicalRebuild" data-mechanical-write ${historical?'data-historical="true"':''}>Rebuild from code</button>`:'')+
   (asset?`<a class="secondary-button" id="mechanicalStepDownload" href="${esc(asset.files.find(f=>f.name==='part.step').url)}" download="${esc(asset.name)}.step">STEP</a><details class="mechanical-export-menu"><summary>Exports</summary><div>${asset.files.filter(f=>['part.stl','part.obj','part.3mf','part.FCStd','report.json'].includes(f.name)).map(f=>`<a href="${esc(f.url)}" download="${esc(f.name)}">${esc(f.name)}</a>`).join('')}</div></details>`:'');
  this.host.classList.toggle('mechanical-parts-present',data.parts.length>0);
  const guard=fn=>()=>{if(valid())Promise.resolve().then(fn).catch(error=>this.toast(error.message,true));};
  bar.querySelector('#newMechanicalPart').onclick=guard(()=>this.newPart());
  bar.querySelector('#importMechanicalAsset').onclick=guard(()=>this.importAssets());
  const newAssembly=document.createElement('button');newAssembly.type='button';newAssembly.className='secondary-button';newAssembly.dataset.mechanicalWrite='';newAssembly.innerHTML=icon('plus')+'New assembly';newAssembly.onclick=guard(()=>this.assembly.open());bar.querySelector('#importMechanicalAsset').after(newAssembly);
  if(asset?.metrics.assembly){const mate=document.createElement('button');mate.type='button';mate.className='secondary-button';mate.dataset.mechanicalWrite='';mate.id='pickNativeMate';mate.textContent='Mate parts';mate.onclick=guard(()=>this.picker.open(asset,part));newAssembly.after(mate);const edit=document.createElement('button');edit.type='button';edit.className='secondary-button';edit.dataset.mechanicalWrite='';if(historical)edit.dataset.historical='true';edit.textContent='Edit assembly';edit.onclick=guard(()=>this.assembly.open(part));newAssembly.after(edit);this.assembly?.renderReview(this.host,asset,part,valid);}
  for(const button of bar.querySelectorAll('[data-cad-history]'))button.onclick=guard(()=>this.restoreHistory(button.dataset.cadHistory==='redo'));
  const select=bar.querySelector('#mechanicalModelSelect');if(select)select.onchange=()=>{if(!valid()||this.interacting())return;this.setSelection(context.pid,select.value?{source:select.value}:null);if(select.value)this.cadScope.add(context.pid);else this.cadScope.delete(context.pid);this.render();};
  if(part){
   if(asset){const features=document.createElement('button');features.type='button';features.className='secondary-button';features.textContent='Features';features.onclick=guard(()=>this.features.open(part,asset));bar.querySelector('#mechanicalParameters').before(features);}
   bar.querySelector('#mechanicalVersionSelect').onchange=e=>{if(!valid()||this.interacting())return;this.setSelection(context.pid,{source:part.source,assetId:e.target.value,pinned:e.target.value!==part.asset_id});this.render();};
   bar.querySelector('#mechanicalCode').onclick=guard(()=>this.openCode(part.source));
   bar.querySelector('#mechanicalParameters').onclick=guard(()=>this.parameters(part));
   bar.querySelector('#mechanicalRebuild').onclick=guard(()=>this.build(context,{path:part.source,expected_sha256:part.current_source_sha256}));
  }
  this.sync();
  if(!chosen)return;
  const status=this.host.querySelector('#mechanicalPartStatus');
  if(!asset){if(status)status.textContent=part?.asset_error||'This model revision is unavailable. Rebuild from its current source.';return;}
  const scene=asset.files.find(f=>f.name==='scene.json');
  fetch(scene.url).then(async response=>{
   if(!response.ok)throw Error('Could not load this native mechanical model.');
   const bytes=await response.arrayBuffer(),digest=[...new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))].map(n=>n.toString(16).padStart(2,'0')).join('');
   if(digest!==scene.sha256)throw Error('The native mechanical mesh changed. Rebuild a new model revision.');
   const mesh=JSON.parse(new TextDecoder().decode(bytes));
   if(!valid())return;
   mesh.mechanical_asset_id=asset.asset_id;this.replaceMesh(mesh);this.sync();const currentStatus=this.host.querySelector('#mechanicalPartStatus');
   if(currentStatus)currentStatus.textContent=(historical?'Earlier model':part.stale?'Source changed · showing saved model':asset.metrics.geometry_provenance==='faceted-mesh-input'?'Mesh-based solid':'Verified solid')+' · '+dimensions(asset);
   const caption=this.host.querySelector('.view-caption');if(caption){caption.textContent=`${asset.metrics.solids} solid${asset.metrics.solids===1?'':'s'} · ${Number(asset.metrics.volume_mm3).toFixed(2)} mm³${asset.metrics.mass_properties?'':' (kernel estimate)'} · STEP verified`;caption.title=asset.metrics.mass_properties?'Adaptive, span-aware STEP mass properties; no material density inferred.':'Default kernel mass estimate. Rebuild a new revision for adaptive mass verification.';}
  }).catch(error=>{if(valid()&&status){status.textContent=error.message;status.setAttribute('role','alert');}});
 }
 sync(){for(const button of this.host.querySelectorAll('[data-mechanical-write]'))button.disabled=!this.canWrite()||!!this.modal||!!this.openingParameters||button.dataset.historical==='true';const h=this.histories.get(this.state().pid);for(const button of this.host.querySelectorAll('[data-cad-history]')){const direction=button.dataset.cadHistory;button.disabled=!this.canWrite()||!!this.modal||!!this.openingParameters||this.hasCADdraft()||!h?.['can_'+direction];button.title=(h?.[direction]?.label||'CAD '+direction)+(h?.[direction]?.source?' · '+h[direction].source:'');}const build=this.host.querySelector('#buildCADSource');if(build)build.disabled=!this.canWrite()||this.hasCADdraft();if(this.pending)queueMicrotask(()=>this.flush());this.assets?.sync();this.assembly?.sync();this.picker?.sync();this.features?.sync();const native=this.host.querySelector('#pickNativeMate');if(native){const part=this.inventory?.parts.find(p=>p.source===this.current()?.source),asset=part?.versions.find(v=>v.asset_id===(this.current()?.assetId||part.asset_id));native.disabled=native.disabled||!this.picker?.ready(asset,part);native.title=this.picker?.ready(asset,part)?'Pick native references in the 3D view':'Rebuild the current assembly preview to pick native references';}const imported=this.host.querySelector('#importMechanicalAsset');if(imported)imported.disabled=!!this.picker?.active;}
 async importFiles(context,files,onAsset=()=>{},options={}){
  if(!this.same(context)||!this.canWrite())throw Error('Wait for the current run or editing action before importing.');
  const operation={};this.running.set(context.pid,operation);this.sync();
  const current=()=>this.historyIntentCurrent(context)&&this.running.get(context.pid)===operation&&this.editable()&&!this.interacting();
  const results=[];
  try{
   await this.save();if(!current())return results;
   const models=files.filter(isModelFile);
   if(!models.length)throw Error('Choose a CAD or mesh model, together with its companion files.');
   for(const file of models){
    if(!current())break;
    try{
     if(!file.size||file.size>20_000_000)throw Error('Choose a model smaller than 20 MB.');
     const bundle=await meshResources(file,files),data=await fileData(file);if(!current())break;
     const drawing=/\.(dxf|svg)$/i.test(file.name),layers=(options.drawingLayers||'').split(',').map(value=>value.trim()).filter(Boolean);
     const asset=await this.api(`/api/workbench/projects/${context.pid}/mechanical/assets`,{method:'POST',body:{name:file.name,data,...bundle,...(/\.(stl|obj)$/i.test(file.name)?{units:options.units||'mm'}:{}),...(drawing?{units:options.drawingUnits||'auto'}:{}),...(/\.svg$/i.test(file.name)?{drawing_mode:options.drawingMode||'fill'}:{}),...(/\.dxf$/i.test(file.name)&&layers.length?{layers}:{})}});
     results.push({name:file.name,ok:true,asset});if(current())onAsset(asset);
    }catch(error){results.push({name:file.name,ok:false,error:error.message});}
   }
   return results;
  }finally{if(this.running.get(context.pid)===operation)this.running.delete(context.pid);if(this.same(context))this.sync();}
 }
 async build(context,args,endpoint='build'){
  if(!this.same(context)||!this.canWrite())throw Error('Wait for the current run or editing action before rebuilding.');
  if(this.state().fileDrafts?.has(`${context.pid}:${args.path}`))throw Error('Save the CAD source draft before rebuilding its model.');
  const operation={};this.running.set(context.pid,operation);this.sync();
  try{
   await this.save();if(!this.same(context))return;
   this.toast('Building mechanical geometry…');
   const asset=await this.api(`/api/workbench/projects/${context.pid}/mechanical/${endpoint}`,{method:'POST',body:args});
   if(!this.same(context))return asset;
   this.rememberHistory(context.pid,asset.mechanical_history);this.cadScope.add(context.pid);
   const current=await this.api('/api/projects/'+context.pid);if(!this.same(context))return asset;
   this.adopt(current.state);this.setSelection(context.pid,{source:asset.source,assetId:asset.asset_id});
   if(context.active==='files'&&this.state().active==='files'&&this.state().viewToken===context.view&&this.state().currentFile?.path===args.path)this.open3D();else this.render();this.toast('Mechanical part rebuilt. Earlier model versions are preserved.');return asset;
  }finally{if(this.running.get(context.pid)===operation)this.running.delete(context.pid);if(this.same(context))this.sync();}
 }
 form({title,fields,submit,apply}){
  if(!this.canWrite()||this.modal||this.openingParameters)return;
  const context=this.context(),element=document.createElement('dialog');element.id='mechanicalParametersDialog';element.className='mechanical-parameters-dialog';
  element.innerHTML=`<form><h2>${esc(title)}</h2><div class="mechanical-parameter-fields">${fields.map(f=>`<label>${esc(f.label)}${f.type==='select'?`<select name="${esc(f.key)}" aria-label="${esc(f.label)}">${f.options.map(o=>`<option value="${esc(o.value)}" ${o.value===f.value?'selected':''}>${esc(o.label)}</option>`).join('')}</select>`:`<input name="${esc(f.key)}" type="${f.type||'number'}" ${f.type==='text'?'maxlength="100"':'step="any"'} value="${esc(f.value)}" required>`}</label>`).join('')}</div><p class="mechanical-form-error" role="alert" hidden></p><div class="mechanical-form-footer"><button type="button" class="secondary-button" data-cancel>Cancel</button><button type="submit" class="primary-button">${esc(submit)}</button></div></form>`;
  this.modal={element,context};document.body.append(element);element.showModal();element.querySelector('input')?.focus();this.sync();let working=false;
  element.addEventListener('cancel',event=>{if(working)event.preventDefault();});
  element.querySelector('[data-cancel]').onclick=()=>{if(!working)element.close();};
  element.addEventListener('close',()=>{if(this.modal?.element===element)this.modal=null;element.remove();this.sync();this.flush();},{once:true});
  element.querySelector('form').onsubmit=async event=>{
   event.preventDefault();if(working||!this.same(context)||!this.canWrite())return;
   const values=Object.fromEntries(fields.map(f=>[f.key,['text','select'].includes(f.type)?element.querySelector(`[name="${f.key}"]`).value.trim():Number(element.querySelector(`[name="${f.key}"]`).value)]));
   if(fields.some(f=>!['text','select'].includes(f.type)&&!Number.isFinite(values[f.key])))return;
   working=true;for(const node of element.querySelectorAll('input,button'))node.disabled=true;
   try{await apply(values,context);if(element.isConnected)element.close();}
   catch(error){if(element.isConnected&&this.same(context)){const message=element.querySelector('[role="alert"]');message.hidden=false;message.textContent=error.message;}}
   finally{working=false;for(const node of element.querySelectorAll('input,button'))node.disabled=false;}
  };
 }
 newPart(){this.form({title:'New mechanical part',fields:[{key:'name',label:'Part name',type:'text',value:'Mounting plate'},{key:'kind',label:'Part type',type:'select',value:'plate',options:[{value:'plate',label:'Mounting plate'},{value:'sketch',label:'Constrained sketch'}]}],submit:'Create part',apply:(values,context)=>{const slug=values.name.toLowerCase().replace(/[^a-z0-9]+/g,'_').replace(/^_|_$/g,'').slice(0,60)||'part_'+crypto.randomUUID().slice(0,8);return this.build(context,{path:'cad/'+slug+'.cad.json',program:values.kind==='sketch'?constrainedPlate(values.name):mountingPlate(values.name)});}});}
 async parameters(part){
  if(!this.canWrite()||this.modal||this.openingParameters)return;const context=this.context(),ticket={context};this.openingParameters=ticket;this.sync();
  try{
  const source=await this.api(`/api/workbench/projects/${context.pid}/text/${encoded(part.source)}`);if(!this.same(context,true)||this.openingParameters!==ticket)return;
  const program=JSON.parse(source.content),parameters=program.parameters||{},fields=Object.entries(parameters).map(([key,value])=>({key,label:`${key} (${typeof value==='object'?value.unit||'mm':'mm'})`,value:typeof value==='object'?value.value:value}));
  if(!fields.length)throw Error('This source has no editable scalar parameters. Open its CAD code to add them.');
  this.openingParameters=null;
  this.form({title:'Part parameters',fields,submit:'Rebuild part',apply:(values,captured)=>{const next=structuredClone(program);for(const[key,value]of Object.entries(values)){if(typeof next.parameters[key]==='object')next.parameters[key].value=value;else next.parameters[key]=value;}return this.build(captured,{path:part.source,program:next,expected_sha256:source.sha});}});
  }finally{if(this.openingParameters===ticket)this.openingParameters=null;this.sync();}
 }
}
