const keys=['side','group','section','order','subsymbol','name'];
export function sharedPinValues(pins){
 return Object.fromEntries(keys.map(key=>{const values=pins.map(p=>p[key]??(key==='name'?p.number:key==='order'?0:''));return[key,values.length&&values.every(v=>v===values[0])?values[0]:null];}));
}
export function selectSymbolPins(current,id,visible,{additive=false,range=false,anchor=null}={}){
 const selected=additive?new Set(current):new Set();
 if(range&&visible.includes(anchor)&&visible.includes(id)){const a=visible.indexOf(anchor),b=visible.indexOf(id);for(const key of visible.slice(Math.min(a,b),Math.max(a,b)+1))selected.add(key);}
 else if(additive&&selected.has(id))selected.delete(id);else selected.add(id);
 return{selected,anchor:range&&visible.includes(anchor)?anchor:id};
}
export function symbolPreview(scene,ref){
 const scale=scene.mm_per_unit,origin=scene.origin_mm;let x=60,maxHeight=180;
 const symbols=(scene.symbols||[]).filter(s=>s.ref===ref).map(symbol=>{
  const definition=scene.definitions[symbol.definition],[x0,y0,x1,y1]=definition.bbox,width=(x1-x0)/scale,height=(y1-y0)/scale;
  const position=[x-x0/scale,80+y1/scale],fields=[{name:'Reference',value:ref,position_mm:[origin+position[0]*scale,origin+(60)*scale],left:false},{name:'Value',value:(symbol.fields||[]).find(f=>f.name==='Value')?.value||'',position_mm:[origin+position[0]*scale,origin+(100+height)*scale],left:false}];
  x+=Math.max(130,width)+100;maxHeight=Math.max(maxHeight,height+160);
  return{...symbol,position,rotation:0,mirror:'',fields};
 });
 return{...scene,symbols,bbox:[0,0,Math.max(350,x),maxHeight]};
}
export function pinDrop(scene,point){
 const scale=scene.mm_per_unit;let best=null;
 for(const symbol of scene.symbols||[]){
  const definition=scene.definitions[symbol.definition],[x0,y0,x1,y1]=definition.bbox,[x,y]=symbol.position;
  const bounds=[x+x0/scale,y-y1/scale,x+x1/scale,y-y0/scale],dx=Math.max(bounds[0]-point[0],0,point[0]-bounds[2]),dy=Math.max(bounds[1]-point[1],0,point[1]-bounds[3]),distance=Math.hypot(dx,dy);
  if(distance>80||best&&distance>=best.distance)continue;
  const sections=definition.parametric?.sections||[],localY=(y-point[1])*scale;
  const distanceTo=s=>Math.max(s.bounds[1]-localY,0,localY-s.bounds[3]);
  const section=sections.find(s=>localY>=s.bounds[1]&&localY<=s.bounds[3])||sections.reduce((a,b)=>!a||distanceTo(b)<distanceTo(a)?b:a,null);
  const edgesBox=section?[x+section.bounds[0]/scale,y-section.bounds[3]/scale,x+section.bounds[2]/scale,y-section.bounds[1]/scale]:bounds;
  const clamp=(v,a,b)=>Math.max(a,Math.min(b,v));
  const edges=[['left',Math.hypot(point[0]-edgesBox[0],point[1]-clamp(point[1],edgesBox[1],edgesBox[3]))],['right',Math.hypot(point[0]-edgesBox[2],point[1]-clamp(point[1],edgesBox[1],edgesBox[3]))],['top',Math.hypot(point[0]-clamp(point[0],edgesBox[0],edgesBox[2]),point[1]-edgesBox[1])],['bottom',Math.hypot(point[0]-clamp(point[0],edgesBox[0],edgesBox[2]),point[1]-edgesBox[3])]].sort((a,b)=>a[1]-b[1]);
  best={distance,side:edges[0][0],section:section?.name||'',subsymbol:definition.parametric?.suffix||'',unit:symbol.unit};
 }
 if(!best)return null;const{distance,...result}=best;return result;
}
