import {esc,icon} from './workbench-icons.mjs';
import {DesignCanvas} from './workbench-canvas.mjs';

const alignCommands=[['Left','x','min','A'],['Center X','x','center','H'],['Right','x','max','D'],['Top','y','min','W'],['Center Y','y','center','V'],['Bottom','y','max','S']];

export class SelectionTransformsUI{
 constructor(deps){Object.assign(this,deps);this.queue=Promise.resolve();this.epoch=0;this.pending=0;this.basis='bounds';}
 get S(){return this.state();}
 keys(){return [...new Set([...this.S.selection].map(key=>this.S.active==='layout'?key.split('#')[0]:key))].sort();}
 cancel(){this.queuedTranslate=null;this.closeArrange();if(this.dialog)this.dialog.cancel();else this.epoch++;}
 valid(scope){return this.S.pid===scope.pid&&this.S.active===scope.mode&&(scope.mode!=='schematic'||(this.S.schematicSheet||'')===scope.sheet)&&this.epoch===scope.epoch&&JSON.stringify(this.keys())===JSON.stringify(scope.keys);}
 run(action,options={}){
  if(!this.editable()||this.busy()||this.interacting?.()||!['schematic','layout'].includes(this.S.active)||!this.keys().length)return Promise.resolve();
  const coalescible=action==='translate'&&Array.isArray(options.delta)&&options.delta.length===2&&options.delta.every(Number.isFinite)&&Object.keys(options).every(key=>key==='delta');
  const queued=this.queuedTranslate;
  if(coalescible&&queued&&!queued.started&&this.valid(queued.scope)){for(let i=0;i<2;i++)queued.options.delta[i]+=options.delta[i];return queued.promise;}
  if(!coalescible)this.queuedTranslate=null;
  if(this.pending>=16){this.toast('Finish the queued transforms before adding more.',true);return Promise.resolve();}
  const scope={pid:this.S.pid,mode:this.S.active,sheet:this.S.schematicSheet||'',keys:this.keys(),epoch:this.epoch},job={scope,options:structuredClone(options),started:false};this.pending++;
  this.queue=this.queue.then(()=>{job.started=true;if(this.queuedTranslate===job)this.queuedTranslate=null;return this.perform(scope,action,job.options);}).catch(error=>this.toast(error.message,true)).finally(()=>{this.pending--;const status=document.querySelector('#selectionTransformStatus');if(status)status.textContent=this.pending?'Checking native geometry…':'';});
  job.promise=this.queue;if(coalescible)this.queuedTranslate=job;
  return this.queue;
 }
 async perform(scope,action,options){
  if(!this.valid(scope)||!this.editable()||this.busy()||this.interacting?.()||this.dialog)return;
  await this.save();if(!this.valid(scope))return;
  const version=this.S.version,snapshot=JSON.stringify(this.S.spec),status=document.querySelector('#selectionTransformStatus');if(status)status.textContent='Checking native geometry…';
  const {review,...settings}=options,result=await this.api(`/api/workbench/projects/${scope.pid}/transforms/prepare`,{method:'POST',body:{...settings,mode:scope.mode,keys:scope.keys,action,base_version:version}});
  if(!this.valid(scope)||this.S.version!==version||JSON.stringify(this.S.spec)!==snapshot)return;
  if(!result.summary.changed){this.toast(result.summary.skipped_locked.length?'The selected footprints are locked.':'The selection is unchanged.');return;}
  const proposal={scope,version,snapshot,result};
  if(result.summary.requires_review||review||scope.mode==='layout'&&['align','distribute','translate'].includes(action)&&result.drc.errors)this.open(proposal);else await this.apply(proposal);
 }
 async apply(proposal){
  const {scope,version,snapshot,result}=proposal;
  if(!this.valid(scope)||this.S.version!==version||JSON.stringify(this.S.spec)!==snapshot||!this.editable()||this.busy()||this.interacting?.())throw new Error('The design changed. Review this transform again.');
  const action=result.summary.action,label=action==='rotate'?`Rotated ${scope.keys.length} selected objects`:action==='flip_layer'?'Flipped selected board layers':action==='align'?'Aligned selected objects':action==='distribute'?'Spaced selected objects evenly':action==='translate'?'Nudged selected objects':'Mirrored selected symbols';
  this.commit(result.spec,label);await this.save();
  if(result.summary.skipped_locked.length)this.toast(`Kept ${result.summary.skipped_locked.join(', ')} locked.`);
 }
 matchesArrangeKey(event){return ['schematic','layout'].includes(this.S.active)&&event.altKey&&!event.ctrlKey&&!event.metaKey&&(event.shiftKey?this.S.active==='layout'&&['KeyH','KeyV'].includes(event.code):alignCommands.some(row=>'Key'+row[3]===event.code));}
 key(event){
  if(!['schematic','layout'].includes(this.S.active)||this.interacting?.()||event.ctrlKey||event.metaKey||event.target?.closest?.('[role=menu]'))return false;
  if(this.matchesArrangeKey(event)){event.preventDefault();if(!event.repeat){if(event.shiftKey)this.run('distribute',{axis:event.code==='KeyH'?'x':'y',basis:this.basis});else{const [,axis,edge]=alignCommands.find(row=>'Key'+row[3]===event.code);this.run('align',{axis,edge,basis:this.basis});}}return true;}
  if(!event.altKey&&event.code==='KeyS'&&!event.shiftKey&&this.S.active==='schematic'){event.preventDefault();if(!event.repeat)this.run('distribute',{axis:'auto',basis:this.basis});return true;}
  if(event.altKey||!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(event.key)||event.target?.closest?.('[role=treeitem],[role=separator]'))return false;
  event.preventDefault();const direction={ArrowLeft:[-1,0],ArrowRight:[1,0],ArrowUp:[0,-1],ArrowDown:[0,1]}[event.key];
  if(this.keys().length){const step=(this.S.active==='layout'?this.S.boardGrid||.5:10)/(event.shiftKey?10:1);this.run('translate',{delta:direction.map(v=>v*step)});}
  else{const camera=this.S.canvas?.getCamera?.();if(camera&&Number.isFinite(camera.scale)&&camera.scale>0){const next={...camera,center:camera.center.map((v,i)=>v+direction[i]*40/camera.scale)};this.S.canvas.setCamera(next);this.S.planarCameras||=new Map();if(this.S.canvas.workbenchKey)this.S.planarCameras.set(this.S.canvas.workbenchKey,next);}}
  return true;
 }
 arrangeButtons(menu=false){return alignCommands.map(([label,axis,edge,key])=>`<button ${menu?'role="menuitem"':''} class="${menu?'':'secondary-button'}" data-arrange-action="align" data-arrange-axis="${axis}" data-arrange-edge="${edge}" title="Align ${label.toLowerCase()} · Alt+${key}">${menu?'Align ':''}${label}${menu?`<kbd>⌥${key}</kbd>`:''}</button>`).join('');}
 arrangeInspector(){return`<section class="inspector-section selection-arrange-controls"><h3>Align</h3><div class="selection-arrange-grid">${this.arrangeButtons()}</div><div class="selection-transform-row"><button class="secondary-button" data-arrange-action="distribute" data-arrange-axis="x">Space horizontally</button><button class="secondary-button" data-arrange-action="distribute" data-arrange-axis="y">Space vertically</button></div><label class="property-row"><span>Align using</span><select data-arrange-basis><option value="bounds" ${this.basis==='bounds'?'selected':''}>Native bounds</option><option value="origins" ${this.basis==='origins'?'selected':''}>Object origins</option></select></label></section>`;}
 bindArrange(host,close=()=>{}){
  const basis=host.querySelector('[data-arrange-basis]');if(basis)basis.onchange=()=>{this.basis=basis.value;};
  for(const button of host.querySelectorAll('[data-arrange-action]')){button.disabled=!this.editable()||this.busy()||this.keys().length<(button.dataset.arrangeAction==='distribute'?3:2);button.onclick=()=>{close();this.run(button.dataset.arrangeAction,{axis:button.dataset.arrangeAxis,...(button.dataset.arrangeEdge?{edge:button.dataset.arrangeEdge}:{}),basis:this.basis});};}
 }
 closeArrange(){const menu=document.querySelector('#arrangeSelectionMenu');if(menu)menu.hidden=true;this.arrangeAnchor?.setAttribute('aria-expanded','false');}
 openArrangeMenu(anchor,close){
  if(anchor.disabled)return;let menu=document.querySelector('#arrangeSelectionMenu');if(!menu){menu=document.createElement('div');menu.id='arrangeSelectionMenu';menu.className='popover canvas-context-menu arrange-context-menu';menu.setAttribute('role','menu');menu.setAttribute('aria-label','Align selected objects');document.body.append(menu);}
  this.arrangeAnchor=anchor;anchor.setAttribute('aria-haspopup','menu');anchor.setAttribute('aria-expanded','true');
  menu.innerHTML=this.arrangeButtons(true)+`<div class="arrange-menu-separator"></div>${this.S.active==='schematic'?'<button role="menuitem" data-arrange-action="distribute" data-arrange-axis="auto">Space evenly<kbd>S</kbd></button>':''}<button role="menuitem" data-arrange-action="distribute" data-arrange-axis="x">Space evenly horizontally<kbd>${this.S.active==='layout'?'⌥⇧H':''}</kbd></button><button role="menuitem" data-arrange-action="distribute" data-arrange-axis="y">Space evenly vertically<kbd>${this.S.active==='layout'?'⌥⇧V':''}</kbd></button>`;
  menu.hidden=false;const rect=anchor.getBoundingClientRect();menu.style.left=Math.max(8,rect.right+menu.offsetWidth<innerWidth-8?rect.right-3:rect.left-menu.offsetWidth+3)+'px';menu.style.top=Math.max(8,Math.min(innerHeight-menu.offsetHeight-8,rect.top))+'px';
  this.bindArrange(menu,()=>{this.closeArrange();close();});menu.onkeydown=event=>{if(['Escape','ArrowLeft'].includes(event.key)){event.preventDefault();event.stopPropagation();this.closeArrange();anchor.focus();}else if(['ArrowDown','ArrowUp'].includes(event.key)){event.preventDefault();const buttons=[...menu.querySelectorAll('button:not([disabled])')],at=buttons.indexOf(document.activeElement);buttons[(at+(event.key==='ArrowDown'?1:-1)+buttons.length)%buttons.length]?.focus();}};
 }
 inspector(){
  const schematic=this.S.active==='schematic';
  return `<section class="inspector-section selection-transform-controls"><h3>Transform</h3><div class="selection-transform-row"><button class="secondary-button" data-selection-transform="rotate" data-angle="-90" title="Rotate left [">${icon('rotate')}Left</button><button class="secondary-button" data-selection-transform="rotate" data-angle="90" title="Rotate right ]">${icon('rotate')}Right</button></div><label class="selection-transform-option"><input type="checkbox" id="selectionRotateIndividually">Rotate each around its own origin</label><div class="selection-transform-row">${schematic?'<button class="secondary-button" data-selection-transform="flip_horizontal" title="Flip horizontally F">Flip horizontal</button><button class="secondary-button" data-selection-transform="flip_vertical" title="Flip vertically Shift+F">Flip vertical</button>':'<button class="secondary-button" data-selection-transform="flip_layer" title="Flip layer F">Flip layer</button>'}</div><details><summary>Rotation pivot</summary><p>${schematic?'Schematic units':'Board millimetres'} · used for whole-selection rotation; leave blank for automatic.</p><label class="property-row"><span>X</span><input type="number" step="any" id="selectionPivotX" placeholder="Automatic"></label><label class="property-row"><span>Y</span><input type="number" step="any" id="selectionPivotY" placeholder="Automatic"></label><button class="secondary-button" id="reviewSelectionTransform">Review rotation</button></details><p id="selectionTransformStatus" aria-live="polite"></p></section>${this.arrangeInspector()}`;
 }
 bind(host){
  const options=()=>{const x=host.querySelector('#selectionPivotX')?.value,y=host.querySelector('#selectionPivotY')?.value,result={individual:!!host.querySelector('#selectionRotateIndividually')?.checked};if(!result.individual&&(x||y)){if(!x||!y)throw new Error('Enter both pivot coordinates.');result.pivot=[Number(x),Number(y)];}return result;};
  host.querySelectorAll('[data-selection-transform]').forEach(button=>{button.disabled=!this.editable()||this.busy();button.onclick=()=>{try{this.run(button.dataset.selectionTransform,{...options(),angle:Number(button.dataset.angle||90)});}catch(error){this.toast(error.message,true);}};});
  const review=host.querySelector('#reviewSelectionTransform');if(review){review.disabled=!this.editable()||this.busy();review.onclick=()=>{try{this.run('rotate',{...options(),angle:90,review:true});}catch(error){this.toast(error.message,true);}};}
  this.bindArrange(host);
 }
 open(proposal){
  const {result,scope}=proposal,s=result.summary;const d=document.createElement('dialog');d.id='transformReviewDialog';d.className='sheet-dialog selection-transform-dialog';let view=null,applied=false,disposed=false;
  const dispose=()=>{if(disposed)return;disposed=true;view?.destroy?.();d.remove();if(this.dialog?.element===d)this.dialog=null;if(!applied)this.epoch++;};
  const cancel=()=>{d.close();dispose();};this.dialog={element:d,cancel};
  const rows=s.cleared_copper.map(item=>`<tr><td>${esc(item.net)}</td><td>${esc(item.kind)}</td><td>${esc(item.layer||item.layers?.join(', ')||'—')}</td><td title="${esc(item.id||'')}">${esc(item.id||'Unassigned ID')}</td></tr>`).join('');
  d.innerHTML=`<form><h2>Review selection transform</h2><div class="selection-transform-content"><p>${scope.keys.length} selected objects · ${['align','distribute','translate'].includes(s.action)?esc(s.pivot_basis):s.individual?'each object’s own origin':`pivot ${s.pivot.map(v=>Number(v.toFixed(3))).join(', ')} ${scope.mode==='layout'?'mm':'schematic units'}`}. Native pin groups unchanged.</p>${s.skipped_locked.length?`<p>Locked and kept: ${esc(s.skipped_locked.join(', '))}.</p>`:''}${s.rerouted_wires?.length?`<p>${s.rerouted_wires.length} wire paths will be recomputed; electrical pin groups stay unchanged.</p>`:''}${s.gap<0?'<p class="transform-clearance-note">Equal spacing produces overlapping bounds. Review the proposed positions.</p>':''}${s.body_outside?.length?`<p class="transform-clearance-note">Footprint bounds extend beyond the board: ${esc(s.body_outside.join(', '))}.</p>`:''}${s.outside_copper_count?`<p class="transform-clearance-note">${s.outside_copper_count} moved copper outlines extend beyond the board. ${esc(s.outside_copper.slice(0,20).map(item=>item.net+' / '+item.kind+' / '+(item.id||'Unassigned ID')).join('; '))}${s.outside_copper_count>20?' · More items in the native proposal.':''}</p>`:''}<div id="transformImpact">${s.cleared_copper_count?`<p class="transform-clearance-note">${s.cleared_copper_count} copper objects need rerouting on ${esc(s.cleared_nets.join(', '))}.</p><div class="transform-impact-table"><table class="design-table"><thead><tr><th>Net</th><th>Type</th><th>Layer</th><th>Object ID</th></tr></thead><tbody>${rows}</tbody></table></div>${s.cleared_copper_truncated?`<p>Showing ${s.cleared_copper.length} of ${s.cleared_copper_count} affected objects.</p>`:''}`:'<p>Existing copper is retained.</p>'}<p>${Object.entries(s.transformed_copper).map(([kind,count])=>`${count} ${kind}`).join(' · ')} transformed. ${s.unchanged_copper_nets.length?`Unchanged copper: ${esc(s.unchanged_copper_nets.join(', '))}.`:''}</p></div><p class="file-help">${esc(s.pivot_basis)}. DRC: ${result.drc.errors} errors, ${result.drc.warnings} warnings, ${result.drc.unconnected} unconnected. This checks the proposed geometry; run project checks after saving.</p><div class="selection-transform-row"><button type="button" class="secondary-button" data-transform-preview="before">Original</button><button type="button" class="secondary-button active" data-transform-preview="after">Proposed</button></div><div id="transformNativePreview"></div><p id="transformReviewStatus" class="file-help" aria-live="polite"></p></div><div class="dialog-actions"><button type="button" class="secondary-button" data-transform-cancel>Cancel</button><button type="submit" class="primary-button" id="applySelectionTransform">Apply transform</button></div></form>`;
  const draw=which=>{view?.destroy?.();const host=d.querySelector('#transformNativePreview');if(scope.mode==='layout')view=new window.BoardView(host,which==='before'?result.before_geometry:result.geometry,{compact:true,readOnly:true,editable:false,ratsnest:true});else view=new DesignCanvas(host,which==='before'?JSON.parse(proposal.snapshot):result.spec,{mode:'schematic',readOnly:true,nativeScene:which==='before'?result.before_schematic:result.schematic,sheet:scope.sheet||''});d.querySelectorAll('[data-transform-preview]').forEach(button=>button.classList.toggle('active',button.dataset.transformPreview===which));};
  d.querySelectorAll('[data-transform-preview]').forEach(button=>button.onclick=()=>draw(button.dataset.transformPreview));d.querySelector('[data-transform-cancel]').onclick=cancel;
  d.querySelector('form').onsubmit=async event=>{event.preventDefault();const button=d.querySelector('#applySelectionTransform');button.disabled=true;try{await this.apply(proposal);applied=true;d.close();dispose();}catch(error){d.querySelector('#transformReviewStatus').textContent=error.message;this.toast(error.message,true);}};
  d.addEventListener('cancel',event=>{event.preventDefault();cancel();});d.addEventListener('close',dispose,{once:true});document.body.append(d);d.showModal();draw('after');
 }
}
