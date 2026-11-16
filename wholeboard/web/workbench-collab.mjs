import {esc, icon} from './workbench-icons.mjs';
import {renderMarkdown} from './workbench-markdown.mjs';

const $=selector=>document.querySelector(selector);
const $$=(selector,host=document)=>[...host.querySelectorAll(selector)];
const roles=[['viewer','Viewer'],['commenter','Commenter'],['editor','Editor']];
const roleOptions=selected=>roles.map(([value,label])=>`<option value="${value}" ${value===selected?'selected':''}>${label}</option>`).join('');
const roleName=role=>roles.find(r=>r[0]===role)?.[1]||'Owner';

export class CollaborationUI {
  constructor(services){Object.assign(this,services);this.comments=[];this.draft='';this.draftRevision=0;this.pendingComments=new Set();this.commentReadToken=0;this.replyDrafts=new Map();this.replyRevisions=new Map();this.filter='open';this.commentsContext=null;}
  actor(){const s=this.state();return s.session?.user?.id||s.project.access?.user?.id||'device';}
  commentOwner(){const s=this.state();return JSON.stringify([s.pid,s.projectLoadToken,this.actor()]);}
  contextChanged(){const owner=this.commentOwner();if(owner===this.commentsContext)return;this.commentsContext=owner;this.commentReadToken++;this.comments=[];this.commentsPid=null;this.commentsActor=null;this.commentsOwner=null;this.commentsPendingOwner=null;this.commentsPendingToken=null;this.commentFailureOwner=null;this.commentFailureText='';this.draft='';this.draftRevision++;this.replyDrafts.clear();this.replyRevisions.clear();this.replying=null;this.focusedThread=null;this.online=[];this.onlineOwner=null;const count=$('#commentCount');if(count){count.textContent='';count.hidden=true;}const avatars=$('#liveAvatars');if(avatars){avatars.hidden=true;avatars.innerHTML='';}this.state().canvas?.svg?.querySelectorAll('.review-pin,.live-cursors').forEach(e=>e.remove());const host=$('#commentsContent');if(host){if(host.contains(document.activeElement))document.activeElement.blur();host.innerHTML='<p class="drawer-description" role="status">Loading comments…</p>';}this.onContextChanged?.(owner);}
  async commentRequest(path,options={}){const controller=new AbortController(),external=options.signal,abort=()=>controller.abort(external.reason);let timedOut=false;if(external?.aborted)abort();else external?.addEventListener('abort',abort,{once:true});const timer=setTimeout(()=>{timedOut=true;controller.abort();},30000);try{return await this.api(path,{...options,signal:controller.signal});}catch(error){if(timedOut)throw Error('Comment request timed out. Check the thread before sending again.');throw error;}finally{clearTimeout(timer);external?.removeEventListener('abort',abort);}}
  safely(fn){return(...args)=>Promise.resolve().then(()=>fn(...args)).catch(e=>this.toast(e.message,true));}
  commentSafely(owner,fn){return(...args)=>Promise.resolve().then(()=>this.commentOwner()===owner?fn(...args):undefined).catch(error=>{if(this.commentOwner()===owner)this.toast(error.message,true);});}
  async bootstrap(){
    if(location.hash.startsWith('#share=')){
      const token=location.hash.slice(7);
      history.replaceState(null,'',location.pathname+location.search);
      try{const result=await this.api('/api/workbench/session/share',{method:'POST',body:{token}});history.replaceState(null,'',`#${result.project_id}`);}
      catch(error){this.showLogin(error.message);return false;}
    }
    const state=this.state();state.session=await this.api('/api/workbench/session');
    if(!state.session.authenticated){this.showLogin();return false;}
    return true;
  }
  init(){
    $('#workspaceAccountsButton').onclick=this.safely(()=>{$('#settingsDialog').close();return this.openWorkspace();});
    $('#workspaceSignOut').onclick=this.safely(async()=>{await this.api('/api/workbench/session/logout',{method:'POST'});location.reload();});
    $('#workspaceSignIn').onclick=()=>{$('#workspaceDialog').close();this.showLogin();};
    $('#workspaceLoginForm').onsubmit=async event=>{
      event.preventDefault();const button=event.target.querySelector('button[type=submit]');button.disabled=true;
      try{await this.api('/api/workbench/session/login',{method:'POST',body:{username:$('#loginUsername').value,password:$('#loginPassword').value}});$('#loginPassword').value='';location.reload();}
      catch(error){$('#workspaceLoginError').textContent=error.message;}
      finally{button.disabled=false;}
    };
    $('#workspaceLoginDialog').addEventListener('cancel',event=>{if(!this.state().session?.authenticated)event.preventDefault();});
    $('#createAccountForm').onsubmit=this.safely(async event=>{
      event.preventDefault();const button=event.target.querySelector('button[type=submit]');button.disabled=true;
      try{await this.api('/api/workbench/accounts',{method:'POST',body:{username:$('#accountUsername').value,display_name:$('#accountDisplayName').value,password:$('#accountPassword').value}});event.target.reset();await this.loadAccounts();this.toast('Workspace account created');}
      finally{button.disabled=false;}
    });
    $('#addMemberForm').onsubmit=this.safely(async event=>{event.preventDefault();await this.api(`${this.projectUrl()}/members/${$('#memberAccount').value}`,{method:'PUT',body:{role:$('#memberRole').value}});await this.loadAccess();this.toast('Project access updated');});
    $('#createShareForm').onsubmit=this.safely(async event=>{
      event.preventDefault();const button=event.target.querySelector('button[type=submit]');button.disabled=true;
      try{const link=await this.api(`${this.projectUrl()}/shares`,{method:'POST',body:{label:$('#shareLabel').value,role:$('#shareRole').value,days:Number($('#shareDays').value)}});$('#shareUrl').value=location.origin+link.path;$('#copyLink').disabled=false;await this.loadAccess();this.toast('Access link created');}
      finally{button.disabled=false;}
    });
  }
  projectUrl(){return`/api/workbench/projects/${this.state().pid}`;}
  showLogin(message=''){$('#workspaceLoginError').textContent=message;this.dialog('#workspaceLoginDialog');$('#loginUsername').focus();}
  async openWorkspace(){
    const session=this.state().session||{};
    $('#signedInUser').textContent=session.user?.name||'Workspace owner';$('#accountManagement').hidden=!session.admin;
    $('#workspaceSignOut').hidden=session.mode==='device';this.dialog('#workspaceDialog');
    if(session.admin)await this.loadAccounts();
  }
  async loadAccounts(){
    const data=await this.api('/api/workbench/accounts');
    $('#workspaceAccounts').innerHTML=data.accounts.map(user=>`<div class="access-person"><span class="member-avatar">${esc(user.name[0]||'?')}</span><span><strong>${esc(user.name)}</strong><small>${esc(user.username)}${user.disabled?' · Disabled':''}</small></span><button class="secondary-button" data-toggle-account="${esc(user.id)}" data-disabled="${user.disabled?'1':'0'}">${user.disabled?'Enable':'Disable'}</button></div>`).join('')||'<p class="small muted">No accounts yet.</p>';
    $$('[data-toggle-account]').forEach(button=>button.onclick=this.safely(async()=>{await this.api(`/api/workbench/accounts/${button.dataset.toggleAccount}`,{method:'PATCH',body:{disabled:button.dataset.disabled!=='1'}});await this.loadAccounts();}));
  }
  async openShare(){
    await this.save();const state=this.state(),access=state.project.access;
    $('#projectAccessDescription').textContent=access?.can_manage===false?`You have ${roleName(access.role).toLowerCase()} access to this project.`:'Manage people and links for this project.';
    $('#projectAccessManagement').hidden=access?.can_manage===false;
    $('#shareUrl').value='';$('#copyLink').disabled=true;
    this.dialog('#shareDialog');if(access?.can_manage!==false)await this.loadAccess();
  }
  async loadAccess(){
    const [people,links,users]=await Promise.all([this.api(this.projectUrl()+'/members'),this.api(this.projectUrl()+'/shares'),this.api('/api/workbench/accounts')]);
    $('#projectMembers').innerHTML=`<div class="access-person"><span class="member-avatar">P</span><span><strong>Project owner</strong><small>Full project access</small></span><span class="member-role">Owner</span></div>`+people.members.map(user=>`<div class="access-person"><span class="member-avatar">${esc(user.name[0]||'?')}</span><span><strong>${esc(user.name)}</strong><small>${esc(user.username)}${user.disabled?' · Disabled':''}</small></span><select data-member-role="${esc(user.id)}" aria-label="Permission for ${esc(user.name)}">${roleOptions(user.role)}</select><button class="icon-button" data-remove-member="${esc(user.id)}" aria-label="Remove ${esc(user.name)}">×</button></div>`).join('');
    const available=users.accounts.filter(user=>!user.disabled&&!people.members.some(m=>m.id===user.id)&&user.id!==people.owner_id);
    $('#memberAccount').innerHTML=available.map(user=>`<option value="${esc(user.id)}">${esc(user.name)} (${esc(user.username)})</option>`).join('');
    $('#addMemberForm').hidden=!available.length;$('#noWorkspaceAccounts').hidden=!!available.length||!!people.members.length;
    $('#projectShares').innerHTML=links.shares.filter(link=>!link.revoked).map(link=>`<div class="access-person"><span class="member-avatar">${icon('link')}</span><span><strong>${esc(link.label)}</strong><small>${esc(roleName(link.role))} · ${link.expires*1000<Date.now()?'Expired':`Expires ${esc(new Date(link.expires*1000).toLocaleDateString())}`}</small></span><button class="secondary-button" data-revoke-share="${esc(link.id)}">Revoke</button></div>`).join('')||'<p class="small muted">No access links.</p>';
    $$('[data-member-role]').forEach(input=>input.onchange=this.safely(async()=>{await this.api(`${this.projectUrl()}/members/${input.dataset.memberRole}`,{method:'PUT',body:{role:input.value}});this.toast('Permission updated');}));
    $$('[data-remove-member]').forEach(button=>button.onclick=this.safely(async()=>{await this.api(`${this.projectUrl()}/members/${button.dataset.removeMember}`,{method:'DELETE'});await this.loadAccess();}));
    $$('[data-revoke-share]').forEach(button=>button.onclick=this.safely(async()=>{await this.api(`${this.projectUrl()}/shares/${button.dataset.revokeShare}`,{method:'DELETE'});await this.loadAccess();this.toast('Access link revoked');}));
  }
  async loadComments(){
    this.contextChanged();const pid=this.state().pid,owner=this.commentOwner(),actor=this.actor(),token=++this.commentReadToken;if(!pid)return;
    const current=()=>this.commentOwner()===owner&&token===this.commentReadToken;let data;this.commentsPendingOwner=owner;this.commentsPendingToken=token;this.commentFailureOwner=null;this.commentFailureText='';
    try{data=await this.commentRequest(`/api/workbench/projects/${pid}/comments`);}catch(error){if(current()){this.commentFailureOwner=owner;this.commentFailureText=String(error.message||error).slice(0,400);if($('#commentsContent')?.isConnected)this.renderComments();throw error;}return;}finally{if(this.commentsPendingToken===token){this.commentsPendingOwner=null;this.commentsPendingToken=null;}}if(!current())return;
    this.comments=data.comments;this.commentsPid=pid;this.commentsActor=actor;this.commentsOwner=owner;
    const count=data.comments.filter(c=>!c.parent_id&&!c.resolved).length;
    $('#commentCount').textContent=count;$('#commentCount').hidden=!count;
    this.markers(this.state().canvas);
    if($('#commentsContent')?.isConnected)this.renderComments();
  }
  renderComments(){
    this.contextChanged();
    const state=this.state(),host=$('#commentsContent');if(!host)return;
    if(this.commentsOwner!==this.commentOwner()){const owner=this.commentOwner(),failed=this.commentFailureOwner===owner;host.innerHTML=failed?`<p class="drawer-description" role="alert">${esc(this.commentFailureText)}</p><button type="button" class="secondary-button" data-comment-retry>Retry comments</button>`:'<p class="drawer-description" role="status">Loading comments…</p>';host.querySelector('[data-comment-retry]')?.addEventListener('click',()=>{if(this.commentOwner()!==owner)return;this.loadComments().catch(error=>{if(this.commentOwner()===owner)this.toast(error.message,true);});});return;}
    const owner=this.commentOwner(),current=()=>this.commentOwner()===owner,url=`/api/workbench/projects/${state.pid}/comments`,active=document.activeElement;
    const focus=host.contains(active)&&active.matches('textarea')?{thread:active.closest('[data-reply-form]')?.dataset.replyForm||'',start:active.selectionStart,end:active.selectionEnd,scroll:active.scrollTop}:null;
    const access=state.project.access||{can_comment:true,can_edit:true,can_manage:true,user:state.session?.user};
    const canComment=access.can_comment,me=access.user?.id||state.session?.user?.id;
    const threads=this.comments.filter(c=>!c.parent_id&&(this.filter==='all'||(this.filter==='resolved')===c.resolved));
    const message=comment=>`<div class="review-message" data-comment="${esc(comment.id)}"><div class="review-byline"><span class="member-avatar">${esc(comment.author_name[0]||'?')}</span><strong>${esc(comment.author_name)}</strong><time title="${esc(new Date(comment.created*1000).toLocaleString())}">${esc(new Date(comment.created*1000).toLocaleDateString())}</time></div><div class="markdown">${renderMarkdown(comment.text)}</div>${canComment&&(comment.author_id===me||access.can_manage)?`<div class="review-message-actions">${comment.author_id===me?`<button data-edit-comment="${esc(comment.id)}">Edit</button>`:''}<button data-delete-comment="${esc(comment.id)}">Delete</button></div>`:''}</div>`;
    host.innerHTML=`<div class="review-toolbar"><select id="commentFilter" aria-label="Filter comments"><option value="open" ${this.filter==='open'?'selected':''}>Open threads</option><option value="resolved" ${this.filter==='resolved'?'selected':''}>Resolved</option><option value="all" ${this.filter==='all'?'selected':''}>All comments</option></select></div><div class="review-threads">${threads.map(thread=>`<article class="review-thread${thread.resolved?' resolved':''}" data-thread="${esc(thread.id)}">${Object.keys(thread.anchor).length?`<button class="review-anchor" data-comment-anchor="${esc(thread.id)}">${icon('navigation')}${esc(thread.anchor.ref||thread.anchor.net||'Project')} <span>${esc(thread.anchor.view||'')}</span></button>`:''}${message(thread)}${this.comments.filter(c=>c.parent_id===thread.id).map(message).join('')}<div class="review-thread-actions">${canComment?`<button data-reply-thread="${esc(thread.id)}">Reply</button>`:''}${canComment&&(thread.author_id===me||access.can_edit)?`<button data-resolve-thread="${esc(thread.id)}">${icon(thread.resolved?'history':'check')}${thread.resolved?'Reopen':'Resolve'}</button>`:''}</div>${this.replying===thread.id?`<form data-reply-form="${esc(thread.id)}"><textarea aria-label="Reply to thread" required maxlength="20000">${esc(this.replyDrafts.get(thread.id)||'')}</textarea><button class="secondary-button" type="submit">Reply</button></form>`:''}</article>`).join('')||'<p class="drawer-description">No comments in this view.</p>'}</div>${canComment?`<form id="newCommentForm" class="new-comment"><label id="newCommentAnchor">${state.selected?`Comment on ${esc(state.selected)}`:state.selectedNet?`Comment on ${esc(state.selectedNet)}`:'Project comment'}</label><textarea id="newCommentText" aria-label="New comment" placeholder="Leave a comment…" required maxlength="20000">${esc(this.draft)}</textarea><button class="primary-button" type="submit">Comment</button></form>`:'<p class="file-help">Your project role allows viewing comments.</p>'}`;
    $('#commentFilter').onchange=event=>{if(!current())return;this.filter=event.target.value;this.renderComments();};
    if(canComment){
      const form=$('#newCommentForm'),button=form.querySelector('button[type=submit]');button.disabled=this.pendingComments.has(owner);button.textContent=button.disabled?'Posting…':'Comment';
      $('#newCommentText').oninput=event=>{if(!current())return;this.draft=event.target.value;this.draftRevision++;};
      form.onsubmit=event=>{event.preventDefault();if(!current()||this.pendingComments.has(owner))return;const text=this.draft,revision=this.draftRevision,s=this.state(),anchor={view:s.active,...(s.selected?{ref:s.selected}:s.selectedNet?{net:s.selectedNet}:{})};this.pendingComments.add(owner);button.disabled=true;button.textContent='Posting…';
        (async()=>{try{await this.commentRequest(url,{method:'POST',body:{text,anchor}});if(!current())return;if(this.draftRevision===revision)this.draft='';await this.loadComments();}catch(error){if(current())this.toast(error.message,true);}finally{this.pendingComments.delete(owner);if(current())this.renderComments();}})();};
    }
    $$('[data-comment-anchor]',host).forEach(button=>button.onclick=()=>this.selectAnchor(this.comments.find(c=>c.id===button.dataset.commentAnchor).anchor));
    $$('[data-reply-thread]',host).forEach(button=>button.onclick=()=>{this.replying=button.dataset.replyThread;this.renderComments();$('[data-reply-form] textarea').focus();});
    $$('[data-reply-form]',host).forEach(form=>{const id=form.dataset.replyForm,key=owner+'|reply:'+id,button=form.querySelector('button[type=submit]');button.disabled=this.pendingComments.has(key);button.textContent=button.disabled?'Posting…':'Reply';form.querySelector('textarea').oninput=event=>{if(current()){this.replyDrafts.set(id,event.target.value);this.replyRevisions.set(id,(this.replyRevisions.get(id)||0)+1);}};form.onsubmit=event=>{event.preventDefault();if(!current()||this.pendingComments.has(key))return;const text=this.replyDrafts.get(id),revision=this.replyRevisions.get(id)||0;this.pendingComments.add(key);button.disabled=true;button.textContent='Posting…';this.commentSafely(owner,async()=>{await this.commentRequest(url,{method:'POST',body:{text,parent_id:id}});if(!current())return;if((this.replyRevisions.get(id)||0)===revision){this.replyDrafts.delete(id);this.replyRevisions.delete(id);if(this.replying===id)this.replying=null;}await this.loadComments();})().finally(()=>{this.pendingComments.delete(key);if(current())this.renderComments();});};});
    $$('[data-resolve-thread]',host).forEach(button=>button.onclick=this.commentSafely(owner,async()=>{const c=this.comments.find(c=>c.id===button.dataset.resolveThread);await this.commentRequest(`${url}/${c.id}`,{method:'PATCH',body:{resolved:!c.resolved}});if(current())await this.loadComments();}));
    $$('[data-edit-comment]',host).forEach(button=>button.onclick=this.commentSafely(owner,async()=>{const c=this.comments.find(c=>c.id===button.dataset.editComment),text=await this.askText('Edit comment','Comment',c.text);if(text===null||!current())return;await this.commentRequest(`${url}/${c.id}`,{method:'PATCH',body:{text}});if(current())await this.loadComments();}));
    $$('[data-delete-comment]',host).forEach(button=>button.onclick=this.commentSafely(owner,async()=>{await this.commentRequest(`${url}/${button.dataset.deleteComment}`,{method:'DELETE'});if(current())await this.loadComments();}));
    if(this.focusedThread){host.querySelector(`[data-thread="${CSS.escape(this.focusedThread)}"]`)?.scrollIntoView({block:'nearest'});this.focusedThread=null;}
    if(focus){const input=focus.thread?host.querySelector(`[data-reply-form="${CSS.escape(focus.thread)}"] textarea`):host.querySelector('#newCommentText');if(input){input.focus({preventScroll:true});input.setSelectionRange(focus.start,focus.end);input.scrollTop=focus.scroll;}}
  }
  markers(canvas){
    this.contextChanged();
    if(!canvas?.svg)return;
    $$('.review-pin',canvas.svg).forEach(pin=>pin.remove());
    if(this.commentsOwner!==this.commentOwner())return;
    const refs=new Map();
    for(const comment of this.comments.filter(c=>!c.parent_id&&!c.resolved&&c.anchor.ref&&c.anchor.view==='schematic')){const group=refs.get(comment.anchor.ref)||[];group.push(comment);refs.set(comment.anchor.ref,group);}
    for(const [ref,comments] of refs){
      for(const element of $$(`[data-ref="${CSS.escape(ref)}"]`,canvas.svg)){
        const box=element.getBBox(),pin=document.createElementNS('http://www.w3.org/2000/svg','g');
        pin.classList.add('review-pin');pin.setAttribute('transform',`translate(${box.x+box.width+6} ${box.y-5})`);pin.setAttribute('role','button');pin.setAttribute('tabindex','0');pin.setAttribute('aria-label',`${comments.length} comments on ${ref}`);
        pin.innerHTML=`<circle r="11" fill="#1dfdc0" stroke="#101010" stroke-width="2"/><text y="4" text-anchor="middle" font-family="Roboto" font-size="11" fill="#103a2b">${comments.length}</text>`;
        pin.addEventListener('pointerdown',event=>{event.stopPropagation();event.preventDefault();});
        const open=()=>{this.focusedThread=comments[0].id;this.filter='open';this.openComments();};
        pin.addEventListener('click',event=>{event.stopPropagation();open();});pin.addEventListener('keydown',event=>{if(event.key==='Enter'){event.stopPropagation();open();}});element.append(pin);
      }
    }
  }
  presence(event,owner=this.commentOwner()){
    this.contextChanged();if(owner!==this.commentOwner())return;this.onlineOwner=owner;
    this.online=(event.users||[]).filter(user=>user.id!==event.self);
    const host=$('#liveAvatars');host.hidden=!this.online.length;
    host.innerHTML=this.online.slice(0,5).map(user=>`<span class="live-avatar" style="--person-color:${esc(user.color)}" title="${esc(user.name)} · ${esc(user.view)}" aria-label="${esc(user.name)} online">${esc(user.name[0].toUpperCase())}</span>`).join('')+(this.online.length>5?`<span class="live-avatar live-more">+${this.online.length-5}</span>`:'');
    this.presenceMarkers(this.state().canvas);
  }
  presenceMarkers(canvas){
    this.contextChanged();const state=this.state(),people=(this.onlineOwner===this.commentOwner()?this.online||[]:[]).filter(user=>user.view===state.active&&(state.active!=='schematic'||user.sheet===(state.schematicSheet||'')));
    if(canvas?.geo){canvas.opts.presence=people;canvas.draw();return;}
    if(!canvas?.svg||state.active!=='schematic')return;
    canvas.svg.querySelector('.live-cursors')?.remove();
    const group=document.createElementNS('http://www.w3.org/2000/svg','g');group.classList.add('live-cursors');group.setAttribute('pointer-events','none');
    group.innerHTML=people.filter(user=>user.cursor).map(user=>`<g data-live-user="${esc(user.id)}" transform="translate(${user.cursor[0]} ${user.cursor[1]})"><path d="M0 0v20l5-6 7-1z" fill="${esc(user.color)}" stroke="#111" stroke-width="1.4"/><rect x="10" y="14" width="${Math.min(170,user.name.length*6.5+14)}" height="19" rx="3" fill="${esc(user.color)}"/><text x="16" y="27" font-size="10" font-family="Roboto" fill="#111">${esc(user.name)}</text></g>`).join('');
    for(const user of people.filter(user=>user.ref))for(const symbol of $$(`[data-ref="${CSS.escape(user.ref)}"]`,canvas.svg)){const box=symbol.getBBox();group.innerHTML+=`<rect x="${Number(symbol.dataset.x)+box.x-5}" y="${Number(symbol.dataset.y)+box.y-5}" width="${box.width+10}" height="${box.height+10}" rx="3" stroke="${esc(user.color)}" fill="none" stroke-width="1.3" stroke-dasharray="5 4"/>`;}
    canvas.scene.append(group);
  }
}
