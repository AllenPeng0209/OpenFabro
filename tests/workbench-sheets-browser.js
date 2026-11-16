async (page,options={})=>{
 const origin=options.origin||'http://127.0.0.1:8770',checks=[],verify=(ok,label)=>{if(!ok)throw new Error(label);checks.push(label);};
 const created=await(await page.request.post(origin+'/api/workbench/projects',{data:{title:'Sheet authoring acceptance',example:true}})).json(),pid=created.id;
 const state=async()=>(await(await page.request.get(`${origin}/api/projects/${pid}`)).json()).state;
 const saved=()=>page.waitForResponse(r=>r.url().endsWith('/design')&&r.request().method()==='PUT'&&r.ok());
 try{
  await page.goto(origin+'/?sheets-qa='+Date.now()+'#'+pid);await page.getByRole('tab',{name:'Schematic',exact:true}).click();
  await page.locator('.native-symbol-graphics').first().waitFor();const original=(await state()).spec;
  await page.locator('.canvas-component[data-ref="R1"]').click();
  await page.getByRole('button',{name:'Create sheet',exact:true}).click({timeout:2500});
  await page.locator('#sheetId').fill('Power');await page.locator('#sheetTitle').fill('Power stage');
  let wait=saved();await page.getByRole('button',{name:'Create sheet and open',exact:true}).click();await wait;
  await page.locator('#schematicSheet').selectOption('Power');await page.locator('.canvas-component[data-ref="R1"] .native-symbol-graphics').waitFor();
  let current=await state();verify(current.spec.components.find(c=>c.ref==='R1').sheet==='Power','Create a sheet from the selected component');
  verify(JSON.stringify(current.spec.nets)===JSON.stringify(original.nets)&&JSON.stringify(current.spec.components.map(c=>c.placement))===JSON.stringify(original.components.map(c=>c.placement)),'Moving to a sheet preserves nets and physical PCB placements');
  await page.getByRole('button',{name:'Create sheet',exact:true}).click();await page.locator('#sheetId').fill('Bias');await page.locator('#sheetTitle').fill('Bias');
  wait=saved();await page.getByRole('button',{name:'Create sheet and open',exact:true}).click();await wait;
  current=await state();verify(current.spec.editor.sheets.Bias.parent==='Power','Create an empty nested sheet inside the active sheet');
  await page.locator('#schematicSheet').selectOption('');await page.getByRole('button',{name:'Zoom to fit',exact:true}).click();await page.locator('[data-sheet-target="Power"]').click();
  await page.locator('[data-sheet-property="title"]').fill('Supply');wait=saved();await page.locator('[data-sheet-property="title"]').press('Tab');await wait;
  await page.locator('[data-sheet-property="size.0"]').fill('440');wait=saved();await page.locator('[data-sheet-property="size.0"]').press('Tab');await wait;
  current=await state();verify(current.spec.editor.sheets.Power.title==='Supply'&&current.spec.editor.sheets.Power.size[0]===440,'Rename and resize a sheet through the Inspector');
  await page.getByRole('button',{name:'Zoom to fit',exact:true}).click();
  let node=page.locator('[data-sheet-target="Power"]'),before=await node.evaluate(el=>{const m=el.getScreenCTM();return{x:m.e,y:m.f,scale:m.a};});
  const point=await node.evaluate(el=>{const p=new DOMPoint(120,60).matrixTransform(el.getScreenCTM());return{x:p.x,y:p.y};});
  wait=saved();await page.mouse.move(point.x,point.y);await page.mouse.down();await page.mouse.move(point.x+before.scale*60,point.y+before.scale*40,{steps:8});await page.mouse.up();await wait;
  current=await state();verify(current.spec.editor.sheets.Power.position[0]===910&&current.spec.editor.sheets.Power.position[1]===180,'Drag a sheet boundary without moving the PCB');
  await node.locator('.sheet-resize-handle').hover();const handle=await node.locator('.sheet-resize-handle').boundingBox();before=await node.evaluate(el=>({scale:el.getScreenCTM().a}));
  wait=saved();await page.mouse.move(handle.x+handle.width/2,handle.y+handle.height/2);await page.mouse.down();await page.mouse.move(handle.x+handle.width/2+before.scale*60,handle.y+handle.height/2+before.scale*40,{steps:8});await page.mouse.up();await wait;
  current=await state();verify(current.spec.editor.sheets.Power.size[0]===500&&current.spec.editor.sheets.Power.size[1]===220,'Resize a selected sheet with its canvas handle');
  await page.waitForFunction(()=>document.querySelector('[data-sheet-target="Power"]')?.dataset.width==='500');
  await node.dblclick();await page.waitForFunction(()=>document.querySelector('#schematicSheet')?.value==='Power',{},{timeout:2500});await page.locator('.canvas-component[data-ref="R1"] .native-symbol-graphics').waitFor();
  await page.locator('.canvas-component[data-ref="R1"]').click();await page.locator('#componentSheet').selectOption('');
  wait=saved();await page.getByRole('button',{name:'Move to sheet',exact:true}).click();await wait;
  verify((await state()).spec.components.find(c=>c.ref==='R1').sheet==='','Move a component back to Main');
  await page.locator('#schematicSheet').selectOption('');await node.click();await page.getByRole('button',{name:'Remove sheet',exact:true}).click();
  wait=saved();await page.getByRole('button',{name:'Remove sheet and move contents',exact:true}).click();await wait;
  current=await state();verify(Object.keys(current.spec.editor.sheets).length===0&&JSON.stringify(current.spec.nets)===JSON.stringify(original.nets),'Remove a hierarchy while retaining component connectivity');
  return{checks};
 }catch(error){if(options.artifactDir)await page.screenshot({path:options.artifactDir+'/sheet-error.png'});throw error;}
 finally{await page.goto(origin+'/?sheets-qa-finished='+Date.now());await page.request.delete(`${origin}/api/projects/${pid}`);}
}
