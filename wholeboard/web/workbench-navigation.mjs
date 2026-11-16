import {esc,icon} from './workbench-icons.mjs';
import {CUBE_FACES,cameraBasis,cubeTarget,orbitOrientation,directionLabel} from './workbench-camera.mjs';

const dot=(a,b)=>a.reduce((v,n,i)=>v+n*b[i],0);
const materialGlyph=style=>{
 if(style==='blueprint')return`<svg class="icon" viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="#d7e2df" stroke-width="1.4"><path d="m12 2 9 5v10l-9 5-9-5V7zM3 7l9 5 9-5M12 12v10M7.5 4.5l9 5M7.5 9.5v10M16.5 9.5v10"/></svg>`;
 if(style==='xray')return`<svg class="icon" viewBox="0 0 24 24" aria-hidden="true" stroke="#add6cd" stroke-width="1.4"><path d="m12 2 9 5v10l-9 5-9-5V7z" fill="#13b68d" fill-opacity=".22"/><path d="m3 7 9 5 9-5M12 12v10M3 17l9-5 9 5" fill="none"/></svg>`;
 const colors=style==='solid'?['#1dfdc0','#124f42','#112b25']:['#9df4df','#14bf94','#008c73'];return`<svg class="icon" viewBox="0 0 24 24" aria-hidden="true" stroke="#8bdfc9" stroke-width=".9"><path d="m12 2 9 5-9 5-9-5z" fill="${colors[0]}"/><path d="m3 7 9 5v10l-9-5z" fill="${colors[1]}"/><path d="m12 12 9-5v10l-9 5z" fill="${colors[2]}"/></svg>`;
};
const actions=[['up','Orbit up','chevronDown',80,12,180],['right','Orbit right','chevronRight',148,80,0],['down','Orbit down','chevronDown',80,148,0],['left','Orbit left','chevronRight',12,80,180],['rollLeft','Rotate view counterclockwise','rotate',32,32,0],['rollRight','Rotate view clockwise','rotate',128,32,0],['home','Home view','home',32,128,0],['around','Turn view around','rotate',128,128,0]];

export class NavigationCube{
 constructor({state,interacting=()=>false,readSettings,changeSettings}){Object.assign(this,{state,interacting,readSettings,changeSettings});this.epoch=0;this.mobileVisible=false;this.radialOpen=false;this.spacePress=null;this.spaceReleases=new WeakMap();}
 owner(){const s=this.state();return JSON.stringify([s.session?.user?.id||s.project.access?.user?.id||'device',s.pid,s.projectLoadToken]);}
 ownsSpaceRelease(event){const press=this.spaceReleases.get(event);return!!press&&press.epoch===this.epoch&&press.owner===this.owner();}
 ready(){const s=this.state();return this.view===s.canvas&&s.active==='3d'&&!s.starting&&!s.openingProject&&this.host?.isConnected&&this.view?.canvas?.isConnected&&this.mountedOwner===this.owner()&&!this.interacting();}
 attach(view,host){
  this.removeSpaceCapture?.();this.spacePress=null;if(this.mountedOwner!==this.owner()){this.mobileVisible=false;this.radialOpen=false;}this.mountedOwner=this.owner();this.view=view;this.host=host;this.faceKey=null;const epoch=++this.epoch,valid=()=>epoch===this.epoch&&this.view===view&&this.host===host&&this.ready();
  host.className='cad-navigation';host.setAttribute('role','group');host.setAttribute('aria-label','3D view navigation');
  const separators=Array.from({length:8},(_,i)=>{const a=(i*Math.PI/4)+Math.PI/8;return`<path d="M${80+55*Math.cos(a)} ${80+55*Math.sin(a)}L${80+78*Math.cos(a)} ${80+78*Math.sin(a)}"/>`;}).join('');
  host.innerHTML=`<div class="navigation-cube-stage"><svg class="navigation-cube" viewBox="0 0 160 160" aria-label="Orientation cube"><circle class="navigation-ring" cx="80" cy="80" r="67"/><g class="navigation-separators">${separators}</g><g class="navigation-faces"></g></svg>${actions.map(([key,label,glyph,x,y,rotation])=>`<button type="button" class="navigation-orbit" data-nav-action="${key}" aria-label="${esc(label)}" title="${esc(label)}" style="--nav-x:${x}px;--nav-y:${y}px;--nav-rotate:${rotation}deg">${icon(glyph)}</button>`).join('')}</div><button type="button" class="navigation-camera" aria-label="Open camera options" aria-expanded="false">${icon('camera')}</button><div class="navigation-radial" hidden>${[['projection','',80,192],['realistic','Realistic material',24,178],['solid','Solid material',-18,136],['xray','X-ray material',-32,80],['blueprint','Blueprint material',-18,24]].map(([key,label,x,y])=>`<button type="button" data-nav-setting="${key}" aria-label="${label}" title="${label}" style="--nav-x:${x}px;--nav-y:${y}px">${key==='projection'?icon('grid'):materialGlyph(key)}</button>`).join('')}</div><button type="button" class="navigation-toggle" aria-label="Show view cube" title="Show view cube">${icon('cube')}</button><span class="navigation-status"></span>`;
  for(const b of host.querySelectorAll('[data-nav-action]'))b.onclick=()=>{if(valid())this.action(b.dataset.navAction);};
  const camera=host.querySelector('.navigation-camera');camera.onclick=()=>{if(!valid())return;if(matchMedia('(max-width:760px)').matches)this.mobileVisible=true;this.radialOpen=!this.radialOpen;this.update(view);};
  host.querySelector('.navigation-toggle').onclick=()=>{if(!valid())return;this.mobileVisible=!this.mobileVisible;if(!this.mobileVisible)this.radialOpen=false;this.update(view);};
  for(const b of host.querySelectorAll('[data-nav-setting]'))b.onclick=()=>{if(!valid()||!view.renderer)return;const key=b.dataset.navSetting,p=this.readSettings();this.changeSettings(key==='projection'?{projection:p.projection==='perspective'?'orthographic':'perspective'}:{style:key});this.update(view);};
  host.querySelector('svg').onclick=event=>{const target=event.target.closest('[data-nav-target]');if(target&&valid())view.setViewDirection(target.dataset.navTarget.split(',').map(Number));};
  // Trusted key events can run microtasks between listeners. Keep release ownership on the event.
  const releaseSpace=event=>{if(event.key!==' ')return;if(this.spacePress)this.spaceReleases.set(event,this.spacePress);this.spacePress=null;};document.addEventListener('keyup',releaseSpace,true);this.removeSpaceCapture=()=>document.removeEventListener('keyup',releaseSpace,true);
  host.onpointerdown=event=>event.stopPropagation();host.onkeydown=event=>{
   if(event.key===' '&&!event.repeat&&valid())this.spacePress={epoch,owner:this.mountedOwner};
   if(event.key==='Escape'&&this.radialOpen){if(!valid())return;event.preventDefault();event.stopPropagation();this.radialOpen=false;this.update(view);camera.focus();return;}
   if(event.key==='Home'){event.preventDefault();event.stopPropagation();if(valid())this.action('home');return;}
   if(event.target.closest('button')&&['Enter',' ','ArrowUp','ArrowDown','ArrowLeft','ArrowRight'].includes(event.key)){event.stopPropagation();return;}
   const target=event.target.closest('[data-nav-target]');if(target&&['Enter',' '].includes(event.key)){event.preventDefault();event.stopPropagation();if(valid())view.setViewDirection(target.dataset.navTarget.split(',').map(Number));return;}
   if(target&&['ArrowUp','ArrowDown','ArrowLeft','ArrowRight','Home'].includes(event.key)){event.preventDefault();event.stopPropagation();if(valid())this.action(event.key==='Home'?'home':{ArrowUp:'up',ArrowDown:'down',ArrowLeft:'left',ArrowRight:'right'}[event.key]);}
  };
  host.onkeyup=event=>{if(event.key===' '){if(this.ownsSpaceRelease(event))event.stopPropagation();return;}if(['Enter','Home','ArrowUp','ArrowDown','ArrowLeft','ArrowRight'].includes(event.key))event.stopPropagation();};
  this.update(view);const pending=this.pendingFocus;this.pendingFocus=null;
  if(pending?.owner===this.mountedOwner&&this.ready()&&document.activeElement===document.body){let target;
   if(pending.action)target=[...host.querySelectorAll('[data-nav-action]')].find(e=>e.dataset.navAction===pending.action);
   else if(pending.target)target=[...host.querySelectorAll('[data-nav-target]')].find(e=>e.dataset.navTarget===pending.target);
   else if(pending.toggle)target=host.querySelector('.navigation-toggle');
   if(!target?.getBoundingClientRect().width)target=camera;target.focus({preventScroll:true});
  }
 }
 detach(){const s=this.state(),focused=this.host?.contains(document.activeElement)?document.activeElement:null;this.pendingFocus=focused&&s.active==='3d'&&!s.openingProject&&this.mountedOwner===this.owner()?{owner:this.mountedOwner,action:focused.dataset.navAction,target:focused.dataset.navTarget,toggle:focused.classList.contains('navigation-toggle')}:null;this.removeSpaceCapture?.();this.removeSpaceCapture=null;this.spacePress=null;this.epoch++;this.host?.replaceChildren();if(this.host){this.host.onkeydown=null;this.host.onkeyup=null;this.host.onpointerdown=null;}this.view=null;this.host=null;this.radialOpen=false;}
 action(key){
  if(!this.ready())return;const v=this.view;
  if(key==='home'){if(v.setViewDirection([-1,1,1]))v.fit();return;}
  if(key==='rollLeft'||key==='rollRight'){v.setOrientation({roll:v.roll+(key==='rollRight'?1:-1)*Math.PI/2});return;}
  if(key==='around'){v.setOrientation({yaw:v.yaw+Math.PI});return;}
  const move={left:[-Math.PI/4,0],right:[Math.PI/4,0],up:[0,Math.PI/4],down:[0,-Math.PI/4]}[key];if(move)v.setOrientation(orbitOrientation(v,...move));
 }
 faces(basis,ready){
  const project=p=>[80+26*dot(p,basis.right),80-26*dot(p,basis.up)],cuts=[-1,-.65,.65,1];let output='';
  for(const face of CUBE_FACES.filter(f=>dot(f.normal,basis.direction)>1e-7)){
   const point=(u,v)=>project(face.normal.map((n,i)=>n+u*face.right[i]+v*face.up[i]));
   for(let x=0;x<3;x++)for(let y=0;y<3;y++){
    const points=[[cuts[x],cuts[y]],[cuts[x+1],cuts[y]],[cuts[x+1],cuts[y+1]],[cuts[x],cuts[y+1]]].map(p=>point(...p).map(n=>n.toFixed(3)).join(',')).join(' '),target=cubeTarget(face.id,(cuts[x]+cuts[x+1])/2,(cuts[y]+cuts[y+1])/2),label=directionLabel(target).replace(/ view$/,'').toLowerCase();
    output+=`<polygon class="navigation-face-target" points="${points}" data-nav-target="${target.join(',')}" role="button" tabindex="${ready?'0':'-1'}" aria-label="View ${label}" aria-disabled="${!ready}"/>`;
   }
   const outline=[[-1,-1],[1,-1],[1,1],[-1,1]].map(p=>point(...p).join(',')).join(' '),center=project(face.normal),matrix=[dot(face.right,basis.right),-dot(face.right,basis.up),-dot(face.up,basis.right),dot(face.up,basis.up),...center];
   output+=`<polygon class="navigation-face-outline" points="${outline}"/><text class="navigation-face-label" transform="matrix(${matrix.join(' ')})" text-anchor="middle" dominant-baseline="middle">${face.id.toUpperCase()}</text>`;
  }return output;
 }
 update(view=this.view){
  if(view!==this.view||!this.host?.isConnected)return;if(this.mountedOwner!==this.owner()){this.attach(view,this.host);return;}
  const ready=this.ready(),basis=cameraBasis(view),key=[view.yaw,view.pitch,view.roll].map(n=>n.toFixed(7)).join(':'),host=this.host;
  if(key!==this.faceKey){const focused=host.contains(document.activeElement)?document.activeElement.dataset?.navTarget:null;host.querySelector('.navigation-faces').innerHTML=this.faces(basis,ready);this.faceKey=key;if(focused){const next=[...host.querySelectorAll('[data-nav-target]')].find(e=>e.dataset.navTarget===focused);(next||host.querySelector('[data-nav-action=home]')).focus();}}
  host.classList.toggle('mobile-visible',this.mobileVisible);host.querySelector('.navigation-radial').hidden=!this.radialOpen;
  const camera=host.querySelector('.navigation-camera'),cameraLabel=this.radialOpen?'Close camera options':'Open camera options';camera.setAttribute('aria-label',cameraLabel);camera.title=cameraLabel;camera.setAttribute('aria-expanded',String(this.radialOpen));if(camera.dataset.open!==String(this.radialOpen)){camera.innerHTML=icon(this.radialOpen?'close':'camera');camera.dataset.open=String(this.radialOpen);}
  const toggle=host.querySelector('.navigation-toggle'),toggleLabel=this.mobileVisible?'Hide view cube':'Show view cube';toggle.setAttribute('aria-label',toggleLabel);toggle.title=toggleLabel;
  const p=this.readSettings();for(const b of host.querySelectorAll('button'))b.disabled=!ready||b.hasAttribute('data-nav-setting')&&!view.renderer;
  for(const b of host.querySelectorAll('[data-nav-setting]')){const key=b.dataset.navSetting;if(key==='projection'){const label='Switch to '+(p.projection==='perspective'?'orthographic':'perspective');b.setAttribute('aria-label',label);b.title=label;b.setAttribute('aria-pressed',String(p.projection==='orthographic'));}else b.setAttribute('aria-pressed',String(p.style===key));}
  for(const target of host.querySelectorAll('[data-nav-target]')){target.setAttribute('aria-disabled',String(!ready));target.setAttribute('tabindex',ready?'0':'-1');}
  const degrees=Math.round(view.roll*180/Math.PI),status=directionLabel(basis.direction)+(degrees?` · ${degrees}°`:'');host.querySelector('.navigation-status').textContent=status;
 }
}
