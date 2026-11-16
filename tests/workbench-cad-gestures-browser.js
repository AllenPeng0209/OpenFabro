async(page,options={})=>{
 const checks=[];
 await page.evaluate(async()=>{
  const prefix=new URL(document.querySelector('script[src*="workbench.mjs"]').src).pathname.replace(/workbench\.mjs.*$/,'');
  const {CADView}=await import(prefix+'workbench-cad.mjs'),{CADViewUI}=await import(prefix+'workbench-cad-ui.mjs');
  const host=document.createElement('div');host.id='qaCADHost';host.style.cssText='position:fixed;left:0;top:0;width:500px;height:400px;z-index:9999';document.body.append(host);
  const view=new CADView(host,{size:[10,10,4],meshes:[{name:'PCB',group:'board',color:'#88aabb',v:[0,0,1,10,0,1,0,10,1],t:[0,1,2]}]});
  const state={pid:'isolated-cad-gesture',project:{},active:'3d',canvas:view};const ui=new CADViewUI({state:()=>state,toast:()=>{},interacting:()=>!!view.interacting});ui.attach(view);
  window.qaCADGesture={host,view,ui};
 });
 try{
  await page.mouse.move(250,300);await page.mouse.down();const active=await page.evaluate(()=>window.qaCADGesture.view.interacting);if(active!==true)throw Error('The renderer does not expose an active orbit gesture to display guards');
  await page.evaluate(()=>window.qaCADGesture.ui.change({style:'xray'},true));if(await page.evaluate(()=>window.qaCADGesture.view.style)!=='realistic')throw Error('A display update interrupted an active orbit gesture');await page.mouse.move(250,40,{steps:8});await page.mouse.up();
  const orbit=await page.evaluate(()=>({pitch:window.qaCADGesture.view.pitch,active:window.qaCADGesture.view.interacting}));if(orbit.pitch>=0||orbit.active!==false)throw Error('Orbiting cannot inspect the bottom of the board or leaves gesture ownership active');checks.push('Active orbit suppresses display changes and can inspect the underside of a board');
  await page.mouse.move(250,300);await page.mouse.down();await page.evaluate(()=>{const c=window.qaCADGesture.view.canvas;c.dispatchEvent(new PointerEvent('pointercancel',{pointerId:1,bubbles:true}));});await page.mouse.up();await page.evaluate(()=>window.qaCADGesture.ui.change({style:'xray'},true));if(await page.evaluate(()=>window.qaCADGesture.view.style)!=='xray')throw Error('A cancelled pointer left 3D controls locked');checks.push('Pointer cancellation releases the gesture guard for subsequent display changes');
  await page.evaluate(()=>{const fixture=window.qaCADGesture;fixture.view.destroy();fixture.host.replaceChildren();fixture.view=new window.MeshView(fixture.host,{size:[10,10,4],meshes:[{name:'PCB',group:'board',color:'#88aabb',v:[0,0,1,10,0,1,0,10,1],t:[0,1,2]}]});fixture.ui.state=()=>({pid:'isolated-cad-gesture',project:{},active:'3d',canvas:fixture.view});fixture.ui.interacting=()=>!!fixture.view.interacting;fixture.ui.attach(fixture.view);});
  await page.mouse.move(250,300);await page.mouse.down();const software=await page.evaluate(()=>{const f=window.qaCADGesture;f.ui.change({top:false});return{active:f.view.interacting,top:f.view.show.top};});await page.mouse.up();if(software.active!==true||software.top!==true)throw Error('Software orbit allows display changes during the gesture');await page.evaluate(()=>window.qaCADGesture.ui.change({top:false}));if(await page.evaluate(()=>window.qaCADGesture.view.show.top)!==false)throw Error('Software orbit leaves display controls locked after release');checks.push('Software orbit uses the same active-gesture guard and releases it on pointer up');
  return{checks};
 }finally{await page.mouse.up();await page.evaluate(()=>{window.qaCADGesture.view.destroy();window.qaCADGesture.host.remove();delete window.qaCADGesture;localStorage.removeItem('wb-cad-view:device:isolated-cad-gesture');});}
}
