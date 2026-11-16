import {icon,esc} from './workbench-icons.mjs';
import {buildObjectTree,objectRows,chooseObjects,hiddenObjects,nativeObjectKey,guideIdentity,objectSelection} from './workbench-objects-model.mjs';
import {ObjectGroupsUI} from './workbench-object-groups.mjs';

const symbols={root:'folder',layout:'board',schematic:'schematic',group:'folder',user_group:'folder',component:'chip',footprint:'board',pad:'chip',net:'schematic',track:'link',arc:'link',via:'via',zone:'layers',fill:'layers',drawing:'file',outline:'board',sheet:'folder',symbol:'chip',wire:'link',node:'link',label:'netLabel'};
const supported=new Set(['component','symbol','copper','wire','node','net','sheet','sheet_root','project','board']);
export class ObjectsUI{
 constructor(options){Object.assign(this,options);this.ids=new Set();this.expanded=new Set();this.hidden=new Set();this.query='';this.scope=null;this.lastNodes=new Map();this.groups=new ObjectGroupsUI(this);}
 get S(){return this.state();}
 get chosen(){return [...this.ids].map(id=>this.tree?.nodes.get(id)||this.lastNodes.get(id)).filter(Boolean);}
 selectionNodes(nodes=this.chosen){return this.tree?objectSelection(this.tree,nodes):nodes;}
 get canEdit(){const chosen=this.chosen,nodes=this.selectionNodes();return !nodes.some(n=>n.ambiguous)&&(!chosen.length||nodes.length>0&&(nodes.length===1&&supported.has(nodes[0].target?.kind)||nodes.every(n=>['component','symbol'].includes(n.target?.kind))));}
 contextChanged(data){
  const scope=`${data.pid||'reference'}:${data.view}`;if(scope===this.scope)return;
  this.groups.close();this.scope=scope;this.ids=new Set();this.anchor=null;this.query='';this.hidden=new Set();this.expanded=new Set(['root','layout','schematic','components','nets','sheet:','components:','zones']);this.lastNodes=new Map();this.allExpanded=false;this.rowSignature=null;this.treeStamp=null;
  try{const prefs=JSON.parse(localStorage.getItem('wb-object-tree:'+scope)||'null');if(prefs){if(Array.isArray(prefs.hidden))this.hidden=new Set(prefs.hidden.slice(0,20000));if(Array.isArray(prefs.expanded))this.expanded=new Set(prefs.expanded.slice(0,20000));}}catch{}
 }
 remember(){try{localStorage.setItem('wb-object-tree:'+this.scope,JSON.stringify({hidden:[...this.hidden],expanded:[...this.expanded]}));}catch{}}
 mount(host){
  this.host=host;host.innerHTML=`<div class="object-tree-search drawer-search">${icon('search')}<input id="objectSearch" type="search" aria-label="Search objects" placeholder="Search objects"><button class="icon-button" id="expandObjects" aria-label="Expand all objects" title="Expand all objects">${icon('chevronDown')}</button><button class="icon-button" id="collapseObjects" aria-label="Collapse all objects" title="Collapse all objects">${icon('chevronRight')}</button></div><div id="objectTreeStatus" class="object-tree-status" role="status"></div><div id="objectList" class="object-tree-list" role="tree" aria-label="Design objects" aria-multiselectable="true"></div>`;
  host.querySelector('#objectSearch').oninput=event=>{this.query=event.target.value;this.renderRows();};
  host.querySelector('#expandObjects').onclick=()=>{this.allExpanded=true;this.expanded=new Set([...this.tree.nodes.values()].filter(n=>n.children.length).map(n=>n.id));this.remember();this.renderRows();};
  host.querySelector('#collapseObjects').onclick=()=>{this.allExpanded=false;this.expanded=new Set(['root']);this.remember();this.renderRows();};
  const list=host.querySelector('#objectList');
  list.onclick=event=>{const row=event.target.closest('[data-tree-id]');if(!row)return;const id=row.dataset.treeId;if(event.target.closest('[data-tree-menu]'))return this.groups.open(id);if(event.target.closest('[data-tree-toggle]'))return this.toggle(id);if(event.target.closest('[data-tree-visibility]'))return this.toggleVisibility(id);const node=this.tree.nodes.get(id);if(!node?.target)return this.toggle(id);this.choose(id,event);};
  list.ondblclick=event=>{const row=event.target.closest('[data-tree-id]'),node=this.tree.nodes.get(row?.dataset.treeId);if(node?.target?.kind==='sheet')this.openSheet(node.target.id);};
  list.onkeydown=event=>{const row=event.target.closest('[data-tree-id]');if(!row)return;const id=row.dataset.treeId,rows=this.rows||[],index=rows.findIndex(n=>n.id===id);let focus;if(event.altKey&&['ArrowUp','ArrowDown'].includes(event.key))return;
   if(event.target.closest('button')&&['Enter',' '].includes(event.key)){event.stopPropagation();return;}
   if(['ArrowDown','ArrowUp','Home','End'].includes(event.key)){event.preventDefault();event.stopPropagation();focus=rows[event.key==='Home'?0:event.key==='End'?rows.length-1:Math.max(0,Math.min(rows.length-1,index+(event.key==='ArrowDown'?1:-1)))]?.id;}
   if(event.key==='ArrowRight'){event.preventDefault();event.stopPropagation();if(!this.expanded.has(id))this.toggle(id);else focus=this.tree.nodes.get(id)?.children[0];}
   if(event.key==='ArrowLeft'){event.preventDefault();event.stopPropagation();if(this.expanded.has(id))this.toggle(id);else focus=this.tree.nodes.get(id)?.parent;}
   if(['Enter',' '].includes(event.key)){event.preventDefault();event.stopPropagation();if(this.tree.nodes.get(id)?.target)this.choose(id,event);else this.toggle(id);}
   if(focus)list.querySelector(`[data-tree-id="${CSS.escape(focus)}"]`)?.focus({preventScroll:true});
  };
  list.onpointerover=event=>{const node=this.tree.nodes.get(event.target.closest('[data-tree-id]')?.dataset.treeId);this.hoverNet(node?.kind==='net'&&!this.isHidden(node.id)?node.net:null);};list.onpointerleave=()=>this.hoverNet(null);
  this.groups.mount(list);this.refresh();
 }
 refresh(){
  const wasPending=this.pending;
  const data=this.context();if(!data?.spec)return;this.contextChanged(data);this.data=data;
  if(data.loading){if(this.host?.isConnected){this.host.querySelector('#objectList').replaceChildren();this.host.querySelector('#objectTreeStatus').textContent='Opening project…';}return;}
  const stamp=[data.spec,data.geometry,data.scene,data.title,data.view];
  if(!this.treeStamp||stamp.some((value,index)=>value!==this.treeStamp[index])){this.tree=buildObjectTree(data.spec,data);this.treeStamp=stamp;}
  this.pending=data.view==='layout'&&!data.geometry;
  if(data.geometry)this.geometry=data.geometry;
  if(!this.pending){this.lastNodes=new Map(this.tree.nodes);this.ids=new Set([...this.ids].filter(id=>this.tree.nodes.has(id)));if(!this.ids.size&&this.S.objectOnlySelection?.scope===this.scope)this.S.objectOnlySelection=null;}
  if(this.allExpanded)this.expanded=new Set([...this.tree.nodes.values()].filter(n=>n.children.length).map(n=>n.id));
  this.masks=hiddenObjects(this.tree,this.hidden);
  if(this.host?.isConnected){this.host.querySelector('#objectSearch').value=this.query;this.host.querySelector('#objectTreeStatus').textContent=this.pending?'Updating layout objects…':this.tree.organizationError||'';this.renderRows();}
  this.paint(this.chosen);
  if(wasPending&&!this.pending&&document.querySelector('#inspector [data-object-group], #inspector [data-object-type=pad]')){const scope=this.scope,spec=data.spec;queueMicrotask(()=>{if(this.scope===scope&&this.data?.spec===spec&&this.S.inspector)this.refreshInspector?.();});}
 }
 sync(){
  if(this.applying)return;this.refresh();if(!this.tree||this.data?.loading)return;
  const S=this.S;let ids;
  if(S.objectOnlySelection?.scope===this.scope)ids=S.objectOnlySelection.ids;
  else if(S.selectedWireNode)ids=['node:'+S.selectedWireNode];
  else if(S.selectedSheet)ids=['sheet:'+S.selectedSheet];
  else if(S.selectedCopper)ids=[({tracks:'track:',arcs:'arc:',vias:'via:'})[S.selectedCopper.kind]+S.selectedCopper.id];
  else if(S.selectedWireIndex!==null&&S.selectedWireIndex!==undefined){const guide=S.spec.editor?.connection_guides?.[S.selectedWireIndex];ids=guide?['wire:'+guideIdentity(guide)]:[];}
  else if(S.selection.size)ids=[...S.selection].map(key=>this.tree.nodes.has('symbol:'+key)?'symbol:'+key:'component:'+key.split('#')[0]);
  else if(S.selectedNet)ids=['net:'+S.selectedNet];else ids=[];
  this.ids=new Set(ids.filter(id=>this.tree.nodes.has(id)||this.pending&&this.lastNodes.has(id)));this.reveal();this.renderRows();this.paint(this.chosen);
 }
 reveal(){for(const id of this.ids){let node=this.tree?.nodes.get(id),seen=new Set();while(node?.parent&&!seen.has(node.parent)){seen.add(node.parent);this.expanded.add(node.parent);node=this.tree.nodes.get(node.parent);}}}
 renderRows(){
  if(!this.host?.isConnected||!this.tree||this.data?.loading)return;const list=this.host.querySelector('#objectList'),scroll=list.scrollTop,focus=document.activeElement?.closest('[data-tree-id]')?.dataset.treeId;
  this.rows=objectRows(this.tree,{expanded:this.expanded,query:this.query});
  list.dataset.projectId=this.data.pid||'';
  const signature=JSON.stringify(this.rows.map(n=>[n.id,n.label,n.detail,n.kind,n.depth,n.children.length,n.expanded]));
  if(signature===this.rowSignature&&list.childElementCount===this.rows.length){
   const elements=new Map([...list.children].map(element=>[element.dataset.treeId,element]));
   for(const row of this.rows){const element=elements.get(row.id);if(!element)continue;const hidden=this.isHidden(row.id),selected=this.ids.has(row.id);element.draggable=this.groups.writable&&this.groups.canOrganize(row);element.classList.toggle('selected',selected);element.classList.toggle('is-hidden',hidden);element.setAttribute('aria-selected',String(selected));element.dataset.objectHidden=String(hidden);element.tabIndex=row.id===(focus||this.primary||this.rows[0]?.id)?0:-1;const eye=element.querySelector('[data-tree-visibility]');eye.classList.toggle('off',hidden);eye.setAttribute('aria-label',`${hidden?'Show':'Hide'} ${row.label}`);eye.title=hidden?'Show':'Hide';}return;
  }
  this.rowSignature=signature;
  list.innerHTML=this.rows.map(node=>{const hidden=this.isHidden(node.id),selected=this.ids.has(node.id);return `<div class="object-tree-row${selected?' selected':''}${hidden?' is-hidden':''}" role="treeitem" tabindex="${node.id===(focus||this.primary||this.rows[0]?.id)?0:-1}" aria-level="${node.depth+1}" aria-selected="${selected}" ${node.children.length?`aria-expanded="${node.expanded}"`:''} data-tree-id="${esc(node.id)}" data-object-kind="${node.kind}" draggable="${this.groups.writable&&this.groups.canOrganize(node)}" data-object-hidden="${hidden}" ${node.kind==='component'?`data-object="${esc(node.ref)}"`:''} style="--object-depth:${node.depth}" title="${esc([node.label,node.detail,node.id].filter(Boolean).join(' · '))}"><button class="object-tree-toggle" data-tree-toggle aria-label="${node.expanded?'Collapse':'Expand'} ${esc(node.label)}" ${!node.children.length?'disabled tabindex="-1"':''}>${node.children.length?icon(node.expanded?'chevronDown':'chevronRight'):''}</button><span class="object-tree-icon">${icon(symbols[node.kind]||'file')}</span><span class="object-tree-name">${esc(node.label)}</span>${node.children.length?`<small>${node.children.length}</small>`:''}<button class="object-tree-more" data-tree-menu aria-label="Actions for ${esc(node.label)}" title="More actions">⋯</button><button class="object-tree-eye${hidden?' off':''}" data-tree-visibility aria-label="${hidden?'Show':'Hide'} ${esc(node.label)}" title="${hidden?'Show':'Hide'}">${icon('eye')}</button></div>`;}).join('')||'<p class="drawer-description">No matching objects.</p>';
  list.scrollTop=scroll;if(focus)list.querySelector(`[data-tree-id="${CSS.escape(focus)}"]`)?.focus({preventScroll:true});
 }
 toggle(id){this.expanded.has(id)?this.expanded.delete(id):this.expanded.add(id);this.allExpanded=false;this.remember();this.renderRows();}
 choose(id,event={}){
  const result=chooseObjects(this.ids,id,this.rows.filter(n=>n.target).map(n=>n.id),{additive:event.ctrlKey||event.metaKey,range:event.shiftKey,anchor:this.anchor});this.anchor=result.anchor;this.primary=result.primary;this.selectIds(result.selection);
 }
 selectIds(ids){this.ids=new Set(ids);if(!this.ids.has(this.primary))this.primary=[...this.ids].at(-1)||null;this.reveal();this.applying=true;try{this.select(this.chosen);}finally{this.applying=false;}this.renderRows();this.paint(this.chosen);}
 pickNative(collection,id,ref){const node=[...this.tree?.nodes.values()||[]].find(n=>n.collection===collection&&n.native?.id===id&&(!ref||n.ref===ref));if(node)this.selectIds(new Set([node.id]));}
 isHidden(id){let node=this.tree?.nodes.get(id),seen=new Set();while(node&&!seen.has(node.id)){if(this.hidden.has(node.id))return true;seen.add(node.id);node=this.tree.nodes.get(node.parent);}return false;}
 toggleVisibility(id){
  if(this.hidden.has(id))this.hidden.delete(id);else if(this.isHidden(id)){let node=this.tree.nodes.get(id);while(node){this.hidden.delete(node.id);node=this.tree.nodes.get(node.parent);}}else this.hidden.add(id);
  this.masks=hiddenObjects(this.tree,this.hidden);this.remember();const visible=new Set([...this.ids].filter(id=>!this.isHidden(id)));if(visible.size!==this.ids.size)this.selectIds(visible);this.renderRows();this.paint(this.chosen);
 }
 visible(collection,item){const masks=this.masks;if(!masks)return true;if(collection==='board')return !masks.board.size;if(item.ref&&masks.components.has(item.ref))return false;return !masks[collection]?.has(nativeObjectKey(collection,item));}
 visibleSchematic(kind,key){const id=kind==='symbol'?(this.tree?.nodes.has('symbol:'+key)?'symbol:'+key:'component:'+key.split('#')[0]):kind==='sheet'?'sheet:'+key:kind==='node'?'node:'+key:'wire:'+key;return !this.isHidden(id);}
 blockKey(event){const command=event.ctrlKey||event.metaKey,key=event.key.toLowerCase(),edit=!command&&['delete','backspace','f','r','[',']'].includes(key)||command&&['c','x','v','d'].includes(key);if(this.canEdit||!edit)return false;event.preventDefault();this.toast('Select one editable object before changing this selection.',true);return true;}
 inspector(){
  const group=this.groups.inspector();if(group)return group;const selected=this.chosen;if(!selected.length||this.canEdit)return null;
  if(selected.length>1)return `<div id="objectInspector" data-object-type="multiple"><div class="inspector-name"><span class="part-badge">${icon('shapes')}</span><div class="name-stack"><strong>${selected.length} objects selected</strong><small>Mixed object selection</small></div></div><section class="inspector-section"><p>Select one editable object to change its properties.</p>${selected.map(n=>`<div class="pin-row"><span>${esc(n.label)}</span><span>${esc(n.kind)}</span></div>`).join('')}</section></div>`;
  const node=selected[0],item=node.native||{},[ox,oy]=this.geometry?.bbox||[100,100],position=item.x!==undefined?[item.x,item.y]:item.p||item.at||item.start;
  const field=(name,value,key)=>`<div class="property-row"><span>${name}</span><span ${key?`data-object-detail="${key}"`:''}>${esc(value??'—')}</span></div>`;
  return `<div id="objectInspector" data-object-type="${node.kind}"><div class="inspector-name"><span class="part-badge">${icon(symbols[node.kind]||'file')}</span><div class="name-stack"><strong>${esc(node.ref?node.ref+'.'+(item.name||node.label):node.label)}</strong><small>${esc(node.kind==='pad'?'PCB pad':node.label)}</small></div></div><section class="inspector-section"><h3>Properties</h3>${this.pending?'<p>Updating layout objects…</p>':`${field('Net',item.net||node.net)}${field('Layer',item.layer||item.layers?.join(', '))}${item.w!==undefined?field('Width',item.w+' mm'):''}${item.h!==undefined?field('Height',item.h+' mm'):''}${item.drill!==undefined?field('Drill',item.drill+' mm'):''}${item.text!==undefined?field('Text',item.text):''}${item.padstack_note?field('Pad stack',item.padstack_note):''}${position?field('X',+(position[0]-ox).toFixed(4)+' mm','x')+field('Y',+(position[1]-oy).toFixed(4)+' mm','y'):''}`}</section>${node.kind==='pad'&&!this.pending&&this.editable()&&!this.busy()?'<section class="inspector-section"><button class="secondary-button" id="editLayoutPad">Edit pad properties</button></section>':''}${node.ref?'<section class="inspector-section"><button class="secondary-button" id="inspectObjectComponent">Inspect component</button></section>':''}<section class="inspector-section"><details><summary>Object identity</summary><code class="object-identity">${esc(item.id||node.id)}</code></details></section></div>`;
 }
 bindInspector(host){this.groups.bindInspector(host);host.querySelector('#editLayoutPad')?.addEventListener('click',()=>this.editPad?.());host.querySelector('#inspectObjectComponent')?.addEventListener('click',()=>{const ref=this.chosen[0]?.ref;if(ref)this.selectIds(new Set(['component:'+ref]));});}
}
