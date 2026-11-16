import { esc } from './workbench-icons.mjs';
import { arcThroughPoints } from './workbench-geometry.mjs';

const point=(p)=>p.join(' ');
let textContext;
const overlap=(a,b,pad=0)=>a[0]<b[2]+pad&&a[2]>b[0]-pad&&a[1]<b[3]+pad&&a[3]>b[1]-pad;
function netTextWidth(value){
  if(!textContext&&typeof document!=='undefined')textContext=document.createElement('canvas').getContext('2d');
  if(!textContext)return String(value).length*6;
  textContext.font='10px Roboto, Arial, sans-serif';return Math.ceil(textContext.measureText(String(value)).width);
}
function pinNetName(net,ref,px,py,dx,dy,origin,wires,reservations){
  const vertical=Math.abs(dy)>.5,angle=vertical?(dy>0?-90:90):0,anchor=vertical||dx<.5?'start':'end',width=netTextWidth(net),a=angle*Math.PI/180;
  let choice;
  for(const distance of [7,17,27,37,47,57]){
    const x=px-dx*distance,y=py-dy*distance,left=anchor==='end'?-width:0;
    const corners=[[left,-13],[left+width,-13],[left+width,2],[left,2]].map(([u,v])=>[origin[0]+x+u*Math.cos(a)-v*Math.sin(a),origin[1]+y+u*Math.sin(a)+v*Math.cos(a)]);
    const box=[Math.min(...corners.map(p=>p[0])),Math.min(...corners.map(p=>p[1])),Math.max(...corners.map(p=>p[0])),Math.max(...corners.map(p=>p[1]))];choice={x,y,box};
    if(!wires.some(wire=>overlap(box,wire,2))&&!reservations.some(other=>overlap(box,other,2)))break;
  }
  reservations.push(choice.box);
  return `<g transform="translate(${choice.x},${choice.y}) rotate(${angle})"><text class="pin-net-name" data-pin-net="${esc(ref)}" x="0" y="-3" text-anchor="${anchor}" fill="#8bb9a3" font-size="10">${esc(net)}</text></g>`;
}
function graphic(g){
  const fill=g.fill==='background'?'#101010':g.fill==='outline'?'#b9bdbb':'none';
  const style=`class="component-body" stroke="#b9bdbb" stroke-width="0.2032" stroke-linecap="round" stroke-linejoin="round" fill="${fill}"`;
  if(g.kind==='rectangle')return `<rect ${style} x="${Math.min(g.start[0],g.end[0])}" y="${Math.min(g.start[1],g.end[1])}" width="${Math.abs(g.end[0]-g.start[0])}" height="${Math.abs(g.end[1]-g.start[1])}"/>`;
  if(g.kind==='polyline')return `<polyline ${style} points="${g.points.map(p=>p.join(',')).join(' ')}"/>`;
  if(g.kind==='bezier'&&g.points.length>=4)return `<path ${style} d="M${point(g.points[0])} C${g.points.slice(1,4).map(point).join(' ')}"/>`;
  if(g.kind==='circle')return `<circle ${style} cx="${g.center[0]}" cy="${g.center[1]}" r="${g.radius}"/>`;
  if(g.kind==='arc'){
    const arc=arcThroughPoints(g.start,g.mid,g.end);
    return `<path ${style} d="M${point(g.start)} ${arc?`A${arc.radius} ${arc.radius} 0 ${arc.large} ${arc.sweep} ${point(g.end)}`:`L${point(g.end)}`}"/>`;
  }
  if(g.kind==='text')return `<g transform="translate(${point(g.position)}) rotate(${g.angle||0})"><text transform="scale(1,-1)" fill="#c7c7c7" font-size="${g.size||1.27}" text-anchor="middle">${esc(g.text)}</text></g>`;
  return '';
}

export function nativeSymbol(instance,definition,spec,pinNet,scale,origin,selected,wireBoxes=[]){
  const [x,y]=instance.position,rotation=instance.rotation||0,a=rotation*Math.PI/180;
  const mx=instance.mirror==='y'?-1:1,my=instance.mirror==='x'?-1:1;
  const local=(px,py)=>[mx*(px*Math.cos(a)-py*Math.sin(a))/scale,my*(-px*Math.sin(a)-py*Math.cos(a))/scale];
  const [x0,y0,x1,y1]=definition.bbox,corners=[[x0,y0],[x1,y0],[x1,y1],[x0,y1]].map(p=>local(...p));
  const bx=Math.min(...corners.map(p=>p[0]))-20,by=Math.min(...corners.map(p=>p[1]))-25;
  const bw=Math.max(...corners.map(p=>p[0]))-bx+20,bh=Math.max(...corners.map(p=>p[1]))-by+25;
  const margin=70+Math.max(0,...definition.pins.map(p=>netTextWidth(pinNet[`${instance.ref}.${p.number}`]||''))),nearby=wireBoxes.filter(box=>overlap(box,[x+bx-margin,y+by-margin,x+bx+bw+margin,y+by+bh+margin]));
  const reservations=(instance.fields||[]).map(field=>{const fx=(field.position_mm[0]-origin)/scale,fy=(field.position_mm[1]-origin)/scale,width=netTextWidth(field.value);return[fx-(field.left?0:width/2)-1,fy-8,fx+(field.left?width:width/2)+1,fy+7];});
  let body=definition.graphics.map(graphic).join(''),pins='';
  for(const p of definition.pins){
    if(p.hidden)continue;
    const angle=p.angle*Math.PI/180,ex=p.x+Math.cos(angle)*p.length,ey=p.y+Math.sin(angle)*p.length;
    if(!p.hidden){
      body+=`<path class="component-body" d="M${p.x} ${p.y}L${ex} ${ey}" fill="none" stroke="#b9bdbb" stroke-width="0.2032"/>`;
      if(p.shape?.includes('inverted'))body+=`<circle cx="${ex}" cy="${ey}" r="0.5" fill="#101010" stroke="#b9bdbb" stroke-width="0.2032"/>`;
      if(p.shape?.includes('clock')){const dx=Math.cos(angle),dy=Math.sin(angle),perp=[-dy*.6,dx*.6];body+=`<path d="M${ex+perp[0]} ${ey+perp[1]}L${ex+dx*1.2} ${ey+dy*1.2}L${ex-perp[0]} ${ey-perp[1]}" fill="none" stroke="#b9bdbb" stroke-width="0.2032"/>`;}
    }
    const [px,py]=local(p.x,p.y),[qx,qy]=local(ex,ey),dx=(qx-px)/(p.length/scale||1),dy=(qy-py)/(p.length/scale||1);
    const ref=`${instance.ref}.${p.number}`,anchor=`${instance.key}.${p.number}`,net=pinNet[ref];
    if(definition.show_pin_numbers&&!p.hidden)pins+=`<text x="${(px+qx)/2-dy*5}" y="${(py+qy)/2+dx*5}" text-anchor="middle" fill="#919791" font-size="8">${esc(p.number)}</text>`;
    if(!definition.show_pin_numbers&&!p.hidden)pins+=`<text data-inspection-pin-number="${esc(p.number)}" class="inspection-pin-label" display="none" x="${(px+qx)/2-dy*5}" y="${(py+qy)/2+dx*5}" text-anchor="middle" fill="#919791" font-size="8">${esc(p.number)}</text>`;
    if(!p.hidden&&p.name&&p.name!=='~'){
      const tx=qx+dx*6,ty=qy+dy*6,vertical=Math.abs(dy)>.5;
      pins+=`<text ${definition.show_pin_names?`data-symbol-pin-name="${esc(p.number)}"`:`data-inspection-pin-name="${esc(p.number)}" class="inspection-pin-label" display="none"`} x="${tx}" y="${ty+(vertical?0:3)}" ${vertical?`transform="rotate(${dy>0?90:-90} ${tx} ${ty})"`:''} text-anchor="${vertical||dx>0?'start':'end'}" fill="#aeb5ae" font-size="9">${esc(p.name.replace(/~\{([^}]+)\}/g,'$1'))}</text>`;
    }
    const labeled=spec.editor?.connection_guides?.some(g=>[g.from,g.to].some(a=>a.replace(/#\d+(?=\.)/,'')===ref)&&[g.from,g.to].some(a=>a.startsWith('node:')&&spec.editor?.wire_nodes?.[a.slice(5)]?.label));
    if(net&&!labeled)pins+=pinNetName(net,ref,px,py,dx,dy,[x,y],nearby,reservations);
    else if(!net&&p.type!=='no_connect')pins+=`<path d="M${px-3} ${py-3}l6 6m-6 0 6-6" stroke="#7182a0" stroke-width="1"/>`;
    pins+=`<circle cx="${px}" cy="${py}" r="5.5" fill="transparent" data-pinref="${esc(ref)}" data-anchor="${esc(anchor)}" style="cursor:crosshair"/><circle cx="${px}" cy="${py}" r="1.6" fill="#89958c" pointer-events="none"/>`;
  }
  for(const field of instance.fields){
    const fx=(field.position_mm[0]-origin)/scale-x,fy=(field.position_mm[1]-origin)/scale-y;
    let value=field.value;if(field.name==='Reference'){if(definition.parametric?.suffix)value+='.'+definition.parametric.suffix;else if(!definition.parametric&&definition.unit_count>1)value+=String.fromCharCode(64+instance.unit);}
    pins+=`<text x="${fx}" y="${fy+3}" text-anchor="${field.left?'start':'middle'}" font-family="Roboto,Arial,sans-serif" font-size="10" fill="${field.name==='Reference'?'#ddd':'#aeb6af'}">${esc(value)}</text>`;
  }
  return `<g class="canvas-component${selected===instance.ref?' selected':''}" data-ref="${esc(instance.ref)}" data-symbol-key="${esc(instance.key)}" data-x="${x}" data-y="${y}" transform="translate(${x},${y})" role="button" tabindex="0" aria-label="${esc(instance.ref+' '+(spec.components.find(c=>c.ref===instance.ref)?.value||''))}"><rect class="component-hitbox" x="${bx}" y="${by}" width="${bw}" height="${bh}" fill="transparent" pointer-events="all"/><rect class="selection-outline" x="${bx}" y="${by}" width="${bw}" height="${bh}" rx="3"/><g class="native-symbol-graphics" transform="scale(${mx},${my}) rotate(${-rotation}) scale(${1/scale},${-1/scale})">${body}</g>${pins}</g>`;
}

export function nativeNetLabel(node,annotation,definitions,scale,origin,selected){
  let body='';const rotation=node.label.rotation||0;
  if(annotation){
    const definition=definitions[annotation.definition];let shape=definition.graphics.map(graphic).join('');
    for(const p of definition.pins){const a=p.angle*Math.PI/180;shape+=`<path d="M${p.x} ${p.y}L${p.x+Math.cos(a)*p.length} ${p.y+Math.sin(a)*p.length}" stroke="#b9bdbb" stroke-width=".2032"/>`;}
    const mx=annotation.mirror==='y'?-1:1,my=annotation.mirror==='x'?-1:1;
    body=`<g class="native-label-graphics" transform="scale(${mx},${my}) rotate(${-rotation}) scale(${1/scale},${-1/scale})">${shape}</g>`;
    for(const field of annotation.fields.filter(f=>f.name==='Value')){const x=(field.position_mm[0]-origin)/scale-node.position[0],y=(field.position_mm[1]-origin)/scale-node.position[1];body+=`<text x="${x}" y="${y+3}" fill="#8bb9a3" font-size="10" text-anchor="${field.left?'start':'middle'}">${esc(node.net)}</text>`;}
  }else body=`<g transform="rotate(${-rotation})"><path d="M0 0h12" stroke="#8bb59a" stroke-width="1.4"/><text x="15" y="-4" fill="#8bb9a3" font-size="11">${esc(node.net)}</text></g>`;
  const width=Math.max(65,node.net.length*7+25);
  return `<g class="schematic-net-label${selected?' selected':''}" data-net-label="${esc(node.id)}" data-wire-node="${esc(node.id)}" data-x="${node.position[0]}" data-y="${node.position[1]}" transform="translate(${node.position.join(',')})" role="button" tabindex="0" aria-label="${esc('Net label '+node.net)}"><title>${esc(node.net)} · named project net</title><rect x="-18" y="-25" width="${width}" height="60" fill="transparent" pointer-events="all"/>${selected?`<rect x="-18" y="-25" width="${width}" height="60" fill="none" stroke="#1dfdc0" stroke-width="1" stroke-dasharray="4 3" pointer-events="none"/>`:''}${body}<circle cx="0" cy="0" r="${selected?4:2}" fill="#8bb59a" pointer-events="none"/></g>`;
}

export function nativeSheet(sheet){
  const [x,y]=sheet.position,[w,h]=sheet.size;
  const ports=sheet.ports.map(p=>{
    const px=p.position[0]-x,py=p.position[1]-y,angle=p.angle??180,dx=Math.round(Math.cos(angle*Math.PI/180)),dy=-Math.round(Math.sin(angle*Math.PI/180)),side=p.side||({0:'right',90:'top',180:'left',270:'bottom'}[angle]||'left');
    const tx=px-dx*9+(dx?0:4),ty=py-dy*9+(dx?4:0),rotation=dy?`transform="rotate(${dy<0?90:-90} ${tx} ${ty})"`:'';
    const number=p.number?`<text x="${px+dx*10+(dy?5:0)}" y="${py+dy*10+(dx?-5:0)}" text-anchor="middle" font-size="8" fill="#82978b" pointer-events="none">${esc(p.number)}</text>`:'';
    return `<g class="canvas-net" data-net="${esc(p.net)}" data-boundary-side="${side}"><path d="M${px+dx*18} ${py+dy*18}L${px} ${py}" stroke="#91aa9a" fill="none" stroke-width="1.3"/><rect x="${px-3}" y="${py-3}" width="6" height="6" fill="#9fac9e"/>${p.pin?`<circle cx="${px}" cy="${py}" r="7" fill="transparent" data-pinref="${esc(p.pin)}" data-anchor="sheet:${esc(sheet.target)}.${esc(encodeURIComponent(p.label||p.net))}" style="cursor:crosshair"/>`:''}<text x="${tx}" y="${ty}" ${rotation} text-anchor="${dx>0?'end':'start'}" font-size="11" fill="#abbcac" pointer-events="none">${esc(p.label||p.net)}</text>${number}</g>`;
  }).join('');
  return `<g class="schematic-module" data-sheet-target="${esc(sheet.target)}" data-x="${x}" data-y="${y}" data-width="${w}" data-height="${h}" transform="translate(${x},${y})" role="button" tabindex="0" aria-label="Open sheet ${esc(sheet.name)}"><rect class="sheet-boundary" width="${w}" height="${h}" fill="#151b17" stroke="#7b9585" stroke-width="1.5"/><text x="0" y="-12" fill="#c2cdc4" font-family="Roboto" font-size="16">${esc(sheet.name)}</text>${ports}<rect class="sheet-resize-handle" x="${w-5}" y="${h-5}" width="10" height="10"/><text x="${w-14}" y="${h-8}" text-anchor="end" font-size="9" fill="#66786b" pointer-events="none">Double click to open</text></g>`;
}
