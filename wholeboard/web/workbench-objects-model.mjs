import {sheetDefinitions,componentSheet} from './workbench-sheets.mjs';
import {applyObjectOrganization} from './workbench-object-groups-model.mjs';
export {organizeObjectTree,objectSelection,validateObjectOrganization} from './workbench-object-groups-model.mjs';

const sorted=value=>value&&typeof value==='object'?Array.isArray(value)?value.map(sorted):Object.fromEntries(Object.keys(value).sort().map(key=>[key,sorted(value[key])])):value;
function fingerprint(value){let hash=2166136261;for(const c of JSON.stringify(sorted(value))){hash^=c.charCodeAt(0);hash=Math.imul(hash,16777619);}return(hash>>>0).toString(16);}
const identity=item=>String(item.id??'legacy-'+fingerprint(item));
export const guideIdentity=guide=>String(guide.id||'legacy-'+fingerprint(guide));
const order=(a,b)=>String(a.name??a.id??'').localeCompare(String(b.name??b.id??''),undefined,{numeric:true})||identity(a).localeCompare(identity(b));
export const nativeObjectKey=(collection,item)=>['pads','footprints','drawings'].includes(collection)?`${item.ref||'board'}:${identity(item)}`:identity(item);

export function buildObjectTree(spec,{view='layout',geometry=null,scene=null,title=spec.name||'Project'}={}){
 const nodes=new Map(),root='root';
 const add=(id,kind,label,parent,extra={})=>{
  const original=id;let occurrence=1;while(nodes.has(id)){nodes.get(original).ambiguous=true;id=original+'~'+(++occurrence);}
  const node={id,kind,label,parent,children:[],...extra};if(id!==original)node.ambiguous=true;
  nodes.set(id,node);if(parent)nodes.get(parent)?.children.push(id);return node;
 };
 const group=(id,label,parent)=>add(id,'group',label,parent);
 add(root,'root',title,null,{target:{kind:'project'}});
 const nets=parent=>{
  group('nets','Nets',parent);
  const names=new Set((spec.nets||[]).map(net=>net.name));
  for(const collection of ['tracks','arcs','vias'])for(const item of geometry?.[collection]||[])if(item.net)names.add(item.net);
  for(const name of names){const canonical=spec.nets?.find(net=>net.name===name);add('net:'+name,'net',name,'nets',{net:name,detail:canonical?`${canonical.pins.length} pins`:'Native net',target:{kind:'net',name},native:canonical});}
 };
 if(view==='layout'){
  add('layout','layout','Layout',root,{target:{kind:'board'}});group('components','Components','layout');nets('layout');
  group('zones','Zones','layout');group('graphics','Graphics','layout');group('outline','Board outline','layout');
  const refs=new Set((spec.components||[]).map(component=>component.ref));for(const fp of geometry?.footprints||[])refs.add(fp.ref);
  for(const ref of refs){
   const component=spec.components?.find(c=>c.ref===ref),fp=geometry?.footprints?.find(f=>f.ref===ref);
   const node=add('component:'+ref,'component',ref,'components',{ref,detail:component?.value||'Native footprint',native:component,target:component?{kind:'component',ref}:{kind:'footprint',ref,id:fp?.id}});
   if(!fp)continue;
   const footprint=add('footprint:'+ref,'footprint','Footprint',node.id,{ref,detail:fp.lib||'',native:fp,target:{kind:'footprint',ref,id:fp.id},collection:'footprints'});
   const pads=group('pads:'+ref,'Pads',footprint.id),graphics=group('graphics:'+ref,'Graphics',footprint.id);
   const actual=(geometry.pads||[]).filter(p=>p.ref===ref).sort(order),totals=new Map(),seen=new Map();
   for(const pad of actual)totals.set(pad.name,(totals.get(pad.name)||0)+1);
   for(const pad of actual){const n=(seen.get(pad.name)||0)+1;seen.set(pad.name,n);add(`pad:${ref}:${identity(pad)}`,'pad',`Pad ${pad.name||'—'}${totals.get(pad.name)>1?` (${n})`:''}`,pads.id,{ref,net:pad.net,detail:[pad.net,...pad.layers||[]].filter(Boolean).join(' · '),native:pad,collection:'pads',target:{kind:'pad',ref,id:pad.id}});}
   for(const drawing of (geometry.drawings||[]).filter(item=>item.ref===ref).sort(order))addDrawing(drawing,graphics.id);
  }
  function addDrawing(item,parent){add(`drawing:${item.ref||'board'}:${identity(item)}`,'drawing',item.kind==='text'?(item.role==='reference'?'Reference ':item.role==='value'?'Value ':'Text ')+(item.text||''):item.kind[0].toUpperCase()+item.kind.slice(1),parent,{ref:item.ref,detail:item.layer,native:item,collection:'drawings',target:{kind:'drawing',ref:item.ref,id:item.id}});}
  for(const item of geometry?.drawings||[])if(!item.ref)addDrawing(item,'graphics');
  for(const item of geometry?.outline||[])add('outline:'+identity(item),'outline',item.kind==='rect'?'Rectangle':item.kind[0].toUpperCase()+item.kind.slice(1),'outline',{detail:'Edge.Cuts',native:item,collection:'outline',target:{kind:'outline',id:item.id}});
  for(const [collection,kind,label]of [['tracks','track','Trace'],['arcs','arc','Arc'],['vias','via','Via']])for(const item of [...geometry?.[collection]||[]].sort(order)){
   const parent=nodes.has('net:'+item.net)?'net:'+item.net:'nets';
   add(kind+':'+identity(item),kind,`${label} ${identity(item).slice(0,8)}`,parent,{net:item.net,detail:[item.net,item.layer,...item.layers||[]].filter(Boolean).join(' · '),native:item,collection,target:{kind:'copper',collection,id:item.id}});
  }
  const definitions=geometry?.zone_definitions||[];
  for(const item of definitions){const id='zone:'+identity(item);add(id,'zone',`${item.keepout?'Keepout':'Copper zone'} ${identity(item).slice(0,8)}`,'zones',{net:item.net,detail:[item.net,...item.layers||[]].filter(Boolean).join(' · '),native:item,collection:'zone_definitions',target:{kind:'zone',id:item.id}});}
  for(const fill of geometry?.zones||[]){let parent='zone:'+fill.zone_id;if(!nodes.has(parent)){parent='zone:'+identity(fill);if(!nodes.has(parent))add(parent,'zone','Copper zone','zones',{net:fill.net,detail:fill.layer,target:{kind:'zone',id:fill.zone_id||fill.id},native:fill});}add('fill:'+identity(fill),'fill','Filled island '+identity(fill).slice(0,8),parent,{net:fill.net,detail:fill.layer,native:fill,collection:'zones',target:{kind:'fill',id:fill.id,zoneId:fill.zone_id}});}
 }else{
  add('schematic','schematic','Schematic',root,{target:{kind:'board'}});
  add('sheet:','sheet','Main','schematic',{sheet:'',target:{kind:'sheet_root',sheet:''}});
  const definitions=sheetDefinitions(spec);
  for(const [id,definition]of Object.entries(definitions))add('sheet:'+id,'sheet',definition.title||id,null,{sheet:id,detail:id,native:definition,target:{kind:'sheet',id}});
  for(const [id,definition]of Object.entries(definitions)){const node=nodes.get('sheet:'+id),parent=nodes.get('sheet:'+(definition.parent||''))||nodes.get('sheet:');node.parent=parent.id;parent.children.push(node.id);}
  const container=(type,label,sheet='')=>{const id=type+':'+sheet;if(!nodes.has(id))group(id,label,nodes.has('sheet:'+sheet)?'sheet:'+sheet:'sheet:');return id;};
  for(const sheet of ['',...Object.keys(definitions)])container('components','Components',sheet);
  const location=anchor=>anchor?.startsWith('node:')?spec.editor?.wire_nodes?.[anchor.slice(5)]?.sheet||'':anchor?.startsWith('sheet:')?definitions[anchor.slice(6).split('.')[0]]?.parent||'':componentSheet(spec.components?.find(c=>c.ref===anchor?.split('.')[0].split('#')[0])||{});
  for(const component of spec.components||[]){
   const ref=component.ref,sheet=componentSheet(component),parent=container('components','Components',sheet);
   const node=add('component:'+ref,'component',ref,parent,{ref,detail:component.value||'',sheet,native:component,target:{kind:'component',ref}});
   const symbols=scene?.symbols?.filter(symbol=>symbol.ref===ref)||[];
   if(symbols.length>1)for(const symbol of symbols)add('symbol:'+symbol.key,'symbol',symbol.key,node.id,{ref,sheet:symbol.sheet,detail:'Symbol unit',native:symbol,target:{kind:'symbol',ref,symbolKey:symbol.key,sheet:symbol.sheet}});
  }
  (spec.editor?.connection_guides||[]).forEach((guide,index)=>{const route=scene?.routes?.find(r=>r.index===index),sheet=route?.sheet??location(guide.from),net=route?.net||guide.net||spec.nets?.find(n=>n.pins.includes(guide.from)||n.pins.includes(guide.to))?.name||'';add('wire:'+guideIdentity(guide),'wire',`Wire ${guide.id||index+1}`,container('wires','Wires',sheet),{net,sheet,detail:[guide.from,guide.to,net].filter(Boolean).join(' · '),native:guide,target:{kind:'wire',id:guideIdentity(guide),index,sheet}});});
  for(const [id,node]of Object.entries(spec.editor?.wire_nodes||{})){const sheet=node.sheet||'',kind=node.label?'label':'node',label=node.label?(node.label.kind==='power'?'Power ':node.label.kind==='ground'?'Ground ':'Label ')+node.net:'Wire endpoint '+id.slice(0,8);add('node:'+id,kind,label,container(node.label?'labels':'nodes',node.label?'Labels':'Wire endpoints',sheet),{net:node.net,sheet,detail:node.net,native:node,target:{kind:'node',id,sheet}});}
  nets('schematic');
 }
 const tree={root,nodes,view};applyObjectOrganization(tree,spec);
 for(const node of nodes.values()){
  const context=[];let parent=nodes.get(node.parent),visited=new Set();while(parent&&!visited.has(parent.id)){visited.add(parent.id);if(['component','sheet','net','user_group'].includes(parent.kind))context.push(parent.label);parent=nodes.get(parent.parent);}
  node.search=[node.label,node.kind,node.detail,node.ref,node.net,node.id,...context].filter(Boolean).join(' ').toLowerCase();
 }
 return tree;
}

export function objectRows(tree,{expanded=new Set(['root','layout','schematic','components','nets','sheet:','components:','zones']),query=''}={}){
 const words=query.toLowerCase().trim().split(/\s+/).filter(Boolean),included=new Set();
 if(words.length)for(const node of tree.nodes.values())if(words.every(word=>node.search.includes(word))){let item=node,visited=new Set();while(item&&!visited.has(item.id)){visited.add(item.id);included.add(item.id);item=tree.nodes.get(item.parent);}}
 const rows=[],walk=(id,depth,seen)=>{if(seen.has(id)||words.length&&!included.has(id))return;const node=tree.nodes.get(id);if(!node)return;rows.push({...node,depth,expanded:words.length?node.children.some(id=>included.has(id)):expanded.has(id)});if(words.length||expanded.has(id))for(const child of node.children)walk(child,depth+1,new Set([...seen,id]));};
 walk(tree.root,0,new Set());return rows;
}

export function chooseObjects(current,id,visible,{additive=false,range=false,anchor=null}={}){
 const selection=additive?new Set(current):new Set();
 if(range&&visible.includes(anchor)&&visible.includes(id)){const a=visible.indexOf(anchor),b=visible.indexOf(id);for(const key of visible.slice(Math.min(a,b),Math.max(a,b)+1))selection.add(key);}
 else if(additive&&selection.has(id))selection.delete(id);else selection.add(id);
 return{selection,anchor:range&&visible.includes(anchor)?anchor:id,primary:selection.has(id)?id:[...selection].at(-1)||null};
}

export function hiddenObjects(tree,hidden){
 const result=Object.fromEntries(['board','components','nets','footprints','pads','tracks','arcs','vias','drawings','outline','zone_definitions','zones'].map(key=>[key,new Set()]));
 const visit=(id,seen=new Set())=>{if(seen.has(id))return;seen.add(id);const node=tree.nodes.get(id);if(!node)return;
  if(node.kind==='component')result.components.add(node.ref);if(node.kind==='net')result.nets.add(node.net);if(['layout','schematic','root'].includes(node.kind))result.board.add('layout');
  if(node.collection&&node.native)result[node.collection]?.add(nativeObjectKey(node.collection,node.native));
  for(const child of node.children)visit(child,seen);
 };
 for(const id of hidden)visit(id);return result;
}

export function displayedWires(scene,spec,sheet,visible=()=>true){
 if(!visible('sheet',sheet))return[];
 const routes=(scene.routes||[]).filter(route=>route.sheet===sheet&&route.status==='routed'),hidden=routes.filter(r=>!visible('wire',guideIdentity(spec.editor?.connection_guides?.[r.index]||{})));
 const wires=(scene.wires||[]).filter(w=>w.sheet===sheet);if(!hidden.length)return wires;
 const result=[],eps=1e-6;
 const intervals=(a,b,paths)=>{
  const dx=b[0]-a[0],dy=b[1]-a[1],length=dx*dx+dy*dy;if(length<eps)return[];const list=[];
  for(const path of paths)for(let i=1;i<path.points.length;i++){
   const p=path.points[i-1],q=path.points[i];if(Math.abs(dx*(p[1]-a[1])-dy*(p[0]-a[0]))>eps*Math.sqrt(length)||Math.abs(dx*(q[1]-a[1])-dy*(q[0]-a[0]))>eps*Math.sqrt(length))continue;
   const u=((p[0]-a[0])*dx+(p[1]-a[1])*dy)/length,v=((q[0]-a[0])*dx+(q[1]-a[1])*dy)/length,lo=Math.max(0,Math.min(u,v)),hi=Math.min(1,Math.max(u,v));if(hi-lo>eps)list.push([lo,hi]);
  }return list;
 };
 for(const wire of wires)for(let i=1;i<wire.points.length;i++){
  const a=wire.points[i-1],b=wire.points[i],cut=intervals(a,b,hidden.filter(r=>r.net===wire.net)),keep=intervals(a,b,routes.filter(r=>r.net===wire.net&&!hidden.includes(r)));
  const marks=[...new Set([0,1,...cut.flat(),...keep.flat()])].sort((a,b)=>a-b),pieces=[];
  for(let j=1;j<marks.length;j++){const lo=marks[j-1],hi=marks[j],mid=(lo+hi)/2;if(hi-lo<eps||cut.some(([a,b])=>a<=mid&&mid<=b)&&!keep.some(([a,b])=>a<=mid&&mid<=b))continue;const previous=pieces.at(-1);if(previous&&Math.abs(previous[1]-lo)<eps)previous[1]=hi;else pieces.push([lo,hi]);}
  const at=t=>[a[0]+(b[0]-a[0])*t,a[1]+(b[1]-a[1])*t];for(const[lo,hi]of pieces)result.push({...wire,points:[at(lo),at(hi)]});
 }return result;
}
