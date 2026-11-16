const valid=camera=>camera?.kind==='schematic'&&Array.isArray(camera.center)&&camera.center.length===2&&camera.center.every(v=>Number.isFinite(v)&&Math.abs(v)<=1e6)&&Number.isFinite(camera.scale)&&camera.scale>=1e-6&&camera.scale<=1e6;

export class ViewportSlots{
 constructor({state,toast,storage,interacting}){Object.assign(this,{state,toast,interacting});this.memory=new Map();if(storage)this.storage=storage;else try{this.storage=localStorage;}catch{}}
 keyFor(){const s=this.state();return'wb-viewport-slots:'+encodeURIComponent(s.pid)+':'+encodeURIComponent(s.schematicSheet||'');}
 available(){const s=this.state();return s.pid&&s.active==='schematic'&&!s.starting&&!s.openingProject&&s.canvas?.options?.nativeScene;}
 read(){const key=this.keyFor();if(this.memory.has(key))return this.memory.get(key);try{const value=JSON.parse(this.storage?.getItem(key)||'null');if(value?.schema===1&&value.slots&&typeof value.slots==='object')return value.slots;}catch{}return{};}
 save(slot){
  if(![6,7,8,9].includes(Number(slot)))return false;
  if(this.interacting?.())return false;
  if(!this.available()){this.toast('Wait for the schematic to finish loading before saving a view.');return false;}
  const camera=this.state().canvas.getCamera();if(!valid(camera)){this.toast('This view cannot be saved yet.');return false;}
  const slots={...this.read(),[slot]:structuredClone(camera)},key=this.keyFor();this.memory.set(key,slots);while(this.memory.size>64)this.memory.delete(this.memory.keys().next().value);
  let stored=false;try{if(this.storage){this.storage.setItem(key,JSON.stringify({schema:1,slots}));stored=true;}}catch{}
  this.toast(stored?`View ${slot} saved.`:`View ${slot} saved for this session; browser storage is unavailable.`);return true;
 }
 recall(slot){
  if(![6,7,8,9].includes(Number(slot)))return false;
  if(this.interacting?.())return false;
  if(!this.available()){this.toast('Wait for the schematic to finish loading before recalling a view.');return false;}
  const camera=this.read()[slot];if(!valid(camera)){this.toast(`No saved view in slot ${slot} for this sheet.`);return false;}
  const s=this.state();s.canvas.setCamera(structuredClone(camera));s.planarCameras||=new Map();if(s.canvas.workbenchKey)s.planarCameras.set(s.canvas.workbenchKey,structuredClone(camera));this.toast(`View ${slot} restored.`);return true;
 }
 key(event){
  if(this.state().active!=='schematic'||event.ctrlKey||event.metaKey||event.altKey||event.target?.closest?.('input,textarea,select,[contenteditable=true],[role=treeitem],[role=menu]'))return false;
  const match=/^(?:Digit|Numpad)([6-9])$/.exec(event.code);if(!match)return false;event.preventDefault();if(!event.repeat&&!this.interacting?.())(event.shiftKey?this.save(Number(match[1])):this.recall(Number(match[1])));return true;
 }
}
