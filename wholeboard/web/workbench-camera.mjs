const dot=(a,b)=>a.reduce((sum,v,i)=>sum+v*b[i],0);
const clean=v=>v.map(n=>Math.abs(n)<1e-12?0:n);
export const CUBE_FACES=Object.freeze([
 {id:'top',normal:[0,0,1],right:[1,0,0],up:[0,1,0]},
 {id:'bottom',normal:[0,0,-1],right:[1,0,0],up:[0,-1,0]},
 {id:'front',normal:[0,-1,0],right:[1,0,0],up:[0,0,1]},
 {id:'back',normal:[0,1,0],right:[-1,0,0],up:[0,0,1]},
 {id:'left',normal:[-1,0,0],right:[0,-1,0],up:[0,0,1]},
 {id:'right',normal:[1,0,0],right:[0,1,0],up:[0,0,1]},
]);
export const wrapAngle=n=>Math.atan2(Math.sin(n),Math.cos(n));
export function viewOrientation(direction){
 if(!Array.isArray(direction)||direction.length!==3||direction.some(v=>!Number.isFinite(v))||!Math.hypot(...direction))throw Error('Choose a finite, nonzero three-dimensional view direction.');
 const scale=Math.max(...direction.map(Math.abs)),[x,y,z]=direction.map(v=>v/scale),flat=Math.hypot(x,y);return{yaw:flat<1e-12?-Math.PI/2:Math.atan2(y,x),pitch:Math.atan2(z,flat),roll:0};
}
export function cameraBasis({yaw=-.7,pitch=.75,roll=0}={}){
 if(![yaw,pitch,roll].every(Number.isFinite))throw Error('Camera orientation must be finite.');
 const cy=Math.cos(yaw),sy=Math.sin(yaw),cp=Math.cos(pitch),sp=Math.sin(pitch),cr=Math.cos(roll),sr=Math.sin(roll),r=[-sy,cy,0],u=[-cy*sp,-sy*sp,cp];
 return{direction:clean([cy*cp,sy*cp,sp]),right:clean(r.map((v,i)=>v*cr+u[i]*sr)),up:clean(u.map((v,i)=>v*cr-r[i]*sr))};
}
export function projectPoint(point,orientation){const b=cameraBasis(orientation);return clean([dot(point,b.right),-dot(point,b.up),dot(point,b.direction)]);}
export function cubeTarget(id,u,v){
 const face=CUBE_FACES.find(f=>f.id===id);if(!face||![u,v].every(Number.isFinite))throw Error('Choose a valid cube face and position.');
 const band=n=>Math.abs(n)>.65?Math.sign(n):0;return clean(face.normal.map((n,i)=>n+band(u)*face.right[i]+band(v)*face.up[i]));
}
function rotate(v,axis,angle){const c=Math.cos(angle),s=Math.sin(angle),d=dot(v,axis),cross=[axis[1]*v[2]-axis[2]*v[1],axis[2]*v[0]-axis[0]*v[2],axis[0]*v[1]-axis[1]*v[0]];return v.map((n,i)=>n*c+cross[i]*s+axis[i]*d*(1-c));}
export function orbitOrientation(orientation,horizontal,vertical){
 if(![horizontal,vertical].every(Number.isFinite))throw Error('Camera orbit must be finite.');
 let basis=cameraBasis(orientation),direction=rotate(basis.direction,basis.up,horizontal),up=basis.up;
 if(vertical){const right=rotate(basis.right,basis.up,horizontal);direction=rotate(direction,right,-vertical);up=rotate(up,right,-vertical);}
 const pose=viewOrientation(direction),base=cameraBasis(pose);pose.roll=wrapAngle(Math.atan2(-dot(up,base.right),dot(up,base.up)));return pose;
}
export function directionLabel(direction){
 const length=Math.hypot(...direction),d=direction.map(v=>v/length),target=d.map(v=>Math.abs(v)<1e-6?0:Math.sign(v)),tLength=Math.hypot(...target);
 if(!tLength||d.some((v,i)=>Math.abs(v-target[i]/tLength)>1e-6))return'Custom view';
 const words=[target[2]>0?'Top':target[2]<0?'Bottom':'',target[1]<0?'front':target[1]>0?'back':'',target[0]<0?'left':target[0]>0?'right':''].filter(Boolean).join(' ');return words[0].toUpperCase()+words.slice(1)+' view';
}
