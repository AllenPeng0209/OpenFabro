import {esc,icon} from './workbench-icons.mjs';

export class RouteTuningUI{
 constructor(deps){Object.assign(this,deps);this.sequence=0;}
 get S(){return this.state();}
 scope(){const s=this.S;return JSON.stringify([s.pid,s.projectLoadToken,s.session?.user?.id||s.project.access?.user?.id||'device']);}
 cancel(){this.sequence++;this.request?.abort();this.request=null;this.context=null;this.preview?.destroy?.();this.preview=null;const d=this.dialog;this.dialog=null;if(d?.open)d.close();d?.remove();}
 valid(c=this.context){const s=this.S;return!!(c&&this.context===c&&this.dialog?.open&&this.scope()===c.scope&&s.canvas===c.canvas&&s.active==='layout'&&s.version===c.version&&s.generation===c.generation&&JSON.stringify(s.spec)===c.snapshot&&this.editable()&&!this.busy()&&!s.nativePending&&JSON.stringify(s.canvas?.nativeIdentity)===c.identity);}
 reconcile(){if(this.context&&!this.valid())this.cancel();}
 inspectorHTML(){return`<section class="inspector-section"><h3>Length & matching</h3><button class="secondary-button" id="tuneRouteLength">${icon('link')}Tune length…</button><p>Review a length, reference-net or modeled delay target on the current routed PCB.</p></section>`;}
 bind(host,net,trackId=null){const button=host.querySelector('#tuneRouteLength');if(!button)return;button.disabled=!this.editable()||this.busy()||this.S.nativePending;button.onclick=()=>this.open(net,trackId).catch(error=>this.toast(error.message,true));}
 async open(net,trackId=null){
  this.cancel();const ticket=this.sequence,owner=this.scope();if(!this.editable()||this.busy()||this.interacting())throw Error('Finish the current edit before tuning a route.');await this.save();if(this.sequence!==ticket||this.scope()!==owner)return;
  const s=this.S,canvas=s.canvas,native=canvas?.nativeIdentity;if(s.active!=='layout'||s.nativePending||native?.source_version!==s.version)throw Error('Wait for the current native PCB layout before tuning.');
  const version=s.version,generation=s.generation,snapshot=JSON.stringify(s.spec),request=new AbortController();this.request=request;let data;
  try{data=await this.api(`/api/workbench/projects/${s.pid}/route-tuning`,{signal:request.signal});}catch(error){if(request.signal.aborted||this.sequence!==ticket)return;throw error;}
  if(this.sequence!==ticket||this.scope()!==owner||this.S.canvas!==canvas||s.version!==version||s.generation!==generation||JSON.stringify(s.spec)!==snapshot)return;
  if(data.source_version!==version||data.pcb_sha256!==native.pcb_sha256)throw Error('The native PCB changed. Refresh Layout before tuning.');
  const row=data.routes.find(r=>r.net===net);if(!row)throw Error('This net has no current native route.');const pair=s.routingProfiles?.pairs?.find(p=>p.nets.includes(net)),partner=pair?.nets.find(n=>n!==net),d=document.createElement('dialog');d.id='routeTuningDialog';d.className='sheet-dialog route-tuning-dialog';this.dialog=d;
  const c={scope:owner,ticket,pid:s.pid,canvas,identity:JSON.stringify(native),version,generation,snapshot,serial:0,prepared:null};this.context=c;
  const n=value=>value===null||value===undefined?'Unknown':Number(value).toFixed(3);
  d.innerHTML=`<form><h2>Tune route length</h2><div class="tuning-dialog-body"><div class="tuning-settings"><p class="tuning-current"><strong>${esc(net)}</strong> · ${n(row.length_mm)} mm${row.delay_ps===null?'':` · ${n(row.delay_ps)} ps`}</p>${partner?`<label class="tuning-pair-choice"><input id="tuningPair" type="checkbox" checked>Tune declared pair ${esc(net)} / ${esc(partner)} together</label>`:''}<label>Target<select id="tuningTargetMode"><option value="length">Absolute length</option><option value="reference">Match reference net</option><option value="delay">Modeled delay</option></select></label><label id="tuningTargetLabel"><span id="tuningTargetCaption">Target length (mm)</span><input id="tuningTarget" type="number" min="0.001" step="any" value="${row.length_mm===null?'':+(row.length_mm+5).toFixed(3)}"></label><label id="tuningReferenceLabel" hidden>Reference net<select id="tuningReference">${data.routes.filter(r=>r.net!==net&&r.net!==partner).map(r=>`<option value="${esc(r.net)}" ${r.ready?'':'disabled'}>${esc(r.net)} · ${n(r.length_mm)} mm</option>`).join('')}</select></label><div class="tuning-two-fields"><label>Tolerance (mm)<input id="tuningTolerance" type="number" min="0.001" step="any" value="0.05"></label><label>Meander style<select id="tuningStyle"><option value="trombone">Trombone</option><option value="accordion">Accordion</option><option value="sawtooth">Sawtooth</option></select></label></div><details><summary>Meander settings</summary><div class="tuning-two-fields">${[['Radius (mm)','radius_mm'],['Pitch (mm)','pitch_mm'],['Maximum amplitude (mm)','max_amplitude_mm'],['Cells','cells']].map(([label,key])=>`<label>${label}<input data-tuning-option="${key}" type="number" min="${key==='radius_mm'?0:.001}" step="any" placeholder="Automatic"></label>`).join('')}</div><label>Placement<select id="tuningSide"><option value="auto">Either side</option><option value="left">Left of trace direction</option><option value="right">Right of trace direction</option></select></label></details><p class="tuning-model">Lengths follow the trace centreline outside endpoint pads. Delay requires your propagation model. Geometric matching does not establish signal integrity.</p><p id="routeTuningMessage" role="status">${row.ready?'Choose a target, then review the native result.':esc(row.reason)}</p></div><div class="tuning-result"><div id="tuningMeasurements"></div><div id="routeTuningPreview" class="tuning-native-preview" hidden></div><p id="tuningNativeProof" class="tuning-model"></p></div></div><div class="dialog-actions"><button type="button" class="secondary-button" id="cancelRouteTuning">Cancel</button><button type="submit" class="secondary-button" id="reviewRouteTuning" ${row.ready?'':'disabled'}>Review routing</button><button type="button" class="primary-button" id="applyRouteTuning" disabled>Apply tuning</button></div></form>`;
  document.body.append(d);const $=selector=>d.querySelector(selector),names=()=>$('#tuningPair')?.checked?[net,partner]:[net];
  const body=()=>{
   const mode=$('#tuningTargetMode').value,settings={nets:names(),tolerance_mm:Number($('#tuningTolerance').value),style:$('#tuningStyle').value,side:$('#tuningSide').value};
   if(mode==='reference')settings.reference_net=$('#tuningReference').value;else settings[mode==='delay'?'target_delay_ps':'target_mm']=Number($('#tuningTarget').value);
   for(const input of d.querySelectorAll('[data-tuning-option]'))if(input.value!=='')settings[input.dataset.tuningOption]=Number(input.value);
   if(trackId)settings.track_ids=[trackId];return settings;
  };
  const invalidate=()=>{c.serial++;c.prepared=null;this.request?.abort();this.preview?.destroy?.();this.preview=null;$('#routeTuningPreview').hidden=true;$('#tuningMeasurements').replaceChildren();$('#tuningNativeProof').textContent='';$('#applyRouteTuning').disabled=true;$('#reviewRouteTuning').disabled=!row.ready;};
  const changeMode=()=>{const mode=$('#tuningTargetMode').value;$('#tuningTargetLabel').hidden=mode==='reference';$('#tuningReferenceLabel').hidden=mode!=='reference';$('#tuningTargetCaption').textContent=mode==='delay'?'Target delay (ps)':'Target length (mm)';};
  d.querySelector('form').oninput=()=>{invalidate();changeMode();};d.querySelector('form').onchange=()=>{invalidate();changeMode();};
  $('#cancelRouteTuning').onclick=()=>this.cancel();d.oncancel=()=>this.cancel();d.addEventListener('close',()=>{if(this.dialog===d)this.cancel();},{once:true});d.addEventListener('keydown',event=>event.stopPropagation());
  d.querySelector('form').onsubmit=async event=>{
   event.preventDefault();if(!this.valid(c)){this.cancel();return;}const settings=body(),signature=JSON.stringify(settings),serial=++c.serial,controller=new AbortController();this.request=controller;c.prepared=null;$('#applyRouteTuning').disabled=true;$('#reviewRouteTuning').disabled=true;$('#routeTuningMessage').textContent='Building and checking the native meander…';
   try{
    const result=await this.api(`/api/workbench/projects/${c.pid}/route-tuning/prepare`,{method:'POST',body:{...settings,base_version:c.version},signal:controller.signal});
    if(!this.valid(c)||serial!==c.serial||JSON.stringify(body())!==signature)return;
    if(result.base_version!==c.version||result.native_source?.source_pcb_sha256!==native.pcb_sha256||result.native_source?.source_render_inputs_sha256!==native.render_inputs_sha256)throw Error('The reviewed native source differs from this PCB. Refresh Layout.');
    c.prepared={result,signature};const rows=result.summary.measurements;
    $('#tuningMeasurements').innerHTML=`<table class="design-table"><thead><tr><th>Net</th><th>Before</th><th>Target</th><th>After (mm)</th></tr></thead><tbody>${rows.map(r=>`<tr data-tuned-net="${esc(r.net)}" data-after-mm="${r.after_length_mm}"><td>${esc(r.net)}</td><td>${n(r.before_length_mm)}</td><td>${n(r.target_mm)}</td><td>${n(r.after_length_mm)}</td></tr>`).join('')}</tbody></table>`;
    const host=$('#routeTuningPreview');host.hidden=false;this.preview?.destroy?.();this.preview=new window.BoardView(host,result.geometry,{compact:true,readOnly:true,editable:false,ratsnest:false});
    $('#tuningNativeProof').textContent=`Native pin connections ${result.native_parity.ok?'unchanged':'failed'}. KiCad DRC: ${result.drc.errors} errors · ${result.drc.warnings} warnings · ${result.drc.unconnected} unconnected; ${result.new_violation_count} new error/unconnected findings.`;
    $('#routeTuningMessage').textContent=result.safe_to_apply?(result.summary.changed?'Native geometry meets the target. Review the result before applying.':'The current route already meets this target.'):'The preview introduces native findings and cannot be applied.';$('#applyRouteTuning').disabled=!result.safe_to_apply;
   }catch(error){if(this.valid(c)&&serial===c.serial&&!controller.signal.aborted)$('#routeTuningMessage').textContent=error.message;}
   finally{if(this.valid(c)&&serial===c.serial)$('#reviewRouteTuning').disabled=!row.ready;}
  };
  $('#applyRouteTuning').onclick=async()=>{
   if(!this.valid(c)||!c.prepared||c.prepared.signature!==JSON.stringify(body())){invalidate();return;}const result=c.prepared.result;this.cancel();
   try{await this.apply(c.pid,c.version,result.spec,result.native_source);this.toast('Route length tuning saved.');}catch(error){this.toast(error.message,true);}
  };
  d.showModal();$('#tuningTarget').focus();
 }
}
