import test from 'node:test';
import assert from 'node:assert/strict';

async function helper(){let module;try{module=await import('../wholeboard/web/workbench-mesh-files.mjs');}catch{}assert.equal(typeof module?.meshResources,'function','Mesh companion discovery is missing');return module;}
function file(path,data){const f=new File([data],path.split('/').at(-1));Object.defineProperty(f,'webkitRelativePath',{value:path});return f;}

test('nested model resources resolve inside the selected folder without uploading unrelated images',async()=>{
 const {meshResources}=await helper(),root=file('product/parts/model.obj','mtllib ../materials/paint.mtl\n'),material=file('product/materials/paint.mtl','newmtl paint\nmap_Kd ../textures/logo.png\n'),image=file('product/textures/logo.png','image'),other=file('product/private.png','unrelated');
 const result=await meshResources(root,[root,material,image,other]);assert.equal(result.entry_path,'product/parts/model.obj');assert.deepEqual(Object.keys(result.resources).sort(),['product/materials/paint.mtl','product/textures/logo.png']);
});

test('missing companions and paths outside an uploaded folder stop before an API upload',async()=>{
 const {meshResources}=await helper(),root=file('product/model.gltf',JSON.stringify({buffers:[{uri:'../../outside.bin'}]}));
 await assert.rejects(()=>meshResources(root,[root]),/outside|relative|resource/);
 const missing=file('model.gltf',JSON.stringify({buffers:[{uri:'missing.bin'}]}));await assert.rejects(()=>meshResources(missing,[missing]),/Missing|missing/);
});
