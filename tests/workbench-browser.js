async (page, options = {}) => {
  const origin = options.origin || 'http://127.0.0.1:8770';
  const errors = [], checks = [];
  const onError = e => errors.push(e.message);
  page.on('pageerror', onError);
  const verify = (condition, message) => { if (!condition) throw new Error(message); checks.push(message); };
  const saved = () => page.waitForResponse(r => r.url().endsWith('/design') && r.request().method() === 'PUT' && r.status() === 200);
  const state = async pid => (await (await page.request.get(`${origin}/api/projects/${pid}`)).json()).state;
  const response = await page.request.post(`${origin}/api/workbench/projects`, { data: { title: 'Workbench acceptance test', example: true } });
  if (response.status() !== 201) throw new Error('Could not create the acceptance project');
  const draft = await response.json(), pid = draft.id;
  const previous = await page.evaluate(() => localStorage.getItem('wb-workbench-project'));
  try {
    await page.setViewportSize({width:1440,height:1000});
    await page.goto(`${origin}/#${pid}`);
    await page.getByRole('tab', {name:'Schematic',exact:true}).click();
    await page.waitForSelector('.canvas-component[data-ref="R1"]');
    verify(await page.locator('.canvas-component').count() === 9, 'Schematic renders the nine saved components');
    await page.locator('.canvas-component[data-ref="R1"]').click();
    verify(await page.locator('#inspector [data-property="value"]').inputValue() === '5.1k', 'Canvas selection opens the correct component in Inspector');
    let wait = saved();
    await page.locator('#inspector [data-property="value"]').fill('4.7k');
    await page.locator('#inspector [data-property="value"]').press('Tab');
    await wait;
    verify((await state(pid)).spec.components.find(c=>c.ref==='R1').value === '4.7k', 'Inspector edits persist through the actual Python API');

    wait = saved(); await page.keyboard.press('Meta+z'); await wait;
    verify((await state(pid)).spec.components.find(c=>c.ref==='R1').value === '5.1k', 'Undo restores the prior electrical value');
    wait = saved(); await page.keyboard.press('Meta+Shift+z'); await wait;
    verify((await state(pid)).spec.components.find(c=>c.ref==='R1').value === '4.7k', 'Redo restores the edited electrical value');
    await page.reload(); await page.waitForSelector('.canvas-component[data-ref="R1"]');
    await page.locator('.canvas-component[data-ref="R1"]').click();
    verify(await page.locator('#inspector [data-property="value"]').inputValue() === '4.7k', 'Reload restores saved project edits');
    await page.getByRole('button', {name:'Close inspector',exact:true}).click();

    await page.getByRole('button', {name:'Part library',exact:true}).click();
    wait = saved(); await page.locator('[data-library-part="0"]').click(); await wait;
    verify((await state(pid)).spec.components.some(c=>c.ref==='R4' && c.value==='10k'), 'Part library adds a new component with a unique reference');
    await page.getByRole('button', {name:'Close tools panel',exact:true}).click();
    await page.getByRole('button', {name:'Close inspector',exact:true}).click();
    await page.getByRole('button', {name:'Add view',exact:true}).click(); await page.locator('[data-add-view="nets"]').click();
    await page.getByRole('button', {name:'Add net',exact:true}).click();
    await page.locator('#netName').fill('TEST_GPIO'); await page.locator('#netPins').fill('R4.1, J2.3');
    wait = saved(); await page.getByRole('button',{name:'Save net',exact:true}).click(); await wait;
    const wired = await state(pid);
    verify(wired.spec.nets.some(n=>n.name==='TEST_GPIO' && n.pins.includes('R4.1') && n.pins.includes('J2.3')), 'Net editor persists real pin connections');
    verify(!wired.spec.components.find(c=>c.ref==='J2').no_connect.includes('3'), 'Connecting a pin removes its conflicting no-connect marker');
    await page.getByRole('button', {name:'Close inspector',exact:true}).click();
    await page.getByRole('tab', {name:'Layout',exact:true}).click();
    const tools=await (await page.request.get(origin+'/api/status')).json();
    if(tools.kicad_cli&&tools.libs.footprints){await page.waitForSelector('#nativeBoard canvas');verify(await page.locator('#nativeBoard canvas').count()===1,'Layout resolves real KiCad footprint geometry');}
    else verify(await page.locator('svg[aria-label="Interactive PCB placement preview"]').count() === 1, 'Layout opens the placement preview');
    await page.getByRole('tab', {name:'3D View',exact:true}).click();
    verify(await page.locator('#meshHost canvas').count() === 1, '3D view renders an interactive mesh');
    await page.getByRole('button',{name:'Enclosure',exact:true}).click();
    verify(await page.getByRole('slider',{name:'Exploded view'}).count() === 1, 'Enclosure view exposes exploded assembly control');
    await page.getByRole('slider',{name:'Exploded view'}).fill('1');

    await page.getByRole('button', {name:'Add view',exact:true}).click(); await page.locator('[data-add-view="bom"]').click();
    verify(await page.locator('.design-table tbody tr').count() === 10, 'BOM reads the same ten edited components');
    await page.getByRole('searchbox',{name:'Search table'}).fill('R4');
    verify(await page.locator('.design-table tbody tr:visible').count() === 1, 'BOM filtering finds the newly added part');
    const download = page.waitForEvent('download'); await page.getByRole('button',{name:'Export CSV',exact:true}).click();
    const file = await download; await file.saveAs((options.artifactDir||'test-results')+'/bom.csv');
    verify(file.suggestedFilename() === 'bill-of-materials.csv', 'BOM exports a downloadable CSV');
    await page.getByRole('tab', {name:'Files',exact:true}).click();await page.locator('#fileCatalogScope').selectOption('all');await page.locator('#fileSearch').fill('design.json');await page.locator('.file-entry[title="design.json"]').click();await page.waitForSelector('#fileSource');
    await page.waitForFunction(()=>document.querySelector('#fileSource')?.textContent.includes('TEST_GPIO'));
    verify((await page.locator('#fileSource').textContent()).includes('4.7k'), 'Files view shows the real saved design file');

    await page.getByRole('tab',{name:'Schematic',exact:true}).click();await page.getByRole('button',{name:'Design checks',exact:true}).click(); await page.getByRole('button',{name:'Run checks',exact:true}).click();
    await page.waitForSelector('#checkResults .check-row');
    verify((await page.locator('#checkResults').innerText()).includes(tools.kicad_cli?'KiCad DRC':'KiCad CLI is not installed.'), 'Checks show real engineering results or explain missing tools');
    await page.getByRole('button', {name:'Close tools panel',exact:true}).click();
    await page.getByRole('button',{name:'Open settings',exact:true}).click();
    await page.locator('[data-settings="tools"]').click(); await page.waitForSelector('#toolStatus .tool-status-item');
    verify(await page.locator('#toolStatus .tool-status-item').count()===5, 'Engineering settings expose real tool availability');
    await page.getByRole('button',{name:'Close settings',exact:true}).click();

    await page.setViewportSize({width:390,height:844}); await page.getByRole('tab',{name:'Schematic',exact:true}).click();
    verify(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth), 'Mobile editor fits the viewport without horizontal overflow');
    await page.getByRole('button',{name:'Toggle chat',exact:true}).click();
    verify(await page.locator('#chatInput').isVisible(), 'Mobile chat opens and remains usable');
    await page.screenshot({path:(options.artifactDir||'test-results')+'/mobile.png',scale:'css'});
    await page.getByRole('button',{name:'Minimize chat',exact:true}).click();
    verify(!await page.locator('#chatInput').isVisible(), 'Mobile chat closes back to the editor');
    verify(errors.length === 0, 'All exercised views run without browser exceptions');
    return {checks, errors, testProject:pid};
  } finally {
    page.off('pageerror', onError);
    await page.setViewportSize({width:1440,height:1000});
    await page.goto(previous && previous !== pid ? `${origin}/#${previous}` : origin);
    await page.request.delete(`${origin}/api/projects/${pid}`);
  }
}
