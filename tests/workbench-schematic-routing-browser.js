async(page,options={})=>{
  const origin=options.origin||'http://127.0.0.1:8770',checks=[];
  const spec={name:'continuous_schematic',board:{width_mm:30,height_mm:22,layers:2},components:[1,2,3].map(i=>({ref:'R'+i,value:'1k',symbol:'Device:R',footprint:'Resistor_SMD:R_0603_1608Metric',placement:{x_mm:5+(i-1)*10,y_mm:10,rotation:0}})),nets:[{name:'SIG',pins:['R1.1','R2.1']},{name:'GND',pins:['R1.2','R2.2','R3.2']}],editor:{positions:{R1:[200,200],R2:[600,200],R3:[400,520]},connection_guides:[{id:'ground',from:'R1.2',to:'R2.2'}]}};
  const created=await page.request.post(origin+'/api/workbench/projects',{data:{title:'Continuous schematic routing',spec}});if(!created.ok())throw new Error(await created.text());const project=await created.json();
  const state=async()=>(await(await page.request.get(origin+'/api/projects/'+project.id)).json()).state;
  const saved=()=>page.waitForResponse(r=>r.url().endsWith('/design')&&r.request().method()==='PUT'&&r.ok(),{timeout:8000});
  const ready=()=>page.waitForSelector('.native-symbol-graphics');
  const at=point=>page.locator('[data-scene]').evaluate((scene,point)=>{const p=new DOMPoint(...point).matrixTransform(scene.getScreenCTM());return{x:p.x,y:p.y};},point);
  const click=async point=>{const p=await at(point);await page.mouse.click(p.x,p.y);};
  try{
    await page.setViewportSize({width:1440,height:1000});await page.goto(origin+'/?schematic-routing='+Date.now()+'#'+project.id);await page.getByRole('tab',{name:'Schematic',exact:true}).click();await page.locator('#collapseChat').click();await ready();
    // Native auto-fit after collapsing chat can place y=40 under the tab bar.
    // Choose an actual visible canvas before exercising the wire gestures.
    await page.locator('#zoomOut').click();
    for(let attempt=0;attempt<4;attempt++){
      const bounds=await page.locator('#viewContent').boundingBox(),points=await Promise.all([[400,40],[510,60]].map(at));
      if(points.every(p=>p.x>bounds.x+8&&p.x<bounds.x+bounds.width-8&&p.y>bounds.y+8&&p.y<bounds.y+bounds.height-8))break;
      if(attempt===3)throw new Error('The planned wire corners are outside the visible canvas');
      await page.locator('#zoomOut').click();
    }
    const initial=await state();await page.locator('#wireButton').click();await page.locator('[data-pinref="R1.1"]').click();
    await click([300,100]);await page.locator('.schematic-wire-draft').waitFor();
    if(await page.locator('.selection-marquee').count())throw new Error('Clicking a wire bend started a selection marquee');
    let points=await page.locator('.schematic-wire-draft').getAttribute('data-points');
    await click([400,40]);const second=await page.locator('.schematic-wire-draft').getAttribute('data-points');
    if(points===second)throw new Error('A second corner did not extend the wire preview');
    if((await state()).workbench.version!==initial.workbench.version)throw new Error('Pending wire bends changed the saved design');
    checks.push('Blank clicks create consecutive snapped wire bends without changing the saved design');
    await page.keyboard.press('Backspace');points=await page.locator('.schematic-wire-draft').getAttribute('data-points');
    const restored=JSON.parse(points),expected=[[200,170],[200,160],[300,160],[300,100]];
    if(restored.length!==expected.length||restored.some((p,i)=>p.some((v,j)=>Math.abs(v-expected[i][j])>.001)))throw new Error('Backspace did not remove the last bend as one gesture: '+points);
    const cursor=await at([510,60]);await page.mouse.move(cursor.x,cursor.y);const first=await page.locator('.schematic-wire-draft').getAttribute('d');await page.keyboard.press('f');
    if(await page.locator('.schematic-wire-draft').getAttribute('d')===first)throw new Error('F did not flip the active wire elbow');
    await page.keyboard.press('f');
    checks.push('Backspace removes one bend and F flips the active elbow');
    let wait=saved();await page.locator('[data-pinref="R2.1"]').click();await wait;await ready();
    let current=await state(),guide=current.spec.editor.connection_guides.at(-1);
    if(!guide.waypoints?.some(p=>p[0]===300&&p[1]===100)||current.spec.editor.connection_guides.length!==2)throw new Error('Finishing on a pin lost the manually drawn bends');
    if(await page.locator('.schematic-wire-draft').count())throw new Error('Finished wire preview was not cleared');
    let scene=await(await page.request.post(origin+'/api/workbench/schematic-view',{data:current.spec})).json();
    const routed=scene.routes.find(r=>r.index===1);if(routed?.status!=='routed'||!routed.points.some(p=>Math.abs(p[0]-300)<.001&&Math.abs(p[1]-100)<.001))throw new Error('Native wire does not pass through the chosen bend');
    const native=await page.request.post(`${origin}/api/workbench/projects/${project.id}/native`);if(!native.ok()||!(await native.json()).schematic_parity?.ok)throw new Error('Native schematic and saved pin groups differ');
    const checked=await(await page.request.post(`${origin}/api/workbench/projects/${project.id}/native-checks`)).json();
    if([...checked.erc.errors,...checked.erc.warnings].some(row=>row.type==='unconnected_wire_endpoint'))throw new Error('Manual bends left an unintended native dangling wire tail');
    checks.push('Completed bends persist as real KiCad wires with matching native netlist');
    await page.locator('[data-pinref="R3.1"]').click();await click([520,420]);await page.keyboard.press('Escape');
    if(await page.locator('.schematic-wire-draft').count()||(await state()).workbench.version!==current.workbench.version)throw new Error('Esc saved or retained an unfinished wire');
    if(await page.locator('#wireButton').getAttribute('aria-pressed')!=='true')throw new Error('First Esc unexpectedly exited the wire tool');
    checks.push('Esc cancels the pending wire while keeping the tool ready for another connection');
    // A wire can start on the previously committed route and keep its exact join.
    const target=await page.locator('[data-wire-route="1"]').first().evaluate(path=>{const p=path.getPointAtLength(path.getTotalLength()*.4).matrixTransform(path.getScreenCTM());return{x:p.x,y:p.y};});
    await page.mouse.click(target.x,target.y);await page.locator('.schematic-wire-draft').waitFor({state:'attached'});
    await click([720,400]);wait=saved();await page.locator('[data-pinref="R3.1"]').click();await wait;await ready();current=await state();guide=current.spec.editor.connection_guides.at(-1);
    if(!guide.from_join||!guide.waypoints?.length||!current.spec.nets.find(n=>n.name==='SIG').pins.includes('R3.1'))throw new Error('Continuous wire-origin drawing lost its branch or electrical connection');
    checks.push('Existing native wires can start a manually bent branch');
    await page.locator('[data-pinref="R1.1"]').click();await click([150,100]);await page.locator('[data-pinref="R1.2"]').click();await page.locator('#mergeNetDialog').waitFor({state:'visible'});
    await page.locator('#mergeNetDialog').getByRole('button',{name:'Cancel',exact:true}).click();
    if((await state()).workbench.version!==current.workbench.version||await page.locator('.schematic-wire-draft').count())throw new Error('Cancelling the established-net merge saved or retained manual wire geometry');
    checks.push('Manually bent wires retain established-net merge review and cancel without saving');
    wait=saved();await page.keyboard.press('ControlOrMeta+z');await wait;await ready();let undone=await state();
    if(undone.spec.nets.some(n=>n.pins.includes('R3.1'))||undone.spec.editor.connection_guides.length!==2)throw new Error('Undo did not restore both route geometry and pin groups');
    wait=saved();await page.keyboard.press('ControlOrMeta+Shift+z');await wait;await ready();current=await state();
    if(!current.spec.editor.connection_guides.at(-1).from_join||!current.spec.nets.find(n=>n.name==='SIG').pins.includes('R3.1'))throw new Error('Redo did not restore the manually bent branch');
    checks.push('One design undo/redo restores complete wire geometry and electrical membership');
    await page.locator('[data-pinref="R3.1"]').click();await click([650,350]);const external=structuredClone(current.spec);external.components.find(c=>c.ref==='R2').value='2k';
    const updated=await page.request.put(`${origin}/api/workbench/projects/${project.id}/design`,{data:{base_version:current.workbench.version,spec:external}});if(!updated.ok())throw new Error(await updated.text());
    await page.locator('.schematic-wire-draft').waitFor({state:'detached'});await ready();current=await state();
    if(current.spec.editor.connection_guides.length!==3||current.spec.components.find(c=>c.ref==='R2').value!=='2k')throw new Error('External editing preserved an obsolete pending route or lost the new design');
    checks.push('An external saved design cancels obsolete pending wire geometry');
    await page.reload();await ready();current=await state();if(!current.spec.editor.connection_guides.at(-1).waypoints?.length)throw new Error('Reload lost the committed bends');
    scene=await(await page.request.post(origin+'/api/workbench/schematic-view',{data:current.spec})).json();if(scene.routes.some(r=>r.status!=='routed'))throw new Error('A committed branch became unroutable after reload');
    if(options.artifactDir)await page.screenshot({path:options.artifactDir+'/continuous-schematic.png'});
    checks.push('Manual wire geometry and junctions survive reload');return{checks,project:project.id,...(options.keepProject?{initial_spec:spec}: {})};
  }finally{if(!options.keepProject)await page.request.delete(origin+'/api/projects/'+project.id);}
}
