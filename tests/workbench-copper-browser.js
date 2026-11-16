async(page,options={})=>{
  const origin=options.origin||'http://127.0.0.1:8770',checks=[],ids=['11111111-1111-4111-8111-111111111111','22222222-2222-4222-8222-222222222222','33333333-3333-4333-8333-333333333333'];
  const spec=await(await page.request.get(origin+'/api/workbench/example')).json();
  spec.fixed_copper=[{net:'CC1',tracks:[{id:ids[0],a:[2,18],b:[10,18],w:.25,layer:'F.Cu'},{id:ids[1],a:[10,18],b:[10,20],w:.25,layer:'F.Cu'}],vias:[{id:ids[2],p:[10,20],d:.8,drill:.4,layers:['F.Cu','B.Cu']}]}];
  spec.fixed_zones=[{net:'GND',origin:[100,100],source:'(zone (net "GND") (layer "B.Cu") (uuid "44444444-4444-4444-8444-444444444444") (hatch edge 0.5) (connect_pads (clearance 0.25)) (min_thickness 0.2) (fill yes (thermal_gap 0.3) (thermal_bridge_width 0.4)) (polygon (pts (xy 100.5 100.5) (xy 129.5 100.5) (xy 129.5 121.5) (xy 100.5 121.5))))'}];
  const made=await page.request.post(origin+'/api/workbench/projects',{data:{title:'Existing copper editor acceptance',spec}});if(!made.ok())throw new Error(await made.text());const p=await made.json();
  const state=async()=> (await(await page.request.get(origin+'/api/projects/'+p.id)).json()).state;
  const saved=()=>{const waiting=page.waitForResponse(r=>r.url().endsWith('/design')&&r.request().method()==='PUT'&&r.ok());waiting.catch(()=>{});return waiting;};
  const ready=async()=>{const version=(await state()).workbench.version;await page.locator(`#nativeBoard[data-updating="false"][data-design-version="${version}"] canvas`).waitFor();};
  const scene=async()=>{await ready();await page.locator('#fitButton').click();const geo=(await(await page.request.get(`${origin}/api/workbench/projects/${p.id}/layout-geometry`)).json()).geometry,rect=await page.locator('#nativeBoard canvas').boundingBox(),[x0,y0,x1,y1]=geo.bbox,scale=Math.min((rect.width-16)/(x1-x0+12),(rect.height-16)/(y1-y0+12));return{geo,scale,point:(x,y)=>({x:rect.x+rect.width/2+(x-(x0+x1)/2)*scale,y:rect.y+rect.height/2+(y-(y0+y1)/2)*scale})};};
  const field=async(key,value)=>{const input=page.locator(`[data-copper-property="${key}"]`);await input.waitFor({state:'visible',timeout:8000});await Promise.all([saved(),(async()=>{if(await input.evaluate(e=>e.tagName==='SELECT'))await input.selectOption(value);else{await input.fill(value);await input.press('Tab');}})()]);await ready();};
  try{
    await page.setViewportSize({width:1440,height:1000});await page.goto(origin+'/?copper-qa='+Date.now()+'#'+p.id);await page.getByRole('tab',{name:'Layout',exact:true}).click();await page.locator('#collapseChat').click();
    let s=await scene(),at=s.point(106,118);await page.mouse.click(at.x,at.y);
    if(!await page.locator('[data-copper-property="w"]').count())throw new Error('Existing PCB tracks cannot be selected and edited');
    await field('w','0.4');s=await scene();if(s.geo.tracks.find(t=>t.id===ids[0])?.w!==.4)throw new Error('Trace width did not reach the native KiCad board');
    checks.push('Existing native tracks expose editable properties and preserve their identity');
    await page.locator('#restoreChat').click();await page.locator('#historyButton').click();await page.locator('[data-compare-version="1"]').click();
    await page.waitForFunction(()=>document.querySelector('#historyComparison')?.textContent.includes('field_changes'));
    const comparison=JSON.parse(await page.locator('#historyComparison').textContent());
    if(!comparison.field_changes.some(change=>change.path.endsWith('/w')&&change.before===.25&&change.after===.4))throw new Error('Version comparison omitted the real trace-width edit');
    await page.locator('#historyDialog [data-close]').click();await page.locator('#collapseChat').click();checks.push('Version comparison includes actual copper edits and unchanged design sections');
    if(!s.geo.zone_sources.length||!s.geo.zones.some(zone=>zone.layer==='B.Cu'&&zone.net==='GND'))throw new Error('Editing a trace lost the existing native ground pour');
    checks.push('Copper edits preserve zone rules and actually refill them with KiCad');
    let wait=saved();await page.locator('#splitCopperTrace').click();await wait;s=await scene();
    if(s.geo.tracks.filter(t=>t.net==='CC1').length!==3)throw new Error('Splitting a native segment did not create two real segments');
    const handle=page.locator('[data-copper-handle="b"]');await handle.hover();const box=await handle.boundingBox();wait=saved();await page.mouse.move(box.x+box.width/2,box.y+box.height/2);await page.mouse.down();await page.mouse.move(box.x+box.width/2,box.y+box.height/2-s.scale,{steps:8});await page.mouse.up();await wait;
    s=await scene();const first=s.geo.tracks.find(t=>t.id===ids[0]);
    if(Math.abs(first.b[1]-117)>.05||s.geo.tracks.filter(t=>t.net==='CC1'&&Math.hypot(t.a[0]-first.b[0],t.a[1]-first.b[1])<.001).length!==1)throw new Error('Moving a vertex detached its same-net neighboring segment');
    checks.push('Tracks split into editable vertices and connected neighbors move together');
    await field('layer','B.Cu');s=await scene();if(s.geo.tracks.find(t=>t.id===ids[0]).layer!=='B.Cu')throw new Error('Layer edits were not saved to native copper');
    const before=(await state()).spec,originalCount=s.geo.tracks.length;wait=saved();await page.locator('#deleteCopperObject').click();await wait;s=await scene();if(s.geo.tracks.length!==originalCount-1)throw new Error('Deleting copper removed the wrong number of native objects');
    wait=saved();await page.keyboard.press('ControlOrMeta+z');await wait;await ready();const restored=(await state()).spec;if(JSON.stringify(restored.fixed_copper)!==JSON.stringify(before.fixed_copper))throw new Error('Undo did not restore the complete copper edit');
    checks.push('Layer changes, single-segment deletion and undo persist through native regeneration');
    s=await scene();at=s.point(110,120);await page.mouse.click(at.x,at.y);
    await field('drill','0.35');s=await scene();if(s.geo.vias.find(v=>v.id===ids[2])?.drill!==.35)throw new Error('An existing via cannot be edited');
    checks.push('Existing native vias expose their actual diameter and drill');
    if(options.artifactDir)await page.screenshot({path:options.artifactDir+'/copper-editor.png'});
    return{checks,project:p.id};
  }finally{await page.request.delete(origin+'/api/projects/'+p.id);}
}
