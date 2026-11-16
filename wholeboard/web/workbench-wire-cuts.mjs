import {esc} from './workbench-icons.mjs';
import {DesignCanvas} from './workbench-canvas.mjs';

export class WireCutsUI{
 constructor(deps){Object.assign(this,deps);}
 run(fn){return(...args)=>Promise.resolve().then(()=>fn(...args)).catch(error=>this.toast(error.message,true));}
 open(){
  const S=this.state();if(!this.editable()||this.busy())return;
  const route=S.schematicData?.routes.find(r=>r.index===S.selectedWireIndex&&r.sheet===(S.schematicSheet||''));if(!route||route.status!=='routed')throw new Error('Select a routed schematic wire.');
  const pair=route.points.slice(1).map((p,i)=>[route.points[i],p]).sort((a,b)=>Math.hypot(...b[0].map((v,i)=>v-b[1][i]))-Math.hypot(...a[0].map((v,i)=>v-a[1][i])))[0];
  const point=S.selectedWirePoint||pair[0].map((v,i)=>(v+pair[1][i])/2),pid=S.pid;this.cancel();
  document.querySelector('#wireCutDialog')?.close();
  const d=document.createElement('dialog');d.id='wireCutDialog';d.className='sheet-dialog module-dialog conversion-dialog wire-cut-dialog';
  d.innerHTML=`<form><h2>Cut wire</h2><p class="file-help">${esc(route.net)} · Review the resulting electrical groups and PCB changes.</p><div class="conversion-fields"><label>Operation<select id="wireCutMode"><option value="gap">Cut a gap</option><option value="segment">Remove selected segment</option></select></label><label>Gap (grid steps)<input id="wireCutGap" type="number" min="1" max="100" step="1" value="2" required></label><label>New net name<input id="wireCutName" value="${esc(route.net+'_CUT')}" maxlength="240" required></label><label>Keep original name<select id="wireCutRetain"><option value="">Automatic</option></select></label></div><div id="wireCutBindings"></div><div id="wireCutGroups" class="wire-cut-groups"></div><div id="wireCutPreview" class="wire-cut-preview" hidden></div><p id="wireCutSummary" class="file-help" aria-live="polite">Preview the cut before applying.</p><div class="dialog-actions"><button type="button" class="secondary-button" data-cancel>Cancel</button><button type="submit" class="secondary-button" id="prepareWireCut">Preview cut</button><button type="button" class="primary-button" id="confirmWireCut" disabled>Apply cut</button></div></form>`;
  document.body.append(d);const $=s=>d.querySelector(s),confirm=$('#confirmWireCut'),prepare=$('#prepareWireCut');let prepared=null,preview=null,required=[];
  const args=()=>({wire:route.id,sheet:route.sheet,point,mode:$('#wireCutMode').value,gap_units:Number($('#wireCutGap').value)*10,new_name:$('#wireCutName').value.trim(),...($('#wireCutRetain').value?{retain_group:$('#wireCutRetain').value}:{}),port_bindings:Object.fromEntries([...d.querySelectorAll('[data-cut-binding]')].filter(input=>input.value).map(input=>[input.dataset.cutBinding,input.value]))});
  const invalidate=()=>{prepared=null;confirm.disabled=true;$('#wireCutSummary').textContent='Settings changed. Preview the cut again.';};
  d.querySelector('form').oninput=event=>{invalidate();if(['wireCutMode','wireCutGap'].includes(event.target.id)){required=[];$('#wireCutBindings').innerHTML='';$('#wireCutRetain').value='';}};
  $('#wireCutMode').onchange=()=>{$('#wireCutGap').disabled=$('#wireCutMode').value==='segment';invalidate();};
  $('[data-cancel]').onclick=()=>d.close();d.addEventListener('close',()=>{prepared=null;preview?.destroy();d.remove();},{once:true});
  d.querySelector('form').onsubmit=this.run(async event=>{
   event.preventDefault();await this.save();if(!d.open)return;if(S.pid!==pid)throw new Error('The project changed. Select its wire again.');
   const body=args(),settings=JSON.stringify(body),snapshot=JSON.stringify(S.spec),version=S.version;prepare.disabled=true;confirm.disabled=true;
   try{
    const result=await this.api(`/api/workbench/projects/${pid}/wire-cuts/prepare`,{method:'POST',body:{...body,base_version:version}});
    if(!d.open||!d.isConnected)return;
    if(S.pid!==pid||S.version!==version||JSON.stringify(S.spec)!==snapshot||JSON.stringify(args())!==settings){invalidate();return;}
    const selected=$('#wireCutRetain').value;$('#wireCutRetain').innerHTML=`<option value="">${result.summary.retained_by_interface?'Module interface':result.summary.retained_by_label?'Named labels':'Automatic'}</option>`+result.groups.map(g=>`<option value="${esc(g.id)}">${esc(g.name||g.id)} · ${g.pins.length} pins</option>`).join('');$('#wireCutRetain').value=result.summary.retained_by_interface||result.summary.retained_by_label?'':selected;$('#wireCutRetain').disabled=!!(result.summary.retained_by_interface||result.summary.retained_by_label);
    $('#wireCutGroups').innerHTML=result.groups.map(g=>`<div class="wire-cut-group" data-cut-group="${esc(g.id)}"><strong>${esc(g.name||g.id)}</strong><span>${g.pins.map(esc).join(', ')||'Wire only · no component pins'}</span></div>`).join('');
    if(result.required_bindings.length)required=result.required_bindings;
    const previous=body.port_bindings;$('#wireCutBindings').innerHTML=required.length?`<p class="file-help">Choose which group stays connected to each module interface.</p>${required.map(port=>`<label class="wire-cut-binding">${esc(port.label)}<select data-cut-binding="${esc(port.id)}"><option value="">Choose group</option>${(result.binding_groups||result.groups).map((g,i)=>`<option value="${esc(g.id)}" ${previous[port.id]===g.id?'selected':''}>${esc(g.name||'Group '+(i+1))} · ${g.pins.map(esc).join(', ')||'wire only'}</option>`).join('')}</select></label>`).join('')}`:'';
    preview?.destroy();preview=null;const host=$('#wireCutPreview');host.innerHTML='';host.hidden=!result.spec;
    if(!result.spec){$('#wireCutSummary').textContent='The module interface does not identify a unique side. Choose its group and preview again.';prepared=null;return;}
    const colors=Object.fromEntries(result.groups.map((g,i)=>[g.name,['#8bb59a','#e8b172','#82aef2','#ce98e3'][i%4]]));
    preview=new DesignCanvas(host,result.spec,{mode:'schematic',nativeScene:result.preview,sheet:route.sheet,readOnly:true,netColors:colors});
    const s=result.summary,c=s.removed_copper,count=(n,word)=>n+' '+word+(n===1?'':'s');$('#wireCutSummary').textContent=`${count(s.changed_pins.length,'pin')} change${s.changed_pins.length===1?'s':''} net. ${count(s.unrouted_pins.length,'pin')} connected by labels stay${s.unrouted_pins.length===1?'s':''} on ${s.net}. PCB: ${count(c.tracks,'trace')}, ${count(c.arcs,'arc')}, ${count(c.vias,'via')} and ${count(c.zones,'zone')} removed.${s.cleared_planes.length?' Automatic pours cleared: '+s.cleared_planes.join(', ')+'.':''}${s.retained_by_label?' Explicit named labels retain their project net.':''}${!s.electrically_split?' Named pin memberships remain unchanged.':''}`;
    prepared={result,version,snapshot,settings:JSON.stringify(args())};confirm.disabled=false;
   }finally{prepare.disabled=false;}
  });
  confirm.onclick=this.run(()=>{
   if(!prepared||S.pid!==pid||S.version!==prepared.version||JSON.stringify(S.spec)!==prepared.snapshot||JSON.stringify(args())!==prepared.settings){invalidate();throw new Error('The design changed. Preview the cut again.');}
   S.selectedWireIndex=null;S.selectedWireNode=null;S.selectedWirePoint=null;this.commit(prepared.result.spec,'Cut schematic wire electrically',null);d.close();this.toast('Electrical cut saved. Run design checks before routing.');
  });
  d.showModal();prepare.focus();
 }
}
