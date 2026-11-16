const collections={tracks:['a','b'],arcs:['a','m','b'],vias:['p']};
const near=(a,b)=>Math.hypot(a[0]-b[0],a[1]-b[1])<.0001;
const point=p=>Array.isArray(p)&&p.length===2&&p.every(v=>Number.isFinite(v)&&Math.abs(v)<=2000);
const round=p=>p.map(v=>+v.toFixed(4));
export const copperLayers=spec=>['F.Cu',...Array.from({length:Math.max(0,(spec.board.layers||2)-2)},(_,i)=>`In${i+1}.Cu`),...((spec.board.layers||2)>1?['B.Cu']:[])];

export function adoptCopper(spec,geometry){
  const out=structuredClone(spec),nets=new Set(out.nets.map(net=>net.name)),groups=new Map(),[ox,oy]=geometry.bbox||[100,100];
  const local=p=>round([p[0]-ox,p[1]-oy]);
  for(const [kind,coordinates]of Object.entries(collections))for(const item of geometry[kind]||[]){
    if(!nets.has(item.net))throw new Error('This native copper belongs to an unknown net. Import its electrical connections before editing.');
    const group=groups.get(item.net)||{net:item.net,tracks:[],arcs:[],vias:[]};groups.set(item.net,group);
    const copy=structuredClone(item);copy.id||=crypto.randomUUID();for(const key of coordinates)copy[key]=local(copy[key]);group[kind].push(copy);
  }
  out.fixed_copper=[...groups.values()];if(geometry.zone_sources)out.fixed_zones=structuredClone(geometry.zone_sources);return out;
}

export function editCopper(spec,geometry,selection,patch){
  const keys=collections[selection?.kind];
  if(!keys)throw new Error('Select a track, arc or via.');
  const selected=geometry[selection.kind]?.find(item=>item.id===selection.id);
  if(!selected)throw new Error('The layout changed. Select this copper object again.');
  const out=adoptCopper(spec,geometry),groups=new Map(out.fixed_copper.map(group=>[group.net,group])),layers=copperLayers(spec);
  const group=groups.get(selected.net),items=group[selection.kind],index=items.findIndex(item=>item.id===selection.id),item=items[index];
  if(patch===null)items.splice(index,1);
  else{
    const allowed=new Set([...keys,'locked',...(selection.kind==='vias'?['d','drill','layers','type']:['w','layer']),...(selection.kind==='tracks'?['split']:[])]);
    if(Object.keys(patch).some(key=>!allowed.has(key)))throw new Error('This edit cannot change the copper identity or electrical net.');
    if(patch.locked!==undefined&&typeof patch.locked!=='boolean')throw Error('Copper protection must be a boolean.');
    for(const key of keys)if(patch[key]!==undefined&&!point(patch[key]))throw new Error('Copper coordinates must be finite 2D points.');
    if(patch.layer!==undefined&&!layers.includes(patch.layer))throw new Error('Choose a copper layer in this board stackup.');
    if(patch.w!==undefined&&(!Number.isFinite(patch.w)||patch.w<=0||patch.w>100))throw new Error('Trace width must be finite and positive.');
    const original=structuredClone(item);
    const originalGroup=structuredClone(group);
    const moveJunction=(old,next)=>{
      const via=originalGroup.vias.find(v=>near(v.p,old));
      const spans=(v,layer)=>{const ends=v.layers||['F.Cu','B.Cu'];return layers.indexOf(layer)>=Math.min(...ends.map(l=>layers.indexOf(l)))&&layers.indexOf(layer)<=Math.max(...ends.map(l=>layers.indexOf(l)));};
      const attached=target=>selection.kind==='vias'?spans(original,target.layer):target.layer===original.layer||(via&&spans(via,target.layer)&&spans(via,original.layer));
      for(const kind of ['tracks','arcs'])for(let i=0;i<group[kind].length;i++){const target=group[kind][i],prior=originalGroup[kind][i];if(attached(prior))for(const key of ['a','b'])if(near(prior[key],old))target[key]=round(next);}
      for(let i=0;i<group.vias.length;i++){const target=group.vias[i],prior=originalGroup.vias[i];if(near(prior.p,old)&&(selection.kind==='vias'||spans(prior,original.layer)))target.p=round(next);}
    };
    for(const key of keys)if(patch[key]!==undefined){
      if(key!=='m')moveJunction(original[key],patch[key]);
      item[key]=round(patch[key]);
    }
    for(const key of ['w','layer','d','drill','layers','type','locked'])if(patch[key]!==undefined)item[key]=structuredClone(patch[key]);
    if(selection.kind==='vias'){
      if(!Number.isFinite(item.d)||!Number.isFinite(item.drill)||item.drill<=0||item.d<=item.drill||item.d>100)throw new Error('A via needs a positive drill smaller than its diameter.');
      const span=item.layers||['F.Cu','B.Cu'];
      if(span.length!==2||span[0]===span[1]||span.some(layer=>!layers.includes(layer)))throw new Error('Choose two distinct copper layers for the via.');
    }else if(near(item.a,item.b))throw new Error('A trace must have distinct endpoints.');
    if(patch.split!==undefined){
      const at=patch.split;if(!point(at)||near(at,item.a)||near(at,item.b))throw new Error('Place the new vertex between the trace endpoints.');
      const dx=item.b[0]-item.a[0],dy=item.b[1]-item.a[1],t=((at[0]-item.a[0])*dx+(at[1]-item.a[1])*dy)/(dx*dx+dy*dy),on=[item.a[0]+t*dx,item.a[1]+t*dy];
      if(t<=0||t>=1||!near(at,on))throw new Error('Place the new vertex on this trace.');
      const tail={...structuredClone(item),id:crypto.randomUUID(),a:round(at)};item.b=round(at);items.splice(index+1,0,tail);
    }
  }
  out.fixed_copper=[...groups.values()];
  if(geometry.zone_sources)out.fixed_zones=structuredClone(geometry.zone_sources);
  return out;
}

export function previewCopper(spec,geometry,selection,patch){
  return copperGeometry(editCopper(spec,geometry,selection,patch),geometry);
}

export function copperGeometry(spec,geometry){
  const out=structuredClone(geometry),[ox,oy]=geometry.bbox||[100,100];
  for(const [kind,keys]of Object.entries(collections))out[kind]=(spec.fixed_copper||[]).flatMap(group=>(group[kind]||[]).map(item=>{const value={...structuredClone(item),net:group.net};for(const key of keys)value[key]=[value[key][0]+ox,value[key][1]+oy];return value;}));
  if(spec.fixed_zones)out.zone_sources=structuredClone(spec.fixed_zones);
  return out;
}
