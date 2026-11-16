import * as THREE from './vendor/three.module.js';
import {materialUV} from './workbench-material-model.mjs';

function canvas(width=256,height=256){const value=document.createElement('canvas');value.width=width;value.height=height;return value;}
function noise(x,y){let n=Math.imul(x+31,374761393)^Math.imul(y+73,668265263);n=Math.imul(n^(n>>>13),1274126177);return((n^(n>>>16))>>>0)/4294967295;}
function height(pattern,x,y){
 const random=noise(x,y);
 if(pattern==='wood')return .5+.16*Math.sin(y*.19+Math.sin(x*.03)*2)+.1*Math.sin(y*.8+x*.025)+random*.12;
 if(pattern==='carbon'){const a=Math.floor(x/12),b=Math.floor(y/12),warp=(a+b)%4<2;return .28+(warp?.23*Math.sin(x*Math.PI/12):.23*Math.sin(y*Math.PI/12))+.12*((a+b)%2)+random*.035;}
 if(pattern==='fiberglass')return .7+.12*Math.sin(x*Math.PI/8)*Math.sin(y*Math.PI/8)+random*.06;
 if(pattern==='cork')return .42+.32*noise(Math.floor(x/7),Math.floor(y/7))+random*.12;
 if(pattern==='stone')return .55+.18*noise(Math.floor(x/16),Math.floor(y/16))+random*.14;
 return .64+random*.25;
}

export class MaterialRenderer{
 constructor(renderer){this.renderer=renderer;this.patterns=new Map();this.environment=null;}
 studio(){
  if(this.environment)return this.environment.texture;const image=canvas(1024,512),ctx=image.getContext('2d'),gradient=ctx.createLinearGradient(0,0,0,512);gradient.addColorStop(0,'#b9c4d2');gradient.addColorStop(.45,'#333840');gradient.addColorStop(.6,'#161b21');gradient.addColorStop(1,'#53555a');ctx.fillStyle=gradient;ctx.fillRect(0,0,1024,512);
  for(const [x,y,w,h,alpha]of[[70,55,90,290,.9],[360,30,200,100,1],[720,90,40,310,.8],[880,40,85,155,.7]]){ctx.fillStyle=`rgba(255,255,255,${alpha})`;ctx.fillRect(x,y,w,h);}const texture=new THREE.CanvasTexture(image);texture.mapping=THREE.EquirectangularReflectionMapping;texture.colorSpace=THREE.SRGBColorSpace;const generator=new THREE.PMREMGenerator(this.renderer);this.environment=generator.fromEquirectangular(texture);generator.dispose();texture.dispose();return this.environment.texture;
 }
 pattern(name){
  if(this.patterns.has(name))return this.patterns.get(name);const image=canvas(),normalImage=canvas(),ctx=image.getContext('2d'),normalContext=normalImage.getContext('2d'),pixels=ctx.createImageData(256,256),normalPixels=normalContext.createImageData(256,256);
  for(let y=0;y<256;y++)for(let x=0;x<256;x++){const i=(y*256+x)*4,value=Math.max(0,Math.min(1,height(name,x,y))),dx=height(name,(x+1)%256,y)-height(name,(x+255)%256,y),dy=height(name,x,(y+1)%256)-height(name,x,(y+255)%256),n=new THREE.Vector3(-dx*1.8,-dy*1.8,1).normalize();for(let j=0;j<3;j++){pixels.data[i+j]=Math.round((.55+value*.45)*255);normalPixels.data[i+j]=Math.round(([n.x,n.y,n.z][j]*.5+.5)*255);}pixels.data[i+3]=normalPixels.data[i+3]=255;}
  ctx.putImageData(pixels,0,0);normalContext.putImageData(normalPixels,0,0);const color=new THREE.CanvasTexture(image),normal=new THREE.CanvasTexture(normalImage);color.colorSpace=THREE.SRGBColorSpace;for(const texture of[color,normal]){texture.wrapS=texture.wrapT=THREE.RepeatWrapping;texture.anisotropy=Math.min(8,this.renderer.capabilities.getMaxAnisotropy());}const result={color,normal};this.patterns.set(name,result);return result;
 }
 prepare(mesh,source,origin){
  mesh.userData.originalMap=mesh.material.map;mesh.userData.physical=source.material;
  if(source.material?.pattern&&source.material.pattern!=='none'){
   const positions=mesh.geometry.getAttribute('position'),normals=mesh.geometry.getAttribute('normal');mesh.geometry.setAttribute('uv',new THREE.BufferAttribute(materialUV(positions.array,normals.array,source.material.repeat_mm||20,origin),2));mesh.userData.pattern=this.pattern(source.material.pattern);
  }
 }
 apply(mesh,style){
  const material=mesh.material,source=mesh.userData,physical=source.physical,realistic=style==='realistic';
  if(!physical)return;
  material.transmission=realistic?physical.transmission:0;material.ior=physical.ior;material.clearcoat=realistic?physical.clearcoat||0:0;material.clearcoatRoughness=physical.clearcoat_roughness??.2;material.envMap=realistic?this.studio():null;material.envMapIntensity=realistic?1.2:1;
  material.map=realistic&&source.pattern?source.pattern.color:source.originalMap||null;material.normalMap=realistic&&source.pattern?source.pattern.normal:null;material.normalScale.set(.35,.35);material.needsUpdate=true;
 }
 dispose(){this.environment?.dispose();for(const value of this.patterns.values()){value.color.dispose();value.normal.dispose();}this.patterns.clear();}
}
