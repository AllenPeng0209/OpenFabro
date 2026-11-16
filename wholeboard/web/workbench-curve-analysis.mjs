// Curvature is evaluated by the native CAD kernel. This module only scales the
// saved derivatives into display segments; it never fits the tessellation.
export function curvatureComb(data,{gain=20,density=1}={}){
 gain=Number.isFinite(gain)?Math.max(0,Math.min(200,gain)):20;
 density=Number.isFinite(density)?Math.max(1,Math.min(16,Math.round(density))):1;
 const bodies=[];let availableEdges=0,unavailableEdges=0,teeth=0,minimum=Infinity,maximum=0;
 for(const body of data.topology?.bodies||[]){
  const positions=[];
  for(const edge of body.edges||[]){
   const curve=edge.curvature;
   if(!curve?.available||!Array.isArray(curve.samples)){unavailableEdges++;continue;}
   availableEdges++;
   for(let i=0;i<curve.samples.length;i++){
    const sample=curve.samples[i];
    if(!sample||!Number.isFinite(sample.curvature)||sample.curvature<0)continue;
    minimum=Math.min(minimum,sample.curvature);maximum=Math.max(maximum,sample.curvature);
    if(i%density||!gain||sample.curvature<=1e-12)continue;
    const valid=key=>Array.isArray(sample[key])&&sample[key].length===3&&sample[key].every(Number.isFinite);
    if(!valid('point')||!valid('normal'))continue;
    const end=sample.point.map((value,j)=>value+sample.normal[j]*sample.curvature*gain);
    if(!end.every(Number.isFinite))continue;
    positions.push(...sample.point,...end);teeth++;
   }
  }
  if(positions.length)bodies.push({bodyId:body.body_id,memberId:body.member_id,positions});
 }
 return{available:availableEdges>0,availableEdges,unavailableEdges,teeth,minimum:Number.isFinite(minimum)?minimum:null,maximum:availableEdges?maximum:null,bodies};
}

export function curvatureEvents(data,{inflections=false,jumps=false}={}){
 const markers=[],seen=new Set();let analyzedEdges=0,incompleteEdges=0,inflectionEdges=0,jumpEdges=0,inflectionCount=0,jumpCount=0;
 for(const body of data.topology?.bodies||[]){
  const rows=[];
  for(const edge of body.edges||[]){const analysis=edge.curve_events;if(analysis?.available)analyzedEdges++;if(!analysis?.complete)incompleteEdges++;if(analysis?.inflections_available)inflectionEdges++;if(analysis?.jumps_available)jumpEdges++;for(const event of analysis?.events||[])rows.push({...event,edgeIndex:edge.index});}
  rows.push(...(body.curve_events?.events||[]));
  for(const event of rows){
   if(!['inflection','curvature_jump'].includes(event.kind)||!Array.isArray(event.point)||event.point.length!==3||!event.point.every(Number.isFinite))continue;
   const key=body.body_id+':'+event.kind+':'+event.point.map(n=>Math.round(n*1e7)).join(',');if(seen.has(key))continue;seen.add(key);
   if(event.kind==='inflection')inflectionCount++;else jumpCount++;
   if(event.kind==='inflection'?!inflections:!jumps)continue;
   markers.push({...event,bodyId:body.body_id,memberId:body.member_id});
  }
 }
 return{available:analyzedEdges>0,analyzedEdges,incompleteEdges,inflectionEdges,jumpEdges,inflectionCount,jumpCount,markers};
}
