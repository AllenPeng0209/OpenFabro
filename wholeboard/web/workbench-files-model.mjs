const collator=new Intl.Collator(undefined,{numeric:true,sensitivity:'base'});
const order=(a,b)=>(a.kind==='folder'?0:1)-(b.kind==='folder'?0:1)||collator.compare(a.name,b.name)||a.path.localeCompare(b.path);
export const isDocument=file=>!file.path.startsWith('native/')&&!file.path.startsWith('history/')&&/\.(md|markdown)$/i.test(file.path);
export const isAsset=file=>!file.path.startsWith('native/')&&!file.path.startsWith('history/')&&/\.(step|stp|stl|glb|gltf|svg|dxf|png|jpg|jpeg|webp|gif|pdf|kicad_mod|mod|fcstd)$/i.test(file.path);
export const imageFile=file=>/\.(png|jpg|jpeg|webp|gif|svg)$/i.test(file?.path||'');
export function fileBadge(file){
 if(file.native_role==='older_geometry')return'Prior geometry';
 if(['pcb','schematic','geometry'].includes(file.native_role))return(file.native_status==='current'?'Current ':file.native_status==='stale'?'Older design · ':'')+({pcb:'PCB',schematic:'schematic',geometry:'geometry'})[file.native_role];
 if(file.path.startsWith('history/'))return'Saved design';
 return'';
}

export function buildFileTree(files,{native={status:'none',primary_paths:{}}}={}){
 const nodes=new Map(),root='folder:';nodes.set(root,{id:root,path:'',name:'Project files',kind:'folder',parent:null,children:[]});
 const folder=path=>{
  const id='folder:'+path;if(nodes.has(id))return id;const split=path.lastIndexOf('/'),parent=folder(split<0?'':path.slice(0,split)),name=split<0?path:path.slice(split+1);
  const badge=path===native.folder?(native.status==='current'?'Current generation':native.status==='stale'?'Older design':''):path.startsWith('native/')&&path.split('/').length===2?'Saved output':'';
  nodes.set(id,{id,path,name,kind:'folder',parent,children:[],badge});nodes.get(parent).children.push(id);return id;
 };
 for(const file of files){
  const path=file.path;if(typeof path!=='string'||!path||path.startsWith('/')||path.split('/').some(p=>!p||p==='.'||p==='..'||p.startsWith('.')))throw Error('Invalid project file path in the catalog.');
  const id='file:'+path;if(nodes.has(id))throw Error('Duplicate project file path in the catalog.');const split=path.lastIndexOf('/'),parent=folder(split<0?'':path.slice(0,split));
  const node={id,path,name:split<0?path:path.slice(split+1),parent,kind:'file',file,badge:fileBadge(file),readOnly:file.text_editable===false||/^(native|history)\//.test(path),children:[]};nodes.set(id,node);nodes.get(parent).children.push(id);
 }
 for(const node of nodes.values())if(node.children.length)node.children.sort((a,b)=>order(nodes.get(a),nodes.get(b)));
 return{root,nodes,native};
}

export function fileRows(tree,{expanded=new Set(['','docs','native','history','firmware']),query='',scope='all'}={}){
 const words=query.toLowerCase().trim().split(/\s+/).filter(Boolean),matched=new Set(),filtered=words.length||scope!=='all';
 const allowed=node=>scope==='documents'?isDocument(node.file):scope==='assets'?isAsset(node.file):scope==='current'?node.file.native_status==='current':scope==='saved'?node.file.category==='native'&&node.file.native_status!=='current'||node.file.category==='history':true;
 if(filtered)for(const node of tree.nodes.values())if(node.kind==='file'&&allowed(node)&&words.every(word=>[node.path,node.badge,node.file.native_status||''].join(' ').toLowerCase().includes(word))){let current=node;while(current){matched.add(current.id);current=tree.nodes.get(current.parent);}}
 const rows=[],walk=(id,depth)=>{const node=tree.nodes.get(id);if(!node||filtered&&!matched.has(id))return;if(node.path)rows.push({...node,depth:Math.max(0,depth-1),expanded:!!filtered||expanded.has(node.path)});if(filtered||expanded.has(node.path))for(const child of node.children)walk(child,depth+1);};walk(tree.root,0);return rows;
}

export class CatalogCancelled extends Error{constructor(){super('File catalog load cancelled.');this.cancelled=true;}}
export async function loadFileCatalog(fetchPage,{isCurrent=()=>true,pageSize=1000,restarts=2}={}){
 for(let attempt=0;attempt<=restarts;attempt++){
  let first=null,offset=0,entries=[],seen=new Set();
  try{
   while(true){
    if(!isCurrent())throw new CatalogCancelled();
    const page=await fetchPage({offset,limit:pageSize,...(first?{expected_index_sha256:first.index_sha256}:{})});
    if(!isCurrent())throw new CatalogCancelled();
    if(!Array.isArray(page.files)||!Number.isInteger(page.total)||page.total<0||page.offset!==offset||page.next_offset!==offset+page.files.length||page.next_offset>page.total||page.truncated!==(page.next_offset<page.total)||!/^[a-f0-9]{64}$/i.test(page.index_sha256||''))throw Error('The file catalog returned an incomplete page. Refresh the files.');
    if(first&&(page.index_sha256!==first.index_sha256||page.total!==first.total||page.design_version!==first.design_version))throw Object.assign(Error('The file catalog changed while loading.'),{status:409});
    first??=page;
    for(const file of page.files){if(seen.has(file.path))throw Error('The file catalog repeated a path. Refresh the files.');seen.add(file.path);entries.push(file);}
    if(!page.truncated)return{...first,files:entries,offset:0,next_offset:page.total,truncated:false};
    if(page.next_offset<=offset)throw Error('The file catalog did not advance to the next page.');offset=page.next_offset;
   }
  }catch(error){if(error.status!==409||attempt===restarts)throw error;}
 }
}
