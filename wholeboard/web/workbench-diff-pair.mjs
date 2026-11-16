const EPS=1e-7;
const point=p=>Array.isArray(p)&&p.length===2&&p.every(Number.isFinite);
const add=(a,b)=>a.map((v,i)=>v+b[i]),sub=(a,b)=>a.map((v,i)=>v-b[i]),mul=(a,n)=>a.map(v=>v*n),dot=(a,b)=>a.reduce((s,v,i)=>s+v*b[i],0),cross=(a,b)=>a[0]*b[1]-a[1]*b[0];
const rounded=p=>p.map(v=>+v.toFixed(4)),near=(a,b)=>Math.hypot(...sub(a,b))<.00001;
const compact=points=>points.map(rounded).filter((p,i,all)=>!i||!near(p,all[i-1]));
function boundedGuide(points){const guide=compact(points);if(guide.length>512)throw Error('Finish this pair route before adding more corners.');return guide;}
const midpoint=(a,b)=>mul(add(a,b),.5);
function pointSegment(p,a,b){const d=sub(b,a),size=dot(d,d),t=size?Math.max(0,Math.min(1,dot(sub(p,a),d)/size)):0;return Math.hypot(...sub(p,add(a,mul(d,t))));}
function distance(a,b,c,d){const r=sub(b,a),s=sub(d,c),den=cross(r,s);if(Math.abs(den)>EPS){const t=cross(sub(c,a),s)/den,u=cross(sub(c,a),r)/den;if(t>=-EPS&&t<=1+EPS&&u>=-EPS&&u<=1+EPS)return 0;}return Math.min(pointSegment(a,c,d),pointSegment(b,c,d),pointSegment(c,a,b),pointSegment(d,a,b));}
function separated(legs,widths,gap){
 for(let i=1;i<legs[0].length;i++)for(let j=1;j<legs[1].length;j++){
  const required=(widths[0][i-1]+widths[1][j-1])/2+gap;
  const[a,b]=[legs[0][i-1],legs[0][i]],[c,d]=[legs[1][j-1],legs[1][j]];
  if(Math.max(a[0],b[0])+required<Math.min(c[0],d[0])||Math.max(c[0],d[0])+required<Math.min(a[0],b[0])||Math.max(a[1],b[1])+required<Math.min(c[1],d[1])||Math.max(c[1],d[1])+required<Math.min(a[1],b[1]))continue;
  if(distance(a,b,c,d)<required-Math.min(.00012,required*.001))throw Error('Pair spacing conflicts or the fanout crosses. Change the corner, width or gap.');
 }
}
export function pairedPaths(guide,{width,gap,start,end=null,side=null,minimumGap=gap,startWidth=width,endWidth=width}={}){
 if(!Number.isFinite(width)||width<=0||width>100)throw Error('Choose a finite positive pair width.');
 if(!Number.isFinite(gap)||gap<=0||gap>100||!Number.isFinite(minimumGap)||minimumGap<0)throw Error('Choose a finite positive pair gap.');
 if(![startWidth,endWidth].every(v=>Number.isFinite(v)&&v>0&&v<=100))throw Error('Pair fanout widths must be finite and positive.');
 if(!Array.isArray(guide)||guide.length>1024||guide.some(p=>!point(p))||!Array.isArray(start)||start.length!==2||start.some(p=>!point(p))||end&&(!Array.isArray(end)||end.length!==2||end.some(p=>!point(p))))throw Error('Pair routing needs bounded finite guide and terminal points.');
 const points=compact(guide);if(points.length<2)throw Error('Move the pair cursor before placing copper.');
 const directions=points.slice(1).map((p,i)=>{const d=sub(p,points[i]);return mul(d,1/Math.hypot(...d));}),normals=directions.map(d=>[-d[1],d[0]]),sideDot=dot(sub(start[0],start[1]),normals[0]);
 side=Math.abs(sideDot)>EPS?Math.sign(sideDot):side||1;const offset=(width+gap)/2;
 const widths=[],legs=[side,-side].map((sign,leg)=>{
  const result=[add(points[0],mul(normals[0],offset*sign))];
  for(let i=1;i<points.length-1;i++){
   const a=add(points[i],mul(normals[i-1],offset*sign)),b=add(points[i],mul(normals[i],offset*sign)),den=cross(directions[i-1],directions[i]);let at;
   if(Math.abs(den)<EPS){if(dot(directions[i-1],directions[i])<0)throw Error('The pair cannot reverse directly; add a wider turn.');at=a;}
   else at=add(a,mul(directions[i-1],cross(sub(b,a),directions[i])/den));
   if(Math.hypot(...sub(at,points[i]))>offset*8+.001)throw Error('The pair turn is too sharp for this spacing.');result.push(at);
  }
  result.push(add(points.at(-1),mul(normals.at(-1),offset*sign)));const path=[rounded(start[leg])],w=[];
  const append=(p,width)=>{p=rounded(p);if(!near(path.at(-1),p)){path.push(p);w.push(width);}};
  result.forEach((p,i)=>append(p,i===0?Math.min(width,startWidth):width));if(end)append(end[leg],Math.min(width,endWidth));widths.push(w);return path;
 });
 separated(legs,widths,minimumGap);return{legs,widths,side};
}

const pinNets=spec=>new Map(spec.nets.flatMap(n=>n.pins.map(p=>[p,n.name])));
function physicalPair(spec,geo,profile,anchor,layer,resolve,partnerPadId=null){
 const membership=pinNets(spec),other=profile.nets.find(n=>n!==anchor.net),pin=anchor.target.pin;
 const ends=profile.ends.filter(e=>e.pins.includes(pin)),pins=[...new Set(ends.flatMap(e=>e.pins).filter(p=>membership.get(p)===other))];
 if(pins.length!==1)throw Error('The paired terminal is missing or ambiguous. Choose a declared pair endpoint or route a single net.');
 const choices=geo.pads.filter(p=>`${p.ref}.${p.name}`===pins[0]&&p.net===other&&p.kind!=='np_thru_hole'&&(!partnerPadId||p.id===partnerPadId)).map(p=>resolve(spec,geo,{kind:'pad',pin:pins[0],padId:p.id})).filter(p=>p.layers.some(l=>anchor.layers.includes(l)));
 const preferred=choices.filter(p=>p.layers.includes(layer)),candidates=preferred.length?preferred:choices;
 if(candidates.length!==1)throw Error('The physical paired pad is missing, on another layer or ambiguous. Hold Ctrl/Cmd for single routing.');
 const partner=candidates[0],common=anchor.layers.filter(l=>partner.layers.includes(l));return{partner,layer:common.includes(layer)?layer:common[0]};
}
export function beginPair(spec,geo,anchor,layer,settings,resolve){
 if(anchor.target.kind!=='pad'||!settings.profiles)return null;
 const profiles=settings.profiles.pairs||[],possible=profiles.filter(p=>p.nets.length===2&&p.nets.includes(anchor.net));
 if(!possible.length){const issue=(settings.profiles.issues||[]).find(i=>i.nets?.includes(anchor.net));if(issue&&!settings.single)throw Error(issue.message);return null;}
 try{
  if(possible.length!==1)throw Error('This net has more than one differential partner. Resolve its pair declarations.');
  const profile=possible[0],resolved=physicalPair(spec,geo,profile,anchor,layer,resolve,settings.partnerPadId),width=settings.width??profile.width_mm??spec.rules?.track_mm??.25,gap=settings.gap??profile.gap_mm??spec.rules?.clearance_mm??.2,clearance=spec.rules?.clearance_mm??.2;
  if(!Number.isFinite(width)||width<=0||width>100||!Number.isFinite(gap)||gap<=0||gap>100||gap<clearance)throw Error('Pair width/gap must be positive and the gap must meet board clearance.');
  const pair={profile:structuredClone(profile),nets:[anchor.net,resolved.partner.net],primary:{point:[...anchor.point],layers:[...anchor.layers],width},other:{point:[...resolved.partner.point],layers:[...resolved.partner.layers],width},gap,clearance,sections:[],active:null,managed:[]};
  return{pair,layer:resolved.layer,width,single:!!settings.single,point:settings.single?[...anchor.point]:rounded(midpoint(anchor.point,resolved.partner.point))};
 }catch(error){if(settings.single)return null;throw error;}
}
export function pairMode(session,single){
 if(!session.pair)return session;const out=structuredClone(session),p=out.pair;
 if(!single&&!p.other.layers.includes(out.layer))throw Error('The parked partner is on another layer. Finish the single leg or reconnect both legs on one layer before paired routing.');
 out.single=!!single;out.point=single?[...p.primary.point]:rounded(midpoint(p.primary.point,p.other.point));return out;
}
export function recordSingle(result){
 if(!result.session.pair)return result;const p=result.session.pair;p.primary={point:[...result.session.point],layers:[result.session.layer],width:result.session.width};p.active=null;return result;
}
function ensureSection(state){
 const p=state.pair;let section=p.active===null?null:p.sections[p.active];
 if(!section||section.layer!==state.layer||section.width!==state.width||section.gap!==p.gap){section={layer:state.layer,width:state.width,gap:p.gap,start:[p.primary.point,p.other.point].map(v=>[...v]),startWidth:Math.min(state.width,p.primary.width,p.other.width),guide:[rounded(midpoint(p.primary.point,p.other.point))],ids:[[],[]]};p.sections.push(section);p.active=p.sections.length-1;}
 return section;
}
export function sectionPaths(section,clearance){return pairedPaths(section.guide,{width:section.width,gap:section.gap+.001,minimumGap:clearance,start:section.start,startWidth:section.startWidth,end:section.end||null});}
function span(via,stack){const ends=(via.layers||['F.Cu','B.Cu']).map(l=>stack.indexOf(l));if(ends.some(i=>i<0))throw Error('The existing via span is not in this board stackup.');return stack.filter((_,i)=>i>=Math.min(...ends)&&i<=Math.max(...ends));}
function viewPlan(pair){
 const tracks=[[],[]],vias=[[],[]];
 for(const section of pair.sections){
  if(section.guide.length<2)continue;const paths=sectionPaths(section,pair.clearance);
  paths.legs.forEach((points,leg)=>{for(let i=1;i<points.length;i++)tracks[leg].push({a:points[i-1],b:points[i],w:paths.widths[leg][i-1],layer:section.layer,section,index:i-1,leg});});
  for(let leg=0;leg<2;leg++)if(section.vias?.[leg]&&!vias[leg].some(v=>v.id&&v.id===section.vias[leg].id))vias[leg].push(section.vias[leg]);
 }
 for(const a of tracks[0])for(const b of tracks[1])if(a.layer===b.layer&&distance(a.a,a.b,b.a,b.b)<(a.w+b.w)/2+pair.clearance-.00012)throw Error('Paired sections cross or violate clearance. Change the corner or spacing.');
 for(const leg of [0,1])for(const a of tracks[leg])for(const b of vias[1-leg])if((!pair.stack||span(b,pair.stack).includes(a.layer))&&pointSegment(b.p,a.a,a.b)<a.w/2+b.d/2+pair.clearance-.00012)throw Error('A paired via conflicts with the other leg. Move the via or widen the approach.');
 for(const a of vias[0])for(const b of vias[1])if(Math.hypot(...sub(a.p,b.p))<(a.d+b.d)/2+pair.clearance-.00012)throw Error('The pair vias are too close.');
 return{tracks,vias};
}
function boardPoint(at,board){if(!point(at)||at[0]<0||at[1]<0||at[0]>board.width_mm||at[1]>board.height_mm)throw Error('The pair centre or fanout leaves the board. Move the routing corner.');}
function boardPlan(plan,board){for(const track of plan.tracks.flat())for(const at of [track.a,track.b])boardPoint(at,board);for(const via of plan.vias.flat())boardPoint(via.p,board);}
function writePair(spec,geo,state,tools){
 const base=state.initialized?structuredClone(spec):tools.adopt(spec,geo),p=state.pair,old=new Set(p.managed),plan=viewPlan(p),managed=[];
 boardPlan(plan,spec.board);
 for(const g of base.fixed_copper||[])for(const kind of ['tracks','arcs','vias'])if(g[kind])g[kind]=g[kind].filter(item=>!old.has(item.id));
 const group=net=>{base.fixed_copper||=[];let g=base.fixed_copper.find(g=>g.net===net);if(!g){g={net,tracks:[],arcs:[],vias:[]};base.fixed_copper.push(g);}g.tracks||=[];g.vias||=[];return g;};
 for(let leg=0;leg<2;leg++){
  const g=group(p.nets[leg]);
  for(const track of plan.tracks[leg]){
   const id=track.section.ids[leg][track.index]||crypto.randomUUID();track.section.ids[leg][track.index]=id;managed.push(id);g.tracks.push({id,a:track.a,b:track.b,w:track.w,layer:track.layer});
  }
  for(const via of plan.vias[leg]){via.id||=crypto.randomUUID();if(!via.reused)managed.push(via.id);if(!g.vias.some(v=>v.id===via.id)){const{reused,...value}=via;g.vias.push(structuredClone(value));}}
 }
 p.managed=managed;state.initialized=true;
 return base;
}
function destination(spec,geo,state,target,resolve){
 if(target.kind==='point')return{point:target.at,finished:false};
 if(target.kind!=='pad')throw Error('Finish a paired route at its declared pads; hold Ctrl/Cmd to finish one net on a trace or via.');
 const clicked=resolve(spec,geo,target);if(!state.pair.nets.includes(clicked.net))throw Error('Finish on a terminal of this differential pair.');
 const matched=physicalPair(spec,geo,state.pair.profile,clicked,state.layer,resolve),byNet=new Map([[clicked.net,clicked],[matched.partner.net,matched.partner]]),anchors=state.pair.nets.map(n=>byNet.get(n));
 if(anchors.some(a=>!a.layers.includes(state.layer)))throw Error('The destination pair is on another layer. Add paired vias before connecting it.');
 return{point:rounded(midpoint(anchors[0].point,anchors[1].point)),end:anchors.map(a=>a.point),layers:anchors.map(a=>a.layers),finished:true};
}
export function extendPair(spec,geo,session,target,settings,tools){
 const state={...structuredClone(session),...settings},p=state.pair,dest=destination(spec,geo,state,target,tools.resolve);
 boardPoint(dest.point,spec.board);
 if(near(state.point,dest.point)&&!dest.finished)return{spec,session:state,finished:false};
 const section=ensureSection(state),path=tools.route(state.point,dest.point,state,{end:dest.end});section.guide=boundedGuide([...section.guide,...path.slice(1)]);if(dest.end)section.end=dest.end;
 const paths=sectionPaths(section,p.clearance);state.point=rounded(dest.point);p.primary={point:paths.legs[0].at(-1),layers:dest.layers?.[0]||[state.layer],width:paths.widths[0].at(-1)};p.other={point:paths.legs[1].at(-1),layers:dest.layers?.[1]||[state.layer],width:paths.widths[1].at(-1)};
 return{spec:writePair(spec,geo,state,tools),session:state,finished:dest.finished};
}
export function pairLayer(spec,geo,session,at,nextLayer,settings,tools){
 const state=structuredClone(session),p=state.pair,centre=rounded(midpoint(p.primary.point,p.other.point));
 p.stack=tools.layers(spec);
 if(near(at,centre)&&p.primary.layers.includes(nextLayer)&&p.other.layers.includes(nextLayer)){state.layer=nextLayer;p.active=null;state.point=centre;return{spec,session:state,finished:false};}
 let result=extendPair(spec,geo,state,{kind:'point',at},{},tools),next=result.session,context=next.pair,section=context.sections[context.active];
 if(!section||section.guide.length<2)throw Error('Move the pair cursor before placing paired vias.');
 const diameter=settings.diameter??spec.rules?.via_diameter_mm??.6,drill=settings.drill??spec.rules?.via_drill_mm??.3;
 if(!Number.isFinite(diameter)||!Number.isFinite(drill)||drill<=0||diameter<=drill||diameter>10)throw Error('Pair vias need a positive drill smaller than their diameter.');
 const paths=sectionPaths(section,context.clearance),vector=sub(paths.legs[0].at(-1),paths.legs[1].at(-1)),normal=mul(vector,1/Math.hypot(...vector)),pitch=Math.max(next.width+context.gap+.001,diameter+context.clearance+.001,drill+.2+.001),positions=[add(at,mul(normal,pitch/2)),add(at,mul(normal,-pitch/2))].map(rounded);
 const existing=(result.spec.fixed_copper||[]).flatMap(g=>(g.vias||[]).map(v=>({net:g.net,via:v}))),fromLayer=next.layer;
 section.vias=positions.map((position,leg)=>{
  const occupying=existing.filter(v=>Math.hypot(...sub(v.via.p,position))<=.001);
  if(occupying.some(v=>v.net!==context.nets[leg]))throw Error('An existing via of another net occupies this paired via position.');
  if(occupying.length>1)throw Error('Multiple existing vias occupy this pair position. Resolve them before routing.');
  if(occupying.length){const via=occupying[0].via,layers=span(via,context.stack);if(!layers.includes(fromLayer)||!layers.includes(nextLayer))throw Error('The existing paired via does not span both requested routing layers.');return{...structuredClone(via),reused:true};}
  return{p:position,d:diameter,drill,layers:['F.Cu','B.Cu'],type:'through'};
 });
 section.end=section.vias.map(v=>v.p);context.primary={point:section.end[0],layers:span(section.vias[0],context.stack),width:next.width};context.other={point:section.end[1],layers:span(section.vias[1],context.stack),width:next.width};context.active=null;next.layer=nextLayer;next.point=rounded(midpoint(section.end[0],section.end[1]));
 return{spec:writePair(result.spec,geo,next,tools),session:next,finished:false};
}
export function pairPreview(spec,geo,session,target,tools){
 const state=structuredClone(session),dest=destination(spec,geo,state,target,tools.resolve);boardPoint(dest.point,spec.board);const section=ensureSection(state);section.guide=boundedGuide([...section.guide,...tools.route(state.point,dest.point,state,{end:dest.end}).slice(1)]);if(dest.end)section.end=dest.end;const plan=viewPlan(state.pair);boardPlan(plan,spec.board);
 return{paths:plan.tracks.flatMap((tracks,leg)=>tracks.map(t=>({net:state.pair.nets[leg],layer:t.layer,width:t.w,points:[t.a,t.b]}))),vias:plan.vias.flatMap((vias,leg)=>vias.filter(v=>!v.reused).map(v=>({...v,net:state.pair.nets[leg]})))};
}
