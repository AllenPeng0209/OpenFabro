import {esc,icon} from './workbench-icons.mjs';
import {CADPreferences} from './workbench-cad-model.mjs';
import {curvatureComb,curvatureEvents} from './workbench-curve-analysis.mjs';
import {surfaceSummary} from './workbench-surface-analysis.mjs';

// These settings affect the loaded preview, never the saved CAD source.
export class CADViewUI{
 constructor({state,toast,interacting=()=>false}){Object.assign(this,{state,toast,interacting});this.preferences=new CADPreferences({toast});this.orbits=new Map();this.expanded=new Map();this.mountSequence=0;}
 user(){const s=this.state();return s.session?.user?.id||s.project.access?.user?.id||'device';}
 key(){return this.preferences.key(this.user(),this.state().pid);}
 sync(){const key=this.key();if(this.owner!==key){this.owner=key;this.settings=this.preferences.load(this.user(),this.state().pid);}}
 ready(gpu=false){const s=this.state();return s.active==='3d'&&!!s.pid&&!s.starting&&!s.openingProject&&s.canvas?.is3D&&s.canvas.canvas?.isConnected&&(!gpu||!!s.canvas.renderer)&&!this.interacting();}
 capture(view){if(!view?.is3D||!view.displayOwner)return;this.orbits.delete(view.displayOwner);this.orbits.set(view.displayOwner,{renderer:view.renderer?'gpu':'software',yaw:view.yaw,pitch:view.pitch,roll:view.roll||0,zoom:view.zoom,explode:view.explode,pan:Array.isArray(view.pan)?[...view.pan]:view.pan?.toArray()});while(this.orbits.size>128)this.orbits.delete(this.orbits.keys().next().value);}
 attach(view){
  this.sync();if(view.displayOwner&&view.displayOwner!==this.owner)this.capture(view);
  view.displayOwner=this.owner;view.yaw=-.7;view.pitch=.75;view.roll=0;view.zoom=1;view.explode=.6;if(Array.isArray(view.pan))view.pan.fill(0);else view.pan?.set(0,0,0);
  view.measureMode=false;this.clearMeasurement(view);
  const orbit=this.orbits.get(this.owner);if(orbit){for(const k of ['yaw','pitch','roll','zoom','explode'])if(Number.isFinite(orbit[k]))view[k]=orbit[k];if(orbit.pan&&view.pan&&orbit.renderer===(view.renderer?'gpu':'software')){if(Array.isArray(view.pan))view.pan.splice(0,3,...orbit.pan);else view.pan.fromArray(orbit.pan);}}
  this.apply(view);view.options?.onZoom?.(view.zoom);
 }
 clearMeasurement(view){view.measurePoints=[];view._measurement?.();document.querySelector('#measureResult')?.remove();}
 apply(view=this.state().canvas){
  this.sync();const active=this.state().active==='3d';document.querySelector('#canvasBottom')?.classList.toggle('cad-shortcuts-hidden',active&&!this.settings.shortcutBar);
  if(!active||!view?.is3D)return;
  if(view.displayOwner!==this.owner){this.attach(view);return;}
  const p=this.settings;view.show={...view.show,...Object.fromEntries(['board','parts','base','lid','top','bottom'].map(k=>[k,p[k]]))};view.showGrid=p.grid;
  view.show.base=!!this.state().enclosure&&p.base;view.show.lid=!!this.state().enclosure&&p.lid;
  if(view.renderer){view.style=p.style;view.projection=p.projection;view.sectionAxis=p.sectionAxis;const axis=['x','y','z'].indexOf(p.sectionAxis);view.sectionDepth=axis<0?0:p.sectionRatio*view.data.size[axis];view.curvature={enabled:p.comb,gain:p.combGain,density:p.combDensity,inflections:p.combInflections,jumps:p.combJumps};}
  if(view.renderer)view.surface={mode:p.surfaceMode,metric:p.surfaceMetric,range:p.surfaceRange,density:p.zebraDensity,angle:p.zebraAngle};
  view.draw();this.syncSlider(view);this.update();
 }
 change(patch,gpu=false){this.sync();if(!this.ready(gpu))return;if(['top','bottom','board','parts','base','lid','sectionAxis','sectionRatio'].some(k=>Object.hasOwn(patch,k)))this.clearMeasurement(this.state().canvas);this.settings=this.preferences.save(this.user(),this.state().pid,{...this.settings,...patch});this.apply();}
 toggle(key,gpu=false){this.change({[key]:!this.settings[key]},gpu);}
 heading(key,label){const open=this.expanded.get(key)!==false;return`<button type="button" class="display-section-heading" data-cad-section="${key}" aria-expanded="${open}"><strong>${esc(label)}</strong>${icon('chevronDown')}</button>`;}
 section(key,label,body){return`<section class="cad-view-section">${this.heading(key,label)}<div class="cad-section-body" data-cad-body="${key}" ${this.expanded.get(key)===false?'hidden':''}>${body}</div></section>`;}
 row(key,label,glyph='cube'){return`<button type="button" class="schematic-display-row" data-cad-toggle="${key}" aria-label="${esc(label)}" aria-pressed="${this.settings[key]}"><span class="display-row-icon">${icon(glyph)}</span><span>${esc(label)}</span><span class="display-row-check" ${this.settings[key]?'':'hidden'}>${icon('check')}</span></button>`;}
 curvaturePanel(){return`<div class="cad-curve-analysis"><button type="button" class="schematic-display-row" id="cadCurvatureComb" aria-label="Curvature combs" aria-pressed="${this.settings.comb}">${icon('ruler')}<span>Curvature combs</span></button><label class="cad-depth-row"><span>Comb length</span><input id="cadCombGain" type="range" aria-label="Comb length" min="0" max="200" step="1" title="Visual gain: mm² × native curvature in 1/mm"><output id="cadCombGainValue"></output></label><label class="cad-camera-row"><span>Line density</span><select id="cadCombDensity" aria-label="Line density"><option value="1">Full</option><option value="2">Half</option><option value="4">Quarter</option><option value="8">Eighth</option><option value="16">Sparse</option></select></label><p class="cad-view-note" id="cadCombStatus" role="status"></p><p class="cad-view-note">Native edge curves · 1/mm. Display scale only. Samples do not establish surface continuity or rule out inflections and jumps.</p></div>`;}
 surfacePanel(){return`<div class="cad-surface-analysis"><label class="cad-camera-row"><span>Surface continuity</span><select id="cadSurfaceMode" aria-label="Surface continuity"><option value="off">Off</option><option value="zebra">Zebra stripes</option><option value="curvature">Curvature</option></select></label><div id="cadZebraControls"><label class="cad-depth-row"><span>Stripe density</span><input id="cadZebraDensity" type="range" min="2" max="64" step="1" aria-label="Stripe density"><output id="cadZebraDensityValue"></output></label><label class="cad-depth-row"><span>Stripe angle</span><input id="cadZebraAngle" type="range" min="-180" max="180" step="1" aria-label="Stripe angle"><output id="cadZebraAngleValue"></output></label></div><div id="cadSurfaceCurvatureControls"><label class="cad-camera-row"><span>Curvature</span><select id="cadSurfaceMetric" aria-label="Surface curvature metric">${[['max_abs','Max magnitude'],['mean','Mean'],['gaussian','Gaussian'],['min','Minimum'],['max','Maximum']].map(([key,name])=>`<option value="${key}">${name}</option>`).join('')}</select></label><label class="cad-camera-row"><span>Color range</span><input id="cadSurfaceRange" type="number" min="0.001" max="10000" step="any" aria-label="Curvature color range"></label><div id="cadSurfaceLegend" class="cad-surface-legend" role="status"></div></div><p class="cad-view-note" id="cadSurfaceStatus" role="status"></p><p class="cad-view-note">Native surface samples. Gray marks unavailable values. Visual inspection does not prove continuity. Off restores the material display.</p></div>`;}
 eventPanel(){return`<div class="cad-curve-event-controls"><button type="button" class="schematic-display-row" id="cadInflections" aria-label="Inflections" aria-pressed="${this.settings.combInflections}"><span class="cad-event-dot inflection-dot"></span><span>Inflections</span></button><button type="button" class="schematic-display-row" id="cadCurvatureJumps" aria-label="Curvature jumps" aria-pressed="${this.settings.combJumps}"><span class="cad-event-dot jump-dot"></span><span>Curvature jumps</span></button><p class="cad-view-note" id="cadCurveEventStatus" role="status"></p><p class="cad-view-note">Planar native curve roots and one-sided limits. Corners and singularities are separate. Unsupported curves remain unknown.</p></div>`;}
 panel(){
  this.sync();const s=this.state(),fallback=s.canvas?.is3D&&!s.canvas.renderer,unmatched=s.canvas?.data?.meshes.filter(m=>m.group==='parts'&&!m.side).length||0;
  return`<div class="cad-view-controls">`+
   this.section('camera','Camera',`<label class="cad-camera-row"><span>Material</span><select id="cadStyle" aria-label="Material">${[['blueprint','Blueprint'],['xray','X-ray'],['solid','Solid'],['realistic','Realistic']].map(([value,name])=>`<option value="${value}">${name}</option>`).join('')}</select></label><label class="cad-camera-row"><span>Projection</span><select id="cadProjection" aria-label="Projection"><option value="perspective">Perspective</option><option value="orthographic">Orthographic</option></select></label>`)+
   this.section('layers','Layers',this.row('top','Top 3D models')+this.row('bottom','Bottom 3D models')+(unmatched?`<p class="cad-view-note">${unmatched} unassigned model${unmatched===1?'':'s'} remain visible when hiding a side.</p>`:''))+
   this.section('analysis','Analysis',`<label class="cad-camera-row"><span>Section</span><select id="cadSection" aria-label="Cross section"><option value="none">Off</option><option value="x">X axis</option><option value="y">Y axis</option><option value="z">Z axis</option></select></label><label class="cad-depth-row"><span>Section position</span><input id="cadDepth" type="range" aria-label="Section position" min="0" max="1" step="0.01"><output id="cadDepthValue"></output></label><button type="button" class="schematic-display-row" id="cadMeasure" aria-pressed="${!!s.canvas?.measureMode}">${icon('ruler')}<span>Measure distance</span></button>${this.surfacePanel()}${this.curvaturePanel()}${this.eventPanel()}`)+
   this.section('display','Display',this.row('grid','Grid','grid')+this.row('shortcutBar','Keyboard shortcut bar','keyboard'))+
   `<details class="cad-extra"><summary>Assembly controls</summary>${this.row('board','Board')+this.row('parts','Components')+(s.enclosure?this.row('base','Enclosure base')+this.row('lid','Enclosure lid'):'')}<button type="button" class="schematic-display-row" id="cadFit">${icon('frame')}<span>Frame model</span></button></details>${fallback?'<p class="cad-view-note" role="status">Software preview: GPU materials, projection, grid, clipping and measurement are unavailable.</p>':''}</div>`;
 }
 mount(host){
  this.host=host;this.mountOwner=this.owner;
  const sequence=++this.mountSequence,valid=()=>sequence===this.mountSequence&&this.host===host&&this.validHost();
  for(const b of host.querySelectorAll('[data-cad-toggle]'))b.onclick=()=>{if(valid())this.toggle(b.dataset.cadToggle,b.dataset.cadToggle==='grid');};
  for(const b of host.querySelectorAll('[data-cad-section]'))b.onclick=()=>{if(!valid())return;const key=b.dataset.cadSection,open=this.expanded.get(key)===false;this.expanded.set(key,open);b.setAttribute('aria-expanded',String(open));host.querySelector(`[data-cad-body="${key}"]`).hidden=!open;};
  const select=(id,key)=>{host.querySelector('#'+id).onchange=e=>{if(valid())this.change({[key]:e.target.value},true);};};select('cadStyle','style');select('cadProjection','projection');select('cadSection','sectionAxis');
  host.querySelector('#cadDepth').oninput=e=>{if(valid())this.change({sectionRatio:Number(e.target.value)},true);};
  host.querySelector('#cadCurvatureComb').onclick=()=>{if(valid()&&!host.querySelector('#cadCurvatureComb').disabled)this.change({comb:!this.settings.comb},true);};
  host.querySelector('#cadCombGain').oninput=e=>{if(valid())this.change({combGain:Number(e.target.value)},true);};
  host.querySelector('#cadCombDensity').onchange=e=>{if(valid())this.change({combDensity:Number(e.target.value)},true);};
  host.querySelector('#cadInflections').onclick=()=>{if(valid()&&!host.querySelector('#cadInflections').disabled)this.change({combInflections:!this.settings.combInflections},true);};
  host.querySelector('#cadCurvatureJumps').onclick=()=>{if(valid()&&!host.querySelector('#cadCurvatureJumps').disabled)this.change({combJumps:!this.settings.combJumps},true);};
  for(const[id,key]of [['cadSurfaceMode','surfaceMode'],['cadSurfaceMetric','surfaceMetric']])host.querySelector('#'+id).onchange=e=>{if(valid())this.change({[key]:e.target.value},true);};
  for(const[id,key]of [['cadZebraDensity','zebraDensity'],['cadZebraAngle','zebraAngle']])host.querySelector('#'+id).oninput=e=>{if(valid())this.change({[key]:Number(e.target.value)},true);};
  host.querySelector('#cadSurfaceRange').onchange=e=>{if(valid())this.change({surfaceRange:Number(e.target.value)},true);};
  host.querySelector('#cadFit').onclick=()=>{if(valid()&&this.ready())document.querySelector('#fitButton').click();};
  host.querySelector('#cadMeasure').onclick=()=>{if(!valid()||!this.ready(true))return;const v=this.state().canvas;v.measureMode=!v.measureMode;this.clearMeasurement(v);v.explode=0;const slider=document.querySelector('#explodeSlider');if(slider)slider.value=0;v.draw();this.update();this.toast(v.measureMode?'Select two points on the model.':'Measurement off');};
  this.update();
 }
 validHost(){return this.host?.isConnected&&this.host.querySelector('.cad-view-controls')&&this.mountOwner===this.key();}
 syncSlider(view){if(!view?.is3D)return;const slider=document.querySelector('#explodeSlider');if(slider){slider.disabled=!!view.measureMode;slider.value=view.explode;}}
 update(){
  this.syncSlider(this.state().canvas);
  if(!this.validHost())return;const h=this.host,p=this.settings,view=this.state().canvas;
  for(const b of h.querySelectorAll('[data-cad-toggle]')){const key=b.dataset.cadToggle,on=p[key];b.setAttribute('aria-pressed',String(on));b.disabled=!this.ready(key==='grid');b.querySelector('.display-row-check').hidden=!on;}
  for(const[id,key]of [['cadStyle','style'],['cadProjection','projection'],['cadSection','sectionAxis'],['cadDepth','sectionRatio']]){const e=h.querySelector('#'+id);e.value=p[key];e.disabled=!this.ready(true)||(id==='cadDepth'&&p.sectionAxis==='none');}
  h.querySelector('#cadDepthValue').textContent=p.sectionAxis==='none'?'':`${Number(view?.sectionDepth||0).toFixed(2)} mm`;
  h.querySelector('#cadMeasure').disabled=!this.ready(true);h.querySelector('#cadMeasure').setAttribute('aria-pressed',String(!!view?.measureMode));h.querySelector('#cadFit').disabled=!this.ready();
  const summary=view?.data?(view.curvatureSummary||=curvatureComb(view.data,{gain:0})):null,available=this.ready(true)&&summary?.available;
  const toggle=h.querySelector('#cadCurvatureComb');toggle.disabled=!available;toggle.setAttribute('aria-pressed',String(p.comb));
  for(const[id,key]of [['cadCombGain','combGain'],['cadCombDensity','combDensity']]){const input=h.querySelector('#'+id);input.value=p[key];input.disabled=!available||!p.comb;}
  h.querySelector('#cadCombGainValue').textContent=String(p.combGain);
  h.querySelector('#cadCombStatus').textContent=summary?.available?`${summary.availableEdges} native edges · κ ${Number(summary.minimum).toPrecision(4)}–${Number(summary.maximum).toPrecision(4)} 1/mm${summary.unavailableEdges?` · ${summary.unavailableEdges} unavailable`:''}`:'No native curve samples in this revision. Retained models stay unchanged.';
  const events=view?.data?(view.curveEventSummary||=curvatureEvents(view.data)):null;
  for(const[id,key,available]of [['cadInflections','combInflections',events?.inflectionEdges],['cadCurvatureJumps','combJumps',events?.jumpEdges]]){const button=h.querySelector('#'+id);button.setAttribute('aria-pressed',String(p[key]));button.disabled=!this.ready(true)||!p.comb||!available;}
  h.querySelector('#cadCurveEventStatus').textContent=events?.available?`${events.inflectionCount} inflections · ${events.jumpCount} curvature jumps${events.incompleteEdges?` · ${events.incompleteEdges} curves incomplete`:''}`:'No native curve event data in this revision. Retained models stay unchanged.';
  const surfaces=view?.data?(view.surfaceSummary||=surfaceSummary(view.data)):null,surfaceReady=this.ready(true)&&surfaces?.available;
  for(const[id,key]of [['cadSurfaceMode','surfaceMode'],['cadSurfaceMetric','surfaceMetric'],['cadSurfaceRange','surfaceRange'],['cadZebraDensity','zebraDensity'],['cadZebraAngle','zebraAngle']]){const input=h.querySelector('#'+id);input.value=p[key];input.disabled=!surfaceReady||id!=='cadSurfaceMode'&&p.surfaceMode==='off';}
  h.querySelector('#cadZebraControls').hidden=p.surfaceMode!=='zebra';h.querySelector('#cadSurfaceCurvatureControls').hidden=p.surfaceMode!=='curvature';
  h.querySelector('#cadZebraDensityValue').textContent=String(p.zebraDensity);h.querySelector('#cadZebraAngleValue').textContent=p.zebraAngle+'°';
  const units=p.surfaceMetric==='gaussian'?'1/mm²':'1/mm',range=Number(p.surfaceRange.toPrecision(4));
  h.querySelector('#cadSurfaceLegend').innerHTML=`<span class="cad-surface-scale"></span><span>${p.surfaceMetric==='max_abs'?0:-range} to ${range} ${units}</span>`;
  h.querySelector('#cadSurfaceStatus').textContent=surfaces?.available?`${surfaces.faces} native faces · ${surfaces.validSamples}/${surfaces.total} samples${surfaces.unavailableSamples?' · gray values unavailable':''}`:'No native surface samples in this revision. Retained models stay unchanged.';
 }
}
