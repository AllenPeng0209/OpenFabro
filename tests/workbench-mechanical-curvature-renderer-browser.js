async(page,options={})=>{
 const checks=[];
 try{
  await page.evaluate(async()=>{
   const script=new URL(document.querySelector('script[src*="workbench.mjs"]').src),{CADView}=await import(new URL('./workbench-cad.mjs',script));
   const host=document.createElement('div');host.style.cssText='position:fixed;left:20px;top:40px;width:600px;height:450px;z-index:9999';document.body.append(host);
   const samples=Array.from({length:65},(_,i)=>{const a=i*Math.PI*2/64;return{parameter:a,point:[10+4*Math.cos(a),10+4*Math.sin(a),2],normal:[-Math.cos(a),-Math.sin(a),0],tangent:[-Math.sin(a),Math.cos(a),0],curvature:.25};});
   const data={size:[20,20,3],origin:[100,200,0],meshes:[{name:'Cylinder',body_id:0,component_id:'cylinder',group:'mechanical',color:'#99aabb',v:[0,0,0,20,0,0,20,20,0,0,20,0],t:[0,1,2,0,2,3]}],topology:{schema:1,bodies:[{body_id:0,member_id:'cylinder',edges:[{index:0,curvature:{available:true,complete:true,samples}}]}]}};
   const view=new CADView(host,data);window.combFixture={view,host,data};view.explode=0;view.setViewDirection([0,0,1]);view.curvature={enabled:true,gain:8,density:1};view.draw();
   if(!view.combObjects?.length)throw Error('Native curvature combs are missing from the GPU scene');
   const comb=view.combObjects[0],positions=Array.from(comb.geometry.attributes.position.array);if(positions.length!==65*6||positions[0]!==14||positions[3]!==12)throw Error('GPU comb does not use native point/normal/curvature with the requested gain');
  });checks.push('GPU curvature teeth use native derivative samples in scene coordinates');
  const image1=await page.locator('.cad-canvas').last().screenshot();
  await page.evaluate(()=>{const v=window.combFixture.view;v.curvature={enabled:true,gain:12,density:4};v.draw();if(v.combObjects[0].geometry.attributes.position.count!==34)throw Error('Line density did not rebuild comb geometry');v.show.mechanical=false;v.draw();if(v.combObjects[0].visible)throw Error('Hidden model left a visible curvature comb');v.show.mechanical=true;v.sectionAxis='x';v.sectionDepth=10;v.draw();if(v.combObjects[0].material.clippingPlanes.length!==1)throw Error('Combs ignored cross section');v.sectionAxis='none';v.curvature.enabled=false;v.draw();if(v.combObjects[0].visible)throw Error('Disabling curvature left it visible');});
  const image2=await page.locator('.cad-canvas').last().screenshot();if(image1.equals(image2))throw Error('Comb toggle did not change real rendered pixels');checks.push('Density, model visibility, clipping and disable control actual GPU comb geometry');
  await page.screenshot({path:options.artifactDir+'/curvature-renderer.png'});return{checks};
 }catch(error){await page.screenshot({path:options.artifactDir+'/failure-before-cleanup.png'});throw error;}
 finally{await page.evaluate(()=>{const f=window.combFixture;if(f){f.view.destroy();f.host.remove();delete window.combFixture;}});}
}
