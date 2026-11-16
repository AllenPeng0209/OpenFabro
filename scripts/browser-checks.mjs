// These suites exercise real Python APIs and KiCad. They do not make model calls.
import {chromium} from 'playwright';
import {spawn,execFile} from 'node:child_process';
import {promisify} from 'node:util';
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import net from 'node:net';

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const python=path.join(root,'.venv/bin/python');
const run=promisify(execFile),stamp=Date.now().toString()+process.pid.toString().padStart(7,'0');
const directory=path.join(root,'.local','browser-checks-'+stamp);
const artifacts=path.join(root,'test-results','browser-checks-'+stamp);
const servers=[],results=[];
let browser,passed=false;
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const freePort=()=>new Promise((resolve,reject)=>{const server=net.createServer();server.on('error',reject);server.listen(0,'127.0.0.1',()=>{const port=server.address().port;server.close(()=>resolve(port));});});

async function workspace(name){
  const folder=path.join(directory,name),home=path.join(folder,'config');
  await fs.mkdir(folder,{recursive:true});
  const env={...process.env,OPENFABRO_HOME:home};
  if(name==='ai-changes'){
    const bin=path.join(folder,'fixture-bin');await fs.mkdir(bin,{recursive:true});await fs.copyFile(path.join(root,'tests/fixtures/fake-codex-ai-changes.py'),path.join(bin,'codex'));await fs.chmod(path.join(bin,'codex'),0o755);env.PATH=bin+path.delimiter+env.PATH;
  }
  const prepared=await run(python,['scripts/prepare_browser_workspace.py','--directory',folder,'--fixture','tests/fixtures/recorded-usb-c-estimate.json'],{cwd:root,env});
  const fixtureId=prepared.stdout.trim(),port=await freePort(),origin=`http://127.0.0.1:${port}`;
  const child=spawn(python,['-m','openfabro','--host','127.0.0.1','--port',String(port),'--no-browser'],{cwd:root,env,stdio:['ignore','pipe','pipe']});
  const server={child,logs:'',origin,fixtureId};servers.push(server);
  const collect=data=>{server.logs=(server.logs+data.toString()).slice(-32_000);};child.stdout.on('data',collect);child.stderr.on('data',collect);
  const deadline=Date.now()+30_000;
  while(Date.now()<deadline){
    if(child.exitCode!==null)throw new Error(`The isolated ${name} server exited: ${server.logs}`);
    try{if((await fetch(origin+'/api/workbench/example')).ok)return server;}catch{}
    await pause(150);
  }
  throw new Error(`The isolated ${name} server did not start: ${server.logs}`);
}

async function stopServer(server){
  if(server.child.exitCode!==null||server.child.signalCode!==null)return;
  server.child.kill('SIGTERM');
  let timer;
  await Promise.race([new Promise(resolve=>server.child.once('exit',resolve)),new Promise(resolve=>{timer=setTimeout(resolve,10_000);})]);
  clearTimeout(timer);
  if(server.child.exitCode===null&&server.child.signalCode===null)server.child.kill('SIGKILL');
}

try{
  await fs.mkdir(artifacts,{recursive:true});
  const editor=await workspace('editor'),collaboration=await workspace('collaboration');
  browser=await chromium.launch({headless:!process.argv.includes('--headed')});
  const suites=['workbench-browser.js','workbench-schematic-browser.js','workbench-wire-joins-browser.js','workbench-native-browser.js','workbench-selection-browser.js','workbench-pcb-layers-browser.js','workbench-copper-browser.js','workbench-routing-browser.js','workbench-manufacturing-browser.js','workbench-library-browser.js','workbench-collaboration-browser.js','workbench-document-sandbox-browser.js'];
  suites.push('workbench-sheets-browser.js');
  suites.push('workbench-modules-browser.js');
  suites.push('workbench-convert-module-browser.js');
  suites.push('workbench-terminals-browser.js');
  suites.push('workbench-schematic-routing-browser.js');
  suites.push('workbench-wire-nodes-browser.js');
  suites.push('workbench-wire-cuts-browser.js');
  suites.push('workbench-module-updates-browser.js');
  suites.push('workbench-net-labels-browser.js');
  suites.push('workbench-pad-drills-browser.js');
  suites.push('workbench-pad-holes-browser.js');
  suites.push('workbench-pad-contours-browser.js');
  suites.push('workbench-pad-shapes-browser.js');
  suites.push('workbench-pad-shape-owner-browser.js');
  suites.push('workbench-custom-pad-renderer-browser.js');
  suites.push('workbench-layout-pads-browser.js');
  suites.push('workbench-layout-pads-owner-browser.js');
  suites.push('workbench-layout-pads-layers-browser.js');
  suites.push('workbench-buses-browser.js');
  suites.push('workbench-transforms-browser.js');
  suites.push('workbench-arrange-browser.js');
  suites.push('workbench-schematic-crossings-browser.js');
  suites.push('workbench-component-hotkeys-browser.js');
  suites.push('workbench-layer-view-browser.js');
  suites.push('workbench-native-layer-svg-browser.js');
  suites.push('workbench-project-loading-browser.js');
  suites.push('workbench-document-preview-browser.js');
  suites.push('workbench-shortcuts-browser.js');
  suites.push('workbench-objects-browser.js');
  suites.push('workbench-object-groups-browser.js');
  suites.push('workbench-parametric-browser.js');
  suites.push('workbench-design-identity-browser.js');
  suites.push('workbench-checks-browser.js');
  suites.push('workbench-markup-browser.js');
  suites.push('workbench-canvas-context-browser.js');
  suites.push('workbench-canvas-review-browser.js');
  suites.push('workbench-pane-stack-browser.js');
  suites.push('workbench-pane-actions-browser.js');
  suites.push('workbench-pane-resize-browser.js');
  suites.push('workbench-pane-owner-browser.js');
  suites.push('workbench-schematic-display-browser.js');
  suites.push('workbench-comments-scope-browser.js');
  suites.push('workbench-schematic-display-loading-browser.js');
  suites.push('workbench-comment-owner-browser.js');
  suites.push('workbench-comment-replies-browser.js');
  suites.push('workbench-display-typing-browser.js');
  suites.push('workbench-comment-recovery-browser.js');
  suites.push('workbench-access-refresh-browser.js');
  suites.push('workbench-comment-timeout-browser.js');
  suites.push('workbench-schematic-toolbar-browser.js');
  suites.push('workbench-cad-view-browser.js');
  suites.push('workbench-cad-renderer-browser.js');
  suites.push('workbench-cad-gestures-browser.js');
  suites.push('workbench-cad-owner-browser.js');
  suites.push('workbench-cad-navigation-browser.js');
  suites.push('workbench-cad-lifecycle-browser.js');
  suites.push('workbench-cad-toolbar-browser.js');
  suites.push('workbench-cad-explode-recovery-browser.js');
  suites.push('workbench-cad-context-browser.js');
  suites.push('workbench-cad-release-fallback-browser.js');
  suites.push('workbench-navigation-browser.js');
  suites.push('workbench-camera-renderer-browser.js');
  suites.push('workbench-navigation-pose-browser.js');
  suites.push('workbench-navigation-keyboard-browser.js');
  suites.push('workbench-navigation-lifecycle-browser.js');
  suites.push('workbench-navigation-retained-browser.js');
  suites.push('workbench-navigation-space-browser.js');
  suites.push('workbench-diff-pair-browser.js');
  suites.push('workbench-diff-pair-modifier-browser.js');
  suites.push('workbench-route-tuning-browser.js');
  suites.push('workbench-route-tuning-lifecycle-browser.js');
  suites.push('workbench-selective-routing-browser.js');
  suites.push('workbench-selective-routing-repair-browser.js');
  suites.push('workbench-route-obstacles-browser.js');
  suites.push('workbench-route-offgrid-browser.js');
  suites.push('workbench-ai-changes-browser.js');
  suites.push('workbench-file-tree-browser.js');
  suites.push('workbench-design-source-browser.js');
  suites.push('workbench-draft-recovery-browser.js');
  suites.push('workbench-draft-recovery-races-browser.js');
  suites.push('workbench-interface-presets-browser.js');
  suites.push('workbench-interface-owner-browser.js');
  suites.push('workbench-stackup-browser.js');
  suites.push('workbench-stackup-owner-browser.js');
  suites.push('production-browser.js');
  const filter=process.argv.find(argument=>argument.startsWith('--suite='))?.slice(8);
  const aiChanges=(!filter||'workbench-ai-changes-browser.js'.includes(filter))?await workspace('ai-changes'):null;
  if(process.argv.includes('--mechanical')||filter?.includes('mechanical'))suites.push('workbench-mechanical-browser.js','workbench-mechanical-parts-browser.js','workbench-mechanical-history-browser.js','workbench-mechanical-import-browser.js','workbench-mechanical-mesh-browser.js','workbench-mechanical-asset-owner-browser.js','workbench-mechanical-drawing-browser.js','workbench-mechanical-assembly-browser.js','workbench-mechanical-picking-browser.js','workbench-mechanical-picking-renderer-browser.js','workbench-mechanical-sketch-browser.js','workbench-mechanical-materials-renderer-browser.js','workbench-mechanical-materials-browser.js');
  if(process.argv.includes('--mechanical')||filter?.includes('curvature'))suites.push('workbench-mechanical-curvature-renderer-browser.js','workbench-mechanical-curvature-browser.js');
  if(process.argv.includes('--mechanical')||filter?.includes('surface'))suites.push('workbench-mechanical-surface-renderer-browser.js','workbench-mechanical-surface-browser.js');
  if(process.argv.includes('--mechanical')||filter?.includes('curve-events'))suites.push('workbench-mechanical-curve-events-renderer-browser.js','workbench-mechanical-curve-events-browser.js');
  for(const filename of suites.filter(name=>!filter||name.includes(filter))){
    const server=filename.includes('ai-changes')?aiChanges:filename.includes('collaboration')?collaboration:editor;
    const output=path.join(artifacts,filename.replace('.js',''));await fs.mkdir(output,{recursive:true});
    const context=await browser.newContext({viewport:{width:1440,height:1000},acceptDownloads:true});
    const page=await context.newPage(),errors=[];page.on('pageerror',error=>errors.push(error.message));
    try{
      await page.goto(server.origin+'/?acceptance-start='+Date.now());
      // Test sources are trusted repository code, also runnable in the desktop browser tool.
      const execute=new Function('return ('+await fs.readFile(path.join(root,'tests',filename),'utf8')+');')();
      const suiteOptions={origin:server.origin,fixtureId:server.fixtureId,artifactDir:output};
      if(filename==='workbench-mechanical-import-browser.js')suiteOptions.cadFixtures=path.join(root,'tests/fixtures/mechanical-import');
      if(filename==='workbench-mechanical-mesh-browser.js')suiteOptions.meshFixtures=path.join(root,'tests/fixtures/mesh-import');
      if(filename==='workbench-mechanical-sketch-browser.js')suiteOptions.sketchFixture=JSON.parse(await fs.readFile(path.join(root,'tests/fixtures/sketch/plate.cad.json'),'utf8'));
      if(filename.startsWith('workbench-interface-'))suiteOptions.interfaceFixture=JSON.parse(await fs.readFile(path.join(root,'tests/fixtures/interface-presets.json'),'utf8'));
      if(filename.startsWith('workbench-stackup'))suiteOptions.stackupFixture=JSON.parse(await fs.readFile(path.join(root,'tests/fixtures/interface-presets.json'),'utf8'));
      if(filename==='workbench-mechanical-drawing-browser.js')suiteOptions.drawingFixtures=path.join(root,'tests/fixtures/drawing-import');
      if(filename.startsWith('workbench-diff-pair-'))suiteOptions.pairFixture=JSON.parse(await fs.readFile(path.join(root,'tests/fixtures/differential-routing.json'),'utf8'));
      if(filename.startsWith('workbench-route-tuning-'))suiteOptions.tuningFixture=JSON.parse(await fs.readFile(path.join(root,'tests/fixtures/route-tuning.json'),'utf8'));
      if(['workbench-route-obstacles-browser.js','workbench-route-offgrid-browser.js'].includes(filename))suiteOptions.interactiveFixture=JSON.parse(await fs.readFile(path.join(root,'tests/fixtures/interactive-routing.json'),'utf8'));
      if(filename.startsWith('workbench-selective-routing-')){suiteOptions.routingFixture=JSON.parse(await fs.readFile(path.join(root,'tests/fixtures/selective-routing.json'),'utf8'));suiteOptions.routingRepairFixture=JSON.parse(await fs.readFile(path.join(root,'tests/fixtures/selective-routing-repair.json'),'utf8'));}
      if(['workbench-layer-view-browser.js','workbench-canvas-context-browser.js','workbench-canvas-review-browser.js','workbench-pane-stack-browser.js','workbench-pane-actions-browser.js','workbench-pane-resize-browser.js'].includes(filename))suiteOptions.layerFixture=JSON.parse(await fs.readFile(path.join(root,'tests/fixtures/pcb-layer-view.json'),'utf8'));
      const report=await execute(page,suiteOptions);
      if(errors.length)throw new Error('Browser exceptions: '+errors.join('; '));
      results.push({suite:filename,...report,passed:true});
      process.stdout.write(`PASS ${filename}: ${report.checks.length} checks\n`);
    }catch(error){
      await page.screenshot({path:path.join(output,'failure.png')}).catch(()=>{});
      results.push({suite:filename,passed:false,error:error.stack||error.message});
      process.stderr.write(`FAIL ${filename}: ${error.message}\n`);
    }finally{await context.close();}
  }
  passed=results.length>0&&results.every(result=>result.passed);
  const summary={passed,checks:results.reduce((sum,result)=>sum+(result.checks?.length||0),0),results};
  await fs.writeFile(path.join(artifacts,'report.json'),JSON.stringify(summary,null,2));
  process.stdout.write(`${summary.checks} browser checks; ${results.filter(r=>!r.passed).length} failed suites.\nReport: ${path.relative(root,path.join(artifacts,'report.json'))}\n`);
  process.exitCode=passed?0:1;
}catch(error){process.stderr.write(error.stack+'\n');process.exitCode=1;}
finally{
  await browser?.close();
  await Promise.all(servers.map(stopServer));
  if(passed)await fs.rm(directory,{recursive:true,force:true});
  else process.stderr.write(`Isolated debug workspace kept at ${path.relative(root,directory)}\n`);
}
