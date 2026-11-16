import { componentPins, pinIndex } from './workbench-model.mjs';
import { esc, icon } from './workbench-icons.mjs';
import { nativeSymbol, nativeSheet,nativeNetLabel } from './workbench-symbol.mjs';
import {displayedWires,guideIdentity} from './workbench-objects-model.mjs';

const text = (x, y, label, opts = '') => `<text x="${x}" y="${y}" ${opts.includes('fill=') ? '' : 'fill="#c7c7c7"'} font-family="Roboto,Arial,sans-serif" ${opts.includes('font-size=') ? '' : 'font-size="15"'} ${opts}>${esc(label)}</text>`;
const line = (x, y, x2, y2, opts = '') => `<path d="M${x} ${y}L${x2} ${y2}" fill="none" ${opts.includes('stroke=') ? '' : 'stroke="#9a9e9b"'} stroke-width="1.4" ${opts}/>`;

function schematicPosition(spec, c, i) {
  return spec.editor?.positions?.[c.ref] || [180 + i % 4 * 280, 210 + Math.floor(i / 4) * 260];
}

function symbol(c, pins) {
  const passive = /^[RCDLY]/.test(c.ref) && pins.length <= 4;
  let shape = '', anchors = [], box = [-85, -85, 170, 170];
  if (passive) {
    anchors = pins.map(({ pin, net }) => { const down = c.ref.startsWith('D') ? pin === '1' : pin === '2'; return { pin, net, x: 0, y: down ? 58 : -58, direction: down ? 'down' : 'up' }; });
    if (c.ref.startsWith('R')) shape = '<path class="component-body" d="M0 -58v18l-8 5 16 10-16 10 16 10-16 10 16 10-8 5v18" fill="none" stroke="#b9bdbb" stroke-width="1.6"/>';
    else if (c.ref.startsWith('C')) shape = '<path class="component-body" d="M0 -58v51m-17 0h34m-34 14h34M0 7v51" stroke="#b9bdbb" stroke-width="1.7" fill="none"/>';
    else if (c.ref.startsWith('D')) shape = '<path class="component-body" d="M0 -58v32m-17 0h34L0 5zM-17 5h34M0 5v53M21 -13l16-16m-7 0h7v7M27 1l16-16m-7 0h7v7" stroke="#b9bdbb" stroke-width="1.7" fill="none"/>';
    else shape = '<rect class="component-body" x="-13" y="-25" width="26" height="50" fill="#181818" stroke="#b9bdbb" stroke-width="1.4"/>';
    shape += text(47, -17, c.ref, 'font-size="17"') + text(47, 8, c.value, 'font-size="14" fill="#999"');
    box = [-50, -85, 145, 170];
  } else if (c.ref.startsWith('U') && c.value?.includes('1117')) {
    shape = '<rect class="component-body" x="-65" y="-42" width="130" height="84" fill="#181818" stroke="#b9bdbb" stroke-width="1.5"/>';
    anchors = pins.map(p => ({ ...p, x: p.pin === '1' ? 0 : p.pin === '2' ? 100 : -100, y: p.pin === '1' ? 78 : 0, direction: p.pin === '1' ? 'down' : p.pin === '2' ? 'right' : 'left' }));
    shape += text(0, -65, c.ref, 'text-anchor="middle" font-size="18"') + text(0, -8, 'AMS1117', 'text-anchor="middle"') + text(0, 13, '3.3 V', 'text-anchor="middle" font-size="13"');
    shape += text(-58, 27, 'VI', 'font-size="10"') + text(40, 27, 'VO', 'font-size="10"');
    box = [-110, -88, 220, 196];
  } else {
    const connector = c.ref.startsWith('J');
    const width = connector ? 115 : 160;
    const height = Math.max(90, Math.ceil(pins.length / (connector ? 1 : 2)) * 23 + 24);
    shape = `<rect class="component-body" x="${-width / 2}" y="${-height / 2}" width="${width}" height="${height}" fill="#181818" stroke="#b9bdbb" stroke-width="1.4"/>`;
    shape += text(0, -height / 2 - 17, c.ref, 'text-anchor="middle" font-size="18"');
    shape += text(0, height / 2 + 26, c.value?.replaceAll('_', ' '), 'text-anchor="middle" font-size="14"');
    anchors = pins.map((p, i) => {
      const left = !connector && i >= Math.ceil(pins.length / 2);
      const count = connector ? pins.length : left ? Math.floor(pins.length / 2) : Math.ceil(pins.length / 2);
      const j = connector ? i : i % Math.ceil(pins.length / 2);
      const y = -((count - 1) * 23) / 2 + j * 23;
      return { ...p, x: (left ? -1 : 1) * (width / 2 + 28), y, direction: left ? 'left' : 'right' };
    });
    for (const a of anchors) {
      const side = a.direction === 'left' ? -1 : 1;
      shape += text(side * (width / 2 - 8), a.y + 4, a.pin, `text-anchor="${side === 1 ? 'end' : 'start'}" font-size="10" fill="#999"`);
      shape += line(side * width / 2, a.y, a.x, a.y);
    }
    box = [-width / 2 - 35, -height / 2 - 42, width + 70, height + 86];
  }
  for (const a of anchors) {
    const s = a.direction === 'left' || a.direction === 'up' ? -1 : 1;
    const vertical = ['up', 'down'].includes(a.direction);
    const ex = a.x + (vertical ? 0 : s * 35), ey = a.y + (vertical ? s * 25 : 0);
    shape += line(a.x, a.y, ex, ey, 'stroke="#7f9f90"');
    if (!a.net) {
      shape += text(ex + 7, ey + 4, a.pin, 'fill="#555" font-size="10"');
    } else if (a.net === 'GND' && vertical && s === 1) {
      shape += line(ex - 12, ey, ex + 12, ey) + line(ex - 8, ey + 5, ex + 8, ey + 5) + line(ex - 4, ey + 10, ex + 4, ey + 10);
    } else {
      shape += text(ex + (vertical ? 7 : s * 7), ey + (vertical ? -3 : 4), a.net, `fill="#8bb9a3" font-size="12" text-anchor="${!vertical && s < 0 ? 'end' : 'start'}"`);
    }
    shape += `<circle cx="${a.x}" cy="${a.y}" r="7" fill="transparent" data-pinref="${esc(c.ref + '.' + a.pin)}" style="cursor:crosshair"/><circle cx="${a.x}" cy="${a.y}" r="2.4" fill="#aaa" pointer-events="none"/>`;
  }
  return { shape, box };
}

export class DesignCanvas {
  constructor(host, spec, options = {}) {
    this.host = host; this.spec = spec; this.options = options;
    this.mode = options.mode || 'schematic'; this.zoom = 1; this.offset = [0, 0]; this.panTool = false;
    this.selectedKeys=new Set(options.selection||(options.selected?[options.selectedKey||options.selected]:[]));
    this.showGrid = false; this.hiddenLayers = new Set();
    this.render();
    if(options.camera)this.setCamera(options.camera);
    this.ro=new ResizeObserver(()=>{if(this.camera)this.setCamera(this.camera);this.revealSelection();});this.ro.observe(host);
  }
  render() {
    const schematic = this.mode === 'schematic';
    const s = this.spec, selected = this.options.selected;
    this.extent = schematic ? [1200, Math.max(800, Math.ceil(s.components.length / 4) * 260 + 110)] : [1200, 850];
    let content = '';
    if (schematic) {
      if (s.name === 'usb_led_3v3'&&!this.options.nativeScene) {
        content += text(80, 95, 'USB-C power input', 'fill="#6d736f" font-size="17"') + line(80, 112, 360, 112, 'stroke="#343b37"');
        content += text(465, 95, '3.3 V regulator', 'fill="#6d736f" font-size="17"') + line(465, 112, 830, 112, 'stroke="#343b37"');
        content += text(920, 95, 'Status & expansion', 'fill="#6d736f" font-size="17"') + line(920, 112, 1125, 112, 'stroke="#343b37"');
      }
      if(this.options.nativeScene){
        const scene=this.options.nativeScene,nets=pinIndex(s);
        const sheet=this.options.sheet||'';
        const wireBoxes=(scene.wires||[]).filter(w=>w.sheet===sheet).map(w=>[Math.min(...w.points.map(p=>p[0])),Math.min(...w.points.map(p=>p[1])),Math.max(...w.points.map(p=>p[0])),Math.max(...w.points.map(p=>p[1]))]);
        content+=scene.symbols.filter(instance=>instance.sheet===sheet).map(instance=>nativeSymbol(instance,scene.definitions[instance.definition],s,nets,scene.mm_per_unit,scene.origin_mm,selected,wireBoxes)).join('');
        content+=(scene.sheet_nodes||[]).filter(n=>n.sheet===sheet).map(nativeSheet).join('');
      }else s.components.forEach((c, i) => {
        const pins = componentPins(s, c.ref), known = /^[RCD]\d/.test(c.ref) ? ['1', '2'] : c.value?.includes('1117') ? ['1', '2', '3'] : c.value?.startsWith('Header 1x') ? Array.from({length: Number(c.value.match(/1x(\d+)/)?.[1]) || 4}, (_,i) => String(i+1)) : [];
        for (const pin of known) if (!pins.some(p => p.pin === pin)) pins.push({ pin, net: '' });
        const [x, y] = schematicPosition(s, c, i), { shape, box } = symbol(c, pins);
        content += `<g class="canvas-component${selected === c.ref ? ' selected' : ''}" data-ref="${esc(c.ref)}" data-x="${x}" data-y="${y}" transform="translate(${x},${y})" role="button" tabindex="0" aria-label="${esc(c.ref + ' ' + c.value)}"><rect class="component-hitbox" x="${box[0]}" y="${box[1]}" width="${box[2]}" height="${box[3]}" fill="transparent" pointer-events="all"/><rect class="selection-outline" x="${box[0]}" y="${box[1]}" width="${box[2]}" height="${box[3]}" rx="3"/>${shape}</g>`;
      });
      if(!this.options.nativeScene)content += text(80, this.extent[1] - 25, `${s.components.length} components     ${s.nets.length} nets`, 'font-size="12" fill="#555f58"');
    } else {
      content = this.layoutMarkup();
    }
    this.host.innerHTML = `<svg class="design-svg" viewBox="0 0 ${this.extent[0]} ${this.extent[1]}" aria-label="${schematic ? 'Interactive schematic' : 'Interactive PCB placement preview'}"><defs><pattern id="editorGrid" width="20" height="20" patternUnits="userSpaceOnUse"><circle cx="1" cy="1" r=".8" fill="#343a36"/></pattern></defs><rect class="grid-background" width="100%" height="100%" fill="url(#editorGrid)" opacity="${this.showGrid ? .6 : 0}"/><g data-scene>${content}</g></svg>${schematic ? '' : `<div class="view-badge">${icon('info')}Placement preview · simplified footprints</div><div class="view-caption">${esc(s.board.width_mm)} × ${esc(s.board.height_mm)} mm · ${esc(s.board.layers || 2)} layers · Unrouted</div>`}`;
    this.svg = this.host.querySelector('svg.design-svg'); this.scene = this.svg.querySelector('[data-scene]');
    if(this.options.nativeScene){const e=this.options.nativeScene.sheets.find(s=>s.name===(this.options.sheet||''))?.extent,box=this.scene.getBBox(),x=e?.[0]??box.x,y=e?.[1]??box.y,w=e?e[2]-e[0]:box.width,h=e?e[3]-e[1]:box.height;this.extent=[Math.max(600,w+120),Math.max(400,h+120)];this.frame={x:x+w/2-this.extent[0]/2,y:y+h/2-this.extent[1]/2};this.svg.setAttribute('viewBox',`${this.frame.x} ${this.frame.y} ${this.extent[0]} ${this.extent[1]}`);this.svg.querySelector('.grid-background').setAttribute('x',this.frame.x);this.svg.querySelector('.grid-background').setAttribute('y',this.frame.y);}
    this.applyTransform(); this.bind();this.selectMany([...this.selectedKeys]);this.selectSheet(this.options.selectedSheet);
    this.drawConnections();
  }
  layoutMarkup() {
    const s = this.spec, b = s.board, scale = Math.min(24, 760 / b.width_mm, 570 / b.height_mm);
    const w = b.width_mm * scale, h = b.height_mm * scale;
    this.layout = { scale, x: (1200 - w) / 2, y: (820 - h) / 2, w, h };
    const { x, y } = this.layout;
    let markup = `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="${Math.min(18, (b.corner_radius_mm || 1) * scale)}" fill="#080d0a" stroke="#4b946c" stroke-width="2"/>`;
    const positions = new Map(), anchors = new Map();
    s.components.forEach((c, i) => {
      const pl = c.placement || {}, xx = x + (pl.x_mm ?? b.width_mm * (.2 + i % 4 * .2)) * scale, yy = y + (pl.y_mm ?? b.height_mm * (.2 + Math.floor(i / 4) * .2)) * scale;
      positions.set(c.ref, [xx, yy]);
      const pins = componentPins(s, c.ref);
      pins.forEach((p, j) => anchors.set(`${c.ref}.${p.pin}`, [xx + (j % 2 ? 1 : -1) * scale * 1.2, yy + (Math.floor(j / 2) - Math.ceil(pins.length / 2) / 2 + .5) * scale * .6]));
    });
    if (!this.hiddenLayers.has('ratsnest')) for (const net of s.nets || []) {
      const ps = net.pins.map(p => anchors.get(p)).filter(Boolean);
      for (let i = 1; i < ps.length; i++) markup += `<path class="canvas-net" data-net="${esc(net.name)}" d="M${ps[i - 1][0]} ${ps[i - 1][1]}L${ps[i][0]} ${ps[i][1]}" stroke="${net.name === 'GND' ? '#415e4c' : '#53645d'}" stroke-width="1.1" fill="none" stroke-dasharray="4 3" opacity=".6"/>`;
    }
    for (const [i, c] of s.components.entries()) {
      const [xx, yy] = positions.get(c.ref), pins = componentPins(s, c.ref), fp = c.footprint || '';
      const bw = (fp.includes('SOT-223') ? 5.8 : c.ref.startsWith('J') ? 4.5 : c.ref.startsWith('U') ? 5 : 1.6) * scale;
      const bh = (fp.includes('SOT-223') ? 5.5 : c.ref.startsWith('J') ? 5.8 : c.ref.startsWith('U') ? 5 : .8) * scale;
      let shapes = `<rect class="component-body" x="${-bw / 2}" y="${-bh / 2}" width="${bw}" height="${bh}" fill="${c.ref.startsWith('U') ? '#222527' : '#14231c'}" stroke="#8bbeb5" stroke-width="1"/>`;
      if (!this.hiddenLayers.has('pads')) for (const [j, p] of pins.entries()) {
        const [ax, ay] = anchors.get(`${c.ref}.${p.pin}`), px = ax - xx, py = ay - yy;
        shapes += `<rect x="${px - scale * .25}" y="${py - scale * .22}" width="${scale * .5}" height="${scale * .44}" rx="1" fill="#d63f38" stroke="#b88563" stroke-width=".7"/>`;
        shapes += text(px, py + 3, p.pin, 'font-size="8" text-anchor="middle" fill="#eee"');
      }
      if (!this.hiddenLayers.has('refs')) shapes += text(0, -bh / 2 - 11, c.ref, 'text-anchor="middle" fill="#7dd6d2" font-size="14"');
      markup += `<g class="canvas-component${this.options.selected === c.ref ? ' selected' : ''}" data-ref="${esc(c.ref)}" data-x="${xx}" data-y="${yy}" transform="translate(${xx},${yy})" role="button" tabindex="0" aria-label="${esc(c.ref + ' ' + c.value)}"><rect x="${-bw / 2 - 14}" y="${-bh / 2 - 24}" width="${bw + 28}" height="${bh + 38}" fill="transparent" pointer-events="all"/><rect class="selection-outline" x="${-bw / 2 - 14}" y="${-bh / 2 - 24}" width="${bw + 28}" height="${bh + 38}" rx="3"/>${shapes}</g>`;
    }
    markup += `<path d="M${x} ${y + h + 35}h${w}m0-7v14m${-w}-14v14" stroke="#65796c" fill="none"/>` + text(x + w / 2, y + h + 57, `${b.width_mm} mm`, 'text-anchor="middle" font-size="13" fill="#8b9b90"');
    return markup;
  }
  point(e) {
    const p = this.svg.createSVGPoint(); p.x = e.clientX; p.y = e.clientY;
    return p.matrixTransform(this.svg.getScreenCTM().inverse());
  }
  bind() {
    let drag = null;
    this.svg.addEventListener('pointerdown', e => {
      const p = this.point(e), el = e.target.closest('[data-ref]');
      const node=e.target.closest('[data-wire-node]');
      if(e.button===0&&!this.panTool&&!e.altKey&&!this.wiringMode&&this.options.canEditSelection?.()===false){
        const sheet=e.target.closest('[data-sheet-target]'),wire=e.target.closest('[data-wire-route]');e.preventDefault();
        if(node)this.options.onWireNodeSelect?.(node.dataset.wireNode);else if(sheet)this.options.onSheetSelect?.(sheet.dataset.sheetTarget);else if(el)this.options.onSelect?.(el.dataset.ref,{symbolKey:el.dataset.symbolKey||el.dataset.ref});else if(wire)this.options.onWireSelect?.(Number(wire.dataset.wireRoute));
        this.options.onBlocked?.('Select one editable object or only components before dragging.');return;
      }
      if(node&&e.button===0&&!this.panTool&&!e.altKey){
        e.preventDefault();if(this.wiringMode&&!this.options.readOnly){this.options.onWireNodeConnect?.(node.dataset.wireNode);return;}
        if(this.options.readOnly){this.options.onWireNodeSelect?.(node.dataset.wireNode);return;}
        drag={kind:'wire-node',id:node.dataset.wireNode,el:node,label:!!node.dataset.netLabel,start:this.worldPoint(e),position:node.dataset.netLabel?[+node.dataset.x,+node.dataset.y]:[+node.getAttribute('cx'),+node.getAttribute('cy')]};this.interacting=true;this.svg.setPointerCapture(e.pointerId);return;
      }
      const handle=e.target.closest('[data-wire-segment]');
      if(handle&&e.button===0&&!this.panTool&&!this.wiringMode&&!this.options.readOnly){
        const route=this.options.nativeScene.routes.find(r=>r.index===Number(handle.dataset.wireIndex)&&r.sheet===(this.options.sheet||''));
        drag={kind:'wire',route,segment:Number(handle.dataset.wireSegment),start:this.worldPoint(e),points:structuredClone(route.points)};
        this.interacting=true;e.preventDefault();e.stopPropagation();this.svg.setPointerCapture(e.pointerId);return;
      }
      const wire=e.target.closest('[data-wire-route]');
      if(wire&&e.button===0&&!this.panTool&&this.wiringMode&&!this.options.readOnly&&this.options.onWireConnect){e.preventDefault();const at=this.worldPoint(e);this.options.onWireConnect(Number(wire.dataset.wireRoute),[at.x,at.y]);return;}
      if(wire&&e.button===0&&!this.panTool&&!this.wiringMode&&this.options.onWireSelect){e.preventDefault();const at=this.worldPoint(e);this.options.onWireSelect(Number(wire.dataset.wireRoute),[at.x,at.y]);return;}
      const pin = e.target.closest('[data-pinref]');
      const terminalPin=this.mode==='schematic'&&el&&this.spec.components.find(component=>component.ref===el.dataset.ref)?.terminal;
      if (pin&&e.button===0&&!this.panTool&&!e.altKey&&(!terminalPin||this.wiringMode)) { e.preventDefault(); this.options.onPin?.(pin.dataset.pinref,pin.dataset.anchor,[e.clientX,e.clientY]); return; }
      const sheet=e.target.closest('[data-sheet-target]');
      if(sheet&&e.button===0&&!this.panTool&&!e.altKey){
        if(this.options.readOnly||this.wiringMode){this.options.onSheetSelect?.(sheet.dataset.sheetTarget);return;}
        this.selectSheet(sheet.dataset.sheetTarget);
        drag={kind:'sheet',id:sheet.dataset.sheetTarget,el:sheet,start:this.worldPoint(e),position:[+sheet.dataset.x,+sheet.dataset.y],size:[+sheet.dataset.width,+sheet.dataset.height],resize:!!e.target.closest('.sheet-resize-handle')};
        this.interacting=true;e.preventDefault();this.svg.setPointerCapture(e.pointerId);return;
      }
      if(e.button===2)return;
      if (e.button === 1 || this.panTool || e.altKey) drag = { kind: 'pan', start: p, offset: [...this.offset] };
      else if (el) {
        const key=el.dataset.symbolKey||el.dataset.ref;
        if(e.shiftKey){this.selectedKeys.has(key)?this.selectedKeys.delete(key):this.selectedKeys.add(key);this.selectMany([...this.selectedKeys]);this.options.onSelection?.([...this.selectedKeys],key);e.preventDefault();return;}
        if(this.options.readOnly){this.options.onSelect?.(el.dataset.ref,{symbolKey:key});return;}
        if(this.wiringMode){this.options.onSelect?.(el.dataset.ref,{symbolKey:el.dataset.symbolKey||el.dataset.ref});return;}
        if(!this.selectedKeys.has(key))this.selectedKeys=new Set([key]);this.selectMany([...this.selectedKeys]);
        const c = this.spec.components.find(c => c.ref === el.dataset.ref);
        if (this.mode === 'layout' && c.placement?.locked) { this.options.onSelect?.(el.dataset.ref); this.options.onBlocked?.('Unlock this component in the Inspector before moving it.'); return; }
        const members=[...this.svg.querySelectorAll('[data-ref]')].filter(node=>this.selectedKeys.has(node.dataset.symbolKey||node.dataset.ref)).map(node=>({el:node,key:node.dataset.symbolKey||node.dataset.ref,x:+node.dataset.x,y:+node.dataset.y}));
        drag = { kind: 'part', start: p, ref: el.dataset.ref, symbolKey:key, el, x: +el.dataset.x, y: +el.dataset.y,members };
      } else {
        if(this.mode==='schematic'&&this.wiringMode&&!this.options.readOnly){const at=this.worldPoint(e);e.preventDefault();this.options.onWireBend?.([at.x,at.y]);return;}
        const net = e.target.closest('[data-net]');
        if (net){this.options.onNet?.(net.dataset.net);return;}
        const start=this.worldPoint(e),rect=document.createElementNS('http://www.w3.org/2000/svg','rect');rect.classList.add('selection-marquee');rect.setAttribute('pointer-events','none');this.scene.append(rect);
        drag={kind:'box',start,p0:start,p1:start,rect,prior:e.shiftKey?[...this.selectedKeys]:[]};
      }
      this.interacting=true;e.preventDefault(); this.svg.setPointerCapture(e.pointerId);
    });
    this.svg.addEventListener('pointermove', e => {
      if(this.wireDraft&&!this.panTool){const target=this.worldPoint(e);this.drawWireDraft(this.wireDraft.move([target.x,target.y]));}
      else if(this.wireOrigin){const target=this.worldPoint(e),mid=(this.wireOrigin.x+target.x)/2;this.wirePath.setAttribute('d',`M${this.wireOrigin.x} ${this.wireOrigin.y}H${mid}V${target.y}H${target.x}`);}
      if (!drag) return;
      if(drag.kind==='wire-node'){const at=this.worldPoint(e);drag.point=drag.position.map((v,i)=>Math.round((v+(i?at.y-drag.start.y:at.x-drag.start.x))/10)*10);if(drag.label)drag.el.setAttribute('transform',`translate(${drag.point.join(',')})`);else{drag.el.setAttribute('cx',drag.point[0]);drag.el.setAttribute('cy',drag.point[1]);}return;}
      if(drag.kind==='sheet'){
        const at=this.worldPoint(e),dx=Math.round((at.x-drag.start.x)/10)*10,dy=Math.round((at.y-drag.start.y)/10)*10;
        drag.moved=Math.abs(dx)+Math.abs(dy);
        if(drag.resize){
          const minimum=this.options.nativeScene.sheet_nodes.find(node=>node.target===drag.id)?.minimum_size||[60,60];
          drag.patch={size:[Math.min(10000,Math.max(Math.ceil(minimum[0]/10)*10,drag.size[0]+dx)),Math.min(10000,Math.max(Math.ceil(minimum[1]/10)*10,drag.size[1]+dy))]};
          const[w,h]=drag.patch.size;drag.el.querySelector('.sheet-boundary').setAttribute('width',w);drag.el.querySelector('.sheet-boundary').setAttribute('height',h);drag.el.querySelector('.sheet-resize-handle').setAttribute('x',w-5);drag.el.querySelector('.sheet-resize-handle').setAttribute('y',h-5);for(const port of drag.el.querySelectorAll('[data-boundary-side]'))port.setAttribute('transform',`translate(${port.dataset.boundarySide==='right'?w-drag.size[0]:0},${port.dataset.boundarySide==='bottom'?h-drag.size[1]:0})`);
        }else{drag.patch={position:[drag.position[0]+dx,drag.position[1]+dy]};drag.el.setAttribute('transform',`translate(${drag.patch.position.join(',')})`);}
        return;
      }
      if(drag.kind==='wire'){
        const at=this.worldPoint(e),k=drag.segment,original=drag.route.points,horizontal=Math.abs(original[k][1]-original[k+1][1])<.001,axis=horizontal?1:0;
        drag.points=structuredClone(original);const value=Math.round((original[k][axis]+(horizontal?at.y-drag.start.y:at.x-drag.start.x))/10)*10;
        drag.points[k][axis]=value;drag.points[k+1][axis]=value;drag.moved=Math.abs(value-original[k][axis]);
        if(!drag.preview){drag.preview=document.createElementNS('http://www.w3.org/2000/svg','path');drag.preview.classList.add('wire-edit-preview');drag.preview.setAttribute('fill','none');drag.preview.setAttribute('stroke','#1dfdc0');drag.preview.setAttribute('stroke-width','2');drag.preview.setAttribute('pointer-events','none');this.scene.append(drag.preview);}
        drag.preview.setAttribute('d','M'+drag.points.map(p=>p.join(' ')).join('L'));return;
      }
      if(drag.kind==='box'){drag.p1=this.worldPoint(e);for(const [key,value]of Object.entries({x:Math.min(drag.p0.x,drag.p1.x),y:Math.min(drag.p0.y,drag.p1.y),width:Math.abs(drag.p1.x-drag.p0.x),height:Math.abs(drag.p1.y-drag.p0.y)}))drag.rect.setAttribute(key,value);return;}
      const p = this.point(e), dx = (p.x - drag.start.x) / this.zoom, dy = (p.y - drag.start.y) / this.zoom;
      if (drag.kind === 'pan') { this.offset = [drag.offset[0] + dx * this.zoom, drag.offset[1] + dy * this.zoom]; this.applyTransform(); }
      else { drag.dx = dx; drag.dy = dy;for(const member of drag.members)member.el.setAttribute('transform', `translate(${member.x + dx},${member.y + dy})`);this.drawConnections(); }
    });
    const end = event => {
      if(drag?.kind==='wire-node'){const moved=drag.point&&drag.point.some((v,i)=>Math.abs(v-drag.position[i])>1);this.options.onWireNodeSelect?.(drag.id);if(moved)this.options.onWireNodeMove?.(drag.id,drag.point);}
      if(drag?.kind==='sheet'){
        const sheet=drag;drag=null;this.interacting=false;
        if(!sheet.moved&&this.sheetTap?.id===sheet.id&&Date.now()-this.sheetTap.time<450){this.sheetTap=null;this.options.onSheet?.(sheet.id);return;}
        this.sheetTap=sheet.moved?null:{id:sheet.id,time:Date.now(),point:[event.clientX,event.clientY]};
        this.options.onSheetSelect?.(sheet.id);if(sheet.moved>2)this.options.onSheetChange?.(sheet.id,sheet.patch);this.options.onIdle?.();return;
      }
      if(drag?.kind==='wire'){const wire=drag;drag=null;wire.preview?.remove();if(wire.moved>1)this.options.onWireReshape?.(wire.route.index,wire.points.slice(1,-1));this.interacting=false;this.drawConnections();this.options.onIdle?.();return;}
      if(drag?.kind==='box'){
        const x0=Math.min(drag.p0.x,drag.p1.x),y0=Math.min(drag.p0.y,drag.p1.y),x1=Math.max(drag.p0.x,drag.p1.x),y1=Math.max(drag.p0.y,drag.p1.y),keys=[...drag.prior];
        if(Math.hypot(x1-x0,y1-y0)>4)for(const el of this.svg.querySelectorAll('[data-ref]')){const b=el.getBBox(),x=+el.dataset.x+b.x,y=+el.dataset.y+b.y;if(x<=x1&&x+b.width>=x0&&y<=y1&&y+b.height>=y0)keys.push(el.dataset.symbolKey||el.dataset.ref);}
        drag.rect.remove();this.selectMany([...new Set(keys)]);this.options.onSelection?.([...this.selectedKeys]);
      }
      if (drag?.kind === 'part') this.options.onSelect?.(drag.ref,{symbolKey:drag.symbolKey,selection:[...this.selectedKeys]});
      if (drag?.kind === 'part' && (Math.abs(drag.dx || 0) + Math.abs(drag.dy || 0) > 2)) {
        let x = drag.x + (drag.dx || 0), y = drag.y + (drag.dy || 0);
        if (this.mode === 'layout') { x = Math.max(0, Math.min(this.spec.board.width_mm, (x - this.layout.x) / this.layout.scale)); y = Math.max(0, Math.min(this.spec.board.height_mm, (y - this.layout.y) / this.layout.scale)); }
        else { x = Math.round(x / 10) * 10; y = Math.round(y / 10) * 10; }
        if(this.options.onMoveMany){const dx=this.mode==='layout'?(x-(drag.x-this.layout.x)/this.layout.scale)*this.layout.scale:x-drag.x,dy=this.mode==='layout'?(y-(drag.y-this.layout.y)/this.layout.scale)*this.layout.scale:y-drag.y;const moves=drag.members.map(m=>({key:m.key,x:this.mode==='layout'?(m.x+dx-this.layout.x)/this.layout.scale:m.x+dx,y:this.mode==='layout'?(m.y+dy-this.layout.y)/this.layout.scale:m.y+dy}));this.options.onMoveMany(moves,this.mode);}
        else this.options.onMove?.(drag.ref, x, y, this.mode, drag.symbolKey);
      }
      drag = null;
      this.interacting=false;this.drawConnections();this.options.onIdle?.();
    };
    this.svg.addEventListener('pointerup', end); this.svg.addEventListener('pointercancel',()=>{if(drag?.kind==='wire-node'){if(drag.label)drag.el.setAttribute('transform',`translate(${drag.position.join(',')})`);else{drag.el.setAttribute('cx',drag.position[0]);drag.el.setAttribute('cy',drag.position[1]);}}if(drag?.kind==='part')for(const member of drag.members)member.el.setAttribute('transform',`translate(${member.x},${member.y})`);if(drag?.kind==='sheet'){drag.el.setAttribute('transform',`translate(${drag.position.join(',')})`);const[w,h]=drag.size;drag.el.querySelector('.sheet-boundary').setAttribute('width',w);drag.el.querySelector('.sheet-boundary').setAttribute('height',h);drag.el.querySelector('.sheet-resize-handle').setAttribute('x',w-5);drag.el.querySelector('.sheet-resize-handle').setAttribute('y',h-5);for(const port of drag.el.querySelectorAll('[data-boundary-side]'))port.removeAttribute('transform');}drag?.rect?.remove();drag?.preview?.remove();drag=null;this.interacting=false;this.drawConnections();this.options.onIdle?.();});
    this.svg.addEventListener('dblclick',e=>{if(this.mode==='schematic'&&!this.options.readOnly&&!this.panTool&&!e.target.closest('[data-ref],[data-sheet-target],[data-pinref],[data-wire-route],[data-wire-node]')){e.preventDefault();const at=this.worldPoint(e);this.options.onWireCanvasDoubleClick?.([at.x,at.y]);}});
    this.sheetDoubleClick=e=>{
      const sheet=e.target.closest('[data-sheet-target]'),tap=this.sheetTap;
      // Opening Inspect can resize the viewport between the two clicks. Pointer
      // capture also retargets a click to the SVG, so retain the first sheet hit.
      const retained=tap&&Date.now()-tap.time<450&&Math.hypot(e.clientX-tap.point[0],e.clientY-tap.point[1])<8;
      if(sheet&&this.svg.contains(sheet)&&this.options.readOnly||retained){e.preventDefault();this.sheetTap=null;this.options.onSheet?.(retained?tap.id:sheet.dataset.sheetTarget);}
    };
    document.addEventListener('dblclick',this.sheetDoubleClick);
    this.svg.addEventListener('keydown',e=>{const sheet=e.target.closest('[data-sheet-target]');if(sheet&&e.key==='Enter'){e.preventDefault();this.options.onSheet?.(sheet.dataset.sheetTarget);}});
    this.svg.addEventListener('keydown', e => { const el = e.target.closest('[data-ref]'); if (el && ['Enter', ' '].includes(e.key)) { e.preventDefault(); this.options.onSelect?.(el.dataset.ref); } });
    this.svg.addEventListener('wheel', e => { e.preventDefault(); this.setZoom(this.zoom * Math.exp(-e.deltaY * .0015)); }, { passive: false });
  }
  select(ref,options={}) {
    this.options.selected = ref;
    this.options.selectedKey=options.symbolKey||ref;
    this.selectMany(ref?[options.symbolKey||ref]:[]);
  }
  selectMany(keys){this.selectedKeys=new Set(keys);for(const el of this.svg.querySelectorAll('[data-ref]'))el.classList.toggle('selected',this.selectedKeys.has(el.dataset.symbolKey||el.dataset.ref));}
  selectSheet(id){this.options.selectedSheet=id;for(const el of this.svg.querySelectorAll('[data-sheet-target]'))el.classList.toggle('selected',el.dataset.sheetTarget===id);}
  selectWire(index){this.options.selectedWire=index;this.drawConnections();}
  setObjects(objects){this.objectSelections=objects;this.drawConnections();}
  _applyObjects(){
    const visible=(kind,key)=>this.options.isObjectVisible?.(kind,key)!==false;
    for(const element of this.svg.querySelectorAll('[data-ref]'))element.style.display=visible('symbol',element.dataset.symbolKey||element.dataset.ref)?'':'none';
    for(const element of this.svg.querySelectorAll('[data-sheet-target]'))element.style.display=visible('sheet',element.dataset.sheetTarget)?'':'none';
    for(const element of this.svg.querySelectorAll('[data-wire-node]'))element.style.display=visible('node',element.dataset.wireNode)?'':'none';
    this.svg.querySelectorAll('[data-object-selected]').forEach(element=>delete element.dataset.objectSelected);this.scene.querySelector('[data-object-highlight]')?.remove();
    const highlight=document.createElementNS('http://www.w3.org/2000/svg','g');highlight.dataset.objectHighlight='';highlight.setAttribute('pointer-events','none');
    for(const object of this.objectSelections||[]){const target=object.target;
      if(['component','symbol'].includes(object.kind))for(const element of this.svg.querySelectorAll('[data-ref]'))if(element.dataset.ref===object.ref&&(!target?.symbolKey||element.dataset.symbolKey===target.symbolKey))element.dataset.objectSelected='true';
      if(object.kind==='sheet')for(const element of this.svg.querySelectorAll('[data-sheet-target]'))if(element.dataset.sheetTarget===target?.id)element.dataset.objectSelected='true';
      if(['node','label'].includes(object.kind))for(const element of this.svg.querySelectorAll('[data-wire-node]'))if(element.dataset.wireNode===target?.id)element.dataset.objectSelected='true';
      if(object.kind==='net')for(const element of this.svg.querySelectorAll('.native-schematic-wire'))if(element.dataset.net===object.net)element.setAttribute('stroke','#1dfdc0');
      if(object.kind==='wire'){
        const route=this.options.nativeScene?.routes?.find(r=>r.index===target?.index&&r.sheet===(this.options.sheet||''));if(!route?.points?.length||!visible('wire',target.id))continue;
        const path=document.createElementNS('http://www.w3.org/2000/svg','path');path.setAttribute('d','M'+route.points.map(p=>p.join(' ')).join('L'));path.setAttribute('fill','none');path.setAttribute('stroke','#1dfdc0');path.setAttribute('stroke-width','1.8');highlight.append(path);
      }
    }
    this.scene.append(highlight);
  }
  worldPoint(event){const p=this.svg.createSVGPoint();p.x=event.clientX;p.y=event.clientY;return p.matrixTransform(this.scene.getScreenCTM().inverse());}
  pinLocation(anchor){const pin=[...this.svg.querySelectorAll('[data-pinref]')].find(p=>p.dataset.anchor===anchor||p.dataset.pinref===anchor);if(!pin)return null;const p=this.svg.createSVGPoint();p.x=pin.cx.baseVal.value;p.y=pin.cy.baseVal.value;return p.matrixTransform(pin.getScreenCTM()).matrixTransform(this.scene.getScreenCTM().inverse());}
  startWire(anchor){const point=this.pinLocation(anchor);if(point)this.startWirePoint([point.x,point.y]);}
  startWirePoint(point){this.clearWire();this.wireOrigin={x:point[0],y:point[1]};this.wirePath=document.createElementNS('http://www.w3.org/2000/svg','path');this.wirePath.setAttribute('stroke','#1dfdc0');this.wirePath.setAttribute('fill','none');this.wirePath.setAttribute('stroke-width','1.6');this.wirePath.setAttribute('stroke-dasharray','5 4');this.wirePath.setAttribute('pointer-events','none');this.scene.append(this.wirePath);}
  setWireDraft(draft){
    this.startWirePoint(draft.points[0]);this.wireDraft=draft;this.wirePath.classList.add('schematic-wire-draft');this.drawWireDraft();
    this.wireHint=document.createElement('div');this.wireHint.className='schematic-wire-hint';
    this.wireHint.textContent='Click to add a bend · Double-click to finish · F flip · Backspace undo · Esc cancel';this.host.append(this.wireHint);
  }
  drawWireDraft(points=this.wireDraft?.preview()){
    if(!this.wirePath||!points)return;
    this.wirePath.setAttribute('d','M'+points.map(p=>p.join(' ')).join('L'));this.wirePath.dataset.points=JSON.stringify(this.wireDraft.points);
  }
  clearWire(){this.wireDraft=null;this.wireOrigin=null;this.wirePath?.remove();this.wirePath=null;this.wireHint?.remove();this.wireHint=null;}
  drawConnections(){
    this.connectionPaths?.remove();this.wireControls?.remove();this.connectionPaths=document.createElementNS('http://www.w3.org/2000/svg','g');
    this.connectionPaths.classList.add('schematic-connections');
    const native=this.options.nativeScene,sheet=this.options.sheet||'';
    if(native&&!this.interacting){
      const visible=(kind,key)=>this.options.isObjectVisible?.(kind,key)!==false;
      const routeVisible=r=>visible('wire',guideIdentity(this.spec.editor?.connection_guides?.[r.index]||{}));
      const segments=displayedWires(native,this.spec,sheet,visible);
      this.connectionPaths.innerHTML=segments.map(w=>`<path class="native-schematic-wire" data-net="${esc(w.net)}" d="M${w.points.map(p=>p.join(' ')).join('L')}" fill="none" stroke="${esc(this.options.netColors?.[w.net]||'#8bb59a')}" stroke-width="1.4" pointer-events="none"/>`).join('');
      for(const route of (native.routes||[]).filter(r=>r.sheet===sheet&&r.status==='routed'&&routeVisible(r))){
        const hit=document.createElementNS('http://www.w3.org/2000/svg','path');hit.setAttribute('d','M'+route.points.map(p=>p.join(' ')).join('L'));hit.setAttribute('stroke','transparent');hit.setAttribute('stroke-width','9');hit.setAttribute('fill','none');hit.setAttribute('pointer-events','stroke');hit.dataset.net=route.net;hit.dataset.wireRoute=route.index;this.connectionPaths.append(hit);
      }
      for(const junction of (native.junctions||[]).filter(j=>j.sheet===sheet)){
        const dot=document.createElementNS('http://www.w3.org/2000/svg','circle');dot.classList.add('native-junction');dot.setAttribute('cx',junction.position[0]);dot.setAttribute('cy',junction.position[1]);dot.setAttribute('r',junction.diameter/2);dot.setAttribute('fill','#8bb59a');dot.setAttribute('pointer-events','none');this.connectionPaths.append(dot);
      }
      const selected=(native.routes||[]).find(r=>r.index===this.options.selectedWire&&r.sheet===sheet&&routeVisible(r));
      if(selected?.status==='routed'){
        const outline=document.createElementNS('http://www.w3.org/2000/svg','path');outline.setAttribute('d','M'+selected.points.map(p=>p.join(' ')).join('L'));outline.setAttribute('stroke','#1dfdc0');outline.setAttribute('stroke-width','1.8');outline.setAttribute('fill','none');outline.setAttribute('pointer-events','none');this.connectionPaths.append(outline);
        this.wireControls=document.createElementNS('http://www.w3.org/2000/svg','g');this.wireControls.classList.add('wire-controls');
        if(!this.options.readOnly&&!this.wiringMode)for(let k=1;k<selected.points.length-2;k++){
          const a=selected.points[k],b=selected.points[k+1];if(Math.hypot(a[0]-b[0],a[1]-b[1])<8)continue;
          const handle=document.createElementNS('http://www.w3.org/2000/svg','rect');handle.classList.add('wire-segment-handle');handle.setAttribute('x',(a[0]+b[0])/2-4);handle.setAttribute('y',(a[1]+b[1])/2-4);handle.setAttribute('width',8);handle.setAttribute('height',8);handle.setAttribute('fill','#101010');handle.setAttribute('stroke','#1dfdc0');handle.setAttribute('stroke-width','1.5');handle.dataset.wireSegment=k;handle.dataset.wireIndex=selected.index;handle.style.cursor=Math.abs(a[1]-b[1])<.001?'ns-resize':'ew-resize';this.wireControls.append(handle);
        }
      }
      for(const route of (native.routes||[]).filter(r=>r.sheet===sheet&&r.status!=='routed'&&r.points?.length&&routeVisible(r))){
        const guide=document.createElementNS('http://www.w3.org/2000/svg','path');guide.classList.add('unresolved-wire');guide.setAttribute('d','M'+route.points.map(p=>p.join(' ')).join('L'));guide.setAttribute('stroke','#d4ac72');guide.setAttribute('stroke-width','1.4');guide.setAttribute('stroke-dasharray','5 4');guide.setAttribute('fill','none');guide.dataset.net=route.net;guide.dataset.wireRoute=route.index;const title=document.createElementNS('http://www.w3.org/2000/svg','title');title.textContent=route.reason||'Connection retained through net labels';guide.append(title);this.connectionPaths.append(guide);
      }
      for(const node of (native.wire_nodes||[]).filter(n=>(n.sheet||'')===sheet&&visible('node',n.id))){
        if(node.label){const group=document.createElementNS('http://www.w3.org/2000/svg','g');group.innerHTML=nativeNetLabel(node,(native.label_symbols||[]).find(s=>s.id===node.id),native.definitions,native.mm_per_unit,native.origin_mm,this.options.selectedWireNode===node.id);this.connectionPaths.append(group.firstElementChild);continue;}
        const dot=document.createElementNS('http://www.w3.org/2000/svg','circle');dot.classList.add('schematic-wire-node');dot.dataset.wireNode=node.id;dot.setAttribute('cx',node.position[0]);dot.setAttribute('cy',node.position[1]);dot.setAttribute('r',this.options.selectedWireNode===node.id?5:3.5);dot.setAttribute('fill','#111');dot.setAttribute('stroke','#8bb59a');dot.setAttribute('stroke-width','1.5');dot.setAttribute('pointer-events','all');dot.style.cursor=this.wiringMode?'crosshair':'move';const title=document.createElementNS('http://www.w3.org/2000/svg','title');title.textContent='Wire endpoint · '+node.net;dot.append(title);this.connectionPaths.append(dot);
      }
      this.scene.prepend(this.connectionPaths);if(this.wireControls)this.scene.append(this.wireControls);this._applyObjects();return;
    }
    this.connectionPaths.setAttribute('pointer-events','none');const nets=pinIndex(this.spec);
    for(const guide of this.spec.editor?.connection_guides||[]){
      const logical=p=>p.replace(/#\d+(?=\.)/,'');if(!nets[logical(guide.from)]||nets[logical(guide.from)]!==nets[logical(guide.to)])continue;
      const a=this.pinLocation(guide.from),b=this.pinLocation(guide.to);if(!a||!b)continue;
      const path=document.createElementNS('http://www.w3.org/2000/svg','path');path.setAttribute('d',`M${a.x} ${a.y}H${(a.x+b.x)/2}V${b.y}H${b.x}`);path.setAttribute('fill','none');path.setAttribute('stroke','#6b9b7d');path.setAttribute('stroke-width','1.3');path.setAttribute('stroke-dasharray','4 4');path.setAttribute('opacity','.7');this.connectionPaths.append(path);
    }
    this.scene.prepend(this.connectionPaths);this._applyObjects();
  }
  setZoom(value) { this.zoom = Math.max(.25, Math.min(5, value)); this.applyTransform(); this.options.onZoom?.(this.zoom); }
  applyTransform() {const x=(this.frame?.x||0)+this.extent[0]/2,y=(this.frame?.y||0)+this.extent[1]/2;this.scene?.setAttribute('transform',`translate(${x+this.offset[0]},${y+this.offset[1]}) scale(${this.zoom}) translate(${-x},${-y})`);this.camera=this.getCamera();}
  getCamera(){
    const matrix=this.scene?.getScreenCTM();if(!matrix||!Math.hypot(matrix.a,matrix.b))return null;
    const box=this.svg.getBoundingClientRect(),point=this.svg.createSVGPoint();point.x=box.x+box.width/2;point.y=box.y+box.height/2;
    const center=point.matrixTransform(matrix.inverse());return{kind:this.mode,center:[center.x,center.y],scale:Math.hypot(matrix.a,matrix.b)};
  }
  setCamera(camera){
    const base=this.svg?.getScreenCTM();if(camera?.kind!==this.mode||!base||!Math.hypot(base.a,base.b))return;
    const x=(this.frame?.x||0)+this.extent[0]/2,y=(this.frame?.y||0)+this.extent[1]/2;
    this.zoom=camera.scale/Math.hypot(base.a,base.b);this.offset=[(x-camera.center[0])*this.zoom,(y-camera.center[1])*this.zoom];this.applyTransform();this.options.onZoom?.(this.zoom);
  }
  revealSelection(){
    const selected=[...this.svg.querySelectorAll('[data-ref]')].find(el=>(el.dataset.symbolKey||el.dataset.ref)===(this.options.selectedKey||this.options.selected));if(!selected)return;
    const view=this.svg.getBoundingClientRect(),box=selected.getBoundingClientRect(),x=box.x+box.width/2,y=box.y+box.height/2,dx=Math.max(view.left+35,Math.min(view.right-35,x))-x,dy=Math.max(view.top+35,Math.min(view.bottom-35,y))-y,base=this.svg.getScreenCTM();
    if((dx||dy)&&base?.a){this.offset[0]+=dx/base.a;this.offset[1]+=dy/base.a;this.applyTransform();}
  }
  fit() { this.offset = [0, 0]; this.setZoom(1); }
  fitSelection(){const elements=[...this.svg.querySelectorAll('[data-ref]')],el=elements.find(e=>e.dataset.symbolKey===this.options.selectedKey)||elements.find(e=>e.dataset.ref===this.options.selected);if(!el){this.fit();return;}const box=el.getBBox(),x=+el.dataset.x+box.x+box.width/2,y=+el.dataset.y+box.y+box.height/2,z=Math.min(5,this.extent[0]/(box.width+60),this.extent[1]/(box.height+60)),cx=(this.frame?.x||0)+this.extent[0]/2,cy=(this.frame?.y||0)+this.extent[1]/2;this.offset=[(cx-x)*z,(cy-y)*z];this.setZoom(z);}
  grid(show) { this.showGrid = show; this.svg.querySelector('.grid-background').setAttribute('opacity', show ? '.6' : '0'); }
  destroy() {this.ro?.disconnect();document.removeEventListener('dblclick',this.sheetDoubleClick);}
}

function cuboid(name, x, y, z, w, h, d, color, group) {
  return { name, color, group, v: [x,y,z,x+w,y,z,x+w,y+h,z,x,y+h,z,x,y,z+d,x+w,y,z+d,x+w,y+h,z+d,x,y+h,z+d], t: [0,2,1,0,3,2,4,5,6,4,6,7,0,1,5,0,5,4,1,2,6,1,6,5,2,3,7,2,7,6,3,0,4,3,4,7] };
}

export function conceptMeshes(spec, enclosure = false) {
  const w = Number(spec.board.width_mm), h = Number(spec.board.height_mm), off = enclosure ? 5 : 0, z = enclosure ? 4 : 0;
  const meshes = [cuboid('PCB', off, off, z, w, h, 1.6, '#236f51', 'board')];
  for (const [i, c] of spec.components.entries()) {
    const p = c.placement || {}, x = p.x_mm ?? (w * (.2 + i % 4 * .2)), y = p.y_mm ?? (h * (.2 + Math.floor(i / 4) * .2));
    const metal = c.ref.startsWith('J'), passive = /^[RCD]/.test(c.ref), sw = metal ? 6 : passive ? 1.7 : 5.8, sh = metal ? 5 : passive ? .9 : 6, sz = metal ? 3.2 : passive ? .7 : 1.9;
    meshes.push(cuboid(c.ref, off + x - sw/2, off + y - sh/2, z + 1.6, sw, sh, sz, metal ? '#b1b6b6' : c.ref.startsWith('C') ? '#aa8755' : '#303331', 'board'));
    if (!metal) for (const side of [-1, 1]) meshes.push(cuboid(c.ref + ' pad', off+x+side*sw/2-.2, off+y-sh/2, z+1.6, .4, sh, .2, '#c9b77d', 'board'));
  }
  if (enclosure) {
    meshes.unshift(cuboid('Base',0,0,0,w+10,h+10,2,'#c2c7c4','base'));
    meshes.push(cuboid('Back',0,h+8,2,w+10,2,14,'#b8bfbb','base'), cuboid('Right',w+8,0,2,2,h+10,14,'#b8bfbb','base'));
    meshes.push(cuboid('Front left',0,0,2,5,2,14,'#b8bfbb','base'), cuboid('Front',5,0,2,w+5,2,14,'#b8bfbb','base'));
    meshes.push(cuboid('Left bottom',0,2,2,2,h/2-4,14,'#b8bfbb','base'), cuboid('Left top',0,h/2+7,2,2,h/2+1,14,'#b8bfbb','base'));
    meshes.push(cuboid('Lid',0,0,16,w+10,h+10,2,'#d9dedb','lid'));
    for (const [x,y] of [[4,4],[w+6,4],[4,h+6],[w+6,h+6]]) meshes.push(cuboid('Standoff',x-1.4,y-1.4,2,2.8,2.8,2,'#aab4ad','base'));
  }
  return { size: [w + off*2, h + off*2, enclosure ? 18 : 6], meshes };
}
