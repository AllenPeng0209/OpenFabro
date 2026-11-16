async (page, options = {}) => {
  const origin=options.origin||'http://127.0.0.1:8770',checks=[];
  const verify=(value,label)=>{if(!value)throw new Error(label);checks.push(label);};
  const previous=await page.evaluate(()=>location.hash.slice(1));
  const created=await (await page.request.post(origin+'/api/workbench/projects',{data:{title:'Native canvas gesture test',example:true}})).json();
  const pid=created.id;
  const state=async()=> (await (await page.request.get(`${origin}/api/projects/${pid}`)).json()).state;
  const saved=()=>page.waitForResponse(r=>r.url().endsWith('/design')&&r.request().method()==='PUT'&&r.status()===200);
  const scene=async()=>{
    await page.getByRole('button',{name:'Zoom to fit',exact:true}).click();
    const native=await(await page.request.post(`${origin}/api/workbench/projects/${pid}/native`)).json();
    const geo=await(await page.request.get(origin+native.geometry_url)).json();
    const rect=await page.locator('#nativeBoard canvas').boundingBox();
    const [x0,y0,x1,y1]=geo.bbox;
    const scale=Math.min((rect.width-16)/(x1-x0+12),(rect.height-16)/(y1-y0+12));
    const point=(x,y)=>({x:rect.x+rect.width/2+(x-(x0+x1)/2)*scale,y:rect.y+rect.height/2+(y-(y0+y1)/2)*scale});
    return{geo,rect,scale,point};
  };
  try{
    await page.goto(origin+'/?native-qa='+Date.now()+'#'+pid);
    await page.getByRole('tab',{name:'Layout',exact:true}).click();await page.waitForSelector('#nativeBoard canvas');
    let s=await scene();const c=s.geo.footprints.find(f=>f.ref==='C2'),p=s.point(c.x,c.y);
    const wait=saved();await page.mouse.move(p.x,p.y);await page.mouse.down();await page.mouse.move(p.x+s.scale*.5,p.y,{steps:8});await page.mouse.up();await wait;
    verify(Math.abs((await state()).spec.components.find(c=>c.ref==='C2').placement.x_mm-21.8)<.04,'Dragging a real KiCad footprint persists board-local coordinates');
    await page.getByRole('button',{name:'Close inspector',exact:true}).click();await page.waitForSelector('#nativeBoard canvas');
    s=await scene();await page.getByRole('button',{name:'Route trace',exact:true}).click();
    const a=s.geo.pads.find(p=>p.ref==='R1'&&p.name==='1'),b=s.geo.pads.find(p=>p.ref==='J1'&&p.name==='A5');
    const pa=s.point(a.x,a.y),pb=s.point(b.x,b.y);await page.mouse.click(pa.x,pa.y);
    const routed=saved();await page.mouse.click(pb.x,pb.y);await routed;
    verify((await state()).spec.fixed_copper.some(c=>c.net==='CC1'&&c.tracks.length),'Routing between native pads creates actual copper in the saved spec');
    await page.waitForSelector('#nativeBoard canvas');s=await scene();
    verify(s.geo.tracks.some(t=>t.net==='CC1'),'Saved routes survive native KiCad regeneration');
    const near=(point,pad)=>Math.hypot(point[0]-pad.x,point[1]-pad.y)<.01;
    verify(!s.geo.ratsnest.some(line=>near(line[0],a)&&near(line[1],b)||near(line[1],a)&&near(line[0],b)),'Airwires remove the connection completed by the actual manual copper route');
    await page.getByRole('button',{name:'Conversation history',exact:true}).click();await page.waitForSelector('.history-version');
    verify(await page.locator('[data-restore-version="1"]').count()===1,'Immutable design history offers the initial version');
    await page.locator('[data-restore-version="1"]').click();await page.waitForFunction(()=>!document.querySelector('#historyDialog').open);
    verify(!(await state()).spec.fixed_copper?.length,'Restoring a design version also restores its copper state');
    return {checks,project:pid};
  }finally{
    await page.goto(origin+'/?native-qa-finished='+Date.now()+(previous?'#'+previous:''));
    await page.request.delete(`${origin}/api/projects/${pid}`);
  }
}
