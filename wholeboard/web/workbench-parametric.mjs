import {icon,esc} from './workbench-icons.mjs';
import {nativeSymbol} from './workbench-symbol.mjs';
import {symbolPreview,pinDrop,sharedPinValues,selectSymbolPins} from './workbench-parametric-model.mjs';

const sides=['left','right','top','bottom'];
export class ParametricUI{
 constructor(options){Object.assign(this,options);this.selected=new Set();this.token=0;this.request=0;this.dirty=new Set();document.addEventListener('keyup',event=>{if(event.code==='Space')this.space=false;});window.addEventListener('blur',()=>this.space=false);}
 get S(){return this.state();}
 get writable(){return this.editable()&&!this.busy()&&!this.pending;}
 async render(host){
  const token=++this.token;this.host=host;this.pending=null;
  if(this.pid!==this.S.pid){this.pid=this.S.pid;this.ref=this.S.selected;this.selected.clear();this.anchor=null;}
  const components=this.S.spec.components.filter(c=>!c.terminal);
  if(!components.some(c=>c.ref===this.ref))this.ref=components[0]?.ref;
  if(!this.ref){host.innerHTML='<div class="empty-canvas"><h2>No part selected</h2><p>Add a component to edit its symbol.</p></div>';return;}
  host.innerHTML='<div class="empty-canvas" role="status"><p>Reading source pins and native symbol geometry…</p></div>';
  try{
   await this.save();const pid=this.S.pid,version=this.S.version,spec=this.S.spec,ref=this.ref;
   const info=await this.api(`/api/workbench/projects/${pid}/symbols/${encodeURIComponent(ref)}`);
   if(token!==this.token||this.S.pid!==pid||this.S.active!=='symbol'||this.ref!==ref||this.S.spec!==spec||this.S.version!==version)return;
   this.pid=pid;this.info=info;this.dirty.clear();this.selected=new Set([...this.selected].filter(n=>info.layout.pins.some(p=>p.number===n)));
   host.innerHTML=`<div class="symbol-editor" id="symbolEditor"><header class="symbol-editor-header"><span>${icon('chip')}Symbol</span><label>Part<select id="symbolComponent" aria-label="Symbol component">${components.map(c=>`<option value="${esc(c.ref)}" ${c.ref===ref?'selected':''}>${esc(c.ref+' · '+c.value)}</option>`).join('')}</select></label><label>Style<select id="symbolStyle" data-symbol-edit><option value="native" ${info.layout.style==='native'?'selected':''}>Native</option><option value="parametric" ${info.layout.style==='parametric'?'selected':''}>Parametric</option></select></label><button class="secondary-button" id="fitSymbol">Fit</button><span id="symbolEditorStatus" role="status"></span>${info.layout.issues?.length?'<button class="symbol-review-badge" id="reviewIncompleteSymbol">'+info.layout.issues.length+' pins need layout properties</button>':''}</header><div class="symbol-workspace"><div class="symbol-canvas" id="symbolCanvas"></div><aside class="symbol-pin-inspector" id="symbolPinInspector"></aside></div><section class="symbol-pin-table"><div class="symbol-table-heading"><strong>Pins</strong><span>${info.layout.pins.length} physical pins</span><input type="search" id="symbolPinSearch" aria-label="Search symbol pins" placeholder="Search pins"><button class="secondary-button" id="selectAllSymbolPins">Select all</button></div><div class="symbol-table-scroll"><table class="design-table"><thead><tr><th></th><th>Number</th><th>Name</th><th>Electrical type</th><th>Orientation</th><th>Pin Group</th><th>Section</th><th>Order</th><th>Sub-symbol</th></tr></thead><tbody id="symbolPinTable"></tbody></table></div></section></div>`;
   host.querySelector('#symbolComponent').onchange=event=>{this.ref=event.target.value;this.selected.clear();this.render(host);};
   host.querySelector('#symbolStyle').onchange=event=>this.run({action:'style',style:event.target.value});
   host.querySelector('#fitSymbol').onclick=()=>this.fit();host.querySelector('#symbolPinSearch').oninput=()=>this.table();
   host.querySelector('#selectAllSymbolPins').onclick=()=>{this.selected=new Set(this.visiblePins().map(p=>p.number));this.paintSelection();};
   host.querySelector('#reviewIncompleteSymbol')?.addEventListener('click',()=>{this.selected=new Set(info.layout.issues.map(p=>p.number));this.paintSelection();});
   this.table();this.draw();this.paintSelection();this.markBusy();
  }catch(error){if(token===this.token){host.innerHTML=`<div class="empty-canvas"><h2>Cannot open this symbol</h2><p role="alert">${esc(error.message)}</p></div>`;}}
 }
 visiblePins(){const query=this.host.querySelector('#symbolPinSearch')?.value.toLowerCase()||'';return this.info.layout.pins.filter(p=>[p.number,p.name,p.group,p.section,p.subsymbol].join(' ').toLowerCase().includes(query));}
 table(){
  const rows=this.visiblePins();this.host.querySelector('#symbolPinTable').innerHTML=rows.map(p=>`<tr data-symbol-pin="${esc(p.number)}" class="${this.selected.has(p.number)?'selected':''}"><td><input type="checkbox" data-symbol-select="${esc(p.number)}" aria-label="Select pin ${esc(p.number)}" ${this.selected.has(p.number)?'checked':''}></td><td>${esc(p.number)}</td><td>${esc(p.name||p.number)}</td><td>${esc(p.type)}</td><td>${esc(p.side)}</td><td>${esc(p.group)}</td><td>${esc(p.section)}</td><td>${p.order}</td><td>${esc(p.subsymbol||'Primary')}</td></tr>`).join('');
  this.host.querySelector('#symbolPinTable').onclick=event=>{const row=event.target.closest('[data-symbol-pin]');if(!row)return;this.choose(row.dataset.symbolPin,event,event.target.matches('input'));};
 }
 choose(number,event={},checkbox=false){
  const result=selectSymbolPins(this.selected,number,this.visiblePins().map(p=>p.number),{additive:checkbox||event.metaKey||event.ctrlKey,range:event.shiftKey,anchor:this.anchor});this.selected=result.selected;this.anchor=result.anchor;this.paintSelection();
 }
 paintSelection(){
  if(!this.host.querySelector('#symbolEditor'))return;
  for(const row of this.host.querySelectorAll('#symbolPinTable tr')){const on=this.selected.has(row.dataset.symbolPin);row.classList.toggle('selected',on);row.querySelector('input').checked=on;}
  this.host.querySelectorAll('[data-pinref]').forEach(circle=>circle.classList.toggle('symbol-pin-selected',this.selected.has(circle.dataset.pinref.slice(this.ref.length+1))));
  this.inspector();
 }
 inspector(){
  const host=this.host.querySelector('#symbolPinInspector'),pins=this.info.layout.pins.filter(p=>this.selected.has(p.number)),shared=sharedPinValues(pins);this.dirty.clear();
  if(!pins.length){host.innerHTML=`<h3>Symbol</h3><p>Select a pin or draw a selection box.</p><p>Drag pins to a side, section or group. Drop outside the symbols to create a sub-symbol.</p><div class="symbol-section-list"><h4>Sections</h4>${this.info.layout.sections.map((s,i)=>`<div><span>${esc(s||'Unassigned')}</span><button data-section-up="${i}" aria-label="Move ${esc(s||'Unassigned')} section up" ${i?'':'disabled'}>↑</button><button data-section-down="${i}" aria-label="Move ${esc(s||'Unassigned')} section down" ${i<this.info.layout.sections.length-1?'':'disabled'}>↓</button></div>`).join('')}</div>`;
   host.querySelectorAll('[data-section-up],[data-section-down]').forEach(button=>button.onclick=()=>{const up=button.dataset.sectionUp!==undefined,index=+(up?button.dataset.sectionUp:button.dataset.sectionDown),sections=[...this.info.layout.sections],other=index+(up?-1:1);[sections[index],sections[other]]=[sections[other],sections[index]];this.run({action:'sections',sections});});return;
  }
  const input=(key,label,type='text')=>`<label>${label}<input id="${{group:'symbolGroup',section:'symbolSection',order:'symbolOrder',subsymbol:'symbolSubsymbol',name:'symbolPinName'}[key]}" data-symbol-property="${key}" data-symbol-edit type="${type}" ${type==='number'?'step="any"':''} value="${esc(shared[key]??'')}" placeholder="${shared[key]===null?'Mixed — unchanged':'Unassigned'}" ${key==='subsymbol'?'list="symbolSuffixes"':''}></label>`;
  host.innerHTML=`<h3>${pins.length===1?'Pin '+esc(pins[0].number):pins.length+' pins selected'}</h3><p class="file-help">${esc(pins.map(p=>p.number).join(', '))}</p><form id="symbolPinForm"><label>Pin Orientation<select id="symbolSide" data-symbol-property="side" data-symbol-edit>${shared.side===null?'<option value="">Mixed — unchanged</option>':''}${sides.map(side=>`<option value="${side}" ${shared.side===side?'selected':''}>${side[0].toUpperCase()+side.slice(1)}</option>`).join('')}</select></label>${input('group','Pin Group')}${input('section','Section')}${input('order','Terminal Order','number')}${input('subsymbol','Sub-symbol suffix')}${input('name','Display name')}<datalist id="symbolSuffixes">${this.info.layout.units.map(s=>`<option value="${esc(s)}"></option>`).join('')}</datalist><button class="primary-button" type="submit" id="applySymbolPins" disabled>Apply pin properties</button><p class="file-help">Physical numbers and electrical types stay unchanged. Native KiCad pin groups are checked before saving.</p></form>`;
  host.querySelector('form').oninput=event=>{if(event.target.dataset.symbolProperty)this.dirty.add(event.target.dataset.symbolProperty);this.markBusy();};
  host.querySelector('form').onsubmit=event=>{event.preventDefault();const patch={};for(const key of this.dirty){const input=host.querySelector(`[data-symbol-property="${key}"]`);patch[key]=key==='order'?(input.value===''?null:Number(input.value)):input.value;}this.run({action:'pins',pins:[...this.selected],patch});};this.markBusy();
 }
 svg(scene,id='symbolSvg'){
  const preview=symbolPreview(scene,this.ref);this.preview=preview;
  let body='';
  for(const instance of preview.symbols){const definition=preview.definitions[instance.definition];body+=nativeSymbol(instance,definition,this.S.spec,{},preview.mm_per_unit,preview.origin_mm,null);
   for(const label of definition.parametric?.labels||[]){const x=instance.position[0]+label.position[0]/preview.mm_per_unit,y=instance.position[1]-label.position[1]/preview.mm_per_unit,width=Math.max(35,label.text.length*7);body+=`<rect data-symbol-label="${esc(label.text)}" data-label-kind="${label.kind}" data-label-section="${esc(label.section||'')}" data-label-group="${esc(label.group||'')}" data-label-side="${esc(label.side||'')}" data-label-unit="${instance.unit}" x="${x-width/2}" y="${y-8}" width="${width}" height="17" fill="transparent" class="symbol-label-target"/>`;}
   const titleX=instance.position[0],suffix=definition.parametric?.suffix??this.info.layout.units[instance.unit-1]??'';body+=`<rect data-symbol-unit-title="${instance.unit}" data-unit-suffix="${esc(suffix)}" x="${titleX-45}" y="42" width="90" height="24" fill="transparent" class="symbol-label-target"/>`;
   if(definition.parametric&&!definition.pins.length)body+=`<g role="button" tabindex="0" data-remove-symbol-unit="${esc(suffix)}"><rect x="${titleX-40}" y="${preview.bbox[3]-30}" width="80" height="22" fill="#333"/><text x="${titleX}" y="${preview.bbox[3]-15}" text-anchor="middle" font-size="10" fill="#aaa">Remove empty</text></g>`;
  }
  return `<svg id="${id}" tabindex="0" role="${id==='symbolSvg'?'application':'img'}" aria-label="Component symbol editor" viewBox="${preview.bbox[0]} ${preview.bbox[1]} ${preview.bbox[2]} ${preview.bbox[3]}">${body}<rect id="symbolSelectionBox" hidden fill="#1dfdc012" stroke="#1dfdc0" stroke-width="1"/></svg>`;
 }
 draw(){
  const host=this.host.querySelector('#symbolCanvas');if(!host)return;host.innerHTML=this.svg(this.info.scene);this.bindCanvas();this.paintSelection();
 }
 point(event){const svg=this.host.querySelector('#symbolSvg'),point=svg.createSVGPoint();point.x=event.clientX;point.y=event.clientY;return point.matrixTransform(svg.getScreenCTM().inverse());}
 fit(){const svg=this.host.querySelector('#symbolSvg');if(svg&&this.preview)svg.setAttribute('viewBox',this.preview.bbox.join(' '));}
 bindCanvas(){
  const svg=this.host.querySelector('#symbolSvg');let drag=null;
  svg.addEventListener('wheel',event=>{event.preventDefault();const point=this.point(event),box=svg.viewBox.baseVal,factor=event.deltaY>0?1.15:1/1.15,width=Math.max(20,Math.min(this.preview.bbox[2]*20,box.width*factor)),ratio=width/box.width,height=box.height*ratio;svg.setAttribute('viewBox',[point.x-(point.x-box.x)*ratio,point.y-(point.y-box.y)*ratio,width,height].join(' '));},{passive:false});
  svg.onpointerdown=event=>{if(event.button===1||event.button===0&&this.space){const box=svg.viewBox.baseVal,matrix=svg.getScreenCTM();drag={kind:'pan',client:[event.clientX,event.clientY],box:[box.x,box.y,box.width,box.height],matrix};event.preventDefault();svg.setPointerCapture(event.pointerId);return;}if(event.button!==0)return;const pin=event.target.closest('[data-pinref],[data-symbol-pin-name]'),label=event.target.closest('[data-symbol-label]'),point=this.point(event);
   if(pin){const number=pin.dataset.pinref?.slice(this.ref.length+1)??pin.dataset.symbolPinName;if(!this.selected.has(number)||event.metaKey||event.ctrlKey||event.shiftKey)this.choose(number,event);drag={kind:'pin',start:point,client:[event.clientX,event.clientY],pins:[...this.selected]};}
   else if(label){const info=label.dataset,suffix=this.info.layout.units[+info.labelUnit-1],pins=this.info.layout.pins.filter(p=>p.subsymbol===suffix&&p.section===info.labelSection&&(info.labelKind==='section'||p.group===info.labelGroup&&p.side===info.labelSide));this.selected=new Set(pins.map(p=>p.number));this.paintSelection();drag={kind:info.labelKind,start:point,client:[event.clientX,event.clientY],pins:[...this.selected],section:info.labelSection};}
   else if(!event.target.closest('[data-symbol-unit-title],[data-remove-symbol-unit]')){drag={kind:'box',start:point,client:[event.clientX,event.clientY]};if(!event.metaKey&&!event.ctrlKey)this.selected.clear();}
   if(drag){event.preventDefault();svg.setPointerCapture(event.pointerId);}
  };
  svg.onpointermove=event=>{if(!drag)return;if(drag.kind==='pan'){const[x,y,w,h]=drag.box;svg.setAttribute('viewBox',[x-(event.clientX-drag.client[0])/drag.matrix.a,y-(event.clientY-drag.client[1])/drag.matrix.d,w,h].join(' '));return;}const point=this.point(event);if(drag.kind==='box'){const box=svg.querySelector('#symbolSelectionBox');box.removeAttribute('hidden');box.setAttribute('x',Math.min(point.x,drag.start.x));box.setAttribute('y',Math.min(point.y,drag.start.y));box.setAttribute('width',Math.abs(point.x-drag.start.x));box.setAttribute('height',Math.abs(point.y-drag.start.y));}};
  svg.onpointerup=event=>{if(!drag)return;const item=drag;drag=null;if(item.kind==='pan')return;const point=this.point(event);svg.querySelector('#symbolSelectionBox').setAttribute('hidden','');if(Math.hypot(event.clientX-item.client[0],event.clientY-item.client[1])<6){this.paintSelection();return;}
   if(item.kind==='box'){for(const circle of svg.querySelectorAll('[data-pinref]')){const p=svg.getScreenCTM().inverse().multiply(circle.getScreenCTM()),local=svg.createSVGPoint();local.x=+circle.getAttribute('cx');local.y=+circle.getAttribute('cy');const a=local.matrixTransform(p);if(a.x>=Math.min(item.start.x,point.x)&&a.x<=Math.max(item.start.x,point.x)&&a.y>=Math.min(item.start.y,point.y)&&a.y<=Math.max(item.start.y,point.y))this.selected.add(circle.dataset.pinref.slice(this.ref.length+1));}this.paintSelection();return;}
   const target=pinDrop(this.preview,[point.x,point.y]);if(!target)return this.newSubsymbol(item.pins);
   if(item.kind==='section'){const sections=[...this.info.layout.sections],from=sections.indexOf(item.section),to=sections.indexOf(target.section);if(from>=0&&to>=0&&from!==to){sections.splice(from,1);sections.splice(to,0,item.section);this.run({action:'sections',sections});}return;}
   const under=document.elementFromPoint(event.clientX,event.clientY)?.closest('[data-symbol-label]'),patch={action:'move',pins:item.pins,side:target.side,section:target.section,subsymbol:target.subsymbol};if(under?.dataset.labelKind==='group'){patch.group=under.dataset.labelGroup;patch.side=under.dataset.labelSide;patch.section=under.dataset.labelSection;}
   let closest=null;for(const instance of this.preview.symbols){if(instance.unit!==target.unit)continue;const definition=this.preview.definitions[instance.definition];for(const pin of definition.pins){if(item.pins.includes(pin.number))continue;const x=instance.position[0]+pin.x/this.preview.mm_per_unit,y=instance.position[1]-pin.y/this.preview.mm_per_unit,d=Math.hypot(point.x-x,point.y-y);if(!closest||d<closest.d)closest={d,number:pin.number};}}
   if(closest&&closest.d<35)patch.before=closest.number;this.run(patch);
  };
  svg.onpointercancel=()=>{drag=null;svg.querySelector('#symbolSelectionBox').setAttribute('hidden','');};
  svg.ondblclick=event=>{const target=document.elementFromPoint(event.clientX,event.clientY)||event.target,label=target.closest('[data-symbol-label]'),title=target.closest('[data-symbol-unit-title]'),pin=target.closest('[data-pinref],[data-symbol-pin-name]');if(label)this.rename(label.dataset.labelKind,label.dataset.symbolLabel);else if(title)this.rename('subsymbol',title.dataset.unitSuffix);else if(pin){const number=pin.dataset.pinref?.slice(this.ref.length+1)??pin.dataset.symbolPinName;this.renamePin(number);}};
  svg.querySelectorAll('[data-remove-symbol-unit]').forEach(button=>button.onclick=()=>this.run({action:'remove_unit',suffix:button.dataset.removeSymbolUnit}));
 }
 async newSubsymbol(pins){if(!this.writable)return;const pid=this.S.pid,ref=this.ref,spec=this.S.spec,value=await this.askText('New sub-symbol','Suffix','B');if(value===null||pid!==this.S.pid||ref!==this.ref||spec!==this.S.spec)return;this.run({action:'pins',pins,patch:{subsymbol:value}});}
 async rename(field,from){if(!this.writable)return;const pid=this.S.pid,ref=this.ref,spec=this.S.spec,to=await this.askText('Rename '+field,'Name',from);if(to===null||pid!==this.S.pid||ref!==this.ref||spec!==this.S.spec)return;this.run({action:'rename',field,from,to,pins:[...this.selected]});}
 async renamePin(number){if(!this.writable)return;const pid=this.S.pid,ref=this.ref,spec=this.S.spec,pin=this.info.layout.pins.find(p=>p.number===number),value=await this.askText('Pin display name','Name',pin?.name||number);if(value!==null&&this.S.pid===pid&&this.ref===ref&&this.S.spec===spec)this.run({action:'pins',pins:[number],patch:{name:value}});}
 async run(arguments_){
  if(!this.writable)return this.toast(this.editable()?'Wait for the current project before editing its symbol.':'This project is read-only.',true);const request=++this.request,pid=this.S.pid,ref=this.ref;this.pending=request;this.markBusy();
  try{await this.save();if(this.S.pid!==pid||this.S.active!=='symbol'||this.ref!==ref)return;const version=this.S.version,spec=this.S.spec;const result=await this.api(`/api/workbench/projects/${pid}/symbols/prepare`,{method:'POST',body:{...arguments_,ref,base_version:version}});
   if(this.S.pid!==pid||this.S.active!=='symbol'||this.ref!==ref||this.S.spec!==spec||this.S.version!==version||this.pending!==request)return;
   this.pending=null;
   const apply=()=>{if(!this.editable()||this.busy()||this.S.pid!==pid||this.S.spec!==spec||this.S.version!==version||this.ref!==ref)throw Error('The design changed. Review symbol properties again.');this.commit(result.spec,'Edited symbol layout',null);return this.save();};
   if(result.summary.requires_route_review){const previousPreview=this.preview,preview=this.svg(result.scene,'symbolReviewSvg');this.preview=previousPreview;const d=document.createElement('dialog');d.className='modal symbol-route-dialog';d.innerHTML=`<div class="modal-heading"><h2>Review schematic routes</h2></div><p class="modal-description">${esc(result.summary.released_exact_routes.join(', '))}: these exact drawing paths will be rebuilt for the new pin positions. Native pin connections match; PCB data stays unchanged.</p><div class="symbol-review-preview symbol-canvas">${preview}</div><div class="modal-footer"><button class="secondary-button" data-cancel>Cancel</button><button class="primary-button" data-apply>Apply symbol layout</button></div>`;document.body.append(d);d.querySelector('[data-cancel]').onclick=()=>d.close();d.querySelector('[data-apply]').onclick=()=>Promise.resolve().then(apply).then(()=>d.close()).catch(e=>this.toast(e.message,true));d.onclose=()=>{d.remove();if(this.S.pid===pid&&this.ref===ref&&this.S.spec===spec&&this.S.version===version){const style=this.host.querySelector('#symbolStyle');if(style)style.value=this.info.layout.style;this.draw();}};d.showModal();}
   else await apply();
  }catch(error){this.toast(error.message,true);}finally{if(this.pending===request)this.pending=null;this.markBusy();}
 }
 markBusy(){if(this.S.active!=='symbol'||!this.host?.querySelector('#symbolEditor'))return;const locked=!this.writable;this.host.querySelectorAll('[data-symbol-edit]').forEach(input=>input.disabled=locked);const apply=this.host.querySelector('#applySymbolPins');if(apply)apply.disabled=locked||!this.dirty.size||!this.selected.size;const status=this.host.querySelector('#symbolEditorStatus');if(status)status.textContent=this.pending?'Checking native pin connections…':this.busy()?'Project is busy':'Native source pins';}
 key(event){if(event.target.closest('input,textarea,select,[contenteditable=true]'))return false;const command=event.ctrlKey||event.metaKey,key=event.key.toLowerCase();if(command&&key==='z')return false;if(event.code==='Space'){event.preventDefault();this.space=true;return true;}if(['delete','backspace','r','f','[',']'].includes(key)||command&&['c','v','x','d'].includes(key)){event.preventDefault();return true;}if(key==='0'){event.preventDefault();this.fit();return true;}return false;}
}
