import {esc,icon} from './workbench-icons.mjs';
import {appendPickedMate} from './workbench-cad-topology.mjs';

export class NativeMatePicker{
 constructor(parts){this.parts=parts;parts.picker=this;}
 get active(){return !!this.session;}
 ready(asset,part){const viewer=this.parts.viewer?.();return !!viewer?.setNativeSelection&&viewer.data.mechanical_asset_id===asset?.asset_id&&viewer.data.topology?.bodies.some(body=>body.member_id)&&asset?.asset_id===part?.asset_id&&!part?.stale;}
 valid(session){return this.session===session&&session.element.isConnected&&this.parts.historyIntentCurrent(session.context)&&this.parts.same(session.context,true)&&this.parts.viewer()===session.viewer&&this.parts.current()?.source===session.part.source&&this.parts.current()?.assetId===session.asset.asset_id;}
 async open(asset,part){
  const p=this.parts;if(!p.canWrite()||p.modal||p.openingParameters||this.active||this.opening)return;if(!this.ready(asset,part)){p.toast('Rebuild this assembly preview before choosing native references.',true);return;}
  const ticket={context:p.context(),viewer:p.viewer()};this.opening=ticket;p.onPickingChange?.(true);p.sync();
  try{
   const text=await p.api(`/api/workbench/projects/${ticket.context.pid}/text/${part.source.split('/').map(encodeURIComponent).join('/')}`);
   if(this.opening!==ticket||!p.historyIntentCurrent(ticket.context)||!p.same(ticket.context,true)||p.viewer()!==ticket.viewer||p.modal||!this.ready(asset,part))return;
   if(text.sha!==asset.source_sha256)throw Error('The assembly source changed. Rebuild its preview before choosing references.');
   const program=JSON.parse(text.content),assembly=program.features.find(f=>f.id===program.result&&f.op==='assembly'),members=asset.metrics.assembly.members,fixed=assembly.fixed||assembly.members.slice(0,1),moving=members.find(m=>!fixed.includes(m.id));if(!moving)throw Error('This assembly has no movable parts. Edit its fixed parts first.');
   const element=document.createElement('section');element.id='nativeMatePicker';element.className='native-mate-picker';element.setAttribute('aria-label','Mate parts');
   const options=selected=>members.map(m=>`<option value="${esc(m.id)}" ${m.id===selected?'selected':''}>${esc(m.label)}</option>`).join(''),reference=members.find(m=>m.id!==moving.id);
   element.innerHTML=`<header><h3>Mate parts</h3><button type="button" id="cancelNativeMate" class="icon-button" aria-label="Cancel mate">${icon('close')}</button></header><div class="native-mate-options"><label>Mate<select id="pickedMateType"><option value="coincident">Coincident</option><option value="concentric">Concentric</option><option value="aligned">Aligned</option><option value="offset">Offset</option></select></label><label>Pick<select id="matePickMode"><option value="face">Face</option><option value="edge">Edge</option></select></label></div><div class="native-reference-card" data-native-role="moving"><button type="button" data-pick-role="moving">Moving reference</button><select id="mateMovingPart" aria-label="Moving part">${options(moving.id)}</select><span id="mateMovingSelection">Pick a face</span></div><div class="native-reference-card" data-native-role="reference"><button type="button" data-pick-role="reference">Reference surface</button><select id="mateReferencePart" aria-label="Reference part">${options(reference.id)}</select><span id="mateReferenceSelection">Pick a face</span></div><div class="native-mate-options"><label>Offset (mm)<input type="number" id="mateOffset" value="1" step="any"></label><label class="native-mate-flip"><input type="checkbox" id="mateFlip" checked>Flip alignment</label></div><p id="nativeMateMessage" role="status">Pick the moving reference in the 3D view.</p><footer><button type="button" id="applyPickedMate" class="primary-button" disabled>Add mate</button></footer>`;
   const session={context:ticket.context,viewer:ticket.viewer,element,program,sha:text.sha,asset,part,members,role:'moving',picks:{moving:null,reference:null},undo:[],redo:[]};this.session=session;p.host.append(element);p.onPickingChange?.(true);
   element.querySelector('#cancelNativeMate').onclick=()=>this.close();element.querySelector('#applyPickedMate').onclick=()=>this.submit(session);
   for(const button of element.querySelectorAll('[data-pick-role]'))button.onclick=()=>{session.role=button.dataset.pickRole;this.activate(session);};
   for(const [role,id]of[['moving','mateMovingPart'],['reference','mateReferencePart']])element.querySelector('#'+id).onchange=()=>{session.picks[role]=null;session.role=role;this.activate(session);};
   element.querySelector('#matePickMode').onchange=()=>this.activate(session);element.querySelector('#pickedMateType').onchange=()=>{element.querySelector('#mateFlip').checked=element.querySelector('#pickedMateType').value==='coincident';this.sync();};
   for(const id of ['mateOffset','mateFlip'])element.querySelector('#'+id).oninput=()=>this.sync();
   session.keydown=event=>{if(!this.valid(session))return;if(event.key==='Escape'){event.preventDefault();event.stopImmediatePropagation();this.close();}else if((event.metaKey||event.ctrlKey)&&event.key.toLowerCase()==='z'&&!event.target.closest('input,textarea,select')){event.preventDefault();event.stopImmediatePropagation();this.restoreSelection(!!event.shiftKey);}};document.addEventListener('keydown',session.keydown,true);this.activate(session);
  }catch(error){if(this.opening===ticket&&p.same(ticket.context))p.toast(error.message,true);}
  finally{if(this.opening===ticket)this.opening=null;if(!this.opening&&!this.session)p.onPickingChange?.(false);p.sync();}
 }
 activate(session){
  if(!this.valid(session))return;const memberId=session.element.querySelector(session.role==='moving'?'#mateMovingPart':'#mateReferencePart').value,mode=session.element.querySelector('#matePickMode').value;
  for(const card of session.element.querySelectorAll('[data-native-role]'))card.classList.toggle('active',card.dataset.nativeRole===session.role);
  session.viewer.measureMode=false;session.viewer.measurePoints=[];session.viewer._measurement?.();document.querySelector('#measureResult')?.remove();
  session.viewer.setNativeSelection({memberId,mode,onPick:pick=>this.pick(session,pick),onHover:pick=>{if(this.valid(session)&&pick)session.element.querySelector('#nativeMateMessage').textContent=`${pick.label} · ${pick.entity==='face'?'Face':'Edge'} ${pick.index+1}`;}});this.sync();
 }
 pick(session,pick){
  if(!this.valid(session))return;if(!pick?.selector){this.message(session,'Choose a supported planar face, cylinder or edge.',true);return;}
  const id=session.element.querySelector(session.role==='moving'?'#mateMovingPart':'#mateReferencePart').value;if(pick.member_id!==id)return;
  session.undo.push({picks:structuredClone(session.picks),role:session.role});session.redo=[];session.picks[session.role]=pick;if(session.role==='moving')session.role='reference';this.activate(session);
 }
 restoreSelection(redo=false){const s=this.session;if(!s||!this.valid(s))return;const from=redo?s.redo:s.undo,to=redo?s.undo:s.redo;if(!from.length)return;to.push({picks:structuredClone(s.picks),role:s.role});Object.assign(s,from.pop());this.activate(s);}
 message(session,text,error=false){const node=session.element.querySelector('#nativeMateMessage');node.textContent=text;node.setAttribute('role',error?'alert':'status');}
 args(session){const el=session.element;return{type:el.querySelector('#pickedMateType').value,moving:session.picks.moving,reference:session.picks.reference,offset:Number(el.querySelector('#mateOffset').value),flip:el.querySelector('#mateFlip').checked};}
 sync(){
  const session=this.session;if(!session)return;if(!this.valid(session)||!this.parts.editable()||this.parts.busy()){this.close();return;}
  for(const [role,id]of[['moving','mateMovingSelection'],['reference','mateReferenceSelection']]){const pick=session.picks[role];session.element.querySelector('#'+id).textContent=pick?`${pick.entity==='face'?'Face':'Edge'} ${pick.index+1} · ${pick.selector.kind==='axis'?'Axis':pick.selector.kind}`:'Pick a reference';}
  let error='';try{appendPickedMate(session.program,this.args(session));}catch(value){error=value.message;}session.element.querySelector('#applyPickedMate').disabled=!!error;
  this.message(session,error||'Both references are ready. Add the mate to solve the assembly.',!!error&&!!session.picks.moving&&!!session.picks.reference);
 }
 onViewChange(){if(this.session&&!this.valid(this.session))this.close();if(this.opening&&!this.parts.historyIntentCurrent(this.opening.context)){this.opening=null;if(!this.session)this.parts.onPickingChange?.(false);}}
 close(){const session=this.session;this.session=null;if(session){document.removeEventListener('keydown',session.keydown,true);if(session.viewer.canvas?.isConnected)session.viewer.setNativeSelection(null);session.element.remove();this.parts.onPickingChange?.(false);}this.parts.sync();this.parts.flush();}
 async submit(session){
  if(!this.valid(session))return;let program;try{program=appendPickedMate(session.program,this.args(session));}catch(error){this.message(session,error.message,true);return;}
  this.close();try{await this.parts.build(session.context,{path:session.part.source,program,expected_sha256:session.sha,expected_asset_id:session.asset.asset_id});}catch(error){if(this.parts.same(session.context))this.parts.toast(error.message,true);}
 }
}
