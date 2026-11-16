async(page,options={})=>{
 const origin=options.origin||'http://127.0.0.1:8770',checks=[],ids=[],echoes=[];let release=()=>{};
 const pause=ms=>new Promise(r=>setTimeout(r,ms));
 const eventually=async(test,message)=>{for(let i=0;i<100;i++){if(await test())return;await pause(50);}throw Error(message);};
 const state=async id=>(await(await page.request.get(`${origin}/api/projects/${id}`)).json()).state;
 const make=async title=>{const r=await page.request.post(origin+'/api/workbench/projects',{data:{title,spec:{name:'source_edit',board:{width_mm:30,height_mm:22,layers:2},components:[{ref:'R1',value:'1k',symbol:'Device:R',footprint:'Resistor_SMD:R_0603_1608Metric'}],nets:[]}}});if(!r.ok())throw Error(await r.text());const id=(await r.json()).id;ids.push(id);return id;};
 const open=async id=>{await page.goto(origin+'/#'+id);await page.locator('#saveLabel').filter({hasText:'Saved locally'}).waitFor();await page.getByRole('tab',{name:'Files',exact:true}).click();await page.locator('#fileCatalogScope').selectOption('all');await page.locator('.file-entry[title="design.json"]').click();await page.locator('#editTextFile').click();await page.locator('#fileEditor').waitFor({state:'visible'});};
 const hold=async id=>{let arrived;const started=new Promise(r=>arrived=r),gate=new Promise(r=>release=r),pattern=`**/api/workbench/projects/${id}/design`;await page.route(pattern,async route=>{if(route.request().method()!=='PUT')return route.continue();const response=await route.fetch();arrived();await gate;await route.fulfill({response});});return{started,pattern};};
 const finish=async(id,held)=>{const response=page.waitForResponse(r=>r.url().endsWith(`/projects/${id}/design`)&&r.request().method()==='PUT');release();await(await response).json();await page.unroute(held.pattern);await page.evaluate(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))));};
 const choose=async path=>{await page.locator(`.file-entry[title="${path}"]`).click();};
 page.on('websocket',socket=>socket.on('framereceived',event=>{try{const e=JSON.parse(event.payload);if(e.type==='design_saved')echoes.push(socket.url().split('/projects/')[1].split('/')[0]+':'+e.version);}catch{}}));
 try{
  const a=await make('Design source A'),initial=await state(a);await open(a);
  const edited=structuredClone(initial.spec);edited.board.width_mm=34;
  const first=await hold(a);await page.locator('#fileEditor').fill(JSON.stringify(edited,null,2));await page.locator('#saveTextFile').click();await first.started;await eventually(()=>echoes.includes(a+':2'),'The real source save did not reach the browser WebSocket');
  await page.evaluate(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))));const finished=page.waitForResponse(r=>r.url().endsWith(`/projects/${a}/design`)&&r.request().method()==='PUT');release();await(await finished).json();await page.unroute(first.pattern);
  await eventually(async()=>(await state(a)).workbench.version===2,'Source save was not persisted');
  await page.evaluate(()=>document.activeElement?.blur());await page.keyboard.press('ControlOrMeta+z');
  await eventually(async()=>{const p=await state(a);return p.workbench.version===3&&JSON.stringify(p.spec)===JSON.stringify(initial.spec);},'The source save lost Undo when its own WebSocket echo arrived before the PUT response');
  await page.evaluate(()=>document.activeElement?.blur());await page.keyboard.press('ControlOrMeta+Shift+z');
  await eventually(async()=>{const p=await state(a);return p.workbench.version===4&&JSON.stringify(p.spec)===JSON.stringify(edited);},'Redo did not restore the complete saved source design');
  checks.push('A real own-save WebSocket echo arriving before the source response preserves full-design Undo and Redo');

  await choose('design.json');await page.locator('#editTextFile').click();const intermediate=structuredClone(edited);intermediate.board.width_mm=36;const newest=structuredClone(edited);newest.board.width_mm=38;
  const second=await hold(a);await page.locator('#fileEditor').fill(JSON.stringify(intermediate,null,2));await page.locator('#saveTextFile').click();await second.started;
  if(!await page.locator('#saveTextFile').isDisabled()||await page.locator('#fileEditor').evaluate(e=>e.readOnly))throw Error('A pending source save permits duplicate submission or prevents editing a newer local draft');
  await page.locator('#fileEditor').fill(JSON.stringify(newest,null,2));await page.keyboard.press('ControlOrMeta+s');
  await finish(a,second);if(JSON.parse(await page.locator('#fileEditor').inputValue()).board.width_mm!==38||(await state(a)).spec.board.width_mm!==36)throw Error('A source response discarded or prematurely saved the newer draft');
  await page.locator('#saveTextFile').click();await eventually(async()=>{const p=await state(a);return p.workbench.version===6&&JSON.stringify(p.spec)===JSON.stringify(newest);},'The newer source draft did not save against the accepted version');
  checks.push('Pending source saves coalesce repeated Save and rebase newer local drafts without saving them early');

  const file=await page.request.put(`${origin}/api/workbench/projects/${a}/text/docs/readme.md`,{data:{content:'# Side document',base_sha:null}});if(!file.ok())throw Error(await file.text());
  await page.getByRole('tab',{name:'Schematic',exact:true}).click();await page.getByRole('tab',{name:'Files',exact:true}).click();await page.locator('#fileCatalogScope').selectOption('all');await choose('design.json');await page.locator('#editTextFile').click();
  const switched=structuredClone(newest);switched.board.width_mm=40;const third=await hold(a);await page.locator('#fileEditor').fill(JSON.stringify(switched,null,2));await page.locator('#saveTextFile').click();await third.started;
  await choose('docs/readme.md');await page.locator('#editTextFile').click();await page.locator('#fileEditor').fill('# Unrelated local draft');await finish(a,third);
  if(await page.locator('#fileEditor').inputValue()!=='# Unrelated local draft'||await page.locator('#fileViewName').innerText()!=='docs/readme.md')throw Error('A late design save replaced another file draft');
  await choose('design.json');await page.locator('#editTextFile').click();if(JSON.parse(await page.locator('#fileEditor').inputValue()).board.width_mm!==40)throw Error('Accepted source was not installed in the project after switching files');
  await page.evaluate(()=>document.activeElement?.blur());await page.keyboard.press('ControlOrMeta+z');await eventually(async()=>{const p=await state(a);return p.workbench.version===8&&JSON.stringify(p.spec)===JSON.stringify(newest);},'Switching files during a source save lost its Undo history');
  checks.push('A design response after a file switch updates the project and Undo while leaving the other file draft intact');

  const b=await make('Design source B'),beforeB=await state(b);await choose('design.json');await page.locator('#editTextFile').click();const moved=structuredClone(newest);moved.board.width_mm=42;const fourth=await hold(a);await page.locator('#fileEditor').fill(JSON.stringify(moved,null,2));await page.locator('#saveTextFile').click();await fourth.started;await page.evaluate(id=>location.hash=id,b);
  await page.locator('#projectLoading').waitFor();if((await page.locator('#projectTitle').innerText()).includes('Design source B'))throw Error('A project switch overtook a pending source save');await finish(a,fourth);await page.locator('#projectTitle').filter({hasText:'Design source B'}).waitFor();
  const afterB=await state(b);if(JSON.stringify(afterB.spec)!==JSON.stringify(beforeB.spec)||afterB.workbench.version!==beforeB.workbench.version||(await state(a)).spec.board.width_mm!==42)throw Error('A late source save crossed project identities');
  await page.locator('#fileCatalogScope').selectOption('all');await choose('design.json');await page.locator('#editTextFile').click();if(JSON.parse(await page.locator('#fileEditor').inputValue()).board.width_mm!==30)throw Error('The new project editor adopted the old project source');
  checks.push('Project switching waits for an outstanding design save and never installs its spec or version into another project');

  const invalid=JSON.stringify({...beforeB.spec,board:{...beforeB.spec.board,width_mm:-1}},null,2);await page.locator('#fileEditor').fill(invalid);await page.locator('#saveTextFile').click();await page.locator('.toast.error').filter({hasText:/positive|width|board/i}).waitFor();
  if(await page.locator('#fileEditor').inputValue()!==invalid||await page.locator('#saveTextFile').isDisabled())throw Error('A rejected source save lost the raw draft or left editing locked');const rejected=await state(b);if(rejected.workbench.version!==1||JSON.stringify(rejected.spec)!==JSON.stringify(beforeB.spec))throw Error('A rejected design was installed or created a saved version');
  checks.push('Backend validation failure preserves the raw source draft and saved design and releases the save lock');

  const remote=structuredClone(beforeB.spec);remote.board.height_mm=26;const external=await page.request.put(`${origin}/api/workbench/projects/${b}/design`,{data:{base_version:1,spec:remote}});if(!external.ok())throw Error(await external.text());await page.locator('#saveLabel').filter({hasText:'Updated from another editor'}).waitFor();
  await page.locator('#fileEditor').waitFor({state:'visible'});if(await page.locator('#fileEditor').inputValue()!==invalid)throw Error('Remote design synchronization discarded a stale local source draft');const stale=structuredClone(beforeB.spec);stale.board.width_mm=44;await page.locator('#fileEditor').fill(JSON.stringify(stale,null,2));await page.locator('#saveTextFile').click();await page.locator('.toast.error').filter({hasText:/changed.*source|Another editor/i}).waitFor();
  const unchanged=await state(b);if(unchanged.workbench.version!==2||JSON.stringify(unchanged.spec)!==JSON.stringify(remote)||JSON.parse(await page.locator('#fileEditor').inputValue()).board.width_mm!==44)throw Error('A stale source draft overwrote a remote version or was lost');
  checks.push('Remote saves preserve local source drafts while stale base versions cannot overwrite the saved design');

  const c=await make('Concurrent source save');await open(c);const local=structuredClone((await state(c)).spec);local.board.width_mm=34;const fifth=await hold(c);await page.locator('#fileEditor').fill(JSON.stringify(local,null,2));await page.locator('#saveTextFile').click();await fifth.started;
  const peer=structuredClone(local);peer.board.height_mm=26;const peerSave=await page.request.put(`${origin}/api/workbench/projects/${c}/design`,{data:{base_version:2,spec:peer}});if(!peerSave.ok())throw Error(await peerSave.text());await eventually(()=>echoes.includes(c+':3'),'The peer save did not reach the pending client');
  const laterDraft=structuredClone(local);laterDraft.board.width_mm=38;await page.locator('#fileEditor').fill(JSON.stringify(laterDraft,null,2));await finish(c,fifth);
  await page.locator('#saveLabel').filter({hasText:'Updated from another editor'}).waitFor({timeout:5000});await page.locator('#fileEditor').waitFor({state:'visible'});
  if(JSON.stringify(JSON.parse(await page.locator('#fileEditor').inputValue()))!==JSON.stringify(laterDraft))throw Error('Catching up to a peer save discarded the newer local draft');await page.locator('#saveTextFile').click();await page.locator('.toast.error').filter({hasText:/changed.*source/i}).last().waitFor();
  const peerFinal=await state(c);if(peerFinal.workbench.version!==3||JSON.stringify(peerFinal.spec)!==JSON.stringify(peer))throw Error('The client overwrote the peer save received during its own pending save');
  checks.push('A newer peer save received during an outstanding local save is applied afterward without rebasing stale drafts over it');

  await page.setViewportSize({width:390,height:844});if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth))throw Error('Source editing overflows the mobile viewport');if(options.artifactDir)await page.screenshot({path:options.artifactDir+'/design-source-mobile.png'});checks.push('Source drafts and conflict feedback remain accessible within the mobile viewport');
  return{checks};
 }finally{release();await page.unrouteAll({behavior:'ignoreErrors'});for(const id of ids)await page.request.delete(origin+'/api/projects/'+id);}
}
