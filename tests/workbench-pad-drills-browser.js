async(page,options={})=>{
 const origin=options.origin||'http://127.0.0.1:8770',checks=[];let project;
 try{
  const made=await page.request.post(origin+'/api/workbench/projects',{data:{title:'Native pad drill display',example:true}});if(!made.ok())throw Error(await made.text());project=(await made.json()).id;
  const native=await page.request.post(`${origin}/api/workbench/projects/${project}/native`);if(!native.ok())throw Error(await native.text());const metadata=await native.json(),response=await page.request.get(`${origin}/api/workbench/projects/${project}/layout-geometry`);if(!response.ok())throw Error(await response.text());const geometry=(await response.json()).geometry;
  const round=geometry.pads.filter(p=>p.ref==='J2'&&p.kind==='thru_hole'),slots=geometry.pads.filter(p=>p.drill_shape==='oval');if(metadata.geometry_schema!==geometry.schema||!round.length||round.some(p=>p.drill!==1)||!slots.length||slots.some(p=>Math.min(...p.drill_size)<=0))throw Error('Native API lost circular or slotted pad drills');checks.push('Real KiCad USB-C and header footprints retain their slot and round-hole dimensions');
  await page.goto(origin+'/?pad-drill-render');await page.waitForFunction(()=>!!window.BoardView);
  const pixels=await page.evaluate(async()=>{
   const host=document.createElement('div');host.id='drill-render-acceptance';Object.assign(host.style,{position:'fixed',left:'30px',top:'80px',width:'640px',height:'480px',zIndex:'2000'});document.body.append(host);
   const geo={outline:[{kind:'rect',start:[-5,-4],end:[8,4]}],bbox:[-5,-4,8,4],layers:['F.Cu','B.Cu'],footprints:[],tracks:[],arcs:[],vias:[],zones:[],drawings:[],ratsnest:[],pads:[{ref:'J1',name:'1',x:0,y:0,w:4,h:4,rot:90,shape:'rect',kind:'thru_hole',drill:.8,drill_shape:'oval',drill_size:[.8,2],drill_offset:[.6,-.2],front:true,back:true,net:'SIG',layers:['*.Cu','*.Mask']},{ref:'H1',name:'',x:5,y:0,w:3,h:3,rot:0,shape:'circle',kind:'np_thru_hole',drill:1,drill_shape:'circle',drill_size:[1,1],drill_offset:[0,0],front:true,back:true,net:'',layers:['*.Cu','*.Mask']}]};
   const view=new window.BoardView(host,geo,{editable:true});window.__drillView=view;await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));view.fit();
   const pixel=(x,y)=>Array.from(view.ctx.getImageData(Math.round((x*view.scale+view.ox)*view.dpr),Math.round((y*view.scale+view.oy)*view.dpr),1,1).data);
   // At90 degrees, local(u,v) maps to world(v,-u).
   return{offsetCenter:pixel(-.2,-.6),slotLongAxis:pixel(.5,-.6),padCenter:pixel(0,0),nonplatedHole:pixel(5,0),nonplatedOuter:pixel(6,0),substrate:pixel(7,0)};
  });
  const dark=p=>p[0]<40&&p[1]<40&&p[2]<40;
  if(!dark(pixels.offsetCenter)||!dark(pixels.slotLongAxis)||pixels.padCenter[0]<100)throw Error('The canvas collapses a rotated offset slot into a centered circle: '+JSON.stringify(pixels));checks.push('Canvas pixels show the rotated oval drill at its actual local offset');
  if(!dark(pixels.nonplatedHole)||JSON.stringify(pixels.nonplatedOuter)!==JSON.stringify(pixels.substrate))throw Error('A non-plated hole paints the entire pad as a hole');checks.push('Non-plated openings remove only the drill area rather than an imaginary copper pad');
  const point=await page.evaluate(()=>{const v=window.__drillView,b=v.canvas.getBoundingClientRect();return{x:b.x+v.ox,y:b.y+v.oy};});await page.mouse.move(point.x,point.y);const text=await page.locator('#drill-render-acceptance .board-tip').innerText();if(!text.includes('0.8')||!text.includes('2')||!text.includes('0.6'))throw Error('The pad tooltip omits slot dimensions or offset: '+text);checks.push('Pad hover exposes the native hole size and offset');
  if(options.artifactDir)await page.screenshot({path:options.artifactDir+'/native-pad-drills.png'});await page.evaluate(()=>{window.__drillView.destroy();document.querySelector('#drill-render-acceptance')?.remove();delete window.__drillView;});return{checks};
 }finally{if(project)await page.request.delete(origin+'/api/projects/'+project);}
}
