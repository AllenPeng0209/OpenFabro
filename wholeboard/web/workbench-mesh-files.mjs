const model=/\.(step|stp|stpz|iges|igs|brep|stl|obj|glb|gltf|dxf|svg)$/i;
export const isModelFile=file=>model.test(file.name);
const pathOf=file=>file.webkitRelativePath||file.relativePath||file.name;
const base64=bytes=>{let text='';for(let i=0;i<bytes.length;i+=32768)text+=String.fromCharCode(...bytes.subarray(i,i+32768));return btoa(text);};
export const fileData=async file=>base64(new Uint8Array(await file.arrayBuffer()));

function relative(uri,entry){
 if(/^[a-z][a-z0-9+.-]*:|^\/|[\\\0?#]/i.test(uri))throw Error('Use a relative resource inside the uploaded folder.');
 let decoded;try{decoded=decodeURIComponent(uri);}catch{throw Error('Invalid encoded mesh resource path.');}
 const parts=entry.split('/').slice(0,-1);for(const part of decoded.split('/')){if(!part||part==='.')continue;if(part==='..'){if(!parts.length)throw Error('Mesh resource is outside the uploaded folder.');parts.pop();}else parts.push(part);}
 if(!parts.length)throw Error('Invalid mesh resource path.');return parts.join('/');
}

function words(line){return(line.match(/"[^"]*"|'[^']*'|[^\s]+/g)||[]).map(word=>word.replace(/^["']|["']$/g,''));}

export async function meshResources(root,files){
 const entry_path=pathOf(root),byPath=new Map(files.map(file=>[pathOf(file),file])),resources={},visited=new Set();
 if(byPath.size!==files.length)throw Error('Some uploaded files have duplicate paths. Choose the folder to keep their structure.');
 const take=async(uri,entry,kind)=>{
  if(uri.startsWith('data:'))return;
  const path=relative(uri,entry);if(visited.has(path))return;const file=byPath.get(path);if(!file)throw Error('Missing mesh resource: '+path);
  if(file===root)throw Error('A mesh resource refers to the model itself.');if(resources[path]||visited.size>=128)throw Error('Too many mesh resources.');visited.add(path);
  if(file.size>20_000_000)throw Error('A mesh resource exceeds 20 MB.');resources[path]=await fileData(file);
  if(kind==='mtl'){const text=await file.text();for(const line of text.split(/\r?\n/)){const parts=words(line);if(parts.length&&/^(map_kd|map_ka|map_ks|map_d|map_bump|bump|norm)$/i.test(parts[0]))await take(parts.at(-1),path,'image');}}
 };
 if(/\.obj$/i.test(root.name)){
  for(const line of (await root.text()).split(/\r?\n/)){const parts=words(line);if(parts[0]==='mtllib')for(const uri of parts.slice(1))await take(uri,entry_path,'mtl');}
 }else if(/\.(gltf|glb)$/i.test(root.name)){
  let tree;if(/\.glb$/i.test(root.name)){const bytes=await root.arrayBuffer(),view=new DataView(bytes);if(bytes.byteLength<20||view.getUint32(0,true)!==0x46546c67||view.getUint32(4,true)!==2)throw Error('Use a valid glTF 2 GLB file.');const size=view.getUint32(12,true);if(20+size>bytes.byteLength||view.getUint32(16,true)!==0x4e4f534a)throw Error('Invalid GLB JSON chunk.');tree=JSON.parse(new TextDecoder().decode(new Uint8Array(bytes,20,size)));}
  else tree=JSON.parse(await root.text());
  for(const item of [...(tree.buffers||[]),...(tree.images||[])])if(item.uri)await take(item.uri,entry_path,'resource');
 }
 return{entry_path,resources};
}

export async function droppedFiles(transfer){
 const result=[];
 const walk=async(entry,prefix='',depth=0)=>{
  if(depth>16||result.length>=256)throw Error('Choose a smaller model folder.');
  if(entry.isFile){const file=await new Promise((resolve,reject)=>entry.file(resolve,reject));Object.defineProperty(file,'relativePath',{value:prefix+file.name});result.push(file);}
  else if(entry.isDirectory){const reader=entry.createReader();while(true){const batch=await new Promise((resolve,reject)=>reader.readEntries(resolve,reject));if(!batch.length)break;for(const child of batch)await walk(child,prefix+entry.name+'/',depth+1);}}
 };
 const entries=[...(transfer.items||[])].map(item=>item.webkitGetAsEntry?.()).filter(Boolean);
 if(entries.length){for(const entry of entries)await walk(entry);return result;}
 return[...transfer.files];
}
