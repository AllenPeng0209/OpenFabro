"use strict";
// A small 3D viewer for the enclosure preview: flat-shaded triangles drawn back to front on a canvas.
// Drag to orbit, wheel to zoom. No libraries, so it works offline and on any machine on the LAN.

class MeshView {
  constructor(host, data, options = {}) {
    this.host = host;
    this.is3D = true;
    this.data = data;
    this.options = options; this.pan = [0, 0, 0]; this.cameraMath = options.cameraMath || MeshView.cameraMath;
    this.yaw = -0.7; this.pitch = 0.75; this.roll = 0; this.zoom = 1; this.explode = 0.6;
    this.show = { base: true, lid: true, board: true, parts: true, top: true, bottom: true };
    this.canvas = document.createElement("canvas");
    this.canvas.className = "mesh-canvas";
    host.append(this.canvas);
    this.ctx = this.canvas.getContext("2d");
    const [sx, sy, sz] = data.size;
    this.center = [sx / 2, sy / 2, sz / 2];
    this.radius = Math.hypot(sx, sy, sz) / 2;
    this.meshes = data.meshes.map(m => this._prep(m));
    this._bind();
    this.ro = new ResizeObserver(() => this._resize());
    this.ro.observe(host);
    this._resize();
    this._onTheme = () => this.draw();
    window.addEventListener("wb-theme", this._onTheme);
    this._onZoom = () => this._resize();
    window.addEventListener("wb-zoom", this._onZoom);
  }

  destroy() {
    this.ro.disconnect();
    window.removeEventListener("wb-theme", this._onTheme);
    window.removeEventListener("wb-zoom", this._onZoom);
    this.canvas.remove();
  }

  selectComponent(id){if(this.options.canInteract?.()===false)return;this.selectedComponent=id;this.canvas.dataset.selectedComponent=id;for(const mesh of this.meshes)mesh.assemblySelected=mesh.component_id===id;this.draw();}

  _prep(m) {
    const v = Float32Array.from(m.v), t = Uint32Array.from(m.t), n = t.length / 3;
    const normals = new Float32Array(n * 3);
    for (let i = 0; i < n; i++) {
      const a = t[3 * i] * 3, b = t[3 * i + 1] * 3, c = t[3 * i + 2] * 3;
      const ux = v[b] - v[a], uy = v[b + 1] - v[a + 1], uz = v[b + 2] - v[a + 2];
      const wx = v[c] - v[a], wy = v[c + 1] - v[a + 1], wz = v[c + 2] - v[a + 2];
      let nx = uy * wz - uz * wy, ny = uz * wx - ux * wz, nz = ux * wy - uy * wx;
      const l = Math.hypot(nx, ny, nz) || 1;
      normals[3 * i] = nx / l; normals[3 * i + 1] = ny / l; normals[3 * i + 2] = nz / l;
    }
    const hex = m.color.replace("#", "");
    const rgb = [0, 2, 4].map(k => parseInt(hex.slice(k, k + 2), 16));
    return { ...m, v, t, n, normals, rgb };
  }

  _resize() {
    // layout pixels; the backing store also covers the page zoom so it stays sharp
    this.dpr = (window.devicePixelRatio || 1) * wbZoom();
    this.w = this.host.clientWidth; this.h = this.host.clientHeight;
    this.canvas.width = Math.max(1, this.w * this.dpr);
    this.canvas.height = Math.max(1, this.h * this.dpr);
    this.canvas.style.width = this.w + "px"; this.canvas.style.height = this.h + "px";
    this.draw();
  }

  _bind() {
    let drag = null;
    this.canvas.addEventListener("pointerdown", e => { if (this.options.canInteract?.() === false || e.button !== 0 && e.button !== 1) return; drag = { x: e.clientX, y: e.clientY, initialX:e.clientX,initialY:e.clientY,pan: e.button === 1 || e.shiftKey || this.panTool }; this.interacting = true; this.canvas.setPointerCapture(e.pointerId); });
    this.canvas.addEventListener("pointermove", e => {
      if (!drag) {if(this.nativeSelection)this._hoverNative(e);return;}
      if (this.options.canInteract?.() === false) { drag = null; this.interacting = false; return; }
      if (drag.pan) { const scale = Math.min(this.w, this.h) / (2.4 * this.radius) * this.zoom; this.pan[0] += (e.clientX - drag.x) / scale; this.pan[1] += (e.clientY - drag.y) / scale; }
      else if (this.cameraMath) Object.assign(this, this.cameraMath.orbitOrientation(this, (e.clientX-drag.x)*.008, (e.clientY-drag.y)*.008));
      else { this.yaw += (e.clientX - drag.x) * 0.01; this.pitch = Math.max(-1.55, Math.min(1.55, this.pitch + (e.clientY - drag.y) * 0.01)); }
      drag.x = e.clientX; drag.y = e.clientY;
      this.draw();
    });
    const cancel = () => { drag = null; this.interacting = false; this.options.onCameraChange?.(this); };
    this.canvas.addEventListener("pointerup", event=>{if(drag&&this.nativeSelection&&Math.hypot(event.clientX-drag.initialX,event.clientY-drag.initialY)<4)this._pickNative(event);cancel();});
    this.canvas.addEventListener("pointercancel", cancel);
    this.canvas.addEventListener("lostpointercapture", cancel);
    this.canvas.addEventListener("wheel", e => {
      e.preventDefault();
      if (this.options.canInteract?.() === false) return;
      this.setZoom(this.zoom * Math.exp(-e.deltaY * 0.0015));
    }, { passive: false });
  }

  meshVisible(mesh) { return this.show[mesh.group] !== false && (mesh.group !== 'parts' || !mesh.side || this.show[mesh.side] !== false)&&(!this.nativeSelection?.memberId||mesh.component_id===this.nativeSelection.memberId); }
  setNativeSelection(options){this.nativeSelection=options;this.nativeHighlight=null;this.canvas.style.cursor=options?'crosshair':'';this.draw();}
  _nativeProject(vertices,group='mechanical'){
    const basis=this.cameraBasis(),cy=Math.cos(this.yaw),sy=Math.sin(this.yaw),cp=Math.cos(this.pitch),sp=Math.sin(this.pitch),scale=Math.min(this.w,this.h)/(2.4*this.radius)*this.zoom,result=[];
    for(let i=0;i<vertices.length;i+=3){const x=vertices[i]-this.center[0],y=vertices[i+1]-this.center[1],z=vertices[i+2]+(group==='lid'?this.explode*this.data.size[2]:0)-this.center[2],a=x*cy-y*sy,b=x*sy+y*cy;result.push(this.w/2+((basis?x*basis.right[0]+y*basis.right[1]+z*basis.right[2]:a)+this.pan[0])*scale,this.h/2-((basis?x*basis.up[0]+y*basis.up[1]+z*basis.up[2]:b*sp+z*cp)-this.pan[1])*scale,basis?x*basis.direction[0]+y*basis.direction[1]+z*basis.direction[2]:-b*cp+z*sp);}
    return result;
  }
  _nativeHit(event){
    const api=MeshView.nativeTopology;if(!api)return null;const box=this.canvas.getBoundingClientRect(),point=[event.clientX-box.left,event.clientY-box.top];let face=null;
    for(const mesh of this.meshes){if(!this.meshVisible(mesh))continue;const p=this._nativeProject(mesh.v,mesh.group);for(let i=0;i<mesh.t.length;i+=3){const[a,b,c]=[...mesh.t.slice(i,i+3)].map(index=>p.slice(index*3,index*3+3)),den=(b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1]);if(Math.abs(den)<1e-10)continue;const u=((b[1]-c[1])*(point[0]-c[0])+(c[0]-b[0])*(point[1]-c[1]))/den,v=((c[1]-a[1])*(point[0]-c[0])+(a[0]-c[0])*(point[1]-c[1]))/den;if(u<0||v<0||u+v>1)continue;const depth=u*a[2]+v*b[2]+(1-u-v)*c[2];if(!face||depth>face.depth)face={depth,pick:api.nativeFace(this.data,mesh,i/3)};}}
    if(this.nativeSelection.mode==='face')return face?.pick||null;let closest=null;const tolerance=7/(Math.min(this.w,this.h)/(2.4*this.radius)*this.zoom);
    for(const body of this.data.topology?.bodies||[]){const mesh=this.meshes.find(m=>m.body_id===body.body_id&&this.meshVisible(m));if(!mesh)continue;for(const edge of body.edges){const hit=api.nearestSegment(point,this._nativeProject(edge.v,mesh.group),7);if(!hit||face&&hit.depth<face.depth-tolerance)continue;if(!closest||hit.distance<closest.distance||hit.distance===closest.distance&&hit.depth>closest.depth)closest={...hit,pick:api.nativeEdge(this.data,body.body_id,edge.index)};}}
    return closest?.pick||null;
  }
  _hoverNative(event){if(this.options.canInteract?.()===false)return;this.nativeHighlight=this._nativeHit(event);this.draw();this.nativeSelection?.onHover?.(this.nativeHighlight);}
  _pickNative(event){if(this.options.canInteract?.()===false)return;this.nativeHighlight=this._nativeHit(event);this.draw();this.nativeSelection?.onPick?.(this.nativeHighlight);}
  cameraBasis() { return this.cameraMath?.cameraBasis(this); }
  setOrientation(pose) { if (!this.cameraMath || this.options.canInteract?.() === false) return false; const next = { yaw: pose.yaw ?? this.yaw, pitch: pose.pitch ?? this.pitch, roll: pose.roll ?? this.roll }; this.cameraMath.cameraBasis(next); this.yaw = this.cameraMath.wrapAngle(next.yaw); this.pitch = Math.max(-Math.PI/2, Math.min(Math.PI/2, next.pitch)); this.roll = this.cameraMath.wrapAngle(next.roll); this.draw(); return true; }
  setViewDirection(direction) { return this.cameraMath ? this.setOrientation(this.cameraMath.viewOrientation(direction)) : false; }
  setZoom(value) { this.zoom = Math.max(0.3, Math.min(6, value)); this.draw(); this.options.onZoom?.(this.zoom); }
  fit() { this.pan.fill(0); this.setZoom(1); }

  draw() {
    const c = this.ctx;
    if (!c || !this.w) return;
    // Rasterise with a depth buffer (painter's sorting fails on long, thin wall faces).
    const ss = this.dpr < 2 ? 2 : 1;                       // supersample on low-density screens
    const W = Math.round(this.w * this.dpr * ss), H = Math.round(this.h * this.dpr * ss);
    if (!this.off || this.off.width !== W || this.off.height !== H) {
      this.off = document.createElement("canvas"); this.off.width = W; this.off.height = H;
      this.offCtx = this.off.getContext("2d");
      this.img = this.offCtx.createImageData(W, H);
      this.px = new Uint32Array(this.img.data.buffer);
      this.zb = new Float32Array(W * H);
    }
    const px = this.px, zb = this.zb;
    const bg = parseColour(getComputedStyle(document.documentElement).getPropertyValue("--panel-2")) || [34, 34, 34];
    px.fill((255 << 24) | (bg[2] << 16) | (bg[1] << 8) | bg[0]);
    zb.fill(-Infinity);
    const cy = Math.cos(this.yaw), sy = Math.sin(this.yaw), cp = Math.cos(this.pitch), sp = Math.sin(this.pitch), basis = this.cameraBasis();
    const scale = Math.min(W, H) / (2.4 * this.radius) * this.zoom;
    const lift = this.explode * this.data.size[2];
    const [ox, oy, oz] = this.center;
    const L = [-0.35, 0.45, 0.82];
    for (const m of this.meshes) {
      if (!this.meshVisible(m)) continue;
      const dz = m.group === "lid" ? lift : 0;
      const v = m.v, nv = v.length / 3, P = new Float32Array(nv * 3);
      // World Z is up. Turn about Z (yaw), then tilt about the screen's X axis (pitch).
      for (let i = 0; i < nv; i++) {
        const x = v[3 * i] - ox, y = v[3 * i + 1] - oy, z = v[3 * i + 2] + dz - oz;
        const x1 = x * cy - y * sy, y1 = x * sy + y * cy;
        const sx = basis ? x*basis.right[0]+y*basis.right[1]+z*basis.right[2] : x1;
        const uy = basis ? x*basis.up[0]+y*basis.up[1]+z*basis.up[2] : y1*sp+z*cp;
        P[3 * i] = W / 2 + (sx + this.pan[0]) * scale;
        P[3 * i + 1] = H / 2 - (uy - this.pan[1]) * scale;
        P[3 * i + 2] = basis ? x*basis.direction[0]+y*basis.direction[1]+z*basis.direction[2] : -y1*cp+z*sp;
      }
      const pickedRange=this.nativeHighlight?.entity==='face'&&this.nativeHighlight.body_id===m.body_id?m.face_ranges?.find(([index])=>index===this.nativeHighlight.index):null;
      for (let i = 0; i < m.n; i++) {
        const nx = m.normals[3 * i], ny = m.normals[3 * i + 1], nz = m.normals[3 * i + 2];
        const nx1 = basis ? nx*basis.right[0]+ny*basis.right[1]+nz*basis.right[2] : nx*cy-ny*sy, ny1 = nx*sy+ny*cy;
        const nsy = basis ? nx*basis.up[0]+ny*basis.up[1]+nz*basis.up[2] : ny1*sp+nz*cp, nd = basis ? nx*basis.direction[0]+ny*basis.direction[1]+nz*basis.direction[2] : -ny1*cp+nz*sp;
        if (nd < -1e-3) continue;                           // facing away
        const lit = 0.35 + 0.65 * Math.max(0, nx1 * L[0] + nsy * L[1] + nd * L[2]);
        const nativeSelected=pickedRange&&i>=pickedRange[1]&&i<pickedRange[1]+pickedRange[2],rgb=nativeSelected?m.rgb.map((v,j)=>v*.45+[30,250,190][j]*.55):m.assemblySelected?m.rgb.map((value,index)=>value*.6+[40,180,140][index]*.4):m.rgb;
        const col = (255 << 24) | ((rgb[2] * lit | 0) << 16) | ((rgb[1] * lit | 0) << 8) | (rgb[0] * lit | 0);
        const a = m.t[3 * i] * 3, b = m.t[3 * i + 1] * 3, cc = m.t[3 * i + 2] * 3;
        tri(P[a], P[a + 1], P[a + 2], P[b], P[b + 1], P[b + 2], P[cc], P[cc + 1], P[cc + 2], col, px, zb, W, H);
      }
    }
    this.offCtx.putImageData(this.img, 0, 0);
    c.setTransform(1, 0, 0, 1, 0, 0);
    c.imageSmoothingEnabled = true; c.imageSmoothingQuality = "high";
    c.drawImage(this.off, 0, 0, this.canvas.width, this.canvas.height);
    if(this.nativeSelection?.mode==='edge'){
      c.save();c.setTransform(this.dpr,0,0,this.dpr,0,0);c.lineWidth=1.2;
      for(const body of this.data.topology?.bodies||[]){const mesh=this.meshes.find(m=>m.body_id===body.body_id&&this.meshVisible(m));if(!mesh)continue;for(const edge of body.edges){const p=this._nativeProject(edge.v,mesh.group);c.strokeStyle=this.nativeHighlight?.body_id===body.body_id&&this.nativeHighlight?.index===edge.index?'#1dfdc0':'#6eac98';c.beginPath();for(let i=0;i+5<p.length;i+=6){const x=(p[i]+p[i+3])/2,y=(p[i+1]+p[i+4])/2,z=(p[i+2]+p[i+5])/2,ix=Math.round(x*W/this.w),iy=Math.round(y*H/this.h);if(ix<0||iy<0||ix>=W||iy>=H||z+1e-3<zb[iy*W+ix])continue;c.moveTo(p[i],p[i+1]);c.lineTo(p[i+3],p[i+4]);}c.stroke();}}
      c.restore();
    }
    this.options.onCameraChange?.(this);
  }
}

function tri(x0, y0, z0, x1, y1, z1, x2, y2, z2, col, px, zb, W, H) {
  const area = (x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0);
  if (Math.abs(area) < 1e-9) return;
  const minX = Math.max(0, Math.floor(Math.min(x0, x1, x2))), maxX = Math.min(W - 1, Math.ceil(Math.max(x0, x1, x2)));
  const minY = Math.max(0, Math.floor(Math.min(y0, y1, y2))), maxY = Math.min(H - 1, Math.ceil(Math.max(y0, y1, y2)));
  const inv = 1 / area;
  for (let y = minY; y <= maxY; y++) {
    const py = y + 0.5;
    for (let x = minX; x <= maxX; x++) {
      const pxc = x + 0.5;
      const w0 = ((x1 - pxc) * (y2 - py) - (x2 - pxc) * (y1 - py)) * inv;
      if (w0 < -1e-6) continue;
      const w1 = ((x2 - pxc) * (y0 - py) - (x0 - pxc) * (y2 - py)) * inv;
      if (w1 < -1e-6) continue;
      const w2 = 1 - w0 - w1;
      if (w2 < -1e-6) continue;
      const z = w0 * z0 + w1 * z1 + w2 * z2, k = y * W + x;
      if (z > zb[k]) { zb[k] = z; px[k] = col; }
    }
  }
}

function parseColour(s) {
  s = (s || "").trim();
  let m = s.match(/^#([0-9a-f]{3})$/i);
  if (m) return [...m[1]].map(h => parseInt(h + h, 16));
  m = s.match(/^#([0-9a-f]{6})/i);
  if (m) return [0, 2, 4].map(k => parseInt(m[1].slice(k, k + 2), 16));
  m = s.match(/rgba?\(([^)]+)\)/);
  if (m) return m[1].split(",").slice(0, 3).map(x => parseInt(x));
  return null;
}
window.MeshView = MeshView;
