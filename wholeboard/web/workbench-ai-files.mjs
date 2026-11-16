import {esc} from './workbench-icons.mjs';
import {changeTable} from './workbench-ai-changes.mjs';

export class AIFilesUI{
 constructor({state,api,editable,busy,updated,onBusy,toast}){
  Object.assign(this,{state,api,editable,busy,updated,onBusy,toast});this.token=0;this.fileToken=0;
  this.dialog=document.createElement('dialog');this.dialog.id='aiFilesDialog';this.dialog.className='modal ai-files-dialog';
  this.dialog.setAttribute('aria-labelledby','aiFilesTitle');document.body.append(this.dialog);
  this.dialog.addEventListener('close',()=>{this.token++;this.fileToken++;this.context=null;});
 }
 close(){this.token++;this.fileToken++;this.context=null;if(this.dialog.open)this.dialog.close();}
 current(context){const s=this.state();return this.context===context&&this.token===context.token&&s.pid===context.pid&&s.projectLoadToken===context.load&&!s.openingProject&&this.dialog.open;}
 endpoint(context){return`/api/workbench/projects/${context.pid}/ai-changes/${context.requestId}`;}
 draftReason(){const s=this.state();if(s.dirty||s.saving||s.sourceSaving)return'Save the current design draft before restoring these changes.';if([...s.fileDrafts?.keys()||[]].some(key=>key.startsWith(s.pid+':')))return'Save or discard project file drafts before restoring these changes.';if(!this.editable())return'Editing access is required to restore these changes.';if(this.busy())return'Wait for the active run before restoring these changes.';return null;}
 async open(requestId){
  const s=this.state(),context={pid:s.pid,load:s.projectLoadToken,requestId,token:++this.token};this.context=context;this.fileToken++;
  this.dialog.innerHTML='<div class="modal-heading"><h2 id="aiFilesTitle">AI changes</h2><button class="icon-button" data-close-ai-files aria-label="Close AI changes">×</button></div><p class="modal-description">Loading saved changes…</p>';
  this.dialog.querySelector('[data-close-ai-files]').onclick=()=>this.close();if(!this.dialog.open)this.dialog.showModal();
  try{const data=await this.api(this.endpoint(context));if(!this.current(context))return;this.data=data;this.render(context);}
  catch(error){if(this.current(context)){this.dialog.querySelector('.modal-description').textContent=error.message;}}
 }
 render(context){
  const data=this.data,undo=data.status==='applied',designCount=data.design.field_change_count||0;
  this.dialog.innerHTML=`<div class="modal-heading"><div><h2 id="aiFilesTitle">AI changes</h2><p class="modal-description">${data.files.length} file${data.files.length===1?'':'s'}${designCount?` · ${designCount} design field${designCount===1?'':'s'}`:''} · ${undo?'Applied':'Undone'}</p></div><button class="icon-button" data-close-ai-files aria-label="Close AI changes">×</button></div><div id="aiFilesError" class="ai-files-message" role="status"></div><div class="ai-files-layout"><nav class="ai-files-list" aria-label="Changed files">${data.files.map(file=>`<button class="ai-file-choice" data-ai-change-file="${esc(file.path)}"><span>${esc(file.path)}</span><small>${file.before_sha256===null?'Added':file.after_sha256===null?'Deleted':'Modified'}</small></button>`).join('')}</nav><section class="ai-files-detail"><div class="ai-files-design">${designCount?`<details><summary>${designCount} saved design field${designCount===1?'':'s'}</summary>${changeTable(data.design)}</details>`:'<p class="modal-description">The circuit design is unchanged.</p>'}</div><div id="aiFileHeader"></div><pre id="aiFileDiff" class="ai-file-diff" aria-label="Saved file difference">Select a file to review.</pre></section></div><div class="modal-actions ai-files-actions"><span class="modal-description">${undo?'Restore the previous design and file contents. Newly created files will be removed.':'Reapply the saved design and file contents.'}</span><button class="secondary-button" id="aiFilesRefresh">Refresh</button><button class="primary-button" id="aiFilesRestore">${undo?'Undo all changes':'Redo all changes'}</button></div>`;
  this.dialog.querySelector('[data-close-ai-files]').onclick=()=>this.close();this.dialog.querySelector('#aiFilesRefresh').onclick=()=>this.open(context.requestId);
  for(const button of this.dialog.querySelectorAll('[data-ai-change-file]'))button.onclick=()=>this.file(context,button.dataset.aiChangeFile);
  this.dialog.querySelector('#aiFilesRestore').onclick=()=>this.restore(context);
  this.refreshAccess();if(data.files.length)this.file(context,data.files[0].path);
 }
 refreshAccess(){
  const button=this.dialog.querySelector('#aiFilesRestore');if(!button||!this.context)return;
  const reason=this.draftReason()||this.data.blocked_reason;
  button.disabled=!!this.pending||!!reason||!this.data.can_restore;
  if(!this.pending)this.dialog.querySelector('#aiFilesError').textContent=reason||'';
 }
 async file(context,path){
  const token=++this.fileToken;for(const button of this.dialog.querySelectorAll('[data-ai-change-file]'))button.setAttribute('aria-current',String(button.dataset.aiChangeFile===path));
  const body=this.dialog.querySelector('#aiFileDiff');body.textContent='Loading saved difference…';
  try{
   const data=await this.api(this.endpoint(context)+'/file?path='+encodeURIComponent(path));if(!this.current(context)||token!==this.fileToken)return;
   if(data.receipt_sha256!==this.data.receipt_sha256)throw Error('The saved changes were updated. Refresh this review before restoring.');
   this.dialog.querySelector('#aiFileHeader').innerHTML=`<h3>${esc(path)}</h3><div class="ai-file-snapshots">${data.before_url?`<a href="${esc(data.before_url)}" target="_blank" rel="noopener">Before · ${data.before_bytes} bytes</a>`:'<span>Before · File did not exist</span>'}${data.after_url?`<a href="${esc(data.after_url)}" target="_blank" rel="noopener">After · ${data.after_bytes} bytes</a>`:'<span>After · File removed</span>'}</div>${data.line_endings_changed?'<p class="modal-description">Line endings also changed. Undo restores the original bytes.</p>':''}${data.encoding_replaced?'<p class="modal-description">Some bytes cannot be displayed as UTF-8. Open the saved snapshots to inspect them.</p>':''}${data.truncated?'<p class="modal-description">This difference is truncated. Open the complete before and after snapshots above.</p>':''}`;
   body.innerHTML=data.diff?data.diff.split('\n').map(line=>`<span class="${line.startsWith('@@')?'diff-range':line.startsWith('+')&&!line.startsWith('+++')?'diff-added':line.startsWith('-')&&!line.startsWith('---')?'diff-removed':''}">${esc(line)||' '}</span>`).join(''):'<span>No line-content changes. See snapshot bytes and line endings above.</span>';
  }catch(error){if(this.current(context)&&token===this.fileToken){body.textContent=error.message;this.data.can_restore=false;this.refreshAccess();}}
 }
 async restore(context){
  if(!this.current(context)||this.pending)return;
  const reason=this.draftReason()||this.data.blocked_reason;if(reason||!this.data.can_restore){this.refreshAccess();return;}
  const s=this.state(),direction=this.data.status==='applied'?'undo':'redo',body={direction,base_version:s.version,receipt_sha256:this.data.receipt_sha256};
  this.pending=true;s.aiRestoring=true;this.onBusy();this.refreshAccess();
  try{
   const result=await this.api(this.endpoint(context)+'/restore',{method:'POST',body});
   if(!this.current(context))return;this.updated(context,result);this.toast(direction==='undo'?'AI changes undone.':'AI changes reapplied.');
   const data=await this.api(this.endpoint(context));if(this.current(context)){this.data=data;this.render(context);}
  }catch(error){if(this.current(context)){this.data.can_restore=false;this.data.blocked_reason=error.message;this.dialog.querySelector('#aiFilesError').textContent=error.message;}}
  finally{this.pending=false;this.state().aiRestoring=false;this.onBusy();this.refreshAccess();}
 }
}
