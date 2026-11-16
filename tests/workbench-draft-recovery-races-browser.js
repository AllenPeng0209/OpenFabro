async(page,options={})=>{
 const {origin,artifactDir}=options,checks=[],ids=[];let failed=false,release=()=>{};
 const json=async response=>{if(!response.ok())throw Error(await response.text());return response.json();};
 const make=async title=>{const {id}=await json(await page.request.post(origin+'/api/workbench/projects',{data:{title,spec:{name:'durable_source',board:{width_mm:40,height_mm:30,layers:2},components:[],nets:[]}}}));ids.push(id);return id;};
 const text=async(id,path)=>json(await page.request.get(`${origin}/api/workbench/projects/${id}/text/${path}?allow_missing=true`));
 const write=async(id,path,content,sha=null)=>json(await page.request.put(`${origin}/api/workbench/projects/${id}/text/${path}`,{data:{content,base_sha:sha}}));
 const state=async id=>(await json(await page.request.get(`${origin}/api/projects/${id}`))).state;
 const open=async(id,path)=>{await page.goto(origin+'/#'+id);await page.locator('[data-view=files]').click();await page.locator('#fileCatalogScope').selectOption('all');await page.locator('#fileSearch').fill(path);await page.locator('[data-file-path="'+path+'"]').click();await page.locator('#editTextFile').click();await page.locator('#fileEditor').waitFor();};
 const review=async path=>{await page.locator('#reviewStoredDrafts').click();await page.locator('[data-draft-path="'+path+'"] [data-review-draft]').first().click();await page.locator('#applyRecoveredDraft').waitFor();};
 const apply=async()=>{await page.locator('#applyRecoveredDraft').click();await page.locator('#fileDraftReviewDialog').waitFor({state:'detached'});await page.locator('#fileEditor').waitFor();};
 const save=async(design=false)=>{const response=page.waitForResponse(r=>r.request().method()==='PUT'&&(design?r.url().endsWith('/design'):r.url().includes('/text/')));await page.locator('#saveTextFile').click();await json(await response);await page.waitForFunction(()=>document.querySelector('#fileDraftStatus')?.textContent==='');};
 const accept=d=>d.type()==='beforeunload'?d.accept():d.dismiss();page.on('dialog',accept);
 try{
  const id=await make('Durable source races'),path='docs/races.md',base='first\nsecond\nlast';await write(id,path,base);
  await open(id,path);await page.locator('#fileEditor').fill('LOCAL\nsecond\nlast');await page.reload();await review(path);
  const old=await text(id,path);await write(id,path,'first\nsecond\nPEER',old.sha);await page.locator('#applyRecoveredDraft').click();
  await page.locator('#fileDraftReviewDialog [role=status]').filter({hasText:'saved file changed again'}).waitFor();if((await text(id,path)).content!=='first\nsecond\nPEER')throw Error('Review wrote the saved file');await apply();
  if(await page.locator('#fileEditor').inputValue()!=='LOCAL\nsecond\nPEER')throw Error('Updated comparison did not use the newest saved file');await save();checks.push('A saved-file change during review requires another comparison and cannot be overwritten by stale Apply');

  let started;const arrived=new Promise(r=>started=r),gate=new Promise(r=>release=r),pattern=`**/api/workbench/projects/${id}/text/${path}`;
  await page.route(pattern,async route=>{if(route.request().method()!=='PUT')return route.continue();const response=await route.fetch();started();await gate;await route.fulfill({response});});
  await page.locator('#fileEditor').fill('ONE\nsecond\nPEER');await page.locator('#saveTextFile').click();await arrived;await page.locator('#fileEditor').fill('TWO\nsecond\nPEER');
  const response=page.waitForResponse(r=>r.request().method()==='PUT'&&r.url().includes('/text/'));release();await json(await response);await page.unroute(pattern);
  await page.locator('.toast').filter({hasText:'newer changes are still unsaved'}).waitFor();await page.reload();await review(path);if(await page.locator('[data-draft-conflict]').count())throw Error('A pending save did not update the newer draft base');await apply();
  if(await page.locator('#fileEditor').inputValue()!=='TWO\nsecond\nPEER'||(await text(id,path)).content!=='ONE\nsecond\nPEER')throw Error('Save completion cleared or prematurely saved newer input');await save();checks.push('A save response rebases later keystrokes and their durable snapshot without saving or clearing them');

  await page.locator('#fileEditor').fill('DURABLE BEFORE QUOTA\nsecond\nPEER');await page.evaluate(()=>{window.draftOriginalSet=Storage.prototype.setItem;Storage.prototype.setItem=function(k,v){if(k.startsWith('wb-file-draft:1:'))throw new DOMException('Full','QuotaExceededError');return window.draftOriginalSet.call(this,k,v);};});
  await page.locator('#fileEditor').fill('QUOTA\nsecond\nPEER');await page.locator('#fileDraftStorageStatus').filter({hasText:'only in this tab'}).waitFor();if(await page.locator('#fileEditor').inputValue()!=='QUOTA\nsecond\nPEER')throw Error('Storage failure lost editor content');await save();
  if(await page.locator('#fileDraftStorageStatus').isVisible())throw Error('Storage warning remains after the only draft was saved');await page.evaluate(()=>{Storage.prototype.setItem=window.draftOriginalSet;delete window.draftOriginalSet;});checks.push('Real browser quota failure retains the tab buffer, permits saving and clears the warning when no draft remains');

  const missing='docs/recreate.md';await write(id,missing,'saved\n');await open(id,missing);await page.locator('#fileEditor').fill('recovered\n');await page.reload();
  const config=await json(await page.request.get(origin+'/api/config')),fs=await import('node:fs/promises'),paths=await import('node:path');
  const root=paths.resolve(config.projects_dir);if(!root.includes('/.local/browser-checks-')||!root.endsWith('/editor/projects'))throw Error('Deletion fixture is not isolated');
  const project=(await fs.readdir(root)).filter(name=>name===id||name.startsWith(id+'-'));if(project.length!==1)throw Error('Own fixture project path is ambiguous');await fs.unlink(paths.join(root,project[0],missing));
  await review(missing);if(!await page.locator('#applyRecoveredDraft').isDisabled())throw Error('Deleted file recovery did not require confirmation');await page.locator('#confirmDraftRecreate').check();await apply();
  if((await text(id,missing)).exists!==false||await page.locator('#fileEditor').inputValue()!=='recovered\n')throw Error('Recovery recreated a deleted file before explicit Save');await save();if((await text(id,missing)).content!=='recovered\n')throw Error('Recovered virtual file could not be saved');checks.push('Deleted file recovery is explicit and creates the file only when Save is pressed');

  await open(id,'design.json');const initial=await state(id),local=structuredClone(initial.spec);local.name='recovered_name';await page.locator('#fileEditor').fill(JSON.stringify(local,null,2));await page.reload();
  const peer=structuredClone(initial.spec);peer.board.width_mm=46;await json(await page.request.put(`${origin}/api/workbench/projects/${id}/design`,{data:{base_version:initial.workbench.version,spec:peer}}));await review('design.json');
  if(await page.locator('[data-draft-conflict]').count())throw Error('Independent design edits became conflicts');await apply();const merged=JSON.parse(await page.locator('#fileEditor').inputValue());if(merged.name!=='recovered_name'||merged.board.width_mm!==46)throw Error('Recovered design lost an independent peer edit');await save(true);
  const final=await state(id);if(final.spec.name!=='recovered_name'||final.spec.board.width_mm!==46||final.workbench.version!==initial.workbench.version+2)throw Error('Recovered design bypassed the accepted current version');checks.push('Recovered design.json merges peer changes and saves through the normal version and Undo pipeline');
  const cycle='docs/save-base.md';await write(id,cycle,'first\nsecond\nlast');await open(id,cycle);await page.locator('#fileEditor').fill('SAVED FIRST\nsecond\nlast');await save();await page.locator('#fileEditor').fill('SAVED FIRST\nLOCAL SECOND\nlast');await page.reload();
  const cycleSaved=await text(id,cycle);await write(id,cycle,'PEER FIRST\nsecond\nlast',cycleSaved.sha);await review(cycle);if(await page.locator('[data-draft-conflict]').count())throw Error('A new edit after Save used the previous editor base and invented a conflict');await apply();if(await page.locator('#fileEditor').inputValue()!=='PEER FIRST\nLOCAL SECOND\nlast')throw Error('Save did not advance the next draft comparison base');await save();checks.push('Successive edits after Save use the newly accepted base and merge later independent peer edits');
  await open(id,path);await page.locator('#fileEditor').fill('TAB ONE\nsecond\nPEER');const other=await page.context().newPage();other.on('dialog',accept);
  try{
   await other.goto(origin+'/#'+id);await other.locator('[data-view=files]').click();await other.locator('#reviewStoredDrafts').click();await other.locator('[data-draft-path="'+path+'"] [data-review-draft]').first().click();await other.locator('#applyRecoveredDraft').waitFor();
   await page.locator('#fileEditor').fill('TAB TWO\nsecond\nPEER');await other.locator('#applyRecoveredDraft').click();await other.locator('#fileDraftReviewDialog [role=status]').filter({hasText:'draft changed in another tab'}).waitFor();
   await other.locator('#applyRecoveredDraft').click();await other.locator('#fileDraftReviewDialog').waitFor({state:'detached'});if(await other.locator('#fileEditor').inputValue()!=='TAB TWO\nsecond\nPEER'||(await text(id,path)).content!=='QUOTA\nsecond\nPEER')throw Error('Foreign-tab recovery applied an obsolete revision or wrote before Save');
   const response=other.waitForResponse(r=>r.request().method()==='PUT'&&r.url().includes('/text/'));await other.locator('#saveTextFile').click();await json(await response);await other.waitForFunction(()=>document.querySelector('#fileDraftStatus')?.textContent==='');
   if((await text(id,path)).content!=='TAB TWO\nsecond\nPEER'||await page.locator('#fileEditor').inputValue()!=='TAB TWO\nsecond\nPEER')throw Error('Recovery across tabs lost the current writer buffer');checks.push('A draft changed in another real tab is re-reviewed by revision without deleting the active writer snapshot');
  }finally{await other.close({runBeforeUnload:false});}
  const uuidPath='docs/uuid-compat.md';await write(id,uuidPath,'saved');const compatible=await page.context().newPage();compatible.on('dialog',accept);
  try{
   await compatible.addInitScript(()=>Object.defineProperty(crypto,'randomUUID',{value:undefined,configurable:true}));await compatible.goto(origin+'/#'+id);await compatible.locator('[data-view=files]').click();await compatible.locator('#fileCatalogScope').selectOption('all');await compatible.locator('#fileSearch').fill(uuidPath);await compatible.locator('[data-file-path="'+uuidPath+'"]').click();await compatible.locator('#editTextFile').click();await compatible.locator('#fileEditor').fill('recover without UUID helper');await compatible.reload();
   await compatible.locator('#reviewStoredDrafts').click();await compatible.locator('[data-draft-path="'+uuidPath+'"] [data-review-draft]').first().click();await compatible.locator('#applyRecoveredDraft').click();await compatible.locator('#fileDraftReviewDialog').waitFor({state:'detached'});if(await compatible.locator('#fileEditor').inputValue()!=='recover without UUID helper')throw Error('Draft recovery required the secure-context UUID helper');checks.push('Files startup and reload recovery work when randomUUID is unavailable and cryptographic random bytes remain available');
  }finally{await compatible.close({runBeforeUnload:false});}
  await page.screenshot({path:artifactDir+'/draft-recovery-saved.png'});return{checks};
 }catch(error){failed=true;await page.screenshot({path:artifactDir+'/failure-before-cleanup.png'});throw error;}
 finally{release();await page.unrouteAll({behavior:'ignoreErrors'});page.removeListener('dialog',accept);if(!failed)for(const id of ids)await page.request.delete(origin+'/api/projects/'+id);}
}
