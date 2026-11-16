async (page, options = {}) =>{
  const origin=options.origin||'http://127.0.0.1:8770',previous=page.url(),checks=[];
  const p=await(await page.request.post(origin+'/api/workbench/projects',{data:{title:'PCB layers and vias acceptance',example:true}})).json();
  const native=async()=>{const n=await(await page.request.post(`${origin}/api/workbench/projects/${p.id}/native`)).json();return await(await page.request.get(origin+n.geometry_url)).json();};
  const scene=async()=>{await page.getByRole('button',{name:'Zoom to fit',exact:true}).click();const geo=await native(),rect=await page.locator('#nativeBoard canvas').boundingBox(),[x0,y0,x1,y1]=geo.bbox,scale=Math.min((rect.width-16)/(x1-x0+12),(rect.height-16)/(y1-y0+12));return{geo,point:(x,y)=>({x:rect.x+rect.width/2+(x-(x0+x1)/2)*scale,y:rect.y+rect.height/2+(y-(y0+y1)/2)*scale})};};
  try{
    await page.setViewportSize({width:1440,height:1000});
    await page.goto(origin+'/?workbench-qa='+Date.now()+'#'+p.id);await page.getByRole('tab',{name:'Layout',exact:true}).click();await page.waitForSelector('#nativeBoard canvas');await page.locator('#collapseChat').click();
    let s=await scene();if(!s.geo.drawings.some(g=>g.layer==='F.SilkS'&&g.kind!=='text'))throw new Error('Native library silkscreen geometry is missing');
    checks.push('Layout receives actual KiCad footprint silkscreen and fabrication graphics');
    await page.getByRole('button',{name:'Layers',exact:true}).click();
    const before=await page.locator('#nativeBoard canvas').evaluate(canvas=>canvas.toDataURL());await page.locator('[data-layer="F.SilkS"]').uncheck();
    const after=await page.locator('#nativeBoard canvas').evaluate(canvas=>canvas.toDataURL());if(before===after)throw new Error('The silkscreen checkbox did not affect rendered geometry');
    await page.locator('[data-layer="F.SilkS"]').check();await page.locator('[data-layer="grid"]').check();await page.locator('#routingWidth').selectOption('0.35');await page.locator('#closeDrawer').click();
    checks.push('Native layer visibility changes actual canvas pixels without rebuilding the design');
    await page.getByRole('button',{name:'Place via',exact:true}).click();await page.locator('#viaNet').selectOption('GND');await page.locator('#viaDiameter').fill('0.8');await page.locator('#viaDrill').fill('0.4');await page.locator('#viaForm button[type=submit]').click();
    s=await scene();const at=s.point(112,119),saved=page.waitForResponse(r=>r.url().endsWith('/design')&&r.request().method()==='PUT'&&r.ok());await page.mouse.click(at.x,at.y);await saved;
    let state=(await(await page.request.get(origin+'/api/projects/'+p.id)).json()).state;
    if(!state.spec.fixed_copper.some(c=>c.net==='GND'&&c.vias.some(v=>v.d===.8&&v.drill===.4&&Math.abs(v.p[0]-12)<.01)))throw new Error('Via placement was not saved as real board copper');
    s=await scene();if(!s.geo.vias.some(v=>v.net==='GND'&&v.d===.8&&v.drill===.4))throw new Error('The saved via did not enter the native KiCad PCB');
    checks.push('Placing a through via saves its net, diameter, drill and native KiCad geometry');
    await page.getByRole('button',{name:'Route trace',exact:true}).click();const pad=s.geo.pads.find(p=>p.ref==='R1'&&p.name==='2'),via=s.geo.vias.find(v=>v.net==='GND'),a=s.point(pad.x,pad.y),b=s.point(...via.p);
    await page.mouse.click(a.x,a.y);const routed=page.waitForResponse(r=>r.url().endsWith('/design')&&r.request().method()==='PUT'&&r.ok());await page.mouse.click(b.x,b.y);await routed;
    state=(await(await page.request.get(origin+'/api/projects/'+p.id)).json()).state;const copper=state.spec.fixed_copper.find(c=>c.net==='GND');if(!copper.vias.length||!copper.tracks.length||copper.tracks.some(t=>t.w!==.35))throw new Error('Pad-to-via routing did not preserve the chosen trace width');
    if(await page.locator('.design-svg').count())throw new Error('Saving a native PCB edit replaced the editor with simplified preview geometry');
    await page.locator(`#nativeBoard[data-design-version="${state.workbench.version}"][data-updating="false"] canvas`).waitFor();
    checks.push('Routing to an actual via preserves its copper and uses the selected trace width');
    await page.getByRole('button',{name:'Layers',exact:true}).click();await page.screenshot({path:(options.artifactDir||'test-results')+'/pcb-editor.png'});
    return{checks};
  }finally{await page.goto(previous);await page.request.delete(origin+'/api/projects/'+p.id);}
}
