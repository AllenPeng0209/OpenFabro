// Continuous geometric clearance checks and bounded interactive path planning.
// Native DRC remains authoritative for electrical rules and manufacturing.
const EPS=1e-8,SAFE=.003,TAU=2*Math.PI;
export class RouteBudgetError extends Error{}
export const createRouteBudget=()=>({operations:0,candidates:0,maxOperations:2000000,maxCandidates:2000});
function charge(budget,count=1){if(budget&&(budget.operations+=count)>budget.maxOperations)throw new RouteBudgetError('Interactive routing work budget reached. Place a nearer waypoint.');}
const add=(a,b)=>[a[0]+b[0],a[1]+b[1]],sub=(a,b)=>[a[0]-b[0],a[1]-b[1]],mul=(a,k)=>[a[0]*k,a[1]*k],dot=(a,b)=>a[0]*b[0]+a[1]*b[1],cross=(a,b)=>a[0]*b[1]-a[1]*b[0];
const dist=(a,b)=>Math.hypot(...sub(a,b)),round=p=>p.map(v=>+v.toFixed(4)),near=(a,b)=>dist(a,b)<.0001;
const finite=p=>Array.isArray(p)&&p.length===2&&p.every(Number.isFinite);
const identical=(a,b)=>a[0]===b[0]&&a[1]===b[1];
const bounds=(ps,r=0)=>[Math.min(...ps.map(p=>p[0]))-r,Math.min(...ps.map(p=>p[1]))-r,Math.max(...ps.map(p=>p[0]))+r,Math.max(...ps.map(p=>p[1]))+r];
const overlap=(a,b)=>a[0]<=b[2]+EPS&&b[0]<=a[2]+EPS&&a[1]<=b[3]+EPS&&b[1]<=a[3]+EPS;
function projection(p,a,b){const d=sub(b,a),n=dot(d,d);return add(a,mul(d,n?Math.max(0,Math.min(1,dot(sub(p,a),d)/n)):0));}
function intersection(a,b,c,d){const v=sub(b,a),w=sub(d,c),den=cross(v,w);if(den===0)return null;const t=cross(sub(c,a),w)/den,u=cross(sub(c,a),v)/den;return t>=-EPS&&t<=1+EPS&&u>=-EPS&&u<=1+EPS?add(a,mul(v,t)):null;}
function segmentDistance(a,b,c,d){if(intersection(a,b,c,d))return 0;return Math.min(dist(a,projection(a,c,d)),dist(b,projection(b,c,d)),dist(c,projection(c,a,b)),dist(d,projection(d,a,b)));}
function inside(p,poly){let on=false;for(let i=0,j=poly.length-1;i<poly.length;j=i++){const a=poly[i],b=poly[j];if((a[1]>p[1])!==(b[1]>p[1])&&p[0]<(b[0]-a[0])*(p[1]-a[1])/(b[1]-a[1])+a[0])on=!on;}return on;}
function edges(points,closed=false){return points.length===1?[[points[0],points[0]]]:points.slice(1).map((p,i)=>[points[i],p]).concat(closed?[[points.at(-1),points[0]]]:[]);}
function feature(points,r=0,extra={}){if(!points.length||points.some(p=>!finite(p))||!Number.isFinite(r)||r<0)throw Error('Unknown native obstacle geometry. Refresh the layout.');return{points,r,box:bounds(points,r),edges:edges(points,extra.closed),...extra};}
function onArc(arc,p){const angle=Math.atan2(p[1]-arc.c[1],p[0]-arc.c[0]),n=((angle-arc.start)*arc.dir%TAU+TAU)%TAU;return n<=arc.span+1e-10;}
function pointArc(p,arc){return onArc(arc,p)?Math.abs(dist(p,arc.c)-arc.r):Math.min(dist(p,arc.a),dist(p,arc.b));}
function segmentArc(a,b,arc){
 const v=sub(b,a),size=dot(v,v);if(size<EPS*EPS)return pointArc(a,arc);let best=Math.min(pointArc(a,arc),pointArc(b,arc),dist(arc.a,projection(arc.a,a,b)),dist(arc.b,projection(arc.b,a,b))),offset=sub(a,arc.c),bb=2*dot(offset,v),cc=dot(offset,offset)-arc.r*arc.r,disc=bb*bb-4*size*cc;
 if(disc>=0)for(const t of [(-bb-Math.sqrt(disc))/(2*size),(-bb+Math.sqrt(disc))/(2*size)])if(t>=0&&t<=1&&onArc(arc,add(a,mul(v,t))))return 0;
 const length=Math.sqrt(size),normal=[-v[1]/length,v[0]/length];for(const sign of [1,-1]){const p=add(arc.c,mul(normal,sign*arc.r)),t=dot(sub(p,a),v)/size;if(t>=0&&t<=1&&onArc(arc,p))best=Math.min(best,dist(p,projection(p,a,b)));}return best;
}
function separation(a,b,f){if(f.arc)return segmentArc(a,b,f.arc);if(f.closed&&(inside(a,f.points)||inside(b,f.points)))return 0;return Math.min(...f.edges.map(([c,d])=>segmentDistance(a,b,c,d)));}
function guide(a,b,{flip=false,free=false}={}){if(identical(a,b))return[[...a]];const dx=b[0]-a[0],dy=b[1]-a[1],n=Math.min(Math.abs(dx),Math.abs(dy)),c=flip?[a[0]+Math.sign(dx)*n,a[1]+Math.sign(dy)*n]:Math.abs(dx)>Math.abs(dy)?[b[0]-Math.sign(dx)*Math.abs(dy),a[1]]:[a[0],b[1]-Math.sign(dy)*Math.abs(dx)],grid=[...a,...b].every(v=>+v.toFixed(4)===v);return(free?[a,b]:[a,grid?round(c):c,b]).map(p=>[...p]).filter((p,i,all)=>!i||!identical(p,all[i-1]));}
function compact(points,anchors=[]){const out=[];for(const p of points){if(out.length&&identical(p,out.at(-1)))continue;while(out.length>1){const a=out.at(-2),b=out.at(-1),u=sub(b,a),v=sub(p,b);if(anchors.some(q=>identical(q,b))||cross(u,v)!==0||dot(u,v)<0)break;out.pop();}out.push([...p]);}return out;}
function validatedCompact(world,points,anchors=[]){const result=compact(points,anchors);if(result.length===points.length)return points;try{return world.pathClear(result)?result:points;}catch(error){if(error instanceof RouteBudgetError)return points;throw error;}}
function arcPoints(a,m,b){
 const den=2*cross(sub(m,a),sub(b,a));if(Math.abs(den)<EPS)return{points:[a,m,b],sag:0};const aa=dot(a,a),mm=dot(m,m),bb=dot(b,b),c=[(aa*(m[1]-b[1])+mm*(b[1]-a[1])+bb*(a[1]-m[1]))/den,(aa*(b[0]-m[0])+mm*(a[0]-b[0])+bb*(m[0]-a[0]))/den],r=dist(a,c),angle=p=>Math.atan2(p[1]-c[1],p[0]-c[0]),norm=x=>(x%TAU+TAU)%TAU,start=angle(a),dir=norm(angle(m)-start)<=norm(angle(b)-start)?1:-1,span=norm(dir*(angle(b)-start)),step=2*Math.acos(Math.max(-1,1-.001/Math.max(r,.001))),count=Math.max(2,Math.ceil(span/Math.max(step,.00001)));
 if(count>4096)throw Error('This curved obstacle exceeds the interactive geometry budget.');return{points:Array.from({length:count+1},(_,i)=>add(c,[r*Math.cos(start+dir*span*i/count),r*Math.sin(start+dir*span*i/count)])),sag:r*(1-Math.cos(span/count/2)),arc:{c,r,start,dir,span,a,b}};
}
export function padLayers(p,layers){const explicit=p.layers;if(explicit?.length)return explicit.includes('*.Cu')?layers:layers.filter(l=>explicit.includes(l));return p.kind==='thru_hole'?layers:[...(p.front!==false?['F.Cu']:[]),...(p.back?['B.Cu']:[])];}
function padShape(p,local,layers){
 const centre=local([p.x,p.y]),angle=(p.rot||0)*Math.PI/180,rotate=([x,y])=>add(centre,[x*Math.cos(angle)+y*Math.sin(angle),-x*Math.sin(angle)+y*Math.cos(angle)]);
 if(p.kind==='np_thru_hole'){
  const size=p.drill_size||[p.drill,p.drill],offset=p.drill_offset||[0,0];if(!size?.every(v=>Number.isFinite(v)&&v>0))throw Error('Unknown nonplated hole geometry.');const r=Math.min(...size)/2,d=[Math.max(0,size[0]/2-r),Math.max(0,size[1]/2-r)],hole=feature([rotate(sub(offset,d)),rotate(add(offset,d))],r,{kind:'hole',layers,net:'',id:p.id});
  if(p.npth_copper){const copper=padShape({...p,kind:'smd'},local,layers);return[...(Array.isArray(copper)?copper:[copper]),hole];}return hole;
 }
 if(p.shape==='custom'&&p.copper_polygons?.length){
  if(p.copper_polygons.reduce((n,r)=>n+r.length,0)>12000||p.copper_polygons.some(r=>r.length<3||r.some(v=>!finite(v))))throw Error('Invalid or excessive custom pad copper geometry.');
  return p.copper_polygons.map(polygon=>feature(polygon.map(rotate),0,{closed:true,kind:'pad',layers:p.kind==='thru_hole'?layers:padLayers(p,layers),net:p.net,id:p.id}));
 }
 if(!['rect','circle','oval','roundrect'].includes(p.shape)||![p.w,p.h].every(v=>Number.isFinite(v)&&v>0))throw Error('Unsupported or unknown pad copper. Use native DRC and manual geometry editing.');
 const hw=p.w/2,hh=p.h/2,r=p.shape==='circle'||p.shape==='oval'?Math.min(hw,hh):p.shape==='roundrect'?Math.min(hw,hh,Math.min(hw,hh)*2*(p.rratio??.25)):0,x=Math.max(0,hw-r),y=Math.max(0,hh-r);
 return feature([[-x,-y],[x,-y],[x,y],[-x,y]].map(rotate),r,{closed:true,kind:'pad',layers:p.kind==='thru_hole'?layers:padLayers(p,layers),net:p.net,id:p.id});
}
function outline(geo,local,spec){
 const native=[...(geo.outline||[]),...(geo.drawings||[]).filter(d=>d.layer==='Edge.Cuts')],loops=native.length?[]:[[[0,0],[spec.board.width_mm,0],[spec.board.width_mm,spec.board.height_mm],[0,spec.board.height_mm]]],loose=[];let padding=0;
 for(const item of native){
  if(item.kind==='poly'){if(!item.points||item.points.length<3)throw Error('Unknown footprint board cutout.');loops.push(item.points.map(local));}
  else if(item.kind==='rect'){const a=local(item.start),b=local(item.end);loops.push([a,[b[0],a[1]],b,[a[0],b[1]]]);}
  else if(item.kind==='line')loose.push([local(item.start),local(item.end)]);
  else if(item.kind==='arc'){const arc=arcPoints(...[item.start,item.mid,item.end].map(local));padding=Math.max(padding,arc.sag);loose.push(arc.points);}
  else if(item.kind==='circle'){const c=local(item.center),p=local(item.end),r=dist(c,p),count=Math.min(4096,Math.max(32,Math.ceil(Math.PI/Math.acos(Math.max(-1,1-.001/r)))));padding=Math.max(padding,r*(1-Math.cos(Math.PI/count)));loops.push(Array.from({length:count},(_,i)=>add(c,[r*Math.cos(TAU*i/count),r*Math.sin(TAU*i/count)])));}
  else throw Error('Unsupported native board edge. Refresh or edit its outline before routing.');
 }
 while(loose.length){const path=[...loose.pop()];while(!near(path[0],path.at(-1))){const i=loose.findIndex(p=>near(p[0],path.at(-1))||near(p.at(-1),path.at(-1)));if(i<0)throw Error('The native board outline is open.');let next=loose.splice(i,1)[0];if(!near(next[0],path.at(-1)))next=next.toReversed();path.push(...next.slice(1));}loops.push(path.slice(0,-1));}
 if(!loops.length)loops.push([[0,0],[spec.board.width_mm,0],[spec.board.width_mm,spec.board.height_mm],[0,spec.board.height_mm]]);
 const boundary=loops.flatMap(p=>edges(p,true)),guides=[];
 for(const loop of loops){const step=Math.max(1,Math.ceil(loop.length/24));for(let i=0;i<loop.length;i++){const a=sub(loop[i],loop[(i+loop.length-1)%loop.length]),b=sub(loop[(i+1)%loop.length],loop[i]),n=Math.hypot(...a)*Math.hypot(...b);if(i%step===0||n&&dot(a,b)/n<Math.cos(Math.PI/8))guides.push(loop[i]);}}
 return{loops,padding,edges:boundary,guides,maxX:Math.max(...loops.flat().map(p=>p[0])),index:new Index(boundary.map(points=>feature(points)))};
}
class Index{
 constructor(features){this.features=features;this.cells=new Map();this.large=[];for(const f of features){const box=f.box.map(n=>Math.floor(n/2)),count=(box[2]-box[0]+1)*(box[3]-box[1]+1);if(count>1024){this.large.push(f);continue;}for(let x=box[0];x<=box[2];x++)for(let y=box[1];y<=box[3];y++){const key=x+','+y;if(!this.cells.has(key))this.cells.set(key,[]);this.cells.get(key).push(f);}}}
 query(box,budget){const b=box.map(n=>Math.floor(n/2));if((b[2]-b[0]+1)*(b[3]-b[1]+1)>4096){charge(budget,this.features.length);return this.features.filter(f=>overlap(f.box,box));}charge(budget,this.large.length);const found=new Set(this.large);for(let x=b[0];x<=b[2];x++)for(let y=b[1];y<=b[3];y++){const rows=this.cells.get(x+','+y)||[];charge(budget,rows.length);for(const f of rows)found.add(f);}return[...found].filter(f=>overlap(f.box,box));}
}
const cache=new WeakMap();
function compile(spec,geometry){
 const geo=geometry.obstacles||geometry,key=JSON.stringify([spec.board?.width_mm,spec.board?.height_mm,spec.rules?.clearance_mm,spec.rules?.edge_clearance_mm,geo.bbox,geo.layers,geo.pads,geo.tracks,geo.arcs,geo.vias,geo.zones,geo.zone_definitions,geo.outline,(geo.drawings||[]).filter(d=>d.layer==='Edge.Cuts'||/^(F|B|In\d+)\.Cu$/.test(d.layer))]),previous=cache.get(geo);if(previous?.key===key)return previous.value;
 const [ox,oy]=geo.bbox||[100,100],local=p=>[p[0]-ox,p[1]-oy],layers=geo.layers||['F.Cu','B.Cu'],features=[],keepouts=[],definitions=new Map((geo.zone_definitions||[]).map(z=>[z.id,z]));
 for(const p of geo.pads||[]){const shape=padShape(p,local,layers);features.push(...(Array.isArray(shape)?shape:[shape]));if(p.kind==='thru_hole')features.push({...padShape({...p,kind:'np_thru_hole'},local,layers),id:'hole:'+p.id,net:p.net,plated:true});}
 for(const t of geo.tracks||[])features.push(feature([local(t.a),local(t.b)],t.w/2,{kind:'track',net:t.net,id:t.id,layers:[t.layer],locked:t.locked!==false,source:t}));
 for(const v of geo.vias||[]){const ends=(v.layers||['F.Cu','B.Cu']).map(l=>layers.indexOf(l));if(ends.some(i=>i<0))throw Error('Unknown native via span.');features.push(feature([local(v.p)],v.d/2,{kind:'via',net:v.net,id:v.id,layers:layers.slice(Math.min(...ends),Math.max(...ends)+1),source:v}));}
 for(const a of geo.arcs||[]){const arc=arcPoints(...[a.a,a.m,a.b].map(local));features.push(feature(arc.points,a.w/2+arc.sag,{kind:'arc',net:a.net,id:a.id,layers:[a.layer],source:a,arc:arc.arc}));}
 for(const d of geo.drawings||[])if(layers.includes(d.layer)){
  const extra={kind:'graphic',net:'',id:d.id,layers:[d.layer]},stroke=(d.width??.15)/2;
  if(d.kind==='poly')features.push(feature(d.fill?d.points.map(local):[...d.points,d.points[0]].map(local),stroke,{...extra,closed:!!d.fill}));
  else if(d.kind==='line')features.push(feature([local(d.start),local(d.end)],stroke,extra));
  else if(d.kind==='arc'){const arc=arcPoints(...[d.start,d.mid,d.end].map(local));features.push(feature(arc.points,stroke+arc.sag,{...extra,arc:arc.arc}));}
  else if(d.kind==='circle'){const c=local(d.center),r=dist(c,local(d.end));if(d.fill)features.push(feature([c],r+stroke,extra));else{const count=Math.max(32,Math.ceil(Math.PI/Math.acos(Math.max(-1,1-.001/r))));if(count>4096)throw Error('Copper graphic exceeds the curved geometry budget.');features.push(feature(Array.from({length:count+1},(_,i)=>add(c,[r*Math.cos(TAU*i/count),r*Math.sin(TAU*i/count)])),stroke+r*(1-Math.cos(Math.PI/count)),{...extra,arc:{c,r,start:0,dir:1,span:TAU,a:add(c,[r,0]),b:add(c,[r,0])}}));}}
  else features.push({...extra,kind:'unknown-graphic',box:[-Infinity,-Infinity,Infinity,Infinity]});
 }
 for(const z of geo.zones||[]){const definition=definitions.get(z.zone_id);if(definition&&!definition.locked)continue;const f=feature(z.pts.map(local),0,{kind:'zone',net:z.net,id:z.zone_id,layers:[z.layer],closed:true});const multiplicity=new Map();for(const e of f.edges){const key=e.map(p=>p.join(',')).sort().join('/');multiplicity.set(key,(multiplicity.get(key)||0)+1);}f.edges=f.edges.filter(e=>multiplicity.get(e.map(p=>p.join(',')).sort().join('/'))%2);features.push(f);}
 for(const z of geo.zone_definitions||[])if(z.keepout){for(const polygon of z.polygons||[])keepouts.push(feature(polygon.map(local),0,{kind:'keepout',id:z.id,net:'',layers:z.layers?.includes('*.Cu')?layers:z.layers||layers,closed:true,permissions:z.keepout_rules}));}
 const edge=outline(geo,local,spec),clearance=spec.rules?.clearance_mm??.2,edgeClearance=spec.rules?.edge_clearance_mm??.3;if(![clearance,edgeClearance].every(v=>Number.isFinite(v)&&v>=0))throw Error('Choose finite nonnegative routing clearances.');
 const value={features,keepouts,edge,clearance,edgeClearance,layers,local};cache.set(geo,{key,value});return value;
}
function requestWorld(base,request,extra=[],exclude=new Set()){
 exclude=new Set([...exclude,...(request.ignoreIds||[])]);
 const ignore=new Set(request.ignoreNets||[request.net]),radius=request.width/2,active=base.features.filter(f=>f.layers.includes(request.layer)&&!exclude.has(f.id)&&(!ignore.has(f.net)||f.kind==='hole'&&!f.plated));
 if(active.some(f=>f.kind==='unknown-graphic'))throw Error('Unsupported native copper graphic or text on '+request.layer+'. Use manual geometry editing and native DRC.');
 for(const ko of base.keepouts)if(ko.layers.includes(request.layer)){const policy=ko.permissions?.tracks;if(!['allowed','not_allowed'].includes(policy))throw Error('Unknown keepout track policy. Refresh the native layout.');if(policy==='not_allowed')active.push(ko);}
 active.push(...extra.filter(f=>f.layers.includes(request.layer)&&!ignore.has(f.net)));const index=new Index(active),edgeMargin=radius+base.edgeClearance+SAFE+base.edge.padding,clearance=base.clearance,stats={edgeChecks:0,expanded:0},encountered=new Set(),budget=request.budget||createRouteBudget(),boardCache=new Map();
 const boundaryClear=(a,b)=>base.edge.index.query(bounds([a,b],edgeMargin),budget).every(f=>{charge(budget,8);return segmentDistance(a,b,...f.points)>=edgeMargin-EPS;});
 const inBoard=p=>{const key=p.join(',');if(boardCache.has(key))return boardCache.get(key);let on=false;for(const f of base.edge.index.query([p[0],p[1],base.edge.maxX+1,p[1]],budget)){const[a,b]=f.points;if((a[1]>p[1])!==(b[1]>p[1])&&p[0]<(b[0]-a[0])*(p[1]-a[1])/(b[1]-a[1])+a[0])on=!on;}const answer=on&&boundaryClear(p,p);boardCache.set(key,answer);return answer;};
 const blockers=(a,b)=>{const hits=index.query(bounds([a,b],radius+Math.max(clearance,.2)+SAFE),budget).filter(f=>{charge(budget,f.arc?64:8*(f.edges.length+f.points.length));const required=f.r+radius+(f.kind==='hole'?.2:clearance);return separation(a,b,f)<required-Math.min(.00001,required*1e-6);});for(const f of hits)encountered.add(f);return hits;};
 const clear=(a,b)=>{charge(budget);stats.edgeChecks++;return inBoard(a)&&inBoard(b)&&boundaryClear(a,b)&&!blockers(a,b).length;};
 const pathClear=points=>points.length===1?clear(points[0],points[0]):points.slice(1).every((p,i)=>clear(points[i],p));
 return{active,base,radius,edgeMargin,clearance,inBoard,blockers,clear,pathClear,stats,encountered,budget};
}
function pathLength(points){return points.slice(1).reduce((n,p,i)=>n+dist(points[i],p),0);}
function improvePath(world,request,points){
 const result=[points[0]];let at=0,checks=0;
 try{
 while(at<points.length-1){let next=at+1,path=[points[at],points[next]],saving=0,length=0;
  for(let end=at+1;end<points.length;end++){
   length+=dist(points[end-1],points[end]);if(end<at+2)continue;
   for(const flip of [!!request.flip,!request.flip]){
    if(checks>=128||world.budget.operations>world.budget.maxOperations*.6)break;
    checks++;
    const candidate=guide(points[at],points[end],{...request,flip}),gain=length-pathLength(candidate);
    if(gain>saving+.0001&&world.pathClear(candidate)){next=end;path=candidate;saving=gain;}
   }
  }
  result.push(...path.slice(1));at=next;
 }
 return validatedCompact(world,result);
 }catch(error){if(error instanceof RouteBudgetError)return points;throw error;}
}
function solve(world,request){
 const {from,to}=request,preferred=guide(from,to,request);if(world.pathClear(preferred))return preferred;
 if(!world.clear(from,from))throw Error('The routing start is blocked by copper, a keepout or board-edge clearance.');
 if(!world.clear(to,to))throw Error('The destination is blocked by an obstacle, keepout or board-edge clearance.');
 const focus=new Set();for(let i=1;i<preferred.length;i++)for(const f of world.blockers(preferred[i-1],preferred[i]))focus.add(f);
 let best=null;
 for(let pass=0;pass<5;pass++){
  let path;try{path=search(world,request,[...focus]);}catch(error){if(best&&error instanceof RouteBudgetError)return best;throw error;}
  if(path){if(!best||pathLength(path)<pathLength(best)-.0001)best=path;path=improvePath(world,request,path);if(pathLength(path)<pathLength(best)-.0001)best=path;}
  const margin=2*(world.radius+Math.max(world.clearance,.2)+SAFE);let added=0;
  for(const f of world.encountered)if(!focus.has(f)&&(!best||[...focus].some(g=>overlap(f.box,[g.box[0]-margin,g.box[1]-margin,g.box[2]+margin,g.box[3]+margin])))){focus.add(f);added++;}
  if(!added||best&&world.budget.operations>world.budget.maxOperations*.6)break;
 }
 if(best)return best;
 throw Error('No clear route was found. Move the cursor or place a nearer waypoint.');
}
function search(world,request,nearby){
 const {from,to}=request,points=[[...from],[...to]],unique=new Set(points.map(p=>p.join(',')));
 const append=p=>{if(points.length>=384)return;if(++world.budget.candidates>world.budget.maxCandidates)throw new RouteBudgetError('Interactive routing candidate budget reached. Place a nearer waypoint.');p=round(p);const key=p.join(',');if(!unique.has(key)&&world.clear(p,p)){unique.add(key);points.push(p);}};
 for(const f of nearby){const margin=world.radius+(f.kind==='hole'?.2:world.clearance)+SAFE+.015,vertices=f.points.length>24?f.points.filter((_,i)=>i%Math.ceil(f.points.length/24)===0):f.points;for(const v of vertices)for(let i=0;i<8;i++)append(add(v,[(f.r+margin)/Math.cos(Math.PI/8)*Math.cos(i*Math.PI/4),(f.r+margin)/Math.cos(Math.PI/8)*Math.sin(i*Math.PI/4)]));if(points.length>270)break;}
 const boundary=[...world.base.edge.guides].sort((a,b)=>dist(a,projection(a,from,to))-dist(b,projection(b,from,to))).slice(0,32);
 for(const v of boundary)for(let i=0;i<8;i++)append(add(v,[Math.SQRT2*(world.edgeMargin+.02)*Math.cos(i*Math.PI/4),Math.SQRT2*(world.edgeMargin+.02)*Math.sin(i*Math.PI/4)]));
 if(points.length>384)points.length=384;const scores=Array(points.length).fill(Infinity),parents=Array(points.length),open=new Set([0]),closed=new Set(),edgeCache=new Map();scores[0]=0;
 while(open.size){if(world.stats.expanded++>180||world.stats.edgeChecks>40000)throw new RouteBudgetError('Interactive routing search budget reached. Place a nearer waypoint.');let at=-1,best=Infinity;for(const i of open){const cost=scores[i]+dist(points[i],to);if(cost<best){at=i;best=cost;}}open.delete(at);if(at===1){const result=[];let i=1;while(i){const e=parents[i];result.unshift(...e.path.slice(1));i=e.from;}result.unshift(from);return validatedCompact(world,result);}
  closed.add(at);for(let next=0;next<points.length;next++){if(next===at||closed.has(next))continue;const direct=dist(points[at],points[next]);if(scores[at]+direct>=scores[next]-EPS)continue;const key=at+':'+next;let path=edgeCache.get(key);if(path===undefined){path=null;for(const flip of [!!request.flip,!request.flip]){const p=guide(points[at],points[next],{...request,flip});if(world.pathClear(p)){path=p;break;}}edgeCache.set(key,path);}if(!path)continue;const cost=scores[at]+pathLength(path)+.002*(path.length-2);if(cost<scores[next]-EPS){scores[next]=cost;parents[next]={from:at,path};open.add(next);}}
 }
 return null;
}
function contactAnchor(a,b,f){
 const candidates=[a,b,...f.points.map(p=>projection(p,a,b))];for(const[c,d]of f.edges){const hit=intersection(a,b,c,d);if(hit)candidates.push(hit);}candidates.sort((p,q)=>separation(p,p,f)-separation(q,q,f));return candidates[0];
}
function shovePlan(base,request,preferred){
 const world=requestWorld(base,request),collisions=new Map();for(let i=1;i<preferred.length;i++)for(const f of world.blockers(preferred[i-1],preferred[i]))collisions.set(f.id,f);
 const movable=[...collisions.values()];if(!movable.length||movable.length>16||movable.some(f=>f.kind!=='track'||f.locked||!f.id))return null;
 const excluded=new Set(movable.map(f=>f.id)),reserved=preferred.slice(1).map((p,i)=>feature([preferred[i],p],request.width/2,{kind:'track',net:request.net,layers:[request.layer]})),shoves=[],added=[];
 movable.sort((a,b)=>dist(a.points[0],request.to)-dist(b.points[0],request.to));
 for(const f of movable){
  const[a,b]=f.points,anchors=[a,b];for(const other of base.features){if(other.id===f.id||other.net!==f.net||!other.layers.includes(request.layer))continue;if(separation(a,b,other)>f.r+other.r+.00015)continue;if(other.kind==='arc'||other.kind==='zone')return null;const p=contactAnchor(a,b,other);if(!anchors.some(v=>identical(v,p)))anchors.push(p);}
  anchors.sort((p,q)=>dot(sub(p,a),sub(b,a))-dot(sub(q,a),sub(b,a)));let path=[a];
  for(let i=1;i<anchors.length;i++){const foreign={...request,net:f.net,ignoreNets:[f.net],width:f.r*2,from:anchors[i-1],to:anchors[i],mode:'walkaround'},w=requestWorld(base,foreign,[...reserved,...added],excluded);path.push(...solve(w,foreign).slice(1));}
  path=validatedCompact(requestWorld(base,{...request,net:f.net,ignoreNets:[f.net],width:f.r*2},[...reserved,...added],excluded),path,anchors);shoves.push({id:f.id,net:f.net,points:path,width:f.r*2,layer:request.layer,locked:false});for(let i=1;i<path.length;i++)added.push(feature([path[i-1],path[i]],f.r,{kind:'track',net:f.net,layers:[request.layer]}));
 }
 for(const moved of shoves){const check=requestWorld(base,{...request,net:moved.net,ignoreNets:[moved.net],width:moved.width},[...reserved,...added],excluded);if(!check.pathClear(moved.points))return null;}
 const final=requestWorld(base,request,added,excluded);return final.pathClear(preferred)?{points:preferred,shoves,stats:final.stats}:null;
}
export function planInteractiveRoute(spec,geometry,request){
 if(!request||![request.from,request.to].every(finite)||!Number.isFinite(request.width)||request.width<=0||!['walkaround','shove'].includes(request.mode||'walkaround'))throw Error('Choose a finite route and a supported obstacle behavior.');
 request={...request,budget:request.budget||createRouteBudget()};const base=compile(spec,geometry);if(!base.layers.includes(request.layer))throw Error('Choose a native copper routing layer.');const preferred=guide(request.from,request.to,request),world=requestWorld(base,request);
 if(world.pathClear(preferred))return{points:preferred,shoves:[],stats:world.stats};
 if(request.mode==='shove'){try{const pushed=shovePlan(base,request,preferred);if(pushed)return pushed;}catch(error){if(error instanceof RouteBudgetError)throw error;/* A fixed junction or blocked shove falls back to walking around. */}}
 return{points:solve(world,request),shoves:[],stats:world.stats};
}
export function assertInteractivePaths(spec,geometry,paths,{ignoreIds=[],budget=createRouteBudget()}={}){
 const base=compile(spec,geometry),worlds=new Map();
 for(const path of paths){const key=[path.net,path.width,path.layer].join(':');let world=worlds.get(key);if(!world){world=requestWorld(base,{net:path.net,width:path.width,layer:path.layer,ignoreIds,budget});worlds.set(key,world);}if(!world.pathClear(path.points))throw Error('The routed copper violates an obstacle, keepout or board-edge clearance.');}
 return true;
}
export function validateInteractiveVia(spec,geometry,request){
 const base=compile(spec,geometry),p=request.p,diameter=request.d,drill=request.drill??spec.rules?.via_drill_mm??.3,ignore=new Set(request.ignoreIds||[]);if(!finite(p)||!Number.isFinite(diameter)||diameter<=0||!Number.isFinite(drill)||drill<=0||diameter<=drill)throw Error('Choose finite positive via dimensions.');const ends=(request.layers||['F.Cu','B.Cu']).map(l=>base.layers.indexOf(l));if(ends.length!==2||ends[0]===ends[1]||ends.some(i=>i<0))throw Error('Choose two distinct native via layers.');
 for(const layer of base.layers.slice(Math.min(...ends),Math.max(...ends)+1)){
  for(const ko of base.keepouts)if(ko.layers.includes(layer)){const policy=ko.permissions?.vias;if(!['allowed','not_allowed'].includes(policy))throw Error('Unknown via keepout policy. Refresh the native layout.');if(policy==='not_allowed'&&separation(p,p,ko)<diameter/2+SAFE)throw Error('The via intersects a native via keepout.');}
  const w=requestWorld({...base,keepouts:[]},{net:request.net,width:diameter,layer,ignoreIds:[...ignore]});if(!w.clear(p,p))throw Error('The via violates copper, hole or board-edge clearance on '+layer+'.');
 }
 for(const pad of (geometry.obstacles||geometry).pads||[])if(pad.drill>0){const hole=padShape({...pad,kind:'np_thru_hole'},base.local,base.layers);if(separation(p,p,hole)<hole.r+drill/2+.2-.00001)throw Error('The via drill is too close to an existing hole.');}
 for(const via of (geometry.obstacles||geometry).vias||[])if(via.id!==request.id&&dist(p,base.local(via.p))<(drill+via.drill)/2+.2-.00001)throw Error('The via drill is too close to an existing via.');
 return true;
}
