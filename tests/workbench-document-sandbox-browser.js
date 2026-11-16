async(page,options={})=>{
  const origin=options.origin||'http://127.0.0.1:8770',pid=options.fixtureId,checks=[];
  if(!pid)throw new Error('This suite uses the isolated runner document fixtures');
  await page.goto(`${origin}/api/projects/${pid}/files/docs/sandbox.svg`);
  if(await page.evaluate(()=>window.executed))throw new Error('An SVG document executed script with workspace origin');
  checks.push('Project SVG diagrams render without executing embedded scripts');
  await page.goto(`${origin}/api/projects/${pid}/files/docs/sandbox.html`);
  await page.locator('#counter').click();if(await page.locator('#counter').textContent()!=='1')throw new Error('The interactive report was broken');
  if(await page.evaluate(()=>window.origin)!=='null')throw new Error('The report inherited the workspace origin');
  const reachable=await page.evaluate(async()=>{try{await fetch('/api/config');return true;}catch{return false;}});
  if(reachable)throw new Error('The report can access workspace APIs');
  checks.push('Interactive HTML reports retain their controls in an isolated origin without API access');
  return{checks};
}
