async(page,options={})=>{
 const checks=[];
 const result=await page.evaluate(async()=>{
  const prefix=new URL(document.querySelector('script[src*="workbench.mjs"]').src).pathname.replace(/workbench\.mjs.*$/,'');
  const {CADView}=await import(prefix+'workbench-cad.mjs');
  const host=document.createElement('div');host.style.cssText='position:fixed;left:0;top:0;width:500px;height:400px;z-index:9999';document.body.append(host);
  const triangle=(name,group,side,z)=>({name,group,side,component_id:group==='parts'?'module':'pcb',color:'#99aabb',v:[0,0,z,10,0,z,0,10,z],t:[0,1,2]});
  const data={size:[10,10,4],meshes:[{...triangle('PCB','board',null,1),opacity:.4,roughness:.2,metalness:0,alpha_test:.3},{...triangle('R1','parts','top',3),opacity:.4,transparent:false,alpha_test:.5},triangle('R2','parts','bottom',0),triangle('Unknown STEP body','parts',null,2)]};
  let view;
  try{
   view=new CADView(host,data);view.show.top=false;view.draw();const top=view.meshes.map(m=>m.visible);view.show.bottom=false;view.draw();const both=view.meshes.map(m=>m.visible);view.show.parts=false;view.draw();const parts=view.meshes.map(m=>m.visible);
   view.showGrid=false;view.draw();const off=view.grid?.visible;view.showGrid=true;view.draw();const on=view.grid?.visible;
   view.style='xray';view.projection='perspective';view.sectionAxis='z';view.sectionDepth=2;view.draw();const material=view.meshes[0].material;
   const gpu={top,both,parts,gridOff:off,gridOn:on,transparent:material.transparent,opacity:material.opacity,perspective:view.camera.isPerspectiveCamera,clipping:material.clippingPlanes[0]?.distanceToPoint({x:0,y:0,z:0})};
   view.style='solid';view.draw();gpu.restoredPaint={opacity:material.opacity,roughness:material.roughness,metalness:material.metalness,transparent:material.transparent,alphaTest:material.alphaTest};
   const mask=view.meshes[1].material;gpu.restoredMask={opacity:mask.opacity,transparent:mask.transparent,alphaTest:mask.alphaTest};
   view.selectComponent('module');const selected=view.meshes.filter(m=>m.material.emissive.getHex()!==0).map(m=>m.name);gpu.assemblySelection=selected;view.destroy();view=null;host.replaceChildren();const fallback=new window.MeshView(host,data);fallback.show.top=false;fallback.show.bottom=false;
   fallback.selectComponent?.('module');const selection=fallback.meshes.filter(m=>m.assemblySelected).map(m=>m.name);const software=typeof fallback.meshVisible==='function'?{top:fallback.meshVisible(data.meshes[1]),bottom:fallback.meshVisible(data.meshes[2]),board:fallback.meshVisible(data.meshes[0]),unknown:fallback.meshVisible(data.meshes[3])}:null;fallback.destroy();return{gpu,software,selection};
  }finally{view?.destroy();host.remove();}
 });
 if(JSON.stringify(result.gpu.top)!=='[true,false,true,true]'||JSON.stringify(result.gpu.both)!=='[true,false,false,true]'||JSON.stringify(result.gpu.parts)!=='[true,false,false,false]')throw Error('GPU side filters did not affect the actual matched component meshes: '+JSON.stringify(result));checks.push('GPU top/bottom filters hide only matched component bodies and retain PCB and unknown bodies');
 if(result.gpu.gridOff!==false||result.gpu.gridOn!==true)throw Error('Grid control is not connected to a real scene object');if(!result.gpu.transparent||result.gpu.opacity!==.24||!result.gpu.perspective||result.gpu.clipping!==0)throw Error('Material/projection/clipping no longer reach the actual GPU scene');checks.push('GPU grid, material, projection and clipping operate on actual render objects');
 if(JSON.stringify(result.gpu.restoredPaint)!=='{"opacity":0.4,"roughness":0.2,"metalness":0,"transparent":true,"alphaTest":0.3}')throw Error('Returning from xray discarded imported material properties');checks.push('Returning from xray preserves imported opacity and material properties');
 if(JSON.stringify(result.gpu.restoredMask)!=='{"opacity":0.4,"transparent":false,"alphaTest":0.5}')throw Error('Masked material was incorrectly turned into alpha blending');checks.push('Masked alpha cutoff remains distinct from blending after xray');
 if(JSON.stringify(result.software)!=='{"top":false,"bottom":false,"board":true,"unknown":true}')throw Error('Software fallback ignores side visibility');checks.push('Software fallback retains board and unresolved bodies while honoring side visibility');
 if(JSON.stringify(result.gpu.assemblySelection)!=='["R1","R2","Unknown STEP body"]'||JSON.stringify(result.selection)!==JSON.stringify(result.gpu.assemblySelection))throw Error('Assembly selection must highlight all bodies of one member in GPU and fallback');checks.push('Assembly selection highlights every body of one component in both rendering backends');
 return{checks,result};
}
