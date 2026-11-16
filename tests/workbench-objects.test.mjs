import test from 'node:test';
import assert from 'node:assert/strict';
let objects;try{objects=await import('../wholeboard/web/workbench-objects-model.mjs');}catch{}
test('the native object tree model is implemented',()=>assert.ok(objects,'The object tree still contains component rows only'));

const spec=()=>({name:'Object fixture',board:{layers:2},components:[{ref:'J1',value:'Header'},{ref:'J2',value:'Header'}],nets:[{name:'SIG',pins:['J1.1','J2.1']},{name:'GND',pins:[]}],editor:{}});
const geometry=()=>({schema:4,footprints:[{id:'fp1',ref:'J1'},{id:'fp2',ref:'J2'}],
 pads:[{id:'p1',ref:'J1',name:'1',net:'SIG',layers:['F.Cu']},{id:'p2',ref:'J1',name:'1',net:'SIG',layers:['F.Cu']},{id:'p3',ref:'J2',name:'1',net:'SIG',layers:['B.Cu']}],
 tracks:[{id:'t1',net:'SIG',layer:'F.Cu',a:[1,1],b:[2,1],w:.25}],arcs:[{id:'a1',net:'SIG',layer:'F.Cu'}],vias:[{id:'v1',net:'SIG',layers:['F.Cu','B.Cu']}],
 outline:[{id:'o1',kind:'rect'}],drawings:[{id:'d1',ref:'J1',kind:'line',layer:'F.SilkS'},{id:'d2',ref:'',kind:'text',text:'Board label',layer:'B.SilkS'}],
 zone_definitions:[{id:'z1',net:'GND',layers:['B.Cu'],polygons:[]},{id:'z2',net:'',layers:['F.Cu'],keepout:true,polygons:[]}],
 zones:[{id:'island1',zone_id:'z1',net:'GND',layer:'B.Cu'},{id:'island2',zone_id:'z1',net:'GND',layer:'B.Cu'}]});

test('layout hierarchy contains real pads, copper, graphics and unfilled zones without changing inputs',{skip:!objects},()=>{
 const source=spec(),geo=geometry(),before=JSON.stringify([source,geo]),tree=objects.buildObjectTree(source,{view:'layout',geometry:geo});
 for(const id of ['component:J1','footprint:J1','pad:J1:p1','pad:J1:p2','track:t1','arc:a1','via:v1','outline:o1','drawing:J1:d1','drawing:board:d2','zone:z1','zone:z2','fill:island1','fill:island2'])assert.ok(tree.nodes.has(id),id);
 assert.equal(tree.nodes.get('pad:J1:p1').target.id,'p1');assert.equal(tree.nodes.get('pad:J1:p2').target.id,'p2');
 assert.equal(tree.nodes.get('track:t1').parent,'net:SIG');assert.equal(tree.nodes.get('fill:island1').parent,'zone:z1');assert.equal(tree.nodes.get('zone:z2').target.kind,'zone');
 assert.equal(JSON.stringify([source,geo]),before);
});

test('object identities and pad labels do not follow geometry list indexes',{skip:!objects},()=>{
 const first=objects.buildObjectTree(spec(),{view:'layout',geometry:geometry()}),geo=geometry();for(const value of Object.values(geo))if(Array.isArray(value))value.reverse();geo.tracks[0].w=.4;
 const next=objects.buildObjectTree(spec(),{view:'layout',geometry:geo});assert.deepEqual([...first.nodes.keys()].sort(),[...next.nodes.keys()].sort());
 for(const id of ['pad:J1:p1','pad:J1:p2','track:t1']){assert.equal(next.nodes.get(id).label,first.nodes.get(id).label);assert.equal(next.nodes.get(id).target.id,first.nodes.get(id).target.id);}
});

test('search reveals the matching native object and its ancestors while keeping unrelated branches out',{skip:!objects},()=>{
 const tree=objects.buildObjectTree(spec(),{view:'layout',geometry:geometry()}),rows=objects.objectRows(tree,{expanded:new Set(),query:'SIG trace'}),ids=rows.map(row=>row.id);
 assert.ok(ids.includes('root')&&ids.includes('layout')&&ids.includes('nets')&&ids.includes('net:SIG')&&ids.includes('track:t1'));assert.ok(!ids.includes('component:J2')&&!ids.includes('zone:z2'));
 assert.ok(objects.objectRows(tree,{expanded:new Set(),query:'J1 pad'}).some(row=>row.id==='pad:J1:p2'));
 assert.equal(objects.objectRows(tree,{query:'no-such-object'}).length,0);
});

test('Cmd toggles and Shift ranges use visible selectable rows and preserve the selection anchor',{skip:!objects},()=>{
 const visible=['component:J1','component:J2','track:t1','arc:a1'],base=new Set(['component:J1']);
 let result=objects.chooseObjects(base,'track:t1',visible,{range:true,anchor:'component:J1'});assert.deepEqual([...result.selection],visible.slice(0,3));assert.equal(result.anchor,'component:J1');
 result=objects.chooseObjects(result.selection,'component:J2',visible,{additive:true,anchor:result.anchor});assert.deepEqual([...result.selection],['component:J1','track:t1']);assert.deepEqual([...base],['component:J1']);
 result=objects.chooseObjects(base,'arc:a1',visible,{range:true,anchor:'hidden-object'});assert.deepEqual([...result.selection],['arc:a1']);
});

test('visibility follows hierarchy and never hides other nets or edits the board geometry',{skip:!objects},()=>{
 const geo=geometry(),before=JSON.stringify(geo),tree=objects.buildObjectTree(spec(),{view:'layout',geometry:geo});
 const hidden=objects.hiddenObjects(tree,new Set(['component:J1','zone:z1']));assert.ok(hidden.pads.has('J1:p1')&&hidden.pads.has('J1:p2')&&!hidden.pads.has('J2:p3'));assert.ok(hidden.zones.has('island1')&&hidden.zones.has('island2'));assert.equal(hidden.tracks.size,0);
 const net=objects.hiddenObjects(tree,new Set(['net:SIG']));assert.ok(net.tracks.has('t1')&&net.arcs.has('a1')&&net.vias.has('v1'));assert.equal(net.pads.size,0);assert.equal(JSON.stringify(geo),before);
});

test('schematic sheets, units, wires and labels retain their own identities and current route indexes',{skip:!objects},()=>{
 const s=spec();s.components[0].sheet='Control';s.editor={sheets:{Control:{title:'Control',parent:''},Child:{title:'Sensors',parent:'Control'},Empty:{title:'Empty',parent:''}},connection_guides:[{id:'wire-a',from:'J1.1',to:'node:label-a'}],wire_nodes:{'label-a':{net:'SIG',sheet:'Control',label:{kind:'power'},position:[100,100]},loose:{net:'GND',sheet:'Child',position:[50,50]}}};
 const scene={symbols:[{ref:'J1',key:'J1#1',sheet:'Control'},{ref:'J1',key:'J1#2',sheet:'Control'}],routes:[{index:0,net:'SIG',sheet:'Control'}]};const tree=objects.buildObjectTree(s,{view:'schematic',scene});
 for(const id of ['sheet:Control','sheet:Child','sheet:Empty','component:J1','symbol:J1#1','symbol:J1#2','wire:wire-a','node:label-a','node:loose'])assert.ok(tree.nodes.has(id),id);
 assert.equal(tree.nodes.get('sheet:Child').parent,'sheet:Control');assert.equal(tree.nodes.get('wire:wire-a').target.index,0);assert.equal(tree.nodes.get('wire:wire-a').target.sheet,'Control');assert.equal(tree.nodes.get('node:label-a').kind,'label');assert.equal(tree.nodes.get('symbol:J1#2').target.symbolKey,'J1#2');
 s.editor.connection_guides.unshift({id:'new-wire',from:'J2.1',to:'J2.2'});scene.routes[0].index=1;assert.equal(objects.buildObjectTree(s,{view:'schematic',scene}).nodes.get('wire:wire-a').target.index,1);
});

test('pending schematic data still locates a nested sheet boundary wire in its parent',{skip:!objects},()=>{
 const s=spec();s.components[0].sheet='Control';s.editor={sheets:{Control:{parent:''},Child:{parent:'Control'}},connection_guides:[{id:'boundary',from:'sheet:Child.SIG',to:'J1.1'}]};
 const tree=objects.buildObjectTree(s,{view:'schematic'});assert.equal(tree.nodes.get('wire:boundary').target.sheet,'Control');
});

test('hiding one schematic guide clips only its native union and retains shared visible branches',{skip:!objects},()=>{
 assert.equal(typeof objects.displayedWires,'function','Schematic wire visibility is not implemented');
 const s=spec();s.editor.connection_guides=[{id:'hidden'},{id:'visible'}];
 const scene={wires:[{sheet:'',net:'SIG',points:[[0,0],[100,0]]},{sheet:'',net:'GND',points:[[0,10],[100,10]]}],routes:[{index:0,sheet:'',net:'SIG',points:[[0,0],[60,0]],status:'routed'},{index:1,sheet:'',net:'SIG',points:[[40,0],[100,0]],status:'routed'}]};
 const before=JSON.stringify([s,scene]),wires=objects.displayedWires(scene,s,'',(_kind,id)=>id!=='hidden');
 assert.deepEqual(wires.find(w=>w.net==='SIG').points,[[40,0],[100,0]]);assert.deepEqual(wires.find(w=>w.net==='GND').points,[[0,10],[100,10]]);assert.equal(JSON.stringify([s,scene]),before);
 assert.deepEqual(objects.displayedWires(scene,s,'',kind=>kind!=='sheet'),[]);
});
