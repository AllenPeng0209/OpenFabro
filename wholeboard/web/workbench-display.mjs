import {esc,icon} from './workbench-icons.mjs';

export const DISPLAY_DEFAULTS=Object.freeze({pinLabels:false,comments:true,cursors:true,shortcutBar:true});
const rows=[['pinLabels','All pin labels','link'],['comments','Comments','chat'],['cursors','Collaborative cursors','navigation'],['shortcutBar','Keyboard shortcut bar','keyboard']];
const normalized=value=>Object.fromEntries(Object.entries(DISPLAY_DEFAULTS).map(([key,initial])=>[key,typeof value?.[key]==='boolean'?value[key]:initial]));

export class DisplayPreferences{
 constructor({storage,toast=()=>{}}={}){this.memory=new Map();this.warned=new Set();this.toast=toast;if(storage)this.storage=storage;else try{this.storage=globalThis.localStorage;}catch{}}
 key(user,pid){return'wb-schematic-display:'+encodeURIComponent(user||'device')+':'+encodeURIComponent(pid||'reference');}
 cache(key,value){this.memory.delete(key);this.memory.set(key,value);while(this.memory.size>128)this.memory.delete(this.memory.keys().next().value);}
 load(user,pid){const key=this.key(user,pid);if(this.memory.has(key)){const value=this.memory.get(key);this.cache(key,value);return{...value};}let flags={};try{const raw=this.storage?.getItem(key);if(raw&&raw.length<=2048){const value=JSON.parse(raw);if(value?.schema===1)flags=normalized(value.flags);}}catch{}const result=normalized(flags);this.cache(key,result);return{...result};}
 save(user,pid,flags){const key=this.key(user,pid),value=normalized(flags);this.cache(key,value);try{if(!this.storage)throw Error('Storage unavailable');this.storage.setItem(key,JSON.stringify({schema:1,flags:value}));}catch{if(!this.warned.has(key)){this.warned.add(key);while(this.warned.size>128)this.warned.delete(this.warned.values().next().value);this.toast('Display settings are kept for recent views in this session; browser storage is unavailable.');}}return{...value};}
}

export class SchematicDisplayUI{
 constructor({state,interacting=()=>false,changed=()=>{},toast}){Object.assign(this,{state,interacting,changed,toast});this.preferences=new DisplayPreferences({toast});this.owner=null;this.flags={...DISPLAY_DEFAULTS};this.expanded=true;}
 user(){const s=this.state();return s.session?.user?.id||s.project.access?.user?.id||'device';}
 sync(){const s=this.state(),owner=JSON.stringify([this.user(),s.pid,s.projectLoadToken]);if(owner!==this.owner){this.owner=owner;this.flags=this.preferences.load(this.user(),s.pid);}}
 ready(key){const s=this.state();return s.active==='schematic'&&!!s.pid&&!s.starting&&!s.openingProject&&!!s.canvas?.svg?.isConnected&&(key!=='pinLabels'||!!s.canvas.options?.nativeScene)&&!this.interacting();}
 panel(){this.sync();return`<div class="schematic-display-controls"><button type="button" class="display-section-heading" data-display-section aria-expanded="${this.expanded}"><strong>Display</strong>${icon('chevronDown')}</button><div class="schematic-display-rows" ${this.expanded?'':'hidden'}>${rows.map(([key,name,glyph])=>`<button type="button" class="schematic-display-row" data-display="${key}" aria-label="${esc(name)}" aria-pressed="${this.flags[key]}" ${this.ready(key)?'':'disabled'}><span class="display-row-icon">${icon(glyph)}</span><span>${esc(name)}</span><span class="display-row-check" ${this.flags[key]?'':'hidden'}>${icon('check')}</span></button>`).join('')}</div></div>`;}
 mount(host){this.host=host;for(const button of host.querySelectorAll('[data-display]')){button.onclick=()=>this.toggle(button.dataset.display);button.onkeydown=event=>{if(event.key===' '||event.key==='Enter')event.stopPropagation();};}host.querySelector('[data-display-section]')?.addEventListener('click',event=>{this.expanded=!this.expanded;event.currentTarget.setAttribute('aria-expanded',String(this.expanded));host.querySelector('.schematic-display-rows').hidden=!this.expanded;});this.apply();}
 apply(){
  this.sync();const s=this.state(),active=s.active==='schematic',svg=s.canvas?.svg;
  if(svg){svg.classList.toggle('inspect-all-pin-labels',active&&this.flags.pinLabels);svg.classList.toggle('schematic-comments-hidden',active&&!this.flags.comments);svg.classList.toggle('schematic-cursors-hidden',active&&!this.flags.cursors);}
  document.querySelector('#canvasBottom')?.classList.toggle('schematic-shortcuts-hidden',active&&!this.flags.shortcutBar);
  if(this.host?.isConnected)for(const button of this.host.querySelectorAll('[data-display]')){const on=this.flags[button.dataset.display];button.setAttribute('aria-pressed',String(on));button.disabled=!this.ready(button.dataset.display);button.querySelector('.display-row-check').hidden=!on;}
 }
 toggle(key){this.sync();if(!Object.hasOwn(DISPLAY_DEFAULTS,key)||!this.ready(key))return false;this.flags=this.preferences.save(this.user(),this.state().pid,{...this.flags,[key]:!this.flags[key]});this.apply();this.changed();return true;}
 key(event){
  if(event.isComposing||event.altKey||event.target.isContentEditable||event.target.closest?.('input,textarea,select,[contenteditable=true]')||document.querySelector('dialog[open]')||!this.ready())return false;
  const command=event.metaKey||event.ctrlKey,key=command&&event.shiftKey&&event.code==='Backslash'?'cursors':!command&&event.shiftKey&&event.code==='KeyP'?'pinLabels':!command&&event.shiftKey&&event.code==='KeyC'?'comments':null;
  if(!key)return false;event.preventDefault();if(!event.repeat)this.toggle(key);return true;
 }
}
