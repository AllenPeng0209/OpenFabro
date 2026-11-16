async(page,options={})=>{
 const origin=options.origin||'http://127.0.0.1:8770',checks=[],references=[],tasks=[];let pid,release;const old=(await(await page.request.get(origin+'/api/config')).json()).ai;
 const key=async(...keys)=>{await page.locator('#viewContent').focus();for(const value of keys)await page.keyboard.press(value);};
 const enter=async()=>{await page.locator('#markupButton:not([disabled])').click();await page.locator('#canvasMarkup').waitFor();};
 const send=async text=>{await page.locator('#chatInput').fill(text);await page.locator('#chatForm button[type="submit"]').click();await page.locator('#canvasMarkup').waitFor({state:'detached'});await Promise.all(tasks);return references.at(-1);};
 page.on('response',response=>{if(response.url().endsWith('/canvas-reference')&&response.ok())tasks.push(response.json().then(ref=>references.push(ref)));});
 try{
  await page.request.post(origin+'/api/config',{data:{ai:{provider:'codex',vision:'auto'}}});
  const made=await page.request.post(origin+'/api/workbench/projects',{data:{title:'Frozen canvas layers',spec:options.layerFixture}});if(!made.ok())throw Error(await made.text());pid=(await made.json()).id;
  await page.route('**/api/workbench/codex/status',route=>route.fulfill({json:{ready:true}}));await page.route(`**/api/workbench/projects/${pid}/codex`,route=>route.fulfill({json:{ok:true}}));
  await page.goto(origin+'/#'+pid);await page.getByRole('tab',{name:'Layout',exact:true}).click();await page.locator('#nativeBoard[data-updating="false"] canvas').waitFor();
  const geometry=(await(await page.request.get(origin+`/api/workbench/projects/${pid}/layout-geometry`)).json());
  await page.getByRole('button',{name:'Layers',exact:true}).click();await key('l','m');await page.locator('#nativeBoard[data-native-layer-f-mask="ready"]').waitFor();
  await page.getByRole('button',{name:'Objects',exact:true}).click();await page.locator('[data-tree-id="component:R2"] [data-tree-visibility]').click();await page.locator('#nativeBoard[data-native-layer-f-mask="ready"]').waitFor();await page.locator('#closeDrawer').click();
  await enter();const ready=await send('Review the frozen mask and copper');
  if(ready.display_context?.focus!=='F.Mask'||ready.display_context.native.pcb_sha256!==geometry.pcb_sha256)throw Error('The real PCB markup discarded its layer/source context');
  const mask=ready.display_context.apertures.find(a=>a.layer==='F.Mask');if(mask.status!=='ready'||mask.client_path_count!==2||!/^[a-f0-9]{64}$/.test(mask.svg_sha256)||!ready.display_context.layers['B.Cu'].visible)throw Error('Capture did not distinguish verified F.Mask vectors from visible bottom copper');
  checks.push('A real marked PCB carries focused mask, visible copper and committed native SVG identity');
  const r2=geometry.geometry.footprints.find(f=>f.ref==='R2');if(!ready.display_context.hidden_objects.footprints.includes(r2.id))throw Error('The capture lost personal object hiding');checks.push('Personal hidden native objects are frozen with the image without saving the design');
  await page.getByRole('button',{name:'Objects',exact:true}).click();await page.locator('[data-tree-id="component:R2"] [data-tree-visibility]').click();await page.locator('#closeDrawer').click();
  let started;const start=new Promise(r=>started=r),gate=new Promise(r=>release=r);const pattern=url=>url.pathname.includes(`/projects/${pid}/`)&&url.pathname.includes('/B-Paste-')&&url.pathname.endsWith('/layer.svg');
  await page.route(pattern,async route=>{const response=await route.fetch();started();await gate;await route.fulfill({response});});
  await key('l','Shift+KeyP');await Promise.race([start,new Promise((_,reject)=>setTimeout(()=>reject(Error('Delayed paste fixture did not start')),10000))]);await enter();release();await page.locator('#nativeBoard[data-native-layer-b-paste="waiting"]').waitFor();
  const pending=await send('Explain the captured loading state');if(pending.display_context?.apertures.find(a=>a.layer==='B.Paste')?.status!=='loading')throw Error('Send read a newer waiting/ready state instead of the capture-time loading state');
  checks.push('A native SVG resolving after capture cannot relabel that frozen loading image at send time');
  await page.unroute(pattern);await key('l','Digit4');const historical=await(await page.request.get(origin+pending.url.replace('.png','.json'))).json();if(historical.display_context.focus!=='B.Paste'||historical.display_context.apertures.find(a=>a.layer==='B.Paste').status!=='loading')throw Error('Later focus/loading completion changed the historical image context');
  checks.push('Later focus and native completion leave stored image context unchanged');
  const project=(await(await page.request.get(origin+'/api/projects/'+pid)).json()).state;if(project.workbench.version!==1)throw Error('Image context saved a physical design edit');
  if(options.artifactDir)await page.screenshot({path:options.artifactDir+'/frozen-canvas-context.png'});return{checks};
 }finally{release?.();await page.unrouteAll({behavior:'ignoreErrors'});await page.request.post(origin+'/api/config',{data:{ai:{provider:old.provider,vision:old.vision||'auto'}}});if(pid)await page.request.delete(origin+'/api/projects/'+pid);}
}
