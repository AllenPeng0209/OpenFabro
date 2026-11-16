import {componentSheet,sheetDefinitions} from './workbench-sheets.mjs';

export function interfaceRows(spec,{refs=null,publish=false,sheet=''}={}){
 const chosen=refs?new Set(refs):null,membership=new Map(spec.nets.flatMap(net=>net.pins.map(pin=>[pin,net.name]))),defs=sheetDefinitions(spec);
 const terms=spec.components.filter(c=>c.terminal&&c.terminal.expose!==false&&(chosen?chosen.has(c.ref):componentSheet(c)===''));
 const rows=terms.filter(c=>membership.has(c.ref+'.1')).map(c=>({net:membership.get(c.ref+'.1'),label:c.value,required:true,checked:true,terminal:true})),covered=new Set(rows.map(row=>row.net)),labels=new Map(),ancestors=[];
 for(let current=sheet;current;current=defs[current]?.parent||''){if(ancestors.includes(current))break;ancestors.push(current);}
 ancestors.push('');
 for(const page of ancestors){
  for(const[label,port]of Object.entries(defs[page]?.ports||{}))if(!labels.has(port.net))labels.set(port.net,label);
  for(const c of spec.components.filter(c=>c.terminal&&c.terminal.expose!==false&&componentSheet(c)===page)){const net=membership.get(c.ref+'.1');if(net&&!labels.has(net))labels.set(net,c.value);}
 }
 const hasRootTerminal=spec.components.some(c=>c.terminal&&componentSheet(c)==='');
 for(const net of spec.nets){
  if(covered.has(net.name)||chosen&&!net.pins.some(pin=>chosen.has(pin.split('.')[0])))continue;
  const required=!publish&&(net.pins.some(pin=>!chosen?.has(pin.split('.')[0]))||labels.has(net.name));
  rows.push({net:net.name,label:publish?net.name:labels.get(net.name)||net.name,required,checked:required||publish&&!hasRootTerminal,terminal:false});
 }
 return rows;
}
