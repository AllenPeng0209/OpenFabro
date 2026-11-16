import test from 'node:test';
import assert from 'node:assert/strict';
import * as objects from '../wholeboard/web/workbench-objects-model.mjs';
import {updateComponent,upsertNet} from '../wholeboard/web/workbench-model.mjs';

const gid='user-group:power',nested='user-group:input';
const source=()=>({name:'Groups',board:{width_mm:30,height_mm:22,layers:2},components:[{ref:'R1',value:'1k'},{ref:'R2',value:'2k'},{ref:'C1',value:'1u'}],nets:[{name:'SIG',pins:['R1.1','R2.1']}],editor:{positions:{R1:[10,20]}}});
const make=(spec=source(),view='layout',geometry=null)=>objects.buildObjectTree(spec,{view,geometry});
const state=()=>({groups:{[gid]:{name:'Power',parent:'components'}},parents:{'component:R1':gid,'component:R2':gid},order:{components:[gid,'component:C1'],[gid]:['component:R2','component:R1']}});

test('saved groups reparent and order actual component rows without altering their electrical ownership',()=>{
 const spec=source();spec.editor.object_tree={layout:state()};const before=JSON.stringify(spec),tree=make(spec);
 assert.equal(tree.nodes.get('component:R1').parent,gid,'Saved object groups are not applied to the actual tree');
 assert.equal(tree.nodes.get(gid).parent,'components');assert.deepEqual(tree.nodes.get(gid).children,['component:R2','component:R1']);
 assert.deepEqual(tree.nodes.get('components').children,[gid,'component:C1']);assert.equal(tree.nodes.get('component:R1').naturalParent,'components');assert.equal(tree.nodes.get('component:R1').target.ref,'R1');assert.equal(JSON.stringify(spec),before);
 const rows=objects.objectRows(tree,{expanded:new Set(),query:'power'});assert.ok(rows.some(n=>n.id==='component:R1')&&rows.some(n=>n.id==='component:R2'));assert.ok(!rows.some(n=>n.id==='component:C1'));
});

test('grouping a selection is a pure metadata edit and preserves original sibling order',()=>{
 const spec=source(),before=JSON.stringify(spec),next=objects.organizeObjectTree?.(spec,make(spec),{action:'group',id:gid,name:'Power',ids:['component:R2','component:R1']});
 assert.deepEqual(next?.editor?.object_tree?.layout?.groups,{[gid]:{name:'Power',parent:'components'}},'Grouping did not produce saved group metadata');
 const tree=make(next);assert.deepEqual(tree.nodes.get(gid).children,['component:R1','component:R2']);assert.deepEqual(tree.nodes.get('components').children,[gid,'component:C1']);
 const expected=source();delete next.editor.object_tree;assert.deepEqual(next,expected);assert.equal(JSON.stringify(spec),before);
});

test('nested groups flatten component selections once and their visibility reaches real descendants',()=>{
 const spec=source();spec.editor.object_tree={layout:state()};spec.editor.object_tree.layout.groups[nested]={name:'Input',parent:gid};spec.editor.object_tree.layout.parents['component:R1']=nested;
 const tree=make(spec),selection=objects.objectSelection?.(tree,[gid,nested,'component:R1']);assert.deepEqual(selection?.map(n=>n.ref),['R2','R1']);
 const mask=objects.hiddenObjects(tree,new Set([gid]));assert.deepEqual([...mask.components].sort(),['R1','R2']);assert.ok(!mask.components.has('C1'));
});

test('reorder and moves preserve categories, reject cycles and never move a pad into another footprint',()=>{
 const spec=source();spec.editor.object_tree={layout:state()};const tree=make(spec);
 const ordered=objects.organizeObjectTree?.(spec,tree,{action:'reorder',id:'component:R1',delta:-1});assert.deepEqual(ordered?.editor?.object_tree?.layout?.order?.[gid],['component:R1','component:R2']);
 if(!objects.organizeObjectTree)return;
 const moved=objects.organizeObjectTree(spec,tree,{action:'move',ids:['component:C1'],parent:gid,before:'component:R1'});assert.deepEqual(make(moved).nodes.get(gid).children,['component:R2','component:C1','component:R1']);
 const nestedSpec=objects.organizeObjectTree(spec,tree,{action:'create',id:nested,name:'Input',parent:gid});assert.throws(()=>objects.organizeObjectTree(nestedSpec,make(nestedSpec),{action:'move',ids:[gid],parent:nested}),/cycle|itself|descendant/i);
 const geo={footprints:[{ref:'R1',id:'f1'},{ref:'R2',id:'f2'}],pads:[{id:'p1',name:'1',ref:'R1'},{id:'p2',name:'1',ref:'R2'}]};assert.throws(()=>objects.organizeObjectTree(spec,make(spec,'layout',geo),{action:'group',id:nested,name:'Bad',ids:['pad:R1:p1','pad:R2:p2']}),/category|same/i);
});

test('ungroup releases nested members in place and removes only the organizational folder',()=>{
 const spec=source();spec.editor.object_tree={layout:state()};spec.editor.object_tree.layout.groups[nested]={name:'Input',parent:gid};spec.editor.object_tree.layout.parents['component:R1']=nested;
 const next=objects.organizeObjectTree?.(spec,make(spec),{action:'ungroup',id:gid});assert.ok(next?.editor?.object_tree,'Ungroup did not return an editable saved design');
 assert.equal(next.editor.object_tree.layout.groups[gid],undefined);assert.equal(next.editor.object_tree.layout.groups[nested].parent,'components');
 const tree=make(next);assert.deepEqual(tree.nodes.get('components').children,['component:R2',nested,'component:C1']);assert.deepEqual(next.components,spec.components);assert.deepEqual(next.nets,spec.nets);
});

test('groups are view-scoped and never reassign a component after it moves to a different sheet',()=>{
 const spec=source();spec.editor.object_tree={layout:state(),schematic:{groups:{[gid]:{name:'Control',parent:'components:Control'}},parents:{'component:R1':gid},order:{}}};spec.editor.sheets={Control:{title:'Control',parent:''},Other:{title:'Other',parent:''}};spec.components[0].sheet='Control';
 assert.equal(make(spec).nodes.get('component:R1').parent,gid);assert.equal(make(spec,'schematic').nodes.get('component:R1').parent,gid,'Schematic groups are not applied');
 spec.components[0].sheet='Other';const changed=make(spec,'schematic');assert.equal(changed.nodes.get('component:R1').parent,'components:Other');assert.ok(!changed.nodes.get(gid).children.includes('component:R1'));
});

test('missing objects remain absent and invalid imported group cycles cannot hide the design',()=>{
 const spec=source();spec.editor.object_tree={layout:state()};spec.components=spec.components.filter(c=>c.ref!=='R2');const tree=make(spec);assert.equal(tree.nodes.has('component:R2'),false);assert.equal(tree.nodes.get('component:R1').parent,gid);assert.equal(tree.nodes.get(gid).missingMembers,1);
 spec.editor.object_tree.layout.groups[gid].parent=nested;spec.editor.object_tree.layout.groups[nested]={name:'Cycle',parent:gid};const safe=make(spec);assert.equal(safe.nodes.get('component:R1').parent,'components');assert.ok(objects.objectRows(safe).some(n=>n.id==='component:R1'));assert.ok(safe.organizationError);
});

test('optional null metadata stays absent and unavailable native categories never invent objects',()=>{
 const spec=source();spec.editor.object_tree=null;assert.equal(make(spec).organizationError,undefined,'A backend-accepted absent organization is rendered as an error');
 spec.editor.object_tree={layout:{groups:{[gid]:{name:'Old pads',parent:'pads:removed'}},parents:{'pad:removed:old':gid},order:{}}};
 const tree=make(spec);assert.equal(tree.nodes.get(gid)?.unavailable,true);assert.equal(tree.nodes.has('pad:removed:old'),false);assert.equal(tree.nodes.get('component:R1').parent,'components');
});

test('renaming a component retains its organizational membership and order in both views',()=>{
 const spec=source();spec.editor.object_tree={layout:state(),schematic:state()};spec.editor.object_tree.schematic.groups[gid].parent='components:';
 const renamed=updateComponent(spec,'R1',{ref:'R8'});
 for(const view of ['layout','schematic']){
  const meta=renamed.editor.object_tree[view];assert.equal(meta.parents['component:R8'],gid,'Component rename lost its saved group membership');assert.equal(meta.parents['component:R1'],undefined);assert.deepEqual(meta.order[gid],['component:R2','component:R8']);assert.equal(make(renamed,view).nodes.get('component:R8').parent,gid);
 }
 assert.equal(spec.components[0].ref,'R1');
});

test('renaming a net retains its group and the category of its native trace groups',()=>{
 const spec=source();spec.editor.object_tree={layout:{groups:{[gid]:{name:'Signals',parent:'nets'},[nested]:{name:'Traces',parent:'net:SIG'}},parents:{'net:SIG':gid},order:{[gid]:['net:SIG'],'net:SIG':[nested]}}};
 const renamed=upsertNet(spec,{name:'SENSE',class:'signal',pins:['R1.1','R2.1']},'SIG'),tree=make(renamed);
 assert.equal(tree.nodes.get('net:SENSE').parent,gid);assert.equal(renamed.editor.object_tree.layout.groups[nested].parent,'net:SENSE');assert.deepEqual(renamed.editor.object_tree.layout.order[gid],['net:SENSE']);
});
