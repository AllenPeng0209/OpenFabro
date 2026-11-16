async(page,options={})=>{
 const origin=options.origin||'http://127.0.0.1:8770',checks=[],verify=(ok,label)=>{if(!ok)throw new Error(label);checks.push(label);};
 const p=await(await page.request.post(origin+'/api/workbench/projects',{data:{title:'Terminal authoring acceptance',example:true}})).json();
 const state=async()=>(await(await page.request.get(origin+'/api/projects/'+p.id)).json()).state;
 const saved=(timeout=30000)=>{const pending=page.waitForResponse(r=>r.url().endsWith('/design')&&r.request().method()==='PUT'&&r.ok(),{timeout});pending.catch(()=>{});return pending;};
 const field=async(key,value)=>{const el=page.locator(`[data-terminal-property="${key}"]`),wait=saved();if(await el.evaluate(el=>el.tagName)==='SELECT')await el.selectOption(value);else{await el.fill(value);await el.press('Tab');}await wait;};
 try{
  let before=await state();before.spec.fixed_copper=[{net:'CC1',tracks:[{a:[12,12],b:[14,12],w:.25,layer:'F.Cu'}]}];await page.request.put(`${origin}/api/workbench/projects/${p.id}/design`,{data:{base_version:before.workbench.version,spec:before.spec}});
  await page.goto(origin+'/?terminals='+Date.now()+'#'+p.id);await page.locator('#collapseChat').click();await page.getByRole('tab',{name:'Schematic',exact:true}).click();await page.locator('.native-symbol-graphics').first().waitFor();
  await page.getByRole('button',{name:'Part library',exact:true}).click();let wait=saved();await page.getByRole('button',{name:'Add terminal',exact:true}).click({timeout:2500});await wait;await page.locator('[data-ref="TP1"]').waitFor();
  let current=await state();verify(current.spec.components.at(-1).terminal&&current.spec.nets.some(net=>net.placeholder_ref==='TP1'),'Add an isolated terminal with a real canonical single-pin connection');
  await field('name','OUT');await field('direction','output');await field('side','right');await field('diameter_mm','2.2');
  verify((await state()).spec.components.find(c=>c.ref==='TP1').value==='OUT','Terminal designator, electrical direction and pad dimensions are editable');
  await page.getByRole('button',{name:'Zoom to fit',exact:true}).click();const initialPosition=(await state()).spec.editor.positions.TP1;
  const handle=await page.locator('[data-ref="TP1"]').evaluate(el=>{const m=el.getScreenCTM();return{x:m.e,y:m.f,scale:m.a};});wait=saved(5000);await page.mouse.move(handle.x,handle.y);await page.mouse.down();await page.mouse.move(handle.x+handle.scale*60,handle.y+handle.scale*40,{steps:8});await page.mouse.up();await wait;
  verify(JSON.stringify((await state()).spec.editor.positions.TP1)===JSON.stringify([initialPosition[0]+60,initialPosition[1]+40]),'Dragging a terminal in selection mode moves it without opening the net editor');
  await page.getByRole('button',{name:'Zoom to fit',exact:true}).click();await page.locator('#wireButton').click();await page.locator('[data-pinref="TP1.1"]').click();wait=saved();await page.locator('[data-pinref="R1.1"]').click();await wait;
  verify(!await page.locator('#mergeNetDialog').isVisible(),'Connecting a new isolated terminal does not request an established-net short');
  current=await state();verify(current.spec.nets.find(net=>net.name==='CC1').pins.includes('TP1.1')&&current.spec.fixed_copper.find(g=>g.net==='CC1').tracks[0].a[0]===12,'Wiring the terminal extends the existing net and preserves routed copper');
  await page.locator('#wireButton').click();await page.locator('[data-ref="TP1"]').click();await page.getByRole('tab',{name:'Layout',exact:true}).click();await page.waitForFunction(()=>document.querySelector('#nativeBoard')?.dataset.updating==='false');
  let native=await(await page.request.post(`${origin}/api/workbench/projects/${p.id}/native`)).json(),geo=await(await page.request.get(origin+native.geometry_url)).json();
  verify(geo.pads.some(p=>p.ref==='TP1'&&p.w===2.2&&p.h===2.2),'The terminal creates a native PCB test pad with the edited diameter');
  await field('exclude_from_pcb','true');native=await(await page.request.post(`${origin}/api/workbench/projects/${p.id}/native`)).json();geo=await(await page.request.get(origin+native.geometry_url)).json();
  verify(!geo.footprints.some(p=>p.ref==='TP1')&&native.schematic_parity.ok,'Excluding a terminal removes only its PCB pad and preserves native schematic connectivity');
  await page.getByRole('tab',{name:'Schematic',exact:true}).click();await page.locator('[data-ref="TP1"]').click();await page.keyboard.down('Shift');await page.locator('[data-ref="R1"]').click();await page.keyboard.up('Shift');await page.getByRole('button',{name:'Convert to Component',exact:true}).click();
  await page.locator('#moduleId').fill('WithTerminal');await page.locator('#moduleInstance').fill('M1');await page.getByRole('button',{name:'Prepare module',exact:true}).click();await page.waitForFunction(()=>!document.querySelector('#confirmModuleConversion').disabled);wait=saved();await page.locator('#confirmModuleConversion').click();await wait;
  current=await state();verify(current.spec.library.modules.WithTerminal.ports.OUT.net==='CC1','Converting a selection carries its terminal designator and connection into the reusable module');
  await page.locator('#schematicSheet').selectOption('');await page.getByRole('button',{name:'Zoom to fit',exact:true}).click();await page.locator('#wireButton').click();await page.locator('[data-pinref="J1.A5"]').click();wait=saved();await page.locator('[data-anchor="sheet:M1.OUT"]').click();await wait;await page.locator('#wireButton').click();
  await page.locator('#schematicSheet').selectOption('M1');await page.locator('[data-ref="TP1"]').click();await field('name','VOUT');current=await state();
  verify(current.spec.editor.connection_guides.some(g=>g.to==='sheet:M1.VOUT')&&!current.spec.editor.sheets.M1.ports.OUT,'Renaming a module terminal keeps outside wire anchors current without leaving an old port');
  await field('side','bottom');native=await(await page.request.post(`${origin}/api/workbench/projects/${p.id}/native`)).json();verify(native.schematic_parity.ok,'Native KiCad pin groups remain equal after terminal creation, wiring, exclusion, conversion and rename');
  await page.locator('#schematicSheet').selectOption('');await page.getByRole('button',{name:'Zoom to fit',exact:true}).click();await page.locator('[data-sheet-target="M1"]').click();wait=saved();await page.getByRole('button',{name:'Edit terminal GND',exact:true}).click();await wait;
  await page.waitForFunction(()=>document.querySelector('#schematicSheet')?.value==='M1',{},{timeout:2500});await page.locator('[data-ref="TP2"]').waitFor();
  verify((await state()).spec.components.find(c=>c.ref==='TP2').terminal.exclude_from_pcb===true,'Editing a legacy boundary port opens its child sheet and preserves the existing PCB');
  return{checks};
 }catch(error){if(options.artifactDir)await page.screenshot({path:options.artifactDir+'/terminal-error.png'});throw error;}
 finally{await page.goto(origin+'/?terminals-finished='+Date.now());await page.request.delete(origin+'/api/projects/'+p.id);}
}
