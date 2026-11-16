async (page, options = {}) =>{
  const origin=options.origin||'http://127.0.0.1:8770',previous=page.url(),checks=[];
  const created=await page.request.post(origin+'/api/workbench/projects',{data:{title:'Selection editing acceptance',example:true}}),p=await created.json();
  try{
    await page.setViewportSize({width:1440,height:1000});
    await page.goto(origin+'/?workbench-qa='+Date.now()+'#'+p.id);await page.getByRole('tab',{name:'Schematic',exact:true}).click();await page.waitForSelector('.native-symbol-graphics');
    await page.locator('#collapseChat').click();
    await page.locator('.canvas-component[data-ref="R1"]').click();await page.locator('.canvas-component[data-ref="R2"]').click({modifiers:['Shift']});
    if(await page.locator('.canvas-component.selected').count()!==2)throw new Error('Shift-click did not select both native symbols');
    await page.getByText('2 objects selected',{exact:true}).waitFor();checks.push('Shift-click selects multiple native symbols with a selection inspector');
    const saved=page.waitForResponse(r=>r.url().endsWith('/design')&&r.request().method()==='PUT'&&r.ok());
    await page.locator('#selectionDx').fill('40');await page.locator('#selectionDy').fill('30');await page.locator('#moveSelectionButton').click();await saved;
    let state=(await(await page.request.get(origin+'/api/projects/'+p.id)).json()).state;
    if(state.spec.editor.positions.R1[0]!==200||state.spec.editor.positions.R2[0]!==370)throw new Error('Batch movement did not preserve selected symbol offsets');
    checks.push('Batch movement saves both schematic poses as one design revision');
    await page.getByRole('button',{name:'Close inspector',exact:true}).click();await page.getByRole('button',{name:'Zoom to fit',exact:true}).click();
    const a=await page.locator('.canvas-component[data-ref="R1"]').boundingBox(),b=await page.locator('.canvas-component[data-ref="R2"]').boundingBox();
    await page.mouse.move(Math.min(a.x,b.x)-8,Math.min(a.y,b.y)-8);await page.mouse.down();await page.mouse.move(Math.max(a.x+a.width,b.x+b.width)+8,Math.max(a.y+a.height,b.y+b.height)+8,{steps:8});await page.mouse.up();
    if(await page.locator('.canvas-component.selected').count()!==2)throw new Error('Rectangle selection did not select the enclosed symbols');
    checks.push('Dragging a rectangle selects the actual native symbol bounds');
    await page.locator('.canvas-component[data-ref="R1"]').click({button:'right'});await page.locator('[data-canvas-action="duplicate"]').waitFor();
    const duplicated=page.waitForResponse(r=>r.url().endsWith('/design')&&r.request().method()==='PUT'&&r.ok());await page.locator('[data-canvas-action="duplicate"]').click();await duplicated;
    state=(await(await page.request.get(origin+'/api/projects/'+p.id)).json()).state;
    if(!state.spec.components.some(c=>c.ref==='R4')||!state.spec.components.some(c=>c.ref==='R5'))throw new Error('Duplicate did not allocate actual component designators');
    if(!state.spec.nets.find(n=>n.name==='GND').pins.includes('R4.2')||state.spec.nets.find(n=>n.name==='CC1').pins.includes('R4.1'))throw new Error('Copied net connectivity is incorrect');
    checks.push('The context menu duplicates components, shared power and isolated signal nets');
    await page.locator('#viewContent').click({position:{x:550,y:800}});await page.keyboard.press('ControlOrMeta+a');
    if(await page.locator('.canvas-component.selected').count()!==11)throw new Error('Select all missed visible schematic objects');
    const deleted=page.waitForResponse(r=>r.url().endsWith('/design')&&r.request().method()==='PUT'&&r.ok());await page.keyboard.press('Backspace');await deleted;
    state=(await(await page.request.get(origin+'/api/projects/'+p.id)).json()).state;if(state.spec.components.length)throw new Error('Batch deletion left components');
    const restored=page.waitForResponse(r=>r.url().endsWith('/design')&&r.request().method()==='PUT'&&r.ok());await page.keyboard.press('ControlOrMeta+z');await restored;
    state=(await(await page.request.get(origin+'/api/projects/'+p.id)).json()).state;if(state.spec.components.length!==11)throw new Error('One undo did not restore the complete deleted selection');
    checks.push('Select all, batch delete and one-step undo preserve the complete design');
    await page.getByRole('tab',{name:'Layout',exact:true}).click();await page.waitForSelector('#nativeBoard canvas');
    await page.getByRole('button',{name:'Objects',exact:true}).click();await page.locator('[data-object="R1"]').click();await page.locator('[data-object="R2"]').click({modifiers:['Shift']});await page.locator('#closeDrawer').click();
    await page.getByText('2 objects selected',{exact:true}).waitFor();await page.getByRole('button',{name:'Zoom to fit',exact:true}).click();
    const native=await(await page.request.post(`${origin}/api/workbench/projects/${p.id}/native`)).json(),geo=await(await page.request.get(origin+native.geometry_url)).json(),rect=await page.locator('#nativeBoard canvas').boundingBox();
    const [x0,y0,x1,y1]=geo.bbox,scale=Math.min((rect.width-16)/(x1-x0+12),(rect.height-16)/(y1-y0+12)),part=geo.footprints.find(f=>f.ref==='R1'),px=rect.x+rect.width/2+(part.x-(x0+x1)/2)*scale,py=rect.y+rect.height/2+(part.y-(y0+y1)/2)*scale;
    const moved=page.waitForResponse(r=>r.url().endsWith('/design')&&r.request().method()==='PUT'&&r.ok());await page.mouse.move(px,py);await page.mouse.down();await page.mouse.move(px+scale*.5,py+scale*.3,{steps:8});await page.mouse.up();await moved;
    state=(await(await page.request.get(origin+'/api/projects/'+p.id)).json()).state;
    if(Math.abs(state.spec.components.find(c=>c.ref==='R1').placement.x_mm-8.5)>.04||Math.abs(state.spec.components.find(c=>c.ref==='R2').placement.x_mm-8.5)>.04)throw new Error('Native PCB group drag did not move both selected footprints together');
    checks.push('Native PCB footprints drag together and persist one shared translation');
    return{checks};
  }finally{await page.goto(previous);await page.request.delete(origin+'/api/projects/'+p.id);}
}
