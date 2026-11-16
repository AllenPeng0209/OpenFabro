async(page,options={})=>{
 const origin=options.origin||'http://127.0.0.1:8770',checks=[],verify=(ok,label)=>{if(!ok)throw new Error(label);checks.push(label);};
 const p=await(await page.request.post(origin+'/api/workbench/projects',{data:{title:'Reusable modules acceptance',example:true}})).json();
 const state=async()=>(await(await page.request.get(`${origin}/api/projects/${p.id}`)).json()).state;
 const saved=()=>{const pending=page.waitForResponse(r=>r.url().endsWith('/design')&&r.request().method()==='PUT'&&r.ok());pending.catch(()=>{});return pending;};
 try{
  const original=await state();original.spec.board.width_mm=80;original.spec.fixed_copper=[{net:'CC1',tracks:[{a:[12,12],b:[14,12],w:.35,layer:'F.Cu'}]}];
  await page.request.put(`${origin}/api/workbench/projects/${p.id}/design`,{data:{base_version:original.workbench.version,spec:original.spec}});
  await page.goto(origin+'/?modules-qa='+Date.now()+'#'+p.id);await page.locator('#collapseChat').click();await page.locator('#addTabButton').click();await page.locator('[data-add-view="library"]').click();
  verify(await page.locator('#libraryKind option[value="modules"]').count()===1,'Reusable modules are available in the project library');
  await page.locator('#libraryKind').selectOption('modules');await page.getByRole('button',{name:'Save project as module',exact:true}).click();
  await page.locator('#moduleId').fill('Supply');await page.locator('#moduleName').fill('USB supply');
  let wait=saved();await page.getByRole('button',{name:'Save module',exact:true}).click();await wait;
  let current=await state(),asset=current.spec.library.modules.Supply;
  verify(asset.design.components.length===9&&asset.design.fixed_copper.some(c=>c.tracks?.length),'Publishing captures the project circuit and real native routed geometry');
  const originalCu=JSON.stringify(current.spec.fixed_copper),originalNets=JSON.stringify(current.spec.nets);
  await page.getByRole('button',{name:'Insert module',exact:true}).click();await page.locator('#moduleInstance').fill('M1');await page.locator('#moduleOffsetX').fill('35');
  await page.locator('[data-module-connection="GND"]').selectOption('GND');
  wait=saved();await page.getByRole('button',{name:'Insert and open',exact:true}).click();await wait;
  current=await state();verify(current.spec.components.length===18&&new Set(current.spec.components.map(c=>c.ref)).size===18,'Inserting allocates globally unique component references');
  verify(current.spec.editor.sheets.M1.ports.GND.net==='GND'&&current.spec.nets.some(n=>n.name==='M1_CC1'),'Explicit terminals connect externally while internal module nets remain isolated');
  const copied=current.spec.fixed_copper.find(c=>c.net==='M1_CC1');verify(copied.tracks[0].a[0]===47&&JSON.stringify(current.spec.fixed_copper.filter(c=>c.net==='CC1'))===originalCu,'Inserting translates routed copper and preserves existing copper');
  await page.locator('.native-symbol-graphics').first().waitFor();verify(await page.locator('#schematicSheet').inputValue()==='M1','An inserted module opens as an editable hierarchical schematic');
  await page.locator('#schematicSheet').selectOption('');await page.getByRole('button',{name:'Zoom to fit',exact:true}).click();
  verify(await page.locator('[data-sheet-target="M1"]').count()===1,'A module boundary and its exposed ports appear on Main');
  current=await state();current.spec.components.push({ref:'R7',value:'10k',symbol:'Device:R',footprint:'Resistor_SMD:R_0603_1608Metric',placement:{x_mm:72,y_mm:18}});current.spec.editor.positions.R7=[600,100];
  await page.request.put(`${origin}/api/workbench/projects/${p.id}/design`,{data:{base_version:current.workbench.version,spec:current.spec}});await page.reload();await page.locator('[data-sheet-target="M1"]').waitFor();await page.getByRole('button',{name:'Zoom to fit',exact:true}).click();
  await page.locator('#wireButton').click();await page.locator('[data-pinref="R7.1"]').click();
  wait=saved();await page.locator('[data-anchor="sheet:M1.CC1"]').click({timeout:2500});await wait;
  current=await state();verify(current.spec.nets.find(n=>n.name==='M1_CC1').pins.includes('R7.1')&&current.spec.fixed_copper.find(c=>c.net==='M1_CC1').tracks.length===copied.tracks.length,'Drawing a wire to a module terminal extends its canonical net and retains internal routes');
  verify(current.spec.editor.connection_guides.at(-1).to==='sheet:M1.CC1','Module wires retain a stable terminal anchor');
  const native=await page.request.post(`${origin}/api/workbench/projects/${p.id}/native`);if(!native.ok())throw new Error(await native.text());verify((await native.json()).schematic_parity.ok,'Native KiCad confirms the drawn module terminal connection');
  await page.locator('#wireButton').click();
  if(!await page.getByRole('tab',{name:'Library',exact:true}).count()){await page.locator('#addTabButton').click();await page.locator('[data-add-view="library"]').click();}else await page.getByRole('tab',{name:'Library',exact:true}).click();
  await page.locator('#libraryKind').selectOption('modules');await page.getByRole('button',{name:'Export module',exact:true}).waitFor();
  const exported=page.waitForEvent('download');exported.catch(()=>{});await page.getByRole('button',{name:'Export module',exact:true}).click();const file=await exported;
  verify(file.suggestedFilename()==='Supply.module.json','A module can be exported as a portable library package');
  return{checks};
 }catch(error){if(options.artifactDir)await page.screenshot({path:options.artifactDir+'/module-error.png'});throw error;}
 finally{await page.goto(origin+'/?modules-finished='+Date.now());await page.request.delete(`${origin}/api/projects/${p.id}`);}
}
