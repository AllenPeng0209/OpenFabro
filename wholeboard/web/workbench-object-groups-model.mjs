// Groups organize the object tree. They do not change electrical or geometric ownership.
const record=value=>value!==null&&typeof value==='object'&&!Array.isArray(value);
const groupId=id=>typeof id==='string'&&/^user-group:[A-Za-z0-9_-]{1,80}$/.test(id);
const itemId=id=>typeof id==='string'&&id.length<=256&&/^(component|symbol|net|pad|track|arc|via|zone|drawing|outline|wire|node):.+$/u.test(id);
const categoryId=id=>typeof id==='string'&&id.length<=256&&(/^(components|nets|zones|graphics|outline)$/.test(id)||/^(components|wires|nodes|labels):.*$/u.test(id)||/^(component|net|pads|graphics):.+$/u.test(id));
const kinds=new Set(['component','symbol','net','pad','track','arc','via','zone','drawing','outline','wire','node','label','user_group']);
const stateFor=(spec,view)=>({groups:{},parents:{},order:{},...spec.editor?.object_tree?.[view]});

export function validateObjectOrganization(value){
 if(value==null)return;
 if(!record(value)||Object.keys(value).some(k=>!['layout','schematic'].includes(k)))throw Error('Object groups need layout or schematic metadata.');
 for(const state of Object.values(value)){
  if(!record(state)||Object.keys(state).some(k=>!['groups','parents','order'].includes(k)))throw Error('Object group metadata must contain groups, parents and order.');
  const groups=state.groups??{},parents=state.parents??{},order=state.order??{};
  if(!record(groups)||!record(parents)||!record(order)||Object.keys(groups).length>1000||Object.keys(parents).length>20000||Object.keys(order).length>20000)throw Error('Object group metadata is too large or malformed.');
  for(const[id,group]of Object.entries(groups)){
   if(!groupId(id)||!record(group)||typeof group.name!=='string'||!group.name.trim()||group.name.length>120||Object.keys(group).some(k=>!['name','parent'].includes(k))||!(categoryId(group.parent)||groupId(group.parent)))throw Error('Each object group needs a valid identity, name and parent category.');
   const seen=new Set([id]);let parent=group.parent;
   while(groupId(parent)){if(seen.has(parent))throw Error('Object groups cannot contain a parent cycle.');seen.add(parent);if(!groups[parent])throw Error('An object group parent does not exist.');parent=groups[parent].parent;}
   if(!categoryId(parent))throw Error('Object groups need a parent category.');
  }
  for(const[id,parent]of Object.entries(parents))if(!itemId(id)||!groupId(parent)||!groups[parent])throw Error('Group members must refer to an existing object group.');
  for(const[parent,ids]of Object.entries(order))if(!(categoryId(parent)||groupId(parent)&&groups[parent])||!Array.isArray(ids)||ids.length>20000||new Set(ids).size!==ids.length||ids.some(id=>!itemId(id)&&!(groupId(id)&&groups[id])))throw Error('Object order must contain distinct object identities within a category.');
 }
}

export function remapObjectOrganization(spec,replace){
 for(const state of Object.values(spec.editor?.object_tree||{})){
  if(!record(state))continue;
  for(const group of Object.values(state.groups||{}))group.parent=replace(group.parent);
  const entries=Object.entries(state.parents||{});
  // A merge preserves the destination object's own membership when both IDs existed.
  state.parents=Object.fromEntries([...entries.filter(([id])=>replace(id)!==id),...entries.filter(([id])=>replace(id)===id)].map(([id,parent])=>[replace(id),parent]));
  const order={};
  for(const[parent,ids]of Object.entries(state.order||{}).sort(([a],[b])=>Number(replace(a)!==a)-Number(replace(b)!==b))){const key=replace(parent);order[key]=[...new Set([...(order[key]||[]),...ids.map(replace)])];}
  state.order=order;
 }
}

export function applyObjectOrganization(tree,spec){
 for(const node of tree.nodes.values())node.naturalParent=node.parent;
 try{validateObjectOrganization(spec.editor?.object_tree);}catch(error){tree.organizationError=error.message;return tree;}
 const state=stateFor(spec,tree.view),nodes=tree.nodes;
 const category=id=>{let parent=state.groups[id]?.parent;while(state.groups[parent])parent=state.groups[parent].parent;return parent;};
 for(const[id,definition]of Object.entries(state.groups)){
  const base=category(id),unavailable=!nodes.has(base);
  nodes.set(id,{id,kind:'user_group',label:definition.name,parent:null,children:[],category:base,unavailable,missingMembers:0,detail:unavailable?'Category unavailable':'Group',native:definition,target:{kind:'object_group',id}});
 }
 for(const[id,definition]of Object.entries(state.groups)){
  const node=nodes.get(id),parent=nodes.has(definition.parent)?definition.parent:tree.view;
  node.parent=parent;nodes.get(parent)?.children.push(id);
 }
 for(const[id,destination]of Object.entries(state.parents)){
  const node=nodes.get(id),group=nodes.get(destination);
  // A component moved to another sheet remains there. Stale membership never reassigns it.
  if(!group)continue;if(!node||node.ambiguous||!kinds.has(node.kind)||group.category!==node.naturalParent){group.missingMembers++;continue;}
  const original=nodes.get(node.parent);if(original)original.children=original.children.filter(child=>child!==id);
  node.parent=destination;group.children.push(id);
 }
 for(const[parent,order]of Object.entries(state.order)){
  const node=nodes.get(parent);if(!node)continue;const positions=new Map(order.map((id,index)=>[id,index]));
  node.children.sort((a,b)=>(positions.get(a)??Infinity)-(positions.get(b)??Infinity));
 }
 for(const id of Object.keys(state.groups)){const node=nodes.get(id);if(node.missingMembers)node.detail+=` · ${node.missingMembers} unavailable member${node.missingMembers===1?'':'s'}`;}
 return tree;
}

export function objectSelection(tree,ids){
 const chosen=[],seen=new Set();
 const visit=id=>{if(seen.has(id))return;seen.add(id);const node=tree.nodes.get(id);if(!node)return;if(node.kind==='user_group')for(const child of node.children)visit(child);else chosen.push(node);};
 for(const id of ids)visit(typeof id==='string'?id:id.id);
 return chosen;
}

export function organizeObjectTree(spec,tree,operation){
 validateObjectOrganization(spec.editor?.object_tree);
 const next=structuredClone(spec),state=structuredClone(stateFor(spec,tree.view)),nodes=tree.nodes;
 const node=id=>{const item=nodes.get(id);if(!item||item.ambiguous||!kinds.has(item.kind))throw Error('Select an available object or group to organize.');return item;};
 const category=item=>item.kind==='user_group'?item.category:item.naturalParent;
 const destination=parent=>{
  const item=nodes.get(parent);if(!item||item.unavailable)throw Error('The destination category is unavailable.');
  if(item.kind==='user_group')return item.category;
  if(!categoryId(parent))throw Error('Move objects within their original category.');
  return parent;
 };
 const parentOf=id=>state.groups[id]?.parent||state.parents[id]||nodes.get(id)?.naturalParent;
 const ancestry=(id,ancestor)=>{let parent=parentOf(id),seen=new Set();while(parent&&!seen.has(parent)){if(parent===ancestor)return true;seen.add(parent);parent=parentOf(parent);}return false;};
 const selected=ids=>{
  const unique=[...new Set(ids||[])];unique.forEach(node);
  return unique.filter(id=>!unique.some(other=>other!==id&&ancestry(id,other)));
 };
 const move=(ids,parent)=>{
  const base=destination(parent);
  for(const id of ids){const item=node(id);if(category(item)!==base)throw Error('Move objects within the same category.');if(id===parent||ancestry(parent,id))throw Error('A group cannot move into itself or a descendant.');}
  for(const order of Object.values(state.order))for(const id of ids){let at;while((at=order.indexOf(id))>=0)order.splice(at,1);}
  for(const id of ids){if(state.groups[id])state.groups[id].parent=parent;else if(state.groups[parent])state.parents[id]=parent;else delete state.parents[id];}
 };
 const siblings=parent=>[...nodes.get(parent)?.children||[]];
 const put=(parent,ids,before,after)=>{
  const order=siblings(parent).filter(id=>!ids.includes(id));let at=before?order.indexOf(before):after?order.indexOf(after)+1:order.length;
  if((before&&!order.includes(before))||(after&&!order.includes(after)))throw Error('The destination sibling is no longer available.');
  order.splice(Math.max(0,at),0,...ids);state.order[parent]=order;
 };
 const {action,id}=operation;
 if(action==='create'||action==='group'){
  if(!groupId(id)||state.groups[id]||nodes.has(id))throw Error('Use a new object group identity.');
  const ids=action==='group'?selected(operation.ids):[];
  if(action==='group'&&!ids.length)throw Error('Select objects to group.');
  const parents=ids.map(key=>parentOf(key)),base=ids.length?category(node(ids[0])):null;
  if(ids.some(key=>category(node(key))!==base))throw Error('Group objects from the same category.');
  const parent=operation.parent||(new Set(parents).size===1?parents[0]:base);
  destination(parent);if(ids.length&&destination(parent)!==base)throw Error('Group objects within their original category.');
  const name=String(operation.name??'').trim();if(!name||name.length>120)throw Error('Use a group name from1 to120 characters.');
  state.groups[id]={name,parent};
  // Validate against the original live tree before introducing the new destination.
  for(const key of ids){if(state.groups[key])state.groups[key].parent=id;else state.parents[key]=id;}
  const original=siblings(parent),at=original.findIndex(key=>ids.includes(key)),remaining=original.filter(key=>!ids.includes(key));
  remaining.splice(at<0?remaining.length:at,0,id);state.order[parent]=remaining;
  if(ids.length){const rank=new Map([...nodes.keys()].map((key,index)=>[key,index]));
   // Visual sibling order is authoritative, not the order the user clicked the selection.
   for(const p of new Set(parents)){const list=siblings(p);for(let i=0;i<list.length;i++)rank.set(list[i],i);}
   state.order[id]=[...ids].sort((a,b)=>(rank.get(a)??0)-(rank.get(b)??0));
  }
 }else if(action==='rename'){
  if(!state.groups[id])throw Error('Select a group to rename.');const name=String(operation.name??'').trim();if(!name||name.length>120)throw Error('Use a group name from1 to120 characters.');state.groups[id].name=name;
 }else if(action==='move'){
  const ids=selected(operation.ids);if(!ids.length)throw Error('Select objects to move.');const parent=operation.parent;move(ids,parent);put(parent,ids,operation.before,operation.after);
 }else if(action==='reorder'){
  const item=node(id),parent=item.parent,order=siblings(parent),from=order.indexOf(id),delta=operation.delta;
  if(delta!==1&&delta!==-1)throw Error('Move one position up or down.');const to=Math.max(0,Math.min(order.length-1,from+delta));order.splice(from,1);order.splice(to,0,id);state.order[parent]=order;
 }else if(action==='ungroup'||action==='remove'){
  if(!state.groups[id])throw Error('Select a group to ungroup.');const item=nodes.get(id),parent=state.groups[id].parent,children=[...item?.children||[]];
  if(action==='remove'&&children.length)throw Error('Move members out before deleting this group.');
  const order=siblings(parent),at=order.indexOf(id);if(at>=0)order.splice(at,1,...children);state.order[parent]=order;
  for(const group of Object.values(state.groups))if(group.parent===id)group.parent=parent;
  for(const[key,group]of Object.entries(state.parents))if(group===id){if(state.groups[parent])state.parents[key]=parent;else delete state.parents[key];}
  delete state.groups[id];delete state.order[id];
  for(const order of Object.values(state.order)){let at;while((at=order.indexOf(id))>=0)order.splice(at,1);}
 }else throw Error('Choose a supported object organization action.');
 next.editor??={};next.editor.object_tree??={};next.editor.object_tree[tree.view]=state;
 validateObjectOrganization(next.editor.object_tree);return next;
}
