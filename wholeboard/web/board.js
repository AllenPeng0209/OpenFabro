// Board viewer: draws OpenFabro geometry JSON on a canvas with pan, zoom and layer toggles.
"use strict";

const LAYER_COLORS = {
  "F.Cu": "#e5534b", "B.Cu": "#4d8df6", "In1.Cu": "#d6b33a", "In2.Cu": "#38c793",
  "In3.Cu": "#c45ad6", "In4.Cu": "#5ad6d0",
  "F.SilkS":"#e1e5df","B.SilkS":"#8ba2c0","F.Fab":"#809c8d","B.Fab":"#7c869c",
};

class BoardView {
  constructor(host, geo, opts = {}) {
    this.host = host;
    this.geo = geo;
    this.opts = opts;
    this.zoom = 1;
    this.showGrid=!!opts.grid;this.gridMm=opts.gridMm||.5;
    this.layers = new Set([...(geo.layers || []), "pads", "vias", "zones", "outline", "refs",
                           "F.SilkS","B.SilkS",
                           ...(opts.ratsnest ? ["ratsnest"] : []), ...(opts.courtyards ? ["courtyards"] : [])]);
    host.innerHTML = "";
    host.classList.add("boardview");
    this.canvas = document.createElement("canvas");
    this.canvas.tabIndex=0;
    this.tip = document.createElement("div");
    this.tip.className = "board-tip";
    this.bar = document.createElement("div");
    this.bar.className = "board-bar";
    this.handles=document.createElement('div');this.handles.className='copper-handles';
    this.routeTerminals=document.createElement('div');this.routeTerminals.className='route-terminals';
    host.append(this.canvas, this.tip, this.bar,this.handles,this.routeTerminals);
    this.routeTerminals.addEventListener('pointerdown',event=>{
      const button=event.target.closest('[data-route-terminal]');if(!button||this.opts.readOnly)return;
      event.preventDefault();event.stopPropagation();this.canvas.focus({preventScroll:true});
      if((event.ctrlKey||event.metaKey)&&button.routeTarget.kind==='pad'){
        const target=button.routeTarget,pad=this.geo.pads.find(p=>`${p.ref}.${p.name}`===target.pin&&(!target.padId||p.id===target.padId)&&this._shown('pads',p));
        if(pad?.id&&this.opts.onObjectSelect)this.opts.onObjectSelect({collection:'pads',id:pad.id,ref:pad.ref});else this.opts.onSelect?.(target.pin.split('.')[0]);
      }
      else this.opts.onRoutingTarget?.(button.routeTarget,event);
    });
    this._buildBar();
    this.ctx = this.canvas.getContext("2d");
    this._bindObjectPicking();
    this._bindEvents();
    if (opts.editable) {this._bindEditing();this._bindCopper();}
    this.ro = new ResizeObserver(() => { const camera=this.getCamera()||opts.camera;this._resize();if(camera)this.setCamera(camera);else this.fit();const f=this.geo.footprints.find(f=>f.ref===this.selected);if(f){const x=f.x*this.scale+this.ox,y=f.y*this.scale+this.oy;this.ox+=Math.max(35,Math.min(this.w-35,x))-x;this.oy+=Math.max(35,Math.min(this.h-35,y))-y;this.draw();} });
    this.ro.observe(host);
    if(opts.editable){this._resize();if(opts.camera)this.setCamera(opts.camera);else this.fit();}
    this._onTheme = () => this.draw();
    window.addEventListener("wb-theme", this._onTheme);
    this._onZoom = () => { this._resize(); this.draw(); };
    window.addEventListener("wb-zoom", this._onZoom);
  }

  _visible(kind,item){return this.opts.isVisible?.(kind,item)!==false&&this.layerRules?.visible(kind,item)!==false;}
  _layerAlpha(kind,item,layer){return this.layerRules?.opacity(kind,item,layer)??1;}
  _layerColor(layer){return this.layerColors?.[layer]||LAYER_COLORS[layer]||'#aaa';}
  _itemCuColor(kind,item){if(!this.layerRules)return null;const layers=(kind==='pads'?this.layerRules.padLayers(item):this.layerRules.viaLayers(item)).filter(l=>this.layerRules.visible(kind,item,l)),focus=this.layerRules.focused,preferred=focus==='bottom'?'B.Cu':focus==='top'?'F.Cu':(focus||'').split('/')[0];return this._layerColor(layers.includes(preferred)?preferred:layers.includes(this.routingLayer)?this.routingLayer:layers[0]);}
  _shown(kind,item){
    if(!this._visible(kind,item))return false;
    if(kind==='pads'){
      if(!this.layers.has('pads'))return false;
      if(this.layerRules)return this.layerRules.visible('pads',item);
      return item.kind==='np_thru_hole'||item.front&&this.layers.has('F.Cu')||item.back&&this.layers.has('B.Cu');
    }
    if(kind==='vias')return this.layers.has('vias');
    if(kind==='drawings')return this.layers.has(item.layer)&&(item.role!=='reference'||this.layers.has('refs'));
    if(kind==='tracks'||kind==='arcs'||kind==='zones')return this.layers.has(item.layer)&&(kind!=='zones'||this.layers.has('zones'));
    if(kind==='zone_definitions')return this.layers.has(this.layerRules?'zoneOutlines':'zones')&&(item.layers||[]).some(layer=>this.layers.has(layer));
    if(kind==='outline')return this.layers.has('outline');
    return true;
  }
  _padPickShape(p){return p.drill>0&&this.layerRules&&!this.layerRules.padLayers(p).some(l=>this.layerRules.visible('pads',p,l))?{...p,kind:'np_thru_hole',npth_copper:false}:p;}
  _bindObjectPicking(){
    this.host.addEventListener('pointerdown',event=>{
      if(event.target!==this.canvas||event.button!==0||!(event.ctrlKey||event.metaKey)||this.routing||!this.opts.onObjectSelect)return;
      const[x,y]=this._world(event),pads=this.geo.pads.filter(p=>{
        return this._shown('pads',p)&&padHit(this._padPickShape(p),x,y,.06);
      }).sort((a,b)=>a.w*a.h-b.w*b.h);
      const pad=pads[0];if(!pad?.id)return;
      event.preventDefault();event.stopImmediatePropagation();this.canvas.focus({preventScroll:true});this.opts.onObjectSelect({collection:'pads',id:pad.id,ref:pad.ref});
    },true);
  }
  setObjects(objects){this.objectSelections=objects;this.draw();}
  setHoveredNet(net){if(net===this.hoveredNet)return;this.hoveredNet=net;this.draw();}
  _drawObjectSelection(c){
    const draw=(kind,item)=>{
      if(!this._shown(kind,item))return;c.save();c.strokeStyle='#1dfdc0';c.lineWidth=2/this.scale;c.setLineDash([]);c.beginPath();
      if(kind==='pads'){item=this._padPickShape(item);c.translate(item.x,item.y);c.rotate(-(item.rot||0)*Math.PI/180);if(item.kind==='np_thru_hole'&&!item.npth_copper){const hole=padOpening(item);c.translate(...hole.offset);padPath(c,hole);}else padPath(c,item);}
      else if(kind==='tracks'){c.lineWidth=item.w+.12;c.moveTo(...item.a);c.lineTo(...item.b);}
      else if(kind==='arcs'){c.lineWidth=item.w+.12;arcPath(c,item.a,item.m,item.b);}
      else if(kind==='vias')c.arc(...item.p,item.d/2+.05,0,Math.PI*2);
      else if(kind==='footprints'){if(item.court)c.rect(item.court[0],item.court[1],item.court[2]-item.court[0],item.court[3]-item.court[1]);}
      else if(kind==='outline')outlinePath(c,[item]);
      else if(kind==='zones'||kind==='zone_definitions')for(const points of item.polygons||[item.pts]){if(!points?.length)continue;c.moveTo(...points[0]);for(const point of points.slice(1))c.lineTo(...point);c.closePath();}
      else if(kind==='drawings'){
        if(item.kind==='line'){c.moveTo(...item.start);c.lineTo(...item.end);}
        else if(item.kind==='arc')arcPath(c,item.start,item.mid,item.end);
        else if(item.kind==='circle')c.arc(...item.center,Math.hypot(item.end[0]-item.center[0],item.end[1]-item.center[1]),0,Math.PI*2);
        else if(item.kind==='poly'&&item.points?.length){c.moveTo(...item.points[0]);for(const point of item.points.slice(1))c.lineTo(...point);c.closePath();}
        else if(item.kind==='curve'&&item.points?.length>=4){c.moveTo(...item.points[0]);c.bezierCurveTo(...item.points.slice(1,4).flat());}
        else if(item.kind==='text'){c.translate(...item.at);c.rotate(-(item.angle||0)*Math.PI/180);const h=item.size?.[1]||1,w=(item.text||'').length*(item.size?.[0]||1)*.65;c.rect(item.align==='left'?0:item.align==='right'?-w:-w/2,-h/2,w,h);}
      }
      c.stroke();c.restore();
    };
    for(const selection of this.objectSelections||[]){
      if(selection.kind==='net'){for(const kind of ['pads','tracks','arcs','vias'])for(const item of this.geo[kind]||[])if(item.net===selection.net)draw(kind,item);continue;}
      if(selection.kind==='component'){const fp=this.geo.footprints.find(f=>f.ref===selection.ref);if(fp)draw('footprints',fp);continue;}
      const kind=selection.collection,item=this.geo[kind]?.find(item=>item.id===selection.id&&(!selection.ref||item.ref===selection.ref));if(item)draw(kind,item);
    }
  }

  _buildBar() {
    const items = [...(this.geo.layers || []).map(l => [l, l]), ["zones", "Pour"], ["pads", "Pads"],
                   ["vias", "Vias"], ["ratsnest", "Air wires"], ["courtyards", "Courtyards"], ["refs", "Labels"]];
    for (const [key, label] of items) {
      const b = document.createElement("button");
      b.type = "button";
      b.textContent = label;
      b.className = "chip toggle" + (this.layers.has(key) ? " on" : "");
      if (LAYER_COLORS[key]) b.style.setProperty("--dot", LAYER_COLORS[key]);
      b.onclick = () => {
        this.layers.has(key) ? this.layers.delete(key) : this.layers.add(key);
        b.classList.toggle("on");
        this.draw();
      };
      this.bar.append(b);
    }
    const fit = document.createElement("button");
    fit.type = "button"; fit.className = "chip"; fit.textContent = "Fit";
    fit.onclick = () => this.fit(true);
    this.bar.append(fit);
  }

  _resize() {
    // layout pixels; the backing store also covers the page zoom so it stays sharp
    const dpr = (window.devicePixelRatio || 1) * wbZoom();
    this.w = Math.max(100, this.host.clientWidth); this.h = Math.max(100, this.host.clientHeight);
    this.canvas.width = this.w * dpr; this.canvas.height = this.h * dpr;
    this.canvas.style.width = this.w + "px"; this.canvas.style.height = this.h + "px";
    this.dpr = dpr;
  }

  bounds() {
    if (this.geo.bbox) {
      // include parts placed beside the board (before placement)
      let [x0, y0, x1, y1] = this.geo.bbox;
      for (const p of this.geo.pads) { x0 = Math.min(x0, p.x); y0 = Math.min(y0, p.y); x1 = Math.max(x1, p.x); y1 = Math.max(y1, p.y); }
      return [x0, y0, x1, y1];
    }
    return [0, 0, 100, 100];
  }

  // the whole board, or the marked points when there are any (unless all)
  fit(all = false) {
    if (!this.w) this._resize();
    const [x0, y0, x1, y1] = this.opts.marks?.length && !all ? this.markBounds() : this.bounds();
    const pad = 6, bar = this.opts.compact ? 0 : 36;     // a compact view has no layer bar to leave room for
    const s = Math.min((this.w - (bar ? 40 : 16)) / (x1 - x0 + pad * 2), (this.h - (bar ? 80 : 16)) / (y1 - y0 + pad * 2));
    this.scale = Math.max(0.5, s);
    this.baseScale = this.scale; this.zoom = 1;
    this.ox = this.w / 2 - ((x0 + x1) / 2) * this.scale;
    this.oy = (this.h - bar) / 2 - ((y0 + y1) / 2) * this.scale;
    this.draw();
  }

  // frame the marked points with a few millimetres of board around them
  markBounds() {
    const xs = this.opts.marks.map(m => m.x), ys = this.opts.marks.map(m => m.y);
    const cx = (Math.min(...xs) + Math.max(...xs)) / 2, cy = (Math.min(...ys) + Math.max(...ys)) / 2;
    const half = Math.max(4, (Math.max(...xs) - Math.min(...xs)) / 2 + 2, (Math.max(...ys) - Math.min(...ys)) / 2 + 2);
    return [cx - half, cy - half, cx + half, cy + half];
  }

  // stop following resizes, theme and zoom changes, for a view that is being replaced
  destroy() {
    this.ro.disconnect();
    window.removeEventListener("wb-theme", this._onTheme);
    window.removeEventListener("wb-zoom", this._onZoom);
  }

  _bindEvents() {
    let drag = null;
    this.canvas.addEventListener("wheel", e => {
      e.preventDefault();
      const k = Math.exp(-e.deltaY * 0.0015);
      const r = this.canvas.getBoundingClientRect(), z = wbZoom();
      const mx = (e.clientX - r.left) / z, my = (e.clientY - r.top) / z;
      this.ox = mx - (mx - this.ox) * k; this.oy = my - (my - this.oy) * k;
      this.scale *= k;
      this.zoom = this.scale / (this.baseScale || this.scale); this.opts.onZoom?.(this.zoom);
      this.draw();
    }, { passive: false });
    this.canvas.addEventListener("pointerdown", e => { drag = [e.clientX, e.clientY]; this.canvas.setPointerCapture(e.pointerId); });
    this.canvas.addEventListener("pointerup", () => { drag = null; });
    this.canvas.addEventListener("pointermove", e => {
      if (drag) {
        const z = wbZoom();
        this.ox += (e.clientX - drag[0]) / z; this.oy += (e.clientY - drag[1]) / z;
        drag = [e.clientX, e.clientY];
        this.draw();
        return;
      }
      const r = this.canvas.getBoundingClientRect(), z = wbZoom();
      const mx = (e.clientX - r.left) / z, my = (e.clientY - r.top) / z;
      this._hover((mx - this.ox) / this.scale, (my - this.oy) / this.scale, mx, my);
    });
    this.canvas.addEventListener("pointerleave", () => { this.tip.style.display = "none"; });
  }

  _hover(x, y, sx, sy) {
    let best = null, bd = 1e9;
    for (const p of this.geo.pads) {
      if(!this._shown('pads',p))continue;
      const d = Math.hypot(p.x - x, p.y - y);
      if (padHit(p,x,y,.2) && d < bd) {
        bd = d; best = `${p.ref} pad ${p.name}` + (p.net ? ` · ${p.net}` : "");
        if(p.drill>0){const size=p.drill_size||[p.drill,p.drill],offset=p.drill_offset||[0,0];best+=` · ${p.kind==='np_thru_hole'?'Non-plated':'Plated'} hole ${size[0]} × ${size[1]} mm${offset.some(v=>v!==0)?` · Offset ${offset[0]}, ${offset[1]} mm`:''}`;}
      }
    }
    if (!best) {
      for (const t of this.geo.tracks) {
        if(!this._shown('tracks',t))continue;
        const d = segDist(x, y, t.a, t.b);
        if (d < t.w / 2 + 0.15 && d < bd) { bd = d; best = `${t.net || "track"} · ${t.layer} · ${t.w} mm`; }
      }
    }
    if (!best) {
      for (const f of this.geo.footprints) {
        if(!this._visible('footprints',f))continue;
        if (f.court && x >= f.court[0] && x <= f.court[2] && y >= f.court[1] && y <= f.court[3]) {
          best = `${f.ref} · ${f.lib.split(":").pop()}`; break;
        }
      }
    }
    if (best) {
      this.tip.textContent = best;
      this.tip.style.display = "block";
      this.tip.style.left = (sx + 14) + "px"; this.tip.style.top = (sy + 10) + "px";
    } else this.tip.style.display = "none";
    this._routingTerminal(x,y);
  }

  _routingTarget(x,y){
    const pads=this.geo.pads.filter(p=>this._shown('pads',p)&&p.net&&p.kind!=='np_thru_hole'&&padHit(p,x,y,.2)).sort((a,b)=>Math.hypot(a.x-x,a.y-y)-Math.hypot(b.x-x,b.y-y));
    const via=this.geo.vias?.filter(v=>this._shown('vias',v)&&v.net&&Math.hypot(v.p[0]-x,v.p[1]-y)<v.d/2+.15).sort((a,b)=>Math.hypot(a.p[0]-x,a.p[1]-y)-Math.hypot(b.p[0]-x,b.p[1]-y))[0],pad=pads[0];
    if(via&&(!pad||Math.hypot(via.p[0]-x,via.p[1]-y)<Math.hypot(pad.x-x,pad.y-y)))return{kind:'via',id:via.id};
    if(pad)return{kind:'pad',pin:`${pad.ref}.${pad.name}`,...(pad.id?{padId:pad.id}:{})};
    const copper=this._copperHit(x,y,this.routing?this.routingLayer:null);
    if(copper?.kind==='tracks')return{...copper,at:[x,y]};
    return null;
  }

  _routingTerminal(x,y){
    if(!this.opts.onRoutingTarget||this.opts.readOnly||this.routing||this.panTool||this.layerRules?.visible('tracks',{layer:this.routingLayer||'F.Cu'})===false){this.routeTerminals.replaceChildren();return;}
    const target=this._routingTarget(x,y);let point,label;
    if(target?.kind==='pad'){const pad=this.geo.pads.find(p=>`${p.ref}.${p.name}`===target.pin&&(!target.padId||p.id===target.padId)&&this._shown('pads',p));if(pad){point=pad.routing_anchor||[pad.x,pad.y];label=target.pin;}}
    else if(target?.kind==='tracks'&&!this.copperSelection){const track=this.geo.tracks.find(t=>t.id===target.id),near=[track.a,track.b].sort((a,b)=>Math.hypot(a[0]-x,a[1]-y)-Math.hypot(b[0]-x,b[1]-y))[0];if(Math.hypot(near[0]-x,near[1]-y)<7/this.scale){point=near;target.at=[...near];label=`${target.id}:end`;}}
    if(!point){this.routeTerminals.replaceChildren();return;}
    let button=this.routeTerminals.firstElementChild;if(!button){button=document.createElement('button');button.className='route-terminal';button.type='button';this.routeTerminals.append(button);}
    button.dataset.routeTerminal=label;button.routeTarget=target;button.setAttribute('aria-label',`Draw trace from ${label}`);button.style.left=(point[0]*this.scale+this.ox)+'px';button.style.top=(point[1]*this.scale+this.oy)+'px';
  }

  _world(e) {
    const r = this.canvas.getBoundingClientRect(), z = wbZoom();
    return [(e.clientX-r.left-this.ox*z)/(this.scale*z), (e.clientY-r.top-this.oy*z)/(this.scale*z)];
  }

  selectCopper(selection){this.copperSelection=selection;this.selected=null;this.selectedRefs=new Set();this.draw();}
  _copperItem(selection=this.copperSelection){return selection&&this.geo[selection.kind]?.find(item=>item.id===selection.id);}
  _copperHit(x,y,onlyLayer=null){
    let hit=null,distance=Infinity;
    for(const kind of ['vias','tracks','arcs'])for(const item of this.geo[kind]||[]){
      if(!this._shown(kind,item))continue;
      if(kind==='vias'?!this.layers.has('vias'):!this.layers.has(item.layer))continue;
      if(onlyLayer&&kind!=='vias'&&item.layer!==onlyLayer)continue;
      const centerDistance=kind==='vias'?Math.hypot(x-item.p[0],y-item.p[1]):kind==='tracks'?segDist(x,y,item.a,item.b):arcDistance(x,y,item.a,item.m,item.b);
      const d=Math.max(0,centerDistance-(kind==='vias'?item.d:item.w)/2),limit=5/this.scale;
      if(d<=limit&&d<distance-1e-7){hit={kind,id:item.id};distance=d;}
    }
    return hit;
  }
  _bindCopper(){
    if(!this.opts.onCopperSelect)return;
    const down=event=>{
      if(event.button!==0||this.panTool||event.altKey||this.routing||this.placingVia)return;
      if(event.target.closest('[data-route-terminal]'))return;
      const at=this._world(event),handle=event.target.closest('[data-copper-handle]')?.dataset.copperHandle;
      if(!handle&&this.geo.pads.some(p=>this._shown('pads',p)&&Math.hypot(p.x-at[0],p.y-at[1])<Math.max(p.w,p.h)/2+.15))return;
      const selection=handle?this.copperSelection:this._copperHit(...at);if(!selection)return;
      event.stopImmediatePropagation();event.preventDefault();
      this.copperDrag={selection,start:at,handle,original:structuredClone(this.geo),prior:this.copperSelection,blocked:this.opts.canEditSelection?.()===false};
      this.copperSelection=selection;this.selected=null;this.selectedRefs=new Set();this.draw();this.canvas.setPointerCapture(event.pointerId);
    };
    this.host.addEventListener('pointerdown',down,true);
    this.host.addEventListener('pointermove',event=>{
      const drag=this.copperDrag;if(!drag)return;event.stopImmediatePropagation();
      if(this.opts.readOnly||drag.blocked){if(drag.blocked&&!drag.warned){drag.warned=true;this.opts.onSelectionBlocked?.();}return;}
      const at=this._world(event),[ox,oy]=drag.original.bbox||[100,100],snap=p=>p.map(v=>+(Math.round(v/this.gridMm)*this.gridMm).toFixed(4)),item=drag.original[drag.selection.kind].find(t=>t.id===drag.selection.id);
      let patch;
      if(drag.handle)patch={[drag.handle]:snap([at[0]-ox,at[1]-oy])};
      else{
        const delta=snap(at.map((v,i)=>v-drag.start[i]));if(Math.hypot(...delta)<.001)return;
        patch=Object.fromEntries((drag.selection.kind==='vias'?['p']:drag.selection.kind==='arcs'?['a','m','b']:['a','b']).map(key=>[key,item[key].map((v,i)=>+(v-[ox,oy][i]+delta[i]).toFixed(4))]));
      }
      try{this.geo=this.opts.onCopperPreview(drag.selection,patch,drag.original);drag.patch=patch;drag.error=null;this.draw();}catch(error){drag.error=error;}
    },true);
    this.host.addEventListener('pointerup',event=>{
      const drag=this.copperDrag;if(!drag)return;event.stopImmediatePropagation();this.copperDrag=null;
      if(this.canvas.hasPointerCapture(event.pointerId))this.canvas.releasePointerCapture(event.pointerId);
      if(drag.error){this.geo=drag.original;this.draw();this.opts.onCopperError?.(drag.error);return;}
      this.opts.onCopperSelect(drag.selection);
      if(drag.patch&&!this.opts.readOnly)this.opts.onCopperEdit?.(drag.selection,drag.patch,drag.original);
    },true);
    this.host.addEventListener('pointercancel',()=>{if(!this.copperDrag)return;this.geo=this.copperDrag.original;this.copperSelection=this.copperDrag.prior;this.copperDrag=null;this.draw();},true);
  }

  _bindEditing() {
    let editing = null;
    this.canvas.addEventListener("pointerdown", e => {
      if (e.button !== 0 || this.panTool || e.altKey) return;
      const [x,y] = this._world(e);
      if(this.placingVia&&!this.opts.readOnly){e.stopImmediatePropagation();e.preventDefault();this.opts.onPoint?.(x,y);return;}
      if(this.routing&&this.opts.onRoutingTarget&&!this.opts.readOnly){
        e.stopImmediatePropagation();e.preventDefault();this.canvas.focus({preventScroll:true});
        const target=this._routingTarget(x,y);if(target)this.opts.onRoutingTarget(target,e);else this.opts.onRoutingPoint?.(x,y,e);return;
      }
      const pad = this.geo.pads.filter(p => this._shown('pads',p)&&Math.hypot(p.x-x,p.y-y)<Math.max(p.w,p.h)/2+.25).sort((a,b)=>Math.hypot(a.x-x,a.y-y)-Math.hypot(b.x-x,b.y-y))[0];
      const via=this.geo.vias?.map((v,i)=>({...v,i})).filter(v=>this._shown('vias',v)&&Math.hypot(v.p[0]-x,v.p[1]-y)<v.d/2+.2).sort((a,b)=>Math.hypot(a.p[0]-x,a.p[1]-y)-Math.hypot(b.p[0]-x,b.p[1]-y))[0];
      if(this.routing&&via&&!this.opts.readOnly&&!pad){e.stopImmediatePropagation();e.preventDefault();this.opts.onPad?.(`via:${via.i}`);return;}
      if (this.routing && pad && pad.kind!=='np_thru_hole' && !this.opts.readOnly) { e.stopImmediatePropagation(); e.preventDefault(); this.opts.onPad?.(`${pad.ref}.${pad.name}`); return; }
      const f = this.geo.footprints.find(f=>this._visible('footprints',f)&&f.court && x>=f.court[0] && x<=f.court[2] && y>=f.court[1] && y<=f.court[3]) || (pad && this.geo.footprints.find(f=>this._visible('footprints',f)&&f.ref===pad.ref));
      e.stopImmediatePropagation(); e.preventDefault(); this.canvas.setPointerCapture(e.pointerId);
      if(!f){editing={kind:'box',p0:[x,y],p1:[x,y],prior:e.shiftKey?[...(this.selectedRefs||[])]:[]};this.selectionBox=[x,y,x,y];return;}
      this.selectedRefs||=new Set(this.selected?[this.selected]:[]);
      if(e.shiftKey){this.selectedRefs.has(f.ref)?this.selectedRefs.delete(f.ref):this.selectedRefs.add(f.ref);this.draw();this.opts.onSelection?.([...this.selectedRefs],f.ref);return;}
      if(!this.selectedRefs.has(f.ref))this.selectedRefs=new Set([f.ref]);
      const blocked=this.opts.canEditSelection?.()===false;
      const members=this.geo.footprints.filter(f=>this.selectedRefs.has(f.ref)&&this._visible('footprints',f)).map(f=>({f,fx:f.x,fy:f.y,court:f.court&&[...f.court],locked:blocked||this.opts.readOnly||this.opts.locked?.has(f.ref),pads:this.geo.pads.filter(p=>p.ref===f.ref).map(p=>({p,x:p.x,y:p.y})),drawings:(this.geo.drawings||[]).filter(g=>g.ref===f.ref).map(g=>({g,source:JSON.parse(JSON.stringify(g))}))}));
      editing = { kind:'part', f, start:[x,y], blocked,locked:blocked||this.opts.readOnly||this.opts.locked?.has(f.ref),members };
      this.selected = f.ref; this.draw();
    }, true);
    this.canvas.addEventListener("pointermove", e => {
      const [x,y] = this._world(e); this.pointerWorld = [x,y];
      this.opts.onRoutingPointer?.(x,y,e);
      if(this.routing&&this.routeStart)this.draw();
      if (!editing) return;
      e.stopImmediatePropagation();
      if(editing.kind==='box'){editing.p1=[x,y];this.selectionBox=[...editing.p0,...editing.p1];this.draw();return;}
      if (editing.locked) {if(editing.blocked&&!editing.warned&&Math.hypot(x-editing.start[0],y-editing.start[1])>.05){editing.warned=true;this.opts.onSelectionBlocked?.();}return;}
      const dx=x-editing.start[0],dy=y-editing.start[1];
      editing.dx=dx; editing.dy=dy;
      for(const member of editing.members){if(member.locked)continue;member.f.x=member.fx+dx;member.f.y=member.fy+dy;if(member.court)member.f.court=member.court.map((v,i)=>v+(i%2?dy:dx));for(const p of member.pads){p.p.x=p.x+dx;p.p.y=p.y+dy;}for(const {g,source}of member.drawings){for(const key of ['start','end','mid','center','at'])if(source[key])g[key]=[source[key][0]+dx,source[key][1]+dy];if(source.points)g.points=source.points.map(p=>[p[0]+dx,p[1]+dy]);}}
      this.draw();
    }, true);
    this.canvas.addEventListener("pointerup", e => {
      if (!editing) return;
      e.stopImmediatePropagation(); const edit=editing; editing=null;
      if(edit.kind==='box'){
        const[x0,y0]=edit.p0,[x1,y1]=edit.p1,refs=new Set(edit.prior);
        if(Math.hypot(x1-x0,y1-y0)>.1)for(const f of this.geo.footprints)if(this._visible('footprints',f)&&f.court&&f.court[0]<=Math.max(x0,x1)&&f.court[2]>=Math.min(x0,x1)&&f.court[1]<=Math.max(y0,y1)&&f.court[3]>=Math.min(y0,y1))refs.add(f.ref);
        this.selectionBox=null;this.selectMany([...refs]);this.opts.onSelection?.([...refs]);return;
      }
      this.opts.onSelect?.(edit.f.ref,{selection:[...this.selectedRefs]});
      if (Math.hypot(edit.dx||0,edit.dy||0)>.05) {
        const [ox,oy]=this.geo.bbox||[100,100];
        if(this.opts.onMoveMany)this.opts.onMoveMany(edit.members.filter(m=>!m.locked).map(m=>({key:m.f.ref,x:m.f.x-ox,y:m.f.y-oy})));
        else this.opts.onMove?.(edit.f.ref,edit.f.x-ox,edit.f.y-oy);
      }
    }, true);
    this.canvas.addEventListener("pointercancel",()=>{if(editing?.kind==='part')for(const m of editing.members){m.f.x=m.fx;m.f.y=m.fy;if(m.court)m.f.court=m.court;for(const p of m.pads){p.p.x=p.x;p.p.y=p.y;}for(const {g,source}of m.drawings)Object.assign(g,source);}editing=null;this.selectionBox=null;this.draw();},true);
  }

  select(ref) { this.selected=ref;this.selectedRefs=new Set(ref?[ref]:[]);if(ref)this.copperSelection=null; this.draw(); }
  selectMany(refs){this.selectedRefs=new Set(refs);if(!this.selectedRefs.has(this.selected))this.selected=refs.at(-1)||null;this.draw();}
  grid(show){this.showGrid=show;this.draw();}

  getCamera(){return this.scale&&this.w?{kind:'board',center:[(this.w/2-this.ox)/this.scale,(this.h/2-this.oy)/this.scale],scale:this.scale,zoom:this.zoom}:null;}
  setCamera(camera){if(camera?.kind!=='board'||!this.w)return;this.scale=camera.scale;this.zoom=camera.zoom||1;this.baseScale=this.scale/this.zoom;this.ox=this.w/2-camera.center[0]*this.scale;this.oy=this.h/2-camera.center[1]*this.scale;this.draw();this.opts.onZoom?.(this.zoom);}

  setZoom(value) {
    this.baseScale ||= this.scale;
    const before=this.scale; this.zoom=Math.max(.25,Math.min(6,value)); this.scale=this.baseScale*this.zoom;
    this.ox=this.w/2-(this.w/2-this.ox)*this.scale/before;
    this.oy=this.h/2-(this.h/2-this.oy)*this.scale/before;
    this.draw(); this.opts.onZoom?.(this.zoom);
  }

  draw() {
    const c = this.ctx, g = this.geo;
    const preview=this.routing&&this.routeStart&&this.pointerWorld?this.opts.routePreview?.(this.pointerWorld,this._routingTarget(...this.pointerWorld)):null,routeHidden=new Set(preview?.hideIds||[]);
    if (!c || !this.scale) return;
    const css = getComputedStyle(document.documentElement);
    c.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
    c.fillStyle = css.getPropertyValue("--board-bg").trim() || "#0f1512";
    c.fillRect(0, 0, this.w, this.h);
    c.setTransform(this.dpr * this.scale, 0, 0, this.dpr * this.scale, this.dpr * this.ox, this.dpr * this.oy);

    // substrate
    if (g.outline.length&&this._visible('board',{id:'layout'})) {
      c.beginPath(); outlinePath(c, g.outline);
      c.fillStyle = css.getPropertyValue("--board-mask").trim() || "#1f4a35"; c.fill();
    }
    if(this.showGrid){c.globalAlpha=this._layerAlpha('grid');let step=this.gridMm;while(step*this.scale<9)step*=2;const left=-this.ox/this.scale,top=-this.oy/this.scale;c.fillStyle='#7d998156';for(let x=Math.ceil(left/step)*step;x<left+this.w/this.scale;x+=step)for(let y=Math.ceil(top/step)*step;y<top+this.h/this.scale;y+=step)c.fillRect(x-.45/this.scale,y-.45/this.scale,.9/this.scale,.9/this.scale);c.globalAlpha=1;}
    const cuOrder = [...(g.layers || [])].reverse(); // back first, front last
    for (const layer of cuOrder) {
      if (!this.layers.has(layer)) continue;
      const col = this._layerColor(layer);
      if (this.layers.has("zones")) {
        c.globalAlpha = layer === "F.Cu" ? 0.30 : 0.25;
        c.fillStyle = col;
        for (const z of g.zones) {
          if (z.layer !== layer || z.pts.length < 3||!this._visible('zones',z)) continue;
          c.globalAlpha=(layer==='F.Cu'?.30:.25)*this._layerAlpha('zones',z,layer);
          c.beginPath(); c.moveTo(z.pts[0][0], z.pts[0][1]);
          for (const p of z.pts) c.lineTo(p[0], p[1]);
          c.closePath(); c.fill();
        }
        c.globalAlpha = 1;
      }
      c.strokeStyle = col; c.lineCap = "round"; c.lineJoin = "round";
      c.globalAlpha = layer === "F.Cu" ? 0.95 : 0.8;
      for (const t of g.tracks) {
        if (t.layer !== layer||routeHidden.has(t.id)||!this._visible('tracks',t)) continue;
        c.globalAlpha=(this.layerRules?1:layer==='F.Cu'?.95:.8)*this._layerAlpha('tracks',t,layer);
        c.lineWidth = t.w; c.beginPath(); c.moveTo(t.a[0], t.a[1]); c.lineTo(t.b[0], t.b[1]); c.stroke();
      }
      for (const a of g.arcs) {
        if (a.layer !== layer||!this._visible('arcs',a)) continue;
        c.globalAlpha=(this.layerRules?1:layer==='F.Cu'?.95:.8)*this._layerAlpha('arcs',a,layer);
        c.lineWidth = a.w; c.beginPath(); arcPath(c, a.a, a.m, a.b); c.stroke();
      }
      c.globalAlpha = 1;
    }
    if (this.layers.has("pads")) {
      for (const p of g.pads) {
        if(!this._visible('pads',p))continue;
        const copperPad=p.kind==='np_thru_hole'?{...p,kind:'smd'}:p;
        const front = p.front && this.layers.has("F.Cu")&&this.layerRules?.visible('pads',copperPad,'F.Cu')!==false, back = p.back && this.layers.has("B.Cu")&&this.layerRules?.visible('pads',copperPad,'B.Cu')!==false;
        const inner=this.layerRules?.padLayers(copperPad).some(l=>/^In/.test(l)&&this.layerRules.visible('pads',copperPad,l));
        if (!front && !back&&!inner && !(p.drill>0)) continue;
        c.save();c.globalAlpha=this._layerAlpha('pads',p); c.translate(p.x, p.y); c.rotate(-p.rot * Math.PI / 180);
        if((p.kind!=="np_thru_hole"||p.npth_copper)&&(front||back||inner)){
          c.globalAlpha=this._layerAlpha('pads',copperPad);
          c.fillStyle = this._itemCuColor('pads',copperPad)||(p.kind === "thru_hole" ? "#e0b84f" : (front ? "#d4a43c" : "#7aa7e8"));
          padPath(c, p); c.fill(p.shape==='custom'?'evenodd':'nonzero');
        }
        if (p.drill > 0) {
          c.globalAlpha=this._layerAlpha('pads',p);
          const hole=padOpening(p);
          c.save();c.translate(...hole.offset);c.fillStyle=this.layerRules?'#000000':"#0b0f0d";
          padPath(c,hole);c.fill();
          if(p.kind==='np_thru_hole'||!front&&!back&&!inner){c.strokeStyle='#929997';c.lineWidth=1/this.scale;c.stroke();}
          c.restore();
        }
        c.restore();
      }
    }
    if (this.layers.has("vias")) {
      for (const v of g.vias) {
        if(routeHidden.has(v.id)||!this._visible('vias',v))continue;
        c.save();c.globalAlpha=this._layerAlpha('vias',v);
        c.fillStyle = this._itemCuColor('vias',v)||"#c9ced6"; c.beginPath(); c.arc(v.p[0], v.p[1], v.d / 2, 0, 7); c.fill();
        c.fillStyle = this.layerRules?'#000000':"#0b0f0d"; c.beginPath(); c.arc(v.p[0], v.p[1], v.drill / 2, 0, 7); c.fill();
        c.restore();
      }
    }
    for(const graphic of g.drawings||[]){
      if(!this._visible('drawings',graphic)||!this.layers.has(graphic.layer)||graphic.role==='reference'&&!this.layers.has('refs')||this.layerRules&&/^[FB]\.(Mask|Paste)$/.test(graphic.layer))continue;
      c.globalAlpha=this._layerAlpha('drawings',graphic);
      c.strokeStyle=this._layerColor(graphic.layer);c.fillStyle=c.strokeStyle;c.lineWidth=Math.max(graphic.width||.12,.5/this.scale);c.beginPath();
      if(graphic.kind==='text'){c.save();c.translate(...graphic.at);c.rotate(-graphic.angle*Math.PI/180);if(graphic.mirror)c.scale(-1,1);c.font=`${graphic.size?.[1]||1}px Roboto,Arial,sans-serif`;c.textAlign=graphic.align||'center';c.textBaseline='middle';c.fillText(graphic.text,0,0);c.restore();continue;}
      if(graphic.kind==='line'){c.moveTo(...graphic.start);c.lineTo(...graphic.end);}
      else if(graphic.kind==='arc')arcPath(c,graphic.start,graphic.mid,graphic.end);
      else if(graphic.kind==='circle')c.arc(...graphic.center,Math.hypot(graphic.end[0]-graphic.center[0],graphic.end[1]-graphic.center[1]),0,Math.PI*2);
      else if(graphic.kind==='poly'&&graphic.points?.length){c.moveTo(...graphic.points[0]);for(const p of graphic.points.slice(1))c.lineTo(...p);c.closePath();}
      else if(graphic.kind==='curve'&&graphic.points?.length>=4){c.moveTo(...graphic.points[0]);c.bezierCurveTo(...graphic.points.slice(1,4).flat());}
      if(graphic.fill)c.fill();c.stroke();
    }
    c.globalAlpha=1;
    for(const[layer,paths]of this.nativeLayerPaths||[]){if(this.layers.has(layer))this.opts.paintNativeLayer?.(c,paths,this.layerColors?.[layer]||'#a3aaa5',this._layerAlpha('apertures',{},layer));}
    if(this.layers.has('zoneOutlines'))for(const zone of g.zone_definitions||[]){
      if(!this._visible('zone_definitions',zone))continue;const layer=(zone.layers||[]).find(l=>this.layers.has(l)&&this.layerRules?.feature(l,'polygons')!==false);if(!layer)continue;
      c.save();c.globalAlpha=this._layerAlpha('zone_definitions',zone,layer);c.strokeStyle=zone.keepout?'#ff6e7a':this._layerColor(layer);c.lineWidth=Math.max(.06,1/this.scale);c.setLineDash([3/this.scale,3/this.scale]);
      for(const pts of zone.polygons||[]){if(!pts.length)continue;c.beginPath();c.moveTo(...pts[0]);for(const p of pts.slice(1))c.lineTo(...p);c.closePath();c.stroke();}c.restore();
    }
    if (this.layers.has("outline") && g.outline.length) {
      c.globalAlpha=this._layerAlpha('outline');
      c.strokeStyle = "#f3e7b3"; c.lineWidth = Math.max(0.15, 1.5 / this.scale);
      c.beginPath(); outlinePath(c, g.outline.filter(item=>this._visible('outline',item))); c.stroke();
    }
    if (this.layers.has("courtyards")) {
      c.globalAlpha=this._layerAlpha('courtyards');
      c.strokeStyle = "rgba(255,110,200,.7)"; c.lineWidth = 1 / this.scale; c.setLineDash([4 / this.scale, 3 / this.scale]);
      for (const f of g.footprints) if (f.court&&this._visible('footprints',f)) c.strokeRect(f.court[0], f.court[1], f.court[2] - f.court[0], f.court[3] - f.court[1]);
      c.setLineDash([]);
    }
    if (this.layers.has("ratsnest") && g.ratsnest) {
      c.globalAlpha=this._layerAlpha('nets');
      const selected=new Set((this.objectSelections||[]).filter(n=>n.kind==='net').map(n=>n.net)),focus=this.hoveredNet;if(focus)selected.add(focus);
      c.lineWidth=1/this.scale;
      if(g.airwire_objects){for(const wire of g.airwire_objects){if(!this._visible('nets',{id:wire.net}))continue;c.strokeStyle=selected.has(wire.net)?'#ffffff':selected.size?'rgba(120,230,255,.18)':'rgba(120,230,255,.75)';c.beginPath();c.moveTo(...wire.a);c.lineTo(...wire.b);c.stroke();}}
      else{c.strokeStyle='rgba(120,230,255,.75)';c.beginPath();for(const[a,b]of g.ratsnest){c.moveTo(...a);c.lineTo(...b);}c.stroke();}
    }
    if (this.layers.has("refs") && this.scale > 3) {
      c.globalAlpha=this._layerAlpha('labels');
      c.fillStyle = "rgba(255,255,255,.85)"; c.textAlign = "center"; c.textBaseline = "middle";
      const fs = Math.min(1.6, Math.max(0.7, 11 / this.scale));
      c.font = `600 ${fs}px Roboto, Arial, sans-serif`;
      for (const f of g.footprints) {
        if(!this._visible('footprints',f))continue;
        if (!f.court) continue;
        if((g.drawings||[]).some(d=>d.ref===f.ref&&d.role==='reference'))continue;
        c.fillText(f.ref, (f.court[0] + f.court[2]) / 2, (f.court[1] + f.court[3]) / 2);
      }
    }
    c.globalAlpha=1;
    for(const ref of this.selectedRefs||[this.selected]) {
      const f = g.footprints.find(f=>f.ref===ref);
      if (f?.court&&this._visible('footprints',f)) { const p=1/this.scale; c.strokeStyle="#1dfdc0"; c.lineWidth=p; c.setLineDash([4*p,3*p]); c.strokeRect(f.court[0],f.court[1],f.court[2]-f.court[0],f.court[3]-f.court[1]); c.setLineDash([]); }
    }
    if(this.selectionBox){const[a,b,x,y]=this.selectionBox;c.fillStyle='#1dfdc018';c.strokeStyle='#1dfdc0';c.lineWidth=1/this.scale;c.fillRect(Math.min(a,x),Math.min(b,y),Math.abs(x-a),Math.abs(y-b));c.strokeRect(Math.min(a,x),Math.min(b,y),Math.abs(x-a),Math.abs(y-b));}
    const rawSelectedCopper=this._copperItem(),selectedCopper=rawSelectedCopper&&this._shown(this.copperSelection.kind,rawSelectedCopper)?rawSelectedCopper:null;
    if((!selectedCopper||this.opts.readOnly)&&this.handles.childElementCount)this.handles.replaceChildren();
    if(selectedCopper&&this.copperSelection){
      const kind=this.copperSelection.kind;c.strokeStyle='#1dfdc0';c.lineWidth=(selectedCopper.w||selectedCopper.d)+.12;c.globalAlpha=.75;c.beginPath();
      if(kind==='tracks'){c.moveTo(...selectedCopper.a);c.lineTo(...selectedCopper.b);}
      else if(kind==='arcs')arcPath(c,selectedCopper.a,selectedCopper.m,selectedCopper.b);
      else c.arc(...selectedCopper.p,selectedCopper.d/2,0,Math.PI*2);
      c.stroke();c.globalAlpha=1;
      const keys=kind==='vias'?['p']:kind==='arcs'?['a','m','b']:['a','b'];
      for(const button of this.handles.children)if(!keys.includes(button.dataset.copperHandle))button.remove();
      if(!this.opts.readOnly)for(const key of keys){
        const point=selectedCopper[key];let button=this.handles.querySelector(`[data-copper-handle="${key}"]`);
        if(!button){button=document.createElement('button');button.className='copper-handle';button.dataset.copperHandle=key;button.type='button';button.setAttribute('aria-label',`Move copper ${key==='a'?'start':key==='b'?'end':key==='m'?'arc midpoint':'via'}`);this.handles.append(button);}
        button.style.left=(point[0]*this.scale+this.ox)+'px';button.style.top=(point[1]*this.scale+this.oy)+'px';
      }
    }
    this._drawObjectSelection(c);
    if(this.routing||this.opts.readOnly)this.routeTerminals.replaceChildren();
    else if(this.pointerWorld)this._routingTerminal(...this.pointerWorld);
    if(this.routing&&this.routeStart&&this.pointerWorld){
      const fallback=()=>{const[a,b]=[this.routeStart,this.pointerWorld];return[{layer:this.routingLayer||'F.Cu',width:this.routingWidth||.25,points:this.opts.routePoints?this.opts.routePoints(a,b,{flip:this.routeFlip,free:this.routeFree}):[a,b]}];};
      for(const path of preview?.paths||fallback()){if(!this.layers.has(path.layer))continue;c.save();c.strokeStyle=preview?.error?'#ff6e7a':path.shoved?'#f5b95f':this._layerColor(path.layer);c.lineWidth=path.width;c.globalAlpha=path.shoved?.8:.65;if(path.shoved)c.setLineDash([.15,.12]);c.beginPath();c.moveTo(...path.points[0]);for(const p of path.points.slice(1))c.lineTo(...p);c.stroke();c.restore();}
      if(this.layers.has('vias'))for(const v of preview?.vias||[]){if(!this._visible('vias',v))continue;c.globalAlpha=.65;c.fillStyle=this._itemCuColor('vias',v)||'#d4a43c';c.beginPath();c.arc(...v.p,v.d/2,0,Math.PI*2);c.fill();c.fillStyle='#101010';c.beginPath();c.arc(...v.p,v.drill/2,0,Math.PI*2);c.fill();}c.globalAlpha=1;
    }
    for(const person of this.opts.presence||[]){
      const f=g.footprints.find(f=>f.ref===person.ref),p=1/this.scale;
      if(f?.court){c.strokeStyle=person.color;c.lineWidth=p;c.setLineDash([4*p,3*p]);c.strokeRect(f.court[0]-p,f.court[1]-p,f.court[2]-f.court[0]+2*p,f.court[3]-f.court[1]+2*p);c.setLineDash([]);}
      if(person.cursor){const[x,y]=person.cursor;c.fillStyle=person.color;c.strokeStyle='#101010';c.lineWidth=p;c.beginPath();c.moveTo(x,y);c.lineTo(x,y+18*p);c.lineTo(x+5*p,y+12*p);c.lineTo(x+11*p,y+11*p);c.closePath();c.fill();c.stroke();c.font=`${10*p}px Roboto,Arial,sans-serif`;c.textAlign='left';c.textBaseline='middle';const width=c.measureText(person.name).width+12*p;c.fillRect(x+10*p,y+15*p,width,17*p);c.fillStyle='#101010';c.fillText(person.name,x+16*p,y+24*p);}
    }
    if (this.opts.marks?.length) {
      // the points a finding is about: a ring and crosshair that keep their size on screen
      const r = 10 / this.scale;
      c.strokeStyle = this.opts.markColor || "#ff3b8d"; c.lineWidth = 2 / this.scale;
      for (const m of this.opts.marks) {
        c.beginPath(); c.arc(m.x, m.y, r, 0, 7);
        c.moveTo(m.x - r * 1.6, m.y); c.lineTo(m.x - r * 0.5, m.y); c.moveTo(m.x + r * 0.5, m.y); c.lineTo(m.x + r * 1.6, m.y);
        c.moveTo(m.x, m.y - r * 1.6); c.lineTo(m.x, m.y - r * 0.5); c.moveTo(m.x, m.y + r * 0.5); c.lineTo(m.x, m.y + r * 1.6);
        c.stroke();
      }
    }
  }
}

function segDist(x, y, a, b) {
  const dx = b[0] - a[0], dy = b[1] - a[1];
  const l = dx * dx + dy * dy;
  let t = l ? ((x - a[0]) * dx + (y - a[1]) * dy) / l : 0;
  t = Math.max(0, Math.min(1, t));
  return Math.hypot(x - (a[0] + t * dx), y - (a[1] + t * dy));
}

function circleFrom3(a, m, b) {
  const ax = a[0], ay = a[1], bx = m[0], by = m[1], cx = b[0], cy = b[1];
  const d = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by));
  if (Math.abs(d) < 1e-9) return null;
  const ux = ((ax * ax + ay * ay) * (by - cy) + (bx * bx + by * by) * (cy - ay) + (cx * cx + cy * cy) * (ay - by)) / d;
  const uy = ((ax * ax + ay * ay) * (cx - bx) + (bx * bx + by * by) * (ax - cx) + (cx * cx + cy * cy) * (bx - ax)) / d;
  return [ux, uy, Math.hypot(ax - ux, ay - uy)];
}

function arcDistance(x,y,a,m,b){
  const circle=circleFrom3(a,m,b);if(!circle)return segDist(x,y,a,b);
  const [cx,cy,r]=circle,norm=n=>(n+4*Math.PI)%(2*Math.PI),start=Math.atan2(a[1]-cy,a[0]-cx),middle=Math.atan2(m[1]-cy,m[0]-cx),end=Math.atan2(b[1]-cy,b[0]-cx),at=Math.atan2(y-cy,x-cx),clockwise=norm(middle-start)<norm(end-start),inside=clockwise?norm(at-start)<=norm(end-start):norm(start-at)<=norm(start-end);
  return inside?Math.abs(Math.hypot(x-cx,y-cy)-r):Math.min(Math.hypot(x-a[0],y-a[1]),Math.hypot(x-b[0],y-b[1]));
}

function arcPath(c, a, m, b, move = true) {
  const k = circleFrom3(a, m, b);
  if (!k) { if (move) c.moveTo(a[0], a[1]); c.lineTo(b[0], b[1]); return; }
  const [ux, uy, r] = k;
  const s = Math.atan2(a[1] - uy, a[0] - ux), e = Math.atan2(b[1] - uy, b[0] - ux), mid = Math.atan2(m[1] - uy, m[0] - ux);
  const norm = v => (v + 4 * Math.PI) % (2 * Math.PI);
  const ccw = !(norm(mid - s) < norm(e - s));
  if (move) c.moveTo(a[0], a[1]);
  c.arc(ux, uy, r, s, e, ccw);
}

function outlinePath(c, items) {
  // chain the outline pieces end to end
  const rest = items.slice();
  const near = (p, q) => Math.hypot(p[0] - q[0], p[1] - q[1]) < 0.01;
  while (rest.length) {
    let cur = rest.shift();
    if (cur.kind === "rect") { c.rect(cur.start[0], cur.start[1], cur.end[0] - cur.start[0], cur.end[1] - cur.start[1]); continue; }
    if (cur.kind === "circle") { c.moveTo(cur.end[0], cur.end[1]); c.arc(cur.center[0], cur.center[1], Math.hypot(cur.end[0] - cur.center[0], cur.end[1] - cur.center[1]), 0, 7); continue; }
    c.moveTo(cur.start[0], cur.start[1]);
    let end = cur.start;
    for (;;) {
      if (cur.kind === "arc") arcPath(c, cur.start, cur.mid, cur.end, false); else c.lineTo(cur.end[0], cur.end[1]);
      end = cur.end;
      const i = rest.findIndex(o => o.start && (near(o.start, end) || near(o.end, end)));
      if (i < 0) break;
      cur = rest.splice(i, 1)[0];
      if (!near(cur.start, end)) cur = { ...cur, start: cur.end, end: cur.start };
    }
    c.closePath();
  }
}

function padOpening(p){const size=p.drill_size||[p.drill,p.drill];return{w:size[0],h:size[1],shape:p.drill_shape==='oval'?'oval':'circle',offset:p.drill_offset||[0,0]};}
function padHit(p,x,y,slop=0){
  const angle=(p.rot||0)*Math.PI/180,dx=x-p.x,dy=y-p.y,u=dx*Math.cos(angle)-dy*Math.sin(angle),v=dx*Math.sin(angle)+dy*Math.cos(angle);
  if(p.shape==='custom'&&(p.kind!=='np_thru_hole'||p.npth_copper)&&p.copper_polygons?.length){
    let inside=false;for(const ring of p.copper_contours||p.copper_polygons){let hit=false;for(let i=0,j=ring.length-1;i<ring.length;j=i++){
      const a=ring[j],b=ring[i];if(segDist(u,v,a,b)<=slop)return true;if((a[1]>v)!==(b[1]>v)&&u<(b[0]-a[0])*(v-a[1])/(b[1]-a[1])+a[0])hit=!hit;
    }inside=inside!==hit;}return inside;
  }
  if(p.kind!=='np_thru_hole'||p.npth_copper)return Math.abs(u)<=p.w/2+slop&&Math.abs(v)<=p.h/2+slop;
  const h=padOpening(p),r=Math.min(h.w,h.h)/2,a=Math.max(0,h.w/2-r),b=Math.max(0,h.h/2-r);
  return segDist(u-h.offset[0],v-h.offset[1],[-a,-b],[a,b])<=r+slop;
}
function padPath(c, p) {
  const w = p.w, h = p.h;
  c.beginPath();
  if(p.shape==='custom'){for(const ring of p.copper_contours||p.copper_polygons||[]){if(!ring.length)continue;c.moveTo(...ring[0]);for(const point of ring.slice(1))c.lineTo(...point);c.closePath();}}
  else if (p.shape === "circle") c.arc(0, 0, w / 2, 0, 7);
  else if (p.shape === "oval") {
    const r = Math.min(w, h) / 2;
    roundRect(c, -w / 2, -h / 2, w, h, r);
  } else if (p.shape === "roundrect") roundRect(c, -w / 2, -h / 2, w, h, Math.min(w, h) * 0.25);
  else c.rect(-w / 2, -h / 2, w, h);
}

function roundRect(c, x, y, w, h, r) {
  c.moveTo(x + r, y); c.arcTo(x + w, y, x + w, y + h, r); c.arcTo(x + w, y + h, x, y + h, r);
  c.arcTo(x, y + h, x, y, r); c.arcTo(x, y, x + w, y, r); c.closePath();
}

window.BoardView = BoardView;
