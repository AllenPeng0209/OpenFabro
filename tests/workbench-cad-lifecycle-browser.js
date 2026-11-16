async(page,options={})=>{
 const origin=options.origin||'http://127.0.0.1:8770',checks=[];
 const p=await(await page.request.post(origin+'/api/workbench/projects',{data:{title:'Controlled CAD replacement',example:true}})).json();
 const scene={size:[30,20,4],source:'controlled-mesh-fixture',meshes:[{name:'PCB',group:'board',color:'#88aabb',v:[0,0,0,30,0,0,0,20,0],t:[0,1,2]}]};
 const file=origin+`/api/projects/${p.id}/files/docs/controlled-scene.json`;
 let release,entered;const held=new Promise(r=>release=r),arrival=new Promise(r=>entered=r);
 await page.route('**/api/projects/'+p.id,async route=>{const response=await route.fetch(),data=await response.json();data.state.workbench_board3d={version:1,url:file};await route.fulfill({response,json:data});});
 await page.route(file,async route=>{entered();await held;await route.fulfill({json:scene});});
 try{
  await page.goto(origin+'/#'+p.id);await page.getByRole('tab',{name:'3D View',exact:true}).click();await arrival;await page.locator('#meshHost canvas').waitFor();
  await page.evaluate(()=>{const e=document.createElement('div');e.id='measureResult';e.textContent='Controlled previous model distance';document.querySelector('#viewContent').append(e);});
  release();await page.getByText('KiCad STEP geometry · 1 objects',{exact:true}).waitFor();const oldFeedback=await page.locator('#measureResult').count();
  await page.locator('[data-mesh=enclosure]').click();await page.locator('#cameraOptions').click();await page.locator('#cadMeasure').click();const measuring=await page.locator('#cadMeasure').getAttribute('aria-pressed'),explodeBlocked=await page.locator('#explodeSlider').isDisabled();await page.locator('#cadMeasure').click();const explodeReleased=await page.locator('#explodeSlider').isEnabled();
  if(oldFeedback)throw Error('Native replacement retained measurement feedback from the previous model; explode state '+JSON.stringify({measuring,explodeBlocked,explodeReleased}));checks.push('Controlled native model replacement removes feedback tied to the old geometry');
  if(measuring!=='true'||!explodeBlocked||!explodeReleased)throw Error('Measuring does not freeze and release the exploded view: '+JSON.stringify({measuring,explodeBlocked,explodeReleased}));checks.push('Measurement locks explosion until the user exits measurement mode');return{checks};
 }finally{release();await page.unroute(file);await page.unroute('**/api/projects/'+p.id);await page.request.delete(origin+'/api/projects/'+p.id);}
}
