async (page, options = {}) =>{
  const origin=options.origin||'http://127.0.0.1:8770',previous=page.url(),checks=[];
  const created=await page.request.post(origin+'/api/workbench/projects',{data:{title:'Manufacturing estimate UI acceptance'}}),p=await created.json();
  try{
    await page.setViewportSize({width:1440,height:1000});
    await page.goto(origin+'/?workbench-qa='+Date.now()+'#'+p.id);await page.locator('#priceButton').click();
    await page.locator('#estimateQuantity').fill('5');await page.locator('#estimateAssembly').uncheck();
    const estimated=page.waitForResponse(r=>r.url().endsWith('/quote')&&r.request().method()==='POST'&&r.ok());await page.locator('#refreshEstimate').click();await estimated;
    await page.locator('.estimate-total strong').waitFor();
    const state=(await(await page.request.get(origin+'/api/projects/'+p.id)).json()).state;
    if(!(state.quote.total>0)||state.quote.source_version!==1)throw new Error('The estimate UI did not use the actual saved draft');
    const total=await page.locator('.estimate-total strong').textContent(),badge=await page.locator('#priceButton').textContent();if(!badge.includes(total))throw new Error('The price badge differs from the saved estimate');
    if(!await page.locator('.estimate-disclaimer').isVisible())throw new Error('Estimate status is not visible to the user');
    checks.push('A draft gets an actual table-based estimate without requiring a native build');
    checks.push('The header total matches the saved batch cost and clearly labels the estimate');
    const spec=state.spec;spec.board.width_mm+=10;
    await page.request.put(`${origin}/api/workbench/projects/${p.id}/design`,{data:{base_version:state.workbench.version,spec}});
    await page.reload();await page.locator('#priceButton').click();await page.locator('.estimate-stale').waitFor();checks.push('Editing the design marks the old manufacturing estimate stale');
    await page.goto(origin+'/#'+(options.fixtureId||'20261111-004018-3ab1'));await page.locator('#addTabButton').click();await page.locator('[data-add-view="bom"]').click();await page.getByRole('heading',{name:'Bill of materials',exact:true}).waitFor();
    const first=page.locator('tr[data-ref="J1"]');
    if(!await first.textContent().then(text=>text.includes('$0.0882')&&text.includes('65,775')))throw new Error('Saved supplier price and stock did not reach the BOM');
    checks.push('BOM columns display real saved supplier unit prices and stock');
    return{checks};
  }finally{await page.goto(previous);await page.request.delete(origin+'/api/projects/'+p.id);}
}
