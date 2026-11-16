import {esc} from './workbench-icons.mjs';
import {sheetDefinitions} from './workbench-sheets.mjs';
import {interfaceRows} from './workbench-interfaces.mjs';

export class ModuleConversionUI{
 constructor(deps){Object.assign(this,deps);}
 run(fn){return(...args)=>Promise.resolve().then(()=>fn(...args)).catch(error=>this.toast(error.message,true));}
 openDialog(){
  const S=this.state();if(!this.editable()||this.busy())return;
  const refs=[...new Set([...S.selection].map(key=>key.split('#')[0]))];if(!refs.length)return;
  const definitions=sheetDefinitions(S.spec);let index=1;while(definitions['M'+index])index++;
  const portRows=interfaceRows(S.spec,{refs,sheet:S.schematicSheet||''});
  document.querySelector('#moduleDialog')?.remove();document.querySelector('#moduleConversionDialog')?.remove();
  const d=document.createElement('dialog');d.id='moduleConversionDialog';d.className='sheet-dialog module-dialog conversion-dialog';
  d.innerHTML=`<form><h2>Convert to Component</h2><p class="file-help">${refs.length} selected components. Existing PCB placements, copper and electrical connections stay in this project.</p><div class="conversion-fields"><label>Library ID<input id="moduleId" value="Circuit" pattern="[A-Za-z][A-Za-z0-9_-]{0,63}" maxlength="64" required></label><label>Instance ID<input id="moduleInstance" value="M${index}" pattern="[A-Za-z][A-Za-z0-9_-]{0,63}" maxlength="64" required></label><label class="conversion-name">Name<input id="moduleName" value="Circuit module" maxlength="120" required></label></div><details><summary>Terminals</summary><p class="file-help">Connections leaving the selection become required terminals. Other nets can also be exposed.</p><div class="module-terminal-list">${portRows.map((row,i)=>`<label class="module-terminal"><input type="checkbox" data-convert-net="${i}" ${row.checked?'checked':''} ${row.required?'disabled':''}><span>${esc(row.net)}${row.required?' *':''}</span><input data-convert-label="${i}" value="${esc(row.label)}" maxlength="100" ${row.terminal?'readonly':''} aria-label="Terminal name for ${esc(row.net)}"></label>`).join('')}</div></details><details><summary>PCB capture bounds</summary><label class="sheet-check"><input id="autoCaptureBounds" type="checkbox" checked>Include selected footprints and their complete internal routes automatically</label><div class="conversion-bounds">${['Left','Top','Right','Bottom'].map((label,i)=>`<label>${label} (mm)<input data-capture-bound="${i}" type="number" step="any" disabled required></label>`).join('')}</div><p class="file-help">Shared nets are clipped to this region. Unselected footprints are excluded from shared-net copper. Review boundary connections after reuse.</p></details><div id="moduleCapturePreview" class="module-capture-preview" hidden></div><p id="moduleCaptureSummary" class="file-help" aria-live="polite">Prepare the module to inspect the layout before converting.</p><div class="dialog-actions"><button type="button" class="secondary-button" data-cancel>Cancel</button><button type="submit" class="secondary-button" id="prepareModuleConversion">Prepare module</button><button type="button" class="primary-button" id="confirmModuleConversion" disabled>Convert to component</button></div></form>`;
  document.body.append(d);const $=selector=>d.querySelector(selector),confirm=$('#confirmModuleConversion');this.prepared=null;
  const invalidate=()=>{this.prepared=null;confirm.disabled=true;$('#moduleCaptureSummary').textContent='Settings changed. Prepare the module to update the preview.';};
  d.querySelector('form').addEventListener('input',invalidate);
  $('#autoCaptureBounds').onchange=()=>d.querySelectorAll('[data-capture-bound]').forEach(input=>input.disabled=$('#autoCaptureBounds').checked);
  $('[data-cancel]').onclick=()=>d.close();d.addEventListener('close',()=>{this.preview?.destroy?.();this.preview=null;this.prepared=null;d.remove();},{once:true});
  d.querySelector('form').onsubmit=this.run(async event=>{
   event.preventDefault();const ports={};d.querySelectorAll('[data-convert-net]:checked').forEach(input=>{const i=Number(input.dataset.convertNet),label=$(`[data-convert-label="${i}"]`).value.trim();if(!label||Object.hasOwn(ports,label))throw new Error('Terminal names must be nonempty and unique.');ports[label]=portRows[i].net;});
   const body={refs,module:$('#moduleId').value,instance:$('#moduleInstance').value,name:$('#moduleName').value.trim(),ports};
   if(!$('#autoCaptureBounds').checked)body.bounds=[...d.querySelectorAll('[data-capture-bound]')].map(input=>Number(input.value));
   const prepare=$('#prepareModuleConversion');prepare.disabled=true;confirm.disabled=true;
   try{
    const result=await this.request(body);if(!d.open||!d.isConnected)return;this.prepared={result,snapshot:JSON.stringify(S.spec),version:S.version,pid:S.pid};
    d.querySelectorAll('[data-capture-bound]').forEach((input,i)=>input.value=result.capture.bounds[i]);
    this.preview?.destroy?.();const host=$('#moduleCapturePreview');host.hidden=false;host.innerHTML='';
    if(window.BoardView)this.preview=new window.BoardView(host,result.capture_geometry,{compact:true,editable:false,readOnly:true,ratsnest:true});
    const c=result.capture,counts=c.counts;$('#moduleCaptureSummary').textContent=`Captured ${refs.length} components, ${counts.tracks} traces, ${counts.arcs} arcs, ${counts.vias} vias and ${counts.zones} zones. ${c.clipped_tracks+c.clipped_arcs+c.clipped_zones} boundary clips; ${c.excluded_components.length} unselected footprints excluded.${c.omitted_guide_ids?.length?` ${c.omitted_guide_ids.length} outdated wire drawings do not match the saved nets and will be removed.`:''} The current PCB remains unchanged.`;
    confirm.disabled=false;
   }finally{prepare.disabled=false;}
  });
  confirm.onclick=this.run(()=>{
   const prepared=this.prepared;if(!prepared||prepared.pid!==S.pid||prepared.version!==S.version||prepared.snapshot!==JSON.stringify(S.spec)){invalidate();throw new Error('The design changed. Prepare the module again.');}
   this.commit(prepared.result.spec,'Converted selection to component',null);d.close();this.open(prepared.result.instance);this.toast('Selection converted. The current PCB layout and net connections are preserved.');
  });
  d.showModal();$('#moduleName').focus();$('#moduleName').select();
 }
}
