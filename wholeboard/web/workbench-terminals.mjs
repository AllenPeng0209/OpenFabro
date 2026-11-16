import {esc,icon} from './workbench-icons.mjs';

export class TerminalsUI{
 constructor(deps){Object.assign(this,deps);this.pending=false;}
 get S(){return this.state();}
 run(fn){return(...args)=>Promise.resolve().then(()=>fn(...args)).catch(error=>this.toast(error.message,true));}
 async perform(body,action,{open=false,page}={}){
  if(!this.editable()||this.busy()||this.pending)return;
  this.pending=true;this.markBusy();
  try{
   await this.save();const S=this.S,pid=S.pid,version=S.version,snapshot=JSON.stringify(S.spec);
   const result=await this.api(`/api/workbench/projects/${pid}/terminals/prepare`,{method:'POST',body:{...body,base_version:version}});
   if(S.pid!==pid||S.version!==version||JSON.stringify(S.spec)!==snapshot)throw new Error('The design changed while preparing this terminal. Try again.');
   S.inspector=true;this.commit(result.spec,action,result.ref);
   if(open){this.schematic();if(page!==undefined)this.openSheet(page);}
   if(result.ref)this.select(result.ref);
   if(body.action==='delete')this.toast('Terminal removed. Named net links between other pins remain connected.');
   return result;
  }finally{this.pending=false;this.inspect();this.markBusy();}
 }
 markBusy(){for(const input of document.querySelectorAll('[data-terminal-property],[data-terminal-position],[data-add-terminal],[data-edit-terminal]'))input.disabled=this.pending||!this.editable()||this.busy();}
 defaultPosition(page){
  const extent=this.S.schematicData?.sheets.find(value=>value.name===page)?.extent;
  return extent?[Math.floor((extent[0]-100)/10)*10,Math.round(extent[1]/10)*10]:[180,160];
 }
 add(position){
  const S=this.S;if(S.active!=='schematic')this.schematic();
  position||=this.defaultPosition(S.schematicSheet||'');
  this.closeDrawer();return this.perform({action:'add',sheet:S.schematicSheet||'',position},'Added terminal',{open:true});
 }
 editPort(sheet,label,ref){
  if(ref){this.schematic();this.select(ref);return;}
  return this.perform({action:'materialize',sheet,label,position:this.defaultPosition(sheet)},'Made sheet port editable',{open:true,page:sheet});
 }
 remove(ref){return this.perform({action:'delete',ref},'Deleted terminal');}
 inspector(component,field){
  const S=this.S,cfg=component.terminal,net=S.spec.nets.find(net=>net.pins.includes(component.ref+'.1')),isolated=net?.placeholder_ref===component.ref;
  const input=(title,key,value,type='text')=>`<label class="property-row"><span>${title}</span><input data-terminal-property="${key}" value="${esc(value??'')}" type="${type}" ${type==='number'?'step="any"':''}></label>`;
  const select=(title,key,values,value)=>`<label class="property-row"><span>${title}</span><select data-terminal-property="${key}">${values.map(([id,label])=>`<option value="${id}" ${String(value)===id?'selected':''}>${label}</option>`).join('')}</select></label>`;
  const position=S.spec.editor?.positions?.[component.ref]||S.schematicData?.symbols.find(symbol=>symbol.ref===component.ref)?.position||[180,160];
  return `<div class="inspector-name"><span class="part-badge">${icon('link')}</span><div class="name-stack"><strong>${esc(component.value)}</strong><small>Terminal · ${esc(component.ref)}</small></div></div><section class="inspector-section"><h3>Terminal</h3>${input('Designator','name',component.value)}${input('Pin number','number',cfg.number||'1')}${select('Direction','direction',[['passive','Passive'],['input','Input'],['output','Output'],['bidirectional','Bidirectional'],['tri_state','Tri-state']],cfg.direction||'passive')}<label class="property-row"><span>Net</span><select data-terminal-property="net"><option value="" ${isolated?'selected':''}>Unconnected</option>${S.spec.nets.filter(net=>!net.placeholder_ref).map(value=>`<option value="${esc(value.name)}" ${value.name===net?.name?'selected':''}>${esc(value.name)}</option>`).join('')}</select></label>${select('Module pin','expose',[['true','Exposed'],['false','Internal testpoint']],cfg.expose!==false)}</section><section class="inspector-section"><h3>Symbol layout</h3>${select('Pin orientation','side',[['left','Left'],['right','Right'],['top','Top'],['bottom','Bottom']],cfg.side||'left')}${input('Terminal order','order',cfg.order||0,'number')}${input('Pin group','group',cfg.group||'')}${input('Section','section',cfg.section||'')}<div class="property-row"><span>Sheet</span><span>${esc(component.sheet||'Main')}</span></div>${position.map((value,i)=>`<label class="property-row"><span>Schematic ${i?'Y':'X'}</span><input type="number" step="10" data-terminal-position="${i}" value="${value}"></label>`).join('')}</section><section class="inspector-section"><h3>PCB test pad</h3>${select('PCB','exclude_from_pcb',[['false','Include test pad'],['true','Exclude from PCB']],cfg.exclude_from_pcb===true)}${input('Diameter (mm)','diameter_mm',cfg.diameter_mm||1.5,'number')}${field('X (mm)','placement.x_mm',component.placement?.x_mm??0,'number')}${field('Y (mm)','placement.y_mm',component.placement?.y_mm??0,'number')}<p>A terminal creates a bare copper test pad. Exclude it when the connection already exists on a pad or via. It is not an assembled BOM item.</p></section>`;
 }
 bind(host,component){
  host.querySelectorAll('[data-terminal-property]').forEach(input=>input.onchange=this.run(()=>{
   const key=input.dataset.terminalProperty,value=['exclude_from_pcb','expose'].includes(key)?input.value==='true':['diameter_mm','order'].includes(key)?Number(input.value):key==='net'?(input.value||null):input.value;
   return this.perform({action:'update',ref:component.ref,patch:{[key]:value}},'Updated terminal '+key);
  }));
  host.querySelectorAll('[data-terminal-position]').forEach(input=>input.onchange=this.run(()=>{
   const position=[...host.querySelectorAll('[data-terminal-position]')].map(value=>Number(value.value));return this.perform({action:'update',ref:component.ref,patch:{position}},'Moved terminal');
  }));
  this.markBusy();
 }
 bindCatalog(button){
  button.onclick=this.run(()=>this.add());button.draggable=true;
  button.ondragstart=event=>{if(!this.editable()||this.pending){event.preventDefault();return;}event.dataTransfer.setData('application/x-wholeboard-terminal','terminal');event.dataTransfer.effectAllowed='copy';};
  this.markBusy();
 }
 bindDrop(host){
  host.addEventListener('dragover',event=>{if(this.S.active==='schematic'&&[...event.dataTransfer.types].includes('application/x-wholeboard-terminal'))event.preventDefault();});
  host.addEventListener('drop',event=>{
   if(this.S.active!=='schematic'||!event.dataTransfer.getData('application/x-wholeboard-terminal'))return;
   event.preventDefault();const point=this.S.canvas?.worldPoint?.(event);this.run(()=>this.add(point?[Math.round(point.x/10)*10,Math.round(point.y/10)*10]:undefined))();
  });
 }
}
