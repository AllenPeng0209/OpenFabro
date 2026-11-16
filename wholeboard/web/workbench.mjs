import {LayoutPadUI} from './workbench-pad-editor.mjs';
import {StackupUI} from './workbench-stackup.mjs';
import { addComponent, updateComponent, removeComponent, componentPins, upsertNet, addVia, messageAction, copySelection, pasteSelection, moveSelection, editWireRoute,wireMergeNeedsReview,electricalNet } from './workbench-model.mjs';
import { icon, hydrateIcons, esc } from './workbench-icons.mjs';
import { DesignCanvas, conceptMeshes } from './workbench-canvas.mjs';
import { CADView } from './workbench-cad.mjs';
import {MechanicalAssemblyUI} from './workbench-mechanical-assembly.mjs';
import { renderMarkdown } from './workbench-markdown.mjs';
import {FileDraftRecoveryUI} from './workbench-draft-recovery.mjs';
import {editorText} from './workbench-drafts.mjs';
import { combineAssembly } from './workbench-geometry.mjs';
import { CollaborationUI } from './workbench-collab.mjs';
import { ManufacturingUI } from './workbench-manufacturing.mjs';
import { LibraryUI } from './workbench-library.mjs';
import { editCopper,previewCopper,copperLayers } from './workbench-copper.mjs';
import { RoutingUI } from './workbench-routing-ui.mjs';
import { routePoints } from './workbench-routing.mjs';
import {connectWireEndpoints,endpointPin,logicalPin,projectWirePoint,disconnectPin,removeWireDrawing,moveWireNode,splitWireDrawing,removeWireNode} from './workbench-wires.mjs';
import {SheetsUI} from './workbench-sheets-ui.mjs';
import {sheetDefinitions} from './workbench-sheets.mjs';
import {ModulesUI} from './workbench-modules.mjs';
import {ModuleConversionUI} from './workbench-convert-module.mjs';
import {TerminalsUI} from './workbench-terminals.mjs';
import {SchematicWireDraft} from './workbench-schematic-routing.mjs';
import {WireCutsUI} from './workbench-wire-cuts.mjs';
import {ModuleUpdatesUI} from './workbench-module-updates.mjs';
import {NetLabelsUI} from './workbench-net-labels.mjs';
import {BusesUI} from './workbench-buses.mjs';
import {SelectionTransformsUI} from './workbench-transforms.mjs';
import {ShortcutsUI} from './workbench-shortcuts.mjs';
import {ObjectsUI} from './workbench-objects.mjs';
import {ParametricUI} from './workbench-parametric.mjs';
import {FilesTreeUI} from './workbench-files.mjs';
import {loadFileCatalog,fileBadge,isDocument,imageFile} from './workbench-files-model.mjs';
import {MarkupUI,referenceMarkup} from './workbench-markup.mjs';
import {AIChangeHistory,changeTable} from './workbench-ai-changes.mjs';
import {AIFilesUI} from './workbench-ai-files.mjs';
import {ViewportSlots} from './workbench-viewports.mjs';
import {ComponentHotkeys} from './workbench-component-hotkeys.mjs';
import {LayersUI} from './workbench-layers-ui.mjs';
import {ToolPaneDock} from './workbench-pane-dock.mjs';
import {SchematicDisplayUI} from './workbench-display.mjs';
import {CADViewUI} from './workbench-cad-ui.mjs';
import {prepareCADData} from './workbench-cad-model.mjs';
import * as CameraMath from './workbench-camera.mjs';
import {NavigationCube} from './workbench-navigation.mjs';
import {RouteTuningUI} from './workbench-route-tuning.mjs';
import {NativeRoutingUI} from './workbench-native-routing.mjs';
import {MechanicalPartsUI} from './workbench-mechanical-parts.mjs';
import {MechanicalAssetsUI} from './workbench-mechanical-assets.mjs';
import {NativeMatePicker} from './workbench-mechanical-picker.mjs';
import {MechanicalFeaturesUI} from './workbench-mechanical-features.mjs';
import * as NativeTopology from './workbench-cad-topology.mjs';
window.MeshView.cameraMath=CameraMath;
window.MeshView.nativeTopology=NativeTopology;

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const S = { spec: null, pid: null, version: 0, project: {}, projects: [], events: [], selected: null, selectedNet: null,
  active: 'schematic', mode: 'agent', dirty: false, generation: 0, saving: null, undo: [], redo: [], actions: [],
  canvas: null,routingProfiles:null, socket: null, reconnect: null, status: null, config: null, panel: null, inspector: false,chatDrafts:new Map(),chatSends:new Map(),chatDraftGeneration:0,
  attachment: null,attachmentBusy:null, enclosure: false, grid: false, hiddenLayers: new Set(['F.Fab','B.Fab','courtyards']), saveTimer: null, files: [], lastSeq: 0, selection:new Set(),boardGrid:.5,starting:true,openingProject:null,projectLoadToken:0 };
const views = { files: ['file', 'Files'], schematic: ['schematic', 'Schematic'], layout: ['board', 'Layout'], '3d': ['cube', '3D View'],
  bom: ['table', 'BOM'], components: ['chip', 'Components'], nets: ['schematic', 'Nets'], blocks: ['workflow', 'Block diagram'], review: ['shield', 'Review'], simulation: ['workflow', 'Simulation'], pins: ['chip','Pins'],symbol:['chip','Symbol'],buses:['link','Buses'], rules: ['layers','Rules'], knowledge: ['file','Knowledge'],library:['shapes','Library'] };
const toolDock=new ToolPaneDock({host:$('#drawer'),state:()=>S,onFocus:key=>{S.panel=key;}});
const markupUI=new MarkupUI({state:()=>S,save,api,toast,editable,canStart:()=>!S.nativePicking,displayContext:canvas=>S.active==='layout'?layersUI.capture(canvas):null,onChange:()=>{applyAccessUI();updateSendState();},onDraftChange:()=>{recordChatDraft(true);updateSendState();}});
const aiChanges=new AIChangeHistory({state:()=>S,api});
const aiFilesUI=new AIFilesUI({state:()=>S,api,editable,busy,toast,onBusy:()=>applyAccessUI(),updated:(context,result)=>{
 if(S.pid!==context.pid||S.projectLoadToken!==context.load||result.version<S.version||S.dirty)return;
 S.spec=result.spec;S.version=result.version;S.project.spec=result.spec;S.project.workbench=result.workbench;S.undo=[];S.redo=[];aiChanges.commit(S.pid,{batch:null});S.generation++;invalidateCheckDisplay();S.selection.clear();S.selected=null;S.selectedNet=null;renderView();renderInspector();renderChat();updateContext();
}});
const shortcutsUI=new ShortcutsUI({dialog});
const viewportSlots=new ViewportSlots({state:()=>S,toast,interacting:()=>componentHotkeys.active||markupUI.active||markupUI.starting||routingUI.active||!!S.wireDraft||!!S.canvas?.interacting});
const componentHotkeys=new ComponentHotkeys({state:()=>S,toast,editable,busy,api,commit,interacting:()=>markupUI.active||markupUI.starting||routingUI.active||S.schematicWiring||!!S.wireDraft||!!S.canvas?.interacting||!!S.canvas?.panTool||!objectsUI.canEdit});
const layersUI=new LayersUI({state:()=>S,api,toast,openLayout:()=>setView('layout'),visibilityToken:()=>objectsUI.masks,interacting:()=>!!toolDock.resizing||markupUI.active||markupUI.starting||!!S.canvas?.copperDrag||!!S.canvas?.panTool,changed:(model,canvas)=>{
 if(S.routing&&!model.visible('tracks',{layer:S.routeSession?.layer||S.routingLayer||'F.Cu'})){routingUI.stop();toast('Routing stopped because its layer was hidden.');}
 if(S.selectedCopper){const item=canvas.geo[S.selectedCopper.kind]?.find(i=>i.id===S.selectedCopper.id);if(item&&!model.visible(S.selectedCopper.kind,item)){S.selectedCopper=null;canvas.selectCopper(null);S.inspector=false;S.selectedNet=null;renderInspector();updateContext();}}
 const visible=[...S.selection].filter(key=>{const item=canvas.geo.footprints.find(f=>f.ref===key.split('#')[0]);return !item||model.visible('footprints',item);});if(visible.length!==S.selection.size)selectMultiple(visible);
}});
const parametricUI=new ParametricUI({state:()=>S,api,save:saveReady,commit,editable,busy,toast,askText});
const objectsUI=new ObjectsUI({state:()=>S,context:objectContext,commit,editable,busy,askText,refreshInspector:renderInspector,select:selectObjectNodes,paint:paintObjectSelection,hoverNet:name=>{S.canvas?.setHoveredNet?.(name);},openSheet:openSchematicSheet,editPad:()=>layoutPadUI.open().catch(fail),toast});
const layoutPadUI=new LayoutPadUI({state:()=>S,selection:()=>objectsUI.chosen,api,save:saveReady,editable,busy,applySource:(pid,version,spec,native_source)=>saveDesignSource(pid,version,JSON.stringify(spec),{native_source,action:'Edited layout pad'}),refresh:()=>{renderView();renderInspector();}});
const collaborationUI=new CollaborationUI({api,state:()=>S,toast,dialog,save,askText,onContextChanged:()=>scheduleCollaborationRefresh(),openComments:()=>toggleDrawer('comments'),selectAnchor:anchor=>{if(views[anchor.view])setView(anchor.view);if(anchor.ref)selectComponent(anchor.ref);if(anchor.net)selectNet(anchor.net);}});
const displayUI=new SchematicDisplayUI({state:()=>S,toast,interacting:()=>markupUI.active||markupUI.starting||!!toolDock.resizing||componentHotkeys.active||!!S.canvas?.interacting||!!S.wireDraft,changed:()=>{collaborationUI.markers(S.canvas);collaborationUI.presenceMarkers(S.canvas);}});
const cadUI=new CADViewUI({state:()=>S,toast,interacting:()=>markupUI.active||markupUI.starting||!!toolDock.resizing||!!S.canvas?.interacting});
const navigationUI=new NavigationCube({state:()=>S,interacting:()=>markupUI.active||markupUI.starting||!!toolDock.resizing||!!S.canvas?.interacting,readSettings:()=>{cadUI.sync();return cadUI.settings;},changeSettings:patch=>cadUI.change(patch,true)});
const routeTuningUI=new RouteTuningUI({state:()=>S,api,save:saveReady,toast,editable,busy,interacting:()=>markupUI.active||markupUI.starting||routingUI.active||!!S.canvas?.interacting,apply:(pid,version,spec,native_source)=>saveDesignSource(pid,version,JSON.stringify(spec),{native_source,action:'Tuned route length'})});
const nativeRoutingUI=new NativeRoutingUI({state:()=>S,api,save:saveReady,toast,editable,busy,interacting:()=>markupUI.active||markupUI.starting||routingUI.active||!!S.canvas?.interacting,apply:(pid,version,spec,native_source,routing_proposal)=>saveDesignSource(pid,version,JSON.stringify(spec),{native_source,routing_proposal,action:'Applied reviewed routing'})});
const manufacturingUI=new ManufacturingUI({api,state:()=>S,toast,save,redraw:()=>renderDrawer('manufacturing'),updated:()=>{manufacturingUI.badge();if(S.active==='bom')renderTable();}});
const moduleUpdatesUI=new ModuleUpdatesUI({api,state:()=>S,toast,save,commit,editable,busy});
const modulesUI=new ModulesUI({api,state:()=>S,toast,save,commit,download,updates:moduleUpdatesUI,openProject,schematic:()=>setView('schematic'),open:id=>{openSchematicSheet(id);setView('schematic');}});
const moduleConversionUI=new ModuleConversionUI({state:()=>S,toast,commit,editable,busy,request:body=>modulesUI.request('convert',body),open:id=>{openSchematicSheet(id);setView('schematic');}});
const libraryUI=new LibraryUI({api,state:()=>S,toast,save,commit,askText,openPart:openPartPicker,modulesUI,busy,applySource:(pid,version,spec,native_source)=>saveDesignSource(pid,version,JSON.stringify(spec),{native_source,action:'Edited custom pad shape'}),refresh:()=>{renderView();renderInspector();}});
const routingUI=new RoutingUI({state:()=>S,editable,busy,toast,commit,undoDesign:undo,renderInspector,updateContext});
const sheetsUI=new SheetsUI({state:()=>S,editable,busy,toast,commit,open:openSchematicSheet,inspect:()=>{clearObjectContext();renderInspector();},context:updateContext});
const terminalsUI=new TerminalsUI({state:()=>S,api,save,commit,toast,editable,busy,select:selectComponent,inspect:renderInspector,closeDrawer,schematic:()=>setView('schematic'),openSheet:openSchematicSheet});
const netLabelsUI=new NetLabelsUI({state:()=>S,api,save,commit,toast,editable,busy,select:selectWireNode,startWire:(pin,anchor)=>{if(!S.schematicWiring)$('#wireButton').click();handleSchematicPin(pin,anchor);},editNet:pin=>openNetEditor(S.spec.nets.find(n=>n.pins.includes(pin))?.name||null,pin)});
const busesUI=new BusesUI({state:()=>S,api,save,commit,toast,editable,busy,setView,selectComponent,openSymbol,editNet:openNetEditor,refresh:()=>{renderView();renderInspector();}});
const stackupUI=new StackupUI({state:()=>S,api,save,commit,toast,editable,busy,apply:(pid,version,spec,native_source)=>saveDesignSource(pid,version,JSON.stringify(spec),{native_source,action:'Edited physical stackup'}),refresh:()=>{renderView();renderInspector();}});
const selectionTransformsUI=new SelectionTransformsUI({state:()=>S,api,save,commit,toast,editable,busy,interacting:()=>componentHotkeys.active||markupUI.active||markupUI.starting||routingUI.active||!!S.wireDraft||!!S.canvas?.interacting||!objectsUI.canEdit});
netLabelsUI.editBus=pin=>busesUI.open({action:'pins',pins:[pin]});
const wireCutsUI=new WireCutsUI({state:()=>S,api,save,commit,toast,editable,busy,cancel:cancelSchematicWire});
const mechanicalUI=new MechanicalPartsUI({state:()=>S,api,editable,busy,toast,save,host:$('#viewContent'),render:renderView,replaceMesh:replaceMeshData,
 interacting:()=>markupUI.active||markupUI.starting||!!S.canvas?.interacting||!!toolDock.resizing,
 adopt:state=>{S.project={...state,access:S.project.access};},openCode:path=>{S.openFilePath=path;setView('files');},open3D:()=>setView('3d'),selectAssemblyMember:id=>S.canvas?.selectComponent?.(id),onPickingChange:active=>{S.nativePicking=active;markupUI.reconcile();},viewer:()=>S.canvas});
const mechanicalAssetsUI=new MechanicalAssetsUI(mechanicalUI);
const mechanicalAssemblyUI=new MechanicalAssemblyUI(mechanicalUI);
const nativeMatePicker=new NativeMatePicker(mechanicalUI);
const mechanicalFeaturesUI=new MechanicalFeaturesUI(mechanicalUI);
mechanicalUI.importAssets=async()=>{if(!S.pid)await save();setView('3d');await mechanicalAssetsUI.open();};
const fileDraftUI=new FileDraftRecoveryUI({context:draftContext,read:readSavedDraft,apply:applyRecoveredDraft,active:path=>fileDraft(S.pid,path),discard:discardFileDraft,toast});

async function api(path, options = {}) {
  const response = await fetch(path, { ...options, headers: { 'Content-Type': 'application/json', ...options.headers }, body: options.body === undefined ? undefined : JSON.stringify(options.body) });
  const content = response.headers.get('content-type') || '';
  const data = content.includes('application/json') ? await response.json() : await response.text();
  if (!response.ok){const error=new Error(data.detail ? (typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail)) : data.error || `Request failed (${response.status})`);error.status=response.status;throw error;}
  return data;
}
function toast(message, error = false) {
  const el = document.createElement('div'); el.className = `toast${error ? ' error' : ''}`;
  if(!error)$$('.toast:not(.error)',$('#toastStack')).forEach(toast=>toast.remove());
  while($('#toastStack').children.length>2)$('#toastStack').firstElementChild.remove();
  el.setAttribute('role',error?'alert':'status');
  el.innerHTML = icon(error ? 'warning' : 'check'); const span = document.createElement('span'); span.textContent = message; el.append(span);
  $('#toastStack').append(el); setTimeout(() => el.remove(), error ? 6500 : 3500);
}
const fail = error => { console.warn(error.message); toast(error.message, true); };
function safely(fn) { return (...args) => Promise.resolve().then(() => fn(...args)).catch(fail); }
function savedLabel(label, state = '') { $('#saveLabel').textContent = label; $('#saveIndicator').className = `save-indicator ${state}`; $('#saveIndicator').title = label; }
function title(name) { $('#projectTitle').textContent = name; $('#dockProjectName').textContent = name; document.title = `${name} · OpenFabro`; }
function busy() { return ['running', 'waiting'].includes(S.project.status); }
function projectWritable(){return !S.starting&&!S.openingProject&&!S.aiRestoring&&S.project.access?.can_edit!==false;}
function draftOwner(){return`${S.session?.mode||'local'}:${S.session?.user?.id||'device'}`;}
function fileDraft(pid,path){const owner=draftOwner();if(S.fileDraftOwner!==owner){S.fileDraftOwner=owner;S.fileDrafts=new Map();}return S.fileDrafts?.get(`${pid}:${path}`);}
function draftContext(){return{owner:draftOwner(),pid:S.pid,load:S.projectLoadToken,path:S.currentFile?.path,files:S.active==='files'&&!S.openingProject,editable:projectWritable()};}
async function readSavedDraft(path){
 const pid=S.pid;if(path==='design.json'){if(S.dirty||S.saving)await saveReady();const response=await api(`/api/projects/${pid}`);return{exists:true,content:JSON.stringify(response.state.spec,null,2),sha:null,base_version:response.state.workbench.version};}
 const result=await api(`/api/workbench/projects/${pid}/text/${path.split('/').map(encodeURIComponent).join('/')}?allow_missing=true`);return{...result,exists:result.exists!==false,base_version:0};
}
async function applyRecoveredDraft(record,remote,content,owner){
 if(!fileDraftUI.valid(owner))throw Error('Open this project again before restoring its draft.');
 if(record.path==='design.json'){
  if(S.dirty||S.saving)await saveReady();if(!fileDraftUI.valid(owner))throw Error('The draft project changed.');
  if(S.version!==remote.base_version){S.pendingDesignVersion=Math.max(S.pendingDesignVersion||0,remote.base_version);await syncSavedDesign();}
  if(S.version!==remote.base_version||S.dirty)throw Error('The saved design changed again. Refresh the comparison.');
 }
 if(!fileDraftUI.valid(owner))throw Error('The draft project changed.');
 const existing=fileDraft(owner.pid,record.path),draft=fileDraftUI.persist(record.path,{content,base_content:remote.content,sha:remote.sha,base_version:remote.base_version,virtual:!remote.exists,recovered:true,record:existing?.record?.id===record.id?existing.record:undefined});
 S.fileDrafts.set(`${owner.pid}:${record.path}`,draft);S.openFilePath=record.path;await renderFiles();return draft;
}
function discardFileDraft(record){const key=`${record.pid}:${record.path}`,current=fileDraft(record.pid,record.path);if(current?.record?.id===record.id&&current.record.rev===record.rev){S.fileDrafts.delete(key);if(S.pid===record.pid&&S.active==='files')renderFiles().catch(fail);}}
function editable(){return projectWritable()&&!S.sourceSaving&&!S.designSync;}
function applyAccessUI(){
  nativeRoutingUI.reconcile();
  routeTuningUI.reconcile();
  collaborationUI.contextChanged();
  const edit=editable(),admin=S.session?.admin!==false,loading=S.starting||!!S.openingProject||!!S.designSync;
  if(!edit&&routingUI.active)routingUI.stop();
  if((!edit||busy())&&componentHotkeys.active)componentHotkeys.cancel();
  document.body.classList.toggle('read-only',!edit);
  $('#chatInput').disabled=!edit;$('#chatInput').placeholder=loading?'Opening project…':S.sourceSaving?'Saving design source…':edit?'Describe a device, circuit or enclosure…':`${S.project.access?.role||'Read-only'} access · ask the project owner for editing access`;
  $('#composerNote').textContent=loading?'Loading the saved design…':S.sourceSaving?'Saving design source. You can keep editing its draft.':edit?'OpenFabro · Your open-source AI hardware engineer.':`${S.project.access?.role||'Read-only'} access to this project`;
  for(const id of ['projectTitle','priceButton','shareButton','exportButton','historyButton'])if($('#'+id))$('#'+id).disabled=loading;
  $('#modelButton').disabled=!admin;$('#editWorkspaceProfile').hidden=!admin;$('#browserNewProject').hidden=S.session?.mode==='share';
  for(const id of ['autoLayoutButton','wireButton','routeButton','viaButton'])$('#'+id).disabled=!edit||(S.active==='layout'&&S.nativePending&&!(id==='routeButton'&&routingUI.optimistic));
  if(S.canvas?.options)S.canvas.options.readOnly=!edit;
  S.canvas?.drawConnections?.();
  if(S.canvas?.opts)S.canvas.opts.readOnly=!edit||S.nativePending&&!routingUI.optimistic;
  if(toolDock.has('objects'))objectsUI.refresh();
  for(const id of ['buildButton','buildEnclosure','buildNativeBoard3D'])if($('#'+id))$('#'+id).disabled=!edit;
  mechanicalUI.sync();
  for(const id of ['saveTextFile','newTextFile'])if($('#'+id))$('#'+id).disabled=!projectWritable()||id==='saveTextFile'&&!!S.sourceSaving;
  if($('#routeNetsButton'))$('#routeNetsButton').disabled=!edit||busy();
  if($('#fileEditor'))$('#fileEditor').readOnly=!projectWritable();
  $('#settingsButton').textContent=(S.session?.user?.name||'Personal')[0].toUpperCase();
  updateSendState();
  displayUI.apply();
  cadUI.apply();
  if(S.active==='3d'&&toolDock.has('layers')&&cadUI.mountOwner!==cadUI.key())refreshLayerPane();
  scheduleCollaborationRefresh();
  terminalsUI.markBusy();
  markupUI.reconcile();
  layersUI.resume();
  aiFilesUI.refreshAccess();
  fileDraftUI.update();
  busesUI.reconcile();stackupUI.reconcile();libraryUI.shapeEditor.reconcile();layoutPadUI.reconcile();
}
function closeMenus() { $('#mainMenu').hidden = true; $('#addViewMenu').hidden = true; $('#projectActionsMenu').hidden=true;if($('#canvasContextMenu'))$('#canvasContextMenu').hidden=true;selectionTransformsUI.closeArrange();componentHotkeys.closeMenu(); $('#mainMenuButton').setAttribute('aria-expanded', 'false'); }
function dialog(id) { layersUI.cancelPrefix();componentHotkeys.cancel();closeMenus(); const d = $(id); if (!d.open) d.showModal(); return d; }
function getTitle() { return S.project.custom_title || S.project.title || S.spec?.title || 'Untitled project'; }
function download(name, content, type = 'application/json') {
  const url = URL.createObjectURL(new Blob([content], { type })); const a = document.createElement('a'); a.href = url; a.download = name; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
}

// Persist full designs through OpenFabro. In-flight saves never consume later edits.
async function save() {
  clearTimeout(S.saveTimer);
  if (S.saving) { await S.saving; return S.dirty ? save() : S.pid; }
  if (S.pid && !S.dirty) return S.pid;
  S.saving = (async () => {
    savedLabel('Saving…', 'saving');
    const generation = S.generation, spec = structuredClone(S.spec);let savedWorkbench=null;
    if (!S.pid) {
      const result = await api('/api/workbench/projects', { method: 'POST', body: { title: getTitle(), spec } });
      S.pid = result.id; S.version = result.version; S.project = { ...S.project, ...result };
      migrateChatDraft(S.pid);
      if(!S.openingProject)location.hash = S.pid; connectEvents();
    } else {
      const result = await api(`/api/workbench/projects/${S.pid}/design`, { method: 'PUT', body: { base_version: S.version, spec } });
      S.version = result.version;savedWorkbench=result;
    }
    S.dirty = S.generation !== generation;
    savedLabel(S.dirty ? 'Unsaved changes' : 'Saved locally', S.dirty ? '' : 'saved');
    S.project.spec = spec; S.project.workbench = { version: S.version, checks_stale: savedWorkbench?.checks_stale??true, ...(savedWorkbench?.saved_at?{saved_at:savedWorkbench.saved_at}:{}) };
    localStorage.setItem('wb-workbench-project', S.pid);
    return S.pid;
  })();
  try { await S.saving; } catch (e) { savedLabel('Could not save', 'error'); throw e; } finally { S.saving = null; }
  if (S.dirty) return save();
  syncSavedDesign().catch(fail);
  moduleUpdatesUI.refresh().catch(()=>{});
  return S.pid;
}
function queueSave() { clearTimeout(S.saveTimer); S.saveTimer = setTimeout(() => save().catch(fail), 850); }
async function saveReady(){if(S.starting||S.openingProject)throw new Error('Wait for the project to finish opening before saving.');return save();}
function commit(spec, action, select = S.selected) {
  if(!editable()){toast('Your project role does not allow design changes.',true);return;}
  if (busy()) { toast('Stop the active build before changing the design.', true); return; }
  if (JSON.stringify(spec) === JSON.stringify(S.spec)) return;
  cancelSchematicWire();
  if(routingUI.active&&!routingUI.committing)routingUI.stop();
  S.undo.push(structuredClone(S.spec)); if (S.undo.length > 60) S.undo.shift(); S.redo = [];
  if(select!==S.selected)S.selectedSymbolKey=S.selectedSymbolKey?.startsWith(S.selected+'#')?select+S.selectedSymbolKey.slice(S.selected.length):select;
  if(select===null)S.selection.clear();
  else{
    if(S.selected&&select!==S.selected&&!spec.components.some(c=>c.ref===S.selected))S.selection=new Set([...S.selection].map(key=>key===S.selected||key.startsWith(S.selected+'#')?select+key.slice(S.selected.length):key));
    S.selection=new Set([...S.selection].filter(key=>spec.components.some(c=>c.ref===key.split('#')[0])));
    if(![...S.selection].some(key=>key.split('#')[0]===select))S.selection=new Set([select]);
  }
  S.spec = spec; S.selected = select; S.dirty = true; S.generation++;invalidateCheckDisplay();
  S.actions.push({ text: action, time: Date.now() });
  savedLabel('Unsaved changes'); renderView(); renderInspector(); renderChat();updateContext(); queueSave();
  if (toolDock.has('objects')) objectsUI.sync();
}
function undo(redo = false) {
  if (busy()||!editable()) return;
  if(mechanicalUI.handleUndo(redo))return;
  selectionTransformsUI.cancel();
  if(routingUI.active&&!routingUI.undoing){routingUI.guard(()=>routingUI.undo(redo));return;}
  const from = redo ? S.redo : S.undo, to = redo ? S.undo : S.redo;
  if (!from.length) return toast(redo ? 'Nothing to redo' : 'Nothing to undo');
  cancelSchematicWire();
  to.push(structuredClone(S.spec)); S.spec = from.pop(); S.dirty = true; S.generation++;invalidateCheckDisplay();
  S.selection=new Set([...S.selection].filter(key=>S.spec.components.some(c=>c.ref===key.split('#')[0])));
  if (!S.spec.components.some(c => c.ref === S.selected)) S.selected = null;
  routingUI.restoreGeometry();
  renderView(); renderInspector();renderChat(); updateContext(); queueSave();
  savedLabel('Unsaved changes'); toast(redo ? 'Change restored' : 'Change undone');
}

async function refreshProjects() { S.projects = (await api('/api/projects')).filter(p => !p.hidden); renderProjectMenu(); }
function renderProjectMenu() {
  $('#menuProjectList').innerHTML = S.projects.length ? S.projects.slice(0, 8).map(p => `<button data-open-project="${esc(p.id)}" class="${S.pid === p.id ? 'selected' : ''}">${icon('folder')}<span>${esc(p.title)}</span></button>`).join('') : '<div class="menu-foot">Your saved projects will appear here.</div>';
}
async function openProject(pid) {
  fileDraftUI.close();
  recordChatDraft();markupUI.cancel('project');
  componentHotkeys.cancel();
  aiFilesUI.close();
  const loadToken=++S.projectLoadToken;
  $('#partDialog').close();S.partPickerToken=(S.partPickerToken||0)+1;S.pickedPart=null;
  $('#historyDialog').close();
  selectionTransformsUI.cancel();
  closeProjectBrowser();
  if(pid===S.pid){if(S.openingProject){S.openingProject=null;S.starting=false;renderView();renderChat();renderInspector();savedLabel(S.saving?'Saving…':S.dirty?'Unsaved changes':'Saved locally',S.saving?'saving':S.dirty?'':'saved');}applyAccessUI();connectEvents();collaborationUI.loadComments().catch(fail);return;}
  routingUI.stop();
  $('#checkCount').textContent='—';
  S.openingProject={pid,token:loadToken};renderView();renderChat();renderInspector();applyAccessUI();savedLabel('Opening project…','saving');
  let response,historyState;
  try{if(S.saving||S.dirty)await save();if(loadToken!==S.projectLoadToken)return;aiChanges.remember();response=await api(`/api/projects/${encodeURIComponent(pid)}`);if(loadToken!==S.projectLoadToken)return;historyState=await aiChanges.prepare(pid,response.state);}
  catch(error){if(loadToken!==S.projectLoadToken)return;S.openingProject=null;S.starting=false;if(S.pid)history.replaceState(null,'',location.pathname+location.search+'#'+S.pid);renderView();renderChat();renderInspector();applyAccessUI();savedLabel('Could not open project','error');throw error;}
  if(loadToken!==S.projectLoadToken)return;
  S.openingProject=null;S.starting=false;
  disconnectEvents(); S.pid = pid; S.project = response.state; S.project.title = response.title;
  S.spec = response.state.spec || blankSpec(); S.version = response.state.workbench?.version || 0;
  S.dirty = false; S.generation = 0; S.undo = historyState.undo; S.redo = historyState.redo;aiChanges.commit(pid,historyState); S.events = response.events || []; S.lastSeq = S.events.at(-1)?.seq || 0;S.statusSeq=0;
  S.pendingDesignVersion=0;S.designSync=null;
  S.selected = null; S.selectedNet = null; S.objectOnlySelection=null; S.actions = []; S.files = []; S.attachment = null; S.inspector = false;
  restoreChatDraft(pid);
  S.selection.clear();
  S.enclosureDraft=null;S.routingProfiles=null;S.routingGap=null;S.routeStart=null;S.routing=false;S.viaPlacing=null;S.schematicWiring=false;cancelSchematicWire();$('#viaButton').setAttribute('aria-pressed','false');$('#routeButton').setAttribute('aria-pressed','false');$('#wireButton').setAttribute('aria-pressed','false');
  S.selectedSheet=null;S.selectedWireNode=null;S.schematicSheet='';S.schematicData=null;S.selectedWireIndex=null;S.selectedCopper=null;
  title(response.title); location.hash = pid; localStorage.setItem('wb-workbench-project', pid); savedLabel('Saved locally', 'saved');
  closeMenus(); closeDrawer(); renderChat(); renderView(); renderInspector(); updateContext(); updateSendState(); connectEvents();
  applyAccessUI();collaborationUI.loadComments().catch(fail);
  moduleUpdatesUI.refresh().catch(()=>{});
}
function blankSpec() { return { name: 'untitled_board', summary: '', board: { width_mm: 50, height_mm: 35, layers: 2, thickness_mm: 1.6 }, components: [], nets: [] }; }

async function openProjectBrowser() {
  closeMenus();routingUI.stop();if(S.dirty)await save();await refreshProjects();S.screen='projects';
  $('#ideShell').hidden=true;$('#projectBrowser').hidden=false;$('.project-bar').classList.add('projects-screen');$('#projectHeaderSearch').hidden=false;
  $('#workspaceDisplayName').textContent=S.config?.workspace?.display_name||'Personal workspace';
  const cells=[[0,0],[2,0],[4,0],[1,1],[2,1],[3,1],[0,2],[1,2],[3,2],[4,2],[0,3],[2,3],[4,3],[1,4],[2,4],[3,4]];
  $('#workspaceAvatar').innerHTML=`<svg viewBox="0 0 200 200" aria-hidden="true"><circle cx="100" cy="100" r="100" fill="#714b1e"/>${cells.map(([x,y])=>`<rect x="${25+x*30}" y="${25+y*30}" width="30" height="30" fill="#b16be0"/>`).join('')}</svg>`;
  $('#projectStats').textContent=`${S.projects.length} projects · ${S.projects.filter(p=>p.starred).length} starred`;
  $('#returnToEditor').hidden=!S.pid||S.project.access?.role==='revoked';renderProjectBrowser();if(location.hash!=='#projects')location.hash='projects';
}
function closeProjectBrowser() {
  S.screen='editor';$('#projectBrowser').hidden=true;$('#ideShell').hidden=false;$('.project-bar').classList.remove('projects-screen');$('#projectHeaderSearch').hidden=true;
  if(location.hash==='#projects'&&S.pid)location.hash=S.pid;
}
function renderProjectBrowser() {
  $('#projectStats').textContent=`${S.projects.length} projects · ${S.projects.filter(p=>p.starred).length} starred`;
  const search=($('#filterProjectName').value||$('#globalProjectSearch').value||'').toLowerCase();
  const filter=S.projectFilter||'all',template=$('#projectTypeFilter').value==='template';
  const projects=S.projects.filter(p=>(filter!=='starred'||p.starred)&&(!template||p.tags?.includes('template'))&&(`${p.title} ${p.prompt||''} ${(p.tags||[]).join(' ')}`).toLowerCase().includes(search));
  $('#projectBrowserList').innerHTML=projects.map(p=>`<article class="project-browser-row"><button class="project-thumbnail" data-browser-open="${esc(p.id)}" aria-label="Open ${esc(p.title)}">${p.thumb?`<img src="${esc(p.thumb)}" alt="PCB preview">`:icon('schematic')}</button><div class="project-row-info"><div class="project-row-title"><button data-browser-open="${esc(p.id)}">${esc(p.title)}</button><button class="icon-button" data-project-menu="${esc(p.id)}" aria-label="Actions for ${esc(p.title)}">⋯</button></div><p>${esc(p.prompt||'')}</p><div class="project-row-meta"><span class="mini-avatar">P</span><span class="project-author">personal</span><span>${esc(new Date((p.updated||p.created)*1000).toLocaleDateString())}</span><span class="project-state ${esc(p.status||'idle')}">${esc(p.status==='done'?'Built':p.status||'Draft')}</span>${(p.tags||[]).map(tag=>`<span class="project-tag">#${esc(tag)}</span>`).join('')}</div></div><button class="project-star ${p.starred?'starred':''}" data-project-star="${esc(p.id)}" aria-label="${p.starred?'Unstar':'Star'} ${esc(p.title)}">${icon('star')}${p.starred?'Starred':'Star'}</button></article>`).join('')||`<div class="project-browser-empty">${icon('folder')}<h2>${search||filter==='starred'?'No matching projects':'Your next product starts here'}</h2><p>${filter==='starred'?'Star a project to keep it here.':'Create a project or import an existing KiCad design.'}</p></div>`;
  $$('[data-browser-open]').forEach(b=>b.onclick=safely(()=>openProject(b.dataset.browserOpen)));
  $$('[data-project-star]').forEach(b=>b.onclick=safely(async()=>{const p=S.projects.find(p=>p.id===b.dataset.projectStar);await api(`/api/workbench/projects/${p.id}/metadata`,{method:'PATCH',body:{starred:!p.starred}});await refreshProjects();renderProjectBrowser();}));
  $$('[data-project-menu]').forEach(b=>b.onclick=e=>{e.stopPropagation();const r=b.getBoundingClientRect(),p=S.projects.find(p=>p.id===b.dataset.projectMenu);const menu=$('#projectActionsMenu');menu.innerHTML=`<button data-project-action="rename">${icon('file')}Rename</button><button data-project-action="clone">${icon('folder')}Clone project</button><button data-project-action="template">${icon('star')}${p.tags?.includes('template')?'Remove template tag':'Use as template'}</button><div class="menu-divider"></div><button class="danger-text" data-project-action="delete">${icon('trash')}Delete project</button>`;menu.style.left=`${Math.min(innerWidth-205,r.left)}px`;menu.style.top=`${r.bottom+4}px`;menu.hidden=false;$$('[data-project-action]',menu).forEach(action=>action.onclick=safely(()=>projectBrowserAction(p,action.dataset.projectAction)));});
}
async function projectBrowserAction(project,action) {
  closeMenus();
  if(action==='rename'){const value=await askText('Rename project','Project name',project.title);if(value!==null)await api(`/api/projects/${project.id}`,{method:'PATCH',body:{title:value}});}
  if(action==='clone'){const result=await api(`/api/workbench/projects/${project.id}/clone`,{method:'POST',body:{title:project.title+' copy'}});await openProject(result.id);toast('Project cloned');return;}
  if(action==='template'){const tags=project.tags||[];await api(`/api/workbench/projects/${project.id}/metadata`,{method:'PATCH',body:{tags:tags.includes('template')?tags.filter(t=>t!=='template'):[...tags,'template']}});}
  if(action==='delete'){const value=await askText('Delete project',`Type DELETE to permanently remove ${project.title} and its files`,'');if(value!=='DELETE')return;await api(`/api/projects/${project.id}`,{method:'DELETE'});if(S.pid===project.id){disconnectEvents();S.pid=null;localStorage.removeItem('wb-workbench-project');}toast('Project deleted');}
  await refreshProjects();renderProjectBrowser();
}
async function newProject(event) {
  event.preventDefault(); if (S.dirty) await save();
  const form = new FormData(event.target), name = form.get('title').trim();
  const button = $('button[type=submit]', event.target); button.disabled = true;
  try {
    const result = await api('/api/workbench/projects', { method: 'POST', body: { title: name, prompt: form.get('prompt'), example: form.get('template') === 'power' } });
    $('#newProjectDialog').close(); await openProject(result.id); await refreshProjects(); toast('Project created');
  } finally { button.disabled = false; }
}
async function renameProject() {
  const value = await askText('Rename project', 'Project name', getTitle()); if (value === null) return;
  S.project.custom_title = value.trim() || 'Untitled project'; title(getTitle());
  if (S.pid) await api(`/api/projects/${S.pid}`, { method: 'PATCH', body: { title: getTitle() } }); else await save();
  await refreshProjects(); toast('Project renamed');
}
function askText(heading, label, value) {
  return new Promise(resolve => {
    $('#textTitle').textContent = heading; $('#textLabel').firstChild.textContent = label; $('#textInput').value = value;
    const d = dialog('#textDialog'); $('#textInput').focus(); $('#textInput').select();
    let result = null;
    const submit = e => { e.preventDefault(); result = $('#textInput').value; d.close(); };
    $('#textForm').addEventListener('submit', submit);
    d.addEventListener('close', () => { $('#textForm').removeEventListener('submit', submit); resolve(result); }, { once: true });
  });
}

function openSymbol(ref,pin=null){parametricUI.ref=ref;parametricUI.pid=S.pid;parametricUI.selected=new Set(pin?[pin]:[]);setView('symbol');}

function objectContext(){
  const view=S.active==='layout'?'layout':'schematic',geo=S.canvas?.geo;
  const current=geo?.schema>=4&&S.canvas.sceneProject===S.pid&&S.canvas.sceneVersion===S.version&&!S.nativePending&&!S.dirty;
  return{pid:S.openingProject?.pid||S.pid,spec:S.spec,title:getTitle(),version:S.version,view,loading:S.starting||!!S.openingProject,geometry:current?geo:null,scene:S.schematicSpecObject===S.spec?S.schematicData:null};
}
function paintObjectSelection(nodes){layersUI.visibilityChanged();S.canvas?.setObjects?.(objectsUI.selectionNodes(nodes).map(node=>({kind:node.kind,collection:node.collection,id:node.native?.id,ref:node.ref,net:node.net,target:node.target})));}
function clearObjectContext(){if(!objectsUI.applying)S.objectOnlySelection=null;}
function selectObjectNodes(nodes){
  S.objectOnlySelection={scope:objectsUI.scope,ids:[...objectsUI.ids]};nodes=objectsUI.selectionNodes(nodes);
  S.selectedSheet=null;S.selectedWireNode=null;S.selectedWireIndex=null;S.selectedCopper=null;S.selected=null;S.selectedNet=null;S.selectedSymbolKey=null;S.selection.clear();
  S.canvas?.select?.(null);S.canvas?.selectMany?.([]);S.canvas?.selectWire?.(null);S.canvas?.selectSheet?.(null);if(S.canvas?.options)S.canvas.options.selectedWireNode=null;if(S.canvas?.geo)S.canvas.copperSelection=null;
  S.inspector=objectsUI.chosen.length>0;
  if(nodes.length&&nodes.every(n=>['component','symbol'].includes(n.target?.kind))){const keys=nodes.map(n=>n.target.symbolKey||n.target.ref);selectMultiple(keys,keys.at(-1));return;}
  if(nodes.length===1){const node=nodes[0],target=node.target;
    if(target.kind==='copper'){S.canvas?.selectCopper?.({kind:target.collection,id:target.id});selectCopper({kind:target.collection,id:target.id});return;}
    if(target.kind==='net'){selectNet(target.name);return;}
    if(['sheet','sheet_root','wire','node'].includes(target.kind)){
      const sheet=target.kind==='sheet'?(sheetDefinitions(S.spec)[target.id]?.parent||''):target.sheet||'';
      if(S.active!=='schematic'){changeSchematicSheet(sheet);setView('schematic');}else if(S.schematicSheet!==sheet){changeSchematicSheet(sheet);renderView();}
      if(target.kind==='sheet'){sheetsUI.select(target.id);return;}
      if(target.kind==='wire'){selectNet(node.net||null,target.index);return;}
      if(target.kind==='node'){selectWireNode(target.id);return;}
    }
  }
  renderInspector();updateContext();publishPresence();
}

// Canvas, tables, files, and Inspector all read the same saved netlist.
function setView(key) {
  if(key!=='files')fileDraftUI.close();
  if(S.active!==key)componentHotkeys.cancel();
  if(S.active!==key)markupUI.cancel('view');
  if(S.active!==key)selectionTransformsUI.cancel();
  closeMenus(); if (!views[key]) return;
  if(key!=='layout'&&routingUI.active)routingUI.stop();
  if(key!=='schematic')cancelSchematicWire();
  if(key!=='layout')S.selectedCopper=null;
  if(key==='library'||key==='files'||key==='symbol'){S.inspector=false;closeDrawer();renderInspector();}
  S.active = key;busesUI.reconcile();stackupUI.reconcile();libraryUI.shapeEditor.reconcile();layoutPadUI.reconcile();publishPresence(null);
  let tab = $(`[data-view="${key}"]`);
  if (!tab) {
    tab = document.createElement('button'); tab.setAttribute('role', 'tab'); tab.dataset.view = key;
    tab.innerHTML = icon(views[key][0]) + esc(views[key][1]); $('#viewTabs').insertBefore(tab, $('#addTabButton'));
  }
  $$('[data-view]').forEach(t => { t.classList.toggle('active', t.dataset.view === key); t.setAttribute('aria-selected', String(t.dataset.view === key)); });
  $('#viewContent').setAttribute('aria-label', views[key][1]); localStorage.setItem('wb-workbench-view', key); renderView();if(key!=='layout')refreshLayerPane();
}
function planarKey(){return`${S.pid||'reference'}:${S.active}:${S.active==='schematic'?S.schematicSheet||'':''}`;}
function disposeCanvas() {
  nativeRoutingUI.cancel();
  routeTuningUI.cancel();
  navigationUI.detach();
  $('#measureResult')?.remove();
  layersUI.detach();
  componentHotkeys.cancel();
  cadUI.capture(S.canvas);
  if(S.canvas?.workbenchKey&&(S.canvas.options?.nativeScene||S.canvas.geo)){const camera=S.canvas.getCamera?.();if(camera){S.planarCameras||=new Map();S.planarCameras.set(S.canvas.workbenchKey,camera);}}
  if(S.canvas?.geo)S.lastLayout={pid:S.canvas.sceneProject,version:S.canvas.sceneVersion,geo:structuredClone(S.canvas.geo),ratsnest:S.canvas.baseRatsnest,identity:S.canvas.nativeIdentity,profiles:structuredClone(S.routingProfiles)};
  S.canvas?.destroy?.(); S.canvas = null; S.plots?.forEach(p=>p.destroy()); S.plots=[];
}
function renderView() {
  mechanicalUI.onViewChange();
  markupUI.reconcile();
  if(S.starting||S.openingProject){S.viewToken=(S.viewToken||0)+1;disposeCanvas();$('#viewContent').innerHTML='<div class="empty-canvas" id="projectLoading" role="status"><h2>Opening project…</h2><p>Loading the saved design and engineering results.</p></div>';$('#canvasTools').hidden=true;$('#canvasBottom').hidden=true;$('#projectDock').hidden=true;return;}
  queueMicrotask(()=>moduleUpdatesUI.mount());
  if (!S.spec) return;
  manufacturingUI.badge();
  const token = S.viewToken = (S.viewToken || 0) + 1;
  disposeCanvas(); const host = $('#viewContent'); host.classList.toggle('inspecting', S.inspector);
  $('#projectDock').hidden=S.inspector||['library','symbol'].includes(S.active);
  const drawing = ['schematic', 'layout', '3d', 'blocks'].includes(S.active);
  $('#canvasTools').hidden=['library','files','symbol'].includes(S.active);
  $('#canvasBottom').hidden = !drawing; $('#autoLayoutButton').hidden = !['schematic', 'layout'].includes(S.active);
  $('#routeButton').hidden = S.active !== 'layout';
  $('#viaButton').hidden=S.active!=='layout';
  $('#wireButton').hidden=S.active!=='schematic';
  $('#cameraOptions').hidden=S.active!=='3d';
  $('#zoomReset').textContent = '100%'; $('#panButton').setAttribute('aria-pressed', 'false');
  if(S.active==='symbol'){parametricUI.render(host);return;}
  if (!S.spec.components.length && !Object.keys(sheetDefinitions(S.spec)).length && S.active==='blocks') {
    host.innerHTML = `<div class="empty-canvas">${icon('schematic')}<h2>Your next idea starts here</h2><p>Describe what you want to build in Chat, or add a component from the library.</p><button class="secondary-button" id="emptyAddPart">${icon('plus')}Add a component</button></div>`;
    $('#emptyAddPart').onclick = () => toggleDrawer('library'); return;
  }
  if(S.active==='layout'&&window.BoardView){
    S.nativePending=true;
    host.innerHTML=`<div class="boardview" id="nativeBoard"></div><div class="view-badge" id="nativeLayoutStatus">${icon('board')}${busy()?'The layout will refresh when the active run finishes.':'Updating KiCad geometry…'}</div>`;
    if(S.lastLayout?.pid===S.pid)mountNativeBoard(structuredClone(S.lastLayout.geo),S.lastLayout.ratsnest,true,S.lastLayout.identity,S.lastLayout.profiles);
    applyAccessUI();
    renderNativeLayout(token).catch(error=>{if(token===S.viewToken){const badge=$('#nativeLayoutStatus');if(badge)badge.textContent=error.message;console.warn(error.message);}});
    return;
  }
  if (['schematic', 'layout'].includes(S.active)) {
    const visual = S.project.visuals?.['drc:board'];
    if (S.active === 'layout' && visual?.url && !S.dirty && !S.project.workbench?.checks_stale && window.BoardView) {
      host.innerHTML = '<div class="boardview" id="nativeBoard"></div>';
      api(`/api/workbench/projects/${S.pid}/layout-geometry`).then(data => { if (token===S.viewToken&&S.active === 'layout') mountNativeBoard(data.geometry,false,false,layoutIdentity(data)); }).catch(fail);
    } else {
      const options={ mode: S.active, readOnly:!editable(), camera:S.planarCameras?.get(planarKey()), selection:[...S.selection],selected: S.selected, onSelect: selectComponent,onSelection:selectMultiple,onMoveMany:(moves,mode)=>commit(moveSelection(S.spec,moves,mode),`Moved ${moves.length} symbol${moves.length===1?'':'s'}`),onNet: selectNet,
        isObjectVisible:(kind,key)=>objectsUI.visibleSchematic(kind,key),canEditSelection:()=>objectsUI.canEdit,
        selectedWire:S.selectedWireIndex,selectedWireNode:S.selectedWireNode,onWireSelect:selectWire,onWireConnect:(index,point)=>{try{handleWireEndpoint(index,point);}catch(error){fail(error);}},onWireReshape:(index,points)=>commit(editWireRoute(S.spec,index,points),'Reshaped schematic wire'),onWireNodeSelect:selectWireNode,onWireNodeMove:(id,point)=>commit(moveWireNode(S.spec,id,point),'Moved wire endpoint'),onWireNodeConnect:id=>{try{handleWireNode(id);}catch(error){fail(error);}},onWireCanvasDoubleClick:point=>{try{handleWireCanvasDoubleClick(point);}catch(error){fail(error);}},
        onBlocked: message => toast(message), onPin:(...args)=>{try{handleSchematicPin(...args);}catch(error){fail(error);}},onWireBend:point=>{try{handleWireBend(point);}catch(error){fail(error);}}, onZoom: z => $('#zoomReset').textContent = `${Math.round(z * 100)}%`,
        onMove: (ref, x, y, mode, symbolKey) => {
          let next;
          if (mode === 'schematic') { next = structuredClone(S.spec); next.editor ||= {}; next.editor.positions ||= {}; next.editor.positions[symbolKey||ref] = [x, y]; }
          else { const c = S.spec.components.find(c => c.ref === ref); next = updateComponent(S.spec, ref, { placement: { ...c.placement, x_mm: +x.toFixed(2), y_mm: +y.toFixed(2) } }); }
          commit(next, `Moved ${ref}`);
        } };
      S.canvas = new DesignCanvas(host,S.spec,options);
      S.canvas.workbenchKey=planarKey();
      if(S.active==='schematic')restoreSchematicWire();
      S.canvas.grid(S.grid); S.canvas.hiddenLayers = S.hiddenLayers;
      displayUI.apply();
      collaborationUI.markers(S.canvas);
      collaborationUI.presenceMarkers(S.canvas);
      if (S.active === 'layout' && S.hiddenLayers.size) S.canvas.render();
      if (S.active === 'layout') renderNativeLayout(token).catch(error => { if (token === S.viewToken) console.warn(error.message); });
      if(S.active==='schematic')renderNativeSchematic(token,options).catch(error=>{if(token===S.viewToken)console.warn(error.message);});
    }
  } else if (S.active === '3d') render3D();
  else if (['components', 'bom', 'nets'].includes(S.active)) renderTable();
  else if (S.active === 'files') renderFiles().catch(fail);
  else if (S.active === 'blocks') renderBlocks();
  else if (S.active === 'review') renderReview();
  else if (S.active === 'simulation') renderSimulation().catch(fail);
  else if (S.active === 'pins') renderPins().catch(fail);
  else if (S.active === 'buses') busesUI.render(host).catch(fail);
  else if (S.active === 'rules') renderRules();
  else if (S.active === 'knowledge') renderKnowledge().catch(fail);
  else if (S.active === 'library') libraryUI.render(host);
  displayUI.apply();cadUI.apply();
}

async function renderNativeSchematic(token,options){
  const data=await api('/api/workbench/schematic-view',{method:'POST',body:S.spec});
  const apply=()=>{
    if(token!==S.viewToken||S.active!=='schematic')return;
    if(S.canvas?.interacting){S.canvas.options.onIdle=apply;return;}
    S.schematicData=data;S.schematicSpecObject=S.spec;
    if(!data.sheets.some(s=>s.name===(S.schematicSheet||'')))changeSchematicSheet('');
    disposeCanvas();
    S.canvas=new DesignCanvas($('#viewContent'),S.spec,{...options,camera:S.planarCameras?.get(planarKey()),selection:[...S.selection],selected:S.selected,selectedKey:S.selectedSymbolKey,selectedWire:S.selectedWireIndex,selectedWireNode:S.selectedWireNode,nativeScene:data,sheet:S.schematicSheet||'',selectedSheet:S.selectedSheet,onSheet:openSchematicSheet,onSheetSelect:id=>sheetsUI.select(id),onSheetChange:(id,patch)=>{try{sheetsUI.change(id,patch);}catch(error){fail(error);}}});
    S.canvas.workbenchKey=planarKey();
    S.canvas.svg.dataset.schematicHash=data.fingerprint;
    S.canvas.grid(S.grid);
    displayUI.apply();
    if(!S.spec.components.length&&!data.wires.length&&!data.sheet_nodes.length){const guide=document.createElement('div');guide.className='empty-canvas schematic-empty-guide';guide.innerHTML=`${icon('schematic')}<h2>Your next idea starts here</h2><p>Describe what you want to build in Chat, or add a component from the library.</p><button class="secondary-button" id="emptyAddPart">${icon('plus')}Add a component</button>`;$('#viewContent').append(guide);$('#emptyAddPart').onclick=()=>toggleDrawer('library');}
    collaborationUI.markers(S.canvas);
    collaborationUI.presenceMarkers(S.canvas);
    restoreSchematicWire();
    const unresolved=data.routes.filter(r=>r.sheet===(S.schematicSheet||'')&&r.status!=='routed');
    if(unresolved.length){const note=document.createElement('div');note.className='view-badge schematic-route-status';note.textContent=`${unresolved.length} wire route${unresolved.length===1?'':'s'} need adjustment · electrical links retained by labels`;note.title=unresolved.map(r=>r.reason).join('\n');$('#viewContent').append(note);}
    if(S.selectedSheet||S.selectedWireIndex!==null&&S.selectedWireIndex!==undefined)renderInspector();
    sheetsUI.picker($('#viewContent'));
    moduleUpdatesUI.mount();objectsUI.refresh();
  };
  apply();
}
function changeSchematicSheet(name){if((S.schematicSheet||'')!==(name||'')){componentHotkeys.cancel();selectionTransformsUI.cancel();markupUI.cancel('view');}S.schematicSheet=name||'';}
function openSchematicSheet(name){cancelSchematicWire();sheetsUI.clear();changeSchematicSheet(name);publishPresence(null);updateContext();renderInspector();renderView();}

async function renderNativeLayout(token) {
  await save();
  if (token !== S.viewToken || S.active !== 'layout' || busy()) return;
  const result=await api(`/api/workbench/projects/${S.pid}/layout-geometry`),geo=result.geometry,native=result.native,ratsnest=result.source!=='routed';
  if (token !== S.viewToken || S.active !== 'layout') return;
  if(result.source_version!==S.version)throw Error('The layout changed while its geometry loaded. Open Layout again.');
  if(native)S.project.workbench_native = native; disposeCanvas();
  $('#viewContent').innerHTML = `<div class="boardview" id="nativeBoard"></div><div class="view-badge">${icon('board')}KiCad footprints · ${geo.tracks.length} tracks · ${geo.vias.length} vias${native?.validation.errors.length ? ` · ${native.validation.errors.length} placement issues` : ''}</div>`;
  mountNativeBoard(geo,ratsnest,false,layoutIdentity(result),result.routing_profiles);if(S.selectedCopper)renderInspector();applyAccessUI();
}
function layoutIdentity(data){return{source_version:data.source_version,pcb_sha256:data.pcb_sha256,render_inputs_sha256:data.render_inputs_sha256,source:data.source};}
function mountNativeBoard(geo,ratsnest=true,pending=false,identity=null,profiles=null){
  S.nativePending=pending;
  S.routingProfiles=profiles||{schema:1,pairs:[],issues:[]};
  let mountedCanvas;const host=$('#nativeBoard'),owner={pid:S.pid,load:S.projectLoadToken,view:S.viewToken,user:S.session?.user?.id||S.project.access?.user?.id||'device'},current=()=>host.isConnected&&S.canvas===mountedCanvas&&S.pid===owner.pid&&S.projectLoadToken===owner.load&&S.viewToken===owner.view&&(S.session?.user?.id||S.project.access?.user?.id||'device')===owner.user&&S.active==='layout';host.dataset.updating=String(pending);host.dataset.designVersion=String(pending?S.lastLayout?.version||0:S.version);
  S.canvas = mountedCanvas = new window.BoardView(host, geo, { compact: true, ratsnest, editable: true, readOnly:!editable()||pending&&!routingUI.optimistic,camera:S.planarCameras?.get(planarKey()),grid:S.grid,gridMm:S.boardGrid,
    locked: new Set(S.spec.components.filter(c=>c.placement?.locked).map(c=>c.ref)), onSelect: selectComponent,onSelection:selectMultiple,onMoveMany:moves=>commit(moveSelection(S.spec,moves,'layout'),`Moved ${moves.length} components`),
    onCopperSelect:selectCopper,onCopperPreview:(selection,patch,source)=>previewCopper(S.spec,source,selection,patch),onCopperEdit:(selection,patch,source)=>{try{changeCopper(patch,source,selection);}catch(error){fail(error);}},onCopperError:fail,
    isVisible:(kind,item)=>objectsUI.visible(kind,item),canEditSelection:()=>objectsUI.canEdit,onObjectSelect:item=>objectsUI.pickNative(item.collection,item.id,item.ref),
    onSelectionBlocked:()=>toast('This selection cannot be moved together. Select one editable object or only components.',true),
    onRoutingTarget:(target,event)=>{if(current())routingUI.guard(()=>routingUI.target(target,event));},onRoutingPoint:(x,y,event)=>{if(current())routingUI.guard(()=>routingUI.point(x,y,event));},onRoutingPointer:(x,y,event)=>{if(current())routingUI.pointer(x,y,event);},routePreview:(world,target)=>current()?routingUI.preview(world,target):null,routePoints,
    onZoom: z => $('#zoomReset').textContent = `${Math.round(z*100)}%`,
    onMove: (ref,x,y) => { const c=S.spec.components.find(c=>c.ref===ref); commit(updateComponent(S.spec,ref,{placement:{...c.placement,x_mm:+x.toFixed(2),y_mm:+y.toFixed(2)}}),`Moved ${ref}`); },
    onPoint:(x,y)=>{
      if(!S.viaPlacing||!editable()||S.nativePending)return;
      try{const {net,diameter,drill}=S.viaPlacing,[ox,oy]=geo.bbox;const next=addVia(S.spec,net,[x-ox,y-oy],{diameter,drill});S.viaPlacing=null;$('#viaButton').setAttribute('aria-pressed','false');commit(next,'Placed through via');toast('Via saved. Run DRC to check clearances.');}catch(error){fail(error);}
    } });
  S.canvas.workbenchKey=planarKey();S.canvas.routing = S.routing || false; S.canvas.select(S.selected);S.canvas.selectMany?.([...S.selection].map(key=>key.split('#')[0]));
  if(S.selectedCopper)S.canvas.selectCopper(S.selectedCopper);
  S.canvas.sceneProject=S.pid;S.canvas.sceneVersion=Number(host.dataset.designVersion);S.canvas.baseRatsnest=ratsnest;
  S.canvas.placingVia=!!S.viaPlacing;S.canvas.routingLayer=S.routingLayer||'F.Cu';
  for(const key of S.hiddenLayers) S.canvas.layers.delete(key);
  for(const [key,visible]of S.layerOverrides||[])visible?S.canvas.layers.add(key):S.canvas.layers.delete(key);
  layersUI.attach(S.canvas,identity);
  if(toolDock.has('layers')&&!$('#pcbLayerTree'))refreshLayerPane();
  S.canvas.draw();
  routingUI.sync();
  collaborationUI.presenceMarkers(S.canvas);
  objectsUI.refresh();
}
function selectComponent(ref,options={}) {
  clearObjectContext();
  S.selectedSheet=null;S.selectedWireNode=null;if(S.canvas?.options)S.canvas.options.selectedWireNode=null;S.canvas?.selectSheet?.(null);
  S.selectedCopper=null;if(S.canvas?.geo)S.canvas.copperSelection=null;
  S.selectedWireIndex=null;S.canvas?.selectWire?.(null);
  const key=options.symbolKey||ref;
  if(options.additive){const keys=new Set(S.selection);keys.has(key)?keys.delete(key):keys.add(key);options.selection=[...keys];if(!keys.has(key)){const last=[...keys].at(-1);ref=last?.split('#')[0]||null;options.symbolKey=last||null;}}
  S.selection=new Set(options.selection||(ref?[key]:[]));
  S.selected = ref; S.selectedNet = null;busesUI.reconcile();
  S.selectedSymbolKey=options.symbolKey||ref;
  if (ref) S.inspector = true;
  if(ref&&S.active==='schematic'&&S.schematicData){const instance=S.schematicData.symbols.find(s=>s.ref===ref&&(!options.symbolKey||s.key===options.symbolKey));if(instance&&instance.sheet!==(S.schematicSheet||'')){changeSchematicSheet(instance.sheet);renderView();}}
  S.canvas?.select?.(ref,options);S.canvas?.selectMany?.([...S.selection]); renderInspector(); updateContext();
  publishPresence();
  if (toolDock.has('objects')) objectsUI.sync();
  $$('.design-table tr[data-ref]').forEach(tr => tr.classList.toggle('selected', tr.dataset.ref === ref));
}
function selectMultiple(keys,primary){primary=keys.includes(primary)?primary:keys.at(-1)||null;selectComponent(primary?.split('#')[0]||null,{symbolKey:primary,selection:keys});}
function selectNet(name,wireIndex=null) { clearObjectContext();S.selectedSheet=null;S.selectedWireNode=null;if(S.canvas?.options)S.canvas.options.selectedWireNode=null;S.canvas?.selectSheet?.(null);S.selectedCopper=null;S.selection.clear();S.selectedWireIndex=wireIndex;S.selectedNet = name; S.selected = null;S.canvas?.select?.(null);S.canvas?.selectWire?.(wireIndex); S.inspector = true; renderInspector(); updateContext(); }
function copperSelection(){
  if(S.active!=='layout'||!S.selectedCopper)return null;
  const geometry=S.canvas?.geo||S.lastLayout?.geo,item=geometry?.[S.selectedCopper.kind]?.find(item=>item.id===S.selectedCopper.id);
  return item?{geometry,item,kind:S.selectedCopper.kind}:null;
}
function selectCopper(selection){
  clearObjectContext();
  S.selectedCopper=selection;S.selection.clear();S.selected=null;S.selectedSymbolKey=null;S.selectedWireIndex=null;
  const chosen=copperSelection();S.selectedNet=chosen?.item.net||null;S.inspector=true;renderInspector();updateContext();publishPresence();
}
function changeCopper(patch,source=S.canvas?.geo,selection=S.selectedCopper){
  if(!editable()||S.nativePending||busy())throw new Error('Wait for the current layout before editing copper.');
  if(!source||!selection)throw new Error('Select a copper object first.');
  const next=editCopper(S.spec,source,selection,patch);
  if(S.canvas?.geo)S.canvas.geo=previewCopper(S.spec,source,selection,patch);
  if(patch===null)S.selectedCopper=null;
  commit(next,patch===null?'Deleted copper object':'Edited PCB copper',null);
}
function selectWire(index,at){const route=S.schematicData?.routes.find(r=>r.index===index&&r.sheet===(S.schematicSheet||''));if(route){selectNet(route.net,index);S.selectedWirePoint=at;}}
function selectWireNode(id){const node=S.spec.editor?.wire_nodes?.[id];if(!node)return;selectNet(node.net);S.selectedWireNode=id;if(S.canvas?.options)S.canvas.options.selectedWireNode=id;S.canvas?.drawConnections?.();renderInspector();}
function updateContext() {
  const objects=S.objectOnlySelection?.scope===objectsUI.scope?objectsUI.chosen:[];
  $('#contextChip').hidden = !S.selected && !S.selectedNet&&!objects.length;
  $('#contextLabel').textContent = objects.length?objects.length>1?`${objects.length} selected`:objects[0].label:S.selection.size>1?`${S.selection.size} selected`:S.selected || S.selectedNet || '';
  if($('#newCommentAnchor'))$('#newCommentAnchor').textContent=S.selected?`Comment on ${S.selected}`:S.selectedNet?`Comment on ${S.selectedNet}`:'Project comment';
}
function wireEndpointLabel(route,key){
  const join=route[key+'_join']||route.joins?.[key];if(!join)return route[key].startsWith('node:')?'Wire endpoint':route[key];
  const parent=S.spec.editor?.connection_guides?.find(guide=>guide.id===join.wire);
  const label=a=>a.startsWith('node:')?'wire endpoint':a;return parent?`Junction on ${label(parent.from)} ↔ ${label(parent.to)}`:'Wire junction';
}
function renderInspector() {
  if(S.starting||S.openingProject){$('#inspector').hidden=true;$('#projectDock').hidden=true;return;}
  objectsUI.sync();layoutPadUI.reconcile();
  const host = $('#inspector'); host.hidden = !S.inspector; $('#projectDock').hidden = S.inspector||['library','symbol'].includes(S.active);
  $('#viewContent').classList.toggle('inspecting', S.inspector); if (!S.inspector) return;
  const c = S.spec.components.find(c => c.ref === S.selected), net = S.spec.nets.find(n => n.name === S.selectedNet),copper=copperSelection();
  const field = (label, key, value, type = 'text') => `<label class="property-row"><span>${label}</span><input data-property="${key}" value="${esc(value ?? '')}" type="${type}" ${type === 'number' ? 'step="any"' : ''}></label>`;
  let body;
  const selectedNode=S.spec.editor?.wire_nodes?.[S.selectedWireNode];
  const objectInspector=objectsUI.inspector();
  if(objectInspector)body=objectInspector;
  else if(selectedNode?.label)body=netLabelsUI.inspector(S.selectedWireNode,selectedNode);
  else if(selectedNode)body=`<div class="inspector-name"><span class="part-badge">${icon('link')}</span><div class="name-stack"><strong>Wire endpoint</strong><small>${esc(selectedNode.net)}</small></div></div><section class="inspector-section"><h3>Position</h3>${['X','Y'].map((name,i)=>`<label class="property-row"><span>${name}</span><input type="number" step="10" data-wire-node-axis="${i}" value="${selectedNode.position[i]}"></label>`).join('')}<p>Schematic node · no component or PCB pad.</p><button class="secondary-button" id="startWireFromNode">Draw from endpoint</button><button class="secondary-button" id="inspectWireNodeNet">Inspect net</button><button class="secondary-button" id="labelWireNode">Place net label</button></section><section class="inspector-section"><button class="secondary-button danger-text" id="removeWireNode">Remove endpoint and wire drawings</button><p>Named pin connections stay intact. Disconnect pins to change the electrical net.</p></section>`;
  else if(S.selectedSheet&&sheetDefinitions(S.spec)[S.selectedSheet])body=sheetsUI.inspector();
  else if(copper){
    const {item,kind,geometry}=copper,[ox,oy]=geometry.bbox||[100,100];
    const input=(label,key,value)=>`<label class="property-row"><span>${label}</span><input type="number" step="any" data-copper-property="${key}" value="${value}"></label>`;
    body=`<div class="inspector-name"><span class="part-badge">${icon(kind==='vias'?'via':'link')}</span><div class="name-stack"><strong>${kind==='vias'?'Via':kind==='arcs'?'Copper arc':'Copper trace'}</strong><small>${esc(item.net)}</small></div></div><section class="inspector-section"><h3>Properties</h3><div class="property-row"><span>Net</span><span>${esc(item.net)}</span></div>${kind==='vias'?input('Diameter (mm)','d',item.d)+input('Drill (mm)','drill',item.drill)+`<div class="property-row"><span>Layers</span><span>${esc((item.layers||['F.Cu','B.Cu']).join(' → '))}</span></div>`:input('Width (mm)','w',item.w)+`<label class="property-row"><span>Layer</span><select data-copper-property="layer">${copperLayers(S.spec).map(layer=>`<option ${item.layer===layer?'selected':''}>${esc(layer)}</option>`).join('')}</select></label>`}</section><section class="inspector-section"><h3>${kind==='vias'?'Position':'Vertices'}</h3>${(kind==='vias'?['p']:kind==='arcs'?['a','m','b']:['a','b']).map(key=>`<h4>${{a:'Start',m:'Arc midpoint',b:'End',p:'Center'}[key]}</h4>${input('X (mm)',key+'.0',+(item[key][0]-ox).toFixed(4))}${input('Y (mm)',key+'.1',+(item[key][1]-oy).toFixed(4))}`).join('')}<p>Drag the square handles to move a vertex. Attached copper on the same net moves with it.</p><div class="copper-properties-actions">${kind==='tracks'?'<button class="secondary-button" id="splitCopperTrace">Add midpoint</button>':''}<button class="secondary-button danger-text" id="deleteCopperObject">Delete ${kind==='vias'?'via':'segment'}</button></div></section>`;
  }else if(S.selection.size>1){
    const refs=[...new Set([...S.selection].map(key=>key.split('#')[0]))];
    body=`<div class="inspector-name"><span class="part-badge">${icon('shapes')}</span><div class="name-stack"><strong>${S.selection.size} objects selected</strong><small>${refs.length} components</small></div></div><section class="inspector-section"><h3>Selection</h3>${refs.map(ref=>`<div class="pin-row"><span>${esc(ref)}</span><span>${esc(S.spec.components.find(c=>c.ref===ref)?.value)}</span></div>`).join('')}</section><section class="inspector-section"><h3>Move selection (${S.active==='layout'?'mm':'schematic units'})</h3><label class="property-row"><span>Δ X</span><input id="selectionDx" type="number" step="any" value="0"></label><label class="property-row"><span>Δ Y</span><input id="selectionDy" type="number" step="any" value="0"></label><button class="secondary-button" id="moveSelectionButton">Move selected objects</button></section><section class="inspector-section"><button class="secondary-button" id="duplicateSelectionButton">${icon('plus')}Duplicate</button><p>Copy keeps shared power nets and gives copied signal nets new names.</p></section>`;
  }else if(c?.terminal){body=terminalsUI.inspector(c,field);
  }else if (c) {
    body = `<div class="inspector-name"><span class="part-badge">${icon(c.ref.startsWith('R') ? 'resistor' : c.ref.startsWith('C') ? 'capacitor' : 'chip')}</span><div class="name-stack"><strong>${esc(c.ref)}</strong><small>${esc(c.value)}</small></div></div>
      <section class="inspector-section"><h3>Properties</h3>${field('Designator', 'ref', c.ref)}${field('Value', 'value', c.value)}${field('MPN', 'mpn', c.mpn)}${field('LCSC part', 'lcsc', c.lcsc)}${field('Footprint', 'footprint', c.footprint)}${field('Symbol','symbol',c.symbol)}<button class="secondary-button" id="editComponentSymbol">Edit symbol</button></section>
      <section class="inspector-section"><h3>Description</h3><textarea class="inspector-description" data-property="description" aria-label="Component description">${esc(c.description || '')}</textarea></section>
      <section class="inspector-section"><h3>PCB placement</h3>${field('X (mm)', 'placement.x_mm', c.placement?.x_mm ?? 0, 'number')}${field('Y (mm)', 'placement.y_mm', c.placement?.y_mm ?? 0, 'number')}${field('Rotation (°)', 'placement.rotation', c.placement?.rotation ?? 0, 'number')}<label class="property-row"><span>Locked</span><select data-property="placement.locked"><option value="false" ${!c.placement?.locked ? 'selected' : ''}>Unlocked</option><option value="true" ${c.placement?.locked ? 'selected' : ''}>Locked</option></select></label></section>
      <section class="inspector-section"><h3>Connected pins <span class="muted">${componentPins(S.spec, c.ref).length}</span></h3>${componentPins(S.spec, c.ref).map(p => `<div class="pin-row"><span>Pin ${esc(p.pin)}</span><span>${esc(p.net)}</span></div>`).join('') || '<p>No connections yet</p>'}</section>
      <section class="inspector-section"><h3>Pricing & availability</h3><div id="partSourcing"><p>Supplier data is fetched live when requested.</p>${c.lcsc?'<button class="secondary-button" id="checkPartStock">Check price & stock</button>':''}</div></section>`;
  } else if (net) {
    body = `<div class="inspector-name"><span class="part-badge">${icon('schematic')}</span><div class="name-stack"><strong>${esc(net.name)}</strong><small>${net.pins.length} connected pins</small></div></div><section class="inspector-section"><h3>Net properties</h3><div class="property-row"><span>Class</span><div>${esc(net.class || 'signal')}</div></div>${net.pins.map(p => `<button class="object-row" data-select-ref="${esc(p.split('.')[0])}">${icon('chip')}${esc(p)}</button>`).join('')}<button class="secondary-button" id="editNetConnections">${icon('link')}Edit connections</button></section>`;
    const route=S.schematicData?.routes.find(r=>r.index===S.selectedWireIndex&&r.sheet===(S.schematicSheet||''));
    if(route){const bends=S.spec.editor?.connection_guides?.[route.index]?.waypoints||[];body+=`<section class="inspector-section"><h3>Wire route</h3><p>${esc(wireEndpointLabel(route,'from'))} → ${esc(wireEndpointLabel(route,'to'))}</p><p class="${route.status==='routed'?'':'wire-route-warning'}">${route.status==='routed'?'Native wire · drag the square handles to move a segment.':esc(route.reason||'Route needs adjustment')}</p>${bends.map((p,i)=>`<div class="wire-bend-row"><span>${i+1}</span><label>X<input type="number" step="5" data-wire-point="${i}" data-wire-axis="0" value="${p[0]}"></label><label>Y<input type="number" step="5" data-wire-point="${i}" data-wire-axis="1" value="${p[1]}"></label></div>`).join('')}<div class="wire-route-actions"><button class="secondary-button" id="addWireBend">Add bend pair</button><button class="secondary-button" id="resetWireRoute">Auto-route</button><button class="secondary-button" id="splitSchematicWire">Split at selected point</button><button class="secondary-button" id="labelSelectedWire">Place net label</button><button class="secondary-button" id="cutSchematicWire">Cut wire…</button><button class="secondary-button" id="wireConnectionActions">Disconnect…</button></div><div class="wire-pin-actions">${[...new Set([logicalPin(route.from),logicalPin(route.to)])].filter(pin=>S.spec.components.some(c=>c.ref===pin.split('.')[0])).map(pin=>`<button class="asset-text-button" data-disconnect-pin="${esc(pin)}">Disconnect ${esc(pin)}</button>`).join('')}</div></section>`;}
  } else {
    const b = S.spec.board;
    body = `<div class="inspector-name"><span class="part-badge">${icon('folder')}</span><div class="name-stack"><strong>${esc(getTitle())}</strong><small>Local project</small></div></div>
      <section class="inspector-section"><h3>Description</h3><textarea class="inspector-description" data-board-property="summary" aria-label="Project description">${esc(S.spec.summary || '')}</textarea></section>
      <section class="inspector-section"><h3>Board properties</h3>${field('Width (mm)', 'board.width_mm', b.width_mm, 'number')}${field('Height (mm)', 'board.height_mm', b.height_mm, 'number')}${field('Thickness', 'board.thickness_mm', b.thickness_mm || 1.6, 'number')}<label class="property-row"><span>Copper layers</span><select data-property="board.layers">${[2,4,6,8].map(n => `<option ${n === b.layers ? 'selected' : ''}>${n}</option>`).join('')}</select></label></section>
      <section class="inspector-section"><h3>Project objects</h3><div class="pin-row"><span>Components</span><span>${S.spec.components.length}</span></div><div class="pin-row"><span>Nets</span><span>${S.spec.nets.length}</span></div><div class="pin-row"><span>Saved version</span><span>${S.version || 'Reference'}</span></div></section><section class="inspector-section"><h3>Manufacturing</h3><p>${busy() ? 'A OpenFabro build is running.' : 'Changes need a native build and ERC / DRC checks before manufacturing.'}</p><button class="secondary-button" id="inspectBuild">${icon('play')}Build project</button></section>`;
    if(S.active==='3d'&&S.enclosure){
      const enc=S.enclosureDraft||S.project.enclosure_spec||{wall_mm:2,floor_mm:1.6,lid_mm:1.6,gap_mm:.6,headroom_mm:2,corner_radius_mm:2};
      body+=`<section class="inspector-section"><h3>Enclosure parameters</h3>${[['wall_mm','Wall (mm)'],['floor_mm','Floor (mm)'],['lid_mm','Lid (mm)'],['gap_mm','Fit gap (mm)'],['headroom_mm','Headroom'],['corner_radius_mm','Corner radius']].map(([key,label])=>`<label class="property-row"><span>${label}</span><input type="number" min="0.1" step="0.1" data-enclosure-property="${key}" value="${esc(enc[key])}"></label>`).join('')}<button class="secondary-button" id="rebuildEnclosureParameters">Rebuild FreeCAD model</button>${S.project.workbench_enclosure?.summary?`<p>Outer size: ${S.project.workbench_enclosure.summary.outer_mm.map(n=>Number(n).toFixed(1)).join(' × ')} mm</p><p>${S.project.workbench_enclosure.summary.collisions?.length||0} geometry collisions reported. Check estimated component heights.</p>`:''}</section>`;
    }
  }
  body+=sheetsUI.selection();
  if(S.selection.size&&['schematic','layout'].includes(S.active))body+='<section class="inspector-section"><button class="secondary-button" id="convertSelectionComponent">Convert to Component</button></section>';
  if(c)body+=busesUI.componentHTML(c);
  if(S.selection.size&&['schematic','layout'].includes(S.active))body+=selectionTransformsUI.inspector();
  if(S.active==='layout'&&copper)body+=`<section class="inspector-section"><h3>Automatic routing</h3><label class="property-row"><span>Protect copper</span><input id="copperProtected" type="checkbox" ${copper.item.locked!==false?'checked':''}></label><p>Protected copper stays fixed during automatic routing and repairs.</p></section>`;
  if(S.active==='layout'&&(copper||net))body+=routeTuningUI.inspectorHTML();
  host.innerHTML = `<div class="inspector-heading"><span>Inspect</span><button class="icon-button" id="closeInspector" aria-label="Close inspector">${icon('minimize')}</button></div><div class="inspector-content">${body}</div>${c ? `<div class="inspector-footer"><button class="secondary-button" id="rotatePart">${icon('rotate')}Rotate right</button><button class="danger-button" id="deletePart">${icon('trash')}Delete</button></div>` : ''}`;
  if(S.active==='layout'&&(copper||net))routeTuningUI.bind(host,copper?.item.net||net.name,copper?.kind==='tracks'?copper.item.id:null);
  selectionTransformsUI.bind(host);
  sheetsUI.bind(host);
  if(c?.terminal)terminalsUI.bind(host,c);
  if(c)busesUI.bindComponent(host,c);
  objectsUI.bindInspector(host);
  host.querySelector('#editComponentSymbol')?.addEventListener('click',()=>openSymbol(c.ref));
  if(selectedNode?.label)netLabelsUI.bindInspector(host,S.selectedWireNode);
  $$('[data-edit-terminal]',host).forEach(button=>button.onclick=safely(()=>terminalsUI.editPort(button.dataset.editTerminal,button.dataset.terminalLabel,button.dataset.terminalRef)));
  const addSheetTerminal=$('[data-add-sheet-terminal]',host);if(addSheetTerminal)addSheetTerminal.onclick=safely(()=>{openSchematicSheet(addSheetTerminal.dataset.addSheetTerminal);return terminalsUI.add();});
  terminalsUI.markBusy();
  $('#convertSelectionComponent')?.addEventListener('click',()=>moduleConversionUI.openDialog());
  if($('#convertSelectionComponent'))$('#convertSelectionComponent').disabled=!editable()||busy();
  $('#closeInspector').onclick = () => { S.inspector = false; renderInspector(); };
  $('#moveSelectionButton')?.addEventListener('click',safely(()=>moveSelectedBy(Number($('#selectionDx').value),Number($('#selectionDy').value))));
  $('#duplicateSelectionButton')?.addEventListener('click',safely(duplicateSelected));
  $$('[data-property]', host).forEach(input => input.onchange = safely(() => {
    const key = input.dataset.property, value = input.type === 'number' ? Number(input.value) : key === 'placement.locked' ? input.value === 'true' : key === 'board.layers' ? Number(input.value) : input.value;
    if (key.startsWith('board.')) {
      if (!Number.isFinite(value) || value <= 0 || value > 2000) { renderInspector(); throw new Error('Use a positive board dimension up to 2000 mm.'); }
      const next = structuredClone(S.spec); next.board[key.slice(6)] = value; commit(next, `Updated ${key.slice(6)}`);
    } else if (c) {
      const patch = key.startsWith('placement.') ? { placement: { ...c.placement, [key.slice(10)]: value } } : { [key]: value };
      commit(updateComponent(S.spec, c.ref, patch), `Updated ${c.ref} ${key}`, patch.ref || c.ref);
    }
  }));
  $('[data-board-property]', host)?.addEventListener('change', e => { const next = structuredClone(S.spec); next.summary = e.target.value; commit(next, 'Updated project description'); });
  $$('[data-select-ref]', host).forEach(b => b.onclick = () => selectComponent(b.dataset.selectRef));
  $('#rotatePart')?.addEventListener('click', rotatePart); $('#deletePart')?.addEventListener('click', deletePart);
  $('#inspectBuild')?.addEventListener('click', safely(buildProject));
  $('#editNetConnections')?.addEventListener('click', () => openNetEditor(net.name));
  $('#wireConnectionActions')?.addEventListener('click',openWireDisconnect);
  $$('[data-disconnect-pin]',host).forEach(button=>button.onclick=()=>disconnectSchematicPin(button.dataset.disconnectPin));
  $$('[data-copper-property]',host).forEach(input=>input.onchange=safely(()=>{
    const selected=copperSelection();if(!selected)throw new Error('Select this copper object again.');
    const key=input.dataset.copperProperty;let patch;
    if(key.includes('.')){const [point,axis]=key.split('.'),[ox,oy]=selected.geometry.bbox||[100,100],p=[selected.item[point][0]-ox,selected.item[point][1]-oy];p[Number(axis)]=Number(input.value);patch={[point]:p};}
    else patch={[key]:key==='layer'?input.value:Number(input.value)};
    changeCopper(patch);
  }));
  $('#splitCopperTrace')?.addEventListener('click',safely(()=>{const {item,geometry}=copperSelection(),[ox,oy]=geometry.bbox||[100,100];changeCopper({split:[(item.a[0]+item.b[0])/2-ox,(item.a[1]+item.b[1])/2-oy]});}));
  $('#deleteCopperObject')?.addEventListener('click',safely(()=>changeCopper(null)));
  $('#copperProtected')?.addEventListener('change',safely(event=>changeCopper({locked:event.target.checked})));
  if($('#copperProtected'))$('#copperProtected').disabled=!editable()||S.nativePending||busy();
  if(!editable()||S.nativePending)$$('[data-copper-property],#splitCopperTrace,#deleteCopperObject',host).forEach(input=>input.disabled=true);
  $$('[data-wire-point]',host).forEach(input=>input.onchange=safely(()=>{const bends=structuredClone(S.spec.editor.connection_guides[S.selectedWireIndex].waypoints);bends[Number(input.dataset.wirePoint)][Number(input.dataset.wireAxis)]=Number(input.value);commit(editWireRoute(S.spec,S.selectedWireIndex,bends),'Moved wire bend');}));
  $$('[data-wire-node-axis]',host).forEach(input=>input.onchange=safely(()=>{const point=[...S.spec.editor.wire_nodes[S.selectedWireNode].position];point[Number(input.dataset.wireNodeAxis)]=Number(input.value);commit(moveWireNode(S.spec,S.selectedWireNode,point),'Moved wire endpoint');}));
  $('#startWireFromNode')?.addEventListener('click',safely(()=>{if(!S.schematicWiring)$('#wireButton').click();handleWireNode(S.selectedWireNode);}));
  $('#removeWireNode')?.addEventListener('click',safely(removeSelectedWireNode));
  $('#labelWireNode')?.addEventListener('click',safely(()=>netLabelsUI.open({action:'add',id:S.selectedWireNode,net:selectedNode.net,position:selectedNode.position})));
  $('#labelSelectedWire')?.addEventListener('click',safely(labelSelectedWire));
  $('#inspectWireNodeNet')?.addEventListener('click',()=>selectNet(selectedNode.net));
  $('#splitSchematicWire')?.addEventListener('click',safely(splitSelectedSchematicWire));
  $('#cutSchematicWire')?.addEventListener('click',safely(()=>wireCutsUI.open()));
  $('#resetWireRoute')?.addEventListener('click',()=>commit(editWireRoute(S.spec,S.selectedWireIndex,[]),'Auto-routed schematic wire'));
  $('#addWireBend')?.addEventListener('click',safely(()=>{const route=S.schematicData.routes.find(r=>r.index===S.selectedWireIndex&&r.sheet===(S.schematicSheet||''));if(!route?.points?.length)throw new Error('Auto-route this connection before adding a bend.');const points=structuredClone(route.points);let longest=0;for(let i=1;i<points.length-1;i++)if(Math.hypot(points[i][0]-points[i-1][0],points[i][1]-points[i-1][1])>Math.hypot(points[longest+1][0]-points[longest][0],points[longest+1][1]-points[longest][1]))longest=i-1;const a=points[longest],b=points[longest+1],h=Math.abs(a[1]-b[1])<.001;points.splice(longest+1,0,[a[0]+(b[0]-a[0])/3+(h?0:30),a[1]+(b[1]-a[1])/3+(h?30:0)],[a[0]+2*(b[0]-a[0])/3+(h?0:30),a[1]+2*(b[1]-a[1])/3+(h?30:0)]);commit(editWireRoute(S.spec,S.selectedWireIndex,points.slice(1,-1)),'Added wire bend pair');}));
  $$('[data-enclosure-property]',host).forEach(input=>input.onchange=()=>{S.enclosureDraft=structuredClone(S.enclosureDraft||S.project.enclosure_spec||{wall_mm:2,floor_mm:1.6,lid_mm:1.6,gap_mm:.6,headroom_mm:2,corner_radius_mm:2});S.enclosureDraft[input.dataset.enclosureProperty]=Number(input.value);});
  $('#rebuildEnclosureParameters')?.addEventListener('click',safely(()=>runEngineering('enclosure',{spec:S.enclosureDraft||S.project.enclosure_spec})));
  $('#checkPartStock')?.addEventListener('click',safely(async()=>{const data=await api(`/api/workbench/parts/${encodeURIComponent(c.lcsc)}`);if(S.selected!==c.ref)return;$('#partSourcing').innerHTML=`<div class="pin-row"><span>Supplier</span><span>LCSC</span></div><div class="pin-row"><span>In stock</span><span>${Number(data.stock||0).toLocaleString()}</span></div><div class="pin-row"><span>MPN</span><span>${esc(data.mpn)}</span></div><p>${esc(data.description||'')}</p><p class="small muted">Live supplier lookup · verify again before ordering.</p>`;}));
  if(!editable())$$('[data-property],[data-board-property],[data-enclosure-property],[data-wire-point],[data-disconnect-pin],#wireConnectionActions,#resetWireRoute,#addWireBend,#rotatePart,#deletePart,#inspectBuild,#rebuildEnclosureParameters,#editNetConnections,#moveSelectionButton,#duplicateSelectionButton',host).forEach(input=>input.disabled=true);
  if(!editable())$$('[data-wire-node-axis],#startWireFromNode,#splitSchematicWire,#cutSchematicWire,#removeWireNode',host).forEach(input=>input.disabled=true);
}
function rotatePart() {
  return selectionTransformsUI.run('rotate',{angle:90});
}
function deletePart() {
  if(!editable())return;
  const refs=selectedRefs();if(!refs.length)return;
  if(refs.length===1&&S.spec.components.find(c=>c.ref===refs[0])?.terminal){terminalsUI.remove(refs[0]).catch(fail);return;}
  commit(refs.reduce((spec,ref)=>removeComponent(spec,ref),S.spec),`Removed ${refs.join(', ')}`,null);toast(`${refs.length} component${refs.length===1?'':'s'} removed. ⌘Z to undo.`);
}

function selectedRefs(){return[...new Set([...S.selection].map(key=>key.split('#')[0]))];}
function selectionClipboard(){
  const spec=structuredClone(S.spec);spec.editor||={};spec.editor.positions||={};
  for(const instance of S.schematicData?.symbols||[])spec.editor.positions[instance.key]??=instance.position;
  return copySelection(spec,selectedRefs());
}
async function copySelected(){
  const data=selectionClipboard();S.clipboard=data;S.pasteCount=0;
  try{await navigator.clipboard.writeText(JSON.stringify(data));}catch{}
  toast(`${data.components.length} component${data.components.length===1?'':'s'} copied`);return data;
}
async function pasteSelected(clipboard=null){
  if(!editable())throw new Error('Only project editors can paste components.');
  if(!clipboard){let text=null;try{text=await navigator.clipboard.readText();}catch{}if(text){if(text.length>2_000_000)throw new Error('The clipboard selection is too large.');try{clipboard=JSON.parse(text);}catch{throw new Error('The clipboard does not contain copied OpenFabro components.');}}else clipboard=S.clipboard;}
  S.pasteCount=(S.pasteCount||0)+1;const count=S.pasteCount,options={schematicOffset:[40*count,40*count],boardOffset:[count,count],...(S.active==='schematic'?{sheet:S.schematicSheet||''}:{})};
  const result=pasteSelection(S.spec,clipboard,options);S.selection=new Set(result.refs);S.selectedSymbolKey=result.refs.at(-1);commit(result.spec,`Pasted ${result.refs.length} components`,result.refs.at(-1));S.inspector=true;renderInspector();toast('Components pasted. Shared power nets stay connected; signal nets are copied.');
}
async function duplicateSelected(){S.pasteCount=0;await pasteSelected(selectionClipboard());}
function moveSelectedBy(dx,dy){
  if(!['schematic','layout'].includes(S.active))throw new Error('Open Schematic or Layout to move this selection.');
  const moves=[...S.selection].map(key=>{const ref=key.split('#')[0],part=S.spec.components.find(c=>c.ref===ref);const point=S.active==='layout'?[part.placement?.x_mm||0,part.placement?.y_mm||0]:S.spec.editor?.positions?.[key]||S.schematicData?.symbols.find(s=>s.key===key)?.position||[180,220];return{key,x:point[0]+dx,y:point[1]+dy};});
  commit(moveSelection(S.spec,moves,S.active),`Moved ${moves.length} selected objects`);
}
function showCanvasContext(event){
  if(!['schematic','layout'].includes(S.active))return;event.preventDefault();
  if(S.active==='schematic'){
    const pin=event.target.closest('[data-pinref]'),node=event.target.closest('[data-wire-node]');
    if(pin){netLabelsUI.pinMenu(pin.dataset.pinref,pin.dataset.anchor,[event.clientX,event.clientY]);return;}
    if(node){selectWireNode(node.dataset.wireNode);netLabelsUI.open({action:S.spec.editor.wire_nodes[node.dataset.wireNode].label?'update':'add',id:node.dataset.wireNode});return;}
  }
  const element=event.target.closest('[data-ref]');
  if(element){const key=element.dataset.symbolKey||element.dataset.ref;if(!S.selection.has(key))selectComponent(element.dataset.ref,{symbolKey:key});}
  else if(S.canvas?.geo){const[x,y]=S.canvas._world(event),f=S.canvas.geo.footprints.find(f=>f.court&&x>=f.court[0]&&x<=f.court[2]&&y>=f.court[1]&&y<=f.court[3]);if(f&&!S.selection.has(f.ref))selectComponent(f.ref);}
  closeMenus();let menu=$('#canvasContextMenu');if(!menu){menu=document.createElement('div');menu.id='canvasContextMenu';menu.className='popover canvas-context-menu';menu.setAttribute('role','menu');document.body.append(menu);}
  const enabled=S.selection.size>0,edit=editable();
  const actions=[['Copy','copy','⌘C',enabled,copySelected],['Paste','paste','⌘V',edit,()=>pasteSelected()],['Duplicate','duplicate','⌘D',edit&&enabled,duplicateSelected],['Rotate right','rotate',']',edit&&enabled,rotatePart],['Rotate left','rotate-left','[',edit&&enabled,()=>selectionTransformsUI.run('rotate',{angle:-90})],['Rotate right individually','rotate-each','⇧]',edit&&enabled,()=>selectionTransformsUI.run('rotate',{angle:90,individual:true})],['Convert to Component','convert','',edit&&enabled,()=>moduleConversionUI.openDialog()],['Delete','delete','⌫',edit&&enabled,deletePart]];
  if(S.active==='schematic')actions.splice(6,0,['Flip horizontally','flip-horizontal','F',edit&&enabled,()=>selectionTransformsUI.run('flip_horizontal')],['Flip vertically','flip-vertical','⇧F',edit&&enabled,()=>selectionTransformsUI.run('flip_vertical')]);else actions.splice(6,0,['Flip layer','flip-layer','F',edit&&enabled,()=>selectionTransformsUI.run('flip_layer')]);
  actions.splice(actions.findIndex(item=>item[1]==='convert'),0,['Align','arrange','›',edit&&S.selection.size>=2,()=>{}],['Space evenly','space-evenly',S.active==='schematic'?'S':'',edit&&S.selection.size>=3,()=>selectionTransformsUI.run('distribute',{axis:'auto',basis:selectionTransformsUI.basis})]);
  if(S.active==='schematic')actions.splice(actions.findIndex(item=>item[1]==='convert'),0,['Assign component to hotkey','component-hotkeys','›',selectedRefs().length===1,()=>{}]);
  if(S.active==='schematic'){const at=S.canvas?.worldPoint(event),position=at?[at.x,at.y].map(v=>Math.round(v/10)*10):undefined;actions.push(['Place net label','label','',edit,()=>netLabelsUI.open({action:'add',position})],['Place power symbol','power','',edit,()=>netLabelsUI.open({action:'add',position,kind:'power'})],['Place ground symbol','ground','',edit,()=>netLabelsUI.open({action:'add',position,kind:'ground'})]);}
  menu.innerHTML=actions.map(([label,action,key,active])=>`<button role="menuitem" data-canvas-action="${action}" ${active?'':'disabled'}>${esc(label)}<kbd>${esc(key)}</kbd></button>`).join('');
  menu.hidden=false;menu.style.left=`${Math.max(8,Math.min(innerWidth-menu.offsetWidth-8,event.clientX))}px`;menu.style.top=`${Math.max(8,Math.min(innerHeight-menu.offsetHeight-8,event.clientY))}px`;
  actions.forEach(([,action,,,fn])=>$(`[data-canvas-action="${action}"]`,menu).onclick=safely(async()=>{closeMenus();await fn();}));
  const arrange=$('[data-canvas-action="arrange"]',menu);const openArrange=()=>selectionTransformsUI.openArrangeMenu(arrange,closeMenus);arrange.onclick=openArrange;arrange.onmouseenter=openArrange;
  arrange.setAttribute('aria-haspopup','menu');arrange.setAttribute('aria-expanded','false');
  const hotkeys=$('[data-canvas-action="component-hotkeys"]',menu);if(hotkeys){hotkeys.onclick=()=>{selectionTransformsUI.closeArrange();componentHotkeys.openMenu(hotkeys,closeMenus);};hotkeys.setAttribute('aria-haspopup','menu');hotkeys.setAttribute('aria-expanded','false');}
  menu.onpointerover=event=>{if(event.target.closest('button')!==arrange)selectionTransformsUI.closeArrange();if(event.target.closest('button')!==hotkeys)componentHotkeys.closeMenu();};
  menu.onkeydown=event=>{if(['ArrowDown','ArrowUp'].includes(event.key)){event.preventDefault();event.stopPropagation();const buttons=$$('button:not([disabled])',menu),index=buttons.indexOf(document.activeElement);buttons[(index+(event.key==='ArrowDown'?1:-1)+buttons.length)%buttons.length]?.focus();}else if(event.key==='ArrowRight'&&event.target===arrange){event.preventDefault();event.stopPropagation();openArrange();$('#arrangeSelectionMenu button:not([disabled])')?.focus();}else if(event.key==='ArrowRight'&&event.target===hotkeys){event.preventDefault();event.stopPropagation();hotkeys.click();}else if(event.key==='Escape'){event.preventDefault();event.stopPropagation();closeMenus();$('#viewContent').focus();}};
  $('button:not([disabled])',menu)?.focus({preventScroll:true});
}

function openNetEditor(name = null, pin = '') {
  if(!editable()){if(name)selectNet(name);return;}
  const net = S.spec.nets.find(n => n.name === name);
  $('#netForm').dataset.originalName = name || '';
  $('#netDialogTitle').textContent = net ? 'Edit connections' : 'Connect pins';
  $('#netName').value = net?.name || `Net_${S.spec.nets.length + 1}`;
  $('#netClass').value = net?.class || 'signal';
  $('#netPins').value = net ? net.pins.join(', ') : pin;
  $('#netError').textContent = ''; dialog('#netDialog');
}
function saveNet(e) {
  e.preventDefault();
  try {
    const name = $('#netName').value.trim();
    const next = upsertNet(S.spec, { name, class: $('#netClass').value, pins: $('#netPins').value.split(/[,\s]+/).filter(Boolean) }, $('#netForm').dataset.originalName || null);
    commit(next, `Updated net ${name}`); $('#netDialog').close(); selectNet(name); toast('Connections saved');
  } catch (e) { $('#netError').textContent = e.message; }
}

function openViaDialog(){
  if(!editable())return;if((S.spec.board.layers||2)<2)throw new Error('A through via requires at least two copper layers.');
  if(routingUI.active)routingUI.stop();
  $('#viaNet').innerHTML='<option value="">Choose a net</option>'+S.spec.nets.map(net=>`<option value="${esc(net.name)}" ${net.name===S.selectedNet?'selected':''}>${esc(net.name)}</option>`).join('');
  $('#viaDiameter').value=S.spec.rules?.via_diameter_mm||.6;$('#viaDrill').value=S.spec.rules?.via_drill_mm||.3;dialog('#viaDialog');
}
function layerControls(){
  if(S.active==='schematic')return displayUI.panel();
  if(S.active==='3d')return cadUI.panel();
  if(S.active!=='layout')return layersUI.panel();
  const count=S.spec.board.layers||2,copper=['F.Cu',...Array.from({length:Math.max(0,count-2)},(_,i)=>`In${i+1}.Cu`),...(count>1?['B.Cu']:[])];
  return `${layersUI.panel()}<div class="pcb-layer-heading">Routing & grid</div><div class="routing-options"><label>Routing layer<select id="routingLayer">${copper.map(layer=>`<option ${layer===(S.routingLayer||'F.Cu')?'selected':''}>${layer}</option>`).join('')}</select></label><label>Track width (mm)<select id="routingWidth"><option value="0">From net rules</option>${[.15,.2,.25,.35,.5,.75,1,2].map(width=>`<option value="${width}" ${width===S.routingWidth?'selected':''}>${width}</option>`).join('')}</select></label><label>Grid (mm)<select id="boardGrid">${[.01,.05,.1,.25,.5,1,2.54].map(grid=>`<option value="${grid}" ${grid===S.boardGrid?'selected':''}>${grid}</option>`).join('')}</select></label></div>`;
}
function refreshLayerPane(){if(!toolDock.has('layers'))return;const focused=toolDock.model.active;renderDrawer('layers');if(focused&&toolDock.has(focused))toolDock.focus(focused);}
function cancelSchematicWire(){S.wireStart=null;S.wireAnchor=null;S.wireDraft=null;S.wireSpec=null;S.pendingWire=null;S.canvas?.clearWire?.();}
function restoreSchematicWire(){
  if(S.wireStart&&S.wireSpec!==S.spec)cancelSchematicWire();
  if(!S.schematicWiring)return;
  S.canvas.wiringMode=true;S.canvas.svg.classList.add('wire-mode');
  if(S.wireDraft)S.canvas.setWireDraft(S.wireDraft);
}
function schematicAnchor(anchor){return S.canvas?.options.nativeScene?.anchors?.find(a=>a.sheet===(S.schematicSheet||'')&&a.anchor===anchor);}
function beginSchematicWire(endpoint,point){
  if(!S.canvas?.options.nativeScene){toast('Wait for the native schematic before drawing a wire.');return;}
  if(!point)throw new Error('The pin moved. Refresh the schematic before wiring.');
  const native=schematicAnchor(endpoint.anchor);
  S.wireStart=endpoint;S.wireAnchor=endpoint.anchor;S.wireSpec=S.spec;S.wireDraft=new SchematicWireDraft(native?.position||point,{escape:native?.escape});S.canvas.setWireDraft(S.wireDraft);
}
function handleWireBend(point){
  if(!editable()||busy())return;
  if(!S.wireDraft){toast('Double-click the canvas or click a terminal to start drawing.');return;}
  S.wireDraft.bend(point);S.canvas.drawWireDraft();
}
function handleWireCanvasDoubleClick(point){
  if(!editable()||busy())return;point=point.map(v=>Math.round(v/10)*10);
  if(!S.schematicWiring){S.schematicWiring=true;$('#wireButton').setAttribute('aria-pressed','true');restoreSchematicWire();}
  const endpoint={point,sheet:S.schematicSheet||''};
  if(!S.wireStart){beginSchematicWire(endpoint,point);return;}
  if(S.wireStart.point&&Math.hypot(...point.map((v,i)=>v-S.wireStart.point[i]))<1){cancelSchematicWire();return;}
  prepareWireConnection({from:S.wireStart,to:endpoint,waypoints:S.wireDraft.finish(point)});
}
function handleWireNode(id){
  if(!editable()||busy())return;
  const node=S.spec.editor?.wire_nodes?.[id];if(!node)throw new Error('The wire endpoint moved. Refresh the schematic.');
  const endpoint={node:id,anchor:'node:'+id};
  if(!S.wireStart){beginSchematicWire(endpoint,node.position);return;}
  if(S.wireStart.node===id){cancelSchematicWire();return;}
  prepareWireConnection({from:S.wireStart,to:endpoint,waypoints:S.wireDraft.manual?S.wireDraft.finish(node.position):[]});
}
function splitSelectedSchematicWire(){
  if(!editable()||busy())return;
  const route=S.schematicData?.routes.find(r=>r.index===S.selectedWireIndex&&r.sheet===(S.schematicSheet||''));if(!route)throw new Error('Select a native wire first.');
  let point=S.selectedWirePoint;
  if(!point){let length=route.points.slice(1).reduce((sum,p,i)=>sum+Math.hypot(p[0]-route.points[i][0],p[1]-route.points[i][1]),0)/2;for(let i=1;i<route.points.length;i++){const a=route.points[i-1],b=route.points[i],span=Math.hypot(b[0]-a[0],b[1]-a[1]);if(length<=span){point=a.map((v,k)=>v+(b[k]-v)*length/span);break;}length-=span;}}
  const result=splitWireDrawing(S.spec,route,point);S.selectedWireIndex=null;S.selectedWirePoint=null;S.selectedWireNode=result.node;commit(result.spec,'Split schematic wire at a native point',null);toast('Wire split; electrical connectivity preserved');
}
function removeSelectedWireNode(){
  if(!editable()||busy())return;
  if(S.spec.editor?.wire_nodes?.[S.selectedWireNode]?.label)return netLabelsUI.open({action:'delete',id:S.selectedWireNode});
  const next=removeWireNode(S.spec,S.selectedWireNode);S.selectedWireNode=null;S.selectedWireIndex=null;cancelSchematicWire();commit(next,'Removed wire endpoint drawings',null);toast('Endpoint drawings removed; named pin connections remain');
}
function schematicWireKey(event){
  if(!S.wireDraft||S.active!=='schematic')return false;
  if(!event.metaKey&&!event.ctrlKey&&event.key.toLowerCase()==='f'){event.preventDefault();S.wireDraft.flip();S.canvas.drawWireDraft();return true;}
  if(event.key==='Backspace'||(event.metaKey||event.ctrlKey)&&event.key.toLowerCase()==='z'){
    event.preventDefault();if(!S.wireDraft.undo())cancelSchematicWire();else S.canvas.drawWireDraft();return true;
  }
  return false;
}
function labelSelectedWire(){const route=S.schematicData?.routes.find(r=>r.index===S.selectedWireIndex&&r.sheet===(S.schematicSheet||''));if(route)netLabelsUI.open({action:'add',wire:route.id,position:S.selectedWirePoint||route.points[Math.floor(route.points.length/2)],sheet:route.sheet,net:route.net});}
function handleSchematicPin(pin,anchor,point){
  if(!S.schematicWiring&&!S.spec.nets.some(n=>n.pins.includes(pin))){netLabelsUI.pinMenu(pin,anchor,point);return;}
  if(!S.schematicWiring){const net=S.spec.nets.find(n=>n.pins.includes(pin));openNetEditor(net?.name||null,pin);return;}
  if(!editable()||busy())return;
  const endpoint={pin,anchor:anchor||pin};
  if(!S.wireStart){const at=S.canvas?.pinLocation(endpoint.anchor);beginSchematicWire(endpoint,at&&[at.x,at.y]);return;}
  if(pin===S.wireStart.pin){cancelSchematicWire();return;}
  const at=S.canvas?.pinLocation(endpoint.anchor);if(!at)throw new Error('The target pin moved. Refresh the schematic before connecting it.');
  const native=schematicAnchor(endpoint.anchor);
  prepareWireConnection({from:S.wireStart,to:endpoint,waypoints:S.wireDraft.manual?S.wireDraft.finish(native?.position||[at.x,at.y],{escape:native?.escape}):[]});
}
function handleWireEndpoint(index,at){
  if(!S.schematicWiring||!editable()||busy())return;
  const route=S.schematicData?.routes.find(route=>route.index===index&&route.sheet===(S.schematicSheet||''));
  if(!route?.id)throw new Error('Refresh the native schematic before joining its wires.');
  const point=projectWirePoint(route.points,at).point,endpoint={route,at:point};
  if(!S.wireStart){beginSchematicWire(endpoint,point);return;}
  if(S.wireStart.route?.index===index&&Math.hypot(S.wireStart.at[0]-point[0],S.wireStart.at[1]-point[1])<1){cancelSchematicWire();return;}
  prepareWireConnection({from:S.wireStart,to:endpoint,waypoints:S.wireDraft.manual?S.wireDraft.finish(point):[]});
}
function prepareWireConnection(pending){
  if(S.wireSpec!==S.spec){cancelSchematicWire();throw new Error('The design changed. Start the wire again.');}
  pending.baseSpec=S.spec;
  const from=endpointPin(S.spec,pending.from),to=endpointPin(S.spec,pending.to),a=electricalNet(S.spec,from),b=electricalNet(S.spec,to);
  if(wireMergeNeedsReview(S.spec,from,to)){
    const proposed=connectWireEndpoints(S.spec,pending.from,pending.to,{allowMerge:true,waypoints:pending.waypoints}),net=electricalNet(proposed,from);
    $('#mergeNetDescription').textContent=`${a.name} and ${b.name} will become ${net.name}, joining ${net.pins.length} pins.`;
    cancelSchematicWire();S.pendingWire=pending;dialog('#mergeNetDialog');return;
  }
  finishSchematicWire(pending,false);
}
function finishSchematicWire(pending,merge){
  if(!pending)return;
  if(pending.baseSpec!==S.spec){cancelSchematicWire();throw new Error('The design changed. Start the wire again.');}
  const next=connectWireEndpoints(S.spec,pending.from,pending.to,{allowMerge:merge,waypoints:pending.waypoints}),guide=next.editor.connection_guides.at(-1);
  S.selected=null;S.selectedWireNode=null;S.selectedWirePoint=null;S.selection.clear();S.selectedNet=electricalNet(next,guide.from)?.name||null;S.selectedWireIndex=next.editor.connection_guides.length-1;S.inspector=true;
  cancelSchematicWire();commit(next,'Connected schematic endpoints',null);toast('Connection saved');
}
function disconnectSchematicPin(pin){
  if(!editable()||busy())return;
  const next=disconnectPin(S.spec,pin);S.selectedWireIndex=null;cancelSchematicWire();commit(next,`Disconnected ${pin}`,null);toast(`${pin} disconnected`);
}
function removeSelectedWireDrawing(){
  if(!editable()||busy())return;
  const next=removeWireDrawing(S.spec,S.selectedWireIndex);S.selectedWireIndex=null;cancelSchematicWire();commit(next,'Removed wire drawing',null);toast('Wire drawing removed; the named net remains connected');
}
function openWireDisconnect(){
  if(!editable()||busy())return;
  const guide=S.spec.editor?.connection_guides?.[S.selectedWireIndex];if(!guide)return;
  const from=logicalPin(guide.from),to=logicalPin(guide.to),modal=dialog('#wireDisconnectDialog');
  $('#wireDisconnectDescription').textContent=`${wireEndpointLabel(guide,'from')} ↔ ${wireEndpointLabel(guide,'to')}. Named net labels also connect these pins. Choose a pin to disconnect electrically, or remove the wire drawing.`;
  $('#disconnectWireFrom').textContent=`Disconnect ${from}`;$('#disconnectWireTo').textContent=`Disconnect ${to}`;
  $('#disconnectWireFrom').hidden=!S.spec.components.some(c=>c.ref===from.split('.')[0]);$('#disconnectWireTo').hidden=!S.spec.components.some(c=>c.ref===to.split('.')[0]);
  $('#disconnectWireFrom').onclick=()=>{modal.close();disconnectSchematicPin(from);};$('#disconnectWireTo').onclick=()=>{modal.close();disconnectSchematicPin(to);};$('#removeWireDrawingDialog').onclick=()=>{modal.close();removeSelectedWireDrawing();};
}

function renderTable() {
  const type = S.active, nets = type === 'nets', cols = nets ? ['Name', 'Pins', 'Class', 'Connections'] : type === 'bom' ? ['Designator', 'Component', 'Quantity', 'Value', 'Package', 'MPN', 'LCSC', 'Unit price','Stock'] : ['Designator', 'Value', 'Footprint', 'MPN', 'LCSC', 'Description'];
  const rows = nets ? S.spec.nets : type==='bom'?S.spec.components.filter(c=>!c.terminal):S.spec.components;
  const rowHTML = rows.map(item => {
    const price=nets?null:manufacturingUI.partPrice(item);
    const cells = nets ? [item.name, item.pins.length, item.class || 'signal', item.pins.join(', ')] : type === 'bom' ? [item.ref, item.description || item.value, 1, item.value, item.footprint?.split(':').pop() || '—', item.mpn ||price?.mpn|| '—', item.lcsc || '—', manufacturingUI.money(price?.unit,5),Number.isFinite(price?.stock)?Number(price.stock).toLocaleString():'—'] : [item.ref, item.value, item.footprint || '—', item.mpn || '—', item.lcsc || '—', item.description || '—'];
    return `<tr ${nets ? `data-net="${esc(item.name)}"` : `data-ref="${esc(item.ref)}"`} class="${item.ref === S.selected ? 'selected' : ''}">${cells.map((cell, i) => `<td ${!nets && i === (type === 'bom' ? 3 : 1) ? 'class="editable" title="Double-click to edit value"' : ''} title="${esc(cell)}">${esc(cell)}</td>`).join('')}</tr>`;
  }).join('');
  $('#viewContent').innerHTML = `<div class="table-view"><div class="table-heading"><h2>${type === 'bom' ? 'Bill of materials' : views[type][1]}</h2><span class="count">${rows.length} ${nets ? 'nets' : 'components'}</span>${!nets ? `<button class="secondary-button" id="tableExport">${icon('download')}Export CSV</button>` : `<button class="secondary-button" id="addNet">${icon('plus')}Add net</button><button class="secondary-button" id="routeNetsButton">${icon('workflow')}Route connections…</button>`}</div><div class="table-filter"><span>${icon('search')}</span><input id="tableSearch" type="search" placeholder="Search ${nets ? 'nets' : 'components'}…" aria-label="Search table"></div><div class="table-scroll"><table class="design-table"><thead><tr>${cols.map(c => `<th>${c}</th>`).join('')}</tr></thead><tbody>${rowHTML}</tbody></table></div><div class="table-foot">${nets ? 'Double-click a net to edit its connections, or select a pin in Schematic.' : 'Select a component to inspect. Double-click its value to edit.'}${type === 'bom' ? ' Prices and stock use the latest saved supplier lookup. Refresh them in Manufacturing.' : ''}</div></div>`;
  $$('.design-table tr[data-ref]').forEach(row => {
    row.onclick = event => selectComponent(row.dataset.ref,{additive:event.shiftKey});
    $('td.editable', row).ondblclick = safely(async () => {
      if(!editable())return;
      const c = S.spec.components.find(c => c.ref === row.dataset.ref);
      const value = await askText(`Edit ${c.ref}`, 'Component value', c.value);
      if(value!==null){if(c.terminal)await terminalsUI.perform({action:'update',ref:c.ref,patch:{name:value}},'Renamed terminal');else commit(updateComponent(S.spec,c.ref,{value}),`Updated ${c.ref} value`);}
    });
  });
  $$('.design-table tr[data-net]').forEach(row => { row.onclick = () => selectNet(row.dataset.net); row.ondblclick = () => openNetEditor(row.dataset.net); });
  $('#addNet')?.addEventListener('click', () => openNetEditor());
  $('#routeNetsButton')?.addEventListener('click',safely(()=>nativeRoutingUI.open(S.selectedNet?[S.selectedNet]:[])));
  if($('#routeNetsButton'))$('#routeNetsButton').disabled=!editable()||busy();
  $('#tableSearch').oninput = e => $$('.design-table tbody tr').forEach(row => row.hidden = !row.textContent.toLowerCase().includes(e.target.value.toLowerCase()));
  $('#tableExport')?.addEventListener('click', safely(exportBOM));
}

function fileScope(pid,path,token){return S.pid===pid&&S.active==='files'&&S.currentFile?.path===path&&S.fileSelectionToken===token&&!S.openingProject;}
function markdownFile(file){return /\.(md|markdown)$/i.test(file?.name||'');}
function editableFile(file){return typeof file.text_editable==='boolean'?file.text_editable:file.path==='design.json'||(!/^(native|history)\//.test(file.path)&&/\.(md|txt|json|py|cpp|c|h|hpp|ini|scad|csv)$/i.test(file.name));}
function renderFilePresentation(){
  fileDraftUI.update();
  const f=S.currentFile;if(!$('#fileMarkdownPreview'))return;
  $('#fileEmptyPreview').hidden=!!f;$('#fileViewerHead').hidden=!f;if(!f)return;
  const draft=fileDraft(S.pid,f.path),content=S.fileEditing?$('#fileEditor').value:draft?.content??S.fileSavedContent??'',markdown=markdownFile(f),image=imageFile(f)&&S.fileMode!=='source',preview=markdown&&S.fileTextAvailable&&S.fileMode!=='source';
  $('#fileMarkdownPreview').hidden=!preview;$('#fileImagePreview').hidden=!image;$('#fileSource').hidden=preview||image||S.fileEditing;$('#fileEditor').hidden=preview||image||!S.fileEditing;
  $('#filePreviewButton').hidden=$('#fileSourceButton').hidden=!(markdown||imageFile(f))||!S.fileTextAvailable;
  $('#filePreviewButton').setAttribute('aria-pressed',String(preview||image));$('#fileSourceButton').setAttribute('aria-pressed',String(!preview&&!image));
  if(preview)$('#fileMarkdownPreview').innerHTML=renderMarkdown(content,{baseUrl:f.url});else if(!S.fileEditing&&!image)$('#fileSource').textContent=content;
  if(image){const img=$('#fileImage');if(img.getAttribute('src')!==f.url)img.src=f.url;img.alt=f.name;}
  $('#editTextFile').hidden=!projectWritable()||!S.fileTextAvailable||!editableFile(f)||S.fileEditing;$('#saveTextFile').hidden=!S.fileEditing;$('#saveTextFile').disabled=!projectWritable()||!!S.sourceSaving;
  $('#fileDraftStatus').textContent=draft?(draft.record?.persisted?'Unsaved draft · kept in this browser':'Unsaved draft · this tab only'):'';
  const cad=f.path.endsWith('.cad.json')&&editableFile(f);if($('#cadFileActions'))$('#cadFileActions').hidden=!cad;if(cad){mechanicalUI.refreshHistory().catch(fail);mechanicalUI.sync();}
  const role=fileBadge(f),scope=f.category==='native'?'Native output':f.category==='history'?'Saved design snapshot':'Project file';
  $('#fileContextStatus').textContent=[role||scope,!editableFile(f)?'Read-only':null].filter(Boolean).join(' · ');
}
async function renderFiles() {
  const host=$('#viewContent'),pid=S.pid,owner=draftOwner(),viewToken=S.viewToken,renderToken=S.filesRenderToken=(S.filesRenderToken||0)+1;
  S.fileSelectionToken=(S.fileSelectionToken||0)+1;S.fileEditing=false;S.currentFile=null;
  const current=()=>S.pid===pid&&draftOwner()===owner&&S.active==='files'&&S.viewToken===viewToken&&S.filesRenderToken===renderToken&&!S.openingProject;
  host.innerHTML='<div class="file-layout"><div class="file-tree"><div class="file-tree-heading">Files</div><p class="file-help" id="fileLoadStatus">Loading project files…</p></div></div>';
  let data;
  try{
    await save();if(!current())return;
    data=await loadFileCatalog(async params=>{const query=new URLSearchParams(params),page=await api(`/api/workbench/projects/${pid}/files?${query}`);if(current()&&$('#fileLoadStatus'))$('#fileLoadStatus').textContent=`Loading ${page.next_offset} of ${page.total} files…`;return page;},{isCurrent:current});
  }catch(error){if(error.cancelled||!current())return;host.innerHTML=`<div class="file-layout"><div class="file-tree"><h3>Files</h3><p class="file-help" role="alert">${esc(error.message)}</p><button class="secondary-button" id="retryFileCatalog">Refresh files</button></div></div>`;$('#retryFileCatalog').onclick=safely(renderFiles);return;}
  if(!current())return;fileDraft(pid,'');
  for(const[key,draft]of S.fileDrafts||[])if(key.startsWith(pid+':')&&draft.virtual&&!data.files.some(f=>f.path===key.slice(pid.length+1))){const path=key.slice(pid.length+1);data.files.push({path,name:path.split('/').at(-1),category:'project',text_editable:true,size:new TextEncoder().encode(draft.content).length,url:'',virtual:true});}
  S.files=data.files;S.fileCatalog=data;
  host.innerHTML=`<div class="file-layout" id="projectFileLayout"><div class="file-navigation-rail"><button class="tool-button active" id="toggleFileTree" aria-label="Toggle file browser" title="Files">${icon('list')}</button></div><aside class="file-tree" id="fileBrowserPane"></aside><div class="file-viewer"><div class="file-picker-row"><select id="mobileFilePicker" aria-label="Project file"><option value="">Choose a file</option>${S.files.map(f=>`<option value="${esc(f.path)}">${esc(f.path)}</option>`).join('')}</select></div><div class="file-viewer-head" id="fileViewerHead" hidden><span id="fileViewName"></span><small id="fileContextStatus"></small><small id="fileDraftStatus"></small><button class="icon-button file-path-action" id="revealProjectFile" aria-label="Reveal selected file" title="Reveal selected file">${icon('folder')}</button><button class="secondary-button" id="filePreviewButton" hidden aria-pressed="true">Preview</button><button class="secondary-button" id="fileSourceButton" hidden aria-pressed="false">Source</button><button class="secondary-button" id="editTextFile" hidden>${icon('file')}Edit</button><button class="primary-button" id="saveTextFile" hidden>${icon('save')}Save file</button><a id="fileDownload" class="icon-button" aria-label="Download saved file">${icon('download')}</a></div><div class="file-empty-preview" id="fileEmptyPreview">${icon('file')}<p>No documents yet</p></div><div class="file-image-preview" id="fileImagePreview" hidden><img id="fileImage" alt=""></div><div id="fileMarkdownPreview" class="file-markdown-preview markdown" hidden></div><pre id="fileSource" hidden></pre><textarea id="fileEditor" class="file-editor" spellcheck="false" aria-label="Project file editor" hidden></textarea></div></div>`;
  const reviewDraft=document.createElement('button');reviewDraft.type='button';reviewDraft.id='reviewFileDraft';reviewDraft.className='secondary-button';reviewDraft.hidden=true;reviewDraft.textContent='Review draft';$('#fileViewerHead').append(reviewDraft);fileDraftUI.mount();
  const cadActions=document.createElement('div');cadActions.id='cadFileActions';cadActions.className='file-cad-actions';cadActions.hidden=true;cadActions.innerHTML=`<button type="button" class="secondary-button" data-cad-history="undo" aria-label="Undo CAD change">${icon('undo')}</button><button type="button" class="secondary-button" data-cad-history="redo" aria-label="Redo CAD change">${icon('redo')}</button><button type="button" class="secondary-button" id="buildCADSource">${icon('cube')}Build model from saved code</button>`;$('#fileViewerHead').after(cadActions);
  for(const button of cadActions.querySelectorAll('[data-cad-history]'))button.onclick=safely(()=>mechanicalUI.restoreHistory(button.dataset.cadHistory==='redo'));
  $('#buildCADSource').onclick=safely(()=>{if(current()&&S.currentFile?.path.endsWith('.cad.json'))return mechanicalUI.build(mechanicalUI.context(),{path:S.currentFile.path,expected_sha256:S.fileSha});});
  const toggle=force=>{if(!current())return;const layout=$('#projectFileLayout');if(force===true){if(innerWidth<=760)layout.classList.add('mobile-file-browser-open');else layout.classList.remove('file-tree-collapsed');}else layout.classList.toggle(innerWidth<=760?'mobile-file-browser-open':'file-tree-collapsed');};
  const show=async path=>{
    if(!current())return;const f=S.files.find(file=>file.path===path);if(!f)return;
    const token=S.fileSelectionToken=(S.fileSelectionToken||0)+1;S.currentFile=f;S.openFilePath=f.path;S.fileMode=markdownFile(f)||imageFile(f)?'preview':'source';S.fileTextAvailable=/\.(json|md|markdown|txt|py|cpp|c|h|hpp|ini|kicad_sch|kicad_pcb|kicad_pro|csv|log|svg|jsonl|dru|scad)$/i.test(f.name)&&f.size<=2_000_000;
    const draft=fileDraft(pid,f.path);S.fileEditing=!!draft;S.fileSha=draft?.sha;S.fileBaseVersion=draft?.base_version??S.version;S.fileBaseContent=draft?.base_content;S.fileSavedContent=f.virtual?'':S.fileTextAvailable?'Loading file…':'Download this file to open it in its native application.';$('#fileEditor').value=draft?.content??'';$('#saveTextFile').textContent=draft?'Save changes':'Save file';if(draft?.recovered)S.fileMode='source';
    S.filesTree.setSelected(f.path);$('#mobileFilePicker').value=f.path;$('#fileViewName').textContent=f.path;$('#fileViewName').title=f.path;$('#fileDownload').href=f.url;$('#fileDownload').setAttribute('download',f.name);if(innerWidth<=760)$('#projectFileLayout').classList.remove('mobile-file-browser-open');renderFilePresentation();if(!S.fileTextAvailable)return;
    $('#fileDownload').onclick=f.virtual?event=>{event.preventDefault();fileDraftUI.download({path:f.path,content:fileDraft(pid,f.path)?.content||''});}:null;
    if(f.virtual)return;
    try{const response=await fetch(f.url);if(!response.ok)throw new Error('Could not read the selected file.');const content=await response.text();if(fileScope(pid,f.path,token)){S.fileSavedContent=content;renderFilePresentation();}}
    catch(error){if(fileScope(pid,f.path,token)){S.fileSavedContent=error.message;renderFilePresentation();throw error;}}
  };
  S.fileTreeStates??=new Map();if(!S.fileTreeStates.has(pid))S.fileTreeStates.set(pid,{});
  S.filesTree=new FilesTreeUI({host:$('#fileBrowserPane'),data,pid,state:S.fileTreeStates.get(pid),select:safely(show),refresh:safely(renderFiles),toggle,editable:projectWritable()});
  $('#toggleFileTree').onclick=()=>toggle();$('#revealProjectFile').onclick=()=>{S.filesTree.reveal();toggle(true);};
  $('#mobileFilePicker').onchange=safely(event=>show(event.target.value));
  $('#newTextFile').onclick=safely(async()=>{const path=await askText('New project file','File path','docs/requirements.md');if(!path||!current())return;await api(`/api/workbench/projects/${pid}/text/${path.split('/').map(encodeURIComponent).join('/')}`,{method:'PUT',body:{content:/\.(md|markdown)$/i.test(path)?'# Requirements\n\n':'',base_sha:null}});if(!current())return;S.openFilePath=path;await renderFiles();await editCurrentFile();});
  $('#editTextFile').onclick=safely(editCurrentFile);$('#saveTextFile').onclick=safely(saveCurrentFile);
  $('#filePreviewButton').onclick=()=>{S.fileMode='preview';renderFilePresentation();};$('#fileSourceButton').onclick=()=>{S.fileMode='source';renderFilePresentation();};
  $('#fileMarkdownPreview').onclick=event=>{const anchor=event.target.closest('a[href^="#"]');if(!anchor)return;event.preventDefault();let id;try{id=decodeURIComponent(anchor.getAttribute('href').slice(1));}catch{return;}$('#fileMarkdownPreview').querySelector('#'+CSS.escape(id))?.scrollIntoView({block:'start'});};
  $('#fileEditor').oninput=event=>{if(!current()||event.target!==$('#fileEditor'))return;const path=S.currentFile.path,prior=fileDraft(pid,path),content=editorText(event.target.value,prior?.content??S.fileBaseContent??S.fileSavedContent),draft=fileDraftUI.persist(path,{...prior,content,base_content:prior?.base_content??S.fileBaseContent??S.fileSavedContent,sha:S.fileSha,base_version:S.fileBaseVersion??S.version});S.fileDrafts.set(`${pid}:${path}`,draft);$('#saveTextFile').textContent='Save changes';$('#fileDraftStatus').textContent=draft.record.persisted?'Unsaved draft · kept in this browser':'Unsaved draft · this tab only';fileDraftUI.update();mechanicalUI.sync();};
  const initial=S.files.find(f=>f.path===S.openFilePath)||S.files.find(isDocument);
  if(initial)await show(initial.path);else renderFilePresentation();
}
async function editCurrentFile(){
  const f=S.currentFile;if(!f||!projectWritable())return;const pid=S.pid,token=S.fileSelectionToken,cached=fileDraft(pid,f.path),version=S.version;
  const data=f.path==='design.json'?{content:JSON.stringify(S.spec,null,2),sha:null}:await api(`/api/workbench/projects/${pid}/text/${f.path.split('/').map(encodeURIComponent).join('/')}`);
  if(!fileScope(pid,f.path,token))return;S.fileSha=cached?.sha??data.sha;S.fileBaseVersion=cached?.base_version??version;S.fileBaseContent=cached?.base_content??data.content;$('#fileEditor').value=cached?.content??data.content;S.fileEditing=true;S.fileMode='source';renderFilePresentation();$('#fileEditor').focus();
}
async function saveCurrentFile(){
  const f=S.currentFile;if(!f||!$('#fileEditor')||!projectWritable())return;if(S.sourceSaving)return S.saving;const pid=S.pid,token=S.fileSelectionToken,key=`${pid}:${f.path}`,draft=S.fileDrafts?.get(key),content=draft?.content??$('#fileEditor').value,baseSha=draft?.sha??S.fileSha,baseVersion=draft?.base_version??S.fileBaseVersion??S.version;let nextSha=null,nextVersion=baseVersion;
  if(f.path==='design.json'){
    nextVersion=await saveDesignSource(pid,baseVersion,content);
  }else{const cad=f.path.endsWith('.cad.json'),pending=api(`/api/workbench/projects/${pid}/text/${f.path.split('/').map(encodeURIComponent).join('/')}`,{method:'PUT',body:{content,base_sha:baseSha}});if(cad){S.sourceSaving=true;S.saving=pending;applyAccessUI();}try{const result=await pending;nextSha=result.sha;mechanicalUI.rememberHistory(pid,result.mechanical_history);}finally{if(cad){if(S.saving===pending)S.saving=null;S.sourceSaving=false;applyAccessUI();}}}
  const latest=S.fileDrafts?.get(key),newer=latest&&latest.content!==content;
  if(newer){if(latest.sha===baseSha&&latest.base_version===baseVersion)S.fileDrafts.set(key,fileDraftUI.persist(f.path,{...latest,sha:nextSha,base_content:content,base_version:nextVersion}));}
  else{S.fileDrafts?.delete(key);fileDraftUI.saved(draft);}
  if(f.virtual){f.virtual=false;f.url=`/api/projects/${pid}/files/${f.path.split('/').map(encodeURIComponent).join('/')}`;if(fileScope(pid,f.path,token)){$('#fileDownload').onclick=null;$('#fileDownload').href=f.url;}}
  if(!fileScope(pid,f.path,token))return;S.fileSavedContent=content;S.fileBaseContent=content;S.fileSha=newer?S.fileDrafts.get(key).sha:nextSha;S.fileBaseVersion=newer?S.fileDrafts.get(key).base_version:nextVersion;$('#saveTextFile').textContent=newer?'Save changes':'Saved';renderFilePresentation();toast(newer?'Saved earlier edits; newer changes are still unsaved.':'File saved');
}

async function saveDesignSource(pid,baseVersion,content,options={}){
  const spec=JSON.parse(content);
  if(S.saving)await S.saving;
  if(S.pid!==pid||!editable())throw new Error('Open this project again before saving its design source.');
  if(busy())throw new Error('Stop the active run before saving design source.');
  if(S.dirty||S.version!==baseVersion)throw new Error('The design changed since this source draft was opened. Review the saved design before saving your draft.');
  const before=structuredClone(S.spec);
  if(JSON.stringify(before)===JSON.stringify(spec))return S.version;
  S.sourceSaving=true;savedLabel('Saving…','saving');
  const pending=(async()=>{
    const result=await api(`/api/workbench/projects/${pid}/design`,{method:'PUT',body:{base_version:baseVersion,spec,...(options.native_source?{native_source:options.native_source}:{}),...(options.routing_proposal?{routing_proposal:options.routing_proposal}:{})}});
    // The same saving slot holds project switching, graphical edits and own-save echoes
    // until this accepted design and its Undo entry have been installed together.
    S.undo.push(before);if(S.undo.length>60)S.undo.shift();S.redo=[];
    S.spec=spec;S.version=result.version;S.generation++;S.dirty=false;invalidateCheckDisplay();
    S.project.spec=structuredClone(spec);S.project.workbench={...result};
    S.actions.push({text:options.action||'Edited design source',time:Date.now()});
    S.selection=new Set([...S.selection].filter(key=>spec.components.some(c=>c.ref===key.split('#')[0])));
    if(!spec.components.some(c=>c.ref===S.selected))S.selected=null;
    savedLabel('Saved locally','saved');
    if(S.active!=='files')renderView();renderInspector();updateContext();
    return result.version;
  })();
  S.saving=pending;applyAccessUI();
  try{return await pending;}
  catch(error){savedLabel('Could not save','error');throw error;}
  finally{if(S.saving===pending)S.saving=null;S.sourceSaving=false;applyAccessUI();syncSavedDesign().catch(fail);}
}

function render3D() {
  if(mechanicalUI.current()){
    $('#viewContent').innerHTML='<div class="mesh-host" id="meshHost"></div><div class="view-badge" id="mechanicalPartStatus" role="status">Loading saved mechanical model…</div><div class="view-caption"></div>';
    mechanicalUI.mount($('#viewContent'));return;
  }
  const controlsToken=S.viewToken;
  $('#viewContent').innerHTML = `<div class="mesh-host" id="meshHost"></div><div class="view-badge">${icon('info')}Concept preview · not a CAD export</div><div class="mesh-view-controls"><button data-mesh="board" class="${!S.enclosure ? 'active' : ''}">Board</button><button data-mesh="enclosure" class="${S.enclosure ? 'active' : ''}">Enclosure</button></div>${S.enclosure ? '<label class="mesh-explode">Explode<input id="explodeSlider" type="range" min="0" max="1.5" step="0.05" value="0.6" aria-label="Exploded view"></label>' : ''}<div class="view-caption">Drag to orbit · Scroll to zoom${S.enclosure ? ' · Parametric concept' : ''}</div>`;
  const meta=S.project.workbench_enclosure;
  const nativeBoard=S.project.workbench_board3d;
  const matchingBoard=meta?.pcb_sha256&&meta.pcb_sha256===nativeBoard?.source_sha&&nativeBoard.version===S.version;
  const mesh = createMeshView($('#meshHost'), conceptMeshes(S.spec, S.enclosure)); S.canvas = mesh;attachNavigation();
  const actions=document.createElement('div');actions.className='mechanical-actions';actions.innerHTML=S.enclosure?`<button class="secondary-button" id="buildEnclosure">${icon('play')}${meta?'Rebuild enclosure':'Generate enclosure CAD'}</button>`:`<button class="secondary-button" id="buildNativeBoard3D">${icon('cube')}${S.project.workbench_board3d?'Regenerate native 3D':'Generate native board 3D'}</button>`;$('#viewContent').append(actions);
  $('#buildEnclosure')?.addEventListener('click',safely(()=>runEngineering('enclosure')));
  $('#buildNativeBoard3D')?.addEventListener('click',safely(()=>runEngineering('board3d',{force:true})));
  if(meta?.preview&&meta.version===S.version&&!S.dirty&&(S.enclosure||!nativeBoard||nativeBoard.version!==S.version)){
    const token=S.viewToken;
    Promise.all([api(meta.preview),S.enclosure&&nativeBoard?.url&&matchingBoard?api(nativeBoard.url):null]).then(([data,actualBoard])=>{if(S.active!=='3d'||token!==S.viewToken)return;if(actualBoard)data=combineAssembly(data,actualBoard);replaceMeshData(data);$('.view-badge').innerHTML=icon('check')+(actualBoard?'Native PCB + FreeCAD enclosure':'FreeCAD geometry · inspect fit and findings');}).catch(error=>{if(S.active==='3d'&&token===S.viewToken)fail(error);});
  }
  if(!S.enclosure&&nativeBoard?.url&&nativeBoard.version===S.version&&!S.dirty){
    const token=S.viewToken;
    api(nativeBoard.url).then(data=>{if(S.active!=='3d'||S.enclosure||token!==S.viewToken)return;replaceMeshData(data);$('.view-badge').innerHTML=icon('check')+`KiCad STEP geometry · ${data.meshes.length} objects`;}).catch(error=>{if(S.active==='3d'&&token===S.viewToken)fail(error);});
  }
  $$('[data-mesh]').forEach(b => b.onclick = () => {if(controlsToken!==S.viewToken||markupUI.active||markupUI.starting)return;S.enclosure = b.dataset.mesh === 'enclosure';renderView();});
  if($('#explodeSlider'))$('#explodeSlider').oninput=e=>{if(controlsToken!==S.viewToken||!S.canvas?.is3D)return;if(S.canvas.measureMode||markupUI.active||markupUI.starting){e.target.value=S.canvas.explode;return;}S.canvas.explode=Number(e.target.value);S.canvas.draw();};
  mechanicalUI.mount($('#viewContent'));
}
function attachNavigation(){let host=$('#cadNavigation');if(!host){host=document.createElement('div');host.id='cadNavigation';$('#viewContent').append(host);}navigationUI.attach(S.canvas,host);}
function replaceMeshData(data){disposeCanvas();$('#meshHost').innerHTML='';S.canvas=createMeshView($('#meshHost'),data);attachNavigation();if($('.view-caption'))$('.view-caption').textContent='Drag to orbit · Scroll to zoom · CAD geometry (mm)';if($('#explodeSlider'))$('#explodeSlider').value=S.canvas.explode??0;refreshLayerPane();}

function createMeshView(host,data) {
  data=prepareCADData(data,S.spec);
  let view;
  const options={canInteract:()=>!markupUI.active&&!markupUI.starting,onZoom:z=>$('#zoomReset').textContent=`${Math.round(z*100)}%`,
    onCameraChange:view=>{navigationUI.update(view);if(S.canvas===view)cadUI.update();mechanicalUI.flush();},
    onPick:name=>{if(S.spec.components.some(c=>c.ref===name))selectComponent(name);else{S.inspector=true;S.selected=null;renderInspector();}},
    onComponentPick:id=>{for(const button of document.querySelectorAll('[data-assembly-member]'))button.setAttribute('aria-pressed',String(button.dataset.assemblyMember===id));},
    onMeasure:distance=>{let badge=$('#measureResult');if(!badge){badge=document.createElement('div');badge.id='measureResult';badge.className='measure-result';$('#viewContent').append(badge);}badge.textContent=distance===null?'Select the second point':`Assembly distance: ${distance.toFixed(2)} mm`;}};
  try{view=new CADView(host,data,options);}
  catch(error){console.warn('WebGL preview unavailable; using the software viewer.');host.innerHTML='';view=new window.MeshView(host,data,options);}
  cadUI.attach(view);return view;
}
function renderBlocks() {
  const groups = [ { name: 'Power input', refs: S.spec.components.filter(c => c.ref.startsWith('J')).map(c => c.ref), x: 110, y: 240 },
    { name: 'Power management', refs: S.spec.components.filter(c => c.ref.startsWith('U')).map(c => c.ref), x: 470, y: 240 },
    { name: 'Support & indicators', refs: S.spec.components.filter(c => !/^[JU]/.test(c.ref)).map(c => c.ref), x: 830, y: 240 } ];
  const blocks = groups.map(g => `<g><rect x="${g.x}" y="${g.y}" width="260" height="220" rx="8" fill="#1c241f" stroke="#54725e"/><text x="${g.x + 20}" y="${g.y + 35}" fill="#b8d4c3" font-family="Roboto" font-size="19">${g.name}</text>${g.refs.slice(0, 8).map((ref, i) => { const c = S.spec.components.find(c => c.ref === ref); return `<g role="button" tabindex="0" data-ref="${esc(ref)}" class="canvas-component"><text x="${g.x + 20}" y="${g.y + 68 + i * 19}" fill="#aaa" font-family="Roboto" font-size="13">${esc(ref + '  ' + c.value)}</text></g>`; }).join('')}</g>`).join('');
  $('#viewContent').innerHTML = `<svg class="design-svg" viewBox="0 0 1200 800"><path d="M370 350h100m260 0h100" stroke="#669e80" stroke-width="2"/><text x="165" y="155" fill="#848d87" font-family="Roboto" font-size="22">${esc(getTitle())}</text>${blocks}<text x="165" y="550" fill="#5e6c62" font-family="Roboto" font-size="13">Component groups · See Nets for electrical connections</text></svg>`;
  $$('[data-ref]', $('#viewContent')).forEach(g => g.onclick = () => selectComponent(g.dataset.ref));
}

function renderReview() {
  const rows = S.project.workbench_review || [];
  $('#viewContent').innerHTML = `<div class="table-view"><div class="table-heading"><h2>Design review</h2><span class="count">${rows.length} requirements</span><button class="secondary-button" id="requestReview">${icon('sparkles')}Review with AI</button></div><div class="table-scroll">${rows.length ? `<table class="design-table review-table"><thead><tr><th>Requirement</th><th>Status</th><th>Evidence / next step</th></tr></thead><tbody>${rows.map(r => `<tr><td>${esc(r.requirement)}</td><td><span class="review-status ${esc(r.status)}">${icon(r.status === 'pass' ? 'check' : r.status === 'fail' ? 'warning' : 'info')}${esc(r.status === 'unknown' ? 'Needs evidence' : r.status === 'pass' ? 'Supported' : 'Needs changes')}</span></td><td>${esc(r.evidence)}</td></tr>`).join('')}</tbody></table>` : `<div class="empty-canvas">${icon('shield')}<h2>Review the whole design</h2><p>Ask the AI to check every requirement against the current electronics, layout, enclosure, firmware, and available engineering evidence.</p></div>`}</div><div class="table-foot">AI review is separate from ERC, DRC, simulation, and physical testing. Missing evidence remains visible.</div></div>`;
  $('#requestReview').onclick = () => { $('#chatInput').value = 'Review the current design against every project requirement. List supported requirements, failures, and missing evidence separately. Do not claim that anything is measured or production-ready without actual test results. Explain the next changes needed.'; $('#chatInput').focus(); $('#ideShell').classList.remove('chat-hidden'); if (innerWidth <= 760) $('#ideShell').classList.add('mobile-chat-open'); };
}

async function renderSimulation() {
  const legacy=S.project.visuals?.['sim:sim'];
  const host=$('#viewContent'), meta=S.project.workbench_simulation||(legacy?.plot?{url:legacy.plot,result:legacy.result,version:S.project.workbench?.checks_stale?-1:S.version}:null);
  host.innerHTML=`<div class="simulation-view"><div class="table-heading"><h2>Circuit simulation</h2><span class="count">ngspice</span><button class="primary-button" id="runSimulation">${icon('play')}Run simulation</button></div><div class="simulation-content" id="simulationContent"><div class="empty-canvas">${icon('workflow')}<h2>Check the circuit before you build</h2><p>Run a real operating point and transient simulation. Review voltage, current, part ratings, and modelling assumptions.</p></div></div></div>`;
  $('#runSimulation').onclick=safely(()=>runEngineering('simulate'));
  if(!meta?.url)return;
  const fetched=await api(meta.url);const data=meta.result?{...meta.result,...fetched}:fetched;if(S.active!=='simulation')return;
  const content=$('#simulationContent');
  const status=data.ran?(data.ok?'Simulation completed':'Completed with findings'):'Simulation did not run';
  content.innerHTML=`<div class="simulation-summary"><span class="review-status ${data.ran&&data.ok?'pass':'fail'}">${icon(data.ran&&data.ok?'check':'warning')}${status}</span><span class="muted">${meta.version===S.version?'Current saved design':'An earlier design version'}</span></div>${(data.problems||[]).map(p=>`<p class="simulation-finding error">${esc(typeof p==='string'?p:JSON.stringify(p))}</p>`).join('')}${(data.warnings||[]).map(p=>`<p class="simulation-finding">${esc(typeof p==='string'?p:JSON.stringify(p))}</p>`).join('')}<div id="simulationPlots"></div>${data.rails?.length?`<h3>Power rails</h3><table class="design-table"><thead><tr><th>Net</th><th>Voltage</th><th>Peak load</th><th>Ripple</th></tr></thead><tbody>${data.rails.map(r=>`<tr><td>${esc(r.net)}</td><td>${Number(r.volts).toFixed(3)} V</td><td>${Number(r.peak_load).toFixed(3)} V</td><td>${(Number(r.ripple_v)*1000).toFixed(2)} mV</td></tr>`).join('')}</tbody></table>`:''}<details class="simulation-assumptions"><summary>Modelling assumptions (${(data.assumptions||[]).length})</summary><pre>${esc(JSON.stringify(data.assumptions||[],null,2))}</pre></details><p class="file-help">Simulation results depend on these models and assumptions. They are separate from physical measurements.</p>`;
  if(data.plot?.t?.length){
    for(const [suffix,label] of [[' V','V'],[' mA','mA']]){
      const series=Object.entries(data.plot.series).filter(([name])=>name.endsWith(suffix)).map(([name,values])=>({name:name.slice(0,-suffix.length),values}));
      if(!series.length)continue;
      const div=document.createElement('div');div.className='simulation-plot';$('#simulationPlots').append(div);S.plots.push(new window.Plot(div,data.plot.t,series,{ylabel:label,xlabel:'time',height:235}));
    }
  }
}

async function renderPins() {return busesUI.renderPins($('#viewContent'));}

function renderRules() {
  const defaults={track_mm:.25,power_track_mm:.5,clearance_mm:.2,via_diameter_mm:.6,via_drill_mm:.3,edge_clearance_mm:.3};
  const rules={...defaults,...S.spec.rules};
  const labels={track_mm:'Signal trace width',power_track_mm:'Power trace width',clearance_mm:'Copper clearance',via_diameter_mm:'Via diameter',via_drill_mm:'Via drill',edge_clearance_mm:'Board edge clearance'};
  const layers=S.spec.board.layers||2;
  const physical=S.spec.board.stackup;
  const physicalSummary=physical?physical.layers.map(row=>`<div class="stackup-layer"><strong>${esc(row.name||row.native_layer||row.type)}</strong><span>${esc(row.material)} · ${Number(row.thickness_mm||0)} mm${row.epsilon_r!==undefined?' · εr '+esc(row.epsilon_r):''}</span></div>`).join(''):'<p class="file-help">No explicit construction. Open the editor to review material assumptions.</p>';
  $('#viewContent').innerHTML=`<div class="table-view"><div class="table-heading"><h2>Rules & stackup</h2><span class="count">${layers} copper layers</span></div><div class="rules-content"><section><h3>Layout rules</h3><p class="muted">Applied to native KiCad files and the router. Run DRC after changing constraints.</p>${Object.entries(labels).map(([key,label])=>`<label class="rule-field"><span>${label}</span><input type="number" min="0.05" max="20" step="0.025" data-rule="${key}" value="${rules[key]}"><span>mm</span></label>`).join('')}</section><section><h3>Board stackup</h3><button class="secondary-button" id="openStackupEditor">Edit physical stackup</button><label class="rule-field"><span>Copper layers</span><select id="stackupLayers">${[1,2,4,6,8,10,12].map(n=>`<option ${n===layers?'selected':''}>${n}</option>`).join('')}</select></label><label class="rule-field"><span>Board thickness</span><input id="stackupThickness" type="number" min="0.2" max="10" step="0.1" value="${S.spec.board.thickness_mm||1.6}"><span>mm</span></label><div class="stackup-preview" id="stackupPhysicalSummary">${physicalSummary}</div></section></div></div>`;
  $$('[data-rule]').forEach(input=>input.onchange=()=>{const value=Number(input.value);if(!Number.isFinite(value)||value<=0||value>20){toast('Use a rule value between 0 and 20 mm.',true);renderRules();return;}const next=structuredClone(S.spec);next.rules={...rules,[input.dataset.rule]:value};commit(next,`Updated ${labels[input.dataset.rule]}`);});
  $('#openStackupEditor').disabled=!editable()||busy();$('#openStackupEditor').onclick=safely(()=>stackupUI.open());
  $('#stackupLayers').onchange=e=>stackupUI.open({template:'standard-'+e.target.value}).catch(fail);
  $('#stackupThickness').onchange=e=>stackupUI.open({target_thickness:Number(e.target.value)}).catch(fail);
}

async function renderKnowledge() {
  const pid=S.pid,token=S.viewToken,current=()=>S.pid===pid&&S.active==='knowledge'&&S.viewToken===token&&!S.openingProject;
  await save();if(!current())return;
  const data=await loadFileCatalog(params=>api(`/api/workbench/projects/${pid}/files?${new URLSearchParams(params)}`),{isCurrent:current}).catch(error=>{if(error.cancelled)return null;throw error;});if(!data||!current())return;
  const docs=data.files.filter(isDocument);
  $('#viewContent').innerHTML=`<div class="table-view"><div class="table-heading"><h2>Project knowledge</h2><span class="count">${docs.length} documents</span><button class="secondary-button" id="addKnowledge">${icon('plus')}New document</button></div><div class="knowledge-content"><p class="muted">Requirements, decisions, and reference notes are included in the AI's project context.</p>${docs.map((f,i)=>`<button class="knowledge-document" data-document="${i}">${icon('file')}<div><strong>${esc(f.name.replace(/\.md$/,''))}</strong><small>${esc(f.path)} · ${Math.ceil(f.size/1024)} KB</small></div>${icon('chevronRight')}</button>`).join('')||'<div class="empty-canvas"><h2>Keep the brief with the design</h2><p>Create a requirements document so the AI can check every design change against your goals.</p></div>'}</div></div>`;
  $$('[data-document]').forEach(b=>b.onclick=()=>{S.openFilePath=docs[Number(b.dataset.document)].path;setView('files');});
  $('#addKnowledge').onclick=safely(async()=>{const path=await askText('New knowledge document','File path','docs/requirements.md');if(!path)return;await api(`/api/workbench/projects/${S.pid}/text/${path.split('/').map(encodeURIComponent).join('/')}`,{method:'PUT',body:{content:'# Requirements\n\n',base_sha:null}});S.openFilePath=path;setView('files');});
}

async function runEngineering(kind, args={}) {
  if(!editable())throw new Error('Only project editors can run engineering tools.');
  if(busy())throw new Error('Wait for the active run to finish, or stop it first.');
  await save(); const pid=S.pid;
  const path=kind==='simulate'?`/api/workbench/projects/${pid}/simulate`:`/api/workbench/projects/${pid}/engineering/${kind}`;
  toast({simulate:'Running ngspice simulation…',place:'Placing components with TraceMaker…',route:'Routing copper with TraceMaker…',enclosure:'Building FreeCAD enclosure…',board3d:'Generating native STEP board geometry…'}[kind]);
  const data=await api(path,{method:'POST',body:args});if(pid!==S.pid)return;
  S.project={...data.state,access:S.project.access};S.spec=data.state.spec;S.version=data.state.workbench?.version||S.version;S.generation++;invalidateCheckDisplay();
  if(kind==='simulate')setView('simulation');else if(kind==='enclosure'){S.enclosure=true;setView('3d');}else if(kind==='board3d'){S.enclosure=false;setView('3d');}else setView('layout');
  renderInspector();toast(data.ok?'Operation completed. Review the result.':'Operation completed with findings to review.',!data.ok);
}

// Floating project tools.
const library = [
  { ref: 'R1', value: '10k', description: '10 kΩ resistor · 0603', footprint: 'Resistor_SMD:R_0603_1608Metric', symbol: 'Device:R', lcsc: 'C25804', glyph: 'resistor' },
  { ref: 'C1', value: '100nF', description: '100 nF capacitor · 0603', footprint: 'Capacitor_SMD:C_0603_1608Metric', symbol: 'Device:C', lcsc: 'C14663', glyph: 'capacitor' },
  { ref: 'D1', value: 'Red', description: 'Status LED · 0603', footprint: 'LED_SMD:LED_0603_1608Metric', symbol: 'Device:LED', lcsc: 'C2286', glyph: 'led' },
  { ref: 'U1', value: 'AMS1117-3.3', description: '3.3 V linear regulator · SOT-223', footprint: 'Package_TO_SOT_SMD:SOT-223-3_TabPin2', symbol: 'Regulator_Linear:AMS1117-3.3', lcsc: 'C6186', glyph: 'chip' },
  { ref: 'J1', value: 'Header 1x4', description: '4-pin expansion header · 2.54 mm', footprint: 'Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical', symbol: 'Connector:Conn_01x04_Pin', glyph: 'board' },
  { ref: 'U1', value: 'ESP32-C3-WROOM-02', description: 'Wi-Fi / Bluetooth module · unconnected', footprint: 'RF_Module:ESP32-C3-WROOM-02', symbol: 'RF_Module:ESP32-C3-WROOM-02', glyph: 'chip' },
];
function toggleDrawer(panel) { if(panel==='view')panel='layers';if (toolDock.has(panel)) closeDrawer(panel); else renderDrawer(panel); }
function closeDrawer(panel) { if(typeof panel==='string')toolDock.close(panel);else toolDock.clear(); }
function renderDrawer(panel) {
  if(panel==='view')panel='layers';
  const name = { library: 'Part library', objects: 'Objects', layers: 'View', checks: 'Design checks', manufacturing: 'Manufacturing', view:'3D view',comments:'Comments' }[panel];
  const host=toolDock.open(panel,name,panel==='objects'?['object-tree-drawer']:panel==='layers'?['pcb-layers-drawer']:[]);let html = '';
  if(panel==='comments')html='<div id="commentsContent"><p class="drawer-description">Loading comments…</p></div>';
  if (panel === 'library') html = `<select id="librarySource" class="library-source" aria-label="Part library source"><option value="starter">Starter parts</option><option value="project">Project library</option><option value="footprints">KiCad footprints</option><option value="symbols">KiCad symbols</option><option value="parts">LCSC parts</option></select><button class="library-part library-terminal" id="addTerminalCatalog" data-add-terminal aria-label="Add terminal"><span class="part-symbol">${icon('link')}</span><span class="part-info"><strong>Terminal</strong><small>Module pin and PCB test pad</small></span>${icon('plus')}</button><button class="library-part library-terminal" data-add-net-label="auto"><span class="part-symbol">${icon('netLabel')}</span><span class="part-info"><strong>Net label</strong><small>Named connection · no PCB part</small></span>${icon('plus')}</button><button class="library-part library-terminal" data-add-net-label="power"><span class="part-symbol">${icon('power')}</span><span class="part-info"><strong>Power symbol</strong><small>Named connection · no PCB part</small></span>${icon('plus')}</button><button class="library-part library-terminal" data-add-net-label="ground"><span class="part-symbol">${icon('ground')}</span><span class="part-info"><strong>Ground symbol</strong><small>Named connection · no PCB part</small></span>${icon('plus')}</button><div class="drawer-search">${icon('search')}<input id="partSearch" type="search" aria-label="Search part library" placeholder="Keyword or part number"></div><div id="libraryResults">${library.map((c, i) => `<button class="library-part" data-library-part="${i}"><span class="part-symbol">${icon(c.glyph)}</span><span class="part-info"><strong>${esc(c.value)}</strong><small>${esc(c.description)}</small></span>${icon('plus')}</button>`).join('')}</div><button class="asset-text-button" id="openLibraryEditor">${icon('shapes')}Edit project library</button><p class="file-help">Search real KiCad libraries or live supplier data. Verify pinout, ratings, and stock before manufacturing.</p>`;
  if (panel === 'objects') html = '';
  if (panel === 'layers') html = layerControls();
  if (panel === 'checks') html = '<p class="drawer-description">Check saved design integrity and engineering tool availability.</p><button class="secondary-button" id="runChecks">Run checks</button><div id="checkResults"></div>';
  if (panel === 'manufacturing') html = manufacturingUI.markup();
  host.querySelector('.drawer-content').innerHTML=html;
  if(panel==='comments')collaborationUI.loadComments().catch(fail);
  if (panel === 'library') {
    terminalsUI.bindCatalog($('#addTerminalCatalog'));netLabelsUI.bindCatalog(host);
    let queryTimer;
    const query=async()=>{
      if(!host.isConnected)return;
      const sourceInput=host.querySelector('#librarySource'),searchInput=host.querySelector('#partSearch'),results=host.querySelector('#libraryResults'),source=sourceInput?.value,q=searchInput?.value||'',owner=[S.pid,S.projectLoadToken,S.session?.user?.id||'device'];
      const valid=()=>host.isConnected&&results===host.querySelector('#libraryResults')&&sourceInput.value===source&&searchInput.value===q&&owner.every((value,index)=>value===[S.pid,S.projectLoadToken,S.session?.user?.id||'device'][index]);
      if(source==='starter'){$$('.library-part').forEach(b=>b.hidden=!b.textContent.toLowerCase().includes(q.toLowerCase()));return;}
      if(source==='project'){
        const lib=S.spec.library||{},parts=Object.entries(lib.parts||{}).map(([id,item])=>({...item,id}));
        const linked=new Set(parts.map(p=>p.symbol));
        for(const [id,item] of Object.entries(lib.symbols||{}))if(!linked.has('Project:'+id))parts.push({id,name:item.name,value:item.name||id,symbol:'Project:'+id,footprint:item.footprint,description:item.description,reference:item.reference});
        const matches=parts.filter(p=>JSON.stringify(p).toLowerCase().includes(q.toLowerCase()));
        $('#libraryResults').innerHTML=matches.map((item,i)=>`<button class="library-part" data-project-part="${i}"><span class="part-symbol">${icon('chip')}</span><span class="part-info"><strong>${esc(item.name||item.id)}</strong><small>${esc(item.description||item.symbol||'')}</small></span>${icon('plus')}</button>`).join('')||'<p class="file-help">Create a symbol and footprint in the project library editor.</p>';
        $$('[data-project-part]').forEach(button=>button.onclick=()=>openPartPicker(matches[Number(button.dataset.projectPart)]));return;
      }
      if(q.trim().length<2){$('#libraryResults').innerHTML='<p class="file-help">Type at least two characters to search.</p>';return;}
      const token=S.libraryQuery=(S.libraryQuery||0)+1;
      $('#libraryResults').innerHTML='<p class="file-help">Searching…</p>';
      try{
        const data=await api(`/api/workbench/library?kind=${source}&q=${encodeURIComponent(q)}`);
        if(!valid()||token!==S.libraryQuery)return;
        $('#libraryResults').innerHTML=data.results.map((item,i)=>`<button class="library-part" data-search-part="${i}"><span class="part-symbol">${icon(source==='parts'?'chip':source==='symbols'?'schematic':'board')}</span><span class="part-info"><strong>${esc(typeof item==='string'?item.split(':').pop():item.mpn||item.lcsc)}</strong><small>${esc(typeof item==='string'?item:`${item.lcsc} · ${item.package||''} · ${Number(item.stock||0).toLocaleString()} in stock`)}</small></span>${icon('plus')}</button>`).join('')||'<p class="file-help">No matching parts found. Try a package or part number.</p>';
        $$('[data-search-part]',host).forEach(b=>b.onclick=safely(async()=>{if(!valid())return;const item=data.results[Number(b.dataset.searchPart)];if(source==='symbols'){const info=await api(`/api/workbench/library/symbol-info?id=${encodeURIComponent(item)}`);if(valid())openPartPicker({value:item.split(':').pop(),symbol:item,footprint:info.default_footprint,description:info.description});}else if(source==='footprints')openPartPicker({value:item.split(':').pop(),footprint:item,description:item});else openPartPicker({value:item.mpn,mpn:item.mpn,lcsc:item.lcsc,description:item.description,package:item.package});}));
      }catch(e){if(valid()&&token===S.libraryQuery)results.innerHTML=`<p class="file-help">${esc(e.message)}</p>`;}
    };
    $('#partSearch').oninput=()=>{clearTimeout(queryTimer);queryTimer=setTimeout(()=>query().catch(fail),350);};
    $('#librarySource').onchange=()=>{if($('#librarySource').value==='starter'){renderDrawer('library');return;}query().catch(fail);};
    $$('[data-library-part]').forEach(b => b.onclick = () => {
      const { glyph, ...c } = library[Number(b.dataset.libraryPart)]; const next = addComponent(S.spec, {...c,sheet:S.schematicSheet||''}); const ref = next.components.at(-1).ref;
      commit(next, `Added ${ref}`, ref); S.inspector = true; renderInspector(); toast(`${ref} added. Connect its pins before building.`);
    });
    $('#partSearch').focus();
    $('#openLibraryEditor').onclick=()=>setView('library');
  }
  if (panel === 'objects') {
    objectsUI.mount(host.querySelector('.drawer-content'));
  }
  if(panel==='layers'){
    if(S.active==='schematic')displayUI.mount(host);else if(S.active==='3d')cadUI.mount(host);else layersUI.mount(host);
    if($('#routingLayer'))$('#routingLayer').onchange=event=>routingUI.guard(()=>routingUI.changeLayer(event.target.value));
    if($('#routingWidth'))$('#routingWidth').onchange=event=>routingUI.width(Number(event.target.value)||null);
    if($('#boardGrid'))$('#boardGrid').onchange=event=>{S.boardGrid=Number(event.target.value);if(S.canvas?.geo){S.canvas.gridMm=S.boardGrid;S.canvas.draw();}};
  }
  host.querySelector('#runChecks')?.addEventListener('click', safely(runChecks));
  host.querySelector('#buildButton')?.addEventListener('click', safely(buildProject));host.querySelector('#drawerExport')?.addEventListener('click', safely(openExport));
  host.querySelector('#drawerSettings')?.addEventListener('click', safely(() => openSettings('manufacturing')));
  if(panel==='manufacturing')manufacturingUI.bind();
}

function openPartPicker(part) {
  S.partPickerToken=(S.partPickerToken||0)+1;
  S.pickedPart=part;$('#partValue').value=part.value||'';$('#partDescription').textContent=part.description||'';$('#partFootprint').value=part.footprint||'';$('#partSymbol').value=part.symbol||'';
  const text=`${part.footprint||''} ${part.description||''}`;
  const prefix=part.reference||(/Resistor|resistor|电阻/.test(text)?'R':/Capacitor|capacitor|电容/.test(text)?'C':/Connector|connector|Header/.test(text)?'J':/LED|Diode/.test(text)?'D':'U');
  if(![...$('#partPrefix').options].some(option=>option.value===prefix))$('#partPrefix').add(new Option(prefix,prefix));
  $('#partPrefix').value=prefix;
  dialog('#partDialog');
}
async function addPickedPart(e) {
  e.preventDefault();if(!editable()||!S.pickedPart)return;
  const owner={pid:S.pid,load:S.projectLoadToken,user:S.session?.user?.id||'device',generation:S.generation,picker:S.partPickerToken},part={sheet:S.schematicSheet||'',ref:$('#partPrefix').value+'1',value:$('#partValue').value,footprint:$('#partFootprint').value.trim(),symbol:$('#partSymbol').value.trim(),lcsc:S.pickedPart.lcsc||'',mpn:S.pickedPart.mpn||'',description:S.pickedPart.description||''};
  const current=()=>S.pid===owner.pid&&S.projectLoadToken===owner.load&&(S.session?.user?.id||'device')===owner.user&&S.generation===owner.generation&&S.partPickerToken===owner.picker&&$('#partDialog').open&&editable()&&!S.openingProject;
  if(part.footprint.startsWith('Project:')||part.symbol.startsWith('Project:')){await save();if(!current())return;}
  const libraryPath=owner.pid?`/api/workbench/projects/${owner.pid}/library`:'/api/workbench/library';
  await api(`${libraryPath}/footprint-info?id=${encodeURIComponent(part.footprint)}`);if(!current())return;
  if(part.symbol){await api(`${libraryPath}/symbol-info?id=${encodeURIComponent(part.symbol)}`);if(!current())return;}
  const next=addComponent(S.spec,part);
  const ref=next.components.at(-1).ref;S.inspector=true;commit(next,`Added ${ref}`,ref);$('#partDialog').close();if(S.active==='library')setView('schematic');toast(`${ref} added`);
}
function invalidateCheckDisplay(){
  markupUI.cancel('design');
  $('#checkCount').textContent='—';const results=$('#checkResults');
  if(results&&(results.dataset.designVersion||$('#runChecks')?.disabled)){
    results.innerHTML='<p class="drawer-description" role="status">Design changed. Run checks again.</p>';delete results.dataset.designVersion;
  }
}
async function runChecks() {
  const button=$('#runChecks'),results=$('#checkResults'),loadToken=S.projectLoadToken,token=S.checkRunToken=(S.checkRunToken||0)+1;
  if(!button||!results||S.starting||S.openingProject)return;
  const visible=()=>S.checkRunToken===token&&S.projectLoadToken===loadToken&&!S.openingProject&&toolDock.has('checks')&&$('#runChecks')===button&&$('#checkResults')===results&&button.isConnected;
  let pid,version,generation;
  const current=()=>visible()&&S.pid===pid&&S.version===version&&S.generation===generation&&!S.dirty&&!S.saving&&!(S.pendingDesignVersion>version);
  const stale=(message='Design changed. Run checks again.')=>{if(visible()){results.innerHTML=`<p class="drawer-description" role="status">${esc(message)}</p>`;delete results.dataset.designVersion;$('#checkCount').textContent='—';}};
  button.disabled=true;button.textContent='Checking…';results.innerHTML='<p class="drawer-description" role="status">Checking saved design…</p>';delete results.dataset.designVersion;$('#checkCount').textContent='—';
  try {
    pid=await save();if(!visible()||S.pid!==pid)return;version=S.version;generation=S.generation;
    if(!current()){stale();return;}
    const data = await api(`/api/workbench/projects/${pid}/checks`, { method: 'POST' });
    if(!current()){stale();return;}
    if(data.version!==version){stale('Saved design changed. Reload the project before running checks.');return;}
    const status=S.status||await api('/api/status');if(!current()){stale();return;}
    if(status.kicad_cli&&status.libs?.footprints){
      const native=await api(`/api/workbench/projects/${pid}/native-checks`,{method:'POST'});
      if(!current()){stale();return;}
      if(native.design_version!==version){stale('Saved design changed. Reload the project before running checks.');return;}
      S.project.workbench_checks=native;
      data.checks=data.checks.filter(c=>!['erc','drc'].includes(c.id));
      data.checks.push({id:'erc',title:'KiCad ERC',status:!native.erc.clean?'error':native.erc.ignored||native.erc.warnings.length?'warning':'passed',detail:`${native.erc.errors.length} errors · ${native.erc.warnings.length} warnings · ${native.erc.ignored||0} filtered findings`,findings:[...native.erc.errors,...native.erc.warnings,...(native.erc.ignored_list||[]).map(f=>({...f,description:`Filtered (${f.type}): ${f.description}`}))]},
        {id:'drc',title:'KiCad DRC',status:native.drc.clean?'passed':'error',detail:`${native.drc.errors} errors · ${native.drc.unconnected} unconnected · ${native.drc.warnings} warnings`,findings:[...native.drc.error_list,...native.drc.unconnected_list,...(native.drc.warning_list||[])]});
    }
    if(!current()){stale();return;}
    results.innerHTML=`<p class="drawer-description" role="status">Saved design v${version}</p>`+data.checks.map(c => `<div class="check-row ${esc(c.status)}"><div class="check-row-title">${icon(c.status === 'passed' ? 'check' : c.status === 'error' ? 'warning' : 'info')}${esc(c.title)}</div><p>${esc(c.detail)}</p>${c.findings?.length?`<details class="check-details"><summary>Show findings</summary>${c.findings.map(f=>`<p>${esc(typeof f==='string'?f:f.description||JSON.stringify(f))}</p>`).join('')}</details>`:''}</div>`).join('');
    results.dataset.designVersion=String(version);
    $('#checkCount').textContent = data.checks.filter(c => c.status !== 'passed').length;
  } catch(error){if(!visible())return;if(version!==undefined&&!current()){stale();return;}results.innerHTML=`<p class="drawer-description" role="alert">Could not run checks. ${esc(error.message)}</p>`;throw error;}
  finally { if(visible()){button.disabled=false;button.textContent='Run checks';} }
}
async function buildProject() {
  if(!editable())throw new Error('Only project editors can build the design.');
  await save(); S.status = await api('/api/status');
  if (!S.status.kicad_cli || !S.status.libs.footprints) { toast('Install KiCad and its libraries to run a native build.', true); await openSettings('tools'); return; }
  const result = await api(`/api/projects/${S.pid}/spec`, { method: 'PUT', body: S.spec });
  if (result.ok === false) throw new Error((result.errors || ['Build validation failed']).join('\n'));
  toast('OpenFabro build started. Follow its progress in Chat.');
}
function autoLayout() {
  if(!editable())return;
  if (busy()) return toast('Stop the build before arranging components.', true);
  if(S.active==='layout'){runEngineering('place').catch(fail);return;}
  const next = structuredClone(S.spec); const unlocked = next.components.filter(c => !c.placement?.locked);
  if (S.active === 'schematic') { next.editor ||= {}; next.editor.positions = {}; next.components.forEach((c, i) => next.editor.positions[c.ref] = [180 + i % 4 * 280, 220 + Math.floor(i / 4) * 250]); }
  else {
    const cols = Math.max(1, Math.ceil(Math.sqrt(unlocked.length))); const rows = Math.max(1, Math.ceil(unlocked.length / cols));
    unlocked.forEach((c, i) => c.placement = { ...c.placement, x_mm: +(next.board.width_mm * (i % cols + 1) / (cols + 1)).toFixed(2), y_mm: +(next.board.height_mm * (Math.floor(i / cols) + 1) / (rows + 1)).toFixed(2), rotation: c.placement?.rotation || 0 });
  }
  commit(next, 'Arranged components'); toast('Components arranged. Native placement and routing run during a build.');
}

// OpenFabro agent event stream. Opening or editing a project does not make a model request.
function scheduleCollaborationRefresh(){if(S.collaborationRefreshQueued)return;S.collaborationRefreshQueued=true;queueMicrotask(()=>{S.collaborationRefreshQueued=false;if(!S.pid||S.starting||S.openingProject||S.project.access?.role==='revoked')return;const owner=collaborationUI.commentOwner();if(S.collaborationLiveOwner!==owner||!S.socket||S.socket.readyState===WebSocket.CLOSED||S.socket.readyState===WebSocket.CLOSING)connectEvents();if(collaborationUI.commentsOwner!==owner&&collaborationUI.commentsPendingOwner!==owner&&collaborationUI.commentFailureOwner!==owner)collaborationUI.loadComments().catch(error=>{if(collaborationUI.commentOwner()===owner)fail(error);});});}
function disconnectEvents() { clearTimeout(S.reconnect);clearTimeout(S.presenceTimer);S.presenceSent=0;S.collaborationLiveOwner=null; if (S.socket) { S.socket.onclose = null; S.socket.close(); S.socket = null; }collaborationUI.presence({users:[]}); }
function publishPresence(cursor=undefined){
  if(S.socket?.readyState!==WebSocket.OPEN)return;
  if(cursor!==undefined)S.presenceCursor=cursor;
  S.presencePacket={type:'presence',view:S.active,sheet:S.schematicSheet||'',ref:S.selected||null,cursor:S.presenceCursor||null};
  clearTimeout(S.presenceTimer);
  S.presenceTimer=setTimeout(()=>{if(S.socket?.readyState===WebSocket.OPEN){S.socket.send(JSON.stringify(S.presencePacket));S.presenceSent=performance.now();}},Math.max(0,70-(performance.now()-(S.presenceSent||0))));
}
async function syncSavedDesign(){
  if(!S.pid||!S.pendingDesignVersion||S.designSync||S.saving||S.openingProject)return;
  if(S.pendingDesignVersion<=S.version){S.pendingDesignVersion=0;return;}
  if(S.dirty||S.canvas?.interacting){toast('Another editor saved changes. Save or reload before continuing.',true);return;}
  const pid=S.pid,version=S.version,generation=S.generation,loadToken=S.projectLoadToken,statusSeq=S.statusSeq;
  let applied=false;
  const pending=(async()=>{
    const p=await api(`/api/projects/${pid}`);
    if(S.pid!==pid||S.projectLoadToken!==loadToken||S.openingProject||S.saving||S.dirty||S.generation!==generation||S.version!==version||S.canvas?.interacting)return;
    if((p.state.workbench?.version||0)<=S.version)return;
    const historyState=await aiChanges.prepare(pid,p.state);
    if(S.pid!==pid||S.projectLoadToken!==loadToken||S.openingProject||S.saving||S.dirty||S.generation!==generation||S.version!==version||S.canvas?.interacting)return;
    if(S.statusSeq!==statusSeq)Object.assign(p.state,{status:S.project.status,status_note:S.project.status_note,runtime:S.project.runtime});
    routingUI.stop();S.spec=p.state.spec;S.project={...p.state,title:p.title};S.version=p.state.workbench.version;S.generation++;invalidateCheckDisplay();
    S.undo=historyState.undo;S.redo=historyState.redo;aiChanges.commit(pid,historyState);if(S.pendingDesignVersion<=S.version)S.pendingDesignVersion=0;
    applied=true;title(p.title);renderView();renderInspector();renderChat();applyAccessUI();savedLabel(historyState.batch?'AI design changes saved':'Updated from another editor','saved');
  })();
  S.designSync=pending;applyAccessUI();
  try{await pending;}finally{if(S.designSync===pending)S.designSync=null;applyAccessUI();renderChat();}
  if(applied&&S.pid===pid&&S.pendingDesignVersion>S.version)syncSavedDesign().catch(fail);
}
function connectEvents() {
  disconnectEvents(); if (!S.pid||S.starting||S.openingProject) return;
  const pid = S.pid,liveOwner=collaborationUI.commentOwner(),socket = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/api/projects/${pid}/ws?after=${S.lastSeq}`); S.socket = socket;S.collaborationLiveOwner=liveOwner;
  socket.onopen=()=>publishPresence();
  socket.onmessage = event => {
    if (S.pid !== pid||S.socket!==socket) return;
    const e = JSON.parse(event.data);if(e.type==='presence'){collaborationUI.presence(e,liveOwner);return;}if (e.seq <= S.lastSeq) return; S.lastSeq = e.seq;
    S.events.push(e);
    if (e.type === 'status') {
      S.statusSeq=e.seq;
      S.project.status = e.status; S.project.status_note = e.note; S.project.runtime=e.runtime; updateSendState();mechanicalUI.sync();
      if (['done', 'error', 'stopped', 'idle'].includes(e.status)) {
        const statusLoadToken=S.projectLoadToken,statusRequestSeq=S.statusSeq;api(`/api/projects/${pid}`).then(p=>{const incoming=p.state.workbench?.version||0;if(S.pid!==pid||S.projectLoadToken!==statusLoadToken||S.statusSeq!==statusRequestSeq||S.openingProject||S.dirty||S.saving||incoming<S.version)return;if(incoming>S.version){S.pendingDesignVersion=Math.max(S.pendingDesignVersion||0,incoming);syncSavedDesign().catch(fail);return;}if(p.state.spec&&JSON.stringify(p.state.spec)!==JSON.stringify(S.spec)){S.undo=[];S.redo=[];aiChanges.commit(pid,{batch:null});S.generation++;invalidateCheckDisplay();}aiChanges.invalidateFiles(p.state);S.project=p.state;S.version=incoming;if(p.state.spec)S.spec=p.state.spec;title(p.title);if(!mechanicalUI.deferRefresh())renderView();renderInspector();renderChat();}).catch(fail);
      }
    }
    if (e.type === 'visual') { S.project.visuals ||= {}; S.project.visuals[`${e.step}:${e.kind}`] = e; if (['layout', '3d', 'files'].includes(S.active)) renderView(); }
    if (e.type === 'review') { S.project.workbench_review = e.review; if (S.active === 'review') renderView(); }
    if(e.type==='ai_files_changed'&&e.request_id){S.project.ai_file_changes||={};S.project.ai_file_changes[e.request_id]=[...new Set([...(S.project.ai_file_changes[e.request_id]||[]),...(e.paths||[])])];aiChanges.invalidateFiles(S.project);renderChat();}
    if(e.type==='ai_change_set'){renderChat();if(S.active==='files'&&!S.fileDrafts?.size)renderFiles();}
    if(e.type==='mechanical_asset')mechanicalUI.published(e);
    if(e.type==='mechanical_history_changed')mechanicalUI.historyChanged(e);
    if(e.type==='comments_changed')collaborationUI.loadComments().catch(fail);
    if(e.type==='module_catalog_changed'||e.type==='design_saved')moduleUpdatesUI.refresh().catch(()=>{});
    if(e.type==='access_changed'){const owner=collaborationUI.commentOwner(),load=S.projectLoadToken,sequence=S.accessReadSequence=(S.accessReadSequence||0)+1,current=()=>S.pid===pid&&S.projectLoadToken===load&&S.socket===socket&&collaborationUI.commentOwner()===owner&&S.accessReadSequence===sequence&&!S.openingProject;api(`/api/projects/${pid}`).then(p=>{if(!current())return;S.project.access=p.state.access;applyAccessUI();renderInspector();if(toolDock.has('comments'))collaborationUI.renderComments();}).catch(error=>{if(current())fail(error);});}
    if (e.type === 'design_saved' && e.version > S.version) {
      S.pendingDesignVersion=Math.max(S.pendingDesignVersion||0,e.version);syncSavedDesign().catch(fail);
    }
    if (['chat', 'tool', 'tool_result', 'question', 'answer', 'finish', 'status', 'step','design_saved'].includes(e.type)) renderChat();
  };
  socket.onclose = event => {
    if(S.pid!==pid||S.socket!==socket)return;
    if([4401,4403].includes(event.code)){
      S.project.access={role:'revoked',can_edit:false,can_comment:false,can_manage:false};applyAccessUI();
      toast('Your access to this project has been revoked.',true);
      api('/api/workbench/session').then(session=>{S.session=session;if(session.authenticated)return openProjectBrowser();disconnectEvents();disposeCanvas();$('#viewContent').innerHTML='<div class="empty-canvas"><h2>Project access ended</h2><p>Open a new project link or sign in to the workspace.</p></div>';S.inspector=false;renderInspector();collaborationUI.showLogin('This project link has expired or been revoked.');}).catch(fail);
      return;
    }
    S.reconnect=setTimeout(connectEvents,3000);
  };
}
function renderChat() {
  if(S.starting||S.openingProject){$('#welcome').hidden=true;$('#conversation').hidden=true;if(!$('#chatProjectLoading')){const status=document.createElement('div');status.id='chatProjectLoading';status.className='typing-status';status.textContent='Opening project…';$('#chatContent').append(status);}return;}
  $('#chatProjectLoading')?.remove();
  const messages = S.events.filter(e => ['chat', 'tool', 'tool_result', 'question', 'answer', 'finish', 'status', 'step','ai_change_set'].includes(e.type)||e.type==='design_saved'&&e.source==='ai');
  const aiBatches=new Map();for(const event of messages)if(event.type==='design_saved'){const key=event.request_id||'version:'+event.version,previous=aiBatches.get(key);aiBatches.set(key,{first:Math.min(previous?.first??Infinity,event.from_version??event.version-1),last:event});}
  $('#welcome').hidden = messages.length > 0; $('#conversation').hidden = messages.length === 0;
  const answers = new Map(S.events.filter(e => e.type === 'answer').map(e => [e.id, e]));
  $('#conversation').innerHTML = messages.map(e => {
    if (e.type === 'answer') return '';
    if(e.type==='ai_change_set'){if(messages.findLast(item=>item.type==='ai_change_set'&&item.request_id===e.request_id)!==e)return'';return`<div class="ai-design-change"><strong>AI changes · ${e.files} project file${e.files===1?'':'s'}</strong><div><button class="secondary-button" data-ai-files-review="${esc(e.request_id)}">Review all changes</button></div></div>`;}
    if(e.type==='design_saved'){
      const batch=aiBatches.get(e.request_id||'version:'+e.version);if(batch.last!==e)return'';
      const owned=aiChanges.owned.get(e.request_id)?.pid===S.pid,files=S.project.ai_file_changes?.[e.request_id]||[],undoBatch=aiChanges.batches.get(S.pid),canUndo=owned&&!files.length&&undoBatch?.request_id===e.request_id&&undoBatch.version===S.version&&e.version===S.version&&S.undo.length&&!S.dirty&&!S.saving&&!busy()&&editable();
      return`<div class="ai-design-change"><strong>AI design changes · v${batch.first} → v${e.version}</strong><div><button class="secondary-button" data-ai-review-from="${batch.first}" data-ai-review-to="${e.version}">Review changes</button><button class="secondary-button" data-ai-undo="${esc(e.request_id||'')}" ${canUndo?'':'disabled'}>Undo design</button></div>${files.length?`<small>${files.length} project file${files.length===1?'':'s'} also changed. Automatic design-only undo is unavailable for this batch.</small>`:!owned?'<small>Another tab or external request · inspect or restore through history.</small>':''}</div>`;
    }
    if(e.type==='tool_result')return `<details class="tool-result"><summary>${icon(e.ok===false||e.result?.ok===false?'warning':'check')}${esc(e.name)} · ${e.ok===false?'Needs attention':'Completed'}</summary><pre>${esc(JSON.stringify(e.result??e.error,null,2).slice(0,40000))}</pre></details>`;
    if (e.type === 'status') return e.note && ['error', 'stopped'].includes(e.status) ? `<div class="chat-message system ${e.status === 'error' ? 'error' : ''}">${esc(e.note)}</div>` : '';
    if (e.type === 'step') return e.status === 'done' || e.status === 'error' ? `<div class="chat-message tool">${icon(e.status === 'done' ? 'check' : 'warning')} ${esc(e.key)} · ${esc(e.detail || e.status)}</div>` : '';
    if (e.type === 'tool') return `<div class="chat-message tool">${icon('wrench')} ${esc(e.text || e.name || 'Running engineering tool')}</div>`;
    if (e.type === 'question') return `<div class="chat-message assistant"><div class="message-author">${icon('sparkles')}OpenFabro</div>${esc(e.question)}${answers.has(e.id) ? `<p class="muted">${esc(answers.get(e.id).text)}</p>${referenceMarkup(answers.get(e.id).canvas_reference,S.pid)}` : `<div class="question-options">${(e.options || []).map(o => `<button data-answer-id="${esc(e.id)}" data-answer="${esc(o)}">${esc(o)}</button>`).join('')}</div>`}</div>`;
    const role = e.role || 'assistant';
    return `<div class="chat-message ${esc(role)}">${role === 'assistant' ? '<div class="message-author"><img src="/static/openfabro-mascot.png" alt="">OpenFabro</div>' : ''}${role==='assistant'?`<div class="markdown">${renderMarkdown(e.text||'')}</div>`:esc(e.text || '')}${referenceMarkup(e.canvas_reference,S.pid)}</div>`;
  }).join('') + (busy() ? '<div class="typing-status">OpenFabro is working on your project…</div>' : '');
  $$('[data-answer-id]').forEach(b => b.onclick = safely(async () => { await api(`/api/projects/${S.pid}/answer`, { method: 'POST', body: { id: b.dataset.answerId, text: b.dataset.answer } }); }));
  $$('[data-ai-review-from]').forEach(button=>button.onclick=safely(()=>openHistory({from_version:Number(button.dataset.aiReviewFrom),version:Number(button.dataset.aiReviewTo)})));
  $$('[data-ai-undo]').forEach(button=>button.onclick=()=>{if(!button.disabled)undo();});
  $$('[data-ai-files-review]').forEach(button=>button.onclick=safely(()=>aiFilesUI.open(button.dataset.aiFilesReview)));
  $('#chatContent').scrollTop = $('#chatContent').scrollHeight;
}
function updateSendState() {
  const pending=S.chatSends.get(chatKey()),attaching=S.attachmentBusy?.key===chatKey()&&S.attachmentBusy.loadToken===S.projectLoadToken;$('#stopRunButton').hidden = !busy()||!editable();$('#sendButton').disabled=!editable()||attaching||!!markupUI.drawing||['preparing','submitting'].includes(pending?.phase);
  const label = busy() ? S.project.status === 'waiting' ? 'Send answer' : 'Send additional instructions' : 'Send message';
  $('#sendButton').setAttribute('aria-label', label);
  $('#sendButton').title = label + ' (Enter)';
}
function chatKey(){return S.pid||'__new__';}
function recordChatDraft(touch=false){
  const key=chatKey(),old=S.chatDrafts.get(key),text=$('#chatInput').value;
  const changed=touch||!old||old.text!==text||old.attachment!==S.attachment;
  const draft={text,attachment:S.attachment,generation:changed?++S.chatDraftGeneration:old.generation};S.chatDrafts.set(key,draft);return draft;
}
function migrateChatDraft(pid){
  for(const map of [S.chatDrafts,S.chatSends])if(map.has('__new__')){const value=map.get('__new__');map.set(pid,value);map.delete('__new__');if(map===S.chatSends)value.key=pid;}
  if(S.attachmentBusy?.key==='__new__')S.attachmentBusy.key=pid;
}
function restoreChatDraft(pid){
  const draft=S.chatDrafts.get(pid);$('#chatInput').value=draft?.text||'';S.attachment=draft?.attachment||null;$('#attachmentLabel').hidden=!S.attachment;if(S.attachment)$('#attachmentLabel').textContent=`${S.attachment.name} · attached to your next message`;
}
async function sendMessage(event) {
  event.preventDefault();
  if(!editable())throw new Error('Only project editors can send AI instructions.');
  if(markupUI.drawing)return toast('Finish the current markup stroke before sending.',true);
  if(S.attachmentBusy?.key===chatKey()&&S.attachmentBusy.loadToken===S.projectLoadToken)return toast('Wait for the reference to finish attaching.',true);
  const input=$('#chatInput'),draft=recordChatDraft(),raw=draft.text.trim();if(!raw)return input.focus();
  const previous=S.chatSends.get(chatKey());if(['preparing','submitting'].includes(previous?.phase))return;
  if(previous?.phase==='failed'&&previous.markup&&previous.generation===draft.generation&&!markupUI.active&&!previous.retryable)throw Error('The marked view was cancelled. Start Markup again before sending this question.');
  const core={pid:S.pid,loadToken:S.projectLoadToken,generation:S.generation,mode:S.mode},same=()=>S.projectLoadToken===core.loadToken&&!S.openingProject&&(!core.pid||S.pid===core.pid)&&S.generation===core.generation&&S.mode===core.mode&&(core.version===undefined||S.version===core.version);
  const selected=[...S.selection],selectedRefNames=selectedRefs(),net=S.selectedNet,objects=S.objectOnlySelection?.scope===objectsUI.scope?objectsUI.chosen.slice(0,20).map(n=>({id:n.id,kind:n.kind,ref:n.ref,net:n.net,native_id:n.native?.id})):[];
  const record=previous?.phase==='failed'&&previous.retryable&&previous.generation===draft.generation&&previous.mode===S.mode?previous:{key:chatKey(),generation:draft.generation,mode:S.mode,attachment:draft.attachment,markup:markupUI.token(),text:draft.text,phase:'preparing'};
  record.phase=record.body?'submitting':'preparing';S.chatSends.set(record.key,record);updateSendState();
  try {
    if(!record.body){
      const config=await api('/api/config');if(!same())throw Object.assign(Error('The project changed before sending.'),{cancelled:true});S.config=config;const ai=config.ai;
      const question=[...S.events].reverse().find(e=>e.type==='question'&&!S.events.some(answer=>answer.type==='answer'&&answer.id===e.id)),action=messageAction(S.project.status,raw,question?.id);
      if(action==='queue'&&!S.project.runtime?.agent)throw Error('Wait for the engineering operation to finish, or stop it before sending.');
      if(!['queue','answer'].includes(action)){
        if(ai.provider==='codex'&&!(await api('/api/workbench/codex/status')).ready)throw Object.assign(Error('Sign in to the local Codex CLI to continue.'),{needsSettings:true});
        if((ai.provider==='anthropic'&&!ai.anthropic_api_key&&!S.status?.ai?.ready)||(ai.provider==='openai'&&(!ai.openai_base_url||!ai.openai_model)))throw Object.assign(Error('Choose and configure an AI model before sending.'),{needsSettings:true});
      }
      if(!same())throw Object.assign(Error('The project changed before sending.'),{cancelled:true});
      const pid=await save();if(!same()||S.pid!==pid)throw Object.assign(Error('The project changed before sending.'),{cancelled:true});core.pid=pid;core.version=S.version;record.key=pid;
      const reference=record.markup?await markupUI.reference(record.markup):null;
      if(!same())throw Object.assign(Error('The marked project changed before sending.'),{cancelled:true});
      let text=raw;if(selected.length)text+=`\n\nSelected components: ${selectedRefNames.join(', ')}. Selected schematic units: ${selected.join(', ')}.`;if(net)text+=`\n\nSelected net: ${net}.`;
      if(objects.length)text+='\n\nSelected design objects (reference data): '+JSON.stringify({project:pid,version:S.version,objects});
      if(record.attachment)text+=`\n\nAttached reference: ${record.attachment.name}\n${record.attachment.text}`;
      if(record.mode==='chat'&&(ai.provider!=='codex'||action==='queue'))text=`Discussion request: explain and review. Do not change or build the design unless I explicitly ask.\n\n${text}`;
      record.url=action==='answer'?`/api/projects/${pid}/answer`:action==='queue'?`/api/workbench/projects/${pid}/steer`:ai.provider==='codex'?`/api/workbench/projects/${pid}/codex`:`/api/projects/${pid}/message`;
      record.body={text,mode:record.mode,request_id:crypto.randomUUID().replaceAll('-',''),...(action==='answer'?{id:question.id}:{}),...(reference?{canvas_ref:reference.id}:{})};record.action=action;
    }
    aiChanges.register(record.body.request_id,record.key);record.phase='submitting';await api(record.url,{method:'POST',body:record.body});record.phase='accepted';
    if(S.pid===record.key&&!S.openingProject)recordChatDraft();
    const current=S.chatDrafts.get(record.key);
    if(current?.generation===record.generation&&current.text===record.text&&current.attachment===record.attachment){
      S.chatDrafts.set(record.key,{text:'',attachment:null,generation:++S.chatDraftGeneration});
      if(S.pid===record.key&&!S.openingProject){input.value='';S.attachment=null;$('#attachmentLabel').hidden=true;if(record.markup)markupUI.cancel('sent');}
    }
    if(record.action==='queue'&&S.pid===record.key)toast('Instructions queued for the next step');
  }catch(error){record.phase='failed';record.retryable=!!record.body&&(!error.status||error.status>=500)&&!error.cancelled;if(chatKey()===record.key&&!S.openingProject){if(error.cancelled)toast('The view changed before sending. Your draft is kept.',true);else if(error.needsSettings){toast(error.message,true);await openSettings('ai');}else throw error;}}
  finally{if(record.phase==='accepted'&&S.chatSends.get(record.key)===record)S.chatSends.delete(record.key);updateSendState();}
}
async function attachFile(file) {
  if (!file) return; if (file.size > 8_000_000) throw new Error('Choose a file smaller than 8 MB.');
  if(!editable())throw Error('Only project editors can attach references.');
  const operation={key:chatKey(),loadToken:S.projectLoadToken},current=()=>S.attachmentBusy===operation&&S.projectLoadToken===operation.loadToken&&!S.openingProject&&operation.key===chatKey();S.attachmentBusy=operation;recordChatDraft(true);updateSendState();
  try{
    const pid=await save();if(!current()||S.pid!==pid)return;operation.key=pid;
    const data=await fileBase64(file);if(!current())return;
    const result=await api(`/api/workbench/projects/${pid}/attachments`,{method:'POST',body:{name:file.name,data}});if(!current())return;
    S.attachment=result;recordChatDraft(true);$('#attachmentLabel').textContent=`${file.name} · attached to your next message`;$('#attachmentLabel').hidden=false;$('#chatInput').focus();toast('Reference attached');
  }catch(error){if(current())throw error;}
  finally{if(S.attachmentBusy===operation)S.attachmentBusy=null;updateSendState();}
}
function fileBase64(file) { return new Promise((resolve, reject) => { const r = new FileReader(); r.onload = () => resolve(r.result.split(',')[1]); r.onerror = reject; r.readAsDataURL(file); }); }

// Settings and the original manufacturing pipeline.
async function openSettings(section = 'ai') {
  if(S.session?.admin===false){await collaborationUI.openWorkspace();return;}
  S.config = await api('/api/config'); const form = $('#settingsForm');
  $$('[name]', form).forEach(input => { const [group, key] = input.name.split('.'); const value = S.config[group]?.[key]; if (value !== undefined) input.value = value; });
  setSettingsPane(section); syncProvider(); dialog('#settingsDialog'); loadStatus();
  api('/api/workbench/codex/status').then(s => { $('#codexConnection').textContent = s.ready ? `Signed in · ${s.model}` : s.available ? 'Codex installed · sign in with codex login' : 'Codex CLI is not installed on this computer'; }).catch(fail);
}
function setSettingsPane(section) { $$('[data-settings]').forEach(b => b.classList.toggle('active', b.dataset.settings === section)); $$('[data-settings-pane]').forEach(p => p.hidden = p.dataset.settingsPane !== section); }
function syncProvider() { const provider = $('[name="ai.provider"]').value; $$('[data-provider]').forEach(div => div.hidden = div.dataset.provider !== provider); }
async function saveSettings(event) {
  event?.preventDefault(); const patch = {};
  $$('[name]', $('#settingsForm')).forEach(input => {
    const [group, key] = input.name.split('.'); patch[group] ||= {};
    if (input.type === 'password' && input.value.startsWith('•')) return;
    patch[group][key] = input.type === 'number' ? Number(input.value) : input.value;
  });
  S.config = await api('/api/config', { method: 'POST', body: patch }); updateModelLabel(); $('#settingsResult').textContent = 'Settings saved'; toast('Settings saved');
}
function updateModelLabel() {
  const ai = S.config?.ai; if (!ai) return;
  if (ai.provider === 'codex') { $('#modelLabel').textContent = ai.codex_model || 'Codex'; return; }
  const model = ai.provider === 'anthropic' ? ai.anthropic_model : ai.openai_model;
  $('#modelLabel').textContent = ai.provider === 'anthropic' && !ai.anthropic_api_key && !S.status?.ai?.ready ? 'Select model' : model || 'Select model';
}
async function loadStatus() {
  try {
    S.status = await api('/api/status'); updateModelLabel();
    const tools = [['KiCad', S.status.kicad_cli, S.status.kicad_version], ['KiCad libraries', S.status.libs?.footprints, S.status.libs?.footprints ? `${S.status.libs.footprints} footprints` : ''], ['TraceMaker', S.status.tracemaker, S.status.tracemaker_version], ['FreeCAD', S.status.freecad, S.status.freecad_version], ['ngspice', S.status.ngspice, S.status.ngspice_version]];
    $('#toolStatus').innerHTML = tools.map(([name, ok, version]) => `<div class="tool-status-item">${icon('wrench')}<span>${name}</span><span class="tool-state ${ok ? 'ready' : ''}">${ok ? esc(version || 'Detected') : 'Not installed'}</span></div>`).join('');
  } catch (e) { $('#toolStatus').textContent = e.message; }
}
async function openExport() {
  const pid=S.pid,loadToken=S.projectLoadToken,current=()=>S.pid===pid&&S.projectLoadToken===loadToken&&!S.openingProject;
  await save();if(!current())return;
  const data=await loadFileCatalog(params=>api(`/api/workbench/projects/${pid}/files?${new URLSearchParams(params)}`),{isCurrent:current}).catch(error=>{if(error.cancelled)return null;throw error;});if(!data||!current())return;
  const project=await api(`/api/projects/${pid}`);if(!current())return;if(project.state.workbench?.version!==data.design_version)throw new Error('The saved design changed while export was loading. Reopen Export.');
  const exportSpec=structuredClone(project.state.spec),exportVersion=data.design_version;
  const valid=()=>{if(!current()||S.version!==exportVersion){toast('The project changed. Reopen Export before downloading.',true);return false;}return true;};
  const native = data.files.filter(f => /\.(zip|kicad_pcb|kicad_sch|stl|step|bin|uf2)$/i.test(f.name));
  $('#exportOptions').innerHTML = `<button class="export-option" id="exportJSON">${icon('file')}<div><strong>Design specification</strong><small>Editable components, netlist, board rules, and placement</small></div><span>JSON</span></button><button class="export-option" id="exportCSV">${icon('table')}<div><strong>Bill of materials</strong><small>Saved component values, footprints, and part numbers</small></div><span>CSV</span></button>${native.map((f, i) => `<a class="export-option" href="${esc(f.url)}" download="${esc(f.name)}">${icon('download')}<div><strong>${esc(f.name)}</strong><small>Native output from the OpenFabro pipeline</small></div></a>`).join('')}<div class="check-row"><p style="margin:8px 0">${native.length ? 'Rebuild after editing before using existing manufacturing outputs.' : 'Gerbers, native KiCad, firmware, and enclosure CAD files become available after a successful native build.'}</p></div>`;
  $('#exportDialog .modal-description').textContent=`${project.title} · saved design v${exportVersion}.`;
  $('#exportOptions').querySelectorAll('a').forEach((link,index)=>{const file=native[index];link.querySelector('small').textContent=[file.path,fileBadge(file)].filter(Boolean).join(' · ');link.onclick=event=>{if(!valid())event.preventDefault();};});
  $('#exportJSON').onclick = () => {if(valid())download(`${exportSpec.name || 'design'}.json`, JSON.stringify(exportSpec, null, 2));};
  $('#exportCSV').onclick = safely(()=>{if(valid())return exportBOM();}); dialog('#exportDialog');
}
async function exportBOM() { await save(); const a = document.createElement('a'); a.href = `/api/workbench/projects/${S.pid}/bom.csv`; a.download = 'bill-of-materials.csv'; a.click(); toast('BOM exported'); }
async function openShare() { await collaborationUI.openShare(); }
async function importFiles(files) {
  if (!files.length) return;
  if (S.dirty) await save();
  if (files.length === 1 && files[0].name.endsWith('.json')) {
    const spec = JSON.parse(await files[0].text()); const result = await api('/api/workbench/projects', { method: 'POST', body: { title: spec.title || files[0].name.replace(/\.json$/, ''), spec } });
    await openProject(result.id); await refreshProjects(); toast('Design imported'); return;
  }
  const body = { ai: false, files: await Promise.all([...files].map(async f => ({ name: f.name, data: await fileBase64(f) }))) };
  const result = await api('/api/import', { method: 'POST', body }); await openProject(result.id); await refreshProjects(); toast('KiCad import started. Follow progress in Chat.');
}
async function openHistory(selection=null) {
  const pid=S.pid,loadToken=S.projectLoadToken,historyToken=S.historyLoadToken=(S.historyLoadToken||0)+1;
  const current=()=>S.pid===pid&&S.projectLoadToken===loadToken&&S.historyLoadToken===historyToken&&!S.openingProject;
  await save();if(!current())return;
  const history=await api(`/api/workbench/projects/${pid}/history`);if(!current())return;
  const version=S.version;let comparisonToken=0,previewToken=0;
  const entries=[...S.events.filter(e=>['chat','step','finish'].includes(e.type)).map(e=>({time:e.t*1000,text:e.text||`${e.key}: ${e.detail||e.status}`})),...S.actions];
  $('#historyContent').innerHTML=`<div class="history-versions">${history.versions.map(v=>`<div class="history-version"><div><strong>Version ${v.version}</strong>${v.version===history.current_version?' <span class="current-version">Current</span>':''}<small>${esc(new Date(v.saved_at*1000).toLocaleString())} · ${v.components} components · ${v.nets} nets${v.origin?' · AI':''}</small></div><button class="secondary-button" data-compare-version="${v.version}">Compare</button>${v.version!==history.current_version&&editable()?`<button class="secondary-button" data-restore-version="${v.version}">Restore</button>`:''}</div>`).join('')}</div><div id="historyCompareSummary" class="history-compare-summary" role="status" hidden></div><div id="historyDiffRows" hidden></div><section id="historyPreview" class="history-preview" hidden><div class="history-preview-heading"><span>Read-only schematic</span><div id="historyPreviewVersions"></div></div><div id="historyPreviewCanvas"></div></section><details id="historyEvidence" hidden><summary class="activity-summary">Comparison evidence and hashes</summary><pre id="historyComparison" class="history-comparison" aria-label="Complete comparison evidence"></pre></details><details id="historyActivity"><summary class="activity-summary">Conversation and activity</summary>${entries.length?entries.sort((a,b)=>b.time-a.time).map(e=>`<div class="history-entry"><time>${esc(new Date(e.time).toLocaleString())}</time>${esc(e.text)}</div>`).join(''):'<p class="modal-description">No activity yet.</p>'}</details>`;
  const preview=async(snapshot,token)=>{
    const own=++previewToken,host=$('#historyPreviewCanvas');host.innerHTML='<p class="modal-description">Loading saved schematic…</p>';
    try{
      const scene=await api('/api/workbench/schematic-view',{method:'POST',body:snapshot.spec});
      if(!current()||!$('#historyDialog').open||token!==comparisonToken||own!==previewToken)return;
      S.historyPreview?.destroy?.();S.historyPreview=new DesignCanvas(host,snapshot.spec,{mode:'schematic',nativeScene:scene,readOnly:true,sheet:''});
      $('#historyPreview').dataset.version=String(snapshot.version);
    }catch(error){if(current()&&$('#historyDialog').open&&token===comparisonToken&&own===previewToken)host.innerHTML=`<p class="modal-description">Preview unavailable: ${esc(error.message)}</p>`;}
  };
  const compare=async(from,to=null)=>{
    if(!current()||!$('#historyDialog').open)return;const token=++comparisonToken;
    const d=await api(`/api/workbench/projects/${pid}/history/${from}/compare${to===null?'':'?to_version='+to}`);
    if(!current()||!$('#historyDialog').open||token!==comparisonToken)return;
    const snapshots=await Promise.all([api(`/api/workbench/projects/${pid}/history/${d.from_version}`),api(`/api/workbench/projects/${pid}/history/${d.to_version}`)]);
    if(!current()||!$('#historyDialog').open||token!==comparisonToken)return;
    const[before,after]=snapshots,changes=d.field_change_count,formats=d.representation_change_count||0,summary=$('#historyCompareSummary');summary.hidden=false;
    summary.innerHTML=`<strong>${changes?`${changes} design change${changes===1?'':'s'}`:'No design changes'}</strong><span>Version ${esc(d.from_version)} → saved design v${esc(d.to_version)}</span>${formats?`<p>${formats} numeric format change${formats===1?'':'s'}; these values are unchanged.</p><ul>${(d.representation_changes||[]).slice(0,8).map(item=>`<li><code>${esc(item.path)}</code> · ${esc(item.before_json)} → ${esc(item.after_json)}</li>`).join('')}</ul>${formats>8?`<p>${formats-8} more format changes; see comparison evidence.</p>`:''}`:''}${changes?`<p>Changed sections: ${esc((d.changed_sections||[]).join(', '))}</p>`:''}`;
    const exact=before.semantic_sha256===d.before_semantic_sha256&&after.semantic_sha256===d.after_semantic_sha256;
    $('#historyDiffRows').hidden=!changes;$('#historyDiffRows').innerHTML=changeTable(d,exact?before.spec:{},exact?after.spec:{});
    $('#historyEvidence').hidden=false;$('#historyComparison').textContent=JSON.stringify(d,null,2);$('#historyPreview').hidden=!exact;
    if(exact){$('#historyPreviewVersions').innerHTML=[before,after].map((snapshot,i)=>`<button class="secondary-button" data-history-preview="${i}">${i?'After':'Before'} v${snapshot.version}</button>`).join('');$$('[data-history-preview]').forEach(button=>button.onclick=()=>preview(snapshots[Number(button.dataset.historyPreview)],token));await preview(after,token);}
  };
  $$('[data-compare-version]').forEach(button=>button.onclick=safely(()=>compare(Number(button.dataset.compareVersion))));
  $$('[data-restore-version]').forEach(button=>button.onclick=safely(async()=>{
    if(!current()||!$('#historyDialog').open)return;if(S.version!==version||S.dirty||S.saving)throw Error('The design changed. Reopen history before restoring.');
    const restored=await api(`/api/workbench/projects/${pid}/history/${button.dataset.restoreVersion}/restore`,{method:'POST',body:{base_version:version}});
    if(!current()||S.version!==version||S.dirty||S.saving)return;
    S.undo.push(structuredClone(S.spec));S.redo=[];S.spec=restored.spec;S.version=restored.version;S.project.spec=restored.spec;S.project.workbench=restored.workbench;S.generation++;invalidateCheckDisplay();aiChanges.commit(pid,{batch:null});S.selection.clear();S.selected=null;S.selectedNet=null;$('#historyDialog').close();renderView();renderInspector();renderChat();updateContext();toast(`Restored as version ${restored.version}`);
  }));
  dialog('#historyDialog');if(Number.isInteger(selection?.from_version))await compare(selection.from_version,selection.version);
}
const commands = [
  ['Stackup Editor', 'layers', '', () => stackupUI.open()],
  ['New project', 'plus', '⌥N', () => dialog('#newProjectDialog')], ['Save project', 'save', '⌘S', saveReady],
  ['Undo', 'undo', '⌘Z', () => undo()], ['Redo', 'redo', '⇧⌘Z', () => undo(true)],
  ['Part library', 'shapes', 'A', () => toggleDrawer('library')], ['Zoom to fit', 'scan', '0', () => $('#fitButton').click()],
  ['Schematic', 'schematic', '1', () => setView('schematic')], ['PCB layout', 'board', '2', () => setView('layout')],
  ['3D View', 'cube', '3', () => setView('3d')], ['Bill of materials', 'table', '4', () => setView('bom')],
  ['Inspect project', 'info', '', () => { S.selection.clear();S.selected = null; S.inspector = true; renderInspector(); }],
  ['Draw schematic wire', 'link', 'W', () => {setView('schematic');if(!S.schematicWiring)$('#wireButton').click();}],
  ['Design checks', 'shield', '', () => toggleDrawer('checks')], ['Build project', 'play', '', buildProject],
  ['Simulate circuit', 'workflow', '', () => runEngineering('simulate')], ['Route PCB', 'board', '', () => runEngineering('route')],
  ['Export project', 'download', '', openExport], ['Settings', 'settings', '', () => openSettings()],
  ['Keyboard shortcuts','keyboard','⌘/',()=>shortcutsUI.open()],
];
function openCommands() { dialog('#commandDialog'); $('#commandInput').value = ''; renderCommands(''); $('#commandInput').focus(); }
function renderCommands(search) {
  $('#commandList').innerHTML = commands.map((c, i) => ({ c, i })).filter(({ c }) => c[0].toLowerCase().includes(search.toLowerCase())).map(({ c, i }) => `<button data-command="${i}">${icon(c[1])}${esc(c[0])}<kbd>${c[2]}</kbd></button>`).join('');
  $$('[data-command]').forEach(b => b.onclick = safely(async () => { $('#commandDialog').close(); await commands[Number(b.dataset.command)][3](); }));
}

// Application chrome and shortcuts.
function toggleChat() { $('#ideShell').classList.toggle('chat-hidden'); }
function initEvents() {
  terminalsUI.bindDrop($('#viewContent'));
  netLabelsUI.bindDrop($('#viewContent'));
  $('#mainMenuButton').onclick = safely(async e => { e.stopPropagation(); const opening = $('#mainMenu').hidden; closeMenus(); $('#mainMenu').hidden = !opening; $('#mainMenuButton').setAttribute('aria-expanded', String(opening)); if (opening) await refreshProjects(); });
  $('#projectsButton').onclick = safely(openProjectBrowser);
  $('#returnToEditor').onclick=closeProjectBrowser;
  $('#browserNewProject').onclick=()=>dialog('#newProjectDialog');
  $('#filterProjectName').oninput=()=>{$('#globalProjectSearch').value='';renderProjectBrowser();};
  $('#globalProjectSearch').oninput=()=>{$('#filterProjectName').value='';renderProjectBrowser();};
  $('#projectTypeFilter').onchange=renderProjectBrowser;
  $$('[data-project-filter]').forEach(b=>b.onclick=()=>{S.projectFilter=b.dataset.projectFilter;$$('[data-project-filter]').forEach(x=>x.classList.toggle('active',x===b));renderProjectBrowser();});
  $('#editWorkspaceProfile').onclick=safely(async()=>{const name=await askText('Edit profile','Workspace display name',S.config?.workspace?.display_name||'Personal workspace');if(name===null)return;S.config=await api('/api/config',{method:'POST',body:{workspace:{display_name:name}}});$('#workspaceDisplayName').textContent=name;});
  $('#mainMenu').onclick = safely(async e => {
    const open = e.target.closest('[data-open-project]'); if (open) return openProject(open.dataset.openProject);
    const action = e.target.closest('[data-action]')?.dataset.action; if (!action) return; closeMenus();
    if (action === 'new') dialog('#newProjectDialog'); if (action === 'save') { await saveReady(); toast('Project saved'); }
    if(action==='projects')await openProjectBrowser();
    if(action==='component-updates')await moduleUpdatesUI.open(); if (action === 'import') $('#importInput').click();if(action==='import-cad')await mechanicalUI.importAssets(); if (action === 'settings') await openSettings(); if (action === 'shortcuts') shortcutsUI.open();
  });
  $('#viewTabs').onclick = e => { const key = e.target.closest('[data-view]')?.dataset.view; if (key) setView(key); };
  $('#addTabButton').onclick = e => { e.stopPropagation(); const r = e.currentTarget.getBoundingClientRect(); $('#addViewMenu').style.right = `${Math.max(5, innerWidth - r.right)}px`; $('#addViewMenu').hidden = !$('#addViewMenu').hidden; };
  $$('[data-add-view]').forEach(b => b.onclick = () => { if (b.textContent.includes('Enclosure')) S.enclosure = true; setView(b.dataset.addView); });
  document.addEventListener('click', e => { if (!e.target.closest('.popover,#mainMenuButton,#projectsButton,#addTabButton,[data-project-menu],[data-pinref]')) closeMenus(); });
  $$('[data-close]').forEach(b => b.onclick = () => b.closest('dialog').close());
  $('#historyDialog').addEventListener('close',()=>{S.historyLoadToken=(S.historyLoadToken||0)+1;S.historyPreview?.destroy?.();S.historyPreview=null;});
  $$('dialog').forEach(d => d.addEventListener('click', e => { if (e.target === d) { const r = d.getBoundingClientRect(); if (e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom) d.close(); } }));
  $('#projectTitle').onclick = safely(renameProject); $('#newProjectForm').onsubmit = safely(newProject);
  $('#netForm').onsubmit = saveNet;
  $('#partForm').onsubmit=event=>{event.preventDefault();return safely(addPickedPart)(event);};
  $('#confirmNetMerge').onclick=safely(()=>{finishSchematicWire(S.pendingWire,true);$('#mergeNetDialog').close();});
  $('#mergeNetDialog').addEventListener('close',()=>{S.pendingWire=null;});
  let footprintTimer;
  $('#partFootprint').oninput=e=>{clearTimeout(footprintTimer);const q=e.target.value;if(q.length<2)return;footprintTimer=setTimeout(()=>api(`/api/workbench/library?kind=footprints&q=${encodeURIComponent(q)}`).then(d=>$('#footprintChoices').innerHTML=d.results.map(id=>`<option value="${esc(id)}"></option>`).join('')).catch(fail),300);};
  $('#collapseChat').onclick = () => { if (innerWidth <= 760) $('#ideShell').classList.remove('mobile-chat-open'); else toggleChat(); };
  $('#restoreChat').onclick = toggleChat; $('#expandEditor').onclick = toggleChat;
  $('#mobileChat').onclick = () => $('#ideShell').classList.toggle('mobile-chat-open');
  $('#projectDock').onclick = () => { S.selection.clear();S.inspector = true; S.selected = null; S.selectedNet = null; renderInspector(); };
  $$('[data-panel]').forEach(b => b.onclick = () => toggleDrawer(b.dataset.panel));
  $('#fitButton').onclick = () => { if (S.canvas?.fit) S.canvas.fit(); else if (S.canvas instanceof window.MeshView) { S.canvas.yaw = -.7; S.canvas.pitch = .75; S.canvas.zoom = 1; S.canvas.draw(); } };
  const zoom = factor => { if (S.canvas?.setZoom) S.canvas.setZoom(S.canvas.zoom * factor); else if (S.canvas instanceof window.MeshView) { S.canvas.zoom = Math.max(.3, Math.min(6, S.canvas.zoom * factor)); S.canvas.draw(); $('#zoomReset').textContent = `${Math.round(S.canvas.zoom * 100)}%`; } };
  $('#zoomIn').onclick = () => zoom(1.15); $('#zoomOut').onclick = () => zoom(1 / 1.15); $('#zoomReset').onclick = () => $('#fitButton').click();
  $('#panButton').onclick = () => { if (!S.canvas) return; S.canvas.panTool = !S.canvas.panTool; S.canvas.svg?.classList.toggle('pan-mode', S.canvas.panTool); $('#panButton').setAttribute('aria-pressed', String(S.canvas.panTool)); };
  $('#routeButton').onclick=()=>routingUI.guard(()=>routingUI.toggle());
  $('#viaButton').onclick=safely(openViaDialog);
  $('#viaForm').onsubmit=safely(event=>{event.preventDefault();const net=$('#viaNet').value,diameter=Number($('#viaDiameter').value),drill=Number($('#viaDrill').value);if(!(diameter>drill&&drill>0))throw new Error('The via diameter must exceed its positive drill diameter.');S.viaPlacing={net,diameter,drill};S.routing=false;S.routeStart=null;$('#routeButton').setAttribute('aria-pressed','false');$('#viaButton').setAttribute('aria-pressed','true');if(S.canvas?.geo){S.canvas.placingVia=true;S.canvas.routing=false;S.canvas.routeStart=null;}$('#viaDialog').close();toast('Click a position on the PCB to place the via. Escape cancels.');});
  $('#wireButton').onclick=()=>{S.schematicWiring=!S.schematicWiring;cancelSchematicWire();$('#wireButton').setAttribute('aria-pressed',String(S.schematicWiring));if(S.canvas?.svg){S.canvas.wiringMode=S.schematicWiring;S.canvas.svg.classList.toggle('wire-mode',S.schematicWiring);S.canvas.drawConnections();}};
  $('#cameraOptions').onclick=()=>toggleDrawer('view');
  $('#autoLayoutButton').onclick = autoLayout;
  $$('[data-prompt]').forEach(b => b.onclick = () => { $('#chatInput').value = b.dataset.prompt; $('#chatInput').focus(); });
  $('#suggestionsToggle').onclick = () => { const hidden = !$('#suggestionList').hidden; $('#suggestionList').hidden = hidden; $('#suggestionsToggle').setAttribute('aria-expanded', String(!hidden)); };
  $$('[data-mode]').forEach(b => b.onclick = () => { S.mode = b.dataset.mode;recordChatDraft(true); $$('[data-mode]').forEach(x => { x.classList.toggle('active', x === b); x.setAttribute('aria-pressed', String(x === b)); }); });
  $('#chatForm').onsubmit = event=>{event.preventDefault();return safely(sendMessage)(event);};
  $('#chatInput').addEventListener('input',()=>recordChatDraft(true));
  $('#stopRunButton').onclick=safely(()=>api(`/api/projects/${S.pid}/cancel`,{method:'POST'}));
  $('#chatInput').onkeydown = e => { if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); $('#chatForm').requestSubmit(); } };
  $('#clearContext').onclick = () => { S.objectOnlySelection=null; S.selectedSheet=null;S.selectedWireNode=null;if(S.canvas?.options)S.canvas.options.selectedWireNode=null;S.canvas?.selectSheet?.(null);if(S.canvas?.options)S.canvas.options.selectedWireNode=null; S.selectedWireIndex=null;S.canvas?.selectWire?.(null);S.selection.clear();S.selected = null; S.selectedNet = null; S.canvas?.select?.(null); renderInspector(); updateContext(); };
  $('#attachButton').onclick = () => $('#attachmentInput').click(); $('#attachmentInput').onchange = safely(e => attachFile(e.target.files[0]));
  $('#importInput').onchange = safely(e => importFiles(e.target.files));
  $('#settingsButton').onclick = safely(() => openSettings()); $('#modelButton').onclick = safely(() => openSettings());
  $('#settingsForm').onsubmit = safely(saveSettings); $('[name="ai.provider"]').onchange = syncProvider;
  $$('[data-settings]').forEach(b => b.onclick = () => setSettingsPane(b.dataset.settings));
  $('#testConnection').onclick = safely(async () => {
    const b = $('#testConnection'); b.disabled = true; $('#connectionResult').textContent = 'Testing…';
    try { await saveSettings(); const r = await api('/api/ai/test', { method: 'POST' }); $('#connectionResult').textContent = r.ok ? `Connected · ${r.model || ''}` : r.error; if (!r.ok) toast(r.error, true); }
    finally { b.disabled = false; }
  });
  $('#exportButton').onclick = safely(openExport); $('#shareButton').onclick = safely(openShare);
  $('#priceButton').onclick=()=>toggleDrawer('manufacturing');
  $('#commentsButton').onclick=safely(async()=>{await save();toggleDrawer('comments');});
  $('#viewContent').addEventListener('contextmenu',showCanvasContext);
  let presenceAt=0;
  $('#viewContent').addEventListener('pointermove',event=>{
    S.routePointerClient=[event.clientX,event.clientY];
    if(performance.now()-presenceAt<90)return;presenceAt=performance.now();
    if(S.active==='schematic'&&S.canvas?.scene){const point=S.canvas.svg.createSVGPoint();point.x=event.clientX;point.y=event.clientY;const at=point.matrixTransform(S.canvas.scene.getScreenCTM().inverse());publishPresence([+at.x.toFixed(2),+at.y.toFixed(2)]);}
    else if(S.active==='layout'&&S.canvas?.geo)publishPresence(S.canvas._world(event).map(v=>+v.toFixed(3)));
  });
  $('#viewContent').addEventListener('pointerleave',()=>{S.routePointerClient=null;S.routePointerWorld=null;if(S.canvas?.geo){S.canvas.pointerWorld=null;S.canvas.routeTerminals?.replaceChildren();}publishPresence(null);});
  $('#copyLink').onclick = safely(async () => { await navigator.clipboard.writeText($('#shareUrl').value); toast('Project link copied'); $('#copyLink').textContent = 'Copied'; setTimeout(() => $('#copyLink').textContent = 'Copy link', 2000); });
  $('#commandButton').onclick = openCommands; $('#commandInput').oninput = e => renderCommands(e.target.value);
  $('#commandInput').onkeydown = e => { if (e.key === 'Enter') $('#commandList button')?.click(); if (e.key === 'ArrowDown') { e.preventDefault(); $('#commandList button')?.focus(); } };
  $('#historyButton').onclick = safely(openHistory);
  let resizing = false;
  $('#splitter').onpointerdown = e => { resizing = true; e.currentTarget.setPointerCapture(e.pointerId); document.body.style.cursor = 'col-resize'; };
  $('#splitter').onpointermove = e => { if (!resizing) return; const w = Math.max(280, Math.min(innerWidth * .75, e.clientX)); document.documentElement.style.setProperty('--chat-width', `${w}px`); $('#splitter').setAttribute('aria-valuenow', Math.round(w)); };
  $('#splitter').onpointerup = () => { resizing = false; document.body.style.cursor = ''; localStorage.setItem('wb-workbench-chat-width', document.documentElement.style.getPropertyValue('--chat-width')); };
  $('#splitter').ondblclick = () => { document.documentElement.style.setProperty('--chat-width', '48%'); localStorage.removeItem('wb-workbench-chat-width'); };
  $('#splitter').onkeydown = e => { if (!['ArrowLeft','ArrowRight'].includes(e.key)) return; const w = $('#chatPanel').getBoundingClientRect().width + (e.key === 'ArrowRight' ? 20 : -20); document.documentElement.style.setProperty('--chat-width', `${Math.max(280, Math.min(innerWidth*.75,w))}px`); };
  document.addEventListener('keydown', e => {
    if(e.isComposing)return;
    const typing = e.target.isContentEditable||!!e.target.closest?.('input,textarea,select,[contenteditable=true]'), cmd = e.metaKey || e.ctrlKey;
    if(cmd&&!e.altKey&&e.code==='Slash'){e.preventDefault();if($('#shortcutsDialog').open)$('#shortcutsDialog').close();else shortcutsUI.open();return;}
    if($('dialog[open]'))return;
    if(displayUI.key(e))return;
    if((S.starting||S.openingProject)&&cmd&&(e.key.toLowerCase()==='s'||!typing&&['a','c','v','d','z'].includes(e.key.toLowerCase()))){e.preventDefault();return;}
    if (cmd && e.key.toLowerCase() === 's') { e.preventDefault(); if(S.active==='files'&&S.fileEditing)saveCurrentFile().catch(fail);else save().then(() => toast('Project saved')).catch(fail); return; }
    if (cmd && e.key.toLowerCase() === 'k') { e.preventDefault(); openCommands(); return; }
    if(!typing&&!cmd&&e.altKey){
      if(e.code==='KeyN'&&!e.shiftKey&&!S.starting&&!S.openingProject){e.preventDefault();dialog('#newProjectDialog');return;}
      if(e.code==='KeyC'){e.preventDefault();$('#ideShell').classList.remove('chat-hidden');if(innerWidth<=760)$('#ideShell').classList.add('mobile-chat-open');$('#chatInput').focus();return;}
      if(e.code==='KeyL'&&S.active==='layout'){e.preventDefault();toggleDrawer('layers');return;}
      if(e.code==='Digit3'&&['layout','3d'].includes(S.active)){e.preventDefault();setView(S.active==='layout'?'3d':'layout');return;}
      if(!selectionTransformsUI.matchesArrangeKey(e))return;
    }
    if(!typing&&!cmd&&!e.altKey&&e.key==='?'){e.preventDefault();shortcutsUI.open();return;}
    if(S.screen==='projects'&&!typing&&!$('dialog[open]')&&!cmd){if(e.key==='Escape'&&S.pid)closeProjectBrowser();return;}
    if(S.active==='layout'&&e.target.closest?.('#pcbLayerTree')&&layersUI.key(e))return;
    if (typing || $('dialog[open]')) {layersUI.cancelPrefix();return;}
    if(componentHotkeys.key(e))return;
    if(layersUI.key(e))return;
    if(S.active==='symbol'&&parametricUI.key(e))return;
    if(!routingUI.active&&!S.wireDraft&&objectsUI.blockKey(e))return;
    if(schematicWireKey(e))return;
    if(S.active==='layout'&&routingUI.key(e))return;
    if(selectionTransformsUI.key(e)||viewportSlots.key(e))return;
    if(S.active==='library'&&!cmd){if(e.key.toLowerCase()==='f')libraryUI.host?.querySelector('#fitLibrary')?.click();return;}
    if(e.altKey)return;
    if(cmd&&e.key.toLowerCase()==='f'){e.preventDefault();if(!['schematic','layout'].includes(S.active))setView('schematic');renderDrawer('objects');$('#objectSearch').focus();return;}
    if(cmd&&e.key.toLowerCase()==='a'&&['schematic','layout'].includes(S.active)){e.preventDefault();if(e.shiftKey){S.selectedCopper=null;if(S.canvas?.geo)S.canvas.copperSelection=null;$('#clearContext').click();return;}const keys=S.canvas?.svg?[...S.canvas.svg.querySelectorAll('[data-ref]')].map(el=>el.dataset.symbolKey||el.dataset.ref):S.spec.components.map(c=>c.ref);selectMultiple(keys);return;}
    if(cmd&&e.key.toLowerCase()==='c'&&S.selection.size){e.preventDefault();copySelected().catch(fail);return;}
    if(cmd&&e.key.toLowerCase()==='v'&&['schematic','layout'].includes(S.active)){e.preventDefault();pasteSelected().catch(fail);return;}
    if(cmd&&e.key.toLowerCase()==='d'&&S.selection.size){e.preventDefault();duplicateSelected().catch(fail);return;}
    if (cmd && e.key.toLowerCase() === 'z') { e.preventDefault(); undo(e.shiftKey); return; }
    if (cmd && e.key.toLowerCase() === 'n') { e.preventDefault(); dialog('#newProjectDialog'); return; }
    if(cmd)return;
    if(['=','+','-'].includes(e.key)){e.preventDefault();$(e.key==='-'?'#zoomOut':'#zoomIn').click();return;}
    if (!['schematic','layout'].includes(S.active)&&['1','2','3','4'].includes(e.key)) setView({1:'schematic',2:'layout',3:'3d',4:'bom'}[e.key]);
    if(!cmd&&!e.altKey&&['BracketLeft','BracketRight'].includes(e.code)){e.preventDefault();if(!e.repeat)selectionTransformsUI.run('rotate',{angle:e.code==='BracketRight'?90:-90,individual:e.shiftKey});return;}
    if((e.code==='Digit0'||e.key==='0')&&!cmd&&!e.altKey){e.preventDefault();if(!e.shiftKey&&S.selected&&S.canvas?.fitSelection)S.canvas.fitSelection();else $('#fitButton').click();}
    if(e.key.toLowerCase()==='f'&&!cmd&&!e.altKey){e.preventDefault();if(!e.repeat)selectionTransformsUI.run(S.active==='layout'?'flip_layer':e.shiftKey?'flip_vertical':'flip_horizontal');return;}
    if (e.key.toLowerCase() === 'a') toggleDrawer('library');
    if(e.key.toLowerCase()==='r'&&!cmd&&!e.altKey&&!e.repeat)selectionTransformsUI.run('rotate',{angle:90,individual:e.shiftKey});
    if (e.key.toLowerCase() === 'w'){if(S.active==='layout')$('#routeButton').click();else if(S.active==='schematic')$('#wireButton').click();}
    if (e.key.toLowerCase() === 'v'&&!cmd&&S.active==='layout')$('#viaButton').click();
    if(['Delete','Backspace'].includes(e.key)&&S.active==='schematic'&&S.selectedWireNode){e.preventDefault();removeSelectedWireNode();return;}
    if(['Delete','Backspace'].includes(e.key)&&S.active==='schematic'&&S.selectedWireIndex!==null&&S.selectedWireIndex!==undefined){e.preventDefault();openWireDisconnect();return;}
    if(['Delete','Backspace'].includes(e.key)&&S.selectedCopper&&S.active==='layout'){e.preventDefault();try{changeCopper(null);}catch(error){fail(error);}return;}
    if (['Delete', 'Backspace'].includes(e.key) && S.selected) { e.preventDefault(); deletePart(); }
    if (e.key === 'Escape') {S.objectOnlySelection=null;selectionTransformsUI.cancel();if(S.viaPlacing){S.viaPlacing=null;if(S.canvas)S.canvas.placingVia=false;$('#viaButton').setAttribute('aria-pressed','false');return;}if(S.routeStart){S.routeStart=null;if(S.canvas){S.canvas.routeStart=null;S.canvas.draw?.();}return;}if(S.wireStart){cancelSchematicWire();return;}if(S.schematicWiring){S.schematicWiring=false;$('#wireButton').setAttribute('aria-pressed','false');if(S.canvas?.svg){S.canvas.wiringMode=false;S.canvas.svg.classList.remove('wire-mode');}}closeMenus(); closeDrawer(); S.selectedSheet=null;S.selectedWireNode=null;if(S.canvas?.options)S.canvas.options.selectedWireNode=null;S.canvas?.selectSheet?.(null); S.selectedCopper=null;if(S.canvas?.geo)S.canvas.copperSelection=null; S.selectedWireIndex=null;S.canvas?.selectWire?.(null);S.selection.clear();S.selected = null; S.selectedNet = null; S.canvas?.select?.(null); S.inspector = false; renderInspector(); updateContext(); }
    if (e.key === '/' || e.key.toLowerCase() === 'c') { e.preventDefault(); $('#chatInput').focus(); }
    if (e.key === ' ') { e.preventDefault(); if (S.canvas) { S.canvas.panTool = true; S.canvas.svg?.classList.add('pan-mode'); } }
  });
  document.addEventListener('keyup', e => { routingUI.keyUp(e);if (e.key === ' ' && S.canvas&&!navigationUI.ownsSpaceRelease(e)) { S.canvas.panTool = false; S.canvas.svg?.classList.remove('pan-mode'); } });
  window.addEventListener('beforeunload', e => { if (S.dirty || S.saving || S.fileDrafts?.size) { e.preventDefault(); e.returnValue = ''; } });
  window.addEventListener('hashchange', () => { const pid = location.hash.slice(1);if(pid==='projects'){if(S.screen!=='projects')openProjectBrowser().catch(fail);return;}if(pid&&(pid!==S.pid||S.openingProject&&pid!==S.openingProject.pid))openProject(pid).catch(fail);else if(pid===S.pid&&S.screen==='projects')closeProjectBrowser(); });
}

async function init() {
  hydrateIcons(); initEvents();collaborationUI.init();
  renderView();renderChat();applyAccessUI();
  if(!await collaborationUI.bootstrap())return;
  const projectsRoute=location.hash==='#projects';
  const width = localStorage.getItem('wb-workbench-chat-width'); if (width) document.documentElement.style.setProperty('--chat-width', width);
  const results = await Promise.allSettled([api('/api/workbench/example'), api('/api/projects'), api('/api/config')]);
  if (results[0].status !== 'fulfilled') throw results[0].reason;
  S.spec = results[0].value; S.project = { title: S.spec.title, status: 'idle' }; title(S.spec.title);
  if (results[1].status === 'fulfilled') S.projects = results[1].value;
  if (results[2].status === 'fulfilled') { S.config = results[2].value; updateModelLabel(); }
  const pid = (!projectsRoute&&location.hash.slice(1)) || localStorage.getItem('wb-workbench-project');
  if (pid && S.projects.some(p => p.id === pid)){
    try{await openProject(pid);}catch(error){if(![403,404].includes(error.status))throw error;localStorage.removeItem('wb-workbench-project');history.replaceState(null,'',location.pathname+location.search);renderView();renderChat();renderProjectMenu();}
  }else { S.starting=false;renderView(); renderChat(); renderProjectMenu(); }
  const active = localStorage.getItem('wb-workbench-view'); if (active && views[active]) setView(active);
  loadStatus();
  applyAccessUI();
  if(projectsRoute)await openProjectBrowser();
}
init().catch(error => { fail(error); $('#welcome h1').textContent = 'Could not open the workspace'; });
