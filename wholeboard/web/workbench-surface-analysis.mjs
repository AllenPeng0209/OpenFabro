import * as THREE from './vendor/three.module.js';

export function surfaceMetric(principal,metric='max_abs'){
 const[a,b]=principal;
 const value=metric==='mean'?(a+b)/2:metric==='gaussian'?a*b:metric==='min'?Math.min(a,b):metric==='max'?Math.max(a,b):Math.max(Math.abs(a),Math.abs(b));
 return value===0?0:value;
}
function validSample(sample){return sample&&Array.isArray(sample.normal)&&sample.normal.length===3&&sample.normal.every(Number.isFinite)&&Math.hypot(...sample.normal)>1e-9&&Array.isArray(sample.principal)&&sample.principal.length===2&&sample.principal.every(Number.isFinite);}
export function surfaceAttributes(mesh,metric='max_abs'){
 const count=(mesh.v||[]).length/3,normals=new Float32Array(count*3),values=new Float32Array(count),valid=new Float32Array(count);let usable=0;
 for(let i=0;i<count;i++){
  const sample=mesh.surface_samples?.[i];normals[i*3+2]=1;
  if(!validSample(sample))continue;
  normals.set(sample.normal,i*3);values[i]=surfaceMetric(sample.principal,metric);valid[i]=1;usable++;
 }
 return{normals,values,valid,available:usable>0,validSamples:usable,total:count};
}
export function surfaceSummary(data){
 let valid=0,total=0;const faces=new Set();
 for(const mesh of data.meshes||[]){total+=(mesh.v||[]).length/3;for(const sample of mesh.surface_samples||[]){if(!validSample(sample))continue;valid++;faces.add(mesh.body_id+':'+sample.face_index);}}
 return{available:valid>0,validSamples:valid,total,unavailableSamples:total-valid,faces:faces.size};
}

const vertexShader=`
 #include <common>
 #include <clipping_planes_pars_vertex>
 attribute vec3 nativeSurfaceNormal;
 attribute float nativeSurfaceValue;
 attribute float nativeSurfaceValid;
 uniform bool surfaceOrthographic;
 varying vec3 analysisNormal;
 varying vec3 analysisView;
 varying float analysisValue;
 varying float analysisValid;
 void main(){
  vec4 mvPosition=modelViewMatrix*vec4(position,1.0);
  gl_Position=projectionMatrix*mvPosition;
  analysisNormal=normalMatrix*nativeSurfaceNormal;
  analysisView=surfaceOrthographic?vec3(0.0,0.0,1.0):-mvPosition.xyz;
  analysisValue=nativeSurfaceValue;analysisValid=nativeSurfaceValid;
  #include <clipping_planes_vertex>
 }
`;
const fragmentShader=`
 #include <common>
 #include <clipping_planes_pars_fragment>
 uniform float surfaceMode;
 uniform float surfaceDensity;
 uniform float surfaceAngle;
 uniform float surfaceRange;
 uniform bool surfaceSigned;
 varying vec3 analysisNormal;
 varying vec3 analysisView;
 varying float analysisValue;
 varying float analysisValid;
 void main(){
  #include <clipping_planes_fragment>
  vec3 color=vec3(0.25);
  if(analysisValid>0.999){
   if(surfaceMode<1.5){
    vec3 reflected=reflect(-normalize(analysisView),normalize(analysisNormal));
    float phase=dot(reflected.xy,vec2(cos(surfaceAngle),sin(surfaceAngle)))*surfaceDensity*3.14159265359;
    float wave=sin(phase);float width=max(fwidth(wave),0.005);
    color=mix(vec3(0.018),vec3(0.94),smoothstep(-width,width,wave));
   }else{
    float value=surfaceSigned?0.5+0.5*analysisValue/surfaceRange:analysisValue/surfaceRange;
    value=clamp(value,0.0,1.0);
    color=value<0.5?mix(vec3(0.035,0.13,0.7),vec3(0.9),value*2.0):mix(vec3(0.9),vec3(0.8,0.035,0.018),(value-0.5)*2.0);
   }
  }
  gl_FragColor=vec4(color,1.0);
  #include <colorspace_fragment>
 }
`;

// Analysis owns a temporary shader; the saved material and its maps stay intact.
export class SurfaceRenderer{
 constructor(){this.records=new Map();}
 base(mesh){return this.records.get(mesh)?.base||mesh.material;}
 restore(mesh){const record=this.records.get(mesh);if(record)mesh.material=record.base;}
 apply(mesh,settings={},planes=[],orthographic=false){
  if(!['zebra','curvature'].includes(settings.mode))return;
  let record=this.records.get(mesh);
  if(!record){
   const attributes=surfaceAttributes(mesh.userData.nativeMesh,settings.metric);
   if(!attributes.available)return;
   mesh.geometry.setAttribute('nativeSurfaceNormal',new THREE.BufferAttribute(attributes.normals,3));
   mesh.geometry.setAttribute('nativeSurfaceValid',new THREE.BufferAttribute(attributes.valid,1));
   mesh.geometry.setAttribute('nativeSurfaceValue',new THREE.BufferAttribute(attributes.values,1));
   const material=new THREE.ShaderMaterial({vertexShader,fragmentShader,clipping:true,side:THREE.DoubleSide,toneMapped:false,
    uniforms:{surfaceMode:{value:1},surfaceDensity:{value:12},surfaceAngle:{value:0},surfaceRange:{value:.25},surfaceSigned:{value:false},surfaceOrthographic:{value:orthographic}}});
   record={base:mesh.material,material,metric:settings.metric};this.records.set(mesh,record);
  }
  if(record.metric!==settings.metric){
   const values=mesh.geometry.getAttribute('nativeSurfaceValue');values.array.set(surfaceAttributes(mesh.userData.nativeMesh,settings.metric).values);values.needsUpdate=true;record.metric=settings.metric;
  }
  const material=record.material,u=material.uniforms;
  u.surfaceMode.value=settings.mode==='zebra'?1:2;u.surfaceDensity.value=settings.density??12;u.surfaceAngle.value=(settings.angle||0)*Math.PI/180;
  u.surfaceRange.value=settings.range||.25;u.surfaceSigned.value=settings.metric!=='max_abs';u.surfaceOrthographic.value=orthographic;
  material.clippingPlanes=planes;mesh.material=material;
 }
 dispose(){for(const record of this.records.values())record.material.dispose();this.records.clear();}
}
