import {connectPins,pruneWireJoins,electricalPin,electricalNet,pruneWireNodes,pruneSheetPorts,ensureTerminalNets,pcbExcluded} from './workbench-model.mjs';
export const logicalPin=anchor=>anchor.replace(/#\d+(?=\.)/,'');

export function projectWirePoint(points,at){
  if(!Array.isArray(points)||points.length<2||!Array.isArray(at)||at.length!==2||at.some(v=>!Number.isFinite(v)))throw new Error('Choose a point on an existing native wire.');
  let total=0,distance=0,best=null;
  const lengths=points.slice(1).map((point,index)=>Math.hypot(point[0]-points[index][0],point[1]-points[index][1]));
  total=lengths.reduce((a,b)=>a+b,0);
  for(let index=0;index<lengths.length;index++){
    const a=points[index],b=points[index+1],length=lengths[index],dx=b[0]-a[0],dy=b[1]-a[1];let fraction=length?Math.max(0,Math.min(1,((at[0]-a[0])*dx+(at[1]-a[1])*dy)/(length*length))):0;
    const point=[a[0]+fraction*dx,a[1]+fraction*dy],away=Math.hypot(point[0]-at[0],point[1]-at[1]);
    if(Math.abs(dy)<.00001&&dx){point[0]=Math.max(Math.min(a[0],b[0]),Math.min(Math.max(a[0],b[0]),Math.round(point[0]/10)*10));fraction=(point[0]-a[0])/dx;}
    else if(Math.abs(dx)<.00001&&dy){point[1]=Math.max(Math.min(a[1],b[1]),Math.min(Math.max(a[1],b[1]),Math.round(point[1]/10)*10));fraction=(point[1]-a[1])/dy;}
    if(!best||away<best.away)best={point,away,offset:total?(distance+fraction*length)/total:0};distance+=length;
  }
  if(!best||best.away>10)throw new Error('Choose a point on the wire.');
  return{point:best.point,offset:best.offset};
}

export function endpointPin(spec,endpoint){
  if(endpoint.point)return null;
  const anchor=endpoint.node?'node:'+endpoint.node:endpoint.pin||spec.editor?.connection_guides?.[endpoint.route?.index]?.from;
  if(typeof anchor!=='string')throw new Error('The wire changed. Select its endpoint again.');
  return electricalPin(spec,anchor);
}

function endpoint(spec,value){
  if(value.point){
    const id=crypto.randomUUID();spec.editor.wire_nodes||={};spec.editor.wire_nodes[id]={position:wireNodePoint(value.point),sheet:value.sheet||''};
    return{pin:'node:'+id,anchor:'node:'+id};
  }
  if(value.node){if(!spec.editor?.wire_nodes?.[value.node])throw new Error('The wire endpoint no longer exists.');return{pin:'node:'+value.node,anchor:'node:'+value.node};}
  if(value.pin)return{pin:electricalPin(spec,value.pin),anchor:value.anchor||value.pin};
  const route=value.route,guide=spec.editor?.connection_guides?.[route?.index];
  if(!guide||route.status!=='routed')throw new Error('Choose an existing routed wire.');
  const net=electricalNet(spec,guide.from),other=electricalNet(spec,guide.to);
  if(!net||net!==other||net.name!==route.net)throw new Error('The wire net changed. Refresh the schematic before connecting it.');
  if(route.from&&route.from!==guide.from||route.to&&route.to!==guide.to)throw new Error('The wire changed. Select it again.');
  const position=projectWirePoint(route.points,value.at);
  return{pin:electricalPin(spec,guide.from),anchor:guide.from,join:{wire:guide.id,offset:position.offset}};
}

export function connectWireEndpoints(spec,from,to,{allowMerge=false,waypoints=[]}={}){
  if(!Array.isArray(waypoints)||waypoints.length>100||waypoints.some(p=>!Array.isArray(p)||p.length!==2||p.some(v=>!Number.isFinite(v)||Math.abs(v)>1_000_000)))throw new Error('Wire bends require at most 100 finite 2D points.');
  for(const endpoint of [from,to])if(endpoint.route){const guide=spec.editor?.connection_guides?.[endpoint.route.index];if(guide?.id&&guide.id!==endpoint.route.id)throw new Error('The wire changed. Select it again.');}
  const source=structuredClone(spec);source.editor||={};source.editor.connection_guides||=[];
  for(const guide of source.editor.connection_guides)guide.id||=crypto.randomUUID();
  const a=endpoint(source,from),b=endpoint(source,to);
  for(const value of [a,b])if(value.anchor.startsWith('sheet:')){
    const separator=value.anchor.indexOf('.',6),id=value.anchor.slice(6,separator),label=decodeURIComponent(value.anchor.slice(separator+1)),net=source.nets.find(n=>n.pins.includes(value.pin));
    if(net){
      source.editor.sheets||={};source.editor.sheets[id]||={title:id,parent:''};source.editor.sheets[id].ports||={};
      const terminal=source.components.find(c=>c.terminal&&c.value===label&&String((Object.hasOwn(c,'sheet')?c.sheet:c.block)||'')===id);
      const previous=source.editor.sheets[id].ports[label]||{};
      source.editor.sheets[id].ports[label]={...previous,...(terminal?{...terminal.terminal,terminal_ref:terminal.ref}:{}),net:net.name};
    }
  }
  const out=connectPins(source,a.pin,b.pin,allowMerge);
  const guide={id:crypto.randomUUID(),from:a.anchor,to:b.anchor};if(a.join)guide.from_join=a.join;if(b.join)guide.to_join=b.join;
  if(waypoints.length)guide.waypoints=structuredClone(waypoints);
  if(!out.editor.connection_guides.some(prior=>prior.from===guide.from&&prior.to===guide.to&&JSON.stringify(prior.from_join)===JSON.stringify(guide.from_join)&&JSON.stringify(prior.to_join)===JSON.stringify(guide.to_join)&&JSON.stringify(prior.waypoints||[])===JSON.stringify(guide.waypoints||[])))out.editor.connection_guides.push(guide);
  return out;
}

export function disconnectPin(spec,pin){
  pin=logicalPin(pin);const ref=pin.split('.')[0];if(!spec.components.some(component=>component.ref===ref))throw new Error('Choose an existing component pin.');
  const out=structuredClone(spec),affected=new Set(out.nets.filter(net=>net.pins.includes(pin)).map(net=>net.name));
  out.nets=out.nets.map(net=>({...net,pins:net.pins.filter(value=>value!==pin)})).filter(net=>net.pins.length||Object.values(out.editor?.wire_nodes||{}).some(node=>node.net===net.name));
  if(out.fixed_copper)out.fixed_copper=out.fixed_copper.filter(group=>(pcbExcluded(out.components.find(c=>c.ref===ref))||!affected.has(group.net))&&(!affected.has(group.net)||out.nets.some(net=>net.name===group.net)));
  if(out.fixed_zones){const remaining=new Set(out.nets.map(net=>net.name));out.fixed_zones=out.fixed_zones.filter(zone=>!zone.net||remaining.has(zone.net));}
  if(out.editor?.connection_guides)out.editor.connection_guides=pruneWireJoins(out.editor.connection_guides.filter(guide=>logicalPin(guide.from)!==pin&&logicalPin(guide.to)!==pin));
  return pruneSheetPorts(ensureTerminalNets(pruneWireNodes(out)));
}

export function removeWireDrawing(spec,index){
  if(!spec.editor?.connection_guides?.[index])throw new Error('Select an existing wire.');
  const out=structuredClone(spec);out.editor.connection_guides.splice(index,1);out.editor.connection_guides=pruneWireJoins(out.editor.connection_guides);return pruneWireNodes(out);
}

function wireNodePoint(point){
  if(!Array.isArray(point)||point.length!==2||point.some(v=>!Number.isFinite(v)||Math.abs(v)>1_000_000))throw new Error('Wire endpoints need finite coordinates.');
  return point.map(v=>Math.round(v/10)*10);
}
export function moveWireNode(spec,id,point){
  if(!spec.editor?.wire_nodes?.[id])throw new Error('The wire endpoint no longer exists.');
  const out=structuredClone(spec);out.editor.wire_nodes[id].position=wireNodePoint(point);return out;
}
export function removeWireNode(spec,id){
  if(!spec.editor?.wire_nodes?.[id])throw new Error('The wire endpoint no longer exists.');
  const out=structuredClone(spec);out.editor.connection_guides=pruneWireJoins(out.editor.connection_guides.filter(g=>g.from!=='node:'+id&&g.to!=='node:'+id));return pruneWireNodes(out);
}
export function splitWireDrawing(spec,route,at){
  const guide=spec.editor?.connection_guides?.[route.index];if(!guide||guide.id!==route.id||route.status!=='routed')throw new Error('The native wire changed. Select it again.');
  const split=projectWirePoint(route.points,at),fraction=split.offset;
  if(fraction<.00001||fraction>.99999)throw new Error('Split at an interior point, away from the wire ends.');
  const net=electricalNet(spec,guide.from);if(!net||net.name!==route.net)throw new Error('The wire net changed.');
  const out=structuredClone(spec),node=crypto.randomUUID(),rightId=crypto.randomUUID();out.editor.wire_nodes||={};out.editor.wire_nodes[node]={position:split.point,sheet:route.sheet||'',net:net.name};
  const leftPoints=[],rightPoints=[];let found=false;
  for(let i=0;i<route.points.length;i++){
    const p=route.points[i];if(!found)leftPoints.push(p);else rightPoints.push(p);
    if(!found&&i<route.points.length-1){const q=route.points[i+1],a=split.point;if(Math.abs((q[0]-p[0])*(a[1]-p[1])-(q[1]-p[1])*(a[0]-p[0]))<.001&&a.every((v,k)=>v>=Math.min(p[k],q[k])-.001&&v<=Math.max(p[k],q[k])+.001)){leftPoints.push(a);rightPoints.push(a);found=true;}}
  }
  const bends=points=>points.filter((p,i)=>!i||Math.hypot(p[0]-points[i-1][0],p[1]-points[i-1][1])>.0001).slice(1,-1);
  const left={...structuredClone(guide),to:'node:'+node,waypoints:bends(leftPoints)},right={...structuredClone(guide),id:rightId,from:'node:'+node,waypoints:bends(rightPoints)};delete left.to_join;delete right.from_join;
  if(guide.fixed_points){left.fixed_points=[route.points[0],...left.waypoints,split.point];right.fixed_points=[split.point,...right.waypoints,route.points.at(-1)];}
  out.editor.connection_guides.splice(route.index,1,left,right);
  for(const g of out.editor.connection_guides)for(const key of ['from_join','to_join'])if(g[key]?.wire===guide.id){const offset=g[key].offset,parent=offset<=fraction?left:right;g[key]=offset<=fraction?{wire:guide.id,offset:offset/fraction}:{wire:rightId,offset:(offset-fraction)/(1-fraction)};g[key.slice(0,-5)]=parent.from;}
  return{spec:out,node};
}
