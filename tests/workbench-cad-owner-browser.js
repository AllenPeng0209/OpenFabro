async(page,options={})=>{
 const result=await page.evaluate(async()=>{
  const prefix=new URL(document.querySelector('script[src*="workbench.mjs"]').src).pathname.replace(/workbench\.mjs.*$/,'');
  const {CADView}=await import(prefix+'workbench-cad.mjs'),{CADViewUI}=await import(prefix+'workbench-cad-ui.mjs');
  const host=document.createElement('div');host.style.cssText='position:fixed;left:0;top:0;width:400px;height:300px;z-index:9999';document.body.append(host);const tools=document.createElement('div');document.body.append(tools);
  const view=new CADView(host,{size:[10,10,4],meshes:[{name:'PCB',group:'board',color:'#88aabb',v:[0,0,1,10,0,1,0,10,1],t:[0,1,2]}]});
  const state={pid:'isolated-cad-owner',project:{},session:{user:{id:'alice'}},active:'3d',canvas:view};const ui=new CADViewUI({state:()=>state,toast:()=>{}});
  try{
   ui.attach(view);tools.innerHTML=ui.panel();ui.mount(tools);const old=tools.querySelector('#cadStyle');
   view.yaw=1.2;view.pitch=-.4;view.zoom=2;view.pan.set(7,8,9);view.draw();
   state.session.user.id='bob';ui.apply();const newActor={yaw:view.yaw,zoom:view.zoom,pan:view.pan.toArray(),owner:view.displayOwner};
   tools.innerHTML=ui.panel();ui.mount(tools);old.value='xray';old.dispatchEvent(new Event('change',{bubbles:true}));const staleStyle=view.style;
   view.yaw=.2;view.zoom=3;view.pan.set(1,2,3);ui.capture(view);state.session.user.id='alice';ui.apply();const returned={yaw:view.yaw,zoom:view.zoom,pan:view.pan.toArray(),owner:view.displayOwner};
   return{newActor,staleStyle,returned};
  }finally{view.destroy();host.remove();tools.remove();localStorage.removeItem('wb-cad-view:alice:isolated-cad-owner');localStorage.removeItem('wb-cad-view:bob:isolated-cad-owner');}
 });
 if(result.newActor.zoom!==1||JSON.stringify(result.newActor.pan)!=='[0,0,0]'||result.newActor.owner!=='wb-cad-view:bob:isolated-cad-owner')throw Error('A new actor inherited the previous camera or retained its ownership: '+JSON.stringify(result));
 if(result.returned.zoom!==2||result.returned.yaw!==1.2||JSON.stringify(result.returned.pan)!=='[7,8,9]')throw Error('Camera changes were saved into another actor scope');
 if(result.staleStyle!=='realistic')throw Error('A stale detached selector changed the replacement actor preview');
 return{checks:['Camera ownership changes reset new actors and restore the original actor pose','Detached panel controls cannot mutate a replacement owner'],result};
}
