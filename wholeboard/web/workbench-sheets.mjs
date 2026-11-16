import {pruneWireJoins,pruneWireNodes} from './workbench-model.mjs';
export const sheetId=id=>/^[A-Za-z][A-Za-z0-9_-]{0,63}$/.test(id);
export const componentSheet=component=>String((Object.hasOwn(component,'sheet')?component.sheet:component.block)||'').replace(/[^A-Za-z0-9_-]+/g,'_').replace(/^_+|_+$/g,'');

export function sheetDefinitions(spec){
  const result=structuredClone(spec.editor?.sheets||{});
  for(const component of spec.components){const id=componentSheet(component);if(id&&!result[id])result[id]={title:id,parent:''};}
  return result;
}
function checked(spec){
 const defs=sheetDefinitions(spec);
 for(const [id,definition]of Object.entries(defs)){
  if(definition.parent&&!defs[definition.parent])throw new Error('The parent sheet does not exist.');
  let parent=definition.parent,seen=new Set([id]);while(parent){if(seen.has(parent))throw new Error('A sheet cannot be placed inside its own descendant (cycle).');seen.add(parent);parent=defs[parent]?.parent;}
  if(definition.size&&(!Array.isArray(definition.size)||definition.size.length!==2||definition.size.some(v=>!Number.isFinite(v)||v<60||v>10000)))throw new Error('Use sheet dimensions between 60 and 10000 schematic units.');
  if(definition.position&&(!Array.isArray(definition.position)||definition.position.length!==2||definition.position.some(v=>!Number.isFinite(v))))throw new Error('Sheet positions must use finite coordinates.');
 }
 return spec;
}
function cleanGuides(spec){
 const refs=new Map(spec.components.map(component=>[component.ref,componentSheet(component)])),defs=sheetDefinitions(spec);
 const location=anchor=>anchor.startsWith('node:')?(spec.editor?.wire_nodes?.[anchor.slice(5)]?.sheet??null):anchor.startsWith('sheet:')?(defs[anchor.slice(6).split('.',1)[0]]?.parent??null):refs.get(anchor.split('.',1)[0].split('#')[0]);
 if(spec.editor?.connection_guides)spec.editor.connection_guides=pruneWireJoins(spec.editor.connection_guides.filter(guide=>{const a=location(guide.from),b=location(guide.to);return a!==null&&b!==null&&(a===undefined||b===undefined||a===b);}));
 return pruneWireNodes(spec);
}

export function assignSheet(spec,refs,id){
 const out=structuredClone(spec),defs=sheetDefinitions(out);if(id&&!defs[id])throw new Error('Choose an existing sheet.');
 const selected=new Set(refs);if([...selected].some(ref=>!out.components.some(component=>component.ref===ref)))throw new Error('The selected component no longer exists.');
 for(const component of out.components)if(selected.has(component.ref))component.sheet=id;
 return cleanGuides(out);
}
export function createSheet(spec,id,{title=id,parent='',refs=[]}={}){
 if(!sheetId(id))throw new Error('Choose a sheet ID starting with a letter.');
 if(sheetDefinitions(spec)[id])throw new Error('A sheet already uses that ID.');
 const out=structuredClone(spec);out.editor||={};out.editor.sheets||={};
 const siblings=Object.values(sheetDefinitions(spec)).filter(value=>(value.parent||'')===parent),position=[850,140];
 while(siblings.some(value=>value.position&&Math.abs(value.position[0]-position[0])<(value.size?.[0]||300)+80&&Math.abs(value.position[1]-position[1])<(value.size?.[1]||180)+80))position[0]+=450;
 out.editor.sheets[id]={title,parent,position,size:[300,180]};
 return assignSheet(checked(out),refs,id);
}
export function updateSheet(spec,id,patch){
 const defs=sheetDefinitions(spec);if(!defs[id])throw new Error('The sheet no longer exists.');
 const out=structuredClone(spec);out.editor||={};out.editor.sheets||={};out.editor.sheets[id]={...defs[id],...structuredClone(patch)};
 if(!out.editor.sheets[id].title?.trim())throw new Error('Give the sheet a title.');
 return cleanGuides(checked(out));
}
export function removeSheet(spec,id){
 const defs=sheetDefinitions(spec);if(!defs[id])throw new Error('The sheet no longer exists.');
 const remove=new Set([id]);let changed=true;while(changed){changed=false;for(const [key,value]of Object.entries(defs))if(remove.has(value.parent)&&!remove.has(key)){remove.add(key);changed=true;}}
 const out=structuredClone(spec),parent=defs[id].parent||'';for(const component of out.components)if(remove.has(componentSheet(component)))component.sheet=parent;
 for(const node of Object.values(out.editor?.wire_nodes||{}))if(remove.has(node.sheet))node.sheet=parent;
 for(const key of remove)if(out.editor?.sheets)delete out.editor.sheets[key];
 return cleanGuides(out);
}
