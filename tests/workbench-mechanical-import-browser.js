async(page,options={})=>{
 const origin=options.origin,previous=page.url(),checks=[];
 const made=await(await page.request.post(origin+'/api/workbench/projects',{data:{title:'CAD import acceptance',spec:{name:'cad_import',board:{width_mm:40,height_mm:30,layers:2},components:[],nets:[]}}})).json(),id=made.id;
 let failed=false;
 let holdIdle=true,releaseIdle;await page.routeWebSocket('**/api/projects/'+id+'/ws*',socket=>{const server=socket.connectToServer();server.onMessage(raw=>{const event=JSON.parse(raw);if(holdIdle&&event.type==='status'&&event.status==='idle'){releaseIdle=()=>socket.send(raw);return;}socket.send(raw);});});
 const state=async()=>(await(await page.request.get(origin+'/api/projects/'+id)).json()).state;
 try{
  await page.goto(origin+'/?cad-import-qa='+Date.now()+'#'+id);await page.getByRole('tab',{name:'3D View',exact:true}).click();
  await page.getByRole('button',{name:'Import CAD',exact:true}).click({timeout:3000});
  await page.locator('#cadAssetFiles').setInputFiles(options.cadFixtures+'/colored_assembly.step');
  await page.locator('#cadAssetBodyList label').filter({hasText:'Blue bracket'}).waitFor({timeout:15000});
  if(await page.locator('#cadAssetBodyList input:checked').count()!==3)throw Error('All three native bodies must be selected');
  await page.locator('#cadAssetPreview canvas').waitFor();
  await page.locator('#cadAssetsClose:not([disabled])').waitFor();
  if(!releaseIdle)throw Error('Expected the upload completion status to be held');holdIdle=false;releaseIdle();await page.locator('#cadAssetCreate:not([disabled])').waitFor({timeout:3000});
  checks.push('A delayed idle notification reenables import actions without reopening the dialog');
  await page.screenshot({path:options.artifactDir+'/cad-import-preview.png'});
  checks.push('STEP import opens native preview with three separately named and colored bodies');
  const inventory=await(await page.request.get(origin+`/api/workbench/projects/${id}/mechanical/assets`)).json(),original=inventory.assets[0];
  const originalBefore=await(await page.request.get(origin+original.original.url)).body();
  await page.locator('#cadAssetBodyList label').filter({hasText:'Red spacer B'}).locator('input').uncheck();
  await page.getByLabel('CAD source path',{exact:true}).fill('cad/imported.cad.json');
  const built=page.waitForResponse(r=>r.url().endsWith('/mechanical/assets/part')&&r.request().method()==='POST');
  await page.getByRole('button',{name:'Create editable part',exact:true}).click();const firstResponse=await built;if(!firstResponse.ok())throw Error(await firstResponse.text());const first=await firstResponse.json();
  await page.locator('#mechanicalPartStatus').filter({hasText:'Verified solid'}).waitFor({timeout:10000});
  if(first.metrics.solids!==2||first.metrics.bodies.some(b=>b.name==='Red spacer B'))throw Error('Body selection did not reach native modeling');
  checks.push('Selected bodies create an editable native model at a new source path');
  await page.getByRole('button',{name:'Edit CAD code',exact:true}).click();await page.locator('#editTextFile').click();await page.locator('#fileEditor').waitFor({state:'visible'});
  const code=JSON.parse(await page.locator('#fileEditor').inputValue());code.parameters.diameter={value:3.2,unit:'mm'};code.features.push({id:'drilled',op:'hole',target:code.result,diameter:'diameter',depth:6,origin:[17,16,1]});code.result='drilled';
  await page.locator('#fileEditor').fill(JSON.stringify(code,null,2));const saved=page.waitForResponse(r=>r.url().includes('/text/cad/imported.cad.json')&&r.request().method()==='PUT');await page.locator('#saveTextFile').click();if(!(await saved).ok())throw Error('CAD source save failed');await page.waitForFunction(()=>document.querySelector('#fileDraftStatus')?.textContent==='');
  const rebuilding=page.waitForResponse(r=>r.url().endsWith('/mechanical/build')&&r.request().method()==='POST');await page.locator('#buildCADSource').click();const response=await rebuilding;if(!response.ok())throw Error(await response.text());const edited=await response.json();await page.locator('#mechanicalPartStatus').filter({hasText:'Verified solid'}).waitFor();
  if(edited.metrics.solids!==2||Math.abs(first.metrics.volume_mm3-edited.metrics.volume_mm3-Math.PI*1.6**2*4)>1e-5||!edited.metrics.step_metadata_verified)throw Error('Drilling or native STEP metadata roundtrip failed');
  const originalAfter=await(await page.request.get(origin+original.original.url)).body();if(!originalBefore.equals(originalAfter))throw Error('Editing changed the original CAD file');
  checks.push('Imported BRep can be drilled, rebuilt and exported with original bytes retained');
  await page.screenshot({path:options.artifactDir+'/cad-import-edited.png'});
  await page.getByRole('button',{name:'Undo CAD change',exact:true}).click();await page.locator('#mechanicalPartStatus').filter({hasText:'Source changed'}).waitFor();await page.getByRole('button',{name:'Redo CAD change',exact:true}).click();await page.locator('#mechanicalPartStatus').filter({hasText:'Verified solid'}).waitFor();
  checks.push('Imported-model Undo and Redo reuse the saved native revisions');
  await page.reload();await page.locator('#mechanicalPartStatus').filter({hasText:'Verified solid'}).waitFor();await page.setViewportSize({width:390,height:844});await page.getByRole('button',{name:'Import CAD',exact:true}).click();await page.locator('#cadAssetList button').filter({hasText:'colored_assembly.step'}).click();await page.locator('#cadAssetBodyList').filter({hasText:'Blue bracket'}).waitFor();
  const fit=await page.locator('#cadAssetsDialog').evaluate(el=>({width:el.getBoundingClientRect().width,viewport:innerWidth}));if(fit.width>fit.viewport)throw Error('CAD asset manager overflows mobile viewport');
  checks.push('Imported originals and body inventory survive reload and fit mobile width');
  await page.locator('#cadAssetsClose').click();const after=await state();if(after.workbench.version!==1||after.workbench_native||after.runtime.engine_busy)throw Error('CAD import changed the electrical design or left an operation running');
  return{checks,project:id,asset_id:original.asset_id};
 }catch(error){failed=true;await page.screenshot({path:options.artifactDir+'/import-failure-before-cleanup.png'});throw error;}
 finally{await page.setViewportSize({width:1440,height:1000});await page.goto(previous);if(!failed)await page.request.delete(origin+'/api/projects/'+id);}
}
