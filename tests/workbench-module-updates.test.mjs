import test from 'node:test';import assert from 'node:assert/strict';
import {updateComponent,upsertNet,connectPins} from '../wholeboard/web/workbench-model.mjs';
const maps=()=>({refs:{R1:'R1'},nets:{SIG:'LOCAL'}});
const spec=()=>({components:[{ref:'R1'},{ref:'J1'}],nets:[{name:'LOCAL',class:'signal',pins:['R1.1']},{name:'HOST',class:'power',pins:['J1.1']}],
 editor:{module_instances:{M1:{refs:['R1'],nets:{SIG:'LOCAL'},source_maps:maps(),baseline:{maps:maps()}}}}});
test('a module part designator rename rebases both live identity and frozen baseline maps',()=>{
 const out=updateComponent(spec(),'R1',{ref:'R9'}),meta=out.editor.module_instances.M1;assert.equal(meta.source_maps.refs.R1,'R9');assert.equal(meta.baseline.maps.refs.R1,'R9');
});
test('a pure net rename rebases its alias but an electrical merge remains a local override',()=>{
 const renamed=upsertNet(spec(),{name:'RENAMED',class:'signal',pins:['R1.1']},'LOCAL').editor.module_instances.M1;
 assert.equal(renamed.source_maps.nets.SIG,'RENAMED');assert.equal(renamed.baseline.maps.nets.SIG,'RENAMED');
 const merged=connectPins(spec(),'R1.1','J1.1',true).editor.module_instances.M1;assert.equal(merged.nets.SIG,'HOST');assert.equal(merged.baseline.maps.nets.SIG,'LOCAL');
});
