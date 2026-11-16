import {esc} from './workbench-icons.mjs';

// Show implemented gestures. Further Flux bindings stay in the parity register until supported.
const groups=[
 {name:'General',rows:[
  ['Keyboard shortcuts',[['mod','/'],['?']]],['Command search',[['mod','K']]],
  ['Create new project',[['alt','N']]],['Ask AI',[['alt','C'],['/']]],
  ['Save project or active file',[['mod','S']]],['Find component',[['mod','F']]],
  ['Cancel current action',[['Esc']]],
 ]},
 {name:'Edit',rows:[
  ['Undo',[['mod','Z']]],['Redo',[['mod','shift','Z']]],
  ['Select all components',[['mod','A']]],['Deselect all',[['mod','shift','A'],['Esc']]],
  ['Copy components',[['mod','C']]],['Paste components',[['mod','V']]],['Duplicate components',[['mod','D']]],
  ['Delete selected object',[['Backspace'],['Delete']]],
  ['Rotate right',[ [']'],['R']]],['Rotate left',[['[']]],
  ['Rotate right individually',[['shift',']']]],['Rotate left individually',[['shift','[']]],
  ['Nudge selected components',[['←'],['↑'],['→'],['↓']]],
  ['Nudge minor step',[['shift','←'],['shift','↑'],['shift','→'],['shift','↓']]],
 ]},
 {name:'View',rows:[
  ['Zoom to fit selection or design',[['0']]],['Zoom to fit design',[['shift','0']]],
  ['Zoom in',[['='],['+']]],['Zoom out',[['-']]],['Pan canvas',[['Space','Drag']]],
  ['Navigate viewport',[['←'],['↑'],['→'],['↓']],'With no selection'],
  ['Part library',[['A']]],['Schematic view',[['1']],'Outside Schematic / PCB'],['PCB layout',[['2']],'Outside Schematic / PCB'],['3D view',[['3']],'Outside Schematic / PCB'],['Bill of materials',[['4']],'Outside Schematic / PCB'],
 ]},
 {name:'Schematic',rows:[
  ['Show all pin labels',[['shift','P']]],['Show comment markers',[['shift','C']]],['Show collaborative cursors',[['mod','shift','\\']]],
  ['Flip horizontally',[['F']]],['Flip vertically',[['shift','F']]],
  ['Toggle wire tool',[['W']]],['Start or finish a free wire',[['Double-click canvas']]],
  ['Flip wire elbow',[['F']],'While drawing a wire'],['Undo last wire bend',[['Backspace']],'While drawing a wire'],
  ['Add to selection',[['shift','Click']]],
  ['Assign component hotkey',[['shift','1–5']]],['Insert component hotkey',[['1–5']]],
  ['Save viewport slot',[['shift','6–9']]],['Recall viewport slot',[['6–9']]],
 ]},
 {name:'Arrange',rows:[
  ['Align left',[['alt','A']]],['Align right',[['alt','D']]],['Align horizontal center',[['alt','H']]],
  ['Align top',[['alt','W']]],['Align bottom',[['alt','S']]],['Align vertical center',[['alt','V']]],
  ['Space evenly',[['S']],'Schematic'],['Space horizontally',[['alt','shift','H']],'PCB'],['Space vertically',[['alt','shift','V']],'PCB'],
 ]},
 {name:'PCB',rows:[
  ['Focus copper layer',[['1–6']],'Available board copper layers'],
  ['Focus layer',[['L → layer key']],'D/L/A/Z/O/P/M or copper number'],
  ['Show or hide layer',[['H → layer key']],'Shift with O/P/M selects the bottom side'],
  ['Toggle all copper fills',[['H → F']]],
  ['Flip board side',[['F']]],['Open or close layers',[['alt','L']]],
  ['Switch Layout / 3D',[['alt','3']]],['Toggle routing tool',[['W']]],['Place via',[['V']]],
  ['Flip trace elbow',[['F']],'While routing'],['Cycle trace width',[['W']],'While routing'],
  ['Previous trace width',[['shift','W']],'While routing'],['Continue on next layer with via',[['V']],'While routing'],
  ['Draw at any angle',[['shift']],'While routing'],['Undo last trace bend',[['Backspace']],'While routing'],
 ]},
];

export class ShortcutsUI{
 constructor({dialog}){
  this.dialog=dialog;this.host=document.querySelector('#shortcutsDialog');
  this.search=this.host.querySelector('#shortcutSearch');this.platform=this.host.querySelector('#shortcutPlatform');this.scope=this.host.querySelector('#shortcutScope');
  this.platform.value=/Mac|iPhone|iPad/i.test(navigator.platform)?'mac':'windows';
  this.host.querySelector('[data-close-shortcuts]').onclick=()=>this.host.close();
  this.host.addEventListener('keydown',event=>{if(event.key==='Escape'){event.preventDefault();event.stopPropagation();this.host.close();}});
  this.search.oninput=this.platform.onchange=this.scope.onchange=()=>this.render();
 }
 open(){this.search.value='';this.scope.value='all';this.render();this.dialog('#shortcutsDialog');this.search.focus();}
 render(){
  const query=this.search.value.toLowerCase().trim().split(/\s+/).filter(Boolean),mac=this.platform.value==='mac',labels={mod:mac?'⌘':'Ctrl',alt:mac?'⌥':'Alt',shift:mac?'⇧':'Shift'};
  const keyText=key=>labels[key]||key;
  const chord=keys=>keys.map(key=>`<kbd>${esc(keyText(key))}</kbd>`).join('<span class="shortcut-plus">+</span>');
  const html=groups.filter(group=>this.scope.value==='all'||group.name===this.scope.value||['General','Edit','View','Arrange'].includes(group.name)).map(group=>{
   const rows=group.rows.filter(row=>query.every(word=>[group.name,row[0],row[2]||'',...row[1].flat().map(keyText)].join(' ').toLowerCase().includes(word)));
   return rows.length?`<section class="shortcut-group"><h3>${esc(group.name)}</h3>${rows.map(([name,bindings,context])=>`<div class="shortcut-row" data-shortcut-row><span>${esc(name)}${context?`<small>${esc(context)}</small>`:''}</span><span class="shortcut-keys">${bindings.map(chord).join('<span class="shortcut-or">or</span>')}</span></div>`).join('')}</section>`:'';
  }).join('');
  this.host.querySelector('#shortcutList').innerHTML=html||'<p class="shortcut-empty" role="status">No shortcuts found.</p>';
 }
}
