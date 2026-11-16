const kinds=['symbols','footprints','parts'];
export const libraryId=id=>/^[A-Za-z][A-Za-z0-9_-]{0,63}$/.test(id);

export function padHole(pad){return{shape:pad.drill_shape||'circle',size:[...(pad.drill_size||[pad.drill||0,pad.drill||0])],offset:[...(pad.drill_offset||[0,0])]};}
export function validatePad(pad){
 const number=v=>typeof v==='number'&&Number.isFinite(v)&&Math.abs(v)<=100,point=v=>Array.isArray(v)&&v.length===2&&v.every(number),hole=padHole(pad);
 if(!number(pad.w)||!number(pad.h)||pad.w<=0||pad.h<=0||!number(pad.drill||0)||!['circle','oval'].includes(hole.shape)||!point(hole.size)||!point(hole.offset))throw Error('Use finite positive pad and hole dimensions.');
 if(['smd','connect'].includes(pad.kind||'smd')){if(pad.drill||hole.size.some(Boolean)||hole.offset.some(Boolean))throw Error('Surface and edge pads cannot have a drilled hole.');return;}
 if(hole.size.some(v=>v<=0)||Math.abs(Math.min(...hole.size)-pad.drill)>1e-6)throw Error('Hole width and height must be positive and match the minimum drill diameter.');
 if(hole.shape==='circle'&&Math.abs(hole.size[0]-hole.size[1])>1e-6)throw Error('A circular hole needs equal width and height.');
 const radius=Math.min(...hole.size)/2,ends=hole.size.map(v=>Math.max(0,v/2-radius)),rounding=Math.min(pad.w,pad.h)*(['oval','circle'].includes(pad.shape)?.5:pad.shape==='roundrect'?(pad.rratio??.25):0);
 for(const sign of [-1,1]){const q=hole.offset.map((v,i)=>Math.abs(v+sign*ends[i])-([pad.w,pad.h][i]/2-rounding)),distance=Math.hypot(...q.map(v=>Math.max(0,v)))+Math.min(Math.max(...q),0)-rounding;if(distance+radius>1e-6)throw Error('The hole and its offset must fit inside the pad outline.');}
}
export function editPadField(pad,key,value){
 const next=structuredClone(pad);
 if(key.includes('.')){const[name,index]=key.split('.');next[name]||=name==='drill_offset'?padHole(pad).offset:padHole(pad).size;next[name][+index]=value;}else next[key]=value;
 if(key==='kind'){
  if(value!=='np_thru_hole')delete next.npth_copper;
  if(['smd','connect'].includes(value)){next.drill=0;delete next.drill_shape;delete next.drill_size;delete next.drill_offset;if(next.layer==='*.Cu')next.layer='F.Cu';}
  else if(!next.drill)next.drill=Math.min(next.w,next.h)/2;
 }
 if(key==='drill_shape'){if(value==='circle')delete next.drill_size;else next.drill_size||=[next.drill,next.drill];}
 if(key.startsWith('drill_size.'))next.drill=Math.min(...next.drill_size);
 if(key==='drill'&&next.drill_size)next.drill_size=[value,value];
 if(next.shape==='circle'){if(key==='h')next.w=next.h;else next.h=next.w;}
 if(key==='shape'&&value!=='custom')delete next.custom_shape;
 validatePad(next);return next;
}

export function newAsset(kind,id,spec){
  const first=collection=>{const key=Object.keys(spec.library?.[collection]||{})[0];return key?'Project:'+key:'';};
  if(kind==='symbols')return {name:id,description:'',reference:'U',footprint:first('footprints'),graphics:[{kind:'rectangle',start:[-2.54,2.54],end:[2.54,-2.54],fill:'background'}],pins:[{number:'1',name:'IN',x:-5.08,y:0,angle:0,length:2.54,type:'input',unit:1},{number:'2',name:'OUT',x:5.08,y:0,angle:180,length:2.54,type:'output',unit:1}]};
  if(kind==='footprints')return {name:id,description:'',mount:'smd',height_mm:2,pads:[{name:'1',x:-2,y:0,w:1,h:1.5,angle:0,kind:'smd',shape:'roundrect',drill:0,layer:'F.Cu'},{name:'2',x:2,y:0,w:1,h:1.5,angle:0,kind:'smd',shape:'roundrect',drill:0,layer:'F.Cu'}],graphics:[{kind:'rectangle',start:[-1,-1],end:[1,1],layer:'F.SilkS'}]};
  if(kind==='parts')return {name:id,value:id,reference:'U',description:'',symbol:first('symbols'),footprint:first('footprints'),lcsc:'',mpn:''};
  throw new Error('Choose symbols, footprints or parts.');
}

export function writeAsset(spec,kind,id,value,newId=id){
  if(!kinds.includes(kind)||!libraryId(newId))throw new Error('Use an ID beginning with a letter, with up to 64 letters, digits, dashes or underscores.');
  const next=structuredClone(spec);next.library||={};for(const collection of kinds)next.library[collection]||={};
  if(newId!==id&&next.library[kind][newId])throw new Error('A library asset already uses that ID.');
  const oldLink='Project:'+id,newLink='Project:'+newId,field=kind==='symbols'?'symbol':kind==='footprints'?'footprint':null;
  const references=field?[...next.components,...Object.values(next.library.parts),...(kind==='footprints'?Object.values(next.library.symbols):[])].filter(item=>item[field]===oldLink):[];
  if(value===null){
    if(references.length)throw new Error('This asset is used by a component or library part. Change those links before deleting it.');
    delete next.library[kind][id];return next;
  }
  if(field){
    const entries=value[kind==='symbols'?'pins':'pads']||[],numbers=new Set(entries.map(item=>String(item[kind==='symbols'?'number':'name'])));
    for(const component of next.components.filter(item=>item[field]===oldLink)){
      const required=next.nets.flatMap(net=>net.pins).filter(pin=>pin.startsWith(component.ref+'.')).map(pin=>pin.slice(component.ref.length+1));
      required.push(...(component.no_connect||[]).map(String));
      const missing=required.filter(pin=>!numbers.has(pin));
      if(missing.length)throw new Error(`${component.ref} has connected pin/pad ${missing.join(', ')}. Disconnect it before editing the library.`);
    }
  }
  delete next.library[kind][id];next.library[kind][newId]=structuredClone(value);
  if(field&&newId!==id)for(const reference of references)reference[field]=newLink;
  return next;
}
