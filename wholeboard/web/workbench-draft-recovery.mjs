import {esc} from './workbench-icons.mjs';
import {DraftJournal,mergeText,resolveMerge,editorText} from './workbench-drafts.mjs';

export class FileDraftRecoveryUI{
 constructor({context,read,apply,active,discard,toast}){
  Object.assign(this,{context,read,apply,active,discard,toast});this.issue=null;this.warned=false;
  this.journal=new DraftJournal({onError:()=>{this.issue='Draft is only in this tab. Browser storage could not keep a recovery copy.';if(!this.warned){this.warned=true;this.toast(this.issue,true);}}});
  window.addEventListener('storage',event=>{if(event.key?.startsWith('wb-file-draft:1:'))this.update();});
 }
 scope(){const c=this.context();return{owner:c.owner,pid:c.pid};}
 valid(owner){const c=this.context();return c.files&&c.editable&&c.owner===owner.owner&&c.pid===owner.pid&&c.load===owner.load;}
 persist(path,draft){const record=this.journal.put(this.scope(),path,{content:draft.content,base_content:draft.base_content,sha:draft.sha,base_version:draft.base_version},draft.record);return{...draft,record};}
 saved(draft){if(draft?.record)this.journal.remove(draft.record);this.update();}
 close(){const session=this.modal;this.modal=null;if(session?.element.isConnected)session.element.close();}
 create(owner,title){
  this.close();const element=document.createElement('dialog');element.className='file-draft-dialog';element.id='fileDraftReviewDialog';element.innerHTML=`<header><h2>${esc(title)}</h2><button type="button" class="secondary-button" data-draft-close>Close</button></header><div class="file-draft-body" data-draft-body></div><footer data-draft-footer></footer>`;
  const session={owner,element,working:false};this.modal=session;document.body.append(element);element.showModal();element.querySelector('[data-draft-close]').onclick=()=>{if(!session.working)element.close();};
  element.addEventListener('cancel',e=>{if(session.working)e.preventDefault();});element.addEventListener('close',()=>{if(this.modal===session)this.modal=null;element.remove();});return session;
 }
 current(session){return this.modal===session&&session.element.isConnected&&this.valid(session.owner);}
 mount(){
  const host=document.querySelector('.file-viewer');if(!host)return;
  const banner=document.createElement('div');banner.id='fileDraftRecoveryBanner';banner.className='file-draft-recovery-banner';banner.hidden=true;banner.innerHTML='<span id="fileDraftRecoveryCount"></span><button type="button" class="secondary-button" id="reviewStoredDrafts">Review drafts</button>';host.prepend(banner);
  const issue=document.createElement('p');issue.id='fileDraftStorageStatus';issue.className='file-draft-storage-status';issue.hidden=true;issue.setAttribute('role','status');host.prepend(issue);
  document.querySelector('#reviewStoredDrafts').onclick=()=>this.openList();
  document.querySelector('#reviewFileDraft').onclick=()=>{const path=this.context().path,draft=this.active(path);if(draft?.record)this.review(draft.record);else this.openList(path);};this.update();
 }
 update(){
  const c=this.context(),banner=document.querySelector('#fileDraftRecoveryBanner'),button=document.querySelector('#reviewFileDraft');if(!banner||!c.pid)return;
  const rows=c.editable?this.journal.list(this.scope()):[],recoverable=rows.filter(row=>this.active(row.path)?.record?.id!==row.id),selected=rows.filter(row=>row.path===c.path);
  banner.hidden=!recoverable.length;document.querySelector('#fileDraftRecoveryCount').textContent=`${recoverable.length} local draft${recoverable.length===1?'':'s'} available`;
  if(button)button.hidden=!c.editable||!selected.length&&!this.active(c.path)?.record;
  const issue=document.querySelector('#fileDraftStorageStatus');issue.hidden=!this.issue||!rows.some(row=>row.persisted===false);issue.textContent=this.issue||'';
  if(this.modal&&!this.valid(this.modal.owner))this.close();
 }
 async openList(path=null){
  const owner=this.context();if(!owner.files||!owner.editable)return;const session=this.create(owner,'Local drafts');session.element.id='fileDraftListDialog';
  const paint=()=>{
   if(!this.current(session))return;const rows=this.journal.list(this.scope()).filter(r=>!path||r.path===path);session.element.querySelector('[data-draft-body]').innerHTML=`<p>Recovery copies are stored in this browser. Review a draft before putting it back in the editor.</p><div class="file-draft-list">${rows.map((row,i)=>`<article data-draft-path="${esc(row.path)}"><div><strong>${esc(row.path)}</strong><small>${esc(new Date(row.updated).toLocaleString())}</small></div><button type="button" class="secondary-button" data-review-draft="${i}">Review</button><button type="button" class="secondary-button" data-discard-draft="${i}">Discard</button></article>`).join('')||'<p>No local drafts.</p>'}</div>`;
   for(const button of session.element.querySelectorAll('[data-review-draft]'))button.onclick=()=>this.review(rows[Number(button.dataset.reviewDraft)]);
   for(const button of session.element.querySelectorAll('[data-discard-draft]'))button.onclick=()=>{const row=rows[Number(button.dataset.discardDraft)];this.journal.dismiss(row);this.discard(row);this.update();paint();};
  };paint();
 }
 async review(record){
  const owner=this.context();if(!this.valid(owner)||record.owner!==owner.owner||record.pid!==owner.pid)return;const session=this.create(owner,'Review local draft');session.record=record;session.choices={};
  session.element.querySelector('[data-draft-body]').textContent='Reading the current saved file…';
  try{session.remote=await this.read(record.path);if(!this.current(session))return;this.plan(session);this.paint(session);}
  catch(error){if(this.current(session)){session.element.querySelector('[data-draft-body]').innerHTML=`<p role="alert">${esc(error.message)}</p><p>The local draft is still available.</p>`;this.downloadButton(session);}}
 }
 plan(session){
  session.deleted=session.remote.exists===false;session.plan=mergeText(session.record.base_content,session.record.content,session.deleted?session.record.base_content:session.remote.content);session.choices={};
 }
 downloadButton(session){const button=document.createElement('button');button.type='button';button.className='secondary-button';button.textContent='Download draft';button.onclick=()=>this.download(session.record);session.element.querySelector('[data-draft-footer]').append(button);}
 download(record){const blob=new Blob([record.content],{type:'text/plain;charset=utf-8'}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=record.path.split('/').at(-1);a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
 paint(session){
  if(!this.current(session))return;const {record,remote,plan}=session,body=session.element.querySelector('[data-draft-body]'),footer=session.element.querySelector('[data-draft-footer]');
  body.innerHTML=`<p class="file-draft-path">${esc(record.path)}</p>${session.notice?`<p role="status">${esc(session.notice)}</p>`:''}<p>${session.deleted?'This file is missing. Saving the recovered draft will create it again.':plan.conflicts.length?`${plan.conflicts.length} conflict${plan.conflicts.length===1?'':'s'} to resolve.`:'Draft and saved edits can be combined.'}</p>${plan.coarse?'<p>Large edits are grouped for review. No text is truncated.</p>':''}<details class="file-draft-comparison"><summary>Compare full versions</summary><div class="file-draft-columns"><section><h3>Base</h3><pre>${esc(record.base_content)}</pre></section><section><h3>Draft</h3><pre>${esc(record.content)}</pre></section><section><h3>Saved</h3><pre>${esc(remote.content)}</pre></section></div></details>${session.deleted?'<label class="file-draft-recreate"><input type="checkbox" id="confirmDraftRecreate">Recover this deleted file to the editor</label>':''}${plan.conflicts.map(c=>`<section class="file-draft-conflict" data-draft-conflict="${c.id}" aria-label="Conflict at line ${c.line}"><h3>Conflict at line ${c.line}</h3><div class="file-draft-columns"><section><h4>Draft</h4><pre>${esc(c.local)}</pre></section><section><h4>Saved</h4><pre>${esc(c.remote)}</pre></section></div><div class="file-draft-choices">${[['local','Use draft'],['remote','Use saved'],['custom','Edit resolution']].map(([key,label])=>`<button type="button" class="secondary-button" data-draft-choice="${key}" data-conflict-id="${c.id}" aria-pressed="false">${label}</button>`).join('')}</div><textarea data-draft-custom="${c.id}" aria-label="Resolution at line ${c.line}" hidden>${esc(c.local)}</textarea></section>`).join('')}<details class="file-draft-preview"><summary>Recovered text</summary><pre id="fileDraftMergedPreview"></pre></details><p id="fileDraftReviewError" role="alert" hidden></p>`;
  footer.innerHTML='<span>Applying restores an unsaved editor buffer. Save file commits it.</span><button type="button" class="primary-button" id="applyRecoveredDraft">Apply to editor</button>';this.downloadButton(session);
  const update=()=>{
   if(!this.current(session))return;let content;
   try{content=session.deleted?record.content:resolveMerge(plan,session.choices);}catch{}
   session.content=content;session.element.querySelector('#fileDraftMergedPreview').textContent=content??'Choose a resolution for every conflict.';session.element.querySelector('#applyRecoveredDraft').disabled=session.working||content===undefined||session.deleted&&!session.element.querySelector('#confirmDraftRecreate').checked;
  };
  const customText=(key,value)=>{const local=plan.conflicts.find(c=>c.id===key).local;return editorText(value,/[\r\n]/.test(local)?local:record.content);};
  for(const button of body.querySelectorAll('[data-draft-choice]'))button.onclick=()=>{const key=button.dataset.conflictId,choice=button.dataset.draftChoice,custom=body.querySelector(`[data-draft-custom="${key}"]`);session.choices[key]=choice==='custom'?{text:customText(key,custom.value)}:choice;custom.hidden=choice!=='custom';for(const b of body.querySelectorAll(`[data-conflict-id="${key}"]`))b.setAttribute('aria-pressed',String(b===button));update();};
  for(const input of body.querySelectorAll('[data-draft-custom]'))input.oninput=()=>{session.choices[input.dataset.draftCustom]={text:customText(input.dataset.draftCustom,input.value)};update();};body.querySelector('#confirmDraftRecreate')?.addEventListener('change',update);
  session.element.querySelector('#applyRecoveredDraft').onclick=async()=>{
   if(!this.current(session)||session.content===undefined||session.working)return;session.working=true;update();
   try{
    const newest=this.journal.list(this.scope()).find(row=>row.id===record.id);if(newest&&newest.rev!==record.rev){session.record=newest;session.notice='The draft changed in another tab. Review its latest version.';session.remote=await this.read(record.path);if(this.current(session)){this.plan(session);session.working=false;this.paint(session);}return;}
    const saved=await this.read(record.path);if(!this.current(session))return;
    if(saved.content!==remote.content||saved.sha!==remote.sha||saved.base_version!==remote.base_version||saved.exists!==remote.exists){session.remote=saved;session.notice='The saved file changed again. Review the updated comparison.';this.plan(session);session.working=false;this.paint(session);return;}
    const draft=await this.apply(record,saved,session.content,session.owner);if(!this.current(session))return;
    if(draft?.record?.persisted)this.journal.dismiss(record);session.working=false;session.element.close();this.update();
   }catch(error){if(this.current(session)){const target=session.element.querySelector('#fileDraftReviewError');target.hidden=false;target.textContent=error.message;}}
   finally{if(this.current(session)){session.working=false;update();}}
  };update();
 }
}
