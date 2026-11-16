import test from 'node:test';
import assert from 'node:assert/strict';
let files;try{files=await import('../wholeboard/web/workbench-files-model.mjs');}catch{}
test('the project file hierarchy is implemented',()=>assert.ok(files,'Files still renders a flat basename-only list'));
const entries=()=>[
 {path:'design.json',name:'design.json',text_editable:true},
 {path:'docs/a/readme.md',name:'readme.md',text_editable:true},
 {path:'docs/b/readme.md',name:'readme.md',text_editable:true},
 {path:'docs/外壳 #1?/检查.md',name:'检查.md',text_editable:true},
 {path:'native/generation-a/geometry.json',name:'geometry.json',native_status:'saved',text_editable:false},
 {path:'native/generation-b/geometry.json',name:'geometry.json',native_status:'current',native_role:'older_geometry',text_editable:false},
 {path:'native/generation-b/geometry-v4-abcdef.json',name:'geometry-v4-abcdef.json',native_status:'current',native_role:'geometry',text_editable:false},
 {path:'history/design-v1.json',name:'design-v1.json',text_editable:false},
];
const native={status:'current',folder:'native/generation-b',primary_paths:{geometry:'native/generation-b/geometry-v4-abcdef.json'}};

test('same basenames remain distinct leaves under actual project folders',{skip:!files},()=>{
 const input=entries(),before=JSON.stringify(input),tree=files.buildFileTree(input,{native});
 assert.equal(tree.nodes.get('file:docs/a/readme.md').parent,'folder:docs/a');assert.equal(tree.nodes.get('file:docs/b/readme.md').parent,'folder:docs/b');
 assert.equal(tree.nodes.get('file:docs/外壳 #1?/检查.md').file.path,'docs/外壳 #1?/检查.md');
 assert.equal(tree.nodes.get('folder:native/generation-b').badge,'Current generation');
 assert.equal(tree.nodes.get('file:native/generation-b/geometry-v4-abcdef.json').badge,'Current geometry');
 assert.equal(tree.nodes.get('file:native/generation-b/geometry.json').badge,'Prior geometry');
 assert.notEqual(tree.nodes.get('file:native/generation-a/geometry.json').badge,'Current geometry');assert.equal(JSON.stringify(input),before);
});

test('file rows have stable paths, folder-first ordering and natural numeric sorting',{skip:!files},()=>{
 const input=[{path:'docs/r10.md',name:'r10.md'},{path:'docs/z/readme.md',name:'readme.md'},{path:'docs/r2.md',name:'r2.md'}];
 const a=files.buildFileTree(input),b=files.buildFileTree([...input].reverse()),expand=new Set(['','docs','docs/z']);
 assert.deepEqual(files.fileRows(a,{expanded:expand}).map(r=>r.id),files.fileRows(b,{expanded:expand}).map(r=>r.id));
 assert.deepEqual(a.nodes.get('folder:docs').children,['folder:docs/z','file:docs/r2.md','file:docs/r10.md']);
});

test('search reveals ancestors and current-generation filters use authoritative scope',{skip:!files},()=>{
 const tree=files.buildFileTree(entries(),{native});let rows=files.fileRows(tree,{expanded:new Set(),query:'docs/b readme'});
 assert.ok(rows.some(r=>r.id==='folder:docs/b')&&rows.some(r=>r.id==='file:docs/b/readme.md'));assert.ok(!rows.some(r=>r.id==='file:docs/a/readme.md'));
 rows=files.fileRows(tree,{scope:'current',expanded:new Set(['','native','native/generation-b'])});assert.ok(rows.some(r=>r.id==='file:native/generation-b/geometry-v4-abcdef.json'));assert.ok(!rows.some(r=>r.id==='file:native/generation-a/geometry.json'));
 const stale=files.buildFileTree(entries().map(e=>({...e,native_status:e.native_status==='current'?'stale':e.native_status})),{native:{...native,status:'stale'}});
 assert.ok(!files.fileRows(stale,{scope:'current'}).some(r=>r.file));assert.equal(files.fileRows(tree,{query:'not-present'}).length,0);
});

test('Documents and Assets keep generated engineering files in the all-files browser',{skip:!files},()=>{
 const input=[...entries(),{path:'attachments/Subject.png',name:'Subject.png',category:'project'},{path:'native/generation-b/preview.svg',name:'preview.svg',category:'native'},{path:'native/generation-b/report.md',name:'report.md',category:'native'}],tree=files.buildFileTree(input,{native});
 const docs=files.fileRows(tree,{scope:'documents'}).filter(r=>r.file).map(r=>r.path),assets=files.fileRows(tree,{scope:'assets'}).filter(r=>r.file).map(r=>r.path);
 assert.ok(docs.includes('docs/a/readme.md')&&!docs.includes('design.json')&&!docs.includes('native/generation-b/report.md'));
 assert.deepEqual(assets,['attachments/Subject.png']);
});

const packet=(paths,{offset=0,total=paths.length,index='a'.repeat(64),version=1}={})=>({files:paths.map(path=>({path,name:path.split('/').at(-1),url:'/files/'+path})),offset,next_offset:offset+paths.length,total,truncated:offset+paths.length<total,index_sha256:index,design_version:version,native:{status:'none',primary_paths:{}}});
test('the inventory loader reads every pinned page beyond the old fixed limit',{skip:!files},async()=>{
 const names=Array.from({length:1205},(_,i)=>`docs/r${i}.md`),calls=[];
 const result=await files.loadFileCatalog(async params=>{calls.push(params);return packet(names.slice(params.offset,params.offset+1000),{offset:params.offset,total:1205});});
 assert.equal(result.files.length,1205);assert.equal(calls.length,2);assert.equal(calls[1].expected_index_sha256,'a'.repeat(64));assert.equal(result.truncated,false);
});

test('an inventory change discards all old pages before retrying',{skip:!files},async()=>{
 let count=0;
 const result=await files.loadFileCatalog(async params=>{count++;if(count===1)return packet(['old.md'],{total:2});if(count===2)throw Object.assign(new Error('changed'),{status:409});return packet(['new.md'],{index:'b'.repeat(64)});});
 assert.deepEqual(result.files.map(f=>f.path),['new.md']);assert.equal(count,3);
});

test('late catalog responses are cancelled and malformed pages never look complete',{skip:!files},async()=>{
 let current=true;await assert.rejects(files.loadFileCatalog(async()=>{current=false;return packet(['old.md']);},{isCurrent:()=>current}),/cancel/i);
 await assert.rejects(files.loadFileCatalog(async()=>({...packet(['a.md'],{total:2}),next_offset:0})),/catalog|page/i);
 let calls=0;await assert.rejects(files.loadFileCatalog(async()=>{calls++;throw Object.assign(new Error('changed'),{status:409});}),/changed/i);assert.equal(calls,3);
});
