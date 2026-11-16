async (page, options={})=>{
  const origin=options.origin||'http://127.0.0.1:8770',checks=[],previous=page.url();
  const created=await page.request.post(origin+'/api/workbench/projects',{data:{title:'Production workflow UI acceptance',spec:{name:'production_ui',board:{width_mm:25,height_mm:20,layers:2,ground_pour:null},components:[{ref:'R1',value:'1k',symbol:'Device:R',footprint:'Resistor_SMD:R_0603_1608Metric',lcsc:'C21190',placement:{x_mm:10,y_mm:10}}],nets:[]}}});
  if(!created.ok())throw new Error(await created.text());
  const project=await created.json(),pid=project.id,base=`${origin}/api/projects/${pid}/production`;
  let supplier,supplierContext;
  const waitForPost=(target,path)=>target.waitForResponse(response=>response.url().endsWith(path)&&response.request().method()==='POST'&&response.ok());
  const submit=async(target,form,name,path)=>{const response=waitForPost(target,path);await target.locator(form).getByRole('button',{name,exact:true}).click();return (await response).json();};
  try{
    const native=await page.request.post(`${origin}/api/workbench/projects/${pid}/native`);
    if(!native.ok())throw new Error(await native.text());
    const before=(await(await page.request.get(`${origin}/api/projects/${pid}`)).json()).state;
    await page.setViewportSize({width:1440,height:1000});
    await page.goto(`${origin}/#${pid}`);
    await page.locator('#priceButton').click();
    await page.locator('#productionWorkbenchLink').click();
    await page.waitForURL(url=>url.pathname==='/production'&&url.searchParams.get('project')===pid);
    checks.push('The existing Manufacturing drawer opens the production workspace for the saved project');
    await page.getByRole('heading',{name:'Production workflow UI acceptance',exact:true}).waitFor();
    await page.locator('#estimateForm [name=scope]').selectOption('pcb');
    await page.locator('#estimateForm [name=use_ai]').uncheck();
    await submit(page,'#estimateForm','生成估价','/estimates');
    await page.locator('#productionEstimate').waitFor();
    let state=await(await page.request.get(base)).json();
    if(!state.estimates.length||state.estimates[0].source_version!==before.workbench.version)throw new Error('The production estimate did not preserve the saved design version');
    checks.push('Buyer can save a quantity-bound estimate with provenance and an explicit AI state');
    await page.locator('#packageForm [name=files_match_design]').check();
    await page.locator('#packageForm [name=test_plan]').fill('Prototype only: inspect copper and measure resistance before first power-up.');
    const pack=await submit(page,'#packageForm','冻结生产包','/packages');
    await page.locator(`[data-package="${pack.id}"]`).waitFor();
    const download=await page.request.get(base+`/packages/${pack.id}/download`);
    if(!download.ok()||!download.headers()['content-type'].includes('zip'))throw new Error('The frozen package ZIP is not downloadable');
    checks.push('The current native PCB exports a frozen downloadable production package');
    await page.locator('#rfqForm [name=supplier_id]').selectOption('jlcpcb');
    await page.locator('#rfqForm [name=target_budget]').fill('25');
    await page.locator('#rfqForm [name=contact_email]').fill('supplier@example.test');
    const rfq=await submit(page,'#rfqForm','准备询价与供应商链接','/rfqs');
    const row=page.locator(`[data-rfq="${rfq.id}"]`);
    await row.locator('.record-heading>.status').getByText('待发送询价',{exact:true}).waitFor();
    const supplierURL=await row.getByLabel('供应商链接',{exact:true}).inputValue();
    if(!supplierURL.includes('/production/supplier/'))throw new Error('The created RFQ did not expose its one-time supplier link');
    await row.locator('[name=external_reference]').fill('Manual handoff acceptance receipt');
    await row.locator('[name=sent]').check();
    await submit(page,`[data-rfq="${rfq.id}"] .handoff-form`,'记录已发送','/submit');
    checks.push('Prepared inquiries remain unsent until the buyer records an actual external handoff');
    supplierContext=await page.context().browser().newContext({viewport:{width:1440,height:1000}});
    supplier=await supplierContext.newPage();
    await supplier.goto(new URL(supplierURL,origin).href);
    await supplier.locator('#supplierQuoteForm').waitFor();
    await supplier.locator('[name=contact_name]').fill('Acceptance supplier contact');
    await supplier.locator('[name=reference]').fill('QUOTE-UI-001');
    await supplier.locator('[name=line_amount]').fill('20');
    const quoted=await submit(supplier,'#supplierQuoteForm','提交正式报价','/quote');
    await supplier.getByText('供应商报价已提交，等待客户确认。',{exact:true}).waitFor();
    await page.locator('#refreshProduction').click();
    await row.getByRole('button',{name:'接受报价（不付款）',exact:true}).waitFor();
    const accept=waitForPost(page,'/accept');await row.getByRole('button',{name:'接受报价（不付款）',exact:true}).click();await accept;
    checks.push('A supplier submits the real portal quotation and the buyer explicitly accepts it without payment');
    await supplier.locator('#refreshProduction').click();
    await supplier.locator('#progressForm').waitFor();
    for(const status of ['engineering_review','materials','production','testing','shipped']){
      await supplier.locator('#progressForm [name=status]').selectOption(status);
      await supplier.locator('#progressForm [name=note]').fill(`UI acceptance: ${status}`);
      if(status==='shipped'){await supplier.locator('#progressForm [name=carrier]').fill('Acceptance courier');await supplier.locator('#progressForm [name=tracking_number]').fill('DEMO-NOT-A-SHIPMENT');}
      await submit(supplier,'#progressForm','更新生产进度','/events');
    }
    await page.locator('#refreshProduction').click();
    await row.locator('.record-heading>.status').getByText('已发货',{exact:true}).waitFor();
    state=await(await page.request.get(base)).json();
    const final=state.rfqs.find(value=>value.id===rfq.id);
    if(final.status!=='shipped'||!final.accepted_quote_id||final.quotes[0].total!==20)throw new Error('The persisted production RFQ differs from the UI workflow');
    if(!final.events.some(event=>event.tracking_number==='DEMO-NOT-A-SHIPMENT'))throw new Error('Shipment tracking did not reach persisted production events');
    checks.push('Supplier stages and shipment tracking persist and reach the buyer timeline');
    const after=(await(await page.request.get(`${origin}/api/projects/${pid}`)).json()).state;
    if(JSON.stringify(after.spec)!==JSON.stringify(before.spec)||after.workbench.version!==before.workbench.version)throw new Error('Production operations changed the circuit design or design history');
    checks.push('The complete production workflow preserves the saved circuit design and version');
    await page.locator('#rfqForm [name=supplier_id]').selectOption('pcbway');
    const pcbway=await submit(page,'#rfqForm','准备询价与供应商链接','/rfqs');
    if(pcbway.supplier_id!=='pcbway'||pcbway.status!=='prepared'||pcbway.id===rfq.id)throw new Error('The PCBWay inquiry was not created as a separate, unsent RFQ');
    checks.push('JLCPCB and PCBWay each receive a separate inquiry against the same immutable production package');
    if(options.artifactDir){await page.evaluate(()=>window.scrollTo(0,0));await supplier.evaluate(()=>window.scrollTo(0,0));await page.screenshot({path:options.artifactDir+'/production-buyer.png'});await page.screenshot({path:options.artifactDir+'/production-buyer-full.png',fullPage:true});await supplier.screenshot({path:options.artifactDir+'/production-supplier.png'});}
    await page.setViewportSize({width:390,height:844});
    if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth))throw new Error('The buyer production page overflows a mobile viewport');
    await supplier.setViewportSize({width:390,height:844});
    if(await supplier.evaluate(()=>document.documentElement.scrollWidth>innerWidth))throw new Error('The supplier portal overflows a mobile viewport');
    if(options.artifactDir){await page.screenshot({path:options.artifactDir+'/production-buyer-mobile.png'});await supplier.screenshot({path:options.artifactDir+'/production-supplier-mobile.png'});}
    checks.push('Buyer and supplier production pages fit a mobile viewport');
    const revoked=waitForPost(page,'/revoke');await row.getByRole('button',{name:'撤销链接',exact:true}).click();await revoked;
    await supplier.reload();await supplier.locator('#productionNotice.error').waitFor();
    checks.push('Revoking the supplier capability prevents later package and RFQ access');
    return {project:pid,checks};
  }finally{await supplierContext?.close();if(previous&&previous!=='about:blank')await page.goto(previous);await page.request.delete(origin+'/api/projects/'+pid);}
}
