// Pending wire geometry stays separate from the saved electrical netlist.
function coordinate(point){
  if(!Array.isArray(point)||point.length!==2||point.some(value=>!Number.isFinite(value)||Math.abs(value)>1_000_000))throw new Error('Wire bends require finite 2D coordinates.');
  return [...point];
}

const close=(a,b)=>Math.abs(a-b)<.0001;
function compact(points){
  const result=[];
  for(const point of points){
    const b=result.at(-1),a=result.at(-2);
    if(b&&close(point[0],b[0])&&close(point[1],b[1]))continue;
    if(a&&((close(a[0],b[0])&&close(b[0],point[0])&&(b[1]-a[1])*(point[1]-b[1])>=0)||(close(a[1],b[1])&&close(b[1],point[1])&&(b[0]-a[0])*(point[0]-b[0])>=0)))result.pop();
    result.push([...point]);
  }
  return result;
}

export class SchematicWireDraft{
  #points;#steps=[];#cursor;#horizontal=true;
  constructor(origin,{escape}={}){this.#points=compact([coordinate(origin),...(escape?[coordinate(escape)]:[])]);this.#cursor=[...this.#points.at(-1)];}
  get points(){return structuredClone(this.#points);}
  get manual(){return this.#steps.length>0||!this.#horizontal;}
  preview(target=this.#cursor){
    target=coordinate(target);const last=this.#points.at(-1),elbow=this.#horizontal?[target[0],last[1]]:[last[0],target[1]];
    return compact([...this.#points,elbow,target]);
  }
  move(target){this.#cursor=coordinate(target).map(value=>Math.round(value/10)*10);return this.preview();}
  flip(){this.#horizontal=!this.#horizontal;return this.preview();}
  bend(target){
    const snapped=coordinate(target).map(value=>Math.round(value/10)*10),last=this.#points.at(-1);
    if(close(last[0],snapped[0])&&close(last[1],snapped[1]))return false;
    const next=this.preview(snapped);
    // Reserve room for the final elbow within the API's 100-waypoint limit.
    if(next.length>100)throw new Error('A wire can contain at most 100 bends. Finish this wire before continuing.');
    this.#steps.push(this.points);this.#points=next;this.#cursor=snapped;return true;
  }
  undo(){if(!this.#steps.length)return false;this.#points=this.#steps.pop();return true;}
  finish(target,{escape}={}){const waypoints=compact([...this.preview(escape||target),coordinate(target)]).slice(1,-1);if(waypoints.length>100)throw new Error('A wire can contain at most 100 bends.');return waypoints;}
}
