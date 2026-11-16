import test from 'node:test';
import assert from 'node:assert/strict';
import {captureSize,referenceMarkup} from '../wholeboard/web/workbench-markup.mjs';

test('viewport capture respects DPR and limits pixel dimensions without stretching',()=>{
 assert.deepEqual(captureSize(700,900,2),[1400,1800]);
 assert.deepEqual(captureSize(8000,4000,2),[2048,1024]);
 assert.deepEqual(captureSize(4000,8000,3),[1024,2048]);
 assert.throws(()=>captureSize(0,100));assert.throws(()=>captureSize(NaN,100));
});
test('image previews only accept an owning project canonical reference URL',()=>{
 const id='a'.repeat(32),reference={id,project_id:'project-a',design_version:3,view:'schematic',url:`/api/projects/project-a/files/references/canvas/${id}.png?v=123`};
 assert.match(referenceMarkup(reference,'project-a'),/Marked schematic/);
 assert.equal(referenceMarkup(reference,'project-b'),'');
 assert.equal(referenceMarkup({...reference,url:'https://external.invalid'+reference.url},'project-a'),'');
 assert.equal(referenceMarkup({...reference,url:'javascript:alert(1)'},'project-a'),'');
 assert.equal(referenceMarkup({...reference,url:'/api/projects/project-b/files/references/canvas/'+id+'.png'},'project-a'),'');
 assert.equal(referenceMarkup({...reference,id:'x'+id,url:`/api/projects/project-a/files/references/canvas/x${id}.png`},'project-a'),'');
});
