import test from 'node:test';
import assert from 'node:assert/strict';
import {CUBE_FACES,cameraBasis,viewOrientation,projectPoint,cubeTarget,orbitOrientation} from '../wholeboard/web/workbench-camera.mjs';
const near=(got,want)=>{assert.equal(got.length,want.length);got.forEach((v,i)=>assert.ok(Math.abs(v-want[i])<1e-10,`${got} != ${want}`));};

test('all six standard camera directions have a finite orthonormal screen basis, including both poles',()=>{
 const rows=[[[0,0,1],[1,0,0],[0,1,0]],[[0,0,-1],[1,0,0],[0,-1,0]],[[0,-1,0],[1,0,0],[0,0,1]],[[0,1,0],[-1,0,0],[0,0,1]],[[-1,0,0],[0,-1,0],[0,0,1]],[[1,0,0],[0,1,0],[0,0,1]]];
 for(const[d,r,u]of rows){const basis=cameraBasis(viewOrientation(d));near(basis.direction,d);near(basis.right,r);near(basis.up,u);}
});
test('a clockwise quarter roll rotates the image while retaining its viewing direction',()=>{
 const basis=cameraBasis({...viewOrientation([0,-1,0]),roll:Math.PI/2});near(basis.direction,[0,-1,0]);near(basis.right,[0,0,1]);near(basis.up,[-1,0,0]);
});
test('software and cube projection share the labelled world directions',()=>{
 near(projectPoint([3,4,5],viewOrientation([0,0,1])),[3,-4,5]);near(projectPoint([3,4,5],viewOrientation([0,0,-1])),[3,4,-5]);near(projectPoint([3,4,5],viewOrientation([1,0,0])),[4,-5,3]);
});
test('cube face centres, edge bands and corners choose the corresponding three-dimensional direction',()=>{
 assert.deepEqual(cubeTarget('top',0,0),[0,0,1]);assert.deepEqual(cubeTarget('top',.9,0),[1,0,1]);assert.deepEqual(cubeTarget('top',-.9,-.9),[-1,-1,1]);assert.deepEqual(cubeTarget('front',.9,.9),[1,-1,1]);assert.deepEqual(cubeTarget('bottom',0,.9),[0,-1,-1]);
});
test('invalid directions and nonfinite cube hits cannot reach a camera transform',()=>{
 for(const value of [[0,0,0],[NaN,1,0],[0,Infinity,0],[1,2],null])assert.throws(()=>viewOrientation(value));assert.throws(()=>cubeTarget('unknown',0,0));assert.throws(()=>cubeTarget('top',Infinity,0));
});
test('orbit arrows leave a pole smoothly and reach the adjacent side without singularities',()=>{
 const start=viewOrientation([0,0,1]),half=orbitOrientation(start,Math.PI/4,0),right=orbitOrientation(half,Math.PI/4,0);near(cameraBasis(half).direction,[Math.SQRT1_2,0,Math.SQRT1_2]);near(cameraBasis(right).direction,[1,0,0]);
 const back=orbitOrientation(start,0,Math.PI/2);near(cameraBasis(back).direction,[0,1,0]);near(cameraBasis(back).up,[0,0,-1]);
});
test('a direction is independent of vector magnitude for very small or large finite inputs',()=>{
 near(cameraBasis(viewOrientation([1e-15,0,0])).direction,[1,0,0]);near(cameraBasis(viewOrientation([Number.MAX_VALUE,Number.MAX_VALUE,Number.MAX_VALUE])).direction,[1/Math.sqrt(3),1/Math.sqrt(3),1/Math.sqrt(3)]);
});
test('cube hit regions cover exactly the26 signed axis combinations and retain all six face names',()=>{
 const centres={top:[0,0,1],bottom:[0,0,-1],front:[0,-1,0],back:[0,1,0],left:[-1,0,0],right:[1,0,0]},actual=new Set(),expected=[];
 for(const[name,want]of Object.entries(centres))assert.deepEqual(cubeTarget(name,0,0),want);
 for(const face of CUBE_FACES)for(const u of [-.825,0,.825])for(const v of [-.825,0,.825])actual.add(cubeTarget(face.id,u,v).join(','));
 for(const x of [-1,0,1])for(const y of [-1,0,1])for(const z of [-1,0,1])if(x||y||z)expected.push([x,y,z].join(','));assert.deepEqual([...actual].sort(),expected.sort());
});
