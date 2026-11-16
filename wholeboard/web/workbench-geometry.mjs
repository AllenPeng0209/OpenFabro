// STEP scene vertices are rebased for display; origin restores PCB-local millimetres.
export function combineAssembly(enclosure, board) {
  const anchor=enclosure.meshes.find(m=>m.name==='Board');
  if(!anchor?.v?.length)throw new Error('The enclosure has no board reference geometry.');
  const offset=[0,1,2].map(axis=>Math.min(...anchor.v.filter((_,i)=>i%3===axis))+(board.origin?.[axis]||0));
  const native=board.meshes.map(m=>({...m,v:m.v.map((n,i)=>n+offset[i%3])}));
  return {...enclosure,source:'native-step-and-freecad-enclosure',meshes:[...enclosure.meshes.filter(m=>!['board','parts'].includes(m.group)),...native]};
}

export function arcThroughPoints(a,m,b){
  const [ax,ay]=a,[mx,my]=m,[bx,by]=b;
  const d=2*(ax*(my-by)+mx*(by-ay)+bx*(ay-my));if(Math.abs(d)<1e-10)return null;
  const aa=ax*ax+ay*ay,mm=mx*mx+my*my,bb=bx*bx+by*by;
  const x=(aa*(my-by)+mm*(by-ay)+bb*(ay-my))/d,y=(aa*(bx-mx)+mm*(ax-bx)+bb*(mx-ax))/d;
  const normalize=n=>(n+Math.PI*4)%(Math.PI*2),start=Math.atan2(ay-y,ax-x),middle=Math.atan2(my-y,mx-x),end=Math.atan2(by-y,bx-x);
  const sweep=normalize(middle-start)<normalize(end-start)?1:0,span=sweep?normalize(end-start):normalize(start-end);
  return{center:[Object.is(x,-0)?0:x,Object.is(y,-0)?0:y],radius:Math.hypot(ax-x,ay-y),sweep,large:span>Math.PI+1e-10?1:0};
}
