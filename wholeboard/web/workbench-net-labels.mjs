import {esc,icon} from './workbench-icons.mjs';
import {DesignCanvas} from './workbench-canvas.mjs';

export class NetLabelsUI{
 constructor(deps){Object.assign(this,deps);this.pending=false;}
 get S(){return this.state();}
 run(fn){return(...args)=>Promise.resolve().then(()=>fn(...args)).catch(error=>this.toast(error.message,true));}
 async request(body){
  await this.save();const S=this.S,pid=S.pid,version=S.version,snapshot=JSON.stringify(S.spec);
  const result=await this.api(`/api/workbench/projects/${pid}/net-labels/prepare`,{method:'POST',body:{...body,base_version:version}});
  if(S.pid!==pid||S.version!==version||JSON.stringify(S.spec)!==snapshot)throw new Error('The design changed while preparing this label. Review it again.');
  return {result,version,snapshot,pid};
 }
 async change(id,patch){
  if(!this.editable()||this.busy()||this.pending)return;this.pending=true;
  try{const {result}=await this.request({action:'update',id,patch});if(!result.spec)return this.open({action:'update',id,patch});this.commit(result.spec,'Updated net label',null);this.select(id);await this.save();}
  finally{this.pending=false;}
 }
 async open(args={action:'add'}){
  if(!this.editable()||this.busy())return;await this.save();const S=this.S,pid=S.pid,node=S.spec.editor?.wire_nodes?.[args.id],patch=args.patch||{},net=S.spec.nets.find(n=>n.name===(patch.net||node?.net||args.net));
  const anchor=S.schematicData?.anchors.find(a=>a.anchor===args.anchor),origin=anchor?.position,delta=anchor&&anchor.escape.map((v,i)=>v-origin[i]);
  const nearPin=origin?.map((v,i)=>Math.round((v+(Math.abs(delta?.[i]||0)>.01?Math.sign(delta[i])*100:i===1&&!delta?.some(v=>Math.abs(v)>.01)?-100:0))/10)*10);
  const kind=patch.kind||args.kind||node?.label?.kind||'auto',position=patch.position||args.position||node?.position||nearPin||this.defaultPosition(),name=patch.net??args.net??node?.net??(kind==='ground'?'GND':kind==='power'?'+3V3':'Net_'+(S.spec.nets.length+1));
  document.querySelector('#netLabelDialog')?.close();const d=document.createElement('dialog');d.id='netLabelDialog';d.className='sheet-dialog net-label-dialog';
  d.innerHTML=`<form><h2>${args.action==='delete'?'Remove symbol':node?.label?'Edit net label':'Create a net or connect to an existing net'}</h2><div class="net-label-body"><div class="sheet-dialog-content"><label>Net name<input id="labelNetName" value="${esc(name)}" list="labelExistingNets" maxlength="100" required><datalist id="labelExistingNets">${S.spec.nets.map(n=>`<option value="${esc(n.name)}"></option>`).join('')}</datalist></label><div class="asset-property-pair"><label>Symbol<select id="labelKind">${[['auto','From Net Type'],['net','Net label'],['power','Power symbol'],['ground','Ground symbol']].map(([value,label])=>`<option value="${value}" ${value===kind?'selected':''}>${label}</option>`).join('')}</select></label><label>Net Type<select id="labelNetType"><option value="signal" ${net?.class!=='power'&&!['power','ground'].includes(kind)?'selected':''}>Signal</option><option value="power" ${net?.class==='power'||['power','ground'].includes(kind)?'selected':''}>Power</option></select></label></div><label>Rotation<select id="labelRotation">${[0,90,180,270].map(v=>`<option value="${v}" ${v===(patch.rotation??node?.label?.rotation??0)?'selected':''}>${v}°</option>`).join('')}</select></label>${args.wire?'<p>Placed on the selected native wire. Its paths and junctions are retained.</p>':`<div class="asset-property-pair">${position.map((value,i)=>`<label>Schematic ${i?'Y':'X'}<input type="number" step="10" data-label-axis="${i}" value="${value}" required></label>`).join('')}</div>`}<p>${args.action==='delete'?'Remove the label or power symbol. Named pin connections stay intact. A connected wire endpoint remains.':node?.label?'Changing this name renames the project net and every label on it. An existing destination net requires explicit merge review.':'Pins on the same project net are connected without drawing wires between every pin. This symbol adds no PCB part or pad.'}</p></div><div id="labelMergeReview" class="net-label-merge" hidden></div><div id="labelReviewSummary" class="file-help" aria-live="polite"></div><div id="labelPreviewTabs" class="module-update-preview-tabs" hidden><button type="button" class="secondary-button" data-label-preview="schematic">Schematic</button><button type="button" class="secondary-button" data-label-preview="pcb">PCB layout</button></div><div id="labelNativePreview" class="net-label-preview" hidden></div></div><div class="dialog-actions"><button type="button" class="secondary-button" data-cancel>Cancel</button><button type="submit" class="secondary-button" id="reviewNetLabel">Review connection</button><button type="button" class="primary-button" id="applyNetLabel" disabled>${args.action==='delete'?'Remove symbol':'Apply'}</button></div></form>`;
  document.body.append(d);const $=s=>d.querySelector(s),apply=$('#applyNetLabel'),review=$('#reviewNetLabel');let prepared=null,preview=null,mode='schematic';
  if(args.action==='delete')d.querySelectorAll('.sheet-dialog-content input,.sheet-dialog-content select').forEach(input=>input.disabled=true);
  const body=()=>{
   if(args.action==='delete')return{action:'delete',id:args.id};
   const values={net:$('#labelNetName').value.trim(),kind:$('#labelKind').value,rotation:Number($('#labelRotation').value),net_type:$('#labelNetType').value,position:args.wire?position:[...d.querySelectorAll('[data-label-axis]')].map(input=>Number(input.value))};
   return {...(args.action==='update'?{action:'update',id:args.id,patch:values}:{...args,...values,sheet:args.sheet??S.schematicSheet??''}),confirm_merge:$('#confirmLabelMerge')?.checked||false};
  };
  const invalidate=()=>{prepared=null;apply.disabled=true;$('#labelReviewSummary').textContent='Review the current settings before applying them.';};
  d.querySelector('form').oninput=event=>{
   invalidate();if(event.target.id==='labelKind'&&$('#labelKind').value==='ground'){$('#labelNetName').value='GND';$('#labelNetType').value='power';}
   if(event.target.id==='labelNetName'){const target=S.spec.nets.find(n=>n.name===event.target.value);if(target)$('#labelNetType').value=target.class==='power'?'power':'signal';}
   if(event.target.id==='labelKind'&&$('#labelKind').value==='power')$('#labelNetType').value='power';
   if(event.target.id!=='confirmLabelMerge'){$('#labelMergeReview').hidden=true;$('#labelMergeReview').replaceChildren();}
  };
  const draw=()=>{preview?.destroy?.();const host=$('#labelNativePreview');host.replaceChildren();host.classList.remove('boardview');if(!prepared)return;preview=mode==='pcb'&&window.BoardView?new window.BoardView(host,prepared.result.geometry,{compact:true,readOnly:true,editable:false,ratsnest:true}):new DesignCanvas(host,prepared.result.spec,{mode:'schematic',nativeScene:prepared.result.schematic,sheet:args.sheet??S.schematicSheet??'',readOnly:true});};
  d.querySelectorAll('[data-label-preview]').forEach(button=>button.onclick=()=>{mode=button.dataset.labelPreview;draw();});
  $('[data-cancel]').onclick=()=>d.close();d.addEventListener('close',()=>{prepared=null;preview?.destroy?.();d.remove();},{once:true});
  d.querySelector('form').onsubmit=this.run(async event=>{
   event.preventDefault();if(this.busy()||!this.editable())return;const settings=JSON.stringify(body());review.disabled=true;apply.disabled=true;
   try{const proposal=await this.request(body());if(!d.open||S.pid!==pid||JSON.stringify(body())!==settings)return;const {result}=proposal;
    if(result.merge){$('#labelMergeReview').hidden=false;$('#labelMergeReview').innerHTML=`<p>Merge <strong>${esc(result.merge.from)}</strong> into <strong>${esc(result.merge.to)}</strong>. Pins on both nets will become connected. Existing copper on these nets is cleared for rerouting.</p><label class="sheet-check"><input id="confirmLabelMerge" type="checkbox" ${JSON.parse(settings).confirm_merge?'checked':''}>Confirm this electrical merge</label>`;}
    if(!result.spec){prepared=null;preview?.destroy?.();preview=null;$('#labelNativePreview').hidden=true;$('#labelPreviewTabs').hidden=true;$('#labelReviewSummary').textContent='Confirm the electrical merge, then review again.';return;}
    prepared={...proposal,settings:JSON.stringify(body())};$('#labelReviewSummary').textContent=`Native KiCad pin groups match.${result.summary.invalidated_nets.length?' Reroute: '+result.summary.invalidated_nets.join(', ')+'.':' Existing copper is retained.'} Review ERC and DRC before building.${result.validation.errors.length?' Design findings: '+result.validation.errors.join('; '):''}`;$('#labelNativePreview').hidden=false;$('#labelPreviewTabs').hidden=false;draw();apply.disabled=false;
   }finally{review.disabled=false;}
  });
  apply.onclick=this.run(async()=>{if(!prepared||S.pid!==pid||S.version!==prepared.version||JSON.stringify(S.spec)!==prepared.snapshot||JSON.stringify(body())!==prepared.settings){invalidate();throw new Error('The design changed. Review the label again.');}const result=prepared.result;this.commit(result.spec,args.action==='delete'?'Removed net symbol':'Edited named net connection',null);d.close();if(args.action!=='delete')this.select(result.id);await this.save();});
  d.showModal();$('#labelNetName').focus();
 }
 defaultPosition(){const extent=this.S.schematicData?.sheets.find(p=>p.name===(this.S.schematicSheet||''))?.extent;return extent?[Math.round(extent[0]/10)*10,Math.round((extent[1]-80)/10)*10]:[200,160];}
 pinMenu(pin,anchor,point){
  if(!this.editable()||this.busy())return;document.querySelector('#pinNetMenu')?.remove();const menu=document.createElement('div');menu.id='pinNetMenu';menu.className='popover pin-net-menu';menu.setAttribute('role','menu');
  menu.innerHTML=`<p>${esc(pin)}</p><button data-pin-net-action="wire">Draw wire</button><button data-pin-net-action="named">Create a net or connect to an existing net</button><button data-pin-net-action="ground">Connect to the GND net</button><button data-pin-net-action="edit">Edit net connections</button><button data-pin-net-action="bus">Bus and impedance properties</button>`;
  document.body.append(menu);menu.style.left=Math.max(8,Math.min(innerWidth-310,point?.[0]??innerWidth/2))+'px';menu.style.top=Math.max(8,Math.min(innerHeight-210,point?.[1]??innerHeight/2))+'px';
  const dismiss=()=>{menu.remove();document.removeEventListener('pointerdown',close,true);document.removeEventListener('keydown',key,true);};
  const close=event=>{if(!menu.contains(event.target))dismiss();},key=event=>{if(event.key==='Escape')dismiss();};
  menu.querySelectorAll('[data-pin-net-action]').forEach(button=>button.onclick=this.run(()=>{const action=button.dataset.pinNetAction;dismiss();if(action==='wire')this.startWire(pin,anchor);else if(action==='edit')this.editNet(pin);else if(action==='bus')return this.editBus?.(pin);else return this.open({action:'add',anchor:anchor||pin,net:action==='ground'?'GND':this.S.spec.nets.find(n=>n.pins.includes(pin))?.name,kind:action==='ground'?'ground':'auto'});}));
  // The opening pointerdown has already passed document's capture phase.
  document.addEventListener('pointerdown',close,true);document.addEventListener('keydown',key,true);
 }
 inspector(id,node){
  const net=this.S.spec.nets.find(n=>n.name===node.net);
  return `<div class="inspector-name"><span class="part-badge">${icon('link')}</span><div class="name-stack"><strong>${esc(node.net)}</strong><small>${node.label.kind==='ground'?'Ground symbol':node.label.kind==='power'?'Power symbol':'Net label'}</small></div></div><section class="inspector-section"><h3>Named connection</h3><label class="property-row"><span>Net Type</span><select data-label-property="net_type"><option value="signal" ${net?.class!=='power'?'selected':''}>Signal</option><option value="power" ${net?.class==='power'?'selected':''}>Power</option></select></label><label class="property-row"><span>Rotation</span><select data-label-property="rotation">${[0,90,180,270].map(v=>`<option value="${v}" ${v===(node.label.rotation||0)?'selected':''}>${v}°</option>`).join('')}</select></label><p>${net?.pins.length||0} pins on this project net. No PCB part or pad.</p><button class="secondary-button" id="editNetLabel">Edit label and net name</button></section><section class="inspector-section"><h3>Position</h3>${['X','Y'].map((key,i)=>`<label class="property-row"><span>${key}</span><input type="number" step="10" data-wire-node-axis="${i}" value="${node.position[i]}"></label>`).join('')}<button class="secondary-button" id="startWireFromNode">Draw from label</button><button class="secondary-button" id="inspectWireNodeNet">Inspect net</button></section><section class="inspector-section"><button class="secondary-button danger-text" id="deleteNetLabel">Remove symbol</button><p>Named connections stay intact.</p></section>`;
 }
 bindInspector(host,id){host.querySelector('#editNetLabel')?.addEventListener('click',this.run(()=>this.open({action:'update',id})));host.querySelector('#deleteNetLabel')?.addEventListener('click',this.run(()=>this.open({action:'delete',id})));host.querySelectorAll('[data-label-property]').forEach(input=>input.onchange=this.run(()=>this.change(id,{[input.dataset.labelProperty]:input.dataset.labelProperty==='rotation'?Number(input.value):input.value})));}
 bindCatalog(host){host.querySelectorAll('[data-add-net-label]').forEach(button=>{const kind=button.dataset.addNetLabel;button.onclick=this.run(()=>this.open({action:'add',kind}));button.draggable=true;button.ondragstart=e=>e.dataTransfer.setData('application/x-wholeboard-net-label',kind);});}
 bindDrop(host){host.addEventListener('dragover',event=>{if([...event.dataTransfer.types].includes('application/x-wholeboard-net-label'))event.preventDefault();});host.addEventListener('drop',event=>{const kind=event.dataTransfer.getData('application/x-wholeboard-net-label');if(!kind||this.S.active!=='schematic')return;event.preventDefault();const at=this.S.canvas?.worldPoint(event);if(at)this.run(()=>this.open({action:'add',kind,position:[at.x,at.y].map(v=>Math.round(v/10)*10)}))();});}
}
