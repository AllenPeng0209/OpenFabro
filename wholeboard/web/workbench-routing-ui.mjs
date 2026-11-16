import {beginRoute,extendRoute,changeRouteLayer,routePoints,setRouteMode,previewRoute,resolve as resolveRouteTarget} from './workbench-routing.mjs';
import {copperGeometry,copperLayers} from './workbench-copper.mjs';
import {esc,icon} from './workbench-icons.mjs';

export class RoutingUI{
  constructor(deps){Object.assign(this,deps);this.committing=false;this.undoing=false;this.redo=[];}
  get active(){return !!this.state().routeSession;}
  scope(){const s=this.state();return JSON.stringify([s.pid,s.projectLoadToken,s.session?.user?.id||s.project?.access?.user?.id||'device']);}
  current(){const s=this.state();return !this.active||this.owner===this.scope()&&this.expectedGeneration===s.generation;}
  get optimistic(){const s=this.state();return this.active&&s.routeSession.initialized&&this.expectedGeneration===s.generation;}
  ready(layer=null){const s=this.state();if(!this.current()){this.stop();throw Error('The design or route owner changed. Start a new route.');}if(!this.editable()||this.busy()||s.nativePending&&!this.optimistic)throw new Error('Wait for the current editable layout before routing.');if(s.active&&s.active!=='layout'||!s.canvas?.geo)throw new Error('Open the PCB layout before routing.');const target=layer||s.routeSession?.layer||s.routingLayer||'F.Cu';if(s.canvas.layerRules?.visible('tracks',{layer:target})===false)throw Error(`Show ${target} traces before routing.`);}
  geometry(){const c=this.state().canvas;return{...c.geo,pads:c.geo.pads.filter(p=>c._shown?.('pads',p)!==false),obstacles:c.geo};}
  guard(action){try{return action();}catch(error){this.toast(error.message,true);}}
  toggle(){
    const s=this.state();if(s.routing||this.active){this.stop();return;}
    this.ready();s.viaPlacing=null;document.querySelector('#viaButton').setAttribute('aria-pressed','false');
    s.routing=true;this.sync();this.toast('Choose a pad, via or existing trace. Click to place corners; V changes layer.');
  }
  stop(){
    const s=this.state();s.routeSession=null;s.routeStart=null;s.routing=false;this.baseGeometry=null;this.redo=[];this.expectedGeneration=null;this.owner=null;this.modeError='';
    if(!s.selected)s.selectedNet=null;this.sync();this.updateContext();
  }
  target(target,event={}){
    this.ready();const s=this.state(),geometry=this.geometry();
    if(!this.active){
      if(target.kind==='point')return;
      s.viaPlacing=null;document.querySelector('#viaButton').setAttribute('aria-pressed','false');
      const session=beginRoute(s.spec,geometry,target,{layer:s.routingLayer||'F.Cu',width:s.routingWidth||undefined,gap:s.routingGap?Math.max(s.routingGap,s.spec.rules?.clearance_mm??.2):undefined,profiles:s.routingProfiles,single:!!(event.ctrlKey||event.metaKey)});this.ready(session.layer);s.routeSession=session;this.owner=this.scope();this.expectedGeneration=s.generation;this.modeError='';
      if(session.pair){const[ox,oy]=geometry.bbox||[100,100];s.routePointerWorld=session.point.map((n,i)=>n+[ox,oy][i]);s.routePointerClient=null;}
      this.baseGeometry=structuredClone(s.canvas.geo);this.redo=[];s.routing=true;s.selected=null;s.selectedCopper=null;s.selection.clear();s.selectedNet=s.routeSession.net;s.inspector=false;
      s.canvas.selectCopper?.(null);this.renderInspector();this.updateContext();this.sync();return;
    }
    this.mode(!!(event.ctrlKey||event.metaKey));const result=extendRoute(s.spec,geometry,s.routeSession,this.continuationTarget(target,!!event.shiftKey),{free:!!event.shiftKey});this.apply(result,s.routeSession.pair&&!s.routeSession.single?'Placed pair vertex':'Placed routing vertex');
  }
  point(x,y,event={}){
    const s=this.state();if(!this.active)return;const [ox,oy]=s.canvas.geo.bbox||[100,100],grid=s.boardGrid||.5;
    const at=[x-ox,y-oy].map(value=>event.shiftKey?+value.toFixed(4):+(Math.round(value/grid)*grid).toFixed(4));
    this.target({kind:'point',at},event);
  }
  pointer(x,y,event={}){
    const s=this.state();s.routePointerWorld=[x,y];if(Number.isFinite(event.clientX))s.routePointerClient=[event.clientX,event.clientY];
    if(this.active){if(!this.current()){this.stop();return;}this.mode(!!(event.ctrlKey||event.metaKey),false,true);s.routeSession.free=!!event.shiftKey;s.canvas.routeFree=!!event.shiftKey;}
  }
  mode(single,refresh=true,quiet=false){const s=this.state();if(!s.routeSession?.pair||s.routeSession.single===single)return;try{this.ready();s.routeSession=setRouteMode(s.routeSession,single);this.modeError='';if(refresh)this.sync();else{const[ox,oy]=s.canvas.geo.bbox||[100,100];s.canvas.routeStart=s.routeSession.point.map((v,i)=>v+[ox,oy][i]);this.render();}}catch(error){this.modeError=error.message;this.previewError(error.message);if(!quiet)throw error;}}
  gap(value){this.ready();const s=this.state();if(!s.routeSession?.pair)return;const clearance=s.spec.rules?.clearance_mm??.2;if(!Number.isFinite(value)||value<=0||value>100||value<clearance)throw Error('Pair gap must be positive and meet the current board clearance.');s.routeSession.pair.gap=value;s.routingGap=value;this.sync();}
  continuationTarget(target,free=false){
    const s=this.state(),session=s.routeSession,pair=session?.pair;
    if(target?.kind==='tracks'&&s.canvas.geo.tracks.find(t=>t.id===target.id)?.net!==session.net){const[ox,oy]=s.canvas.geo.bbox||[100,100],grid=s.boardGrid||.5;return{kind:'point',at:target.at.map((v,i)=>{v-=[ox,oy][i];return free?+v.toFixed(4):+(Math.round(v/grid)*grid).toFixed(4);})};}
    if(!pair||session.single)return target;
    if(target?.kind==='via'){
      const section=pair.sections.find(section=>section.vias?.some(v=>v.id===target.id));
      if(section)return{kind:'point',at:section.vias[0].p.map((v,i)=>+( (v+section.vias[1].p[i])/2).toFixed(4))};
    }
    if(target?.kind==='tracks'&&pair.managed.includes(target.id)){
      const [ox,oy]=s.canvas.geo.bbox||[100,100],grid=s.boardGrid||.5;
      return{kind:'point',at:target.at.map((v,i)=>{v-=[ox,oy][i];return free?+v.toFixed(4):+(Math.round(v/grid)*grid).toFixed(4);})};
    }
    return target;
  }
  preview(world,target){
    const s=this.state(),session=s.routeSession;if(!session||!this.current())return null;const[ox,oy]=s.canvas.geo.bbox||[100,100],grid=s.boardGrid||.5,at=[world[0]-ox,world[1]-oy].map(n=>session.free?+n.toFixed(4):+(Math.round(n/grid)*grid).toFixed(4));let result;
    try{result=previewRoute(s.spec,this.geometry(),session,this.continuationTarget(target,session.free)||{kind:'point',at});}
    catch(error){this.previewError(error.message);return{error:error.message};}
    const shoves=result.shoves||[],nets=[...new Set(shoves.map(p=>p.net))];this.previewError(this.modeError||(shoves.length?`Move ${shoves.length} unprotected trace${shoves.length===1?'':'s'} · ${nets.join(', ')}`:''),!this.modeError&&!!shoves.length);
    return{paths:[...result.paths,...shoves.map(p=>({net:p.net,layer:p.layer,width:p.width,points:p.points,shoved:true}))].map(p=>({...p,points:p.points.map(p=>[p[0]+ox,p[1]+oy])})),hideIds:result.hideIds||[],vias:result.vias?.map(v=>({...v,p:[v.p[0]+ox,v.p[1]+oy]}))||[]};
  }
  previewError(message,info=false){const node=document.querySelector('#pairRouteMessage');if(node){if(node.textContent!==message)node.textContent=message;node.hidden=!message;node.dataset.tone=info?'info':'error';}}
  behavior(value){this.ready();if(!['walkaround','shove'].includes(value))throw Error('Choose walkaround or shove behavior.');this.state().routeSession.obstacleMode=value;this.sync();}
  cursorPoint(){
    const s=this.state(),[ox,oy]=s.canvas.geo.bbox||[100,100],world=s.routePointerWorld||s.routeSession.point.map((v,i)=>v+[ox,oy][i]),grid=s.boardGrid||.5;
    const target=s.canvas._routingTarget?.(...world);
    if(s.routeSession.pair&&!s.routeSession.single){
      if(target?.kind==='via'){const anchor=this.continuationTarget(target,s.routeSession.free);if(anchor.kind==='point')return anchor.at;}
      if(Math.hypot(world[0]-ox-s.routeSession.point[0],world[1]-oy-s.routeSession.point[1])<.0001)return[...s.routeSession.point];
    }else if(target&&(target.kind==='via'||target.kind==='pad'&&s.canvas.geo.pads.find(p=>target.padId?p.id===target.padId:p.ref+'.'+p.name===target.pin)?.kind==='thru_hole')){
      try{const anchor=resolveRouteTarget(s.spec,this.geometry(),target);if(anchor.net===s.routeSession.net&&anchor.layers.includes(s.routeSession.layer))return anchor.point;}catch{/* Free-space placement still uses the current grid and native checks. */}
    }
    const at=[world[0]-ox,world[1]-oy].map(value=>s.routeSession.free?+value.toFixed(4):+(Math.round(value/grid)*grid).toFixed(4));
    return at.every(Number.isFinite)&&at[0]>=0&&at[1]>=0&&at[0]<=s.spec.board.width_mm&&at[1]<=s.spec.board.height_mm?at:[...s.routeSession.point];
  }
  changeLayer(layer){
    const s=this.state();if(!this.active){s.routingLayer=layer;this.sync();return;}
    this.ready(layer);if(layer===s.routeSession.layer)return;
    this.apply(changeRouteLayer(s.spec,this.geometry(),s.routeSession,this.cursorPoint(),layer),s.routeSession.pair&&!s.routeSession.single?'Changed pair routing layer':'Changed route layer');
  }
  via(){const s=this.state(),layers=copperLayers(s.spec);this.changeLayer(layers[(layers.indexOf(s.routeSession.layer)+1)%layers.length]);}
  widths(){const s=this.state();return[...new Set([.15,.2,.25,.35,.5,1,s.spec.rules?.track_mm||.25,s.spec.rules?.power_track_mm||.5,s.routeSession?.pair?.profile?.width_mm,...(s.spec.rules?.preferred_track_mm||[])])].filter(v=>Number.isFinite(v)&&v>0&&v<=100).sort((a,b)=>a-b);}
  width(value){
    const s=this.state();if(this.active)this.ready();s.routingWidth=value||null;
    if(this.active){const power=s.spec.nets.find(n=>n.name===s.routeSession.net)?.class==='power';s.routeSession.width=value||(power?s.spec.rules?.power_track_mm||.5:s.spec.rules?.track_mm||.25);}
    this.sync();
  }
  cycleWidth(backward){const s=this.state(),widths=this.widths(),at=widths.indexOf(s.routeSession.width),index=(at+(backward?-1:1)+widths.length)%widths.length;this.width(widths[index]);}
  captureLocal(){
    const s=this.state(),keys=['routeSession','routeStart','routing','selectedNet','undo','redo','actions','selection','selected','selectedSymbolKey','dirty'],fields=keys.map(key=>({key,present:Object.hasOwn(s,key),value:Array.isArray(s[key])?[...s[key]]:s[key] instanceof Set?new Set(s[key]):s[key]}));
    return{spec:s.spec,generation:s.generation,fields,geometry:s.canvas?.geo,base:this.baseGeometry,redo:[...this.redo],owner:this.owner,expected:this.expectedGeneration,modeError:this.modeError};
  }
  recoverLocal(before){
    const s=this.state();
    // commit/undoDesign are synchronous local source transactions. Networking
    // belongs to the workbench and retains unsaved drafts on a rejected save.
    if(s.spec!==before.spec||s.generation!==before.generation)return;
    for(const field of before.fields)if(field.present)s[field.key]=field.value;else delete s[field.key];
    if(s.canvas)s.canvas.geo=before.geometry;this.baseGeometry=before.base;this.redo=before.redo;this.owner=before.owner;this.expectedGeneration=before.expected;this.modeError=before.modeError;
    this.sync();this.updateContext();
  }
  apply(result,label){
    if(result.shoves?.length)label+=` · moved ${result.shoves.length} unprotected trace${result.shoves.length===1?'':'s'}`;
    const s=this.state(),before=this.captureLocal(),changed=JSON.stringify(result.spec)!==JSON.stringify(s.spec),geometry=changed?copperGeometry(result.spec,s.canvas.geo):s.canvas.geo;
    try{
    result.session.history.at(-1).designChanged=changed;
    if(result.finished){this.stop();}else{s.routeSession=result.session;s.routing=true;this.redo=[];}
    s.canvas.geo=geometry;this.expectedGeneration=s.generation+(changed?1:0);
    this.committing=true;
    try{if(changed){this.commit(result.spec,label,null);if(s.generation!==before.generation+1||s.spec!==result.spec&&JSON.stringify(s.spec)!==JSON.stringify(result.spec))throw Error('The local source update was not accepted.');}}finally{this.committing=false;}
    this.sync();
    }catch(error){this.committing=false;this.recoverLocal(before);throw error;}
  }
  restoreGeometry(){
    const s=this.state();if(!this.active||!s.canvas?.geo)return;
    s.canvas.geo=s.routeSession.initialized?copperGeometry(s.spec,s.canvas.geo):structuredClone(this.baseGeometry);
  }
  undo(redo=false){
    const s=this.state();this.ready();const before=this.captureLocal(),target=(redo?s.redo:s.undo)?.at(-1);let designChanged;
    try{
    if(redo){const entry=this.redo.at(-1);if(!entry)return;if(entry.designChanged&&!s.redo?.length)return this.toast('Nothing left to redo');this.redo.pop();designChanged=entry.designChanged;s.routeSession=entry.session;}
    else{
      const session=s.routeSession,prior=session.history.at(-1);if(!prior)return;
      designChanged=prior.designChanged!==false;if(designChanged&&!s.undo.length)return this.toast('Nothing left to undo');this.redo.push({session:structuredClone(session),designChanged});
      const {designChanged:ignored,...state}=prior;s.routeSession={...state,history:session.history.slice(0,-1)};
    }
    if(designChanged){this.expectedGeneration=s.generation+1;this.undoing=true;try{this.undoDesign(redo);if(s.generation!==before.generation+1||s.spec!==target&&JSON.stringify(s.spec)!==JSON.stringify(target))throw Error('The local source undo was not accepted.');}finally{this.undoing=false;}}
    else this.restoreGeometry();
    this.sync();
    }catch(error){this.undoing=false;this.recoverLocal(before);throw error;}
  }
  key(event){
    const s=this.state(),key=event.key.toLowerCase(),cmd=event.metaKey||event.ctrlKey;
    if(!this.active){if(s.routing&&key==='escape'){event.preventDefault();this.stop();return true;}return false;}
    if((key==='control'||key==='meta')&&s.routeSession.pair){if(!event.repeat)this.guard(()=>this.mode(true));return false;}
    if(key==='shift'){s.routeSession.free=true;this.sync();return false;}
    if(cmd&&key==='z'){event.preventDefault();this.guard(()=>this.undo(event.shiftKey));return true;}
    if(cmd&&!(s.routeSession.pair&&['f','w','v'].includes(key)))return false;
    if(key==='escape'){event.preventDefault();this.stop();return true;}
    if(key==='backspace'){event.preventDefault();this.guard(()=>this.undo());return true;}
    if(key==='f'){event.preventDefault();s.routeSession.flip=!s.routeSession.flip;this.sync();return true;}
    if(key==='w'){event.preventDefault();this.cycleWidth(event.shiftKey);return true;}
    if(key==='v'){event.preventDefault();this.guard(()=>this.via());return true;}
    return false;
  }
  keyUp(event){if(!this.active)return;if(event.key==='Control'||event.key==='Meta')this.guard(()=>this.mode(!!(event.ctrlKey||event.metaKey)));if(event.key==='Shift'&&this.active){this.state().routeSession.free=false;this.sync();}}
  sync(){
    if(!this.current()){this.stop();return;}
    const s=this.state(),canvas=s.canvas,session=s.routeSession;
    document.querySelector('#routeButton').setAttribute('aria-pressed',String(!!s.routing));
    if(session){s.routingLayer=session.layer;s.routeStart=session.startTarget.target;s.selectedNet=session.net;}
    if(canvas?.geo){
      const [ox,oy]=canvas.geo.bbox||[100,100];canvas.routing=!!s.routing;canvas.routeStart=session?[session.point[0]+ox,session.point[1]+oy]:null;
      canvas.routingLayer=session?.layer||s.routingLayer||'F.Cu';canvas.routingWidth=session?.width||s.routingWidth||s.spec?.rules?.track_mm||.25;canvas.routeFlip=!!session?.flip;canvas.routeFree=!!session?.free;
      if(s.routePointerClient){s.routePointerWorld=canvas._world({clientX:s.routePointerClient[0],clientY:s.routePointerClient[1]});canvas.pointerWorld=s.routePointerWorld;}else canvas.pointerWorld=null;
      canvas.placingVia=!!s.viaPlacing;
      canvas.draw();
    }
    this.render();
  }
  render(){
    const s=this.state(),host=document.querySelector('#viewContent'),session=s.routeSession;let status=document.querySelector('#routingStatus');
    if(s.active!=='layout'||!session){status?.remove();return;}
    if(!status){
      status=document.createElement('div');status.id='routingStatus';status.className='routing-status';status.setAttribute('role','group');status.setAttribute('aria-label','Active PCB route');
      status.innerHTML=`<strong class="route-net"></strong><span class="route-partner"></span><select aria-label="Obstacle routing behavior" id="activeRouteBehavior"><option value="walkaround">Walkaround</option><option value="shove">Shove unprotected</option></select><select aria-label="Active routing layer" id="activeRouteLayer"></select><select aria-label="Active trace width" id="activeRouteWidth"></select><label class="pair-gap-control" title="Parallel-rail spacing; pad and via fanouts meet board clearance." hidden>Gap<input id="activePairGap" type="number" step="0.01" min="0" aria-label="Nominal pair gap (mm)"></label><button id="routeViaNext" title="Next layer with via (V)">${icon('via')}<span>V</span></button><button id="finishRouting" title="Finish drawing (Esc)">${icon('check')}<span>Esc</span></button><small>Click corner · F flip · W width · ⌫ undo</small><span id="pairRouteMessage" role="status" hidden></span>`;
      host.append(status);status.querySelector('#activeRouteLayer').onchange=e=>this.guard(()=>this.changeLayer(e.target.value));status.querySelector('#activeRouteWidth').onchange=e=>this.width(Number(e.target.value));status.querySelector('#routeViaNext').onclick=()=>this.guard(()=>this.via());status.querySelector('#finishRouting').onclick=()=>this.stop();
      status.querySelector('#activePairGap').onchange=e=>this.guard(()=>this.gap(Number(e.target.value)));
      status.querySelector('#activeRouteBehavior').onchange=e=>this.guard(()=>this.behavior(e.target.value));
    }
    for(const [key,value]of Object.entries({net:session.net,layer:session.layer,width:session.width,x:session.point[0],y:session.point[1],flipped:!!session.flip}))status.dataset[key]=String(value);
    status.querySelector('.route-net').textContent=session.net;
    status.dataset.mode=session.pair&&!session.single?'pair':'single';status.dataset.partner=session.pair?.nets[1]||'';status.dataset.gap=String(session.pair?.gap||'');status.querySelector('.route-partner').textContent=session.pair?`${session.single?'· parked':'/'} ${session.pair.nets[1]}`:'';
    const gap=status.querySelector('#activePairGap');gap.parentElement.hidden=!session.pair;gap.value=session.pair?.gap||'';gap.min=s.spec.rules?.clearance_mm??.2;
    const layer=status.querySelector('#activeRouteLayer'),width=status.querySelector('#activeRouteWidth');
    layer.innerHTML=copperLayers(s.spec).map(value=>`<option ${value===session.layer?'selected':''}>${esc(value)}</option>`).join('');
    width.innerHTML=[...new Set([...this.widths(),session.width])].sort((a,b)=>a-b).map(value=>`<option value="${value}" ${value===session.width?'selected':''}>${value} mm</option>`).join('');
    const disabled=!this.editable()||this.busy()||s.nativePending&&!this.optimistic;layer.disabled=disabled;width.disabled=disabled;status.querySelector('#routeViaNext').disabled=disabled||copperLayers(s.spec).length<2;
    gap.disabled=disabled||!!session.single;
    const behavior=status.querySelector('#activeRouteBehavior');behavior.value=session.obstacleMode||'walkaround';behavior.disabled=disabled;
    if(this.modeError)this.previewError(this.modeError);
  }
}
