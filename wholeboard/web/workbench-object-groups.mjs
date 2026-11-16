import {icon,esc} from './workbench-icons.mjs';
import {organizeObjectTree,objectSelection} from './workbench-object-groups-model.mjs';

const kinds=new Set(['component','symbol','net','pad','track','arc','via','zone','drawing','outline','wire','node','label','user_group']);
export class ObjectGroupsUI{
 constructor(owner){this.owner=owner;document.addEventListener('pointerdown',event=>{if(this.menu&&!this.menu.contains(event.target))this.close();});}
 get S(){return this.owner.S;}
 get writable(){return this.owner.editable()&&!this.owner.busy()&&!this.owner.pending&&!this.owner.data?.loading;}
 canOrganize(node){return !!node&&!node.ambiguous&&!node.unavailable&&kinds.has(node.kind);}
 selected(){return [...this.owner.ids];}
 run(operation){
  if(!this.writable)throw Error('Wait for the project and its current objects before organizing them.');
  const tree=this.owner.tree,next=organizeObjectTree(this.S.spec,tree,operation);
  if(JSON.stringify(next)===JSON.stringify(this.S.spec))return;
  const ids=operation.action==='create'||operation.action==='group'?[operation.id]:operation.action==='ungroup'?tree.nodes.get(operation.id)?.children||[]:operation.action==='remove'?[]:operation.ids||[operation.id];
  const labels={create:'Added object group',group:'Grouped objects',rename:'Renamed object group',move:'Moved objects in tree',reorder:'Reordered objects',ungroup:'Ungrouped objects',remove:'Deleted empty group'};
  this.owner.ids=new Set(ids);for(const id of ids)this.owner.expanded.add(id);this.owner.applying=true;
  try{this.owner.commit(next,labels[operation.action],null);}finally{this.owner.applying=false;}
  this.owner.refresh();this.owner.selectIds(new Set(ids.filter(id=>this.owner.tree.nodes.has(id))));this.owner.remember();
 }
 attempt(operation){try{this.run(operation);}catch(error){this.owner.toast(error.message,true);}}
 async named(operation,title,value='Group'){
  if(!this.writable)return this.owner.toast('Wait for the current project before organizing it.',true);
  const pid=this.S.pid,spec=this.S.spec,scope=this.owner.scope;this.close();const name=await this.owner.askText(title,'Group name',value);
  if(name===null)return;if(this.S.pid!==pid||this.S.spec!==spec||this.owner.scope!==scope)return this.owner.toast('The project changed. Open the group action again.',true);
  this.attempt({...operation,name});
 }
 addParent(node){if(node.kind==='user_group'||node.kind==='group'||node.kind==='net')return node.id;if(node.kind==='sheet')return 'components:'+node.sheet;if(node.id==='sheet:')return 'components:';if(node.kind==='layout'||node.kind==='root'||node.kind==='schematic')return this.owner.tree.view==='layout'?'components':'components:';return node.parent;}
 open(id,point){
  const node=this.owner.tree.nodes.get(id);if(!node)return;
  this.close();this.menuId=id;if(node.target&&!this.owner.ids.has(id))this.owner.selectIds(new Set([id]));
  const ids=this.selected(),base=n=>n.kind==='user_group'?n.category:n.naturalParent,groupable=ids.length>0&&ids.every(id=>this.canOrganize(this.owner.tree.nodes.get(id)))&&new Set(ids.map(id=>base(this.owner.tree.nodes.get(id)))).size===1;
  const writable=this.writable,group=node.kind==='user_group',parent=this.owner.tree.nodes.get(node.parent),at=parent?.children.indexOf(id),row=document.querySelector(`[data-tree-id="${CSS.escape(id)}"]`),rect=row?.getBoundingClientRect();
  const root=document.createElement('div');root.id='objectTreeMenus';document.body.append(root);this.menu=root;
  const item=(label,action,enabled=true,extra={})=>({label,action,enabled,...extra});
  const choices=[
   item('Add',()=>this.submenu([{label:'Group',action:()=>this.named({action:'create',id:'user-group:'+crypto.randomUUID(),parent:this.addParent(node)},'New group')}]),writable,{submenu:true,icon:'plus'}),
   item('Group selection',()=>this.named({action:'group',id:'user-group:'+crypto.randomUUID(),ids},'Group selection'),writable&&groupable,{icon:'folder'}),
   item('Rename',()=>this.named({action:'rename',id},'Rename group',node.label),writable&&group),
   item('Ungroup',()=>this.attempt({action:'ungroup',id}),writable&&group),
   {separator:true},
   item('Move to',()=>{const category=base(node),targets=[...this.owner.tree.nodes.values()].filter(n=>n.kind==='user_group'&&n.category===category&&!ids.includes(n.id));this.submenu([{label:this.owner.tree.nodes.get(category)?.label||'Original category',action:()=>this.attempt({action:'move',ids:ids.length?ids:[id],parent:category})},...targets.map(n=>({label:n.label,action:()=>this.attempt({action:'move',ids:ids.length?ids:[id],parent:n.id})}))]);},writable&&this.canOrganize(node)&&groupable,{submenu:true}),
   item('Move up',()=>this.attempt({action:'reorder',id,delta:-1}),writable&&this.canOrganize(node)&&at>0,{key:'Alt ↑'}),
   item('Move down',()=>this.attempt({action:'reorder',id,delta:1}),writable&&this.canOrganize(node)&&at>=0&&at<parent.children.length-1,{key:'Alt ↓'}),
   {separator:true},
   item('Select members',()=>{this.owner.expanded.add(id);this.owner.selectIds(new Set(node.children));},group&&node.children.length>0),
   item(this.owner.isHidden(id)?'Show':'Hide',()=>this.owner.toggleVisibility(id),true,{icon:'eye'}),
   item('Delete empty group',()=>this.attempt({action:'remove',id}),writable&&group&&!node.children.length,{icon:'trash'}),
  ];
  this.makeMenu(choices,point||[rect?.right||80,rect?.top||80],'Object actions');
 }
 makeMenu(choices,point,label,sub=false){
  const menu=document.createElement('div');menu.className='object-tree-menu';menu.setAttribute('role','menu');menu.setAttribute('aria-label',label);if(sub)menu.id='objectTreeSubmenu';this.menu.append(menu);
  menu.innerHTML=choices.map((item,index)=>item.separator?'<div role="separator"></div>':`<button role="menuitem" data-group-action="${index}" ${item.enabled===false?'disabled':''} ${item.submenu?'aria-haspopup="menu" aria-expanded="false"':''}>${item.icon?icon(item.icon):'<span class="object-menu-spacer"></span>'}<span>${esc(item.label)}</span>${item.key?`<kbd>${esc(item.key)}</kbd>`:''}${item.submenu?icon('chevronRight'):''}</button>`).join('');
  menu.style.left=Math.max(8,Math.min(innerWidth-menu.offsetWidth-8,point[0]))+'px';menu.style.top=Math.max(8,Math.min(innerHeight-menu.offsetHeight-8,point[1]))+'px';
  for(const button of menu.querySelectorAll('button'))button.onclick=event=>{event.stopPropagation();const choice=choices[+button.dataset.groupAction];if(choice.submenu){this.submenuAnchor=button;button.setAttribute('aria-expanded','true');}else this.close();Promise.resolve().then(()=>choice.action()).catch(error=>this.owner.toast(error.message,true));};
  menu.onkeydown=event=>{const buttons=[...menu.querySelectorAll('button:not(:disabled)')],index=buttons.indexOf(document.activeElement);let target;
   if(['ArrowUp','ArrowDown','Home','End'].includes(event.key)){event.preventDefault();target=buttons[event.key==='Home'?0:event.key==='End'?buttons.length-1:(index+(event.key==='ArrowDown'?1:-1)+buttons.length)%buttons.length];}
   if(event.key==='ArrowRight'&&document.activeElement?.hasAttribute('aria-haspopup')){event.preventDefault();document.activeElement.click();}
   if(event.key==='ArrowLeft'&&sub){event.preventDefault();menu.remove();this.submenuAnchor?.setAttribute('aria-expanded','false');this.submenuAnchor?.focus();}
   if(event.key==='Escape'){event.preventDefault();this.close(true);}
   if(event.key==='Tab')this.close();event.stopPropagation();target?.focus();
  };menu.querySelector('button:not(:disabled)')?.focus();return menu;
 }
 submenu(choices){
  if(!this.menu||!this.submenuAnchor)return;this.menu.querySelector('#objectTreeSubmenu')?.remove();const r=this.submenuAnchor.getBoundingClientRect();const submenu=this.makeMenu(choices,[r.right+4,r.top],'Object destinations',true);
  if(r.right+submenu.offsetWidth+8>innerWidth)submenu.style.left=Math.max(8,r.left-submenu.offsetWidth-4)+'px';
 }
 close(focus=false){const id=this.menuId;this.menu?.remove();this.menu=null;if(focus)this.owner.host?.querySelector(`[data-tree-id="${CSS.escape(id)}"]`)?.focus({preventScroll:true});}
 mount(list){
  list.addEventListener('contextmenu',event=>{const row=event.target.closest('[data-tree-id]');if(!row)return;event.preventDefault();event.stopPropagation();this.open(row.dataset.treeId,[event.clientX,event.clientY]);});
  list.addEventListener('keydown',event=>{
   const row=event.target.closest('[data-tree-id]');if(!row)return;const id=row.dataset.treeId;
   if(event.key==='ContextMenu'||event.shiftKey&&event.key==='F10'){event.preventDefault();event.stopPropagation();this.open(id);}
   if(event.altKey&&['ArrowUp','ArrowDown'].includes(event.key)){event.preventDefault();event.stopPropagation();this.attempt({action:'reorder',id,delta:event.key==='ArrowUp'?-1:1});}
  });
  list.addEventListener('dragstart',event=>{const row=event.target.closest('[data-tree-id]'),id=row?.dataset.treeId;if(!this.writable||!this.canOrganize(this.owner.tree.nodes.get(id)))return event.preventDefault();
   const ids=this.owner.ids.has(id)?this.selected():[id];if(ids.some(key=>!this.canOrganize(this.owner.tree.nodes.get(key))))return event.preventDefault();this.drag={ids,pid:this.S.pid,scope:this.owner.scope,spec:this.S.spec};event.dataTransfer.effectAllowed='move';event.dataTransfer.setData('application/x-openfabro-object-tree',JSON.stringify({pid:this.S.pid,scope:this.owner.scope,ids}));row.classList.add('is-dragging');
  });
  const dropOperation=event=>{
   const row=event.target.closest('[data-tree-id]'),target=this.owner.tree.nodes.get(row?.dataset.treeId),drag=this.drag;if(!target||!drag||drag.pid!==this.S.pid||drag.scope!==this.owner.scope||drag.spec!==this.S.spec||!this.writable)return null;
   const rect=row.getBoundingClientRect(),ratio=(event.clientY-rect.top)/rect.height,inside=['group','user_group','net'].includes(target.kind)&&ratio>.25&&ratio<.75;
   const operation=inside?{action:'move',ids:drag.ids,parent:target.id}:{action:'move',ids:drag.ids,parent:target.parent,[ratio<.5?'before':'after']:target.id};
   try{organizeObjectTree(this.S.spec,this.owner.tree,operation);}catch{return null;}
   return{row,operation,position:inside?'inside':ratio<.5?'before':'after'};
  };
  list.addEventListener('dragover',event=>{this.clearDrop();const target=dropOperation(event);if(!target)return;event.preventDefault();event.dataTransfer.dropEffect='move';target.row.dataset.dropPosition=target.position;});
  list.addEventListener('drop',event=>{const target=dropOperation(event);this.clearDrop();if(target){event.preventDefault();this.attempt(target.operation);}this.drag=null;});
  list.addEventListener('dragend',()=>{this.drag=null;this.clearDrop();});
 }
 clearDrop(){this.owner.host?.querySelectorAll('[data-drop-position],.is-dragging').forEach(row=>{delete row.dataset.dropPosition;row.classList.remove('is-dragging');});}
 inspector(){
  const selected=this.owner.chosen;if(selected.length!==1||selected[0].kind!=='user_group')return null;const node=selected[0],members=objectSelection(this.owner.tree,[node.id]),enabled=this.writable;
  return `<div data-object-group="${esc(node.id)}"><div class="inspector-name"><span class="part-badge">${icon('folder')}</span><div class="name-stack"><strong>${esc(node.label)}</strong><small>Group</small></div></div><section class="inspector-section"><h3>Properties</h3><label class="property-row"><span>Name</span><input id="objectGroupName" maxlength="120" value="${esc(node.label)}" ${enabled?'':'disabled'}></label><div class="property-row"><span>Members</span><span>${members.length}</span></div><div class="property-row"><span>Category</span><span>${esc(this.owner.tree.nodes.get(node.category)?.label||node.category)}</span></div>${node.unavailable?'<p>Its original category is currently unavailable.</p>':''}${node.missingMembers?'<p>'+node.missingMembers+' stored member identities are unavailable in the current design.</p>':''}</section><section class="inspector-section"><button class="secondary-button" id="selectGroupMembers" ${node.children.length?'':'disabled'}>Select members</button><button class="secondary-button" id="ungroupObjects" ${enabled?'':'disabled'}>Ungroup</button><button class="secondary-button" id="deleteEmptyObjectGroup" ${enabled&&!node.children.length?'':'disabled'}>Delete empty group</button></section></div>`;
 }
 bindInspector(host){const node=this.owner.chosen[0];if(node?.kind!=='user_group')return;
  host.querySelector('#objectGroupName')?.addEventListener('change',event=>this.attempt({action:'rename',id:node.id,name:event.target.value}));
  host.querySelector('#selectGroupMembers')?.addEventListener('click',()=>this.owner.selectIds(new Set(node.children)));
  host.querySelector('#ungroupObjects')?.addEventListener('click',()=>this.attempt({action:'ungroup',id:node.id}));
  host.querySelector('#deleteEmptyObjectGroup')?.addEventListener('click',()=>this.attempt({action:'remove',id:node.id}));
 }
}
