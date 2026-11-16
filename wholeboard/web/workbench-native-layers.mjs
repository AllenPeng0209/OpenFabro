const identity=[1,0,0,1,0,0];
const multiply=(a,b)=>[a[0]*b[0]+a[2]*b[1],a[1]*b[0]+a[3]*b[1],a[0]*b[2]+a[2]*b[3],a[1]*b[2]+a[3]*b[3],a[0]*b[4]+a[2]*b[5]+a[4],a[1]*b[4]+a[3]*b[5]+a[5]];
const finite=v=>Number.isFinite(v)&&Math.abs(v)<=1e6;
const numbers=text=>{const values=String(text).trim().split(/[\s,]+/).filter(Boolean).map(Number);if(values.some(v=>!finite(v)))throw Error('Native SVG has invalid coordinates.');return values;};
function transform(text=''){
 let matrix=identity,rest=text;
 for(const match of text.matchAll(/([A-Za-z]+)\s*\(([^)]*)\)/g)){
  rest=rest.replace(match[0],'');const n=numbers(match[2]);let next;
  if(match[1]==='matrix'&&n.length===6)next=n;
  else if(match[1]==='translate'&&n.length>=1&&n.length<=2)next=[1,0,0,1,n[0],n[1]||0];
  else if(match[1]==='scale'&&n.length>=1&&n.length<=2)next=[n[0],0,0,n.length===2?n[1]:n[0],0,0];
  else if(match[1]==='rotate'&&(n.length===1||n.length===3)){const a=n[0]*Math.PI/180,c=Math.cos(a),s=Math.sin(a);next=[c,s,-s,c,0,0];if(n.length===3)next=multiply([1,0,0,1,n[1],n[2]],multiply(next,[1,0,0,1,-n[1],-n[2]]));}
  else if(['skewX','skewY'].includes(match[1])&&n.length===1){const t=Math.tan(n[0]*Math.PI/180);next=match[1]==='skewX'?[1,0,t,1,0,0]:[1,t,0,1,0,0];}
  else throw Error('Native SVG uses an unsupported transform.');
  matrix=multiply(matrix,next);if(matrix.some(v=>!finite(v)))throw Error('Native SVG transform exceeds the coordinate budget.');
 }
 if(rest.replace(/[\s,]/g,''))throw Error('Native SVG transform is invalid.');return matrix;
}
const styleKeys=new Set(['fill','stroke','fill-opacity','stroke-opacity','stroke-width','opacity','fill-rule','stroke-linecap','stroke-linejoin','stroke-miterlimit','stroke-dasharray','stroke-dashoffset','display','visibility']);
function style(node,parent){
 const value={...parent};let opacity=1;
 const declarations=new Map([...styleKeys].filter(k=>node.hasAttribute(k)).map(k=>[k,node.getAttribute(k)]));
 for(const part of (node.getAttribute('style')||'').split(';').filter(s=>s.trim())){const at=part.indexOf(':');if(at<0)throw Error('Native SVG style is invalid.');declarations.set(part.slice(0,at).trim(),part.slice(at+1).trim());}
 for(const [key,text]of declarations){if(!styleKeys.has(key))throw Error('Native SVG uses an unsupported style.');if(key==='opacity')opacity=Number(text);else value[key]=text;}
 if(!Number.isFinite(opacity)||opacity<0||opacity>1)throw Error('Native SVG opacity is invalid.');
 for(const key of ['fill-opacity','stroke-opacity'])if(!Number.isFinite(Number(value[key]))||Number(value[key])<0||Number(value[key])>1)throw Error('Native SVG paint opacity is invalid.');
 for(const key of ['stroke-width','stroke-dashoffset','stroke-miterlimit'])if(!finite(Number(value[key]))||key==='stroke-width'&&Number(value[key])<0||key==='stroke-miterlimit'&&Number(value[key])<1)throw Error('Native SVG stroke dimensions are invalid.');
 if(value['stroke-dasharray']&&value['stroke-dasharray']!=='none'&&numbers(value['stroke-dasharray']).some(n=>n<0))throw Error('Native SVG dash lengths are invalid.');
 return{value,opacity};
}
function number(node,key,fallback){const raw=node.getAttribute(key);if(raw===null){if(fallback!==undefined)return fallback;throw Error('Native SVG geometry is incomplete.');}const n=Number(raw);if(!finite(n))throw Error('Native SVG geometry exceeds the coordinate budget.');return n;}
function pathFor(node){
 const p=new Path2D(),kind=node.localName;
 if(kind==='path'){const d=node.getAttribute('d')||'';if(d.length>2_000_000)throw Error('This native path is too large to display.');return new Path2D(d);}
 if(kind==='circle'||kind==='ellipse'){const rx=number(node,kind==='circle'?'r':'rx'),ry=kind==='circle'?rx:number(node,'ry');if(rx<0||ry<0)throw Error('Native SVG radius is invalid.');p.ellipse(number(node,'cx',0),number(node,'cy',0),rx,ry,0,0,Math.PI*2);}
 else if(kind==='rect'){const x=number(node,'x',0),y=number(node,'y',0),w=number(node,'width'),h=number(node,'height'),rx=Math.min(w/2,number(node,'rx',number(node,'ry',0))),ry=Math.min(h/2,number(node,'ry',rx));if(w<0||h<0||rx<0||ry<0)throw Error('Native SVG rectangle is invalid.');if(!rx||!ry)p.rect(x,y,w,h);else{p.moveTo(x+rx,y);p.lineTo(x+w-rx,y);p.quadraticCurveTo(x+w,y,x+w,y+ry);p.lineTo(x+w,y+h-ry);p.quadraticCurveTo(x+w,y+h,x+w-rx,y+h);p.lineTo(x+rx,y+h);p.quadraticCurveTo(x,y+h,x,y+h-ry);p.lineTo(x,y+ry);p.quadraticCurveTo(x,y,x+rx,y);p.closePath();}}
 else if(kind==='line'){p.moveTo(number(node,'x1',0),number(node,'y1',0));p.lineTo(number(node,'x2',0),number(node,'y2',0));}
 else if(kind==='polyline'||kind==='polygon'){const n=numbers(node.getAttribute('points')||'');if(n.length%2)throw Error('Native SVG polygon is incomplete.');if(n.length)p.moveTo(n[0],n[1]);for(let i=2;i<n.length;i+=2)p.lineTo(n[i],n[i+1]);if(kind==='polygon')p.closePath();}
 else throw Error('Native SVG contains an unsupported drawing primitive.');return p;
}

export function compileNativeLayer(text){
 if(typeof text!=='string'||text.length>16_000_000)throw Error('Native SVG exceeds the display budget.');
 const doc=new DOMParser().parseFromString(text,'image/svg+xml'),root=doc.documentElement;
 if(doc.querySelector('parsererror')||root.localName!=='svg'||root.namespaceURI!=='http://www.w3.org/2000/svg')throw Error('The native layer is not valid SVG.');
 const view=numbers(root.getAttribute('viewBox')||''),width=/^([\d.eE+-]+)mm$/.exec(root.getAttribute('width')||''),height=/^([\d.eE+-]+)mm$/.exec(root.getAttribute('height')||'');
 if(view.length!==4||view[0]!==0||view[1]!==0||!width||!height||Math.abs(Number(width[1])-view[2])>.0001||Math.abs(Number(height[1])-view[3])>.0001||view[2]<=0||view[3]<=0)throw Error('Native layer coordinates must be absolute PCB millimeters.');
 const output=[];let nodes=0;
 const visit=(node,parent,matrix,alpha)=>{
  if(++nodes>50000)throw Error('Native SVG has too many drawing elements.');
  for(const a of node.attributes){if(/^on/i.test(a.name)||/href$/i.test(a.name)||/url\s*\(|javascript:|@import|expression\s*\(/i.test(a.value))throw Error('Active or external SVG content is not supported.');}
  if(['title','desc'].includes(node.localName))return;
  const s=style(node,parent);if(s.value.display==='none'||s.value.visibility==='hidden')return;
  const m=multiply(matrix,transform(node.getAttribute('transform')||'')),opacity=alpha*s.opacity;if(m.some(v=>!finite(v)))throw Error('Native SVG transform exceeds the coordinate budget.');
  if(['svg','g','defs'].includes(node.localName)){if(node.localName==='defs'&&node.children.length)throw Error('Native SVG definitions require unsupported references.');for(const child of node.children)visit(child,s.value,m,opacity);return;}
  output.push({path:pathFor(node),matrix:m,style:s.value,opacity});
 };
 visit(root,{'fill':'#000000','stroke':'none','fill-opacity':'1','stroke-opacity':'1','stroke-width':'1','stroke-dashoffset':'0','stroke-miterlimit':'4','fill-rule':'nonzero','stroke-linecap':'butt','stroke-linejoin':'miter'},identity,1);return output;
}

export function paintNativeLayer(ctx,items,color,opacity=1){
 for(const item of items){const s=item.style;ctx.save();ctx.transform(...item.matrix);ctx.fillStyle=ctx.strokeStyle=color;
  if(s.fill!=='none'){ctx.globalAlpha=opacity*item.opacity*Math.max(0,Math.min(1,Number(s['fill-opacity'])));ctx.fill(item.path,s['fill-rule']==='evenodd'?'evenodd':'nonzero');}
  if(s.stroke!=='none'&&Number(s['stroke-width'])>0){ctx.globalAlpha=opacity*item.opacity*Math.max(0,Math.min(1,Number(s['stroke-opacity'])));ctx.lineWidth=Number(s['stroke-width']);ctx.lineDashOffset=Number(s['stroke-dashoffset']);ctx.miterLimit=Number(s['stroke-miterlimit']);ctx.lineCap=['butt','round','square'].includes(s['stroke-linecap'])?s['stroke-linecap']:'butt';ctx.lineJoin=['round','bevel','miter'].includes(s['stroke-linejoin'])?s['stroke-linejoin']:'miter';ctx.setLineDash(s['stroke-dasharray']&&s['stroke-dasharray']!=='none'?numbers(s['stroke-dasharray']):[]);ctx.stroke(item.path);}
  ctx.restore();
 }
}
