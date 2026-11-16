import {esc} from './workbench-icons.mjs';

export function planOwnChanges({pid,from,to,owned,changes=[],fileChanges={}}){
 if(!Number.isSafeInteger(from)||!Number.isSafeInteger(to)||to<=from)return{eligible:false,reason:'range',groups:[]};
 const rows=changes.filter(row=>row.version>from&&row.version<=to).sort((a,b)=>a.version-b.version),groups=[];
 if(rows.length!==to-from)return{eligible:false,reason:'missing',groups:[]};
 for(let index=0;index<rows.length;index++){
  const row=rows[index],version=from+index+1,owner=owned.get(row.request_id);
  if(row.version!==version||row.from_version!==version-1||owner?.pid!==pid)return{eligible:false,reason:'foreign',groups:[]};
  if(row.files_changed?.length||fileChanges[row.request_id]?.length)return{eligible:false,reason:'files',groups:[]};
  const last=groups.at(-1);if(last?.request_id===row.request_id)last.version=version;else groups.push({...row});
 }
 return{eligible:true,groups};
}

export function changeLabel(path,spec={}){
 const parts=path.split('/').slice(1).map(value=>value.replaceAll('~1','/').replaceAll('~0','~'));
 if(parts[0]==='editor'&&parts[1]==='positions')return`${parts[2]} · Schematic ${parts[3]==='0'?'X':'Y'} (editor units)`;
 if(parts[0]==='components'){
  const ref=spec.components?.[Number(parts[1])]?.ref||`Component ${Number(parts[1])+1}`;
  if(parts[2]==='placement')return`${ref} · PCB ${parts[3]?.replace('_mm','').toUpperCase()}${parts[3]?.endsWith('_mm')?' (mm)':''}`;
  return`${ref} · ${parts.slice(2).join(' / ')||'Component'}`;
 }
 if(parts[0]==='board')return`Board · ${{width_mm:'Width (mm)',height_mm:'Height (mm)',layers:'Layers',thickness_mm:'Thickness (mm)'}[parts[1]]||parts.slice(1).join(' / ')}`;
 return parts.map(value=>value.replaceAll('_',' ')).join(' · ')||'Design';
}

export function changeTable(comparison,before={},after={}){
 let shortened=false;const value=(item,key)=>{if(!(key in item))return'—';const text=JSON.stringify(item[key]);if(text.length>600){shortened=true;return text.slice(0,600)+' … [truncated]';}return text;};
 const rows=(comparison.field_changes||[]).map(item=>`<tr><th title="${esc(item.path)}">${esc(changeLabel(item.path,item.kind==='added'?after:before))}</th><td>${esc(value(item,'before'))}</td><td>${esc(value(item,'after'))}</td></tr>`).join('');
 return`<table class="history-diff-table"><thead><tr><th>Design item</th><th>Before</th><th>After</th></tr></thead><tbody>${rows}</tbody></table>${comparison.field_changes_truncated||shortened?'<p class="modal-description">Some changes or long values are truncated. Review the complete saved designs before restoring.</p>':''}`;
}

export class AIChangeHistory{
 constructor({state,api}){this.state=state;this.api=api;this.owned=new Map();this.projects=new Map();this.batches=new Map();this.seenMixedFiles=new Map();}
 register(requestId,pid){if(!requestId||!pid)return;this.owned.set(requestId,{pid});while(this.owned.size>256)this.owned.delete(this.owned.keys().next().value);}
 remember(){const s=this.state();if(s.pid&&!s.dirty&&!s.saving){this.projects.delete(s.pid);this.projects.set(s.pid,{version:s.version,spec:structuredClone(s.spec),undo:structuredClone(s.undo),redo:structuredClone(s.redo)});while(this.projects.size>8){const id=this.projects.keys().next().value;this.projects.delete(id);this.batches.delete(id);}}}
 async prepare(pid,incoming,base=null){
  const s=this.state(),stored=base||(s.pid===pid?{version:s.version,spec:s.spec,undo:s.undo,redo:s.redo}:this.projects.get(pid)),to=incoming.workbench?.version||0;
  const mixedSeen=this.newMixedFiles(pid,incoming);
  if(!stored||mixedSeen.length)return{undo:[],redo:[],batch:null,mixedSeen,reason:mixedSeen.length?'files':undefined};
  if(stored.version===to)return JSON.stringify(stored.spec)===JSON.stringify(incoming.spec)?{undo:structuredClone(stored.undo),redo:structuredClone(stored.redo),batch:this.batches.get(pid)||null}:{undo:[],redo:[],batch:null};
  const plan=planOwnChanges({pid,from:stored.version,to,owned:this.owned,changes:incoming.ai_design_changes,fileChanges:incoming.ai_file_changes});
  if(!plan.eligible)return{undo:[],redo:[],batch:null,reason:plan.reason};
  const undo=structuredClone(stored.undo);let batch=this.batches.get(pid)||null;
  for(const group of plan.groups){
   if(!(batch?.request_id===group.request_id&&batch.version===group.from_version)){
    let snapshot;try{snapshot=await this.api(`/api/workbench/projects/${pid}/history/${group.from_version}`);}catch{return{undo:[],redo:[],batch:null,reason:'snapshot'};}
    if(snapshot.version!==group.from_version||!snapshot.spec||typeof snapshot.spec!=='object'||group.previous_snapshot_sha256&&snapshot.snapshot_sha256!==group.previous_snapshot_sha256)return{undo:[],redo:[],batch:null,reason:'snapshot'};
    undo.push(structuredClone(snapshot.spec));if(undo.length>60)undo.shift();
   }
   batch={request_id:group.request_id,from_version:batch?.request_id===group.request_id?batch.from_version:group.from_version,version:group.version};
  }
  return{undo,redo:[],batch};
 }
 newMixedFiles(pid,incoming){const seen=this.seenMixedFiles.get(pid)||new Set();return[...new Set((incoming.ai_design_changes||[]).map(row=>row.request_id).filter(id=>this.owned.get(id)?.pid===pid&&incoming.ai_file_changes?.[id]?.length&&!seen.has(id)))];}
 commit(pid,result){if(result.batch)this.batches.set(pid,result.batch);else this.batches.delete(pid);if(result.mixedSeen?.length){const seen=this.seenMixedFiles.get(pid)||new Set();for(const id of result.mixedSeen)seen.add(id);this.seenMixedFiles.set(pid,seen);}}
 invalidateFiles(incoming){const s=this.state(),mixedSeen=this.newMixedFiles(s.pid,incoming);if(mixedSeen.length){s.undo=[];s.redo=[];this.commit(s.pid,{batch:null,mixedSeen});return true;}return false;}
}
