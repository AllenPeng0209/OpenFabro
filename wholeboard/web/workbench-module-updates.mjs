import {esc,icon} from './workbench-icons.mjs';
import {DesignCanvas} from './workbench-canvas.mjs';

const valueText=value=>value?.removed?'Removed':typeof value==='string'?value:JSON.stringify(value);
export class ModuleUpdatesUI{
 constructor(deps){Object.assign(this,deps);this.rows=[];this.pid=null;}
 run(fn){return(...args)=>Promise.resolve().then(()=>fn(...args)).catch(error=>this.toast(error.message,true));}
 get S(){return this.state();}
 async refresh(){
  const S=this.S,pid=S.pid;if(!pid)return [];
  const result=await this.api(`/api/workbench/projects/${pid}/modules/updates`);if(S.pid!==pid)return [];
  this.pid=pid;this.rows=result.updates.filter(row=>S.spec.editor?.module_instances?.[row.instance]?.version===row.current_version||(!S.spec.editor?.module_instances?.[row.instance]?.version&&row.current_version===1));this.mount();return this.rows;
 }
 mount(){
  document.querySelector('#moduleUpdateNotice')?.remove();const S=this.S;
  if(this.pid!==S.pid||S.screen==='projects'||!['schematic','layout','3d'].includes(S.active))return;
  let dismissed=[];try{dismissed=JSON.parse(localStorage.getItem('wb-module-dismissed-'+S.pid)||'[]');}catch{}
  const rows=this.rows.filter(row=>row.available&&!dismissed.includes(row.instance+':'+row.fingerprint)&&S.spec.editor?.module_instances?.[row.instance]&&(S.spec.editor.module_instances[row.instance].version||1)<row.version);
  if(!rows.length)return;
  const notice=document.createElement('div');notice.id='moduleUpdateNotice';notice.className='component-update-notice';
  notice.innerHTML=`<div>${icon('history')}<strong>${rows.length} component update${rows.length===1?'':'s'} available</strong></div><p>Published modules have newer versions.</p><div class="component-update-actions"><button class="secondary-button" data-dismiss>Dismiss</button><button class="primary-button" id="reviewModuleUpdates">Review</button></div>`;
  document.querySelector('#viewContent').append(notice);notice.querySelector('[data-dismiss]').onclick=()=>{localStorage.setItem('wb-module-dismissed-'+S.pid,JSON.stringify([...new Set([...dismissed,...rows.map(r=>r.instance+':'+r.fingerprint)])]));notice.remove();};notice.querySelector('#reviewModuleUpdates').onclick=this.run(()=>this.open());
 }
 label(instance,path){
  const parts=path.split('/'),meta=this.S.spec.editor?.module_instances?.[instance];
  if(parts[0]==='components')return (meta?.source_maps?.refs?.[parts[1]]||parts[1].replace(/^local:/,''))+' · '+(parts.slice(2).join(' / ')||'Component');
  if(parts[0]==='copper')return 'PCB copper · '+parts.slice(1).join('/');
  return path.replaceAll('/',' · ');
 }
 async open(){
  const rows=await this.refresh(),available=rows.filter(r=>r.available),S=this.S,pid=S.pid;
  document.querySelector('#moduleUpdatesDialog')?.close();const d=document.createElement('dialog');d.id='moduleUpdatesDialog';d.className='sheet-dialog module-dialog module-updates-dialog';
  d.innerHTML=`<form><h2>Component updates</h2><p class="file-help">Review published module changes before applying them. Local changes are merged against the pinned version.</p><div class="module-update-body">${available.length?`<div class="module-update-table"><table class="design-table"><thead><tr><th></th><th>Instance</th><th>Module</th><th>Current</th><th>New version</th></tr></thead><tbody>${available.map(r=>`<tr><td><input type="checkbox" data-update-instance="${esc(r.instance)}" checked></td><td>${esc(r.instance)}</td><td>${esc(r.name)}</td><td>v${r.current_version}</td><td><select data-update-version="${esc(r.instance)}">${r.versions.filter(v=>v>r.current_version).map(v=>`<option value="${v}" ${v===r.version?'selected':''}>v${v}</option>`).join('')}</select></td></tr>`).join('')}</tbody></table></div>`:'<p>No published module updates are available.</p>'}${rows.some(r=>!r.available)?'<p class="file-help">Some source projects are unavailable. Their installed versions stay pinned.</p>':''}<div id="moduleUpdateConflicts"></div><div id="moduleUpdateSummary" class="file-help" aria-live="polite"></div><div class="module-update-preview-tabs" id="moduleUpdatePreviewTabs" hidden><button type="button" class="secondary-button" data-module-preview="pcb">PCB layout</button><button type="button" class="secondary-button" data-module-preview="schematic">Schematic</button></div><div id="moduleUpdatePreview" class="module-update-preview" hidden></div></div><div class="dialog-actions"><button type="button" class="secondary-button" data-cancel>Cancel</button><button class="secondary-button" type="submit" id="prepareModuleUpdates" ${!available.length||!this.editable()||this.busy()?'disabled':''}>Review selected</button><button class="primary-button" type="button" id="confirmModuleUpdates" disabled>Update selected</button></div></form>`;
  document.body.append(d);const $=s=>d.querySelector(s),confirm=$('#confirmModuleUpdates'),prepare=$('#prepareModuleUpdates');let prepared=null,preview=null,mode='pcb';
  const args=()=>{
   const instances=[...d.querySelectorAll('[data-update-instance]:checked')].map(input=>input.dataset.updateInstance),sources={},resolutions={},port_actions={};
   for(const instance of instances){const row=available.find(r=>r.instance===instance);sources[instance]={...(row.catalog_id?{catalog_id:row.catalog_id}:{}),version:Number($(`[data-update-version="${CSS.escape(instance)}"]`).value)};}
   for(const input of d.querySelectorAll('[data-conflict]'))if(input.value&&instances.includes(input.dataset.instance)){resolutions[input.dataset.instance]||={};resolutions[input.dataset.instance][input.dataset.conflict]=input.value;}
   for(const input of d.querySelectorAll('[data-port-action]'))if(input.value&&instances.includes(input.dataset.instance)){port_actions[input.dataset.instance]||={};port_actions[input.dataset.instance][input.dataset.portAction]=input.value;}
   return {instances,sources,resolutions,port_actions};
  };
  const invalidate=()=>{prepared=null;confirm.disabled=true;$('#moduleUpdateSummary').textContent='Preview the current selection and conflict choices.';};
  d.querySelector('form').oninput=event=>{invalidate();if(event.target.matches('[data-update-instance],[data-update-version]'))$('#moduleUpdateConflicts').innerHTML='';};
  const draw=()=>{
   preview?.destroy?.();preview=null;const host=$('#moduleUpdatePreview');host.innerHTML='';host.classList.remove('boardview');if(!prepared?.result.spec)return;
   if(mode==='pcb'&&window.BoardView)preview=new window.BoardView(host,prepared.result.geometry,{compact:true,readOnly:true,editable:false,ratsnest:true});
   else preview=new DesignCanvas(host,prepared.result.spec,{mode:'schematic',nativeScene:prepared.result.schematic,sheet:prepared.result.schematic.sheets.some(p=>p.name===(S.schematicSheet||''))?S.schematicSheet||'':'',readOnly:true});
  };
  d.querySelectorAll('[data-module-preview]').forEach(button=>button.onclick=()=>{mode=button.dataset.modulePreview;draw();});
  $('[data-cancel]').onclick=()=>d.close();d.addEventListener('close',()=>{prepared=null;preview?.destroy?.();d.remove();},{once:true});
  d.querySelector('form').onsubmit=this.run(async event=>{
   event.preventDefault();if(!this.editable()||this.busy())return;const body=args();if(!body.instances.length)throw new Error('Choose a module instance to review.');await this.save();if(!d.open)return;
   const version=S.version,snapshot=JSON.stringify(S.spec),settings=JSON.stringify(body);prepare.disabled=true;confirm.disabled=true;
   try{
    const result=await this.api(`/api/workbench/projects/${pid}/modules/updates/prepare`,{method:'POST',body:{...body,base_version:version}});
    if(!d.open||!d.isConnected)return;
    if(S.pid!==pid||S.version!==version||JSON.stringify(S.spec)!==snapshot||JSON.stringify(args())!==settings){invalidate();return;}
    $('#moduleUpdateConflicts').innerHTML=result.plans.map(plan=>{const instance=plan.summary.instance;return `<section class="module-update-plan"><h3>${esc(instance)} · v${plan.summary.from_version} → v${plan.summary.to_version}</h3>${plan.conflicts.map(c=>`<div class="module-update-conflict"><strong>${esc(this.label(instance,c.id))}</strong><div><span>Local</span><code>${esc(valueText(c.local))}</code></div><div><span>Module</span><code>${esc(valueText(c.module))}</code></div><select data-instance="${esc(instance)}" data-conflict="${esc(c.id)}" aria-label="Resolve ${esc(instance+' '+c.id)}"><option value="">Choose resolution</option><option value="local" ${c.choice==='local'?'selected':''}>Keep local</option><option value="module" ${c.choice==='module'?'selected':''}>Use module</option></select></div>`).join('')}${plan.port_changes.map(p=>`<label class="module-port-resolution">Removed interface ${esc(p.label)}<select data-instance="${esc(instance)}" data-port-action="${esc(p.label)}"><option value="">Choose connection</option><option value="disconnect" ${p.choice==='disconnect'?'selected':''}>Disconnect interface</option>${p.options.map(label=>`<option value="${esc(label)}" ${p.choice===label?'selected':''}>Reconnect to ${esc(label)}</option>`).join('')}</select></label>`).join('')}<p class="file-help">${plan.changes.length} fields change; ${plan.summary.kept_local} local changes kept.${plan.summary.invalidated_nets.length?' Reroute: '+esc(plan.summary.invalidated_nets.join(', '))+'.':''}</p>${plan.local_overrides?.length?`<details class="module-local-overrides" open><summary>Local changes kept</summary><ul>${plan.local_overrides.map(path=>`<li data-kept-field="${esc(path)}">${esc(this.label(instance,path))}</li>`).join('')}</ul></details>`:''}</section>`;}).join('');
    preview?.destroy?.();preview=null;$('#moduleUpdatePreview').hidden=!result.spec;$('#moduleUpdatePreviewTabs').hidden=!result.spec;
    if(!result.spec){prepared=null;$('#moduleUpdateSummary').textContent='Resolve the highlighted local changes or removed interfaces, then review again.';return;}
    const removed=result.plans.reduce((sum,p)=>sum+Object.values(p.summary.removed_copper).reduce((a,b)=>a+b,0),0),updated=result.plans.reduce((sum,p)=>sum+Object.values(p.summary.updated_copper||{}).reduce((a,b)=>a+b,0),0);
    $('#moduleUpdateSummary').textContent=`Native pin groups match the merged design. PCB copper: ${removed} removed, ${updated} changed.${result.validation.errors.length?' Design findings: '+result.validation.errors.join('; '):''}`;
    prepared={result,version,snapshot,settings:JSON.stringify(args())};draw();confirm.disabled=false;
   }finally{prepare.disabled=false;}
  });
  confirm.onclick=this.run(async()=>{
   if(!prepared||S.pid!==pid||S.version!==prepared.version||JSON.stringify(S.spec)!==prepared.snapshot||JSON.stringify(args())!==prepared.settings){invalidate();throw new Error('The design changed. Review the module updates again.');}
   this.commit(prepared.result.spec,'Updated published module instances',null);d.close();await this.save();await this.refresh();this.toast('Module updates saved. Review ERC and DRC before manufacturing.');
  });
  d.showModal();prepare.focus();
 }
}
