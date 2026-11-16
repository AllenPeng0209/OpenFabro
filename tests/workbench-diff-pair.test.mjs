import test from 'node:test';
import assert from 'node:assert/strict';
import {beginRoute,extendRoute,changeRouteLayer} from '../wholeboard/web/workbench-routing.mjs';
import * as routing from '../wholeboard/web/workbench-routing.mjs';
import {copperGeometry} from '../wholeboard/web/workbench-copper.mjs';
const rawFixture=()=>({spec:{name:'pair',board:{width_mm:45,height_mm:30,layers:4},rules:{track_mm:.25,power_track_mm:.5,clearance_mm:.2,via_diameter_mm:.6,via_drill_mm:.3},components:[{ref:'J1'},{ref:'J2'}],nets:[{name:'DP',pins:['J1.1','J2.1']},{name:'DN',pins:['J1.2','J2.2']},{name:'KEEP',pins:[]}]},geo:{bbox:[100,100,145,130],pads:[{id:'p1',ref:'J1',name:'1',x:108,y:108,net:'DP',front:true,kind:'thru_hole'},{id:'n1',ref:'J1',name:'2',x:108,y:110.54,net:'DN',front:true,kind:'thru_hole'},{id:'p2',ref:'J2',name:'1',x:138,y:108,net:'DP',front:true,kind:'thru_hole'},{id:'n2',ref:'J2',name:'2',x:138,y:110.54,net:'DN',front:true,kind:'thru_hole'}],tracks:[{id:'keep',net:'KEEP',a:[104,125],b:[140,125],w:.5,layer:'B.Cu'}],arcs:[],vias:[],zone_sources:[]},profiles:{schema:1,pairs:[{id:'data',nets:['DP','DN'],width_mm:.25,gap_mm:.2,ends:[{pins:['J1.1','J1.2']},{pins:['J2.1','J2.2']}],polarity:{DP:'P',DN:'N'}}],issues:[]}});
const fixture=()=>{const value=rawFixture();value.geo.layers=['F.Cu','In1.Cu','In2.Cu','B.Cu'];value.geo.pads=value.geo.pads.map(p=>({w:.8,h:.8,shape:'circle',layers:['*.Cu'],drill:.4,drill_size:[.4,.4],...p}));return value;};
const target={kind:'pad',pin:'J1.1',padId:'p1'};

test('declared pair starts at both physical pads and creates both nets in one routing transaction',()=>{
 const {spec,geo,profiles}=fixture(),before=structuredClone(spec),s=beginRoute(spec,geo,target,{layer:'F.Cu',profiles});assert.ok(s.pair,'The declared pair was silently treated as a single net');assert.deepEqual(s.point,[8,9.27]);
 const next=extendRoute(spec,geo,s,{kind:'point',at:[18,9.27]});assert.equal(next.finished,false);for(const net of ['DP','DN'])assert.ok(next.spec.fixed_copper.some(g=>g.net===net&&g.tracks.length),'Missing paired copper '+net);assert.deepEqual(next.spec.fixed_copper.find(g=>g.net==='KEEP').tracks[0],{id:'keep',a:[4,25],b:[40,25],w:.5,layer:'B.Cu',net:'KEEP'});assert.deepEqual(spec,before);
});
test('finishing either named leg connects each corresponding destination pad without changing pin membership',()=>{
 const {spec,geo,profiles}=fixture(),s=beginRoute(spec,geo,target,{profiles}),r=extendRoute(spec,geo,s,{kind:'pad',pin:'J2.1',padId:'p2'});assert.ok(s.pair,'Pair routing is missing');assert.equal(r.finished,true);assert.deepEqual(r.spec.nets,spec.nets);const p=r.spec.fixed_copper.find(g=>g.net==='DP'),n=r.spec.fixed_copper.find(g=>g.net==='DN');assert.deepEqual(p.tracks[0].a,[8,8]);assert.deepEqual(p.tracks.at(-1).b,[38,8]);assert.deepEqual(n.tracks[0].a,[8,10.54]);assert.deepEqual(n.tracks.at(-1).b,[38,10.54]);
});
test('a paired layer change adds two separated through vias and leaves an undo snapshot for both legs',()=>{
 const {spec,geo,profiles}=fixture(),s=beginRoute(spec,geo,target,{profiles});assert.ok(s.pair,'Pair routing is missing');const r=changeRouteLayer(spec,geo,s,[22,9.27],'B.Cu');assert.equal(r.session.layer,'B.Cu');const vias=r.spec.fixed_copper.filter(g=>['DP','DN'].includes(g.net)).flatMap(g=>g.vias);assert.equal(vias.length,2);assert.ok(Math.hypot(vias[0].p[0]-vias[1].p[0],vias[0].p[1]-vias[1].p[1])>=.8-1e-4);assert.ok(r.session.history.length);assert.deepEqual(r.spec.fixed_copper.find(g=>g.net==='KEEP').tracks[0].a,[4,25]);
});
test('missing or ambiguous partner pads reject paired routing while explicit single routing remains available',()=>{
 const {spec,geo,profiles}=fixture();geo.pads.push({...geo.pads[1],id:'n1-duplicate',x:109});assert.throws(()=>beginRoute(spec,geo,target,{profiles}),/pair|physical|ambiguous/i);const s=beginRoute(spec,geo,target,{profiles,single:true});assert.deepEqual(s.point,[8,8]);
});
test('single override keeps the parked partner and paired routing can resume from both actual endpoints',()=>{
 const {spec,geo,profiles}=fixture(),s=beginRoute(spec,geo,target,{profiles});assert.ok(s.pair,'Pair routing is missing');const solo=routing.setRouteMode(s,true),one=extendRoute(spec,geo,solo,{kind:'point',at:[18,8]});assert.ok(!one.spec.fixed_copper.find(g=>g.net==='DN')?.tracks.length);const coupled=routing.setRouteMode(one.session,false),two=extendRoute(one.spec,copperGeometry(one.spec,geo),coupled,{kind:'point',at:[24,9.27]});assert.ok(two.spec.fixed_copper.find(g=>g.net==='DN').tracks.length);assert.deepEqual(two.spec.nets,spec.nets);
});
test('changing pair width retains earlier section identities and dimensions',()=>{
 const {spec,geo,profiles}=fixture(),s=beginRoute(spec,geo,target,{profiles});assert.ok(s.pair,'Pair routing is missing');const one=extendRoute(spec,geo,s,{kind:'point',at:[18,9.27]}),old=structuredClone(one.spec.fixed_copper.filter(g=>['DP','DN'].includes(g.net)));one.session.width=.35;const two=extendRoute(one.spec,copperGeometry(one.spec,geo),one.session,{kind:'point',at:[26,9.27]});for(const group of old)for(const item of group.tracks)assert.deepEqual(two.spec.fixed_copper.find(g=>g.net===group.net).tracks.find(t=>t.id===item.id),item);assert.ok(two.spec.fixed_copper.find(g=>g.net==='DP').tracks.some(t=>t.w===.35));
});
test('switching layers at the original through-hole pair reuses those existing layer connections',()=>{
 const {spec,geo,profiles}=fixture(),s=beginRoute(spec,geo,target,{profiles});assert.ok(s.pair,'Pair routing is missing');const r=changeRouteLayer(spec,geo,s,s.point,'B.Cu');assert.equal(r.session.layer,'B.Cu');assert.equal((r.spec.fixed_copper||[]).flatMap(g=>g.vias||[]).length,0);assert.deepEqual(r.spec,spec);
});
test('the exact paired preview segments become the committed copper on both nets',()=>{
 const {spec,geo,profiles}=fixture(),s=beginRoute(spec,geo,target,{profiles});assert.ok(s.pair,'Pair routing is missing');const at={kind:'point',at:[18,9.27]},preview=routing.previewRoute(spec,geo,s,at),r=extendRoute(spec,geo,s,at);const a=preview.paths.map(t=>({net:t.net,layer:t.layer,w:t.width,a:t.points[0],b:t.points[1]})),b=r.spec.fixed_copper.filter(g=>['DP','DN'].includes(g.net)).flatMap(g=>g.tracks.map(t=>({net:g.net,layer:t.layer,w:t.w,a:t.a,b:t.b})));assert.deepEqual(a,b);
});
test('pair previews reject out-of-board centres and offset endpoints before commit',()=>{
 const {spec,geo,profiles}=fixture(),s=beginRoute(spec,geo,target,{profiles});assert.ok(s.pair);for(const at of [[-1,9.27],[20,0]]){assert.throws(()=>routing.previewRoute(spec,geo,s,{kind:'point',at}),/board/i);assert.throws(()=>extendRoute(spec,geo,s,{kind:'point',at}),/board/i);}
});
test('paired layer placement reuses compatible existing via identities instead of adding coincident holes',()=>{
 const {spec,geo,profiles}=fixture();geo.vias=[{id:'old-p-via',net:'DP',p:[120,108.8695],d:.6,drill:.3,layers:['F.Cu','B.Cu'],type:'through'},{id:'old-n-via',net:'DN',p:[120,109.6705],d:.6,drill:.3,layers:['F.Cu','B.Cu'],type:'through'}];const s=beginRoute(spec,geo,target,{profiles,width:.25,gap:.2}),r=changeRouteLayer(spec,geo,s,[20,9.27],'B.Cu'),vias=r.spec.fixed_copper.flatMap(g=>g.vias||[]);assert.equal(vias.length,2);assert.deepEqual(new Set(vias.map(v=>v.id)),new Set(['old-p-via','old-n-via']));
});
test('an existing paired via with an insufficient span cannot silently be replaced',()=>{
 const {spec,geo,profiles}=fixture();geo.vias=[{id:'narrow-p',net:'DP',p:[120,108.8695],d:.6,drill:.3,layers:['F.Cu','In1.Cu'],type:'blind'},{id:'old-n',net:'DN',p:[120,109.6705],d:.6,drill:.3,layers:['F.Cu','B.Cu'],type:'through'}];const s=beginRoute(spec,geo,target,{profiles,width:.25,gap:.2});assert.throws(()=>changeRouteLayer(spec,geo,s,[20,9.27],'B.Cu'),/span|layer|existing/i);assert.equal(geo.vias[0].id,'narrow-p');
});
test('a stationary preview at new paired vias retains the already committed route',()=>{
 const {spec,geo,profiles}=fixture(),s=beginRoute(spec,geo,target,{profiles}),via=changeRouteLayer(spec,geo,s,[20,9.27],'B.Cu'),preview=routing.previewRoute(via.spec,copperGeometry(via.spec,geo),via.session,{kind:'point',at:via.session.point});assert.ok(preview.paths.length>0,'Committed paired copper disappeared from a stationary via preview');assert.equal(preview.vias.length,2);
});
test('pair preview and commit reject the same next corner at the section limit',()=>{
 const {spec,geo,profiles}=fixture(),start=beginRoute(spec,geo,target,{profiles,width:.25}),placed=extendRoute(spec,geo,start,{kind:'point',at:[13.11,9.27]},{free:true});
 placed.session.pair.sections[0].guide=Array.from({length:512},(_,i)=>[+(8+.01*i).toFixed(4),9.27]);
 const next={kind:'point',at:[13.12,9.27]},current=copperGeometry(placed.spec,geo),before=structuredClone(placed);
 assert.throws(()=>extendRoute(placed.spec,current,placed.session,next,{free:true}),/Finish this pair route/);
 assert.throws(()=>routing.previewRoute(placed.spec,current,placed.session,next),/Finish this pair route/);
 assert.deepEqual(placed,before);
});
