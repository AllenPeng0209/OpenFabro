// Native identities come from the sealed scene; display triangles never invent CAD surfaces.
const bodyFor=(data,id)=>data.topology?.schema===1?data.topology.bodies.find(body=>body.body_id===id):null;
const picked=(body,item,entity)=>body&&item?{...structuredClone(item),body_id:body.body_id,member_id:body.member_id,label:body.label,entity}:null;

export function nativeFace(data,mesh,triangle){
 const body=bodyFor(data,mesh.body_id);if(!body||!Number.isInteger(triangle)||triangle<0)return null;
 const range=mesh.face_ranges?.find(([index,start,count])=>triangle>=start&&triangle<start+count);
 return range?picked(body,body.faces.find(face=>face.index===range[0]),'face'):null;
}
export function nativeEdge(data,bodyId,index){const body=bodyFor(data,bodyId);return picked(body,body?.edges.find(edge=>edge.index===index),'edge');}

export function nearestSegment(point,vertices,tolerance=7){
 let closest=null;
 for(let i=0;i+5<vertices.length;i+=6){const[x,y,z,a,b,c]=vertices.slice(i,i+6),dx=a-x,dy=b-y,length=dx*dx+dy*dy;if(length<1e-12)continue;const t=Math.max(0,Math.min(1,((point[0]-x)*dx+(point[1]-y)*dy)/length)),hit=[x+t*dx,y+t*dy],distance=Math.hypot(point[0]-hit[0],point[1]-hit[1]),depth=z+t*(c-z);if(distance<=tolerance&&(!closest||distance<closest.distance||distance===closest.distance&&depth>closest.depth))closest={distance,depth,point:hit};}
 return closest;
}

export function appendPickedMate(program,{type,moving,reference,offset=0,flip=type==='coincident'}){
 const assembly=program.features.find(feature=>feature.id===program.result&&feature.op==='assembly');if(!assembly)throw Error('Choose an assembly before adding a mate.');
 if(!moving?.selector||!reference?.selector)throw Error('Choose two supported native references.');
 if(!assembly.members.includes(moving.member_id)||!assembly.members.includes(reference.member_id)||moving.member_id===reference.member_id)throw Error('Choose references on two different assembly parts.');
 if((assembly.fixed||assembly.members.slice(0,1)).includes(moving.member_id))throw Error('The moving part is fixed. Choose a movable part.');
 const kinds=[moving.selector.kind,reference.selector.kind];
 if(type==='coincident'&&kinds.some(kind=>kind!=='plane'))throw Error('Choose two planar faces for a coincident mate.');
 if(type==='concentric'&&kinds.some(kind=>kind!=='axis'))throw Error('Choose cylinder faces or circular edges for a concentric axis.');
 if(!['coincident','concentric','aligned','offset'].includes(type)||!Number.isFinite(offset)||Math.abs(offset)>10000)throw Error('Choose a mate type and a finite offset.');
 const next=structuredClone(program),target=next.features.find(f=>f.id===next.result);next.parameters||={};let serial=1;while(Object.hasOwn(next.parameters,'mate_offset_'+serial))serial++;const parameter='mate_offset_'+serial;next.parameters[parameter]={value:offset,unit:'mm'};
 let id=1;while((target.mates||[]).some(mate=>mate.id==='picked_mate_'+id))id++;
 target.mates=[...(target.mates||[]),{id:'picked_mate_'+id,type,target:moving.member_id,reference:reference.member_id,target_anchor:structuredClone(moving.selector),reference_anchor:structuredClone(reference.selector),offset:parameter,flip}];return next;
}
