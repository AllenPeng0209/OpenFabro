// Synchronous local snapshots protect the last keystroke during reload. Each page
// owns a separate record ID; foreign snapshots are retired by revision tombstones.
const id=()=>Array.from(globalThis.crypto.getRandomValues(new Uint8Array(16)),value=>value.toString(16).padStart(2,'0')).join('');
const validId=value=>typeof value==='string'&&/^[a-f0-9]{32}$/.test(value);
function validPath(path){return typeof path==='string'&&path.length<=512&&!path.startsWith('/')&&!path.split('/').some(p=>!p||p==='.'||p==='..'||p.startsWith('.'))&&!/^(native|history|mechanical)\//.test(path)&&!path.startsWith('references/canvas/')&&!['state.json','events.jsonl'].includes(path);}
export class DraftJournal{
 constructor({storage,onError=()=>{},now=()=>Date.now()}={}){this.writer=id();this.memory=new Map();this.dismissed=new Set();this.onError=onError;this.now=now;try{this.storage=storage??globalThis.localStorage;}catch(error){this.error(error);}}
 error(error){this.onError(error);}
 prefix(scope){if(typeof scope.owner!=='string'||!scope.owner||typeof scope.pid!=='string'||!scope.pid)throw Error('Choose a draft owner and project.');return'wb-file-draft:1:'+encodeURIComponent(scope.owner)+':'+encodeURIComponent(scope.pid)+':';}
 key(record){return this.prefix(record)+record.id;}
 marker(record){return this.prefix(record)+'dismiss:'+record.id+':'+record.rev;}
 put(scope,path,data,prior=null){
  if(!validPath(path))throw Error('This draft path is protected or invalid.');
  if(typeof data.content!=='string'||typeof data.base_content!=='string'||data.content.length>2_000_000||data.base_content.length>2_000_000)throw Error('Use a bounded text draft.');
  const own=prior?.writer===this.writer&&prior.owner===scope.owner&&prior.pid===scope.pid&&prior.path===path;
  const record={schema:1,owner:scope.owner,pid:scope.pid,path,id:own?prior.id:id(),writer:this.writer,rev:own?prior.rev+1:1,updated:this.now(),content:data.content,base_content:data.base_content,sha:data.sha??null,base_version:data.base_version??0};
  const key=this.key(record),previous=this.memory.get(key);if(previous)record.rev=Math.max(record.rev,previous.rev+1);
  this.memory.set(key,record);let persisted=false;
  try{if(!this.storage)throw Error('Browser storage is unavailable');this.storage.setItem(key,JSON.stringify(record));persisted=true;}catch(error){this.error(error);}
  const result={...record,persisted};this.memory.set(key,result);return result;
 }
 valid(record,scope,key){return record?.schema===1&&record.owner===scope.owner&&record.pid===scope.pid&&validPath(record.path)&&validId(record.id)&&validId(record.writer)&&Number.isSafeInteger(record.rev)&&record.rev>0&&Number.isFinite(record.updated)&&typeof record.content==='string'&&typeof record.base_content==='string'&&record.content.length<=2_000_000&&record.base_content.length<=2_000_000&&key===this.key(record)&&(record.sha===null||typeof record.sha==='string'&&/^[a-f0-9]{64}$/.test(record.sha))&&Number.isSafeInteger(record.base_version)&&record.base_version>=0;}
 list(scope){
  const prefix=this.prefix(scope),rows=new Map();
  try{for(let i=0;i<this.storage.length;i++){const key=this.storage.key(i);if(!key?.startsWith(prefix)||key.slice(prefix.length).startsWith('dismiss:'))continue;const raw=this.storage.getItem(key);if(!raw||raw.length>8_000_000)continue;let record;try{record=JSON.parse(raw);}catch{continue;}if(this.valid(record,scope,key))rows.set(key,record);}}catch(error){this.error(error);}
  for(const[key,record]of this.memory)if(key.startsWith(prefix))rows.set(key,record);
  const result=[];for(const record of rows.values()){
   let hidden=this.dismissed.has(this.marker(record));try{hidden||=!!this.storage?.getItem(this.marker(record));}catch(error){this.error(error);}
   if(!hidden&&record.content!==record.base_content)result.push(record);
  }
  return result.sort((a,b)=>b.updated-a.updated||a.id.localeCompare(b.id));
 }
 remove(record){
  if(record.writer!==this.writer)return false;const key=this.key(record);let current=this.memory.get(key);
  try{const raw=this.storage?.getItem(key);if(raw){const stored=JSON.parse(raw);if(!current||stored.rev>current.rev)current=stored;}}catch(error){this.error(error);}
  if(!current||current.rev!==record.rev)return false;
  try{this.storage?.removeItem(key);}catch(error){this.error(error);return false;}this.memory.delete(key);return true;
 }
 dismiss(record){
  const key=this.marker(record);this.dismissed.add(key);let persisted=false;
  try{if(!this.storage)throw Error('Browser storage is unavailable');this.storage.setItem(key,'1');persisted=true;}catch(error){this.error(error);}
  return persisted;
 }
}

const lines=text=>text.match(/[^\r\n]*(?:\r\n|\r|\n)|[^\r\n]+$/g)||[];
export function editorText(text,reference=''){
 const normalized=reference.replace(/\r\n|\r/g,'\n');if(text===normalized)return reference;
 const endings=reference.match(/\r\n|\r|\n/g)||[],counts=new Map();for(const e of endings)counts.set(e,(counts.get(e)||0)+1);
 const ending=[...counts].sort((a,b)=>b[1]-a[1])[0]?.[0]||'\n';
 if(counts.size<=1)return text.replace(/\n/g,ending);
 const original=lines(reference),a=lines(normalized),hunks=edits(a,lines(text),1_000_000).hunks;let out='',at=0;
 for(const h of hunks){out+=original.slice(at,h.start).join('')+h.lines.join('').replace(/\n/g,ending);at=h.end;}
 return out+original.slice(at).join('');
}
function edits(base,next,maxCells){
 let first=0,last=0;while(first<base.length&&first<next.length&&base[first]===next[first])first++;
 while(last<base.length-first&&last<next.length-first&&base[base.length-1-last]===next[next.length-1-last])last++;
 const a=base.slice(first,base.length-last),b=next.slice(first,next.length-last);if(!a.length&&!b.length)return{hunks:[],coarse:false};
 if((a.length+1)*(b.length+1)>maxCells)return{hunks:[{start:first,end:base.length-last,lines:b}],coarse:true};
 const dp=Array.from({length:a.length+1},()=>new Uint32Array(b.length+1));
 for(let i=a.length-1;i>=0;i--)for(let j=b.length-1;j>=0;j--)dp[i][j]=a[i]===b[j]?dp[i+1][j+1]+1:Math.max(dp[i+1][j],dp[i][j+1]);
 const hunks=[];let i=0,j=0,pending=null;
 const flush=()=>{if(pending){hunks.push(pending);pending=null;}};
 while(i<a.length||j<b.length){
  if(i<a.length&&j<b.length&&a[i]===b[j]){flush();i++;j++;continue;}
  pending??={start:first+i,end:first+i,lines:[]};
  if(j<b.length&&(i===a.length||dp[i][j+1]>=dp[i+1][j]))pending.lines.push(b[j++]);else{i++;pending.end=first+i;}
 }flush();return{hunks,coarse:false};
}
const overlap=(a,b)=>a.start===a.end?b.start===b.end?a.start===b.start:a.start>=b.start&&a.start<=b.end:b.start===b.end?b.start>=a.start&&b.start<=a.end:a.start<b.end&&b.start<a.end;
function applyRegion(base,start,end,hunks){let out='',at=start;for(const h of hunks.sort((a,b)=>a.start-b.start)){out+=base.slice(at,h.start).join('')+h.lines.join('');at=h.end;}return out+base.slice(at,end).join('');}
export function mergeText(base,local,remote,{maxCells=1_000_000}={}){
 if([base,local,remote].some(v=>typeof v!=='string'))throw Error('Three text versions are required.');
 const a=lines(base),left=edits(a,lines(local),maxCells),right=edits(a,lines(remote),maxCells),pending=[...left.hunks.map(h=>({...h,side:'local'})),...right.hunks.map(h=>({...h,side:'remote'}))].sort((a,b)=>a.start-b.start||a.end-b.end);
 const segments=[],conflicts=[];let at=0;
 while(pending.length){
  const group=[pending.shift()];let changed=true;
  while(changed){changed=false;for(let i=0;i<pending.length;i++)if(group.some(h=>overlap(h,pending[i]))){group.push(...pending.splice(i,1));changed=true;i--;}}
  const start=Math.min(...group.map(h=>h.start)),end=Math.max(...group.map(h=>h.end));if(start>at)segments.push({type:'text',text:a.slice(at,start).join('')});
  const l=group.filter(h=>h.side==='local'),r=group.filter(h=>h.side==='remote'),localText=applyRegion(a,start,end,l),remoteText=applyRegion(a,start,end,r);
  if(!l.length||!r.length||localText===remoteText)segments.push({type:'text',text:!l.length?remoteText:localText});
  else{const conflict={type:'conflict',id:'conflict-'+conflicts.length,line:start+1,base:a.slice(start,end).join(''),local:localText,remote:remoteText};segments.push(conflict);conflicts.push(conflict);}
  at=end;
 }
 if(at<a.length)segments.push({type:'text',text:a.slice(at).join('')});return{segments,conflicts,coarse:left.coarse||right.coarse};
}
export function resolveMerge(plan,choices={}){return plan.segments.map(segment=>{if(segment.type==='text')return segment.text;const choice=choices[segment.id];if(choice==='local')return segment.local;if(choice==='remote')return segment.remote;if(choice&&typeof choice.text==='string')return choice.text;throw Error('Choose a resolution for every draft conflict.');}).join('');}
