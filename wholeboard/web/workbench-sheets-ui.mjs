import {icon,esc} from './workbench-icons.mjs';
import {sheetDefinitions,componentSheet,createSheet,updateSheet,assignSheet,removeSheet} from './workbench-sheets.mjs';

export class SheetsUI {
 constructor(options){Object.assign(this,options);}
 get S(){return this.state();}
 run(fn){return(...args)=>{try{fn(...args);}catch(error){this.toast(error.message,true);}};}
 picker(host){
  const S=this.S,defs=sheetDefinitions(S.spec),bar=document.createElement('div');bar.className='schematic-sheet-picker';
  bar.innerHTML=`${icon('folder')}<select id="schematicSheet" aria-label="Schematic sheet"><option value="">Main</option>${Object.entries(defs).map(([id,d])=>`<option value="${esc(id)}" ${id===S.schematicSheet?'selected':''}>${esc(d.parent?'↳ ':'')}${esc(d.title||id)}</option>`).join('')}</select><button class="icon-button" aria-label="Create sheet" title="Create sheet">${icon('plus')}</button>${S.schematicSheet?`<button class="icon-button" data-sheet-inspect aria-label="Inspect current sheet" title="Sheet properties">${icon('settings')}</button>`:''}`;
  host.append(bar);bar.querySelector('select').onchange=e=>this.open(e.target.value);
  bar.querySelector('[aria-label="Create sheet"]').disabled=!this.editable();bar.querySelector('[aria-label="Create sheet"]').onclick=()=>this.create();
  bar.querySelector('[data-sheet-inspect]')?.addEventListener('click',()=>this.select(S.schematicSheet));
 }
 create(){
  if(!this.editable()||this.busy())return;
  const S=this.S,refs=[...new Set([...S.selection].map(key=>key.split('#')[0]))],defs=sheetDefinitions(S.spec);let index=1;while(defs['Sheet'+index])index++;
  const d=this.modal('Create sheet',`<label>Title<input id="sheetTitle" value="New sheet" maxlength="120" required></label><label>Sheet ID<input id="sheetId" value="Sheet${index}" pattern="[A-Za-z][A-Za-z0-9_-]{0,63}" maxlength="64" required></label><p>Inside ${esc(defs[S.schematicSheet]?.title||'Main')}. PCB placements and electrical connections stay linked.</p>${refs.length?`<label class="sheet-check"><input id="sheetMoveSelection" type="checkbox" checked>Move ${refs.length} selected component${refs.length>1?'s':''} into this sheet</label>`:''}`,'Create sheet and open');
  d.querySelector('form').onsubmit=this.run(e=>{e.preventDefault();const id=d.querySelector('#sheetId').value, title=d.querySelector('#sheetTitle').value.trim();const next=createSheet(S.spec,id,{title,parent:S.schematicSheet||'',refs:d.querySelector('#sheetMoveSelection')?.checked?refs:[]});this.clear();this.commit(next,'Created schematic sheet '+title,null);d.close();this.open(id);});
 }
 select(id){
  const S=this.S;if(!sheetDefinitions(S.spec)[id])return;this.clear();S.selectedSheet=id;S.inspector=true;S.canvas?.selectSheet?.(id);this.inspect();this.context();
 }
 clear(){const S=this.S;S.selectedSheet=null;S.selectedWireNode=null;S.selected=null;S.selectedSymbolKey=null;S.selectedNet=null;S.selectedWireIndex=null;S.selection.clear();S.canvas?.selectMany?.([]);S.canvas?.selectWire?.(null);S.canvas?.selectSheet?.(null);}
 change(id,patch){this.commit(updateSheet(this.S.spec,id,patch),'Updated schematic sheet',null);}
 inspector(){
  const S=this.S,id=S.selectedSheet,d=sheetDefinitions(S.spec)[id];if(!d)return'';
  const node=S.schematicData?.sheet_nodes.find(sheet=>sheet.target===id),pos=d.position||node?.position||[850,140],size=d.size||node?.size||[300,180];
  const field=(title,key,value)=>`<label class="property-row"><span>${title}</span><input data-sheet-property="${key}" value="${esc(value)}" type="${key==='title'?'text':'number'}" ${key==='title'?'maxlength="120"':'step="10"'}></label>`;
  return `<div class="inspector-name"><span class="part-badge">${icon('folder')}</span><div class="name-stack"><strong>${esc(d.title||id)}</strong><small>Schematic sheet · ${esc(id)}</small></div></div><section class="inspector-section"><h3>Properties</h3>${field('Title','title',d.title||id)}<label class="property-row"><span>Parent</span><select data-sheet-property="parent"><option value="">Main</option>${Object.entries(sheetDefinitions(S.spec)).filter(([key])=>key!==id).map(([key,value])=>`<option value="${esc(key)}" ${key===d.parent?'selected':''}>${esc(value.title||key)}</option>`).join('')}</select></label></section><section class="inspector-section"><h3>Boundary</h3>${field('X','position.0',pos[0])}${field('Y','position.1',pos[1])}${field('Width','size.0',size[0])}${field('Height','size.1',size[1])}<p>Drag the boundary or its lower right handle. Dimensions use schematic units.</p></section><section class="inspector-section"><h3>Ports</h3>${(node?.ports||[]).map(port=>`<div class="sheet-port-row"><div class="pin-row"><span>${esc(port.label||port.net)}</span><span>${esc(port.net)}</span></div><button class="asset-text-button" data-edit-terminal="${esc(id)}" data-terminal-label="${esc(port.label||port.net)}" data-terminal-ref="${esc(port.terminal_ref||'')}" aria-label="Edit terminal ${esc(port.label||port.net)}">${port.terminal_ref?'Edit terminal':'Make editable'}</button></div>`).join('')||'<p>No boundary connections. Nets crossing the sheet create ports automatically.</p>'}<button class="secondary-button" data-add-sheet-terminal="${esc(id)}" data-add-terminal>Add terminal to sheet</button></section><section class="inspector-section sheet-actions"><button class="secondary-button" id="openSelectedSheet">Open sheet</button><button class="secondary-button danger-text" id="removeSelectedSheet">Remove sheet</button></section>`;
 }
 selection(){
  const S=this.S;if(S.active!=='schematic'||!S.selection.size)return'';
  const ref=[...S.selection][0].split('#')[0],current=componentSheet(S.spec.components.find(c=>c.ref===ref));
  return `<section class="inspector-section"><h3>Schematic sheet</h3><label class="property-row"><span>Destination</span><select id="componentSheet"><option value="">Main</option>${Object.entries(sheetDefinitions(S.spec)).map(([id,d])=>`<option value="${esc(id)}" ${current===id?'selected':''}>${esc(d.title||id)}</option>`).join('')}</select></label><div class="sheet-actions"><button class="secondary-button" id="moveToSheet">Move to sheet</button><button class="secondary-button" id="createSelectionSheet">New sheet from selection</button></div></section>`;
 }
 bind(host){
  const S=this.S;host.querySelectorAll('[data-sheet-property]').forEach(input=>input.onchange=this.run(()=>{
   const key=input.dataset.sheetProperty,id=S.selectedSheet,d=sheetDefinitions(S.spec)[id],node=S.schematicData?.sheet_nodes.find(sheet=>sheet.target===id);let patch;
   if(key.includes('.')){const[field,axis]=key.split('.'),value=[...(d[field]||node?.[field]||[])];value[Number(axis)]=Number(input.value);patch={[field]:value};}else patch={[key]:input.value};
   this.change(id,patch);
  }));
  host.querySelector('#openSelectedSheet')?.addEventListener('click',()=>this.open(S.selectedSheet));
  host.querySelector('#removeSelectedSheet')?.addEventListener('click',()=>this.remove(S.selectedSheet));
  host.querySelector('#createSelectionSheet')?.addEventListener('click',()=>this.create());
  host.querySelector('#moveToSheet')?.addEventListener('click',this.run(()=>{const refs=[...new Set([...S.selection].map(key=>key.split('#')[0]))],id=host.querySelector('#componentSheet').value;this.clear();this.commit(assignSheet(S.spec,refs,id),'Moved components to sheet',null);this.open(id);}));
  if(!this.editable())host.querySelectorAll('[data-sheet-property],#removeSelectedSheet,#createSelectionSheet,#moveToSheet').forEach(input=>input.disabled=true);
 }
 remove(id){
  if(!this.editable()||this.busy())return;const S=this.S,d=sheetDefinitions(S.spec)[id];if(!d)return;
  const modal=this.modal('Remove '+(d.title||id),'Remove this sheet and its child sheets? Their components move to the parent sheet and retain their electrical connections.','Remove sheet and move contents');
  modal.querySelector('form').onsubmit=this.run(e=>{e.preventDefault();const next=removeSheet(S.spec,id);this.clear();this.commit(next,'Removed schematic sheet',null);modal.close();this.open(d.parent||'');});
 }
 modal(title,body,action){
  document.querySelector('#sheetDialog')?.remove();const d=document.createElement('dialog');d.id='sheetDialog';d.className='sheet-dialog';
  d.innerHTML=`<form><h2>${esc(title)}</h2><div class="sheet-dialog-content">${body.startsWith('<')?body:`<p>${esc(body)}</p>`}</div><div class="dialog-actions"><button class="secondary-button" type="button" data-cancel>Cancel</button><button class="primary-button" type="submit">${esc(action)}</button></div></form>`;
  document.body.append(d);d.querySelector('[data-cancel]').onclick=()=>d.close();d.showModal();return d;
 }
}
