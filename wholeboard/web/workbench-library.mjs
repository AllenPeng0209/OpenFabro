import {icon,esc} from './workbench-icons.mjs';
import {newAsset,writeAsset,libraryId,padHole,editPadField,validatePad} from './workbench-library-model.mjs';
import {arcThroughPoints} from './workbench-geometry.mjs';
import {PadShapeUI} from './workbench-pad-shapes.mjs';

const labels={symbols:'Symbol',footprints:'Footprint',parts:'Part',modules:'Module'};
const pinTypes=['input','output','bidirectional','tri_state','passive','free','unspecified','power_in','power_out','open_collector','open_emitter','no_connect'];
const pinShapes=['line','inverted','clock','inverted_clock','input_low','clock_low','output_low','edge_clock_high','non_logic'];
const layers=['F.SilkS','B.SilkS','F.Fab','B.Fab','F.CrtYd','B.CrtYd','Dwgs.User','Cmts.User'];
const options=(items,value)=>items.map(item=>`<option value="${esc(item)}" ${item===value?'selected':''}>${esc(item.replaceAll('_',' '))}</option>`).join('');
const rounded=n=>+n.toFixed(4);

export class LibraryUI{
  constructor(deps){Object.assign(this,deps);this.kind='symbols';this.id=null;this.entity=null;this.tool='select';this.grid=.635;this.cameras=new Map();this.unit=1;this.shapeCache=new Map();this.shapeRequests=new Set();this.shapeEditor=new PadShapeUI({...deps,library:this});}
  get(){return this.state().spec.library?.[this.kind]?.[this.id];}
  run(fn){return(...args)=>Promise.resolve().then(()=>fn(...args)).catch(error=>this.toast(error.message,true));}
  editable(){return this.state().project.access?.can_edit!==false&&!['running','waiting'].includes(this.state().project.status);}
  apply(value,action,newId=this.id){
    if(!this.editable())throw new Error('Editing is unavailable for this project.');
    if(value&&this.kind!=='footprints'&&!/^[A-Z][A-Z_]*$/.test(value.reference||'U'))throw new Error('Use an uppercase reference prefix without a number.');
    if(value&&this.kind==='footprints'&&value.height_mm!==undefined&&(!Number.isFinite(value.height_mm)||value.height_mm<=0))throw new Error('Enter a positive component height in millimetres.');
    const next=writeAsset(this.state().spec,this.kind,this.id,value,newId);this.id=newId;
    this.commit(next,action);return next;
  }
  render(host){
    this.shapeEditor.reconcile();
    if(this.kind==='modules'){this.modulesUI.render(host,{onKind:kind=>{this.kind=kind;this.render(host);}});return;}
    if(this.projectId!==this.state().pid){this.projectId=this.state().pid;this.id=null;this.entity=null;this.cameras.clear();}
    this.host=host;
    const assets=this.state().spec.library?.[this.kind]||{};
    if(!assets[this.id]){this.id=Object.keys(assets)[0]||null;this.entity=null;}
    const asset=this.get(),disabled=this.editable()?'':'disabled';
    host.innerHTML=`<section class="asset-editor"><aside class="asset-browser"><div class="asset-browser-heading">${icon('shapes')}Project library</div><div class="asset-browser-tools"><select id="libraryKind" aria-label="Library asset type">${options(['symbols','footprints','parts','modules'],this.kind)}</select><button class="icon-button" id="newLibraryAsset" aria-label="New library asset" title="New ${labels[this.kind].toLowerCase()}" ${disabled}>${icon('plus')}</button></div><input id="libraryFilter" type="search" placeholder="Search this project" aria-label="Search project library"><div class="asset-list">${Object.entries(assets).map(([id,item])=>`<button class="asset-list-item ${this.id===id?'selected':''}" data-library-asset="${esc(id)}">${icon(this.kind==='footprints'?'board':this.kind==='symbols'?'schematic':'chip')}<span><strong>${esc(id)}</strong><small>${esc(item.description||item.name||'')}</small></span></button>`).join('')||'<p class="file-help">Create a symbol, footprint or reusable part for this project.</p>'}</div><div class="asset-browser-footer"><button id="copyInstalledAsset" class="asset-text-button" ${disabled} ${this.kind==='parts'?'hidden':''}>${icon('copy')}Copy installed asset</button><button id="importLibrary" class="asset-text-button" ${disabled}>${icon('upload')}Import library</button><button id="exportLibrary" class="asset-text-button">${icon('download')}Export KiCad library</button><input type="file" id="importLibraryFile" accept=".json,.kicad_mod,.kicad_sym" hidden></div></aside><main class="asset-main">${asset?`<header class="asset-header"><div><small>${labels[this.kind]}</small><strong>Project:${esc(this.id)}</strong></div><button class="icon-button" id="renameLibraryAsset" title="Rename library ID" aria-label="Rename library ID" ${disabled}>${icon('file')}</button><button class="icon-button" id="duplicateLibraryAsset" title="Duplicate asset" aria-label="Duplicate asset" ${disabled}>${icon('copy')}</button><button class="icon-button danger-text" id="deleteLibraryAsset" title="Delete asset" aria-label="Delete asset" ${disabled}>${icon('trash')}</button></header>${this.kind==='parts'?'<div id="libraryPartEditor" class="asset-part-editor"></div>':`<div class="asset-toolbar" role="toolbar" aria-label="Library drawing tools">${['select',this.kind==='symbols'?'pin':'pad','rectangle','line','circle','text'].map(tool=>`<button data-library-tool="${tool}" class="${this.tool===tool?'active':''}" title="${tool}" ${tool==='select'?'':disabled}>${icon({select:'navigation',pin:'plus',pad:'plus',rectangle:'rectangle',line:'minus',circle:'circle',text:'file'}[tool])}<span>${tool[0].toUpperCase()+tool.slice(1)}</span></button>`).join('')}<div class="asset-toolbar-spacer"></div>${this.kind==='symbols'?`<label>Unit <select id="libraryUnit" aria-label="Symbol unit">${Array.from({length:Math.max(1,...asset.pins.map(p=>p.unit||1))},(_,i)=>`<option ${this.unit===i+1?'selected':''}>${i+1}</option>`).join('')}</select></label>`:''}<label>Grid <select id="libraryGrid" aria-label="Library grid">${[.127,.254,.5,.635,1,1.27,2.54].map(step=>`<option value="${step}" ${this.grid===step?'selected':''}>${step} mm</option>`).join('')}</select></label><button id="fitLibrary" title="Fit asset" aria-label="Fit asset">${icon('scan')}</button></div><div class="asset-workspace"><div class="asset-drawing"><svg id="libraryCanvas" tabindex="0" role="img" aria-label="${labels[this.kind]} drawing"></svg><div class="asset-canvas-note" id="libraryCanvasNote">${this.kind==='symbols'?'Pins use electrical connection points.':'Pad coordinates and dimensions are in millimetres.'}</div></div><aside class="asset-properties" id="libraryProperties"></aside></div><div class="asset-entity-list" id="libraryEntityList"></div>`}`:`<div class="asset-empty">${icon(this.kind==='footprints'?'board':'schematic')}<h2>Create your first ${labels[this.kind].toLowerCase()}</h2><p>${this.kind==='parts'?'Link a symbol and footprint into a reusable part.':'Draw editable geometry that stays with your project and exports to KiCad.'}</p><button class="secondary-button" id="emptyNewLibraryAsset" ${disabled}>${icon('plus')}New ${labels[this.kind].toLowerCase()}</button></div>`}</main></section>`;
    const $=selector=>host.querySelector(selector);
    $('#libraryKind').onchange=e=>{this.kind=e.target.value;this.id=null;this.entity=null;this.tool='select';this.grid=this.kind==='footprints'?.5:.635;this.render(host);};
    $('#newLibraryAsset').onclick=this.run(()=>this.create());
    if($('#emptyNewLibraryAsset'))$('#emptyNewLibraryAsset').onclick=this.run(()=>this.create());
    $('#libraryFilter').oninput=e=>host.querySelectorAll('[data-library-asset]').forEach(button=>button.hidden=!button.textContent.toLowerCase().includes(e.target.value.toLowerCase()));
    host.querySelectorAll('[data-library-asset]').forEach(button=>button.onclick=()=>{this.id=button.dataset.libraryAsset;this.entity=null;this.tool='select';this.render(host);});
    $('#exportLibrary').onclick=this.run(async()=>{await this.save();const a=document.createElement('a');a.href=`/api/workbench/projects/${this.state().pid}/library/export`;a.download='project-library.zip';a.click();});
    $('#importLibrary').onclick=()=>$('#importLibraryFile').click();
    $('#copyInstalledAsset').onclick=this.run(async()=>{
      const source=await this.askText('Copy installed '+labels[this.kind].toLowerCase(),'KiCad Library:Item',this.kind==='symbols'?'Device:R':'Resistor_SMD:R_0603_1608Metric');if(!source)return;
      await this.save();const data=await this.api(`/api/workbench/projects/${this.state().pid}/library/copy`,{method:'POST',body:{kind:this.kind,id:source.trim()}});
      const proposed=source.split(':').pop().replace(/[^A-Za-z0-9_-]/g,'_')+'_copy';
      const id=await this.askText('Copy to project library','New library ID',proposed);if(!id)return;
      if(this.state().spec.library?.[this.kind]?.[id])throw new Error('A library asset already uses that ID.');
      const next=writeAsset(this.state().spec,this.kind,id,data.asset);this.id=id;this.entity=null;this.tool='select';
      await this.api(`/api/workbench/projects/${this.state().pid}/library/validate`,{method:'POST',body:{spec:next}});
      this.commit(next,'Copied installed library asset');this.toast(data.note);
    });
    $('#importLibraryFile').onchange=this.run(async event=>{
      const file=event.target.files[0];if(!file)return;if(file.size>5_000_000)throw new Error('Choose a library JSON smaller than 5 MB.');
      const content=await file.text(),native=/\.kicad_(mod|sym)$/i.test(file.name);let data,note;
      await this.save();
      if(native){const kind=/\.kicad_mod$/i.test(file.name)?'footprints':'symbols',result=await this.api(`/api/workbench/projects/${this.state().pid}/library/import-native`,{method:'POST',body:{kind,content}});data={[kind]:result.assets};note=result.note;}
      else {data=JSON.parse(content);data=data.library||data;}
      const next=structuredClone(this.state().spec);next.library||={};
      for(const kind of ['symbols','footprints','parts']){const source=data[kind]||{};if(typeof source!=='object'||Array.isArray(source))throw new Error('Choose an exported project library JSON.');next.library[kind]||={};for(const [id,value] of Object.entries(source)){if(next.library[kind][id])throw new Error(`Library asset ${id} already exists. Rename it before importing.`);next.library[kind][id]=value;}}
      await this.save();await this.api(`/api/workbench/projects/${this.state().pid}/library/validate`,{method:'POST',body:{spec:next}});
      if(native){this.kind=data.footprints?'footprints':'symbols';this.id=Object.keys(data[this.kind])[0];this.entity=null;}
      this.commit(next,'Imported project library');this.toast(note||'Library imported');
    });
    if(!asset)return;
    $('#renameLibraryAsset').onclick=this.run(async()=>{const id=await this.askText('Rename library ID','Library ID',this.id);if(id===null||id===this.id)return;this.apply(this.get(),'Renamed library asset',id.trim());});
    $('#duplicateLibraryAsset').onclick=this.run(async()=>{
      const id=await this.askText('Duplicate '+labels[this.kind].toLowerCase(),'New library ID',this.id+'_copy');if(!id)return;if(this.state().spec.library[this.kind][id])throw new Error('A library asset already uses that ID.');
      const next=writeAsset(this.state().spec,this.kind,id,this.get());this.id=id;this.entity=null;this.commit(next,'Duplicated library asset');
    });
    $('#deleteLibraryAsset').onclick=this.run(()=>{this.apply(null,'Deleted library asset');this.entity=null;});
    if(this.kind==='parts'){this.renderPart();return;}
    host.querySelectorAll('[data-library-tool]').forEach(button=>button.onclick=()=>{this.tool=button.dataset.libraryTool;host.querySelectorAll('[data-library-tool]').forEach(b=>b.classList.toggle('active',b===button));$('#libraryCanvasNote').textContent=this.tool==='select'?'Select an object to edit. Drag to move it.':`Click to place a ${this.tool}.`;});
    $('#libraryGrid').onchange=e=>{this.grid=Number(e.target.value);this.draw();};
    if($('#libraryUnit'))$('#libraryUnit').onchange=e=>{this.unit=Number(e.target.value);this.entity=null;this.draw();this.properties();this.table();};
    $('#fitLibrary').onclick=()=>{this.cameras.delete(this.cameraKey());this.draw();};
    const svg=$('#libraryCanvas');
    svg.onpointerdown=event=>this.pointerDown(event);
    svg.onpointermove=event=>this.pointerMove(event);
    svg.onpointerup=event=>this.run(()=>this.pointerUp(event))();
    svg.onpointercancel=()=>{this.drag=null;this.preview=null;this.draw();};
    svg.onwheel=event=>{event.preventDefault();const camera=this.camera(),p=this.point(event),factor=event.deltaY>0?1.12:.89;const width=Math.min(4000,Math.max(1,camera[2]*factor)),height=width*camera[3]/camera[2];this.cameras.set(this.cameraKey(),[p[0]+(camera[0]-p[0])*width/camera[2],this.sy(p[1])+(camera[1]-this.sy(p[1]))*height/camera[3],width,height]);this.draw();};
    svg.onkeydown=event=>{if(event.metaKey||event.ctrlKey)return;event.stopPropagation();if(event.key==='Delete'||event.key==='Backspace'){event.preventDefault();this.run(()=>this.removeEntity())();}if(event.key.toLowerCase()==='r')this.run(()=>this.rotate())();if(event.key.toLowerCase()==='f'){$('#fitLibrary').click();}if(event.key==='Escape'){this.tool='select';this.entity=null;this.draw();this.properties();this.table();}};
    this.draw();this.properties();this.table();
  }
  async create(){
    const id=await this.askText('New '+labels[this.kind].toLowerCase(),'Library ID','My'+labels[this.kind]);if(!id)return;
    if(!libraryId(id)||this.state().spec.library?.[this.kind]?.[id])throw new Error('Choose an unused ID beginning with a letter. Use letters, digits, dashes or underscores.');
    const next=writeAsset(this.state().spec,this.kind,id,newAsset(this.kind,id,this.state().spec));this.id=id;this.entity=null;this.tool='select';this.commit(next,'Created '+labels[this.kind].toLowerCase());
  }
  field(label,key,value,{type='text',choices,asset=false,step}={}){
    return `<label>${label}${choices?`<select ${asset?`id="${key}"`:`data-library-field="${key}"`}>${options(choices,value)}</select>`:`<input ${asset?`id="${key}"`:`data-library-field="${key}"`} type="${type}" value="${esc(value??'')}" ${type==='number'?`step="${step||'any'}"`:''}>`}</label>`;
  }
  bindFields(container,callback){
    for(const input of container.querySelectorAll('input,select')){input.disabled=!this.editable();input.onchange=this.run(()=>{let value=input.type==='number'?Number(input.value):input.value;if(input.type==='number'&&(!input.value.trim()||!Number.isFinite(value)||Math.abs(value)>2000))throw new Error('Enter a finite dimension between −2000 and 2000 mm.');callback(input,value);});}
  }
  assetFields(asset){
    return this.field('Name','libraryAssetName',asset.name,{asset:true})+this.field('Description','libraryAssetDescription',asset.description,{asset:true})+(this.kind==='symbols'?this.field('Reference prefix','libraryAssetReference',asset.reference||'U',{asset:true})+this.field('Default footprint','libraryAssetFootprint',asset.footprint||'',{asset:true}):this.field('Mounting','libraryAssetMount',asset.mount||'smd',{asset:true,choices:['smd','through_hole']})+this.field('Height (mm)','libraryAssetHeight',asset.height_mm||2,{asset:true,type:'number'}));
  }
  properties(){
    const host=this.host.querySelector('#libraryProperties');if(!host)return;const asset=this.get(),entry=this.entity&&asset[this.entity[0]]?.[this.entity[1]];
    let html=`<h3>${entry?this.entity[0]==='pins'?'Pin '+entry.number:this.entity[0]==='pads'?'Pad '+entry.name:entry.kind:labels[this.kind]+' properties'}</h3>`;
    if(!entry)html+=this.assetFields(asset);
    else if(this.entity[0]==='pins')html+=this.field('Number','number',entry.number)+this.field('Name','name',entry.name)+this.field('Electrical type','type',entry.type||'passive',{choices:pinTypes})+this.field('Shape','shape',entry.shape||'line',{choices:pinShapes})+this.field('Unit','unit',entry.unit||1,{type:'number',step:1});
    else if(this.entity[0]==='pads'){
      html+=this.field('Number','name',entry.name)+this.field('Type','kind',entry.kind||'smd',{choices:['smd','thru_hole','np_thru_hole','connect']})+this.field('Shape','shape',entry.shape,{choices:['rect','roundrect','circle','oval','custom']})+this.field('Width (mm)','w',entry.w,{type:'number'})+this.field('Height (mm)','h',entry.h,{type:'number'})+(entry.kind==='thru_hole'?'<p class="file-help">Copper spans the enabled through-hole layers.</p>':entry.kind==='np_thru_hole'&&!entry.npth_copper?'<p class="file-help">Mechanical hole without copper.</p>':this.field('Copper layer','layer',entry.layer||'F.Cu',{choices:entry.kind==='np_thru_hole'?['F.Cu','B.Cu','*.Cu']:['F.Cu','B.Cu']}))+'<button id="editCustomPadShape" class="secondary-button">Custom SVG / DXF shape…</button>';
      if(entry.native_shape_note)html+=`<p class="file-help">${esc(entry.native_shape_note)}</p>`;
      if(!['smd','connect'].includes(entry.kind||'smd')){
        const hole=padHole(entry);html+=this.field('Hole shape','drill_shape',hole.shape,{choices:['circle','oval']});
        html+=hole.shape==='oval'?`<div class="asset-property-pair">${this.field('Hole X (mm)','drill_size.0',hole.size[0],{type:'number'})}${this.field('Hole Y (mm)','drill_size.1',hole.size[1],{type:'number'})}</div>`:this.field('Hole diameter (mm)','drill',entry.drill||0,{type:'number'});
        html+=`<div class="asset-property-pair">${this.field('Hole offset X (mm)','drill_offset.0',hole.offset[0],{type:'number'})}${this.field('Hole offset Y (mm)','drill_offset.1',hole.offset[1],{type:'number'})}</div><p class="file-help">Hole position is relative to the copper center, before pad rotation.</p>`;
      }
    }
    if(entry&&this.entity[0]!=='graphics')html+=`<div class="asset-property-pair">${this.field('X (mm)','x',entry.x,{type:'number'})}${this.field('Y (mm)','y',entry.y,{type:'number'})}</div>`+this.field('Rotation (°)','angle',entry.angle||0,{type:'number',step:90})+(this.entity[0]==='pins'?this.field('Length (mm)','length',entry.length,{type:'number'}):'');
    if(entry&&this.entity[0]==='graphics'){
      if(this.kind==='footprints')html+=this.field('Layer','layer',entry.layer||'F.SilkS',{choices:layers});
      html+=this.field('Line width (mm)','width',entry.width||.1524,{type:'number'});
      if(['rectangle','circle','polyline'].includes(entry.kind))html+=this.field('Fill','fill',entry.fill||'none',{choices:this.kind==='symbols'?['none','background','solid']:['none','solid']});
      for(const name of ['start','end','mid','center','position'])if(entry[name])html+=`<div class="asset-property-pair">${this.field(name+' X',name+'.0',entry[name][0],{type:'number'})}${this.field(name+' Y',name+'.1',entry[name][1],{type:'number'})}</div>`;
      if(entry.kind==='circle')html+=this.field('Radius (mm)','radius',entry.radius,{type:'number'});
      if(entry.kind==='text')html+=this.field('Text','text',entry.text)+this.field('Text size (mm)','size',entry.size||1.27,{type:'number'});
    }
    if(entry)html+=`<div class="asset-property-actions"><button class="secondary-button" id="rotateLibraryEntity">${icon('rotate')}Rotate 90°</button><button class="secondary-button danger-text" id="deleteLibraryEntity">${icon('trash')}Delete object</button></div><button class="asset-text-button" id="showLibraryAssetProperties">Asset properties</button>`;
    else html+='<p class="file-help">Changes are saved with the design. Select a drawing object to edit its dimensions.</p>';
    host.innerHTML=html;
    this.bindFields(host,(input,value)=>{
      const changed=structuredClone(this.get());
      if(!entry){const field={libraryAssetName:'name',libraryAssetDescription:'description',libraryAssetReference:'reference',libraryAssetFootprint:'footprint',libraryAssetMount:'mount',libraryAssetHeight:'height_mm'}[input.id];changed[field]=value;}
      else{let item=changed[this.entity[0]][this.entity[1]];const field=input.dataset.libraryField;
        if(this.entity[0]==='pads'&&field==='shape'&&value==='custom'){input.value=entry.shape;this.shapeEditor.open().catch(error=>this.toast(error.message,true));return;}
        if(this.entity[0]==='pads'){item=editPadField(item,field,value);changed.pads[this.entity[1]]=item;}
        else if(field.includes('.')){const [name,index]=field.split('.');item[name][Number(index)]=value;}else item[field]=value;
        this.validateEntry(item,this.entity[0]);
      }
      this.apply(changed,'Updated '+labels[this.kind].toLowerCase());
    });
    const shapeButton=host.querySelector('#editCustomPadShape');if(shapeButton){shapeButton.disabled=!this.editable();shapeButton.onclick=this.run(()=>this.shapeEditor.open());}
    if(entry){host.querySelector('#rotateLibraryEntity').onclick=this.run(()=>this.rotate());host.querySelector('#deleteLibraryEntity').onclick=this.run(()=>this.removeEntity());host.querySelector('#showLibraryAssetProperties').onclick=()=>{this.entity=null;this.properties();this.draw();this.table();};}
  }
  validateEntry(item,collection){
    if(collection==='pins'){
      if(!item.number?.trim()||!Number.isInteger(item.unit||1)||item.unit<0||item.unit>26||item.length<0)throw new Error('A pin needs a number, a valid unit and a nonnegative length.');
      if(this.get().pins.some((pin,i)=>i!==this.entity?.[1]&&pin.number===item.number&&(pin.unit||1)===(item.unit||1)))throw new Error('That pin number is already used in this unit.');
    }
    if(collection==='pads')validatePad(item);
    if(collection==='graphics'&&(item.width<=0||(item.kind==='circle'&&item.radius<=0)||(item.kind==='text'&&item.size<=0)))throw new Error('Drawing dimensions must be positive.');
  }
  renderPart(){
    const host=this.host.querySelector('#libraryPartEditor'),asset=this.get();
    host.innerHTML=`<div class="asset-part-summary">${icon('chip')}<div><h2>${esc(asset.name||this.id)}</h2><p>A reusable part combines its symbol, footprint and sourcing details.</p></div></div><div class="asset-part-fields">${[['Name','name'],['Value','value'],['Reference prefix','reference'],['Symbol','symbol'],['Footprint','footprint'],['Description','description'],['Manufacturer part number','mpn'],['LCSC number','lcsc']].map(([label,field])=>this.field(label,'libraryPart'+field[0].toUpperCase()+field.slice(1),asset[field],{asset:true})).join('')}</div><button class="primary-button" id="useLibraryPart" ${this.editable()?'':'disabled'}>${icon('plus')}Add to design</button><p class="file-help">Connections are made in the schematic after insertion.</p>`;
    this.bindFields(host,(input,value)=>{const changed=structuredClone(this.get()),key=input.id.slice('libraryPart'.length);changed[key[0].toLowerCase()+key.slice(1)]=value;this.apply(changed,'Updated reusable part');});
    host.querySelector('#useLibraryPart').onclick=this.run(async()=>{await this.save();this.openPart({...this.get()});});
  }
  table(){
    const host=this.host.querySelector('#libraryEntityList');if(!host)return;const asset=this.get(),collection=this.kind==='symbols'?'pins':'pads';
    const entries=(asset[collection]||[]).map((item,index)=>({item,index,collection}));
    host.innerHTML=`<div class="asset-entity-heading"><span>${collection==='pins'?'Pins':'Pads'} (${entries.length})</span><button class="asset-text-button" id="addLibraryEntity" ${this.editable()?'':'disabled'}>${icon('plus')}Add ${collection==='pins'?'pin':'pad'}</button></div><div class="asset-entity-table"><table><thead><tr><th>Number</th>${collection==='pins'?'<th>Name</th><th>Electrical type</th>':'<th>Type</th><th>Size (mm)</th>'}<th>X</th><th>Y</th><th>Angle</th></tr></thead><tbody>${entries.map(({item,index})=>`<tr tabindex="0" data-library-row="${collection}:${index}" class="${this.entity?.join(':')===collection+':'+index?'selected':''}"><td>${esc(item.number??item.name)}</td>${collection==='pins'?`<td>${esc(item.name)}</td><td>${esc(item.type)}</td>`:`<td>${esc(item.kind)}</td><td>${item.w} × ${item.h}</td>`}<td>${item.x}</td><td>${item.y}</td><td>${item.angle||0}°</td></tr>`).join('')}</tbody></table></div>`;
    host.querySelectorAll('[data-library-row]').forEach(row=>{const select=()=>{const [kind,index]=row.dataset.libraryRow.split(':');this.entity=[kind,Number(index)];this.draw();this.properties();this.table();};row.onclick=select;row.onkeydown=e=>{if(e.key==='Enter')select();};});
    host.querySelector('#addLibraryEntity').onclick=this.run(()=>this.add(this.kind==='symbols'?'pin':'pad',[0,0]));
  }
  sy(y){return this.kind==='symbols'?-y:y;}
  cameraKey(){return`${this.projectId}:${this.kind}:${this.id}:${this.unit}`;}
  camera(){
    if(!this.cameras.has(this.cameraKey())){
      const asset=this.get(),points=[];
      for(const item of [...(asset.pins||[]),...(asset.pads||[])]){const radius=Math.max(item.w||1,item.h||1)/2;points.push([item.x-radius,this.sy(item.y)-radius],[item.x+radius,this.sy(item.y)+radius]);}
      for(const graphic of asset.graphics||[])for(const key of ['start','end','mid','center','position'])if(graphic[key])points.push([graphic[key][0],this.sy(graphic[key][1])]);
      const xs=points.map(p=>p[0]),ys=points.map(p=>p[1]);const x=xs.length?Math.min(...xs):-5,y=ys.length?Math.min(...ys):-4,w=xs.length?Math.max(...xs)-x:10,h=ys.length?Math.max(...ys)-y:8;
      this.cameras.set(this.cameraKey(),[x-4,y-4,Math.max(16,w+8),Math.max(12,h+8)]);
    }
    return this.cameras.get(this.cameraKey());
  }
  point(event){const svg=this.host.querySelector('#libraryCanvas'),p=new DOMPoint(event.clientX,event.clientY).matrixTransform(svg.getScreenCTM().inverse());return[p.x,this.sy(p.y)];}
  snap(p){return p.map(v=>rounded(Math.round(v/this.grid)*this.grid));}
  shapeKey(pad,index){const s=this.state();return JSON.stringify([s.pid,s.projectLoadToken,s.session?.user?.id,s.version,this.id,index,pad.custom_shape,pad.w,pad.h]);}
  customShape(pad,index){
    const key=this.shapeKey(pad,index);if(this.shapeCache.has(key))return this.shapeCache.get(key);
    if(!this.shapeRequests.has(key)){
      this.shapeRequests.add(key);const s=this.state(),pid=s.pid,footprint=this.id,version=s.version;
      this.api(`/api/workbench/projects/${pid}/library/footprints/${encodeURIComponent(footprint)}/pads/${index}/shape`).then(result=>{
        if(result.version!==version)return;this.shapeCache.set(key,result.shape_report);while(this.shapeCache.size>128)this.shapeCache.delete(this.shapeCache.keys().next().value);
        if(this.state().active==='library'&&this.kind==='footprints'&&this.id===footprint&&this.get()?.pads?.[index]&&this.shapeKey(this.get().pads[index],index)===key)this.draw();
      }).catch(error=>{this.shapeCache.set(key,{error:error.message});if(this.state().pid===pid&&this.state().active==='library')this.draw();}).finally(()=>this.shapeRequests.delete(key));
    }return null;
  }
  draw(){
    const svg=this.host.querySelector('#libraryCanvas');if(!svg)return;const asset=this.preview||this.get(),camera=this.camera();svg.setAttribute('viewBox',camera.join(' '));
    let html=`<defs><pattern id="asset-grid" width="${this.grid}" height="${this.grid}" patternUnits="userSpaceOnUse"><circle cx="0" cy="0" r=".025" fill="#626262"/></pattern></defs><rect x="${camera[0]-10000}" y="${camera[1]-10000}" width="20000" height="20000" fill="url(#asset-grid)"/><path d="M ${camera[0]-10000} 0 H ${camera[0]+10000} M 0 ${camera[1]-10000} V ${camera[1]+10000}" stroke="#3e3e3e" stroke-width=".035"/>`;
    const wrap=(collection,index,content,extra='')=>`<g data-library-entity="${collection}:${index}" class="asset-drawing-entity ${this.entity?.join(':')===collection+':'+index?'selected':''} ${extra}" tabindex="0">${content}</g>`;
    (asset.graphics||[]).forEach((g,index)=>{
      if(this.kind==='symbols'&&g.unit&&g.unit!==this.unit)return;
      let shape='',stroke=g.width||.1524,fill=g.fill==='solid'?'currentColor':g.fill==='background'?'#253029':'none';
      const p=point=>`${point[0]},${this.sy(point[1])}`;
      if(g.kind==='rectangle')shape=`<rect x="${Math.min(g.start[0],g.end[0])}" y="${Math.min(this.sy(g.start[1]),this.sy(g.end[1]))}" width="${Math.abs(g.end[0]-g.start[0])}" height="${Math.abs(g.end[1]-g.start[1])}"/>`;
      if(g.kind==='line')shape=`<line x1="${g.start[0]}" y1="${this.sy(g.start[1])}" x2="${g.end[0]}" y2="${this.sy(g.end[1])}"/>`;
      if(g.kind==='circle')shape=`<circle cx="${g.center[0]}" cy="${this.sy(g.center[1])}" r="${g.radius}"/>`;
      if(g.kind==='polyline')shape=`<${g.closed?'polygon':'polyline'} points="${g.points.map(p).join(' ')}"/>`;
      if(g.kind==='arc'){
        const a=[g.start[0],this.sy(g.start[1])],m=[g.mid[0],this.sy(g.mid[1])],b=[g.end[0],this.sy(g.end[1])],arc=arcThroughPoints(a,m,b);
        shape=`<path d="M ${a} ${arc?`A ${arc.radius} ${arc.radius} 0 ${arc.large} ${arc.sweep} ${b}`:`L ${b}`}"/>`;
      }
      if(g.kind==='text')shape=`<text x="${g.position[0]}" y="${this.sy(g.position[1])}" font-size="${g.size||1.27}" stroke="none" fill="currentColor" transform="rotate(${this.kind==='symbols'?-(g.angle||0):g.angle||0} ${g.position[0]} ${this.sy(g.position[1])})">${esc(g.text)}</text>`;
      html+=wrap('graphics',index,`<g stroke="currentColor" stroke-width="${stroke}" fill="${fill}">${shape}</g>`,'asset-graphic '+(g.layer?.includes('CrtYd')?'courtyard':''));
    });
    (asset.pins||[]).forEach((pin,index)=>{
      if(pin.unit&&pin.unit!==this.unit)return;const radians=(pin.angle||0)*Math.PI/180,end=[pin.x+Math.cos(radians)*pin.length,pin.y+Math.sin(radians)*pin.length];
      const textX=end[0]+Math.cos(radians)*.4,textY=this.sy(end[1]+Math.sin(radians)*.4),anchor=Math.cos(radians)<-.1?'end':Math.cos(radians)>.1?'start':'middle';
      html+=wrap('pins',index,`<line x1="${pin.x}" y1="${this.sy(pin.y)}" x2="${end[0]}" y2="${this.sy(end[1])}" stroke="currentColor" stroke-width=".15"/><circle cx="${pin.x}" cy="${this.sy(pin.y)}" r=".18" fill="#212121" stroke="currentColor" stroke-width=".07"/><text x="${(pin.x+end[0])/2}" y="${this.sy((pin.y+end[1])/2)-.3}" text-anchor="middle" font-size=".7" fill="#c9bb8a">${esc(pin.number)}</text><text x="${textX}" y="${textY+.25}" text-anchor="${anchor}" font-size=".7" fill="currentColor">${esc(pin.name)}</text>`,'asset-pin');
    });
    (asset.pads||[]).forEach((pad,index)=>{
      const x=pad.x,y=this.sy(pad.y),shape=pad.shape,rx=shape==='circle'||shape==='oval'?Math.min(pad.w,pad.h)/2:shape==='roundrect'?Math.min(pad.w,pad.h)*(pad.rratio??.25):0;
      const hole=padHole(pad);
      const compiled=shape==='custom'?this.customShape(pad,index):null,body=shape==='custom'?(compiled?.contours?`<path data-custom-pad-ready d="${compiled.contours.map(r=>'M '+r.map(p=>p.join(' ')).join(' L ')+' Z').join(' ')}" fill-rule="evenodd" fill="${pad.kind==='np_thru_hole'&&!pad.npth_copper?'none':'currentColor'}" stroke="currentColor" stroke-width=".04"/>`:`<rect x="${-pad.w/2}" y="${-pad.h/2}" width="${pad.w}" height="${pad.h}" fill="none" stroke="#777" stroke-dasharray=".15 .1"/><title>${esc(compiled?.error||'Loading custom copper…')}</title>`):`<rect x="${-pad.w/2}" y="${-pad.h/2}" width="${pad.w}" height="${pad.h}" rx="${rx}" fill="${pad.kind==='np_thru_hole'&&!pad.npth_copper?'none':'currentColor'}" stroke="currentColor" stroke-width=".07"/>`;
      html+=wrap('pads',index,`<g transform="translate(${x} ${y}) rotate(${-(pad.angle||0)})">${body}${!['smd','connect'].includes(pad.kind||'smd')?`<rect data-pad-hole x="${hole.offset[0]-hole.size[0]/2}" y="${hole.offset[1]-hole.size[1]/2}" width="${hole.size[0]}" height="${hole.size[1]}" rx="${Math.min(...hole.size)/2}" fill="#212121"/>`:''}<text x="0" y=".25" text-anchor="middle" font-size="${Math.min(.75,pad.w*.65,pad.h*.65)}" fill="#191919">${esc(pad.name)}</text></g>`,'asset-pad '+(pad.layer==='B.Cu'?'back':''));
    });
    svg.innerHTML=html;svg.classList.toggle('placing',this.tool!=='select');
  }
  pointerDown(event){
    if(event.button!==0&&event.button!==1)return;const svg=event.currentTarget,point=this.point(event);svg.focus({preventScroll:true});
    if(event.button===1||event.altKey){event.preventDefault();this.drag={pan:true,start:point,camera:[...this.camera()]};svg.setPointerCapture(event.pointerId);return;}
    if(this.tool!=='select'){if(this.editable())this.run(()=>this.add(this.tool,this.snap(point)))();return;}
    const key=event.target.closest('[data-library-entity]')?.dataset.libraryEntity;
    if(!key){this.entity=null;this.draw();this.properties();this.table();return;}
    const [collection,index]=key.split(':');this.entity=[collection,Number(index)];this.draw();this.properties();this.table();
    if(!this.editable())return;
    this.drag={start:point,original:structuredClone(this.get()),entity:[...this.entity]};svg.setPointerCapture(event.pointerId);event.preventDefault();
  }
  translated(item,collection,delta){
    if(collection!=='graphics'){item.x=rounded(item.x+delta[0]);item.y=rounded(item.y+delta[1]);}
    else{for(const key of ['start','end','mid','center','position'])if(item[key])item[key]=item[key].map((v,i)=>rounded(v+delta[i]));if(item.points)item.points=item.points.map(p=>p.map((v,i)=>rounded(v+delta[i])));}
    return item;
  }
  pointerMove(event){
    if(!this.drag)return;const point=this.point(event),delta=point.map((v,i)=>v-this.drag.start[i]);
    if(this.drag.pan){const camera=[...this.drag.camera];camera[0]-=delta[0];camera[1]-=this.sy(delta[1]);this.cameras.set(this.cameraKey(),camera);this.draw();return;}
    const snapped=this.snap(delta);if(snapped.every(v=>!v))return;
    this.preview=structuredClone(this.drag.original);const [collection,index]=this.drag.entity;this.translated(this.preview[collection][index],collection,snapped);this.draw();
  }
  pointerUp(event){
    if(!this.drag)return;const preview=this.preview;this.drag=null;this.preview=null;if(event.currentTarget.hasPointerCapture(event.pointerId))event.currentTarget.releasePointerCapture(event.pointerId);
    if(preview)this.apply(preview,'Moved library object');else this.draw();
  }
  add(tool,point){
    if(!this.editable())return;const asset=structuredClone(this.get()),[x,y]=point;let collection,item;
    if(tool==='pin'||tool==='pad'){
      collection=tool==='pin'?'pins':'pads';let number=1;while(asset[collection].some(p=>String(p.number??p.name)===String(number)))number++;
      item=tool==='pin'?{number:String(number),name:'PIN'+number,x,y,angle:0,length:2.54,type:'passive',unit:this.unit}:{name:String(number),x,y,w:1,h:1.5,angle:0,kind:asset.mount==='through_hole'?'thru_hole':'smd',shape:'roundrect',drill:asset.mount==='through_hole'?.5:0,layer:'F.Cu'};
    }else{
      collection='graphics';item={kind:tool,width:.1524,...(this.kind==='footprints'?{layer:'F.SilkS'}:{unit:this.unit})};
      if(tool==='rectangle'||tool==='line')Object.assign(item,{start:[x,y],end:[x+2.54,y+(tool==='line'?0:2.54)],fill:'none'});
      if(tool==='circle')Object.assign(item,{center:[x,y],radius:1.27,fill:'none'});
      if(tool==='text')Object.assign(item,{text:'Text',position:[x,y],size:1.27,angle:0});
    }
    asset[collection]||=[];asset[collection].push(item);this.entity=[collection,asset[collection].length-1];this.tool='select';this.apply(asset,'Added library '+tool);
  }
  rotate(){
    if(!this.entity)return;const asset=structuredClone(this.get()),[collection,index]=this.entity,item=asset[collection][index];
    if(collection!=='graphics')item.angle=((item.angle||0)+90)%360;
    else if(item.kind==='text')item.angle=((item.angle||0)+90)%360;
    else{
      const points=['start','end','mid','center'].filter(key=>item[key]),center=points.length?points.reduce((a,key)=>a.map((v,i)=>v+item[key][i]/points.length),[0,0]):[0,0];
      const rotate=p=>[rounded(center[0]-(p[1]-center[1])),rounded(center[1]+p[0]-center[0])];
      for(const key of points)item[key]=rotate(item[key]);if(item.points)item.points=item.points.map(rotate);
    }
    this.apply(asset,'Rotated library object');
  }
  removeEntity(){
    if(!this.entity)return;const asset=structuredClone(this.get()),[collection,index]=this.entity;asset[collection].splice(index,1);const next=writeAsset(this.state().spec,this.kind,this.id,asset);this.entity=null;this.commit(next,'Deleted library object');
  }
}
