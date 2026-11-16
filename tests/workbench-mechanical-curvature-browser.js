async(page,options={})=>{
 const origin=options.origin,previous=page.url(),checks=[];
 const id=(await(await page.request.post(origin+'/api/workbench/projects',{data:{title:'Native curvature acceptance',spec:{name:'curve_analysis',board:{width_mm:40,height_mm:30,layers:2},components:[],nets:[]}}})).json()).id;
 let failed=false;
 try{
  const builtResponse=await page.request.post(origin+`/api/workbench/projects/${id}/mechanical/build`,{data:{path:'cad/curve.cad.json',program:{schema:1,name:'Circular edge reference',units:'mm',parameters:{},features:[{id:'body',op:'cylinder',radius:4,height:3}],result:'body'}}});
  if(!builtResponse.ok())throw Error(await builtResponse.text());const built=await builtResponse.json();
  const state=async()=>{const value=(await(await page.request.get(origin+'/api/projects/'+id)).json()).state;return {spec:value.spec,version:value.workbench.version,models:value.workbench_mechanical,history:value.mechanical_history};},before=await state();
  await page.goto(origin+'/?curvature-qa='+Date.now()+'#'+id);await page.getByRole('tab',{name:'3D View',exact:true}).click();await page.locator('#mechanicalPartStatus').filter({hasText:'8.00'}).waitFor();await page.locator('#cameraOptions').click();
  const toggle=page.getByRole('button',{name:'Curvature combs',exact:true});await toggle.waitFor({timeout:2500});if(await toggle.isDisabled())throw Error('Native edge curvature was not available in Analysis');await toggle.click();
  await page.locator('#cadCombGain').fill('40');await page.locator('#cadCombGain').dispatchEvent('input');await page.locator('#cadCombDensity').selectOption('4');
  if(!/0\.25/.test(await page.locator('#cadCombStatus').innerText()))throw Error('Curvature summary did not use the actual R4 circle');
  await page.screenshot({path:options.artifactDir+'/curvature-analysis.png'});checks.push('Analysis exposes working native curvature gain, density and numerical range');
  await page.reload();await page.locator('#mechanicalPartStatus').filter({hasText:'8.00'}).waitFor();await page.locator('#cameraOptions').click();
  if(await toggle.getAttribute('aria-pressed')!=='true'||await page.locator('#cadCombGain').inputValue()!=='40'||await page.locator('#cadCombDensity').inputValue()!=='4')throw Error('Curvature controls did not survive reload');
  if(JSON.stringify(before)!==JSON.stringify(await state()))throw Error('View analysis changed saved mechanical or electronic design');
  checks.push('Curvature preferences survive reload without publishing a source, model or history revision');
  await page.setViewportSize({width:390,height:844});if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth))throw Error('Curvature pane overflows mobile');await page.screenshot({path:options.artifactDir+'/curvature-mobile.png'});await toggle.click();if(await toggle.getAttribute('aria-pressed')!=='false')throw Error('Mobile curvature toggle did not clear');
  checks.push('Compact Analysis controls remain usable and disabling restores the normal view');return{checks,asset:built.asset_id};
 }catch(error){failed=true;await page.screenshot({path:options.artifactDir+'/failure-before-cleanup.png'});throw error;}
 finally{await page.setViewportSize({width:1440,height:1000});await page.goto(previous);if(!failed)await page.request.delete(origin+'/api/projects/'+id);}
}
