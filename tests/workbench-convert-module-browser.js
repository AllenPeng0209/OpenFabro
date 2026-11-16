async(page,options={})=>{
 const origin=options.origin||'http://127.0.0.1:8770',checks=[],verify=(ok,label)=>{if(!ok)throw new Error(label);checks.push(label);};
 const p=await(await page.request.post(origin+'/api/workbench/projects',{data:{title:'Convert selected circuit acceptance',example:true}})).json();
 const state=async()=>(await(await page.request.get(origin+'/api/projects/'+p.id)).json()).state;
 const saved=()=>{const pending=page.waitForResponse(r=>r.url().endsWith('/design')&&r.request().method()==='PUT'&&r.ok());pending.catch(()=>{});return pending;};
 try{
  let original=await state();original.spec.fixed_copper=[{net:'CC1',tracks:[{a:[8,11],b:[16,11],w:.25,layer:'F.Cu'}]}];
  await page.request.put(`${origin}/api/workbench/projects/${p.id}/design`,{data:{base_version:original.workbench.version,spec:original.spec}});
  original=await state();await page.goto(origin+'/?convert-module='+Date.now()+'#'+p.id);await page.locator('#collapseChat').click();await page.getByRole('tab',{name:'Schematic',exact:true}).click();await page.locator('.native-symbol-graphics').first().waitFor();
  await page.locator('[data-ref="R1"]').click();await page.keyboard.down('Shift');await page.locator('[data-ref="R2"]').click();await page.keyboard.up('Shift');
  await page.locator('[data-ref="R2"]').click({button:'right'});await page.getByRole('menuitem',{name:'Convert to Component',exact:false}).click({timeout:2500});
  await page.locator('#moduleId').fill('CC');await page.locator('#moduleInstance').fill('M1');await page.locator('#moduleName').fill('USB CC pair');
  await page.getByRole('button',{name:'Prepare module',exact:true}).click();await page.locator('#moduleCapturePreview canvas').waitFor();
  const previewBox=await page.locator('#moduleCapturePreview').boundingBox(),nameBox=await page.locator('#moduleName').boundingBox();
  verify(previewBox.y>nameBox.y+nameBox.height,'The native layout preview stays below the form fields and does not cover them');
  verify((await state()).workbench.version===original.workbench.version,'Preparing a selected module shows a real native preview without saving');
  await page.locator('#moduleName').fill('CC resistors');verify(await page.getByRole('button',{name:'Convert to component',exact:true}).isDisabled(),'Changing conversion settings invalidates the prepared draft');
  await page.getByRole('button',{name:'Prepare module',exact:true}).click();await page.waitForFunction(()=>!document.querySelector('#confirmModuleConversion').disabled);
  const wait=saved();await page.getByRole('button',{name:'Convert to component',exact:true}).click();await wait;
  let current=await state();verify(current.spec.components.length===9&&current.spec.library.modules.CC.design.components.length===2,'Converting wraps the selection and saves only its two components in the module');
  verify(JSON.stringify(current.spec.nets)===JSON.stringify(original.spec.nets)&&JSON.stringify(current.spec.components.map(c=>c.placement))===JSON.stringify(original.spec.components.map(c=>c.placement)),'Conversion preserves canonical nets and every physical component placement');
  verify(current.spec.fixed_copper[0].tracks[0].a[0]===8&&current.spec.fixed_copper[0].tracks[0].b[0]===16,'Conversion preserves the complete original PCB trace');
  await page.locator('[data-ref="R1"] .native-symbol-graphics').waitFor();verify(await page.locator('#schematicSheet').inputValue()==='M1'&&!await page.locator('[data-ref="J1"]').count(),'The converted component opens as an editable child schematic');
  const native=await page.request.post(`${origin}/api/workbench/projects/${p.id}/native`);if(!native.ok())throw new Error(await native.text());verify((await native.json()).schematic_parity.ok,'Actual native KiCad pin groups stay equivalent after conversion');
  await page.keyboard.press('ControlOrMeta+z');await page.waitForFunction(()=>!document.querySelector('#schematicSheet option[value="M1"]'));
  await page.locator('#saveIndicator').filter({hasText:'Saved locally'}).waitFor();current=await state();verify(!current.spec.library?.modules?.CC&&JSON.stringify(current.spec.components)===JSON.stringify(original.spec.components),'Undo restores the original unwrapped components and module library');
  for(const component of current.spec.components)component.sheet='Existing';current.spec.editor.sheets={Existing:{ports:{IN:{net:'VBUS'},GND:{net:'GND'},OUT:{net:'+3V3'}}}};
  await page.request.put(`${origin}/api/workbench/projects/${p.id}/design`,{data:{base_version:current.workbench.version,spec:current.spec}});await page.reload();await page.locator('#schematicSheet').selectOption('Existing');await page.locator('.native-symbol-graphics').first().waitFor();
  const refs=current.spec.components.map(c=>c.ref);await page.locator(`[data-ref="${refs[0]}"]`).click();await page.getByRole('button',{name:'Zoom to fit',exact:true}).click();await page.keyboard.down('Shift');for(const ref of refs.slice(1))await page.locator(`[data-ref="${ref}"]`).click();await page.keyboard.up('Shift');
  await page.getByRole('button',{name:'Convert to Component',exact:true}).click();
  verify(await page.locator('[data-convert-net]:checked').count()===3&&(await page.locator('[data-convert-label]').evaluateAll(inputs=>inputs.map(input=>input.value))).includes('IN'),'Nested conversion exposes declared parent terminals even without outside component pins');
  await page.locator('#moduleConversionDialog [data-cancel]').click();
  return{checks};
 }catch(error){if(options.artifactDir)await page.screenshot({path:options.artifactDir+'/conversion-error.png'});throw error;}
 finally{await page.goto(origin+'/?convert-finished='+Date.now());await page.request.delete(origin+'/api/projects/'+p.id);}
}
