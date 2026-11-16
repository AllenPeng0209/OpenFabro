import * as THREE from './vendor/three.module.js';
import {cameraBasis,viewOrientation,orbitOrientation,wrapAngle} from './workbench-camera.mjs';
import {nativeFace,nativeEdge} from './workbench-cad-topology.mjs';
import {MaterialRenderer} from './workbench-material-renderer.mjs';
import {curvatureComb,curvatureEvents} from './workbench-curve-analysis.mjs';
import {SurfaceRenderer} from './workbench-surface-analysis.mjs';

// Render the same millimetre-based meshes emitted by FreeCAD. Geometry stays in
// model coordinates; orbit, explosion, clipping, and measurements are view state.
export class CADView {
  constructor(host,data,options={}) {
    this.host=host;this.data=data;this.options=options;this.is3D=true;this.yaw=-.7;this.pitch=.75;this.roll=0;this.zoom=1;this.explode=.6;
    this.show={base:true,lid:true,board:true,parts:true,top:true,bottom:true};this.projection='orthographic';this.style='solid';this.sectionAxis='none';this.sectionDepth=0;this.measureMode=false;this.measurePoints=[];this.showGrid=true;
    this.pan=new THREE.Vector3();
    this.center=new THREE.Vector3(...data.size).multiplyScalar(.5);this.radius=Math.hypot(...data.size)/2;
    this.scene=new THREE.Scene();this.scene.background=new THREE.Color('#101010');
    this.root=new THREE.Group();this.root.position.copy(this.center).negate();this.scene.add(this.root);
    this.renderer=new THREE.WebGLRenderer({antialias:true,alpha:false,powerPreference:'high-performance'});
    this.renderer.setPixelRatio(Math.min(devicePixelRatio||1,2));this.renderer.outputColorSpace=THREE.SRGBColorSpace;this.renderer.localClippingEnabled=true;
    this.renderer.toneMapping=THREE.ACESFilmicToneMapping;this.renderer.toneMappingExposure=1.3;
    this.materialRenderer=new MaterialRenderer(this.renderer);
    this.surfaceRenderer=new SurfaceRenderer();
    this.canvas=this.renderer.domElement;this.canvas.className='mesh-canvas cad-canvas';this.canvas.tabIndex=0;this.canvas.setAttribute('aria-label','Interactive 3D CAD model');host.append(this.canvas);
    this.scene.add(new THREE.HemisphereLight('#e5f1ff','#3b4741',2));
    const key=new THREE.DirectionalLight('#fff8ed',3.5);key.position.set(40,-60,100);this.scene.add(key);
    const fill=new THREE.DirectionalLight('#b8d5eb',1.1);fill.position.set(-70,30,30);this.scene.add(fill);
    const gridSize=Math.max(...data.size)*2,divisions=20;
    this.grid=new THREE.GridHelper(gridSize,divisions,'#77707f','#414047');this.grid.rotation.x=Math.PI/2;this.grid.position.z=-this.center.z-.02;this.scene.add(this.grid);
    this.meshes=[];this.textureCache=new Map();this.pendingTextures=0;this.textureFailed=false;this.destroyed=false;
    for(const m of data.meshes){
      const geometry=new THREE.BufferGeometry();geometry.setAttribute('position',new THREE.BufferAttribute(Float32Array.from(m.v),3));geometry.setIndex(new THREE.BufferAttribute(Uint32Array.from(m.t),1));geometry.computeVertexNormals();geometry.computeBoundingBox();
      if(m.uv)geometry.setAttribute('uv',new THREE.BufferAttribute(Float32Array.from(m.uv),2));
      if(m.c)geometry.setAttribute('color',new THREE.BufferAttribute(Float32Array.from(m.c),3));
      const material=new THREE.MeshPhysicalMaterial({color:m.color,roughness:m.roughness??.72,metalness:m.metalness??.08,flatShading:true,side:THREE.DoubleSide,vertexColors:!!m.c,opacity:m.opacity??1,transparent:m.transparent??((m.opacity??1)<1),alphaTest:m.alpha_test??0});
      if(m.texture)material.map=this._texture(m.texture);
      const mesh=new THREE.Mesh(geometry,material);mesh.name=m.name;mesh.userData={nativeMesh:m,group:m.group,componentId:m.component_id,color:m.color,side:m.side,opacity:m.opacity??1,transparent:m.transparent??((m.opacity??1)<1),alphaTest:m.alpha_test??0,roughness:m.roughness,metalness:m.metalness};this.materialRenderer.prepare(mesh,m,data.origin||[0,0,0]);this.root.add(mesh);this.meshes.push(mesh);
    }
    this.lines=[];
    for(const line of data.lines||[]){const geometry=new THREE.BufferGeometry();geometry.setAttribute('position',new THREE.BufferAttribute(Float32Array.from(line.v),3));const material=new THREE.LineBasicMaterial({color:line.color||'#9e9e9e'});const object=new THREE.LineSegments(geometry,material);object.name=line.name;object.userData={group:line.group||'mechanical',bodyId:line.body_id,color:line.color||'#9e9e9e'};this.root.add(object);this.lines.push(object);}
    this.raycaster=new THREE.Raycaster();this._camera();this._bind();
    this.observer=new ResizeObserver(()=>this._resize());this.observer.observe(host);this._resize();
  }
  _texture(uri){
    if(this.textureCache.has(uri))return this.textureCache.get(uri);
    if(!/^data:image\/(png|jpeg|webp);base64,[A-Za-z0-9+/=]+$/.test(uri))throw Error('Use an embedded image for a model texture.');
    this.pendingTextures++;this.options.onTexturesChanged?.('loading');
    const texture=new THREE.TextureLoader().load(uri,()=>{this.pendingTextures--;if(!this.destroyed){this.options.onTexturesChanged?.(this.textureFailed?'failed':this.pendingTextures?'loading':'ready');this.draw();}},undefined,()=>{this.pendingTextures--;this.textureFailed=true;if(!this.destroyed)this.options.onTexturesChanged?.('failed');});
    texture.colorSpace=THREE.SRGBColorSpace;this.textureCache.set(uri,texture);return texture;
  }
  _camera(){
    this.camera=this.projection==='perspective'?new THREE.PerspectiveCamera(40,1,.1,100000):new THREE.OrthographicCamera(-1,1,1,-1,.1,100000);
    this.camera.up.set(0,0,1);
  }
  _resize(){this.w=this.host.clientWidth;this.h=this.host.clientHeight;if(!this.w||!this.h)return;this.renderer.setSize(this.w,this.h,false);this.canvas.style.width=this.w+'px';this.canvas.style.height=this.h+'px';this.draw();}
  _bind(){
    let drag=null;
    this.canvas.addEventListener('pointerdown',e=>{if(this.options.canInteract?.()===false||e.button!==0&&e.button!==1)return;drag={x:e.clientX,y:e.clientY,initialX:e.clientX,initialY:e.clientY,pan:e.button===1||e.shiftKey||this.panTool};this.interacting=true;this.canvas.setPointerCapture(e.pointerId);});
    this.canvas.addEventListener('pointermove',e=>{
      if(!drag){if(this.nativeSelection)this._hoverNative(e);return;}
      if(this.options.canInteract?.()===false){drag=null;this.interacting=false;return;}
      if(drag.pan){const target=this.pan.clone().add(new THREE.Vector3(0,0,this.explode*this.data.size[2]*.1)),scale=this.camera.isOrthographicCamera?(this.camera.top-this.camera.bottom)/this.h:2*this.camera.position.distanceTo(target)*Math.tan(this.camera.fov*Math.PI/360)/this.h;this.pan.add(new THREE.Vector3(1,0,0).applyQuaternion(this.camera.quaternion).multiplyScalar(-(e.clientX-drag.x)*scale));this.pan.add(new THREE.Vector3(0,1,0).applyQuaternion(this.camera.quaternion).multiplyScalar((e.clientY-drag.y)*scale));}
      else Object.assign(this,orbitOrientation(this,(e.clientX-drag.x)*.008,(e.clientY-drag.y)*.008));
      drag.x=e.clientX;drag.y=e.clientY;this.draw();
    });
    this.canvas.addEventListener('pointerup',e=>{if(drag&&Math.hypot(e.clientX-drag.initialX,e.clientY-drag.initialY)<4)this._pick(e);drag=null;this.interacting=false;this.options.onCameraChange?.(this);});
    const cancel=()=>{drag=null;this.interacting=false;this.options.onCameraChange?.(this);};this.canvas.addEventListener('pointercancel',cancel);this.canvas.addEventListener('lostpointercapture',cancel);
    this.canvas.addEventListener('wheel',e=>{e.preventDefault();if(this.options.canInteract?.()===false)return;this.setZoom(this.zoom*Math.exp(-e.deltaY*.0015));},{passive:false});
    this.canvas.addEventListener('contextmenu',e=>e.preventDefault());
  }
  _pick(e){
    if(this.options.canInteract?.()===false)return;
    const r=this.canvas.getBoundingClientRect(),point=new THREE.Vector2((e.clientX-r.left)/r.width*2-1,-(e.clientY-r.top)/r.height*2+1);
    this.raycaster.setFromCamera(point,this.camera);
    if(this.nativeSelection){const hit=this._nativeHit();this._nativeHighlight(hit);this.nativeSelection.onPick?.(hit?.pick||null);return;}
    const hit=this.raycaster.intersectObjects(this.meshes.filter(m=>m.visible),false).find(h=>(h.object.material.clippingPlanes||[]).every(plane=>plane.distanceToPoint(h.point)>=-1e-5));if(!hit)return;
    if(this.measureMode){
      const original=hit.point.clone().add(this.center);if(hit.object.userData.group==='lid')original.z-=this.explode*this.data.size[2];
      if(this.measurePoints.length===2)this.measurePoints=[];this.measurePoints.push(original);
      if(this.measurePoints.length===2){const distance=this.measurePoints[0].distanceTo(this.measurePoints[1]);this.options.onMeasure?.(distance,this.measurePoints.map(p=>p.toArray()));}
      else this.options.onMeasure?.(null,[original.toArray()]);
      this._measurement();this.draw();return;
    }
    if(hit.object.userData.componentId){this.selectComponent(hit.object.userData.componentId);this.options.onComponentPick?.(hit.object.userData.componentId);}else this.select(hit.object.name);this.options.onPick?.(hit.object.name,hit.object.geometry.boundingBox.getSize(new THREE.Vector3()).toArray());
  }
  _measurement(){
    if(this.measurement){this.scene.remove(this.measurement);this.measurement.geometry.dispose();this.measurement.material.dispose();this.measurement=null;}
    if(this.measurePoints.length!==2)return;
    const positions=this.measurePoints.map(p=>p.clone().sub(this.center));
    const geometry=new THREE.BufferGeometry().setFromPoints(positions);
    this.measurement=new THREE.Line(geometry,new THREE.LineBasicMaterial({color:'#1dfdc0',depthTest:false}));this.measurement.renderOrder=100;this.scene.add(this.measurement);
  }
  select(name){this.selected=name;for(const m of this.meshes)this.surfaceRenderer.base(m).emissive.set(m.name===name?'#214a3c':'#000000');this.draw();}
  selectComponent(id){if(this.options.canInteract?.()===false)return;this.selectedComponent=id;this.canvas.dataset.selectedComponent=id;for(const mesh of this.meshes)this.surfaceRenderer.base(mesh).emissive.set(mesh.userData.componentId===id?'#214a3c':'#000000');this.draw();}
  setNativeSelection(options){this.nativeSelection=options;this._clearNativeHighlight();if(options?.mode==='edge'&&!this.nativeEdges)this._nativeEdgeObjects();this.canvas.style.cursor=options?'crosshair':'';this.draw();}
  _nativeEdgeObjects(){
    this.nativeEdges=[];
    for(const body of this.data.topology?.bodies||[]){const positions=[],ranges=[];for(const edge of body.edges){const start=positions.length/3;for(const value of edge.v)positions.push(value);ranges.push([edge.index,start,edge.v.length/3]);}if(!positions.length)continue;const geometry=new THREE.BufferGeometry();geometry.setAttribute('position',new THREE.BufferAttribute(Float32Array.from(positions),3));const line=new THREE.LineSegments(geometry,new THREE.LineBasicMaterial({color:'#6eac98'}));line.userData={bodyId:body.body_id,memberId:body.member_id,ranges};this.root.add(line);this.nativeEdges.push(line);}
  }
  _updateCurvature(planes){
    const settings=this.curvature||{},key=`${settings.gain}:${settings.density}:${settings.inflections}:${settings.jumps}`;
    if(settings.enabled&&key!==this._combKey){
      for(const object of this.combObjects||[]){this.root.remove(object);object.geometry.dispose();object.material.dispose();}
      for(const object of this.combMarkers||[]){this.root.remove(object);object.geometry.dispose();object.material.dispose();}
      this.combObjects=[];this.combStats=curvatureComb(this.data,settings);this._combKey=key;
      this.combMarkers=[];this.curveEvents=curvatureEvents(this.data,settings);
      for(const body of this.combStats.bodies){
        const geometry=new THREE.BufferGeometry();geometry.setAttribute('position',new THREE.BufferAttribute(Float32Array.from(body.positions),3));
        const object=new THREE.LineSegments(geometry,new THREE.LineBasicMaterial({color:'#eec46a',toneMapped:false}));
        object.userData={bodyId:body.bodyId,memberId:body.memberId};this.root.add(object);this.combObjects.push(object);
      }
      const groups=new Map();for(const marker of this.curveEvents.markers){if(!groups.has(marker.bodyId))groups.set(marker.bodyId,[]);groups.get(marker.bodyId).push(marker);}
      for(const [bodyId,markers]of groups){
        const positions=[],colors=[];for(const marker of markers){positions.push(...marker.point);const color=new THREE.Color(marker.kind==='inflection'?'#4fd1b1':'#ff6db0');colors.push(color.r,color.g,color.b);}
        const geometry=new THREE.BufferGeometry();geometry.setAttribute('position',new THREE.BufferAttribute(Float32Array.from(positions),3));geometry.setAttribute('color',new THREE.BufferAttribute(Float32Array.from(colors),3));
        const object=new THREE.Points(geometry,new THREE.PointsMaterial({size:8,sizeAttenuation:false,vertexColors:true,toneMapped:false}));object.userData={bodyId,memberId:markers[0].memberId};this.root.add(object);this.combMarkers.push(object);
      }
    }
    for(const object of [...(this.combObjects||[]),...(this.combMarkers||[])]){
      const mesh=this.meshes.find(mesh=>mesh.visible&&mesh.userData.nativeMesh.body_id===object.userData.bodyId),line=this.lines.find(line=>line.visible&&line.userData.bodyId===object.userData.bodyId);
      object.visible=!!settings.enabled&&!!(mesh||line)&&(!this.nativeSelection?.memberId||object.userData.memberId===this.nativeSelection.memberId);
      object.position.z=mesh?.position.z||0;object.material.clippingPlanes=planes;object.material.depthTest=this.style!=='xray';
    }
  }
  _nativeHit(){
    const visible=hit=>(hit.object.material.clippingPlanes||[]).every(plane=>plane.distanceToPoint(hit.point)>=-1e-5),surface=this.raycaster.intersectObjects(this.meshes.filter(mesh=>mesh.visible),false).find(visible);
    if(this.nativeSelection.mode==='face'){if(!surface)return null;const pick=nativeFace(this.data,surface.object.userData.nativeMesh,surface.faceIndex);return pick?{pick,object:surface.object}:null;}
    const worldPixel=this.camera.isOrthographicCamera?(this.camera.top-this.camera.bottom)/this.h:2*this.camera.position.distanceTo(this.pan)*Math.tan(this.camera.fov*Math.PI/360)/this.h;this.raycaster.params.Line.threshold=worldPixel*7;
    for(const hit of this.raycaster.intersectObjects((this.nativeEdges||[]).filter(line=>line.visible),false)){
      if(!visible(hit)||this.style!=='xray'&&surface&&hit.distance>surface.distance+worldPixel*7)continue;const range=hit.object.userData.ranges.find(([,start,count])=>hit.index>=start&&hit.index<start+count);if(!range)continue;const pick=nativeEdge(this.data,hit.object.userData.bodyId,range[0]);if(pick)return{pick,object:hit.object};
    }
    return null;
  }
  _hoverNative(event){if(this.options.canInteract?.()===false)return;const box=this.canvas.getBoundingClientRect();this.raycaster.setFromCamera(new THREE.Vector2((event.clientX-box.left)/box.width*2-1,-(event.clientY-box.top)/box.height*2+1),this.camera);const hit=this._nativeHit();this._nativeHighlight(hit);this.nativeSelection?.onHover?.(hit?.pick||null);}
  _clearNativeHighlight(){if(this.nativeOverlay){this.root.remove(this.nativeOverlay);this.nativeOverlay.geometry.dispose();this.nativeOverlay.material.dispose();this.nativeOverlay=null;}this.nativeHighlightKey=null;}
  _nativeHighlight(hit){
    const key=hit?hit.pick.body_id+':'+hit.pick.entity+':'+hit.pick.index:null;if(key===this.nativeHighlightKey)return;this._clearNativeHighlight();if(!hit){this.draw();return;}this.nativeHighlightKey=key;const positions=[];let object;
    if(hit.pick.entity==='face'){const mesh=hit.object.userData.nativeMesh,range=mesh.face_ranges.find(([index])=>index===hit.pick.index);for(const vertex of mesh.t.slice(range[1]*3,(range[1]+range[2])*3))positions.push(...mesh.v.slice(vertex*3,vertex*3+3));const geometry=new THREE.BufferGeometry();geometry.setAttribute('position',new THREE.BufferAttribute(Float32Array.from(positions),3));object=new THREE.Mesh(geometry,new THREE.MeshBasicMaterial({color:'#1dfdc0',transparent:true,opacity:.38,side:THREE.DoubleSide,polygonOffset:true,polygonOffsetFactor:-1,polygonOffsetUnits:-1}));}
    else{const geometry=new THREE.BufferGeometry();geometry.setAttribute('position',new THREE.BufferAttribute(Float32Array.from(hit.pick.v),3));object=new THREE.LineSegments(geometry,new THREE.LineBasicMaterial({color:'#1dfdc0'}));}
    object.position.copy(hit.object.position);this.nativeOverlay=object;this.root.add(object);this.draw();
  }
  cameraBasis(){return cameraBasis(this);}
  setOrientation(pose){if(this.options.canInteract?.()===false)return false;const next={yaw:pose.yaw??this.yaw,pitch:pose.pitch??this.pitch,roll:pose.roll??this.roll};cameraBasis(next);this.yaw=wrapAngle(next.yaw);this.pitch=Math.max(-Math.PI/2,Math.min(Math.PI/2,next.pitch));this.roll=wrapAngle(next.roll);this.draw();return true;}
  setViewDirection(direction){return this.setOrientation(viewOrientation(direction));}
  setZoom(value){this.zoom=Math.max(.25,Math.min(6,value));this.draw();this.options.onZoom?.(this.zoom);}
  fit(){this.zoom=1;this.pan.set(0,0,0);this.draw();this.options.onZoom?.(1);}
  draw(){
    if(!this.w||!this.h)return;
    if((this.projection==='perspective')!==this.camera.isPerspectiveCamera)this._camera();
    const aspect=this.w/this.h,span=this.radius*1.3/Math.min(1,aspect)/this.zoom;
    if(this.camera.isOrthographicCamera){this.camera.left=-span*aspect;this.camera.right=span*aspect;this.camera.top=span;this.camera.bottom=-span;}
    else this.camera.aspect=aspect;
    const distance=this.radius*3.6/(this.camera.isPerspectiveCamera?this.zoom:1);
    const basis=this.cameraBasis(),target=this.pan.clone().add(new THREE.Vector3(0,0,this.explode*this.data.size[2]*.1));
    this.camera.up.fromArray(basis.up);this.camera.position.fromArray(basis.direction).multiplyScalar(distance).add(target);this.camera.lookAt(target);this.camera.updateProjectionMatrix();
    const clipped=this.sectionAxis!=='none',axis=['x','y','z'].indexOf(this.sectionAxis);
    const planes=clipped?[new THREE.Plane(new THREE.Vector3(axis===0?1:0,axis===1?1:0,axis===2?1:0),this.center.getComponent(axis)-this.sectionDepth)]:[];
    for(const m of this.meshes){
      this.surfaceRenderer.restore(m);
      m.visible=this.show[m.userData.group]!==false&&(m.userData.group!=='parts'||!m.userData.side||this.show[m.userData.side]!==false)&&(!this.nativeSelection?.memberId||m.userData.componentId===this.nativeSelection.memberId);m.position.z=m.userData.group==='lid'?this.explode*this.data.size[2]:0;
      m.material.clippingPlanes=planes;
      if(this._lastStyle!==this.style||this._lastClipped!==clipped){
        m.material.wireframe=this.style==='blueprint';m.material.transparent=this.style==='xray'||m.userData.transparent;m.material.opacity=this.style==='xray'?.24:m.userData.opacity;m.material.alphaTest=this.style==='xray'?0:m.userData.alphaTest;m.material.depthWrite=this.style!=='xray'&&!m.userData.transparent;
        m.material.color.set(this.style==='blueprint'?'#86c7dd':m.userData.color);m.material.roughness=m.userData.roughness??(this.style==='realistic'?.48:.72);m.material.metalness=m.userData.metalness??(this.style==='realistic'?.16:.08);m.material.needsUpdate=true;
        this.materialRenderer.apply(m,this.style);
      }
      this.surfaceRenderer.apply(m,this.surface,planes,this.camera.isOrthographicCamera);
    }
    for(const line of this.lines){line.visible=this.show[line.userData.group]!==false;line.material.clippingPlanes=planes;line.material.color.set(this.style==='blueprint'?'#86c7dd':line.userData.color);}
    for(const line of this.nativeEdges||[]){line.visible=this.nativeSelection?.mode==='edge'&&(!this.nativeSelection.memberId||line.userData.memberId===this.nativeSelection.memberId)&&this.meshes.some(mesh=>mesh.visible&&mesh.userData.nativeMesh.body_id===line.userData.bodyId);line.material.clippingPlanes=planes;line.material.depthTest=this.style!=='xray';}
    if(this.nativeOverlay)this.nativeOverlay.material.clippingPlanes=planes;
    this._updateCurvature(planes);
    this.grid.visible=this.showGrid!==false;this._lastStyle=this.style;this._lastClipped=clipped;this.scene.background.set(this.style==='blueprint'?'#0e1923':'#101010');this.renderer.render(this.scene,this.camera);this.options.onCameraChange?.(this);
  }
  destroy(){this.destroyed=true;this.observer.disconnect();this._clearNativeHighlight();for(const mesh of this.meshes)this.surfaceRenderer.restore(mesh);this.surfaceRenderer.dispose();for(const m of [...this.meshes,...this.lines,...(this.nativeEdges||[]),...(this.combObjects||[]),...(this.combMarkers||[])]){m.geometry.dispose();m.material.dispose();}for(const texture of this.textureCache.values())texture.dispose();this.textureCache.clear();this.materialRenderer.dispose();if(this.measurement){this.measurement.geometry.dispose();this.measurement.material.dispose();}this.grid.geometry.dispose();this.grid.material.dispose();this.renderer.dispose();this.renderer.forceContextLoss();this.canvas.remove();}
}
