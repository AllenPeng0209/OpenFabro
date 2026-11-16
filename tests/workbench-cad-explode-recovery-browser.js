async(page,options={})=>{
 const result=await page.evaluate(async()=>{
  const prefix=new URL(document.querySelector('script[src*="workbench.mjs"]').src).pathname.replace(/workbench\.mjs.*$/,'');const {CADView}=await import(prefix+'workbench-cad.mjs'),{CADViewUI}=await import(prefix+'workbench-cad-ui.mjs');
  const host=document.createElement('div');host.style.cssText='position:fixed;left:0;top:0;width:400px;height:300px;z-index:9999';document.body.append(host);const tools=document.createElement('div'),slider=document.createElement('input');slider.type='range';slider.id='explodeSlider';document.body.append(tools,slider);const data={size:[20,10,4],meshes:[{name:'PCB',group:'board',color:'#88aabb',v:[0,0,1,20,0,1,0,10,1],t:[0,1,2]}]};
  const state={pid:'isolated-explode-recovery',project:{},active:'3d',canvas:new CADView(host,data)},ui=new CADViewUI({state:()=>state,toast:()=>{}});
  try{ui.attach(state.canvas);tools.innerHTML=ui.panel();ui.mount(tools);tools.querySelector('#cadMeasure').click();const before={measuring:state.canvas.measureMode,disabled:slider.disabled};tools.remove();ui.capture(state.canvas);state.canvas.destroy();state.canvas=new CADView(host,data);ui.attach(state.canvas);return{before,after:{measuring:state.canvas.measureMode,disabled:slider.disabled}};}
  finally{state.canvas.destroy();host.remove();tools.remove();slider.remove();localStorage.removeItem('wb-cad-view:device:isolated-explode-recovery');}
 });
 if(!result.before.measuring||!result.before.disabled||result.after.measuring||result.after.disabled)throw Error('Replacing a measured model with its pane closed left explosion disabled: '+JSON.stringify(result));return{checks:['Replacing a measured viewer releases the explode slider even when its tool pane is closed'],result};
}
