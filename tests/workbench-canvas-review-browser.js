async(page,options={})=>{
 const origin=options.origin||'http://127.0.0.1:8770',checks=[];let pid,uploads=0;const old=(await(await page.request.get(origin+'/api/config')).json()).ai;
 try{
  await page.request.post(origin+'/api/config',{data:{ai:{provider:'codex',vision:'auto'}}});
  const made=await page.request.post(origin+'/api/workbench/projects',{data:{title:'Canvas review regressions',spec:options.layerFixture}});if(!made.ok())throw Error(await made.text());pid=(await made.json()).id;
  await page.route('**/api/workbench/codex/status',route=>route.fulfill({json:{ready:true}}));await page.route(`**/api/workbench/projects/${pid}/codex`,route=>route.fulfill({json:{ok:true}}));await page.route(`**/api/workbench/projects/${pid}/canvas-reference`,route=>{uploads++;return route.continue();});
  await page.goto(origin+'/#'+pid);await page.locator('#viewContent svg.design-svg[data-schematic-hash]').waitFor();await page.locator('#markupButton:not([disabled])').click();await page.locator('#canvasMarkup').waitFor();await page.locator('#chatInput').fill('Keep this completed stroke');const box=await page.locator('#markupStrokes').boundingBox();await page.mouse.move(box.x+box.width*.3,box.y+box.height*.3);await page.mouse.down();await page.mouse.move(box.x+box.width*.4,box.y+box.height*.4,{steps:3});
  await page.evaluate(()=>document.querySelector('#chatForm').requestSubmit());await page.locator('#toastStack .toast').filter({hasText:'Finish the current markup stroke'}).waitFor({timeout:2000});if(uploads!==0||!await page.locator('#canvasMarkup').isVisible())throw Error('An unfinished stroke still produced an immutable image reference');
  await page.mouse.move(box.x+box.width*.5,box.y+box.height*.5,{steps:3});await page.mouse.up();await page.locator('#sendButton:not([disabled])').click();await page.locator('#canvasMarkup').waitFor({state:'detached'});if(uploads!==1)throw Error('Finishing and sending the retained stroke did not produce exactly one image');checks.push('Submitting during a held stroke preserves the draft and sends only after the completed stroke');
  const timing=await page.evaluate(async pid=>{
   const url=new URL('./workbench-markup.mjs',document.querySelector('script[src*="workbench.mjs"]').src),{MarkupUI}=await import(url.href),svg=document.querySelector('#viewContent svg.design-svg');let phase='before',ready,release;
   const started=new Promise(r=>ready=r),gate=new Promise(r=>release=r),original=HTMLImageElement.prototype.decode;HTMLImageElement.prototype.decode=function(){ready();return gate.then(()=>original.call(this));};
   const state={pid,version:1,generation:0,projectLoadToken:1,active:'schematic',canvas:{svg}},ui=new MarkupUI({state:()=>state,save:async()=>{},api:async()=>{},toast:()=>{},editable:()=>true,displayContext:()=>({phase})});
   try{const entering=ui.enter();await Promise.race([started,new Promise((_,reject)=>setTimeout(()=>reject(Error('SVG image decode did not start')),5000))]);phase='after';release();await entering;return{captured:ui.frame.displayContext.phase,live:phase};}finally{release();HTMLImageElement.prototype.decode=original;ui.cancel('user');}
  },pid);
  if(timing.captured!=='before'||timing.live!=='after')throw Error('SVG pixels were paired with metadata sampled after asynchronous decode: '+JSON.stringify(timing));checks.push('SVG metadata is frozen alongside the cloned pixels before delayed image decoding');
  return{checks};
 }finally{await page.mouse.up();await page.unrouteAll({behavior:'ignoreErrors'});await page.request.post(origin+'/api/config',{data:{ai:{provider:old.provider,vision:old.vision||'auto'}}});if(pid)await page.request.delete(origin+'/api/projects/'+pid);}
}
