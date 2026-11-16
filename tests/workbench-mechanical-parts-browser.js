async(page,options={})=>{
 const origin=options.origin||'http://127.0.0.1:8770',previous=page.url(),checks=[];
 const made=await(await page.request.post(origin+'/api/workbench/projects',{data:{title:'Editable mechanical modeling',spec:{name:'mechanical_first',board:{width_mm:40,height_mm:30,layers:2},components:[],nets:[]}}})).json(),id=made.id;
 try{
  await page.goto(origin+'/?mechanical-parts-qa='+Date.now()+'#'+id);
  await page.getByRole('tab',{name:'3D View',exact:true}).click();
  await page.getByRole('button',{name:'New mechanical part',exact:true}).waitFor({timeout:5000});
  await page.getByRole('button',{name:'New mechanical part',exact:true}).click();
  await page.getByLabel('Part name',{exact:true}).fill('Mounting plate');
  const created=page.waitForResponse(r=>r.url().endsWith('/mechanical/build')&&r.request().method()==='POST');
  await page.getByRole('button',{name:'Create part',exact:true}).click();
  const response=await created;if(!response.ok())throw Error(await response.text());const first=await response.json();
  await page.locator('#mechanicalPartStatus').filter({hasText:'Verified solid'}).waitFor();
  if(first.metrics.solids!==1||!first.metrics.step_roundtrip.valid)throw Error('No exact native solid');
  checks.push('Creating a mechanical-only part writes editable CAD and builds a real FreeCAD solid with STEP roundtrip proof');
  const old={};for(const f of first.files){const raw=await(await page.request.get(origin+f.url)).body();old[f.path]=raw.toString('base64');}
  await page.getByRole('button',{name:'Parameters',exact:true}).click();
  await page.getByLabel('thickness (mm)',{exact:true}).fill('6');
  const updated=page.waitForResponse(r=>r.url().endsWith('/mechanical/build')&&r.request().method()==='POST');
  await page.getByRole('button',{name:'Rebuild part',exact:true}).click();
  const update=await updated;if(!update.ok())throw Error(await update.text());const second=await update.json();
  await page.locator('#mechanicalPartStatus').filter({hasText:'Verified solid'}).waitFor();
  if(second.metrics.size_mm[2]!==6||second.asset_id===first.asset_id)throw Error('Parameters did not rebuild a new asset');
  for(const f of first.files)if((await(await page.request.get(origin+f.url)).body()).toString('base64')!==old[f.path])throw Error('An earlier model changed');
  checks.push('Parameter edits rebuild a new exact model and retain every original model file byte');
  await page.getByRole('combobox',{name:'Model version',exact:true}).selectOption(first.asset_id);
  await page.locator('#mechanicalPartStatus').filter({hasText:'Earlier model'}).waitFor();
  await page.getByRole('combobox',{name:'Model version',exact:true}).selectOption(second.asset_id);
  await page.locator('#mechanicalPartStatus').filter({hasText:'Verified solid'}).waitFor();
  checks.push('Earlier and current native model assets remain independently viewable');
  await page.getByRole('button',{name:'Edit CAD code',exact:true}).click();
  await page.locator('#fileViewName').filter({hasText:second.source}).waitFor();
  await page.locator('#editTextFile').click();
  await page.locator('#fileEditor').waitFor({state:'visible'});
  const code=JSON.parse(await page.locator('#fileEditor').inputValue());code.parameters.thickness.value=8;
  await page.locator('#fileEditor').fill(JSON.stringify(code,null,2));const savedCode=page.waitForResponse(r=>r.url().includes('/text/')&&r.request().method()==='PUT');await page.locator('#saveTextFile').click();if(!(await savedCode).ok())throw Error('Could not save the CAD edit');await page.waitForFunction(()=>document.querySelector('#fileDraftStatus')?.textContent==='');
  await page.getByRole('tab',{name:'3D View',exact:true}).click();
  await page.locator('#mechanicalPartStatus').filter({hasText:'Source changed'}).waitFor();
  const rebuilt=page.waitForResponse(r=>r.url().endsWith('/mechanical/build')&&r.request().method()==='POST');
  await page.getByRole('button',{name:'Rebuild from code',exact:true}).click();const lastResponse=await rebuilt;if(!lastResponse.ok())throw Error(await lastResponse.text());const third=await lastResponse.json();
  await page.locator('#mechanicalPartStatus').filter({hasText:'Verified solid'}).waitFor();
  if(third.metrics.size_mm[2]!==8)throw Error('Saved editable CAD was not rebuilt');
  checks.push('Direct Files edits mark the displayed model stale until the current saved code is rebuilt');
  const toolbarFit=await page.locator('.mechanical-part-tools button,.mechanical-part-tools select,.mechanical-part-tools>a,.mechanical-part-tools summary').evaluateAll(nodes=>nodes.filter(n=>!n.disabled&&n.getBoundingClientRect().width).map(n=>{const b=n.getBoundingClientRect(),hit=document.elementFromPoint(b.x+b.width/2,b.y+b.height/2);return{label:n.textContent||n.getAttribute('aria-label'),own:hit===n||n.contains(hit)};}));
  if(toolbarFit.some(t=>!t.own))throw Error('Mechanical toolbar is obscured by navigation: '+JSON.stringify(toolbarFit));
  const overlaps=await page.evaluate(()=>{const nav=document.querySelector('#cadNavigation').getBoundingClientRect();return [...document.querySelectorAll('.mechanical-part-tools>button,.mechanical-part-tools>select,.mechanical-part-tools>a,.mechanical-part-tools>details')].filter(n=>{const b=n.getBoundingClientRect();return b.width&&b.left<nav.right&&b.right>nav.left&&b.top<nav.bottom&&b.bottom>nav.top;}).map(n=>n.textContent);});
  if(overlaps.length)throw Error('Mechanical controls visually overlap the navigation cube: '+JSON.stringify(overlaps));
  checks.push('Mechanical editing and export hit targets remain separate from the navigation cube');
  const downloadPromise=page.waitForEvent('download');await page.locator('#mechanicalStepDownload').click();const download=await downloadPromise;if(!download.suggestedFilename().endsWith('.step'))throw Error('No STEP download');
  checks.push('Exact STEP export is downloadable from the modeled part');
  const codeState=await(await page.request.get(origin+`/api/workbench/projects/${id}/text/`+third.source)).json(),external=JSON.parse(codeState.content);external.parameters.thickness.value=10;
  const agentBuild=await page.request.post(origin+`/api/workbench/projects/${id}/mechanical/build`,{data:{path:third.source,program:external,expected_sha256:codeState.sha}});if(!agentBuild.ok())throw Error(await agentBuild.text());const fourth=await agentBuild.json();
  await page.locator('#mechanicalPartStatus').filter({hasText:'Verified solid'}).filter({hasText:'10.00 mm'}).waitFor({timeout:5000});
  checks.push('An Agent-equivalent server build updates the current model without a manual tab switch');
  await page.screenshot({path:options.artifactDir+'/editable-mechanical-desktop.png'});
  await page.setViewportSize({width:390,height:844});
  await page.getByRole('button',{name:'Parameters',exact:true}).click();
  const fit=await page.locator('#mechanicalParametersDialog input,#mechanicalParametersDialog button').evaluateAll(nodes=>nodes.filter(n=>n.getBoundingClientRect().width).every(n=>{const b=n.getBoundingClientRect(),hit=document.elementFromPoint(b.x+b.width/2,b.y+b.height/2);return b.x>=0&&b.right<=innerWidth&&b.y>=0&&b.bottom<=innerHeight&&(hit===n||n.contains(hit));}));
  if(!fit||await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth))throw Error('Mobile mechanical parameters overlap');
  await page.screenshot({path:options.artifactDir+'/editable-mechanical-mobile.png'});await page.getByRole('button',{name:'Cancel',exact:true}).click();
  checks.push('Mobile parameter controls fit and cancellation does not change the model');
  await page.locator('.navigation-toggle').click();
  const expandedFit=await page.locator('.mechanical-part-tools button,.mechanical-part-tools select,.mechanical-part-tools>a,.mechanical-part-tools summary').evaluateAll(nodes=>nodes.filter(n=>!n.disabled&&n.getBoundingClientRect().width).map(n=>{const b=n.getBoundingClientRect(),hit=document.elementFromPoint(b.x+b.width/2,b.y+b.height/2);return{label:n.textContent,inside:b.x>=0&&b.right<=innerWidth&&b.y>=0&&b.bottom<=innerHeight,own:hit===n||n.contains(hit)};}));
  if(!expandedFit.length||expandedFit.some(n=>!n.inside||!n.own))throw Error('Expanded mobile navigation obscures mechanical controls: '+JSON.stringify(expandedFit));
  await page.locator('.navigation-toggle').click();checks.push('Expanded mobile navigation keeps all mechanical controls reachable');
  let release,arrive;const held=new Promise(r=>release=r),arrival=new Promise(r=>arrive=r);let reads=0;
  const sourcePattern='**/api/workbench/projects/'+id+'/text/'+fourth.source;
  await page.route(sourcePattern,async route=>{if(route.request().method()==='GET'){reads++;arrive();await held;}await route.continue();});
  try{const clicked=page.getByRole('button',{name:'Parameters',exact:true}).dblclick();await arrival;await clicked;release();await page.locator('#mechanicalParametersDialog[open]').first().waitFor({timeout:5000});await page.waitForTimeout(150);const dialogs=await page.locator('#mechanicalParametersDialog[open]').count();if(dialogs!==1||reads!==1)throw Error('Repeated parameter clicks opened overlapping requests/dialogs: '+JSON.stringify({reads,dialogs}));await page.getByRole('button',{name:'Cancel',exact:true}).click();}
  finally{release();await page.unroute(sourcePattern);}
  checks.push('Rapid parameter clicks share one pending source read and one dialog');
  const state=(await(await page.request.get(origin+'/api/projects/'+id)).json()).state;
  if(state.workbench.version!==1||JSON.stringify(state.spec)!==JSON.stringify(made.spec)||state.workbench_native)throw Error('Mechanical authoring changed electronics');
  checks.push('The complete mechanical authoring flow preserves source version1 and generates no electrical native files');
  return{checks,project:id,assets:[first.asset_id,second.asset_id,third.asset_id,fourth.asset_id],triangles:fourth.metrics.triangles};
 }finally{await page.setViewportSize({width:1440,height:1000});await page.goto(previous);await page.request.delete(origin+'/api/projects/'+id);}
}
