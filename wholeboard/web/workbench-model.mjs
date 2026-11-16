// Pure design operations. The editor, inspector, and BOM share this model.
import {remapObjectOrganization} from './workbench-object-groups-model.mjs';
export function pinIndex(spec) {
  return Object.fromEntries((spec.nets || []).flatMap(n => (n.pins || []).map(p => [p, n.name])));
}

export function electricalPin(spec,anchor){
  if(!anchor.startsWith('sheet:'))return anchor.replace(/#\d+(?=\.)/,'');
  const separator=anchor.indexOf('.',6),id=anchor.slice(6,separator),label=decodeURIComponent(anchor.slice(separator+1));
  const terminal=spec.components.find(c=>c.terminal&&c.terminal.expose!==false&&c.value===label&&componentPage(c)===id);
  if(terminal)return terminal.ref+'.1';
  const declaration=spec.editor?.sheets?.[id]?.ports?.[label],name=declaration?.net||label;
  if(declaration?.terminal_ref&&spec.nets.find(net=>net.name===name)?.pins.includes(declaration.terminal_ref+'.1'))return declaration.terminal_ref+'.1';
  return spec.nets.find(net=>net.name===name)?.pins[0]||anchor;
}

export function electricalNet(spec,anchor){
  if(anchor?.startsWith('node:'))return spec.nets.find(net=>net.name===spec.editor?.wire_nodes?.[anchor.slice(5)]?.net);
  return anchor?spec.nets.find(net=>net.pins.includes(electricalPin(spec,anchor))):undefined;
}
export function pruneWireNodes(spec){
  if(!spec.editor?.wire_nodes)return spec;
  const used=new Set((spec.editor.connection_guides||[]).flatMap(g=>[g.from,g.to]).filter(a=>a.startsWith('node:')).map(a=>a.slice(5)));
  spec.editor.wire_nodes=Object.fromEntries(Object.entries(spec.editor.wire_nodes).filter(([id,node])=>used.has(id)||node.label));
  const names=new Set(Object.values(spec.editor.wire_nodes).map(n=>n.net));
  spec.nets=spec.nets.filter(net=>net.pins.length||!net.wire_only||names.has(net.name));return spec;
}

const componentPage=c=>String((Object.hasOwn(c,'sheet')?c.sheet:c.block)||'').replace(/[^A-Za-z0-9_-]+/g,'_').replace(/^_+|_+$/g,'');
export const pcbExcluded=c=>c?.terminal?.exclude_from_pcb===true;
export function ensureTerminalNets(spec){
  for(const component of spec.components)if(component.terminal&&!spec.nets.some(net=>net.pins.includes(component.ref+'.1'))){
    const base='PORT_'+component.ref;let name=base,index=2;while(spec.nets.some(net=>net.name===name))name=base+'_'+index++;
    spec.nets.push({name,class:'signal',pins:[component.ref+'.1'],placeholder_ref:component.ref});
  }
  return spec;
}
function placeholderNet(spec,net){
  const ref=net?.placeholder_ref;
  return !!net&&(net.class||'signal')==='signal'&&(net.wire_only===true&&net.pins.length<=1||!!ref&&net.pins.length===1&&net.pins[0]===ref+'.1'&&spec.components.some(c=>c.ref===ref&&c.terminal))&&
    !spec.fixed_copper?.some(group=>group.net===net.name&&['tracks','arcs','vias'].some(kind=>group[kind]?.length))&&!spec.fixed_zones?.some(zone=>zone.net===net.name)&&spec.board?.ground_pour!==net.name&&!Object.values(spec.board?.planes||{}).includes(net.name);
}
export function wireMergeNeedsReview(spec,from,to){
  const a=electricalNet(spec,from),b=electricalNet(spec,to);
  return !!(a&&b&&a.name!==b.name&&!placeholderNet(spec,a)&&!placeholderNet(spec,b));
}

export function pruneSheetPorts(spec){
  const names=new Set(spec.nets.map(net=>net.name));
  for(const sheet of Object.values(spec.editor?.sheets||{}))for(const[label,port]of Object.entries(sheet.ports||{}))if(!names.has(port.net)||port.terminal_ref&&!spec.components.some(c=>c.ref===port.terminal_ref))delete sheet.ports[label];
  if(spec.editor?.connection_guides)spec.editor.connection_guides=pruneWireJoins(spec.editor.connection_guides.filter(guide=>[guide.from,guide.to].every(anchor=>!anchor.startsWith('sheet:')||!electricalPin(spec,anchor).startsWith('sheet:'))));
  return pruneWireNodes(spec);
}

export function componentPins(spec, ref) {
  const prefix = `${ref}.`;
  return Object.entries(pinIndex(spec)).filter(([p]) => p.startsWith(prefix)).map(([p, net]) => ({ pin: p.slice(prefix.length), net }));
}

export function updateComponent(spec, ref, patch) {
  const out = structuredClone(spec);
  const part = out.components.find(c => c.ref === ref);
  if (!part) throw new Error(`Component ${ref} was not found.`);
  const nextRef = patch.ref || ref;
  if (nextRef !== ref && out.components.some(c => c.ref === nextRef)) throw new Error(`${nextRef} already exists.`);
  if (!/^[A-Z][A-Z_]*\d+$/.test(nextRef)) throw new Error('Use a designator such as R1 or U2.');
  for (const [k, v] of Object.entries(patch.placement || {})) {
    if (['x_mm', 'y_mm', 'rotation'].includes(k) && !Number.isFinite(v)) throw new Error('Placement must use finite numbers.');
  }
  const priorPlacement=part.placement||{},priorFootprint=part.footprint,priorValue=part.value,priorPage=componentPage(part);
  Object.assign(part, patch);
  const moved=patch.placement&&['x_mm','y_mm','rotation','side'].some(k=>patch.placement[k]!==priorPlacement[k]);
  if (!pcbExcluded(part)&&(moved || (patch.footprint && patch.footprint!==priorFootprint)) && out.fixed_copper) {
    const affected = new Set((out.nets || []).filter(n=>n.pins.some(p=>p.startsWith(`${ref}.`))).map(n=>n.name));
    out.fixed_copper = out.fixed_copper.filter(c=>!affected.has(c.net));
  }
  if (nextRef !== ref) {
    remapObjectOrganization(out,id=>{if(['component:','pads:','graphics:'].some(prefix=>id===prefix+ref))return id.slice(0,id.length-ref.length)+nextRef;for(const prefix of ['symbol:','pad:','drawing:'])if(id.startsWith(prefix+ref+(prefix==='symbol:'?'#':':')))return prefix+nextRef+id.slice(prefix.length+ref.length);return id;});
    for (const net of out.nets || []) net.pins = net.pins.map(p => p.startsWith(`${ref}.`) ? nextRef + p.slice(ref.length) : p);
    for(const field of ['positions','rotations','mirrors'])if(out.editor?.[field])for(const key of Object.keys(out.editor[field]))if(key===ref||key.startsWith(ref+'#')){out.editor[field][nextRef+key.slice(ref.length)]=out.editor[field][key];delete out.editor[field][key];}
    if(out.editor?.connection_guides)out.editor.connection_guides=out.editor.connection_guides.map(g=>({...g,from:g.from.startsWith(ref+'.')||g.from.startsWith(ref+'#')?nextRef+g.from.slice(ref.length):g.from,to:g.to.startsWith(ref+'.')||g.to.startsWith(ref+'#')?nextRef+g.to.slice(ref.length):g.to}));
    for(const sheet of Object.values(out.editor?.sheets||{}))for(const port of Object.values(sheet.ports||{}))if(port.terminal_ref===ref)port.terminal_ref=nextRef;
    for(const value of Object.values(out.editor?.module_instances||{}))if(value.refs)value.refs=value.refs.map(value=>value===ref?nextRef:value);
    for(const instance of Object.values(out.editor?.module_instances||{}))for(const maps of [instance.source_maps,instance.baseline?.maps])if(maps?.refs)for(const[key,value]of Object.entries(maps.refs))if(value===ref)maps.refs[key]=nextRef;
    for(const net of out.nets)if(net.placeholder_ref===ref)net.placeholder_ref=nextRef;
  }
  if(part.terminal&&priorValue!==part.value&&priorPage){
    const old='sheet:'+priorPage+'.'+encodeURIComponent(priorValue),anchor='sheet:'+priorPage+'.'+encodeURIComponent(part.value);
    for(const guide of out.editor?.connection_guides||[])for(const key of ['from','to'])if(guide[key]===old)guide[key]=anchor;
    const ports=out.editor?.sheets?.[priorPage]?.ports;if(ports?.[priorValue]){ports[part.value]=ports[priorValue];delete ports[priorValue];}
  }
  return out;
}

export function removeComponent(spec, ref) {
  const out = structuredClone(spec);
  const affected = new Set((out.nets || []).filter(n=>n.pins.some(p=>p.startsWith(`${ref}.`))).map(n=>n.name));
  const virtual=pcbExcluded(out.components.find(c=>c.ref===ref));
  if(out.fixed_copper&&!virtual)out.fixed_copper=out.fixed_copper.filter(c=>!affected.has(c.net));
  out.components = out.components.filter(c => c.ref !== ref);
  out.nets = (out.nets || []).map(n => ({ ...n, pins: n.pins.filter(p => !p.startsWith(`${ref}.`)) })).filter(n => n.pins.length||Object.values(out.editor?.wire_nodes||{}).some(node=>node.net===n.name));
  if(out.fixed_copper){const names=new Set(out.nets.map(net=>net.name));out.fixed_copper=out.fixed_copper.filter(group=>!affected.has(group.net)||names.has(group.net));}
  if(out.fixed_zones){const remaining=new Set(out.nets.map(n=>n.name));out.fixed_zones=out.fixed_zones.filter(zone=>!zone.net||remaining.has(zone.net));}
  for(const field of ['positions','rotations','mirrors'])if(out.editor?.[field])for(const key of Object.keys(out.editor[field]))if(key===ref||key.startsWith(ref+'#'))delete out.editor[field][key];
  if(out.editor?.connection_guides)out.editor.connection_guides=out.editor.connection_guides.filter(g=>![g.from,g.to].some(p=>p.startsWith(ref+'.')||p.startsWith(ref+'#')));
  if(out.editor?.connection_guides)out.editor.connection_guides=pruneWireJoins(out.editor.connection_guides);
  return pruneSheetPorts(out);
}

export function addComponent(spec, component) {
  const out = structuredClone(spec);
  const prefix = (component.ref || 'U').replace(/\d+$/, '');
  let n = 1;
  while (out.components.some(c => c.ref === `${prefix}${n}`)) n++;
  out.components.push({ ...structuredClone(component), ref: `${prefix}${n}` });
  return out;
}

export function upsertNet(spec, net, originalName = null) {
  const out = structuredClone(spec), refs = new Set(out.components.map(c => c.ref));
  const name = String(net.name || '').trim(), pins = [...new Set(net.pins || [])];
  if (!name || !pins.length&&!Object.values(out.editor?.wire_nodes||{}).some(node=>node.net===(originalName||name))) throw new Error('Give the net a name and at least one pin or wire endpoint.');
  if (out.nets.some(n => n.name === name && n.name !== originalName)) throw new Error(`Net ${name} already exists.`);
  for (const pin of pins) {
    if (!/^[A-Z][A-Z_]*\d+\.[A-Za-z0-9_+-]+$/.test(pin) || !refs.has(pin.split('.')[0])) throw new Error(`Pin ${pin} refers to an invalid or missing component.`);
    const other = out.nets.find(n => n.name !== originalName && n.pins.includes(pin));
    if (other) throw new Error(`${pin} already belongs to ${other.name}. Remove it there before connecting it here.`);
  }
  const next = {...(out.nets.find(n=>n.name===originalName)||{}),...structuredClone(net),name,class:net.class||'signal',pins};
  if(next.wire_only&&(pins.length>1||originalName&&name!==originalName))delete next.wire_only;
  if(next.placeholder_ref&&(name!==originalName||pins.length!==1||pins[0]!==next.placeholder_ref+'.1'||next.class!=='signal'))delete next.placeholder_ref;
  if(originalName&&originalName!==name)renameNetReferences(out,originalName,name,true);
  for (const pin of pins) {
    const [ref, pad] = pin.split('.');
    const c = out.components.find(c => c.ref === ref);
    if (c.no_connect) c.no_connect = c.no_connect.filter(p => String(p) !== pad);
  }
  const i = out.nets.findIndex(n => n.name === originalName);
  if(i>=0&&out.fixed_copper){
    const preserved=out.nets[i].pins.filter(pin=>!pcbExcluded(out.components.find(c=>c.ref===pin.split('.')[0]))).every(pin=>pins.includes(pin));
    out.fixed_copper=out.fixed_copper.filter(c=>c.net!==originalName||preserved).map(c=>c.net===originalName?{...c,net:name}:c);
  }
  if (i >= 0) out.nets[i] = next; else out.nets.push(next);
  if(out.editor?.connection_guides){
    const membership=new Map(out.nets.flatMap(net=>net.pins.map(pin=>[pin,net.name]))),logical=anchor=>electricalPin(out,anchor);
    out.editor.connection_guides=pruneWireJoins(out.editor.connection_guides.filter(guide=>{const a=logical(guide.from),b=logical(guide.to);if(a.startsWith('node:')||b.startsWith('node:'))return electricalNet(out,a)&&electricalNet(out,a)===electricalNet(out,b);return !refs.has(a.split('.')[0])||!refs.has(b.split('.')[0])||membership.has(a)&&membership.get(a)===membership.get(b);}));
  }
  return ensureTerminalNets(out);
}

export function pruneWireJoins(guides){
  let result=guides,changed=true;
  while(changed){const ids=new Set(result.map(guide=>guide.id)),next=result.filter(guide=>[guide.from_join,guide.to_join].filter(Boolean).every(join=>ids.has(join.wire)));changed=next.length!==result.length;result=next;}
  return result;
}

function renameNetReferences(spec,from,to,rebaseBaseline=false){
  remapObjectOrganization(spec,id=>id==='net:'+from?'net:'+to:id);
  for(const node of Object.values(spec.editor?.wire_nodes||{}))if(node.net===from)node.net=to;
  for(const sheet of Object.values(spec.editor?.sheets||{}))for(const port of Object.values(sheet.ports||{}))if(port.net===from)port.net=to;
  for(const instance of Object.values(spec.editor?.module_instances||{}))for(const [key,name]of Object.entries(instance.nets||{}))if(name===from)instance.nets[key]=to;
  for(const instance of Object.values(spec.editor?.module_instances||{})){
    for(const maps of [instance.source_maps,...(rebaseBaseline?[instance.baseline?.maps]:[])])if(maps?.nets)for(const[key,name]of Object.entries(maps.nets))if(name===from)maps.nets[key]=to;
    for(const[key,names]of Object.entries(instance.net_splits||{}))instance.net_splits[key]=[...new Set(names.map(name=>name===from?to:name))];
  }
  for(const zone of spec.fixed_zones||[])if(zone.net===from)zone.net=to;
  if(spec.board?.ground_pour===from)spec.board.ground_pour=to;
  for(const key of Object.keys(spec.board?.planes||{}))if(spec.board.planes[key]===from)spec.board.planes[key]=to;
  for(const row of [...(spec.simulation?.sources||[]),...(spec.simulation?.expect||[])])if(row.net===from)row.net=to;
  if(spec.simulation?.probes)spec.simulation.probes=spec.simulation.probes.map(n=>n===from?to:n);
  for(const row of spec.impedance||[])if(row.nets)row.nets=row.nets.map(n=>n===from?to:n);
}

export function connectPins(spec,from,to,allowMerge=false){
  const refs=new Set(spec.components.map(c=>c.ref));
  for(const p of [from,to])if(p.startsWith('node:')?!spec.editor?.wire_nodes?.[p.slice(5)]:!p.includes('.')||!refs.has(p.split('.')[0]))throw new Error('Choose actual component pins or existing wire endpoints.');
  const a=electricalNet(spec,from),b=electricalNet(spec,to);
  if(from===to||a&&a===b)return structuredClone(spec);
  if(a&&b){
    if(placeholderNet(spec,a)||placeholderNet(spec,b)){
      const target=placeholderNet(spec,a)&&!placeholderNet(spec,b)?b:a,other=target===a?b:a,out=structuredClone(spec);
      out.nets=out.nets.filter(net=>net.name!==other.name);renameNetReferences(out,other.name,target.name);
      return upsertNet(out,{...target,pins:[...new Set([...target.pins,...other.pins])]},target.name);
    }
    if(!allowMerge)throw new Error(`Pins belong to different nets: ${a.name} and ${b.name}. Review the merge first.`);
    const ground=n=>/^(?:[ADPS]?GND|VSS)$/i.test(n.name);
    const target=ground(a)?a:ground(b)?b:b.class==='power'&&a.class!=='power'?b:a,other=target===a?b:a;
    const out=structuredClone(spec);out.nets=out.nets.filter(n=>n.name!==a.name&&n.name!==b.name);
    if(out.fixed_copper)out.fixed_copper=out.fixed_copper.filter(n=>n.net!==a.name&&n.net!==b.name);
    renameNetReferences(out,other.name,target.name);
    return upsertNet(out,{...target,pins:[...new Set([...target.pins,...other.pins])]},null);
  }
  const net=a||b;let name=net?.name;
  if(!name){let i=1;while(spec.nets.some(n=>n.name===`Net_${i}`))i++;name=`Net_${i}`;}
  const out=structuredClone(spec),pins=[...new Set([...(net?.pins||[]),...[from,to].filter(p=>!p.startsWith('node:'))])];
  for(const anchor of [from,to])if(anchor.startsWith('node:'))out.editor.wire_nodes[anchor.slice(5)].net=name;
  return upsertNet(out,{name,class:net?.class||'signal',pins,...(!net&&pins.length<2?{wire_only:true}:{})},net?.name||null);
}

export function messageAction(status, text, pendingQuestion) {
  if (!text.trim()) return 'none';
  if (status === 'waiting' && pendingQuestion) return 'answer';
  if (['running', 'waiting'].includes(status)) return 'queue';
  return 'message';
}

export function editWireRoute(spec,index,waypoints){
  if(!spec.editor?.connection_guides?.[index])throw new Error('Select an existing wire route.');
  if(!Array.isArray(waypoints)||waypoints.length>100||waypoints.some(p=>!Array.isArray(p)||p.length!==2||p.some(v=>!Number.isFinite(v))))throw new Error('Wire bends require finite coordinates.');
  const out=structuredClone(spec);out.editor.connection_guides[index].waypoints=structuredClone(waypoints);delete out.editor.connection_guides[index].fixed_points;return out;
}

const partRef=key=>key.split('#')[0];
const pinRef=pin=>pin.split('.')[0].split('#')[0];
export function selectedWireGeometry(spec,refs){
  const chosen=new Set(refs),nodes=spec.editor?.wire_nodes||{},allowed=anchor=>anchor.startsWith('node:')?!!nodes[anchor.slice(5)]:chosen.has(pinRef(anchor));
  const possible=(spec.editor?.connection_guides||[]).filter(g=>allowed(g.from)&&allowed(g.to)),included=new Set(),active=new Set();let changed=true;
  while(changed){changed=false;for(const guide of possible)if(!included.has(guide)&&[guide.from,guide.to].some(anchor=>anchor.startsWith('node:')?active.has(anchor.slice(5)):chosen.has(pinRef(anchor)))){
    included.add(guide);for(const a of [guide.from,guide.to])if(a.startsWith('node:'))active.add(a.slice(5));changed=true;
  }}
  return {connection_guides:possible.filter(g=>included.has(g)),wire_nodes:Object.fromEntries(Object.entries(nodes).filter(([id])=>active.has(id)))};
}
export function copySelection(spec,refs){
  const chosen=new Set(refs.map(partRef)),components=spec.components.filter(c=>chosen.has(c.ref));
  if(!components.length)throw new Error('Select components to copy.');
  const subset=values=>Object.fromEntries(Object.entries(values||{}).filter(([key])=>chosen.has(partRef(key))));
  const library={symbols:{},footprints:{},parts:{}},include=(kind,id)=>{if(id?.startsWith('Project:')){const key=id.slice(8),value=spec.library?.[kind]?.[key];if(!value)throw new Error('A copied project library dependency is missing.');library[kind][key]=value;}};
  for(const component of components){include('symbols',component.symbol);include('footprints',component.footprint);}
  for(const symbol of Object.values(library.symbols))include('footprints',symbol.footprint);
  const wires=selectedWireGeometry(spec,[...chosen]);
  return structuredClone({schema:'wholeboard.selection.v1',components,library,nets:spec.nets.map(net=>({...net,pins:net.pins.filter(p=>chosen.has(pinRef(p)))})).filter(net=>net.pins.length),editor:{positions:subset(spec.editor?.positions),rotations:subset(spec.editor?.rotations),mirrors:subset(spec.editor?.mirrors),...wires}});
}

export function pasteSelection(spec,clipboard,options={}){
  if(clipboard?.schema!=='wholeboard.selection.v1'||!Array.isArray(clipboard.components)||!clipboard.components.length||clipboard.components.length>500||!Array.isArray(clipboard.nets))throw new Error('The clipboard does not contain copied OpenFabro components.');
  const out=structuredClone(spec),mapping=new Map(),used=new Set(out.components.map(c=>c.ref)),refs=[],nodeIds=new Map(Object.keys(clipboard.editor?.wire_nodes||{}).map(id=>[id,crypto.randomUUID()])),netNames=new Map();
  const stable=value=>JSON.stringify(value,(_,item)=>item&&typeof item==='object'&&!Array.isArray(item)?Object.fromEntries(Object.keys(item).sort().map(key=>[key,item[key]])):item);
  for(const kind of ['symbols','footprints','parts'])for(const[key,value]of Object.entries(clipboard.library?.[kind]||{})){
    out.library||={};out.library[kind]||={};if(out.library[kind][key]&&stable(out.library[kind][key])!==stable(value))throw new Error('A project library asset differs from the copied dependency. Rename it before pasting.');out.library[kind][key]=structuredClone(value);
  }
  const schematicOffset=options.schematicOffset||[40,40],boardOffset=options.boardOffset||[1,1];
  if([...schematicOffset,...boardOffset].some(v=>!Number.isFinite(v)))throw new Error('Paste offsets must be finite.');
  for(const part of clipboard.components){
    if(!/^[A-Z][A-Z_]*\d+$/.test(part.ref)||mapping.has(part.ref))throw new Error('The copied component designators are invalid.');
    const prefix=part.ref.replace(/\d+$/,'');let number=Math.max(0,...[...used].filter(r=>r.replace(/\d+$/,'')===prefix).map(r=>Number(r.match(/\d+$/)[0])))+1;
    const ref=prefix+number;used.add(ref);mapping.set(part.ref,ref);refs.push(ref);
    const component=structuredClone(part),pose=component.placement||{};
    component.ref=ref;component.placement={...pose,locked:false,x_mm:Math.max(0,Math.min(out.board.width_mm,(Number(pose.x_mm)||0)+boardOffset[0])),y_mm:Math.max(0,Math.min(out.board.height_mm,(Number(pose.y_mm)||0)+boardOffset[1]))};
    if(options.sheet!==undefined)component.sheet=options.sheet;
    if(component.terminal){
      const siblings=out.components.filter(c=>c.terminal&&componentPage(c)===componentPage(component)),base=component.value;let label=base,index=2;while(siblings.some(c=>c.value===label))label=base+'_'+index++;component.value=label;
      const reserved=Object.values(out.editor?.sheets?.[componentPage(component)]?.ports||{}).map(port=>String(port.number));let pin=1;while(reserved.includes(String(pin))||siblings.some(c=>String(c.terminal.number)===String(pin)))pin++;component.terminal.number=String(pin);
    }
    out.components.push(component);
  }
  const rename=pin=>{if(pin.startsWith('node:')){if(!nodeIds.has(pin.slice(5)))throw new Error('A copied wire endpoint is missing.');return 'node:'+nodeIds.get(pin.slice(5));}const ref=pinRef(pin);if(!mapping.has(ref))throw new Error('Copied nets refer to components outside the selection.');return mapping.get(ref)+pin.slice(ref.length);};
  for(const net of clipboard.nets){
    if(!Array.isArray(net.pins)||typeof net.name!=='string')throw new Error('Copied nets are invalid.');
    const pins=net.pins.map(rename),power=net.class==='power'||/^(?:[ADPS]?GND|VSS)$/i.test(net.name),existing=out.nets.find(n=>n.name===net.name);
    if(power&&existing){existing.pins.push(...pins);netNames.set(net.name,net.name);continue;}
    let name=net.name;
    if(!power){name=net.name+'_copy';let i=2;while(out.nets.some(n=>n.name===name))name=net.name+'_copy'+i++;}
    const copied={...structuredClone(net),name,pins};if(copied.placeholder_ref)copied.placeholder_ref=mapping.get(copied.placeholder_ref);out.nets.push(copied);netNames.set(net.name,name);
  }
  out.editor||={};out.editor.positions||={};out.editor.rotations||={};
  for(const[id,node]of Object.entries(clipboard.editor?.wire_nodes||{})){
    if(!Array.isArray(node.position)||node.position.length!==2||node.position.some(v=>!Number.isFinite(v))||!netNames.has(node.net))throw new Error('Copied wire endpoints need finite coordinates and a copied net.');
    out.editor.wire_nodes||={};out.editor.wire_nodes[nodeIds.get(id)]={...structuredClone(node),net:netNames.get(node.net),position:node.position.map((v,i)=>v+schematicOffset[i]),sheet:options.sheet??node.sheet??''};
  }
  for(const [key,position]of Object.entries(clipboard.editor?.positions||{})){
    if(!Array.isArray(position)||position.length!==2||position.some(v=>!Number.isFinite(v)))throw new Error('Copied schematic coordinates must be finite.');
    if(mapping.has(partRef(key)))out.editor.positions[mapping.get(partRef(key))+key.slice(partRef(key).length)]=position.map((v,i)=>v+schematicOffset[i]);
  }
  for(const [key,rotation]of Object.entries(clipboard.editor?.rotations||{}))if(mapping.has(partRef(key)))out.editor.rotations[mapping.get(partRef(key))+key.slice(partRef(key).length)]=rotation;
  for(const [key,mirror]of Object.entries(clipboard.editor?.mirrors||{})){
    if(!['','x','y'].includes(mirror))throw new Error('Copied symbol mirrors must be x or y.');
    if(mapping.has(partRef(key))){out.editor.mirrors||={};out.editor.mirrors[mapping.get(partRef(key))+key.slice(partRef(key).length)]=mirror;}
  }
  const copiedGuides=clipboard.editor?.connection_guides||[],wireIds=new Map(copiedGuides.filter(guide=>guide.id).map(guide=>[guide.id,crypto.randomUUID()]));
  out.editor.connection_guides||=[];out.editor.connection_guides.push(...copiedGuides.map(guide=>{
    const copy={...structuredClone(guide),id:wireIds.get(guide.id)||crypto.randomUUID(),from:rename(guide.from),to:rename(guide.to)};
    for(const field of ['waypoints','fixed_points'])if(copy[field])copy[field]=copy[field].map(point=>{if(!Array.isArray(point)||point.length!==2||point.some(v=>!Number.isFinite(v)))throw new Error('Copied wire coordinates must be finite.');return point.map((value,axis)=>value+schematicOffset[axis]);});
    for(const key of ['from_join','to_join'])if(copy[key]){if(wireIds.has(copy[key].wire))copy[key].wire=wireIds.get(copy[key].wire);else delete copy[key];}
    return copy;
  }));
  return{spec:out,refs};
}

export function moveSelection(spec,moves,mode='schematic'){
  const out=structuredClone(spec),affected=new Set();
  for(const {key,x,y}of moves){
    if(!Number.isFinite(x)||!Number.isFinite(y))throw new Error('Coordinates must be finite.');
    const ref=partRef(key),part=out.components.find(c=>c.ref===ref);if(!part)throw new Error(`Component ${ref} was not found.`);
    if(mode==='schematic'){out.editor||={};out.editor.positions||={};out.editor.positions[key]=[x,y];}
    else if(!part.placement?.locked){part.placement={...part.placement,x_mm:x,y_mm:y};if(!pcbExcluded(part))affected.add(ref);}
  }
  if(affected.size&&out.fixed_copper){const nets=new Set(out.nets.filter(n=>n.pins.some(p=>affected.has(pinRef(p)))).map(n=>n.name));out.fixed_copper=out.fixed_copper.filter(c=>!nets.has(c.net));}
  return out;
}

export function addVia(spec,net,position,{diameter=.6,drill=.3}={}){
  if((spec.board.layers||2)<2)throw new Error('A through via requires at least two copper layers.');
  if(!spec.nets.some(n=>n.name===net))throw new Error('Choose an existing net for this via.');
  if(!Array.isArray(position)||position.length!==2||position.some(v=>!Number.isFinite(v))||position[0]<0||position[1]<0||position[0]>spec.board.width_mm||position[1]>spec.board.height_mm)throw new Error('Place the via inside the board.');
  if(!Number.isFinite(diameter)||!Number.isFinite(drill)||drill<=0||diameter<=drill||diameter>10)throw new Error('The via diameter must exceed its positive drill diameter.');
  const out=structuredClone(spec);out.fixed_copper||=[];let copper=out.fixed_copper.find(c=>c.net===net);if(!copper){copper={net,tracks:[],vias:[]};out.fixed_copper.push(copper);}copper.vias||=[];
  copper.vias.push({p:position.map(v=>+v.toFixed(4)),d:diameter,drill});return out;
}

export function addRoute(spec, geometry, from, to, layer = 'F.Cu',width=null) {
  const pad = name => {if(name.startsWith('via:')){const v=geometry.vias?.[Number(name.slice(4))];return v?{...v,x:v.p[0],y:v.p[1],kind:'via'}:null;}return geometry.pads.find(p => `${p.ref}.${p.name}` === name);};
  const a = pad(from), b = pad(to);
  if (!a || !b || !a.net || a.net !== b.net) throw new Error('Select two pads on the same net.');
  if (from === to) throw new Error('Choose a different destination pad.');
  if (!['F.Cu','B.Cu',...Array.from({length:Math.max(0,(spec.board.layers || 2)-2)},(_,i)=>`In${i+1}.Cu`)].includes(layer)) throw new Error('This copper layer is not in the board stackup.');
  const accessible=p=>{if(p.kind==='via'){const layers=geometry.layers||['F.Cu','B.Cu'],ends=p.layers||['F.Cu','B.Cu'],index=layers.indexOf(layer);return index>=Math.min(...ends.map(l=>layers.indexOf(l)))&&index<=Math.max(...ends.map(l=>layers.indexOf(l)));}if(p.front===undefined&&p.back===undefined)return true;return layer==='F.Cu'?p.front:layer==='B.Cu'?p.back:p.kind==='thru_hole';};
  if(!accessible(a)||!accessible(b))throw new Error('A selected pad is not on this copper layer. Connect it through a via first.');
  const out = structuredClone(spec), [ox, oy] = geometry.bbox || [100,100];
  const p = [a.x-ox,a.y-oy], q = [b.x-ox,b.y-oy], dx=q[0]-p[0], dy=q[1]-p[1];
  const corner = Math.abs(dx)>Math.abs(dy) ? [q[0]-Math.sign(dx)*Math.abs(dy),p[1]] : [p[0],q[1]-Math.sign(dy)*Math.abs(dx)];
  const power = out.nets.find(n=>n.name===a.net)?.class === 'power';
  const w = width??(power ? out.rules?.power_track_mm || .5 : out.rules?.track_mm || .25);
  if(!Number.isFinite(w)||w<=0||w>100)throw new Error('Track width must be a finite positive dimension.');
  out.fixed_copper ||= [];
  let copper = out.fixed_copper.find(n=>n.net===a.net);
  if (!copper) { copper={net:a.net,tracks:[],vias:[]}; out.fixed_copper.push(copper); }
  const points=[p,corner,q];
  for(let i=0;i<2;i++) if(Math.hypot(points[i][0]-points[i+1][0],points[i][1]-points[i+1][1])>.001) copper.tracks.push({a:points[i].map(n=>+n.toFixed(4)),b:points[i+1].map(n=>+n.toFixed(4)),w,layer});
  return out;
}
