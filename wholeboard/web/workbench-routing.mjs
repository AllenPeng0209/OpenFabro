import {adoptCopper,copperLayers,copperGeometry} from './workbench-copper.mjs';
import {beginPair,pairMode,recordSingle,extendPair,pairLayer,pairPreview,sectionPaths} from './workbench-diff-pair.mjs';
import {planInteractiveRoute,assertInteractivePaths,validateInteractiveVia,padLayers,createRouteBudget,RouteBudgetError} from './workbench-route-obstacles.mjs';
const near=(a,b)=>Math.hypot(a[0]-b[0],a[1]-b[1])<.0001;
const rounded=point=>point.map(value=>+value.toFixed(4));
const finitePoint=point=>Array.isArray(point)&&point.length===2&&point.every(value=>Number.isFinite(value));
const snapshot=session=>{const {history,...state}=session;return structuredClone(state);};
const history=(before,after)=>({...after,history:[...(before.history||[]),snapshot(before)]});
const contains=(item,point)=>{
  const dx=item.b[0]-item.a[0],dy=item.b[1]-item.a[1],length=dx*dx+dy*dy,t=length?((point[0]-item.a[0])*dx+(point[1]-item.a[1])*dy)/length:0;
  return t>=0&&t<=1&&near(point,[item.a[0]+t*dx,item.a[1]+t*dy]);
};

export function routePoints(a,b,{flip=false,free=false}={}){
  if(near(a,b))return[rounded(a)];
  const dx=b[0]-a[0],dy=b[1]-a[1],diagonal=Math.min(Math.abs(dx),Math.abs(dy));
  const corner=flip?[a[0]+Math.sign(dx)*diagonal,a[1]+Math.sign(dy)*diagonal]:Math.abs(dx)>Math.abs(dy)?[b[0]-Math.sign(dx)*Math.abs(dy),a[1]]:[a[0],b[1]-Math.sign(dy)*Math.abs(dx)];
  return(free?[a,b]:[a,corner,b]).map(rounded).filter((point,index,all)=>!index||!near(point,all[index-1]));
}

function inside(spec,point){
  if(!finitePoint(point)||point[0]<0||point[1]<0||point[0]>spec.board.width_mm||point[1]>spec.board.height_mm)throw new Error('Place the routing vertex inside the board.');
  return rounded(point);
}
export function resolve(spec,geometry,target){
  const layers=copperLayers(spec),[ox,oy]=geometry.bbox||[100,100],local=point=>rounded([point[0]-ox,point[1]-oy]);
  let item,point,available;
  if(target.kind==='pad'){
    item=geometry.pads.find(pad=>`${pad.ref}.${pad.name}`===target.pin&&(!target.padId||pad.id===target.padId));
    if(!item||item.kind==='np_thru_hole')throw new Error('Choose a connected copper pad.');
    point=local(item.routing_anchor||[item.x,item.y]);available=padLayers(item,layers);
  }else if(target.kind==='via'){
    item=geometry.vias.find(via=>via.id===target.id);if(!item)throw new Error('Choose an existing native via.');
    point=local(item.p);const span=item.layers||['F.Cu','B.Cu'],indices=span.map(layer=>layers.indexOf(layer));available=layers.filter((_,index)=>index>=Math.min(...indices)&&index<=Math.max(...indices));
  }else if(target.kind==='tracks'){
    item=geometry.tracks.find(track=>track.id===target.id);if(!item||!finitePoint(target.at))throw new Error('Choose a point on an existing trace.');
    const dx=item.b[0]-item.a[0],dy=item.b[1]-item.a[1],length=dx*dx+dy*dy,t=length?Math.max(0,Math.min(1,((target.at[0]-item.a[0])*dx+(target.at[1]-item.a[1])*dy)/length)):0;
    point=local([item.a[0]+t*dx,item.a[1]+t*dy]);available=[item.layer];
  }else throw new Error('Start or finish at a real pad, via or trace.');
  if(!item.net||!spec.nets.some(net=>net.name===item.net))throw new Error('Choose a terminal connected to an existing net.');
  return{point:inside(spec,point),net:item.net,layers:available,target:structuredClone(target)};
}

export function beginRoute(spec,geometry,target,settings={}){
  const anchor=resolve(spec,geometry,target),layers=copperLayers(spec),preferred=settings.layer||'F.Cu';
  if(!layers.includes(preferred))throw new Error('Choose a layer in the board stackup.');
  const layer=anchor.layers.includes(preferred)?preferred:anchor.layers[0];if(!layer)throw new Error('This terminal is not on a routing layer.');
  const power=spec.nets.find(net=>net.name===anchor.net)?.class==='power',width=settings.width??(power?spec.rules?.power_track_mm||.5:spec.rules?.track_mm||.25);
  if(!Number.isFinite(width)||width<=0||width>100)throw new Error('Choose a finite, positive trace width.');
  const pair=beginPair(spec,geometry,anchor,layer,settings,resolve);
  return{net:anchor.net,point:anchor.point,layer,width,obstacleMode:settings.obstacleMode||'walkaround',flip:false,free:false,startTarget:anchor,initialized:false,history:[],...(pair||{})};
}
export function setRouteMode(session,single){return pairMode(session,single);}
const pairTools={route:routePoints,resolve,adopt:adoptCopper,layers:copperLayers};

function planned(spec,geometry,state,a,b,paired=false){
 return planInteractiveRoute(spec,geometry,{net:state.net,layer:state.layer,width:paired?2*state.width+state.pair.gap:state.width,from:a,to:b,mode:state.obstacleMode||'walkaround',flip:state.flip,free:state.free,...(paired?{ignoreNets:state.pair.nets,ignoreIds:state.pair.managed}: {})});
}
function writeShoves(spec,shoves){
 for(const moved of shoves){const group=spec.fixed_copper?.find(g=>g.net===moved.net),index=group?.tracks?.findIndex(t=>t.id===moved.id);if(index===undefined||index<0||group.tracks[index].locked!==false)throw Error('The unprotected copper changed before this shove.');const original=group.tracks[index];group.tracks.splice(index,1,...moved.points.slice(1).map((p,i)=>({...structuredClone(original),id:i?crypto.randomUUID():original.id,a:[...moved.points[i]],b:[...p]})));}return spec;
}
function interactivePairTools(spec,geometry){
 const shoves=[],budget=createRouteBudget();return{...pairTools,shoves,route:(a,b,state,{end}={})=>{
  if(near(a,b))return[[...a]];
  const pair=state.pair,section=pair.sections[pair.active],full=geometry.obstacles||geometry,[ox,oy]=geometry.bbox||[100,100],clearance=spec.rules?.clearance_mm??.2;
  const leads=(terminals,centre,toward)=>{const delta=[terminals[0][0]-terminals[1][0],terminals[0][1]-terminals[1][1]],n=Math.hypot(...delta);if(n<.0001)return[];let d=[-delta[1]/n,delta[0]/n];if(d[0]*(toward[0]-centre[0])+d[1]*(toward[1]-centre[1])<0)d=d.map(v=>-v);let extent=state.width;
   for(const p of terminals){for(const pad of full.pads||[])if(near([pad.x-ox,pad.y-oy],p))extent=Math.max(extent,Math.hypot(pad.w,pad.h)/2);for(const via of full.vias||[])if(near([via.p[0]-ox,via.p[1]-oy],p))extent=Math.max(extent,via.d/2);}
   const length=extent+state.width+clearance+.02;return[1,-1].map(sign=>centre.map((v,i)=>+(v+d[i]*length*sign).toFixed(4)));};
  const starts=section.guide.length===1?leads(section.start,a,b):[],ends=end?leads(end,b,a):[],variants=[{start:null,end:null},...(starts.length?starts:[null]).flatMap(start=>(ends.length?ends:[null]).map(finish=>({start,end:finish})))];let lastError;
  for(const scale of [1,1.35,1.8])for(const variant of variants){try{
   const from=variant.start||a,to=variant.end||b,request={net:state.net,layer:state.layer,width:(2*state.width+pair.gap)*scale,from,to,mode:state.obstacleMode||'walkaround',flip:state.flip,free:state.free,ignoreNets:pair.nets,ignoreIds:pair.managed,budget},p=planInteractiveRoute(spec,geometry,request),points=[...(variant.start?[a]:[]),...p.points,...(variant.end?[b]:[])],candidate={...section,guide:[...section.guide,...points.slice(1)],...(end?{end}:{})},paths=sectionPaths(candidate,pair.clearance),view=copperGeometry(writeShoves(adoptCopper(spec,full),p.shoves),full);
   assertInteractivePaths(spec,view,paths.legs.flatMap((leg,i)=>leg.slice(1).map((point,j)=>({net:pair.nets[i],layer:state.layer,width:paths.widths[i][j],points:[leg[j],point]}))),{ignoreIds:pair.managed,budget});shoves.push(...p.shoves);return points;
  }catch(error){if(error instanceof RouteBudgetError)throw error;lastError=error;}}
  throw lastError||Error('No clear paired fanout was found. Place a nearer waypoint.');
 }};
}
function pairResult(spec,geometry,session,result,shoves){
 writeShoves(result.spec,shoves);const ids=new Set([...(session.pair?.managed||[]),...(result.session.pair?.managed||[])]),full=copperGeometry(result.spec,geometry.obstacles||geometry),paths=(result.spec.fixed_copper||[]).flatMap(g=>(g.tracks||[]).filter(t=>ids.has(t.id)).map(t=>({net:g.net,layer:t.layer,width:t.w,points:[t.a,t.b]})));
 assertInteractivePaths(spec,full,paths,{ignoreIds:[...ids]});for(const group of result.spec.fixed_copper||[])for(const v of group.vias||[])if(ids.has(v.id))validateInteractiveVia(spec,full,{...v,net:group.net,ignoreIds:[...ids]});return{...result,shoves};
}

function groupFor(spec,net){spec.fixed_copper||=[];let group=spec.fixed_copper.find(group=>group.net===net);if(!group){group={net,tracks:[],arcs:[],vias:[]};spec.fixed_copper.push(group);}for(const kind of ['tracks','arcs','vias'])group[kind]||=[];return group;}
function splitAnchor(spec,anchor,layer){
  if(anchor.target.kind!=='tracks')return;
  const group=groupFor(spec,anchor.net),index=group.tracks.findIndex(track=>track.id===anchor.target.id&&track.layer===layer&&contains(track,anchor.point));
  if(index<0)throw Error('The selected trace changed before branching.');const track=group.tracks[index];if(track.locked!==false||near(track.a,anchor.point)||near(track.b,anchor.point))return;
  const tail={...structuredClone(track),id:crypto.randomUUID(),a:[...anchor.point]};track.b=[...anchor.point];group.tracks.splice(index+1,0,tail);
}

function append(spec,geometry,session,target,settings){
  if(!spec.nets.some(net=>net.name===session.net))throw new Error('The routing net changed. Start a new trace.');
  const destination=target.kind==='point'?{point:inside(spec,target.at),net:session.net,layers:[session.layer]}:resolve(spec,geometry,target);
  if(destination.net!==session.net)throw new Error('Finish on the same net. The current route remains active.');
  if(!destination.layers.includes(session.layer))throw new Error('This terminal is on another layer. Add a via before connecting it.');
  const out=session.initialized?structuredClone(spec):adoptCopper(spec,geometry),state={...structuredClone(session),...settings};
  if(!Number.isFinite(state.width)||state.width<=0||state.width>100)throw new Error('Choose a finite, positive trace width.');
  if(!session.initialized)splitAnchor(out,session.startTarget,session.layer);
  if(target.kind!=='point')splitAnchor(out,destination,session.layer);
  const route=planned(spec,geometry,state,session.point,destination.point);writeShoves(out,route.shoves);const group=groupFor(out,session.net),points=route.points;
  for(let index=1;index<points.length;index++)group.tracks.push({id:crypto.randomUUID(),a:points[index-1],b:points[index],w:state.width,layer:session.layer});
  return{spec:out,session:{...state,point:destination.point,initialized:true},finished:target.kind!=='point',shoves:route.shoves};
}

export function extendRoute(spec,geometry,session,target,settings={}){
  const tools=interactivePairTools(spec,geometry),result=session.pair&&!session.single?pairResult(spec,geometry,session,extendPair(spec,geometry,session,target,settings,tools),tools.shoves):recordSingle(append(spec,geometry,session,target,settings));result.session=history(session,result.session);return result;
}

export function changeRouteLayer(spec,geometry,session,at,nextLayer,settings={}){
  const layers=copperLayers(spec);if(layers.length<2||!layers.includes(nextLayer)||nextLayer===session.layer)throw new Error('Choose a different copper layer in this board.');
  if(session.pair&&!session.single){const tools=interactivePairTools(spec,geometry),result=pairResult(spec,geometry,session,pairLayer(spec,geometry,session,at,nextLayer,settings,tools),tools.shoves);result.session=history(session,result.session);return result;}
  const diameter=settings.diameter??spec.rules?.via_diameter_mm??.6,drill=settings.drill??spec.rules?.via_drill_mm??.3;
  if(!Number.isFinite(diameter)||!Number.isFinite(drill)||drill<=0||diameter<=drill||diameter>10)throw new Error('The via diameter must exceed its positive drill diameter.');
  const [ox,oy]=geometry.bbox||[100,100],pad=(geometry.obstacles||geometry).pads?.find(p=>p.net===session.net&&p.kind==='thru_hole'&&near((p.routing_anchor||[p.x,p.y]).map((v,i)=>v-[ox,oy][i]),at)&&padLayers(p,layers).includes(nextLayer)&&padLayers(p,layers).includes(session.layer));
  if(pad){const result=near(session.point,at)?{spec,session:structuredClone(session),finished:false}:append(spec,geometry,session,{kind:'point',at},{});result.session=history(session,{...result.session,layer:nextLayer});return result;}
  const result=append(spec,geometry,session,{kind:'point',at},{}),group=groupFor(result.spec,session.net),existing=group.vias.find(via=>near(via.p,result.session.point));
  if(existing){const indices=(existing.layers||['F.Cu','B.Cu']).map(layer=>layers.indexOf(layer));if(![session.layer,nextLayer].every(layer=>layers.indexOf(layer)>=Math.min(...indices)&&layers.indexOf(layer)<=Math.max(...indices)))throw new Error('The existing via does not span both routing layers.');}
  else{validateInteractiveVia(spec,copperGeometry(result.spec,geometry.obstacles||geometry),{net:session.net,p:result.session.point,d:diameter,drill,layers:['F.Cu','B.Cu']});group.vias.push({id:crypto.randomUUID(),p:[...result.session.point],d:diameter,drill,layers:['F.Cu','B.Cu'],type:'through'});}
  result.session=history(session,{...result.session,layer:nextLayer});return recordSingle(result);
}
export function previewRoute(spec,geometry,session,target){
 if(session.pair&&!session.single){const tools=interactivePairTools(spec,geometry),result=pairPreview(spec,geometry,session,target,tools),full=copperGeometry(writeShoves(adoptCopper(spec,geometry.obstacles||geometry),tools.shoves),geometry.obstacles||geometry);assertInteractivePaths(spec,full,result.paths,{ignoreIds:session.pair.managed});return{...result,shoves:tools.shoves,hideIds:[...session.pair.managed,...tools.shoves.map(s=>s.id)]};}
 const dest=target.kind==='point'?{point:inside(spec,target.at),net:session.net,layers:[session.layer]}:resolve(spec,geometry,target);
 if(dest.net!==session.net)throw Error('Finish on the same net. The current route remains active.');
 if(!dest.layers.includes(session.layer))throw Error('This terminal is on another layer. Add a via before connecting it.');
 const result=planned(spec,geometry,session,session.point,dest.point);return{paths:[{net:session.net,layer:session.layer,width:session.width,points:result.points}],shoves:result.shoves,hideIds:result.shoves.map(s=>s.id)};
}
