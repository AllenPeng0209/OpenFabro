async(page,options={})=>{
  const origin=options.origin||'http://127.0.0.1:8770',previous=page.url(),checks=[];
  const p=await(await page.request.post(origin+'/api/workbench/projects',{data:{title:'Native CAD assembly acceptance',example:true}})).json();
  try{
    await page.setViewportSize({width:1440,height:1000});await page.goto(origin+'/?mechanical-qa='+Date.now()+'#'+p.id);
    await page.getByRole('tab',{name:'3D View',exact:true}).click();
    const exported=page.waitForResponse(r=>r.url().endsWith('/engineering/board3d')&&r.request().method()==='POST',{timeout:180000});await page.locator('#buildNativeBoard3D').click();const board=await exported;
    if(!board.ok())throw new Error(await board.text());
    await page.getByText(/KiCad STEP geometry/).waitFor();
    let state=(await(await page.request.get(origin+'/api/projects/'+p.id)).json()).state;
    if(!(state.workbench_board3d.triangles>1000)||state.workbench_board3d.unmatched_components.length)throw new Error('Native 3D did not resolve real component models');
    checks.push('A real KiCad STEP export is converted into native component meshes');
    await page.locator('[data-mesh="enclosure"]').click();
    const enclosed=page.waitForResponse(r=>r.url().endsWith('/engineering/enclosure')&&r.request().method()==='POST',{timeout:180000});await page.locator('#buildEnclosure').click();const enclosure=await enclosed;
    if(!enclosure.ok())throw new Error(await enclosure.text());
    await page.getByText('Native PCB + FreeCAD enclosure',{exact:false}).waitFor();
    state=(await(await page.request.get(origin+'/api/projects/'+p.id)).json()).state;
    if(state.workbench_enclosure.pcb_sha256!==state.workbench_board3d.source_sha)throw new Error('The enclosure and native board do not identify the same PCB source');
    checks.push('Enclosure and board geometry retain the same native PCB source hash');
    if(!state.workbench_enclosure.files.some(f=>/\.step$/i.test(f.name))||!state.workbench_enclosure.files.some(f=>/\.stl$/i.test(f.name)))throw new Error('Mechanical export files are incomplete');
    await page.locator('#cameraOptions').click();await page.locator('#cadStyle').selectOption('xray');await page.locator('#cadSection').selectOption('z');
    await page.locator('#closeDrawer').click();await page.screenshot({path:(options.artifactDir||'test-results')+'/native-assembly.png'});
    checks.push('The combined native assembly renders with material and cross-section controls');
    checks.push('Actual enclosure STEP and STL exports are available');
    return{checks,triangles:state.workbench_board3d.triangles};
  }finally{
    await page.goto(previous);
    const state=await page.request.get(origin+'/api/projects/'+p.id);
    if(state.ok()&&!['running','waiting'].includes((await state.json()).state.status))await page.request.delete(origin+'/api/projects/'+p.id);
  }
}
