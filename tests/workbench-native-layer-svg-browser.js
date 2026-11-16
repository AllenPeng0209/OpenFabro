async(page,options={})=>{
 const checks=[],result=await page.evaluate(async()=>{
  const {compileNativeLayer,paintNativeLayer}=await import('/static/workbench-native-layers.mjs');
  const sample='<svg xmlns="http://www.w3.org/2000/svg" width="297mm" height="210mm" viewBox="0 0 297 210"><g transform="translate(100 100)" style="fill:#ff00ff;fill-opacity:0.5;stroke:none"><path d="M 9 9 L 11 9 L 11 11 L 9 11 Z"/></g></svg>';
  const canvas=document.createElement('canvas');canvas.width=500;canvas.height=400;const c=canvas.getContext('2d');c.setTransform(2,0,0,2,0,0);const compiled=compileNativeLayer(sample);paintNativeLayer(c,compiled,'#00ff00',1);
  const inside=[...c.getImageData(220,220,1,1).data],local=[...c.getImageData(20,20,1,1).data];if(!(inside[1]>200&&inside[3]>100&&inside[3]<150&&local[3]===0))throw Error('Native vectors lost their absolute coordinates, inherited opacity or layer color');
  for(const mode of ['dash','miter']){
   const actual=document.createElement('canvas'),expected=document.createElement('canvas');actual.width=expected.width=100;actual.height=expected.height=100;const d=mode==='dash'?'M10 30 L90 30':'M20 80 L50 10 L80 80',extra=mode==='dash'?'stroke-dasharray:12 8;stroke-dashoffset:5':'stroke-miterlimit:1';
   const svg=`<svg xmlns="http://www.w3.org/2000/svg" width="100mm" height="100mm" viewBox="0 0 100 100"><path d="${d}" style="fill:none;stroke:#000;stroke-width:10;${extra}"/></svg>`;paintNativeLayer(actual.getContext('2d'),compileNativeLayer(svg),'#00ff00');
   const ref=expected.getContext('2d');ref.strokeStyle='#00ff00';ref.lineWidth=10;ref.beginPath();if(mode==='dash'){ref.setLineDash([12,8]);ref.lineDashOffset=5;ref.moveTo(10,30);ref.lineTo(90,30);}else{ref.miterLimit=1;ref.moveTo(20,80);ref.lineTo(50,10);ref.lineTo(80,80);}ref.stroke();if(actual.toDataURL()!==expected.toDataURL())throw Error('Native SVG '+mode+' style is silently ignored');
  }
  const bad=[sample.replace('<g ','<script>throw 1</script><g '),sample.replace('<g ','<image href="https://example.invalid/a.svg"/><g '),sample.replace('<g ','<g onclick="alert(1)" '),sample.replace('fill:#ff00ff','fill:url(https://example.invalid/a.svg)'),sample.replace('viewBox="0 0 297 210"','viewBox="0 0 2970 2100"'),sample.replace('<path ','<foreignObject/> <path ')];
  for(const svg of bad){let rejected=false;try{compileNativeLayer(svg);}catch{rejected=true;}if(!rejected)throw Error('An unsupported or active SVG was accepted by the native layer parser');}
  return{inside,local,rejected:bad.length,compiled:compiled.length};
 });
 checks.push('Native SVG transforms and opacity draw at the actual PCB millimeter coordinates','Layer color is applied without flattening native vector geometry','Scripts, external content, event attributes, paint URLs and incompatible coordinate spaces are rejected');
 checks.push('Native dash offsets and miter limits match independently drawn Canvas reference pixels');
 return{checks,proof:result};
}
