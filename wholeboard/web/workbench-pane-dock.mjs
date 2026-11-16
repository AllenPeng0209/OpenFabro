import {esc,icon} from './workbench-icons.mjs';

const order=['manufacturing','library','objects','layers','view','checks','comments'];

export class ToolPaneLayout{
 constructor(saved={}){this.opened=new Set();this.active=null;const raw=Object.fromEntries(order.map(key=>[key,Number.isFinite(saved[key])&&saved[key]>0?saved[key]:1])),maximum=Math.max(...Object.values(raw));this.weights=Object.fromEntries(order.map(key=>[key,Math.max(1e-6,raw[key]/maximum)]));}
 get keys(){return order.filter(key=>this.opened.has(key));}
 has(key){return this.opened.has(key);}
 open(key){if(!order.includes(key))return false;this.opened.add(key);this.active=key;return true;}
 close(key){this.opened.delete(key);if(this.active===key)this.active=this.keys.at(-1)||null;}
 clear(){this.opened.clear();this.active=null;}
 fractions(){const keys=this.keys,total=keys.reduce((sum,key)=>sum+this.weights[key],0);return Object.fromEntries(keys.map(key=>[key,this.weights[key]/total]));}
 resize(index,delta,height){
  const keys=this.keys;if(!Number.isFinite(delta)||!Number.isFinite(height)||height<=0||!keys[index+1])return false;
  const fractions=this.fractions(),a=keys[index],b=keys[index+1],sum=fractions[a]+fractions[b],minimum=Math.min(72/height,1/keys.length),lo=Math.min(minimum,sum/2),next=Math.max(lo,Math.min(sum-lo,fractions[a]+delta/height));
  const total=keys.reduce((v,key)=>v+this.weights[key],0);this.weights[a]=next*total;this.weights[b]=(sum-next)*total;return true;
 }
}

export class ToolPaneDock{
 constructor({host,state,onFocus=()=>{}}){
  Object.assign(this,{host,state,onFocus});this.panes=new Map();this.model=new ToolPaneLayout();this.owner=null;this.resizing=null;host.classList.add('tool-pane-dock');
  host.addEventListener('focusin',event=>{const key=event.target.closest('[data-dock-pane]')?.dataset.dockPane;if(key)this.focus(key);});
  host.addEventListener('pointerdown',event=>{const key=event.target.closest('[data-dock-pane]')?.dataset.dockPane;if(key)this.focus(key);});
  window.addEventListener('blur',()=>this.cancelResize());window.addEventListener('resize',()=>{this.cancelResize();this.layout();});
  document.addEventListener('keydown',event=>{if(this.resizing&&event.key==='Escape'){event.preventDefault();event.stopImmediatePropagation();this.cancelResize();}},true);
  this.observer=new ResizeObserver(()=>{if(this.resizing&&Math.abs(this.host.clientHeight-this.resizing.hostHeight)>.5)this.cancelResize();this.layout();});this.observer.observe(host);
  const viewport=document.querySelector('#viewport'),content=document.querySelector('#viewContent'),project=document.querySelector('#projectDock');if(viewport){this.viewportObserver=new ResizeObserver(()=>this.layout());this.viewportObserver.observe(viewport);if(content)this.viewportObserver.observe(content);if(project)this.viewportObserver.observe(project);}
 }
 scope(){const s=this.state();return JSON.stringify([s.session?.user?.id||'device',s.pid,s.projectLoadToken]);}
 syncScope(){const next=this.scope();if(this.owner===next)return;this.clear();this.owner=next;const s=this.state();this.storageKey='wb-tool-panes:'+encodeURIComponent(s.session?.user?.id||'device')+':'+encodeURIComponent(s.pid||'');let saved={};try{const raw=localStorage.getItem(this.storageKey);if(raw&&raw.length<4000)saved=JSON.parse(raw);}catch{}this.model=new ToolPaneLayout(saved&&typeof saved==='object'?saved:{});}
 has(key){this.syncScope();return this.model.has(key);}
 remember(){try{localStorage.setItem(this.storageKey,JSON.stringify(this.model.weights));}catch{}}
 focus(key){if(!this.model.has(key))return;this.model.active=key;this.onFocus(key);for(const[k,pane]of this.panes){const close=pane.querySelector('[data-close-pane]');if(k===key){close.id='closeDrawer';close.setAttribute('aria-label','Close tools panel');}else{close.removeAttribute('id');close.setAttribute('aria-label','Close '+pane.dataset.paneTitle+' panel');}}}
 open(key,title,classes=[]){
  this.syncScope();this.cancelResize();if(!this.model.open(key))throw Error('Unknown tool pane.');let pane=this.panes.get(key);
  if(!pane){pane=document.createElement('section');pane.dataset.dockPane=key;pane.dataset.paneTitle=title;pane.className='drawer-pane '+classes.join(' ');pane.setAttribute('aria-label',title+' panel');pane.innerHTML=`<div class="drawer-heading"><span class="object-tree-heading">${icon(key==='objects'?'list':key==='layers'?'layers':key==='view'?'cube':'settings')}${esc(title)}</span><button type="button" class="icon-button" data-close-pane="${esc(key)}" aria-label="Close ${esc(title)} panel">×</button></div><div class="drawer-content"></div>`;pane.querySelector('[data-close-pane]').onclick=()=>this.close(key);this.panes.set(key,pane);}
  this.render();this.focus(key);return pane;
 }
 close(key){this.cancelResize();this.model.close(key);this.panes.get(key)?.remove();this.panes.delete(key);this.render();if(this.model.active)this.focus(this.model.active);else this.onFocus(null);}
 clear(){this.cancelResize();this.model.clear();this.panes.clear();this.host.replaceChildren();this.host.hidden=true;this.updateTools();this.layout();this.onFocus(null);}
 updateTools(){for(const button of document.querySelectorAll('[data-panel]'))button.classList.toggle('active',this.model.has(button.dataset.panel));}
 render(){
  this.cancelResize();const separators=[...this.host.querySelectorAll('.tool-pane-separator')],desired=[],keys=this.model.keys;
  keys.forEach((key,index)=>{if(index){const pair=keys[index-1]+':'+key,bar=separators.find(s=>s.dataset.pair===pair)||this.separator(index-1);bar.dataset.pair=pair;bar.dataset.split=String(index-1);desired.push(bar);}desired.push(this.panes.get(key));});
  for(const bar of separators)if(!desired.includes(bar))bar.remove();
  desired.forEach((node,index)=>{if(this.host.children[index]!==node)this.host.insertBefore(node,this.host.children[index]||null);});this.host.hidden=!desired.length;this.updateTools();this.layout();
 }
 height(){return Math.max(0,this.host.clientHeight-(this.model.keys.length-1));}
 layout(){
  const fractions=this.model.fractions(),height=this.height();for(const key of this.model.keys){const pane=this.panes.get(key);pane.style.flex=`${fractions[key]} 1 0px`;pane.style.minHeight='0px';}
  for(const separator of this.host.querySelectorAll('.tool-pane-separator')){const index=Number(separator.dataset.split),keys=this.model.keys,value=keys.slice(0,index+1).reduce((sum,key)=>sum+fractions[key],0)*100;separator.setAttribute('aria-valuenow',String(Math.round(value)));separator.setAttribute('aria-valuemin','0');separator.setAttribute('aria-valuemax','100');separator.dataset.available=String(height);}
  const viewport=document.querySelector('#viewport');if(viewport){const inset=this.model.keys.length?this.host.offsetLeft+this.host.offsetWidth:0,project=document.querySelector('#projectDock'),reserved=project&&!project.hidden?project.offsetWidth+10:0,available=(document.querySelector('#viewContent')?.clientWidth||viewport.clientWidth)-inset-reserved,compact=!!inset&&available<360;viewport.style.setProperty('--tool-pane-toolbar-inset',inset&&!compact?inset+'px':'0px');viewport.classList.toggle('tool-pane-toolbar-compact',compact);}
 }
 separator(index){
  const bar=document.createElement('div');bar.className='tool-pane-separator';bar.dataset.split=String(index);bar.tabIndex=0;bar.setAttribute('role','separator');bar.setAttribute('aria-label','Adjust tool pane sizes');bar.setAttribute('aria-orientation','horizontal');
  bar.onkeydown=event=>{if(!['ArrowUp','ArrowDown','Home','End'].includes(event.key))return;event.preventDefault();event.stopPropagation();if(this.owner!==this.scope()){this.syncScope();return;}if(this.resizing)return;this.model.resize(Number(bar.dataset.split),event.key==='Home'?-this.height():event.key==='End'?this.height():event.key==='ArrowUp'?-16:16,this.height());this.layout();this.remember();};
  bar.onpointerdown=event=>{if(event.button!==0)return;event.preventDefault();event.stopPropagation();if(this.owner!==this.scope()){this.syncScope();return;}this.cancelResize();bar.focus();bar.setPointerCapture(event.pointerId);this.resizing={bar,id:event.pointerId,y:event.clientY,index:Number(bar.dataset.split),hostHeight:this.host.clientHeight,owner:this.scope(),weights:{...this.model.weights}};document.body.classList.add('resizing-tool-panes');};
  bar.onpointermove=event=>{const drag=this.resizing;if(!drag||drag.id!==event.pointerId)return;if(drag.owner!==this.scope()){this.cancelResize();return;}this.model.weights={...drag.weights};this.model.resize(drag.index,event.clientY-drag.y,this.height());this.layout();};
  bar.onpointerup=event=>{if(this.resizing?.id!==event.pointerId)return;if(this.resizing.owner!==this.scope()){this.cancelResize();this.syncScope();return;}this.endResize();this.remember();};bar.onpointercancel=()=>this.cancelResize();bar.addEventListener('lostpointercapture',()=>{if(this.resizing?.bar===bar)this.cancelResize();});return bar;
 }
 endResize(){const drag=this.resizing;this.resizing=null;document.body.classList.remove('resizing-tool-panes');if(drag?.bar.hasPointerCapture(drag.id))drag.bar.releasePointerCapture(drag.id);}
 cancelResize(){if(!this.resizing)return;this.model.weights={...this.resizing.weights};this.endResize();this.layout();}
}
