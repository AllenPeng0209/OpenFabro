import {icon,esc} from './workbench-icons.mjs';
import {sheetDefinitions} from './workbench-sheets.mjs';
import {interfaceRows} from './workbench-interfaces.mjs';

export class ModulesUI{
 constructor(deps){Object.assign(this,deps);this.id=null;}
 get S(){return this.state();}
 editable(){return this.S.project.access?.can_edit!==false&&!['running','waiting'].includes(this.S.project.status);}
 run(fn){return(...args)=>Promise.resolve().then(()=>fn(...args)).catch(error=>this.toast(error.message,true));}
 async request(path,body){
  await this.save();const S=this.S,pid=S.pid,version=S.version,snapshot=JSON.stringify(S.spec);
  const result=await this.api(`/api/workbench/projects/${pid}/modules/${path}`,{method:'POST',body:{...body,base_version:version}});
  if(S.pid!==pid||S.version!==version||JSON.stringify(S.spec)!==snapshot)throw new Error('The design changed while preparing this module. Try again.');
  return result;
 }
 render(host,{onKind}){
  if(this.pid!==this.S.pid){this.pid=this.S.pid;this.id=null;}
  this.host=host;this.onKind=onKind;const assets=this.S.spec.library?.modules||{};
  if(!assets[this.id])this.id=Object.keys(assets)[0]||null;
  const asset=assets[this.id],disabled=this.editable()?'':'disabled';
  const copper=asset?.design.fixed_copper||[],counts={components:asset?.design.components.length||0,nets:asset?.design.nets.length||0,tracks:copper.reduce((sum,g)=>sum+(g.tracks?.length||0)+(g.arcs?.length||0),0),vias:copper.reduce((sum,g)=>sum+(g.vias?.length||0),0),zones:asset?.design.fixed_zones.length||0};
  host.innerHTML=`<section class="asset-editor"><aside class="asset-browser"><div class="asset-browser-tools"><select id="libraryKind" aria-label="Library asset kind"><option value="symbols">Symbols</option><option value="footprints">Footprints</option><option value="parts">Parts</option><option value="modules" selected>Modules</option></select></div><div class="module-search">${icon('search')}<input id="moduleFilter" placeholder="Search modules" aria-label="Search modules"></div><div class="asset-list">${Object.entries(assets).map(([id,value])=>`<button class="asset-list-item ${id===this.id?'active':''}" data-module="${esc(id)}">${icon('folder')}<span>${esc(value.name)}<small>${esc(id)}</small></span></button>`).join('')||'<p class="file-help">No saved modules.</p>'}</div><div class="asset-browser-footer"><button class="secondary-button" id="publishProjectModule" ${disabled}>${icon('plus')}Save project as module</button><button class="secondary-button" id="importModule" ${disabled}>${icon('upload')}Import module</button><button class="secondary-button" id="browseModuleCatalog">Browse workspace</button><button class="secondary-button" id="publishProjectRelease" ${disabled}>Publish project to workspace</button><input id="importModuleFile" type="file" accept=".json,application/json" hidden></div></aside><main class="asset-main">${asset?`<div class="module-header asset-header"><div><h2>${esc(asset.name)}</h2><p>${esc(this.id)} · v${asset.version||1} · ${asset.design.board.layers} copper layers</p></div><div class="library-title-actions"><button class="secondary-button" id="exportModule">Export module</button><button class="secondary-button" id="editModuleSource" ${disabled}>Open source</button>${!asset.origin||asset.origin.project_id===this.S.pid?`<button class="secondary-button" id="publishModuleVersion" ${disabled}>Publish changes</button>`:''}<button class="primary-button" id="insertModule" ${disabled}>${icon('plus')}Insert module</button></div></div><div class="module-content"><p>${esc(asset.description||'Reusable circuit with its schematic, PCB placements and routed copper.')}</p><div class="module-metrics">${Object.entries(counts).map(([key,count])=>`<div><strong>${count}</strong><span>${esc(key)}</span></div>`).join('')}</div><h3>Terminals</h3><div class="module-ports">${Object.entries(asset.ports).map(([label,port])=>`<div class="pin-row"><span>${esc(label)}</span><span>${esc(port.net)}</span></div>`).join('')||'<p>No exposed terminals. Edit the source and save another version with terminals to connect it externally.</p>'}</div><h3>Components</h3><table class="design-table"><thead><tr><th>Designator</th><th>Value</th><th>PCB position (mm)</th></tr></thead><tbody>${asset.design.components.map(c=>`<tr><td>${esc(c.ref)}</td><td>${esc(c.value||'')}</td><td>${esc(c.placement?.x_mm??'—')}, ${esc(c.placement?.y_mm??'—')}</td></tr>`).join('')}</tbody></table><p class="file-help">Each insertion gets unique component references, internal nets and copper identities. Choose exposed terminal connections when inserting, then check the native design.</p></div>`:`<div class="asset-empty">${icon('folder')}<h2>Reuse a circuit and its layout</h2><p>Save this complete project as a module, or import a module library package.</p><button class="secondary-button" id="emptyPublishModule" ${disabled}>Save first module</button></div>`}</main></section>`;
  const $=selector=>host.querySelector(selector);$('#libraryKind').onchange=e=>onKind(e.target.value);
  host.querySelectorAll('[data-module]').forEach(button=>button.onclick=()=>{this.id=button.dataset.module;this.render(host,{onKind});});
  $('#moduleFilter').oninput=e=>host.querySelectorAll('[data-module]').forEach(button=>button.hidden=!button.textContent.toLowerCase().includes(e.target.value.toLowerCase()));
  $('#publishProjectModule').onclick=()=>this.publish();$('#emptyPublishModule')?.addEventListener('click',()=>this.publish());
  $('#insertModule')?.addEventListener('click',()=>this.insert());
  $('#publishProjectRelease')?.addEventListener('click',this.run(()=>this.publishWorkspace(true)));
  $('#publishModuleVersion')?.addEventListener('click',this.run(()=>this.publishWorkspace(false)));
  $('#browseModuleCatalog')?.addEventListener('click',this.run(()=>this.browseCatalog()));
  $('#editModuleSource')?.addEventListener('click',this.run(()=>this.editSource()));
  $('#exportModule')?.addEventListener('click',()=>this.download(this.id+'.module.json',JSON.stringify({modules:{[this.id]:asset}},null,2)));
  $('#importModule').onclick=()=>$('#importModuleFile').click();
  $('#importModuleFile').onchange=this.run(async event=>{
   const file=event.target.files[0];if(!file)return;if(file.size>10_000_000)throw new Error('Choose a module package smaller than 10 MB.');
   const data=JSON.parse(await file.text());
   if(!data.modules||typeof data.modules!=='object'||Array.isArray(data.modules)||!Object.keys(data.modules).length)throw new Error('Choose an exported module library package.');
   const result=await this.request('package',{modules:data.modules});
   this.id=Object.keys(data.modules)[0];this.commit(result.spec,'Imported portable module revisions');this.toast('Module library imported; existing instances stay pinned');this.updates?.refresh().catch(()=>{});
  });
 }
 modal(title,body,action){
  document.querySelector('#moduleDialog')?.remove();const d=document.createElement('dialog');d.id='moduleDialog';d.className='sheet-dialog module-dialog';
  d.innerHTML=`<form><h2>${esc(title)}</h2><div class="sheet-dialog-content">${body}</div><div class="dialog-actions"><button type="button" class="secondary-button" data-cancel>Cancel</button><button class="primary-button" type="submit">${esc(action)}</button></div></form>`;
  document.body.append(d);d.querySelector('[data-cancel]').onclick=()=>d.close();d.showModal();return d;
 }
 publish(){
  if(!this.editable())return;if(!this.S.spec.components.length){this.toast('Add components before saving a module.',true);return;}
  const portRows=interfaceRows(this.S.spec,{publish:true});
  const d=this.modal('Save project as module',`<label>Library ID<input id="moduleId" value="Module" pattern="[A-Za-z][A-Za-z0-9_-]{0,63}" maxlength="64" required></label><label>Name<input id="moduleName" value="${esc(this.S.project.custom_title||'Circuit module')}" maxlength="120" required></label><p>Capture the complete current circuit and native layout. Choose the nets exposed as terminals.</p><div class="module-terminal-list">${portRows.map((row,index)=>`<label class="module-terminal"><input type="checkbox" data-module-port="${index}" ${row.checked?'checked':''} ${row.required?'disabled':''}><span>${esc(row.net)}</span><input data-module-port-label="${index}" value="${esc(row.label)}" aria-label="Terminal name for ${esc(row.net)}" maxlength="100" ${row.terminal?'readonly':''} required></label>`).join('')}</div>`,'Save module');
  d.querySelector('form').onsubmit=this.run(async event=>{
   event.preventDefault();const id=d.querySelector('#moduleId').value,ports={};if(this.S.spec.library?.modules?.[id])throw new Error('A module already uses that library ID.');
   d.querySelectorAll('[data-module-port]:checked').forEach(input=>{const label=d.querySelector(`[data-module-port-label="${input.dataset.modulePort}"]`).value.trim();if(!label||Object.hasOwn(ports,label))throw new Error('Terminal names must be nonempty and unique.');ports[label]=portRows[Number(input.dataset.modulePort)].net;});
   const button=d.querySelector('[type="submit"]');button.disabled=true;
   try{const result=await this.request('publish',{name:d.querySelector('#moduleName').value.trim(),ports});if(!d.open)return;const next=structuredClone(this.S.spec);next.library||={};next.library.modules||={};next.library.modules[id]=result.module;this.id=id;this.commit(next,'Saved reusable circuit module');d.close();this.toast('Module saved with native layout');}finally{button.disabled=false;}
  });
 }
 insert(){
  if(!this.editable())return;const asset=this.S.spec.library?.modules?.[this.id];if(!asset)return;const defs=sheetDefinitions(this.S.spec);let number=1;while(defs['M'+number])number++;
  const d=this.modal('Insert '+asset.name,`<label>Instance ID<input id="moduleInstance" value="M${number}" pattern="[A-Za-z][A-Za-z0-9_-]{0,63}" required></label><label>Parent sheet<select id="moduleParent"><option value="">Main</option>${Object.entries(defs).map(([id,value])=>`<option value="${esc(id)}" ${id===this.S.schematicSheet?'selected':''}>${esc(value.title||id)}</option>`).join('')}</select></label><div class="asset-property-pair"><label>PCB offset X (mm)<input id="moduleOffsetX" type="number" step="any" value="0" required></label><label>PCB offset Y (mm)<input id="moduleOffsetY" type="number" step="any" value="0" required></label></div><p>Place the module in a free area of the target board. Internal routes keep their positions relative to its components.</p><div class="module-terminal-list">${Object.keys(asset.ports).map(label=>`<label class="property-row"><span>${esc(label)}</span><select data-module-connection="${esc(label)}"><option value="">Isolated internal net</option>${this.S.spec.nets.map(net=>`<option value="${esc(net.name)}">${esc(net.name)}</option>`).join('')}</select></label>`).join('')}</div>`,'Insert and open');
  d.querySelector('form').onsubmit=this.run(async event=>{
   event.preventDefault();const instance=d.querySelector('#moduleInstance').value,connections={};d.querySelectorAll('[data-module-connection]').forEach(input=>{if(input.value)connections[input.dataset.moduleConnection]=input.value;});const button=d.querySelector('[type="submit"]');button.disabled=true;
   try{const result=await this.request('instantiate',{module:this.id,instance,parent:d.querySelector('#moduleParent').value,offset:[Number(d.querySelector('#moduleOffsetX').value),Number(d.querySelector('#moduleOffsetY').value)],connections});if(!d.open)return;this.commit(result.spec,'Inserted circuit module',null);d.close();this.open(instance);this.toast('Module inserted. Run ERC and DRC to verify the complete design.');}finally{button.disabled=false;}
  });
 }
 async publishWorkspace(forceNew=false){
  if(!this.editable())return;await this.save();const S=this.S,pid=S.pid,current=S.spec.library?.modules?.[this.id];
  const selected=!forceNew&&current&&(!current.origin||current.origin.project_id===pid)?current:null,id=selected?this.id:'Module';
  const catalog=await this.api(`/api/workbench/projects/${pid}/modules/catalog`);if(S.pid!==pid)return;
  const rows=interfaceRows(S.spec,{publish:true}).map(row=>{const old=Object.entries(selected?.ports||{}).find(([,p])=>p.net===row.net);return old&&!row.terminal?{...row,label:old[0],checked:true}:row;});
  document.querySelector('#modulePublishDialog')?.close();const d=document.createElement('dialog');d.id='modulePublishDialog';d.className='sheet-dialog module-dialog';
  d.innerHTML=`<form><h2>${selected?'Publish changes':'Publish project to workspace'}</h2><div class="sheet-dialog-content"><label>Library ID<input id="releaseModuleId" value="${esc(id)}" pattern="[A-Za-z][A-Za-z0-9_-]{0,63}" required></label><label>Name<input id="releaseName" value="${esc(selected?.name||S.project.custom_title||'Circuit module')}" maxlength="120" required></label><label>Description<textarea id="releaseDescription" maxlength="2000">${esc(selected?.description||'')}</textarea></label><label>Release notes<textarea id="releaseNote" maxlength="2000"></textarea></label><p>Capture this source project's current circuit and native layout. People with source-project access can discover its published versions.</p><div class="module-terminal-list">${rows.map((row,i)=>`<label class="module-terminal"><input type="checkbox" data-release-net="${esc(row.net)}" data-release-row="${i}" ${row.checked?'checked':''} ${row.required?'disabled':''}><span>${esc(row.net)}</span><input data-release-label="${esc(row.net)}" data-release-index="${i}" value="${esc(row.label)}" maxlength="100" ${row.terminal?'readonly':''}></label>`).join('')}</div></div><div class="dialog-actions"><button type="button" class="secondary-button" data-cancel>Cancel</button><button type="submit" class="primary-button" id="confirmModulePublish">Publish</button></div></form>`;
  document.body.append(d);let publishing=false;const cancel=d.querySelector('[data-cancel]');cancel.onclick=()=>d.close();d.addEventListener('cancel',event=>{if(publishing)event.preventDefault();});d.addEventListener('close',()=>d.remove(),{once:true});
  d.querySelector('form').onsubmit=this.run(async event=>{
   event.preventDefault();await this.save();const version=S.version,snapshot=JSON.stringify(S.spec),module=d.querySelector('#releaseModuleId').value.trim(),ports={};
   for(const input of d.querySelectorAll('[data-release-row]:checked')){const i=Number(input.dataset.releaseRow),label=d.querySelector(`[data-release-index="${i}"]`).value.trim();if(!label||Object.hasOwn(ports,label))throw new Error('Published terminal names must be unique.');ports[label]=rows[i].net;}
   const previous=catalog.entries.find(row=>row.source_project===pid&&row.module===module),button=d.querySelector('#confirmModulePublish');publishing=true;button.disabled=true;cancel.disabled=true;
   try{
    const result=await this.api(`/api/workbench/projects/${pid}/modules/releases/publish`,{method:'POST',body:{base_version:version,module,name:d.querySelector('#releaseName').value.trim(),description:d.querySelector('#releaseDescription').value,note:d.querySelector('#releaseNote').value,ports,expected_version:previous?.version||0}});
    if(S.pid===pid&&S.version===version&&JSON.stringify(S.spec)===snapshot){const next=structuredClone(S.spec);next.library||={};next.library.modules||={};next.library.modules[module]=result.module;this.id=module;this.commit(next,'Published module version '+result.module.version);await this.save();}
    this.toast(`Published ${result.module.name} v${result.module.version}`);d.close();
   }finally{publishing=false;button.disabled=false;cancel.disabled=false;}
  });d.showModal();d.querySelector('#releaseName').focus();
 }
 async browseCatalog(){
  await this.save();const S=this.S,pid=S.pid;document.querySelector('#moduleCatalogDialog')?.close();const d=document.createElement('dialog');d.id='moduleCatalogDialog';d.className='sheet-dialog module-dialog module-catalog-dialog';
  d.innerHTML='<h2>Workspace modules</h2><p class="file-help">Published sources you can access. Installed instances stay pinned until you review an update.</p><div id="moduleCatalogEntries">Loading modules…</div><div class="dialog-actions"><button class="secondary-button" data-cancel>Close</button></div>';document.body.append(d);d.querySelector('[data-cancel]').onclick=()=>d.close();d.addEventListener('close',()=>d.remove(),{once:true});d.showModal();
  const result=await this.api(`/api/workbench/projects/${pid}/modules/catalog`);if(!d.open||S.pid!==pid)return;
  d.querySelector('#moduleCatalogEntries').innerHTML=result.entries.map(row=>`<article class="module-catalog-entry"><div><strong>${esc(row.name)}</strong><small>${esc(row.source_title)} · v${row.version} · ${row.components} components</small><p>${esc(row.description)}</p></div><label>Library ID<input data-catalog-name="${esc(row.id)}" value="${esc(row.module)}" pattern="[A-Za-z][A-Za-z0-9_-]{0,63}"></label><button class="primary-button" data-install-catalog="${esc(row.id)}" ${this.editable()?'':'disabled'}>Install v${row.version}</button></article>`).join('')||'<p>No accessible modules have been published. Publish a source project to start a reusable library.</p>';
  d.querySelectorAll('[data-install-catalog]').forEach(button=>button.onclick=this.run(async()=>{const uid=button.dataset.installCatalog,module=d.querySelector(`[data-catalog-name="${CSS.escape(uid)}"]`).value.trim();button.disabled=true;try{const result=await this.request('catalog/install',{catalog_id:uid,module});if(!d.open)return;this.id=module;this.commit(result.spec,'Installed workspace module');await this.save();d.close();await this.updates?.refresh();this.toast('Module installed');}finally{button.disabled=false;}}));
 }
 async editSource(){
  if(!this.editable()||!this.id)return;const result=await this.request('source',{module:this.id});
  if(JSON.stringify(result.spec)!==JSON.stringify(this.S.spec)){this.commit(result.spec,'Linked editable module source');await this.save();}
  if(result.source_project===this.S.pid)this.schematic?.();else await this.openProject?.(result.source_project);
 }
}
