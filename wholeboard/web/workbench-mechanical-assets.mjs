import {esc,icon} from './workbench-icons.mjs';
import {CADView} from './workbench-cad.mjs';
import {droppedFiles} from './workbench-mesh-files.mjs';

const slug=name=>name.replace(/\.[^.]+$/,'').toLowerCase().replace(/[^a-z0-9]+/g,'_').replace(/^_|_$/g,'').slice(0,60)||'imported_part';

export class MechanicalAssetsUI{
 constructor(parts){this.parts=parts;parts.assets=this;this.generation=0;}
 valid(){return !!this.dialog?.isConnected&&this.parts.modal?.element===this.dialog&&this.parts.historyIntentCurrent(this.context);}
 ownership(){const dialog=this.dialog,context=this.context;return()=>this.dialog===dialog&&this.context===context&&this.valid();}
 async open(){
  const p=this.parts;if(p.modal||p.openingParameters||p.running.has(p.state().pid))return;
  this.viewer?.destroy();this.viewer=null;this.generation++;this.context=p.context();this.selected=null;this.assets=[];this.working=false;
  const dialog=document.createElement('dialog');this.dialog=dialog;dialog.id='cadAssetsDialog';dialog.className='cad-assets-dialog';
  dialog.innerHTML=`<header><div><h2>Import 3D part or assembly</h2><p>Import CAD geometry and create an editable part.</p></div><button id="cadAssetsClose" class="icon-button" aria-label="Close CAD assets">${icon('close')}</button></header>
   <div class="cad-assets-body"><aside><label class="cad-asset-drop" tabindex="0">${icon('upload')}<strong>Choose files or drop here</strong><span>CAD, mesh or drawing · up to 20 MB</span><input id="cadAssetFiles" type="file" accept=".step,.stp,.stpz,.iges,.igs,.brep,.stl,.obj,.glb,.gltf,.dxf,.svg,.mtl,.bin,.png,.jpg,.jpeg,.webp" multiple hidden></label><button type="button" class="secondary-button" id="cadAssetChooseFolder">Choose folder</button><input id="cadAssetFolder" type="file" webkitdirectory multiple hidden><label class="cad-asset-units">STL / OBJ units<select id="cadAssetUnits"><option value="mm">Millimeters</option><option value="cm">Centimeters</option><option value="m">Meters</option><option value="in">Inches</option></select></label><details class="cad-drawing-options"><summary>Drawing options</summary><label class="cad-asset-units">Unitless drawing units<select id="cadDrawingUnits"><option value="auto">Document / default units</option><option value="mm">Millimeters</option><option value="in">Inches</option><option value="cm">Centimeters</option><option value="m">Meters</option><option value="px">CSS pixels (96 ppi)</option></select></label><label class="cad-asset-units">SVG regions<select id="cadDrawingMode"><option value="fill">Filled artwork</option><option value="outline">Closed outlines and cutouts</option></select></label><label class="cad-asset-units">DXF layers<input id="cadDrawingLayers" placeholder="All visible layers, or CUT, HOLES"></label></details><div id="cadAssetList" role="list" aria-label="Imported CAD files"></div></aside>
   <section class="cad-asset-details"><div id="cadAssetPreview" aria-label="CAD import preview"></div><div id="cadAssetInfo"><p>Choose a CAD file to preview its parts.</p></div><div id="cadAssetBodyList"></div>
    <div id="cadAssetFields" hidden><label>Part name<input id="cadAssetName" maxlength="100" required></label><label>CAD source path<input id="cadAssetPath" value="cad/imported_part.cad.json" required></label><label id="cadAssetExtrusion" hidden>Extrusion height (mm)<input id="cadAssetHeight" type="number" value="3" min="0.000001" max="10000" step="any"></label></div>
   </section></div><p id="cadAssetMessage" role="status">Loading imported assets…</p><footer><button class="secondary-button" id="cadAssetReport" disabled>Copy report</button><span></span><button class="primary-button" id="cadAssetCreate" disabled>Create editable part</button></footer>`;
  document.body.append(dialog);p.modal={element:dialog,context:this.context};dialog.showModal();p.sync();
  const owns=this.ownership();
  dialog.querySelector('#cadAssetsClose').onclick=()=>{if(!this.working)dialog.close();};
  dialog.addEventListener('cancel',event=>{if(this.working)event.preventDefault();});
  dialog.addEventListener('close',()=>{if(this.dialog===dialog){this.generation++;this.viewer?.destroy();this.viewer=null;}if(p.modal?.element===dialog)p.modal=null;dialog.remove();p.sync();p.flush();},{once:true});
  const input=dialog.querySelector('#cadAssetFiles'),drop=dialog.querySelector('.cad-asset-drop');
  input.onchange=()=>{const files=[...input.files];input.value='';this.upload(files);};
  const folder=dialog.querySelector('#cadAssetFolder');dialog.querySelector('#cadAssetChooseFolder').onclick=()=>folder.click();folder.onchange=()=>{const files=[...folder.files];folder.value='';this.upload(files);};
  drop.onkeydown=event=>{if((event.key==='Enter'||event.key===' ')&&!this.working){event.preventDefault();input.click();}};
  drop.ondragover=event=>{event.preventDefault();drop.classList.add('dragging');};drop.ondragleave=()=>drop.classList.remove('dragging');
  drop.ondrop=async event=>{event.preventDefault();drop.classList.remove('dragging');if(!this.working&&owns())try{const files=await droppedFiles(event.dataTransfer);if(owns())this.upload(files);}catch(error){if(owns())this.message(error.message,true);}};
  dialog.querySelector('#cadAssetCreate').onclick=()=>this.create();
  dialog.querySelector('#cadAssetReport').onclick=async()=>{try{await navigator.clipboard.writeText(JSON.stringify(this.selected,null,2));p.toast('CAD import report copied');}catch(error){this.message(error.message,true);}};
  try{await this.refresh();if(owns())this.message(this.assets.length?'Select an imported file.':'No CAD files imported yet.');}
  catch(error){if(owns())this.message(error.message,true);}
 }
 message(text,error=false){if(!this.valid())return;const node=this.dialog.querySelector('#cadAssetMessage');node.textContent=text;node.setAttribute('role',error?'alert':'status');}
 async refresh(){const owns=this.ownership(),pid=this.context.pid,data=await this.parts.api(`/api/workbench/projects/${pid}/mechanical/assets`);if(!owns())return;this.assets=data.assets;this.paintList();}
 paintList(){
  if(!this.valid())return;const list=this.dialog.querySelector('#cadAssetList');
  list.innerHTML=this.assets.map(asset=>`<button type="button" role="listitem" data-asset="${esc(asset.asset_id)}" class="${this.selected?.asset_id===asset.asset_id?'selected':''}">${icon('cube')}<span>${esc(asset.name||'Unavailable asset')}<small>${asset.available===false?'Original changed':asset.bodies.length+' bodies · '+asset.format.toUpperCase()}</small></span></button>`).join('');
  for(const button of list.querySelectorAll('button'))button.onclick=()=>{if(!this.working)this.select(this.assets.find(a=>a.asset_id===button.dataset.asset));};
 }
 async select(asset){
  if(!this.valid())return;const generation=++this.generation;this.selected=asset;this.mesh=null;this.viewer?.destroy();this.viewer=null;this.paintList();
  const fields=this.dialog.querySelector('#cadAssetFields');fields.hidden=true;this.dialog.querySelector('#cadAssetBodyList').replaceChildren();this.dialog.querySelector('#cadAssetReport').disabled=false;
  if(asset.available===false){this.dialog.querySelector('#cadAssetInfo').textContent=asset.error;this.sync();return;}
  const metrics=asset.metrics;
  const mesh=asset.geometry_kind==='triangle-mesh',drawing=asset.geometry_kind==='planar-drawing',ignored=asset.diagnostics?.ignored?.length||0;
  this.dialog.querySelector('#cadAssetInfo').innerHTML=`<strong>${esc(asset.name)}</strong><p>${metrics.size_mm.map(n=>Number(n).toFixed(2)).join(' × ')} mm · ${mesh?metrics.closed_mesh_bodies+' closed meshes · '+metrics.triangles+' triangles':drawing?asset.bodies.filter(b=>b.can_extrude).length+' closed profiles':metrics.solids+' solids · '+metrics.faces+' faces'}</p>${mesh?`<p>Triangle mesh · ${asset.units_assumed?esc(asset.source_units)+' source units': 'meters / Y up converted to mm / Z up'}</p>`:drawing?`<p>Drawing · ${esc(asset.source_units)} · ${esc(asset.drawing_mode)} regions${ignored?' · '+ignored+' non-outline entities remain in original':''}</p>`:''}<a class="secondary-button" href="${esc(asset.original.url)}" download="${esc(asset.name)}">${icon('download')}Download original</a>${asset.original_bundle?` <a class="secondary-button" href="${esc(asset.original_bundle.url)}" download="${esc(asset.name)}-originals.zip">Download bundle</a>`:''}`;
  this.dialog.querySelector('#cadAssetBodyList').innerHTML=asset.bodies.map(body=>`<label><input type="checkbox" value="${body.body_id}" ${body.reference_only?'data-reference disabled':'checked'}><span class="cad-body-color" style="background:${esc(body.color)}"></span><span>${esc(body.name)}<small>${body.kind==='solid'?Number(body.volume_mm3).toFixed(2)+' mm³':body.kind==='mesh'?body.can_make_solid?'Closed mesh · editable':body.watertight?'Closed mesh · reference':'Open mesh · reference':body.can_extrude?Number(body.area_mm2).toFixed(2)+' mm² · '+body.holes+' cutouts':body.kind==='curve'?'Reference geometry':'Open surface'}</small></span></label>`).join('');
  this.dialog.querySelector('#cadAssetName').value=asset.name.replace(/\.[^.]+$/,'');this.dialog.querySelector('#cadAssetPath').value='cad/'+slug(asset.name)+'.cad.json';fields.hidden=false;
  for(const input of this.dialog.querySelectorAll('#cadAssetBodyList input'))input.onchange=()=>{this.sync();this.preview();};
  this.sync();this.message('Loading native preview…');
  try{
   const file=asset.files.find(f=>f.name==='scene.json'),response=await fetch(file.url);if(!response.ok)throw Error('Could not load the imported CAD preview.');
   const bytes=await response.arrayBuffer(),digest=[...new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))].map(n=>n.toString(16).padStart(2,'0')).join('');
   if(digest!==file.sha256)throw Error('The imported preview changed. Import a new copy of the original.');
   if(!this.valid()||generation!==this.generation)return;
   this.mesh=JSON.parse(new TextDecoder().decode(bytes));this.preview();this.message('Select the parts to make editable. The original file is preserved.');
  }catch(error){if(this.valid()&&generation===this.generation)this.message(error.message,true);}
 }
 chosen(){return this.valid()?[...this.dialog.querySelectorAll('#cadAssetBodyList input:checked')].map(input=>Number(input.value)):[];}
 preview(){if(!this.valid()||!this.mesh)return;const ids=new Set(this.chosen());this.viewer?.destroy();this.viewer=null;const host=this.dialog.querySelector('#cadAssetPreview');delete host.dataset.textures;const meshes=this.mesh.meshes.filter(m=>ids.has(m.body_id)),lines=this.mesh.lines||[];if(meshes.length||lines.length){const generation=this.generation;this.viewer=new CADView(host,{...this.mesh,meshes,lines},{onTexturesChanged:state=>{if(this.valid()&&generation===this.generation){host.dataset.textures=state;if(state==='failed')this.message('A model texture could not be displayed.',true);}}});this.viewer.explode=0;if(this.selected?.geometry_kind==='planar-drawing')this.viewer.setViewDirection([0,0,1]);this.viewer.draw();}}
 sync(){
  if(!this.valid())return;const writable=this.parts.editable()&&!this.parts.busy(),chosen=this.chosen(),bodies=(this.selected?.bodies||[]).filter(b=>chosen.includes(b.body_id)),surfaces=bodies.filter(b=>b.kind!=='solid'&&!(b.kind==='mesh'&&b.can_make_solid));
  const drawing=this.selected?.geometry_kind==='planar-drawing',surface=drawing?bodies.length>0&&bodies.every(b=>b.can_extrude):surfaces.length===1&&bodies.length===1&&surfaces[0].kind==='surface'&&surfaces[0].faces===1;
  this.dialog.querySelector('#cadAssetExtrusion').hidden=!surface;
  this.dialog.querySelector('#cadAssetExtrusion').firstChild.textContent=drawing?'Thickness (mm)':'Extrusion height (mm)';
  for(const node of this.dialog.querySelectorAll('input,button,select'))node.disabled=this.working||node.hasAttribute('data-reference');
  this.dialog.querySelector('#cadAssetFiles').disabled=this.working||!writable;
  this.dialog.querySelector('#cadAssetFolder').disabled=this.working||!writable;this.dialog.querySelector('#cadAssetChooseFolder').disabled=this.working||!writable;
  this.dialog.querySelector('#cadAssetCreate').disabled=this.working||!writable||!chosen.length||this.selected?.available===false||surfaces.length>0&&!surface;
  this.dialog.querySelector('#cadAssetReport').disabled=!this.selected;
 }
 async upload(files){
  if(!this.valid()||this.working||!files.length)return;const owns=this.ownership();this.working=true;this.sync();this.message('Importing model geometry…');
  try{
   const results=await this.parts.importFiles(this.context,files,asset=>{if(owns()){this.assets=this.assets.filter(a=>a.asset_id!==asset.asset_id);this.assets.push({...asset,available:true});this.select({...asset,available:true});}},{units:this.dialog.querySelector('#cadAssetUnits').value,drawingUnits:this.dialog.querySelector('#cadDrawingUnits').value,drawingMode:this.dialog.querySelector('#cadDrawingMode').value,drawingLayers:this.dialog.querySelector('#cadDrawingLayers').value});
   if(owns()){const failed=results.filter(r=>!r.ok);this.message(failed.length?failed.map(r=>r.name+': '+r.error).join(' · '):results.length+' file(s) imported. Original files are preserved.',!!failed.length);}
  }catch(error){if(owns())this.message(error.message,true);}
  finally{if(owns()){this.working=false;this.sync();}}
 }
 async create(){
  if(!this.valid()||this.working||!this.parts.canWrite())return;
  const owns=this.ownership(),ids=this.chosen(),asset=this.selected,name=this.dialog.querySelector('#cadAssetName').value.trim(),path=this.dialog.querySelector('#cadAssetPath').value.trim();
  if(!name||!path||!ids.length)return;
  const bodies=asset.bodies.filter(b=>ids.includes(b.body_id)),surfaces=bodies.filter(b=>b.kind!=='solid'&&!(b.kind==='mesh'&&b.can_make_solid));
  this.working=true;this.sync();this.message('Building editable CAD geometry…');
  try{
   let args={asset_id:asset.asset_id,bodies:ids,path,name},endpoint='assets/part';
   if(asset.geometry_kind==='planar-drawing'){const height=Number(this.dialog.querySelector('#cadAssetHeight').value);if(!bodies.length||bodies.some(b=>!b.can_extrude)||!Number.isFinite(height)||height<=0)throw Error('Select closed drawing profiles and a positive thickness.');args={asset_id:asset.asset_id,profiles:ids,path,name,thickness:height};endpoint='assets/extrude';}
   else if(surfaces.length){const height=Number(this.dialog.querySelector('#cadAssetHeight').value);if(surfaces.length!==1||bodies.length!==1||!Number.isFinite(height)||height<=0)throw Error('Select one planar face and a positive extrusion height.');
    args={path,program:{schema:1,units:'mm',name,parameters:{height:{value:height,unit:'mm'}},features:[{id:'imported',op:'import',asset_id:asset.asset_id,bodies:ids},{id:'extruded',op:'extrude_shape',target:'imported',vector:[0,0,'height']}],result:'extruded'}};endpoint='build';}
   await this.parts.build(this.context,args,endpoint);if(owns())this.dialog.close();
  }catch(error){if(owns())this.message(error.message,true);}
  finally{if(owns()){this.working=false;this.sync();}}
 }
}
