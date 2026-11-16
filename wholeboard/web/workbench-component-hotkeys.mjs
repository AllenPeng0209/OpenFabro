import {copySelection,pasteSelection,ensureTerminalNets} from './workbench-model.mjs';
import {nativeSymbol} from './workbench-symbol.mjs';
import {esc} from './workbench-icons.mjs';

const SCHEMA='openfabro.component-hotkey.v1',LIMIT=2_000_000;
const point=p=>Array.isArray(p)&&p.length===2&&p.every(v=>Number.isFinite(v)&&Math.abs(v)<=1e6);
const validSlot=n=>Number.isInteger(Number(n))&&Number(n)>=1&&Number(n)<=5;
function validate(template){
 const clip=template?.clipboard,c=clip?.components?.[0];
 if(template?.schema!==SCHEMA||clip?.schema!=='wholeboard.selection.v1'||clip.components.length!==1||!c||!Array.isArray(clip.nets)||clip.nets.length||clip.editor?.connection_guides?.length||Object.keys(clip.editor?.wire_nodes||{}).length||c.module_instance||c.sheet||c.block||c.placement||JSON.stringify(template).length>LIMIT)throw Error('This component hotkey template is invalid. Assign the part again.');
 for(const p of Object.values(clip.editor?.positions||{}))if(!point(p))throw Error('Component hotkey positions need finite coordinates within the limit.');
 return template;
}
export function captureHotkeyComponent(spec,ref,{positions={},selectedKey=ref}={}){
 const source=structuredClone(spec);source.editor||={};source.editor.positions={...positions,...source.editor.positions};
 const clip=copySelection(source,[ref]),c=clip.components[0];
 for(const field of ['placement','sheet','block','module_instance'])delete c[field];
 clip.nets=[];clip.editor.connection_guides=[];clip.editor.wire_nodes={};
 const entries=Object.entries(clip.editor.positions),origin=clip.editor.positions[selectedKey]||clip.editor.positions[ref]||entries[0]?.[1]||[0,0];
 if(!point(origin))throw Error('The selected component position is invalid.');
 clip.editor.positions=entries.length?Object.fromEntries(entries.map(([key,p])=>{if(!point(p))throw Error('The component has invalid coordinates.');return[key,p.map((v,i)=>v-origin[i])];})):{[ref]:[0,0]};
 return validate({schema:SCHEMA,clipboard:clip});
}
export function placeHotkeyComponent(spec,template,position,sheet=''){
 validate(template);if(!point(position))throw Error('Choose a finite component position within the coordinate limit.');
 const result=pasteSelection(spec,template.clipboard,{schematicOffset:position,boardOffset:[spec.board.width_mm/2,spec.board.height_mm/2],sheet});
 for(const ref of result.refs)for(const[key,p]of Object.entries(result.spec.editor.positions))if(key===ref||key.startsWith(ref+'#'))if(!point(p))throw Error('The component position exceeds the coordinate limit.');
 result.spec=ensureTerminalNets(result.spec);return result;
}

export class ComponentHotkeys{
 constructor({state,storage,toast,editable=()=>true,busy=()=>false,interacting,api,commit}){
  Object.assign(this,{state,toast,editable,busy,interacting,api,commit});this.memory=new Map();
  if(storage)this.storage=storage;else try{this.storage=localStorage;}catch{}
 }
 get active(){return!!this.pending;}
 storageKey(){return'wb-component-hotkeys:'+encodeURIComponent(this.state().session?.user?.id||'device');}
 read(){
  const key=this.storageKey();if(this.memory.has(key))return this.memory.get(key);
  try{const raw=this.storage?.getItem(key);if(raw?.length>LIMIT)return{};const record=JSON.parse(raw||'null');if(record?.schema===1&&record.slots&&typeof record.slots==='object')return Object.fromEntries(Object.entries(record.slots).filter(([n,t])=>{try{return validSlot(n)&&!!validate(t);}catch{return false;}}));}catch{}
  return{};
 }
 available(){const s=this.state();return s.pid&&s.active==='schematic'&&!s.starting&&!s.openingProject&&s.canvas?.options?.nativeScene;}
 assign(slot){
  if(!validSlot(slot))return false;
  if(!this.available()||this.active||this.interacting?.()){this.toast('Finish the current canvas action before assigning a component hotkey.');return false;}
  const s=this.state(),refs=[...new Set([...s.selection].map(key=>key.split('#')[0]))];
  if(refs.length!==1){this.toast('Select one component, then press Shift and a number from 1 to 5.');return false;}
  try{
   const positions=Object.fromEntries((s.schematicData?.symbols||[]).filter(i=>i.ref===refs[0]).map(i=>[i.key,i.position]));
   const template=captureHotkeyComponent(s.spec,refs[0],{positions,selectedKey:s.selectedSymbolKey||refs[0]}),slots={...this.read(),[slot]:template};
   const raw=JSON.stringify({schema:1,slots});if(raw.length>LIMIT)throw Error('These component hotkeys exceed browser storage limits. Use smaller library assets.');
   this.memory.set(this.storageKey(),slots);while(this.memory.size>16)this.memory.delete(this.memory.keys().next().value);
   let stored=false;try{if(this.storage){this.storage.setItem(this.storageKey(),raw);stored=true;}}catch{}
   this.toast(stored?`Component ${template.clipboard.components[0].value||refs[0]} assigned to ${slot}.`:`Component assigned to ${slot} for this session; browser storage is unavailable.`);return true;
  }catch(error){this.toast(error.message,true);return false;}
 }
 current(context){const s=this.state();return this.pending===context&&this.storageKey()===context.user&&s.pid===context.pid&&s.spec===context.spec&&s.projectLoadToken===context.load&&s.canvas===context.canvas&&s.schematicSheet===context.sheet&&this.available()&&this.editable()&&!this.busy()&&!this.interacting?.();}
 async start(slot){
  if(!validSlot(slot))return false;
  this.cancel();if(!this.available()||!this.editable()||this.busy()||this.interacting?.()){this.toast('Finish the current action before inserting a component.');return false;}
  const template=this.read()[slot];if(!template){this.toast(`No component in hotkey ${slot}. Select one and press Shift+${slot} to assign it.`);return false;}
  const s=this.state(),candidate=placeHotkeyComponent(s.spec,template,[0,0],s.schematicSheet||''),controller=new AbortController();
  const context={pid:s.pid,spec:s.spec,load:s.projectLoadToken,canvas:s.canvas,sheet:s.schematicSheet,user:this.storageKey(),template,slot,controller};this.pending=context;
  // A click before the symbol is ready belongs to the existing canvas/tool, never to insertion.
  context.pendingGesture=()=>{if(this.pending===context&&!context.group)this.cancel();};document.addEventListener('pointerdown',context.pendingGesture,true);
  try{
   const scene=await this.api('/api/workbench/schematic-view',{method:'POST',body:candidate.spec,signal:controller.signal});
   if(!this.current(context))return false;
   const symbols=scene.symbols.filter(i=>candidate.refs.includes(i.ref));if(!symbols.length)throw Error('The saved component has no native symbol on this sheet.');
   const group=document.createElementNS('http://www.w3.org/2000/svg','g');group.setAttribute('data-component-placement',slot);group.setAttribute('class','component-placement');group.setAttribute('aria-hidden','true');
   group.innerHTML=symbols.map(i=>nativeSymbol(i,scene.definitions[i.definition],candidate.spec,{},scene.mm_per_unit,scene.origin_mm,null)).join('');
   group.querySelectorAll('[tabindex]').forEach(el=>el.removeAttribute('tabindex'));
   document.removeEventListener('pointerdown',context.pendingGesture,true);context.group=group;context.canvas.scene.append(group);context.canvas.svg.classList.add('component-placement-active');context.canvas.host.classList.add('component-placement-show');
   const status=document.createElement('div');status.className='component-placement-status';status.setAttribute('role','status');status.textContent=`${template.clipboard.components[0].value||'Component'} · Click to place · Esc to cancel`;context.status=status;context.canvas.host.append(status);
   const move=event=>{if(!this.current(context)){this.cancel();return;}const at=context.canvas.worldPoint(event);this.move(context,[at.x,at.y]);};
   const down=event=>{if(event.button!==0)return;if(!this.current(context)){this.cancel();return;}event.preventDefault();event.stopImmediatePropagation();const at=context.canvas.worldPoint(event),position=[at.x,at.y].map(v=>Math.round(v/10)*10);const result=placeHotkeyComponent(this.state().spec,template,position,context.sheet||'');this.cancel();this.commit(result.spec,`Inserted ${result.refs[0]} from hotkey ${slot}`,result.refs[0]);};
   const outside=event=>{if(!context.canvas.svg.contains(event.target))this.cancel();};
   context.handlers={move,down,outside};context.canvas.svg.addEventListener('pointermove',move,true);context.canvas.svg.addEventListener('pointerdown',down,true);document.addEventListener('pointerdown',outside,true);
   this.move(context,context.canvas.getCamera()?.center||[200,200]);return true;
  }catch(error){if(error.name!=='AbortError'&&this.pending===context){this.cancel();throw error;}return false;}
  finally{if(this.pending===context&&!context.group)this.cancel();}
 }
 move(context,p){const at=p.map(v=>Math.round(v/10)*10);context.group.setAttribute('transform',`translate(${at.join(',')})`);context.position=at;}
 cancel(){
  const old=this.pending;this.pending=null;if(!old)return;document.removeEventListener('pointerdown',old.pendingGesture,true);old.controller?.abort();old.group?.remove();old.status?.remove();old.canvas?.svg?.classList.remove('component-placement-active');old.canvas?.host?.classList.remove('component-placement-show');
  if(old.handlers){old.canvas.svg.removeEventListener('pointermove',old.handlers.move,true);old.canvas.svg.removeEventListener('pointerdown',old.handlers.down,true);document.removeEventListener('pointerdown',old.handlers.outside,true);}
 }
 key(event){
  const s=this.state();if(s.active!=='schematic'||event.target?.closest?.('input,textarea,select,[contenteditable=true],[role=treeitem],[role=menu]')||event.ctrlKey||event.metaKey||event.altKey)return false;
  if(this.active&&event.code==='Space'){this.cancel();return false;}
  const digit=/^(?:Digit|Numpad)([1-5])$/.exec(event.code);
  if(digit){event.preventDefault();if(!event.repeat){if(event.shiftKey)this.assign(Number(digit[1]));else this.start(Number(digit[1])).catch(error=>this.toast(error.message,true));}return true;}
  if(this.active){if(event.key==='Escape'){event.preventDefault();this.cancel();return true;}if(![' ','=','+','-'].includes(event.key)){event.preventDefault();return true;}}
  return false;
 }
 closeMenu(){const menu=document.querySelector('#componentHotkeyMenu');if(menu)menu.hidden=true;this.menuAnchor?.setAttribute('aria-expanded','false');}
 openMenu(anchor,close){
  if(anchor.disabled)return;this.closeMenu();let menu=document.querySelector('#componentHotkeyMenu');if(!menu){menu=document.createElement('div');menu.id='componentHotkeyMenu';menu.className='popover canvas-context-menu';menu.setAttribute('role','menu');document.body.append(menu);}
  this.menuAnchor=anchor;const slots=this.read();menu.innerHTML=[1,2,3,4,5].map(n=>`<button role="menuitem" data-hotkey-assign="${n}"><span>${n}${slots[n]?' · '+esc(slots[n].clipboard.components[0].value||'Component'):''}</span><kbd>⇧${n}</kbd></button>`).join('');
  menu.querySelectorAll('[data-hotkey-assign]').forEach(b=>b.onclick=()=>{this.assign(Number(b.dataset.hotkeyAssign));close();});
  menu.hidden=false;const rect=anchor.getBoundingClientRect();menu.style.left=Math.max(8,Math.min(innerWidth-menu.offsetWidth-8,rect.right))+'px';menu.style.top=Math.max(8,Math.min(innerHeight-menu.offsetHeight-8,rect.top))+'px';anchor.setAttribute('aria-expanded','true');menu.querySelector('button')?.focus();
  menu.onkeydown=e=>{if(['Escape','ArrowLeft'].includes(e.key)){e.preventDefault();e.stopPropagation();this.closeMenu();anchor.focus();}else if(['ArrowUp','ArrowDown'].includes(e.key)){e.preventDefault();const buttons=[...menu.querySelectorAll('button')],index=buttons.indexOf(document.activeElement);buttons[(index+(e.key==='ArrowDown'?1:-1)+buttons.length)%buttons.length]?.focus();}};
 }
}
