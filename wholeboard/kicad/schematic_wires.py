"""Orthogonal schematic wires between actual emitted symbol pin anchors."""
from __future__ import annotations

from bisect import bisect_left
from collections import defaultdict,deque
import heapq
from itertools import product
import math

EPS = 1e-5
CLEARANCE = .635
CONNECTION_GRID = 1.27
CROSSING_PENALTY = 5.08
POLICY = 'orthogonal-interior-crossings-v2'
MAX_GRID_POINTS = 90_000


def _grid(value,direction=0):
    scaled=value/CONNECTION_GRID
    ticks=math.ceil(scaled-1e-9) if direction>0 else math.floor(scaled+1e-9) if direction<0 else math.floor(scaled+.5)
    return round(ticks*CONNECTION_GRID,5)


def point(value):
    return tuple(round(float(v), 5) for v in value)


def on_segment(p, a, b):
    return (min(a[0], b[0])-EPS <= p[0] <= max(a[0], b[0])+EPS
            and min(a[1], b[1])-EPS <= p[1] <= max(a[1], b[1])+EPS
            and abs((b[0]-a[0])*(p[1]-a[1])-(b[1]-a[1])*(p[0]-a[0])) < EPS)


def _inside(p, box):
    return box[0]+EPS < p[0] < box[2]-EPS and box[1]+EPS < p[1] < box[3]-EPS


def _blocked(a, b, boxes):
    if abs(a[0]-b[0]) > EPS and abs(a[1]-b[1]) > EPS:
        return True
    for box in boxes:
        if abs(a[0]-b[0]) < EPS:
            if box[0]+EPS < a[0] < box[2]-EPS and min(a[1],b[1]) < box[3]-EPS and max(a[1],b[1]) > box[1]+EPS:
                return True
        elif box[1]+EPS < a[1] < box[3]-EPS and min(a[0],b[0]) < box[2]-EPS and max(a[0],b[0]) > box[0]+EPS:
            return True
    return False


def _compress(points):
    result=[]
    for p in points:
        p=point(p)
        if result and p==result[-1]:
            continue
        if len(result)>1 and on_segment(result[-1],result[-2],p):
            result[-1]=p
        else:
            result.append(p)
    return result


def _foreign_intersection(a,b,wire):
    """Classify centerline contact; only perpendicular interior crossings may be unconnected."""
    c,d=wire['a'],wire['b'];horizontal=abs(a[1]-b[1])<EPS;other_horizontal=abs(c[1]-d[1])<EPS
    if horizontal==other_horizontal:
        axis=0 if horizontal else 1
        if abs(a[1-axis]-c[1-axis])<EPS and max(min(a[axis],b[axis]),min(c[axis],d[axis]))<=min(max(a[axis],b[axis]),max(c[axis],d[axis]))+EPS:
            return 'contact',None
        return None,None
    h0,h1,v0,v1=(a,b,c,d) if horizontal else (c,d,a,b);at=point((v0[0],h0[1]))
    if not on_segment(at,h0,h1) or not on_segment(at,v0,v1):return None,None
    if math.dist(at,c)<EPS or math.dist(at,d)<EPS:return 'contact',at
    return 'cross',at


def _path_contacts_foreign(path,wires):
    # A* visibility nodes are temporary. Check compressed final vertices, which become real bends.
    path=_compress(path)
    for a,b in zip(path,path[1:]):
        for wire in wires:
            kind,at=_foreign_intersection(a,b,wire)
            if kind=='contact' or kind=='cross' and (math.dist(at,a)<EPS or math.dist(at,b)<EPS):return True
    return False


def _path(start, end, boxes, wires=(), *, diagnostics=None):
    start,end=point(start),point(end)
    if start==end:
        return [start]
    if any(_inside(start,b) or _inside(end,b) for b in boxes):
        return None
    xs={start[0],end[0]};ys={start[1],end[1]}
    for x0,y0,x1,y1 in [*boxes,*[_wire_box(wire) for wire in wires]]:
        xs.update((_grid(x0,-1),_grid(x1,1)));ys.update((_grid(y0,-1),_grid(y1,1)))
    xs.update((min(xs)-2.54,max(xs)+2.54));ys.update((min(ys)-2.54,max(ys)+2.54))
    xs,ys=sorted(xs),sorted(ys)
    if len(xs)*len(ys)>MAX_GRID_POINTS:
        if diagnostics is not None:diagnostics.update(status='grid_limit',grid_points=len(xs)*len(ys),grid_limit=MAX_GRID_POINTS)
        return None
    first=(bisect_left(xs,start[0]),bisect_left(ys,start[1]),2)
    target=(bisect_left(xs,end[0]),bisect_left(ys,end[1]))
    distances={first:0.0};parents={};queue=[(0.0,0.0,first)];clear={}
    while queue:
        _,cost,state=heapq.heappop(queue)
        if cost>distances[state]+EPS:
            continue
        i,j,direction=state
        if (i,j)==target:
            path=[]
            while state in parents:
                path.append((xs[state[0]],ys[state[1]]));state=parents[state]
            return _compress([start,*reversed(path)])
        for ni,nj,axis in ((i+1,j,0),(i-1,j,0),(i,j+1,1),(i,j-1,1)):
            if not 0<=ni<len(xs) or not 0<=nj<len(ys):
                continue
            a,b=(xs[i],ys[j]),(xs[ni],ys[nj])
            key=tuple(sorted(((i,j),(ni,nj))))
            if key not in clear:
                clear[key]=not _blocked(a,b,boxes)
            if not clear[key]:
                continue
            crossings=0;contact=False
            for wire in wires:
                kind,at=_foreign_intersection(a,b,wire)
                if kind=='contact':contact=True;break
                # Entering an interior crossing is legal only as a straight-through path. Any turn
                # would run along the foreign wire and is rejected as collinear contact on its edge.
                if kind=='cross' and math.dist(at,a)>=EPS:crossings+=1
            if contact:continue
            candidate=cost+abs(a[0]-b[0])+abs(a[1]-b[1])+(.2 if direction!=2 and direction!=axis else 0)+crossings*CROSSING_PENALTY
            next_state=(ni,nj,axis)
            if candidate+EPS<distances.get(next_state,math.inf):
                distances[next_state]=candidate;parents[next_state]=state
                priority=candidate+abs(b[0]-end[0])+abs(b[1]-end[1])
                heapq.heappush(queue,(priority,candidate,next_state))
    return None


def _escape(pin, box):
    x,y=pin["point"];angle=math.radians(pin["angle"])
    dx,dy=round(math.cos(angle)),round(-math.sin(angle))
    if dx:
        return point((_grid(max(x+1.27,box[2]+2*CLEARANCE),1) if dx>0 else _grid(min(x-1.27,box[0]-2*CLEARANCE),-1),y))
    return point((x,_grid(max(y+1.27,box[3]+2*CLEARANCE),1) if dy>0 else _grid(min(y-1.27,box[1]-2*CLEARANCE),-1)))


def validate_guides(guides):
    if not isinstance(guides,list) or len(guides)>5000:
        raise ValueError("Wire routes must be a bounded list.")
    ids={}
    for index,guide in enumerate(guides):
        if not isinstance(guide,dict) or not all(isinstance(guide.get(k),str) for k in ('from','to')):
            raise ValueError("Wire routes need pin anchors.")
        identifier=guide.get('id',f'wire-{index}')
        if not isinstance(identifier,str) or not identifier or len(identifier)>100 or not identifier.isprintable() or identifier in ids:
            raise ValueError("Wire route IDs must be unique bounded printable strings.")
        ids[identifier]=index
        waypoints=guide.get('waypoints',[])
        if not isinstance(waypoints,list) or len(waypoints)>100 or any(not isinstance(p,list) or len(p)!=2 or any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or abs(v)>1_000_000 for v in p) for p in waypoints):
            raise ValueError('Wire waypoints need at most 100 bounded finite 2D bend points.')
        fixed=guide.get('fixed_points')
        if fixed is not None:
            if not isinstance(fixed,list) or not 2<=len(fixed)<=200 or any(not isinstance(p,list) or len(p)!=2 or any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or abs(v)>1_000_000 for v in p) for p in fixed):raise ValueError('Exact wire spans need 2 to 200 bounded finite points.')
            if any(a==b or abs(a[0]-b[0])>EPS and abs(a[1]-b[1])>EPS for a,b in zip(fixed,fixed[1:])):raise ValueError('Exact wire spans must be nonzero orthogonal segments.')
    for identifier,index in ids.items():
        for key in ('from_join','to_join'):
            join=guides[index].get(key)
            if join is None:continue
            if not isinstance(join,dict) or not isinstance(join.get('wire'),str) or join['wire'] not in ids:
                raise ValueError("A wire junction must reference an existing route.")
            offset=join.get('offset')
            if isinstance(offset,bool) or not isinstance(offset,(int,float)) or not math.isfinite(offset) or not 0<=offset<=1:
                raise ValueError("Wire junction offsets must be finite fractions between zero and one.")
    _guide_order(guides,ids)
    return ids


def _guide_order(guides,ids):
    children=defaultdict(list);degrees={identifier:0 for identifier in ids}
    for identifier,index in ids.items():
        parents={guides[index][key]['wire'] for key in ('from_join','to_join') if guides[index].get(key)}
        degrees[identifier]=len(parents)
        for parent in parents:children[parent].append(identifier)
    ready=deque(identifier for identifier in ids if not degrees[identifier]);ordered=[]
    while ready:
        identifier=ready.popleft();ordered.append(ids[identifier])
        for child in children[identifier]:
            degrees[child]-=1
            if degrees[child]==0:ready.append(child)
    if len(ordered)!=len(ids):raise ValueError('Wire junctions cannot form a dependency cycle.')
    return ordered


def _along(points,offset):
    lengths=[math.dist(a,b) for a,b in zip(points,points[1:])]
    remaining=offset*sum(lengths)
    for a,b,length in zip(points,points[1:],lengths):
        if remaining<=length+EPS:
            fraction=min(1,remaining/length) if length else 0
            at=[a[0]+fraction*(b[0]-a[0]),a[1]+fraction*(b[1]-a[1])]
            if EPS<offset<1-EPS:
                axis=0 if abs(a[1]-b[1])<EPS else 1
                at[axis]=min(max(a[axis],b[axis]),max(min(a[axis],b[axis]),_grid(at[axis])))
            return point(at)
        remaining-=length
    return point(points[-1])


def _join_escapes(at,parent,towards,boxes):
    used=set()
    for a,b in zip(parent['points'],parent['points'][1:]):
        if on_segment(at,a,b):
            for end in (a,b):
                if math.dist(at,end)>EPS:used.add((int(math.copysign(1,end[0]-at[0])) if abs(end[0]-at[0])>EPS else 0,int(math.copysign(1,end[1]-at[1])) if abs(end[1]-at[1])>EPS else 0))
    directions=[d for d in ((1,0),(-1,0),(0,1),(0,-1)) if d not in used]
    if not directions:directions=[(0,1)]
    candidates=[point((at[0]+d[0]*1.27,at[1]+d[1]*1.27)) for d in directions]
    return sorted(candidates,key=lambda candidate:math.dist(candidate,towards)+(1_000_000 if any(_inside(candidate,b) for b in boxes) else 0))


def _wire_box(wire,padding=.127):
    x0,x1=sorted((wire['a'][0],wire['b'][0]));y0,y1=sorted((wire['a'][1],wire['b'][1]))
    return (x0-padding,y0-padding,x1+padding,y1+padding)


def _existing_span(points,start,end):
    distances=[0.0]
    for a,b in zip(points,points[1:]):distances.append(distances[-1]+math.dist(a,b))
    def locate(at):
        for index,(a,b) in enumerate(zip(points,points[1:])):
            if on_segment(at,a,b):return distances[index]+math.dist(a,at)
        return None
    first,last=locate(start),locate(end)
    if first is None or last is None:return None
    low,high=sorted((first,last));middle=[p for p,distance in zip(points,distances) if low+EPS<distance<high-EPS]
    if first>last:middle.reverse()
    return _compress([start,*middle,end])


def routes(guides, pins, boxes, *, scale=.127, origin=20.32, initial_segments=()):
    """Resolve pin and wire-junction endpoints before emitting checked native geometry."""
    ids=validate_guides(guides);paths={};emitted=[]
    for segment in initial_segments:
        a,b=point(segment['a']),point(segment['b']);net=segment['net']
        if a==b or abs(a[0]-b[0])>EPS and abs(a[1]-b[1])>EPS:raise ValueError('Terminal stub segments must be nonzero and orthogonal.')
        if _path_contacts_foreign([a,b],[wire for wire in emitted if wire['net']!=net]) or any(on_segment(pin['point'],a,b) for pin in pins.values() if pin['net']!=net):
            raise ValueError('A terminal stub would contact another net. Separate the sheet ports or labels.')
        emitted.append({'net':net,'a':a,'b':b})
    expanded={key:(b[0]-CLEARANCE,b[1]-CLEARANCE,b[2]+CLEARANCE,b[3]+CLEARANCE) for key,b in boxes.items()}
    def route(index):
        if index in paths:return paths[index]
        guide=guides[index];a,b=pins.get(guide['from']),pins.get(guide['to'])
        if not a or not b:return None
        info={'id':guide.get('id',f'wire-{index}'),'index':index,'from':guide['from'],'to':guide['to'],'net':a['net'],'status':'unroutable','points':[],'joins':{}}
        paths[index]=info
        if not a['net'] or a['net']!=b['net']:
            info['reason']='The pins are not in the same saved electrical net.';return info
        parents={};endpoints={}
        for key,pin,opposite in (('from',a,b),('to',b,a)):
            join=guide.get(key+'_join')
            if join:
                parent=route(ids[join['wire']])
                if not parent or parent['status']!='routed' or parent['net']!=a['net']:
                    info['reason']='The parent wire is unavailable on this sheet or net.';return info
                at=_along(parent['points'],join['offset']);escapes=_join_escapes(at,parent,opposite['point'],list(expanded.values()))
                endpoints[key]=(at,escapes);parents[parent['id']]=parent
                info['joins'][key]={'wire':join['wire'],'offset':join['offset'],'point':at}
            else:
                if pin.get('hidden'):
                    info['reason']='Hidden pins use their net labels.';return info
                endpoints[key]=(point(pin['point']),[point(pin['point']) if pin.get('free') else _escape(pin,boxes[pin['symbol']])])
        pa,starts=endpoints['from'];pb,ends=endpoints['to'];local=dict(expanded)
        fixed=guide.get('fixed_points')
        if fixed:
            path=[point((origin+p[0]*scale,origin+p[1]*scale)) for p in fixed]
            if math.dist(path[0],pa)<EPS and math.dist(path[-1],pb)<EPS:
                normalized=_compress(path);foreign_wires=[wire for wire in emitted if wire['net']!=a['net']]
                if _path_contacts_foreign(normalized,foreign_wires):
                    info.update(reason='The exact wire span would contact another net.',points=path);return info
                for k,(x,y) in enumerate(zip(normalized,normalized[1:])):
                    exempt={pin.get('symbol') for pin,active in ((a,k==0),(b,k==len(normalized)-2)) if active and not pin.get('free')}
                    boxes_to_check=[rect for owner,rect in expanded.items() if owner not in exempt]
                    if _blocked(x,y,boxes_to_check) or any(on_segment(pin['point'],x,y) for pin in pins.values() if pin['net']!=a['net']):
                        info.update(reason='The exact wire span would contact another net or cross a symbol.',points=path);return info
                info.update(status='routed',points=path,fixed_path=True)
                emitted.extend({'net':a['net'],'a':x,'b':y} for x,y in zip(normalized,normalized[1:]));return info
            info['fixed_path']=False
        if guide.get('from_join') and guide.get('to_join') and not guide.get('waypoints'):
            for parent in parents.values():
                shared=_existing_span(parent['points'],pa,pb)
                if shared is not None:
                    info.update(status='routed',points=shared,reused_parent=parent['id'])
                    emitted.extend({'net':a['net'],'a':x,'b':y} for x,y in zip(shared,shared[1:]));return info
        for key,pin,escape in (('from',a,starts[0]),('to',b,ends[0])):
            if guide.get(key+'_join') or pin.get('free'):continue
            rect=list(local[pin['symbol']]);x,y=pin['point']
            if escape[0]<x-EPS:rect[0]=min(rect[0],escape[0])
            if escape[0]>x+EPS:rect[2]=max(rect[2],escape[0])
            if escape[1]<y-EPS:rect[1]=min(rect[1],escape[1])
            if escape[1]>y+EPS:rect[3]=max(rect[3],escape[1])
            local[pin['symbol']]=tuple(rect)
        other_wires=[wire for wire in emitted if wire['net']!=a['net']]
        obstacles=list(local.values())
        for parent in parents.values():
            obstacles.extend(_wire_box({'a':x,'b':y}) for x,y in zip(parent['points'],parent['points'][1:]))
        for sa,sb in product(starts,ends):
            invalid=False
            for key,pin,at,escape in (('from',a,pa,sa),('to',b,pb,sb)):
                blocked=[rect for owner,rect in expanded.items() if guide.get(key+'_join') or owner!=pin.get('symbol')]
                if _blocked(at,escape,blocked):
                    info['reason']='The pin or junction exit overlaps a symbol. Move the junction or symbols.';invalid=True;break
            if invalid:continue
            stops=[sa,*[point((origin+p[0]*scale,origin+p[1]*scale)) for p in guide.get('waypoints',[])],sb]
            info['points']=_compress([pa,*stops,pb]);path=[pa]
            for start,end in zip(stops,stops[1:]):
                diagnostics={};leg=_path(start,end,obstacles,other_wires,diagnostics=diagnostics)
                if leg is None:
                    if diagnostics.get('status')=='grid_limit':
                        info['reason']='Routing exceeds the search budget. Simplify this schematic sheet or split it into smaller sheets.';info['search']=diagnostics
                    else:info['reason']='No clear wire path; move a bend or separate the symbols.'
                    path=[];break
                path.extend(leg)
            if not path:continue
            path=_compress([*path,pb])
            if _path_contacts_foreign(path,other_wires):
                info['reason']='The wire endpoint, bend, or overlap would contact another net.';continue
            foreign=[pin['point'] for pin in pins.values() if pin['net']!=a['net']]
            if any(on_segment(pin,x,y) for pin in foreign for x,y in zip(path,path[1:])):
                info['reason']='The wire would contact another net or an unconnected pin.';continue
            info.update(status='routed',points=path);info.pop('reason',None)
            emitted.extend({'net':a['net'],'a':x,'b':y} for x,y in zip(path,path[1:]));break
        return info
    for index in _guide_order(guides,ids):route(index)
    return [paths[index] for index in sorted(paths)],merge(emitted)


def merge(segments):
    """Merge shared collinear copper-free schematic branches and find junctions."""
    groups=defaultdict(list)
    for segment in segments:
        a,b=segment["a"],segment["b"]
        horizontal=abs(a[1]-b[1])<EPS
        fixed=a[1] if horizontal else a[0]
        groups[(segment["net"],horizontal,round(fixed,5))].append(sorted((a[0],b[0]) if horizontal else (a[1],b[1])))
    merged=[]
    for (net,horizontal,fixed),intervals in groups.items():
        intervals.sort();ranges=[]
        for low,high in intervals:
            if high-low<EPS:
                continue
            if ranges and low<=ranges[-1][1]+EPS:
                ranges[-1][1]=max(high,ranges[-1][1])
            else:
                ranges.append([low,high])
        for low,high in ranges:
            merged.append({"net":net,"a":(low,fixed) if horizontal else (fixed,low),"b":(high,fixed) if horizontal else (fixed,high)})
    junctions={}
    for i,a in enumerate(merged):
        ah=abs(a["a"][1]-a["b"][1])<EPS
        for b in merged[i+1:]:
            bh=abs(b["a"][1]-b["b"][1])<EPS
            if a["net"]!=b["net"] or ah==bh:
                continue
            h,v=(a,b) if ah else (b,a);p=(v["a"][0],h["a"][1])
            if not on_segment(p,h["a"],h["b"]) or not on_segment(p,v["a"],v["b"]):
                continue
            directions=(int(p[0]>h["a"][0]+EPS)+int(p[0]<h["b"][0]-EPS)+int(p[1]>v["a"][1]+EPS)+int(p[1]<v["b"][1]-EPS))
            if directions>=3:
                junctions[p]=a["net"]
    return {"segments":merged,"junctions":[{"point":p,"net":net} for p,net in junctions.items()]}
