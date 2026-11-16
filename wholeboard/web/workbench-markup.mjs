import {esc,icon} from './workbench-icons.mjs';

const RED='#ff5f62',MAX_SIDE=2048;
const styleKeys=['color','fill','fill-opacity','stroke','stroke-width','stroke-opacity','stroke-dasharray','stroke-linecap','stroke-linejoin','opacity','display','visibility','font-family','font-size','font-weight','font-style','text-anchor','dominant-baseline','vector-effect'];
let fontPromise;
const fontData=()=>fontPromise??=(async()=>{const response=await fetch(new URL('./fonts/roboto-regular.ttf',import.meta.url));if(!response.ok)throw Error('The canvas font could not be loaded.');const bytes=new Uint8Array(await response.arrayBuffer());let text='';for(const byte of bytes)text+=String.fromCharCode(byte);return btoa(text);})().catch(error=>{fontPromise=undefined;throw error;});
const cancelled=message=>Object.assign(new Error(message),{cancelled:true});
const nonce=()=>crypto.randomUUID().replaceAll('-','');

export function captureSize(width,height,dpr=1){
 if(!Number.isFinite(width)||!Number.isFinite(height)||width<1||height<1)throw Error('Open a visible design canvas before using Markup.');
 const scale=Math.min(Math.max(1,Math.min(4,dpr||1)),MAX_SIDE/Math.max(width,height));return[Math.max(1,Math.round(width*scale)),Math.max(1,Math.round(height*scale))];
}

export function referenceMarkup(reference,pid){
 if(!reference||reference.project_id!==pid)return'';
 const origin=typeof location==='undefined'?'http://local.invalid':location.origin;let url;try{url=new URL(reference.url,origin);}catch{return'';}
 const prefix='/api/projects/'+encodeURIComponent(pid)+'/files/references/canvas/';
 if(url.origin!==origin||!/^[0-9a-f]{32}$/.test(reference.id||'')||url.pathname!==prefix+reference.id+'.png')return'';
 const context=reference.display_context,layerLabel=reference.view==='layout'?(context?` · ${context.focus?context.focus+' focus · ':''}Layer state captured`:' · Layer context unavailable'):'';
 const label=`Marked ${{schematic:'schematic',layout:'PCB layout','3d':'3D view'}[reference.view]||'canvas'} · saved v${reference.design_version}${layerLabel}`;
 return`<figure class="canvas-reference"><a href="${esc(reference.url)}" target="_blank" rel="noopener"><img src="${esc(reference.url)}" alt="${esc(label)}" loading="lazy"></a><figcaption>${esc(label)}</figcaption></figure>`;
}

function surface(viewer){return viewer?.svg||viewer?.canvas;}
async function snapshot(getViewer,displayContext){
 await document.fonts.ready;
 if(getViewer()?.svg)await fontData();
 const viewer=getViewer(),source=surface(viewer);if(!source?.isConnected)throw Error('Open a design canvas before using Markup.');
 const rect=source.getBoundingClientRect(),[width,height]=captureSize(rect.width,rect.height,devicePixelRatio),canvas=document.createElement('canvas');canvas.width=width;canvas.height=height;
 const context=canvas.getContext('2d');context.fillStyle='#101010';context.fillRect(0,0,width,height);
 let capturedContext;
 if(viewer.svg){
  const clone=source.cloneNode(true),originals=[source,...source.querySelectorAll('*')],copies=[clone,...clone.querySelectorAll('*')];
  for(let i=0;i<originals.length;i++){
   const computed=getComputedStyle(originals[i]);for(const key of styleKeys){let value=computed.getPropertyValue(key);value=value.replace(/url\(["']?[^)]*#([^"')]+)["']?\)/g,'url(#$1)');copies[i].style.setProperty(key,value);}
  }
  capturedContext=structuredClone(displayContext(viewer));
  clone.setAttribute('xmlns','http://www.w3.org/2000/svg');clone.setAttribute('width',String(rect.width));clone.setAttribute('height',String(rect.height));clone.style.width=rect.width+'px';clone.style.height=rect.height+'px';
  const style=document.createElementNS('http://www.w3.org/2000/svg','style');style.textContent=`@font-face{font-family:Roboto;src:url(data:font/ttf;base64,${await fontData()})}`;clone.prepend(style);
  const url=URL.createObjectURL(new Blob([new XMLSerializer().serializeToString(clone)],{type:'image/svg+xml;charset=utf-8'}));
  try{const image=new Image();image.src=url;await image.decode();context.drawImage(image,0,0,width,height);}finally{URL.revokeObjectURL(url);}
 }else{viewer.draw?.();context.drawImage(source,0,0,width,height);capturedContext=structuredClone(displayContext(viewer));}
 return{canvas,rect,viewer,displayContext:capturedContext};
}

export class MarkupUI{
 constructor({state,save,api,toast,editable,canStart=()=>true,displayContext=()=>null,onChange=()=>{},onDraftChange=()=>{}}){
  Object.assign(this,{state,save,api,toast,editable,canStart,displayContext,onChange,onDraftChange});this.active=false;this.starting=false;this.counter=0;this.paused=new Map();
  this.button=document.querySelector('#markupButton');this.more=document.querySelector('#composerMore');this.menu=document.querySelector('#composerMoreMenu');
  this.button.onclick=()=>this.toggle().catch(error=>this.toast(error.message,true));this.more.onclick=()=>this.openMenu();
  this.menu.querySelector('[data-composer-action="markup"]').onclick=()=>{this.menu.hidden=true;this.toggle().catch(error=>this.toast(error.message,true));};
  this.menu.querySelector('[data-composer-action="attach"]').onclick=()=>{this.menu.hidden=true;document.querySelector('#attachmentInput').click();};
  document.addEventListener('click',event=>{if(!event.target.closest('#composerMore,#composerMoreMenu'))this.menu.hidden=true;});
  document.addEventListener('keydown',event=>{
   if(!this.active&&!this.starting)return;
   if(event.key==='Escape'){event.preventDefault();event.stopImmediatePropagation();this.cancel('user');return;}
   if(!this.active||event.target.closest('input,textarea,[contenteditable="true"]')||event.key==='Tab')return;
   if(!event.metaKey&&!event.ctrlKey&&!event.altKey&&['1','2','3','4'].includes(event.key))return;
   event.preventDefault();event.stopImmediatePropagation();
  },true);
  window.addEventListener('resize',()=>this.cancel('resize'));
  document.addEventListener('wb:zoom',()=>this.cancel('resize'));document.addEventListener('wb:theme',()=>this.cancel('view'));
  this.observer=new ResizeObserver(()=>this.reconcile());this.observer.observe(document.querySelector('#viewContent'));
  this.mutations=new MutationObserver(()=>this.reconcile());this.mutations.observe(document.querySelector('#viewContent'),{childList:true});
  this.updateControls();
 }
 available(){const s=this.state();return this.canStart()&&this.editable()&&!s.starting&&!s.openingProject&&['schematic','layout','3d'].includes(s.active)&&!!surface(s.canvas)&&!(s.active==='layout'&&s.nativePending);}
 owner(){const s=this.state();return{pid:s.pid,version:s.version,generation:s.generation,loadToken:s.projectLoadToken,view:s.active,sheet:s.schematicSheet||'',enclosure:!!s.enclosure};}
 same(owner){const current=this.owner();return Object.keys(owner).every(key=>current[key]===owner[key])&&!this.state().openingProject&&this.editable();}
 async toggle(){if(this.active||this.starting){this.cancel('user');return;}return this.enter();}
 async enter(){
  if(!this.available())throw Error('Open Schematic, Layout or3D before using Markup.');
  this.menu.hidden=true;this.starting=true;const token=++this.counter,loadToken=this.state().projectLoadToken;this.onChange();
  try{
   await this.save();if(token!==this.counter||loadToken!==this.state().projectLoadToken)return;
   const owner=this.owner();let frame;
   for(let attempt=0;attempt<2;attempt++){frame=await snapshot(()=>this.state().canvas,this.displayContext);if(token!==this.counter||!this.same(owner))return;if(frame.viewer===this.state().canvas)break;frame=null;}
   if(!frame)throw Error('The canvas is still updating. Start Markup again once it settles.');
   this.ownerState=owner;this.frame=frame;this.active=true;this.starting=false;this.revision=0;this.captureId=nonce();this.uploaded=null;this.strokeCount=0;this.drawing=null;
   const viewport=document.querySelector('#viewport'),bounds=viewport.getBoundingClientRect(),host=document.createElement('div');host.id='canvasMarkup';host.className='canvas-markup';
   Object.assign(host.style,{left:(frame.rect.left-bounds.left)+'px',top:(frame.rect.top-bounds.top)+'px',width:frame.rect.width+'px',height:frame.rect.height+'px'});
   frame.canvas.id='markupBase';frame.canvas.setAttribute('aria-hidden','true');host.append(frame.canvas);const ink=document.createElement('canvas');ink.id='markupStrokes';ink.tabIndex=0;ink.width=frame.canvas.width;ink.height=frame.canvas.height;ink.setAttribute('aria-label','Draw markup on the frozen design canvas');host.append(ink);this.ink=ink;this.context=ink.getContext('2d');
   host.insertAdjacentHTML('beforeend',`<div class="markup-bar"><span>${icon('pen')}Markup</span><button type="button" id="markupAsk">Ask AI</button><button type="button" id="markupExit" aria-label="Exit Markup"><kbd>Esc</kbd> Exit</button></div>`);viewport.append(host);this.host=host;
   host.querySelector('#markupExit').onclick=()=>this.cancel('user');host.querySelector('#markupAsk').onclick=()=>{document.querySelector('#ideShell').classList.add('mobile-chat-open');document.querySelector('#chatInput').focus();};
   const point=event=>{const r=ink.getBoundingClientRect();return[(event.clientX-r.left)/r.width*ink.width,(event.clientY-r.top)/r.height*ink.height];};
   const style=()=>{this.context.strokeStyle=RED;this.context.fillStyle=RED;this.context.lineWidth=3.5*ink.width/frame.rect.width;this.context.lineCap='round';this.context.lineJoin='round';};
   ink.addEventListener('pointerdown',event=>{if(event.button!==0)return;event.preventDefault();event.stopPropagation();if(this.strokeCount>=500){this.toast('Use up to500 strokes in one marked reference.',true);return;}ink.setPointerCapture(event.pointerId);this.drawing={id:event.pointerId,last:point(event),points:1};this.strokeCount++;this.revision++;this.captureId=nonce();this.uploaded=null;style();const[x,y]=this.drawing.last;this.context.beginPath();this.context.arc(x,y,this.context.lineWidth/2,0,Math.PI*2);this.context.fill();this.onDraftChange();});
   ink.addEventListener('pointermove',event=>{if(!this.drawing||this.drawing.id!==event.pointerId||this.drawing.points>=20000)return;event.preventDefault();event.stopPropagation();const next=point(event);style();this.context.beginPath();this.context.moveTo(...this.drawing.last);this.context.lineTo(...next);this.context.stroke();this.drawing.last=next;this.drawing.points++;this.revision++;this.uploaded=null;});
   const finish=event=>{if(this.drawing?.id===event.pointerId){this.drawing=null;this.captureId=nonce();this.onDraftChange();}};ink.addEventListener('pointerup',finish);ink.addEventListener('pointercancel',finish);
   ink.addEventListener('wheel',event=>{event.preventDefault();event.stopPropagation();},{passive:false});ink.addEventListener('contextmenu',event=>event.preventDefault());
   document.body.classList.add('markup-active');if(innerWidth<=760)document.querySelector('#ideShell').classList.remove('mobile-chat-open');this.onDraftChange();this.reconcile();this.onChange();document.querySelector('#chatInput').focus({preventScroll:true});
  }finally{if(token===this.counter){this.starting=false;this.onChange();}}
 }
 pause(viewer){
  if(!viewer||this.paused.has(viewer))return;const methods={};for(const key of ['fit','setZoom','setCamera'])if(typeof viewer[key]==='function'){methods[key]=viewer[key];const ui=this,original=viewer[key];viewer[key]=function(...args){if(!ui.active)return original.apply(this,args);};}this.paused.set(viewer,methods);
 }
 reconcile(){
  if(!this.active){this.updateControls();return;}
  const r=surface(this.state().canvas)?.getBoundingClientRect(),old=this.frame.rect;
  if(!this.same(this.ownerState)||!r||['width','height','left','top'].some(key=>Math.abs(r[key]-old[key])>1)){this.cancel('view');return;}
  this.pause(this.state().canvas);this.updateControls();
 }
 updateControls(){
  const available=this.available();this.button.disabled=this.starting||!this.active&&!available;this.button.setAttribute('aria-label',this.active?'Exit Markup':'Markup');this.button.title=this.active?'Exit Markup (Esc)':'Draw on the canvas and ask AI';this.button.classList.toggle('active',this.active);this.button.setAttribute('aria-pressed',String(this.active));
  const item=this.menu.querySelector('[data-composer-action="markup"]');item.disabled=this.starting||!this.active&&!available;item.querySelector('span').textContent=this.active?'Exit Markup':'Markup';
  this.more.disabled=!this.editable();this.menu.querySelector('[data-composer-action="attach"]').disabled=!this.editable();
  if(this.active){document.querySelector('#chatInput').placeholder='Draw on the canvas and ask about it';for(const id of ['fitButton','zoomIn','zoomOut','zoomReset','panButton','autoLayoutButton','wireButton','routeButton','viaButton','cameraOptions']){const button=document.getElementById(id);if(button)button.disabled=true;}}
 }
 openMenu(){this.updateControls();const r=this.more.getBoundingClientRect();this.menu.hidden=!this.menu.hidden;if(!this.menu.hidden){this.menu.style.left=Math.max(8,Math.min(innerWidth-190,r.left))+'px';this.menu.style.top=Math.max(8,r.top-this.menu.offsetHeight-8)+'px';}}
 token(){return this.active?{owner:this.ownerState,revision:this.revision}:null;}
 async reference(token){
  if(this.drawing)throw Error('Finish the current markup stroke before sending.');
  if(!token||!this.active||token.owner!==this.ownerState||token.revision!==this.revision||!this.same(token.owner))throw cancelled('The marked view changed before sending.');
  if(this.uploaded?.revision===token.revision)return this.uploaded.reference;
  const canvas=document.createElement('canvas');canvas.width=this.frame.canvas.width;canvas.height=this.frame.canvas.height;const context=canvas.getContext('2d');context.drawImage(this.frame.canvas,0,0);context.drawImage(this.ink,0,0);
  const body={capture_id:this.captureId,base_version:token.owner.version,view:token.owner.view,sheet:token.owner.sheet,width:canvas.width,height:canvas.height,strokes:this.strokeCount,data:canvas.toDataURL('image/png').split(',')[1],...(this.frame.displayContext?{display_context:this.frame.displayContext}:{})};
  const reference=await this.api(`/api/workbench/projects/${token.owner.pid}/canvas-reference`,{method:'POST',body});
  if(!this.active||token.owner!==this.ownerState||token.revision!==this.revision||!this.same(token.owner))throw cancelled('The marked view changed before sending.');
  this.uploaded={revision:token.revision,reference};return reference;
 }
 cancel(reason='view'){
  if(!this.active&&!this.starting)return;this.counter++;this.active=false;this.starting=false;this.host?.remove();this.host=null;this.menu.hidden=true;this.uploaded=null;this.drawing=null;this.ownerState=null;this.frame=null;this.ink=null;this.context=null;document.body.classList.remove('markup-active');
  for(const[viewer,methods]of this.paused)for(const[key,value]of Object.entries(methods))viewer[key]=value;this.paused.clear();
  for(const id of ['fitButton','zoomIn','zoomOut','zoomReset','panButton','cameraOptions']){const button=document.getElementById(id);if(button)button.disabled=false;}
  if(reason==='user')this.onDraftChange();this.onChange();
 }
}
