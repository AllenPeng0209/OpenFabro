"""Copper islands for the interactive airwire overlay, independent of DRC.

Standard pads are rounded rectangles/capsules, traces are swept segments, and
filled polygons retain their actual boundary. Arcs are tessellated to 1 µm sag
where possible. Native DRC still decides electrical/manufacturing acceptance.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import math

EPS = .00015


def _bounds(points, radius=0):
    return (min(p[0] for p in points)-radius, min(p[1] for p in points)-radius,
            max(p[0] for p in points)+radius, max(p[1] for p in points)+radius)


def _overlap(a, b, margin=EPS):
    return a[0] <= b[2]+margin and b[0] <= a[2]+margin and a[1] <= b[3]+margin and b[1] <= a[3]+margin


def _inside(point, polygon):
    x, y = point
    inside = False
    previous = polygon[-1]
    for current in polygon:
        if (current[1] > y) != (previous[1] > y) and x < (previous[0]-current[0])*(y-current[1])/(previous[1]-current[1])+current[0]:
            inside = not inside
        previous = current
    return inside


def _point_segment2(p, a, b):
    dx, dy = b[0]-a[0], b[1]-a[1]
    length = dx*dx+dy*dy
    t = max(0, min(1, ((p[0]-a[0])*dx+(p[1]-a[1])*dy)/length)) if length else 0
    return (p[0]-a[0]-t*dx)**2+(p[1]-a[1]-t*dy)**2


def _segment_distance2(a, b, c, d):
    def cross(p, q, r):
        return (q[0]-p[0])*(r[1]-p[1])-(q[1]-p[1])*(r[0]-p[0])
    ab_c, ab_d, cd_a, cd_b = cross(a,b,c), cross(a,b,d), cross(c,d,a), cross(c,d,b)
    if ab_c*ab_d <= 0 and cd_a*cd_b <= 0 and _overlap(_bounds((a,b)), _bounds((c,d))):
        return 0
    return min(_point_segment2(a,c,d), _point_segment2(b,c,d), _point_segment2(c,a,b), _point_segment2(d,a,b))


def _feature(points, layers, *, radius=0, closed=False, kind="track", anchors=None):
    points = [tuple(p) for p in points]
    edges = list(zip(points, points[1:]+([points[0]] if closed else []))) if len(points)>1 else [(points[0],points[0])]
    if kind == "zone":
        # KiCad fractures polygon holes using oppositely repeated bridge edges.
        counts = Counter(tuple(sorted((a,b))) for a,b in edges)
        edges = [(a,b) for a,b in edges if counts[tuple(sorted((a,b)))] % 2]
    return {"points": points, "layers": set(layers), "radius": radius, "closed": closed,
            "kind": kind, "anchors": anchors or points, "edges": edges, "bounds": _bounds(points,radius)}


def _touch(a, b):
    if not a["layers"] & b["layers"] or not _overlap(a["bounds"],b["bounds"]):
        return False
    if b["closed"] and any(_inside(p,b["points"]) for p in a["points"]):
        return True
    if a["closed"] and any(_inside(p,a["points"]) for p in b["points"]):
        return True
    radius = a["radius"]+b["radius"]+EPS
    if 'arc' in a and 'arc' in b:return _arc_arc_distance2(a['arc'],b['arc'])<=radius*radius
    if 'arc' in a:return any(_arc_segment_distance2(a['arc'],p,q)<=radius*radius for p,q in b['edges'])
    if 'arc' in b:return any(_arc_segment_distance2(b['arc'],p,q)<=radius*radius for p,q in a['edges'])
    for p,q in a["edges"]:
        box = _bounds((p,q),radius)
        for r,s in b["edges"]:
            if _overlap(box,_bounds((r,s))) and _segment_distance2(p,q,r,s)<=radius*radius:
                return True
    return False


def _pad(p, layers):
    explicit = p.get("layers")
    if explicit:
        active = set(layers) if "*.Cu" in explicit else set(explicit) & set(layers)
    elif p.get("kind")=="thru_hole":
        active = set(layers)
    elif "front" not in p and "back" not in p:
        active = {"F.Cu"}
    else:
        active = ({"F.Cu"} if p.get("front") else set()) | ({"B.Cu"} if p.get("back") else set())
    if p.get("kind")=="np_thru_hole" or not active:
        return None
    if p.get('shape')=='custom' and p.get('copper_polygons'):
        angle=math.radians(p.get('rot',0));co,si=math.cos(angle),math.sin(angle)
        return [_feature([(p['x']+u*co+v*si,p['y']-u*si+v*co) for u,v in polygon],active,closed=True,kind='pad',anchors=[tuple(p.get('routing_anchor') or [p['x'],p['y']])]) for polygon in p['copper_polygons']]
    hw, hh = p["w"]/2, p["h"]/2
    radius = min(hw,hh) if p["shape"] in ("circle","oval") else min(hw,hh)*2*p.get("rratio",.25) if p["shape"]=="roundrect" else 0
    radius = min(radius,hw,hh)
    x,y = max(0,hw-radius),max(0,hh-radius)
    angle = math.radians(p.get("rot",0));co,si=math.cos(angle),math.sin(angle)
    points = [(p["x"]+u*co+v*si,p["y"]-u*si+v*co) for u,v in ((-x,-y),(x,-y),(x,y),(-x,y))]
    return _feature(points,active,radius=radius,closed=True,kind="pad",anchors=[(p["x"],p["y"])])


def _arc_spec(arc):
    a,m,b = arc["a"],arc["m"],arc["b"]
    ax,ay=a;mx,my=m;bx,by=b
    d=2*(ax*(my-by)+mx*(by-ay)+bx*(ay-my))
    if abs(d)<1e-10:
        return None
    aa,mm,bb=ax*ax+ay*ay,mx*mx+my*my,bx*bx+by*by
    x=(aa*(my-by)+mm*(by-ay)+bb*(ay-my))/d
    y=(aa*(bx-mx)+mm*(ax-bx)+bb*(mx-ax))/d
    radius=math.hypot(ax-x,ay-y)
    start,middle,end=[math.atan2(p[1]-y,p[0]-x) for p in (a,m,b)]
    norm=lambda angle:angle%(2*math.pi)
    direction=1 if norm(middle-start)<=norm(end-start) else -1
    span=norm((end-start)*direction)
    return {'center':(x,y),'radius':radius,'start':start,'direction':direction,'span':span,'a':tuple(a),'b':tuple(b)}


def _on_arc(arc,point):
    x,y=arc['center'];angle=math.atan2(point[1]-y,point[0]-x)
    return ((angle-arc['start'])*arc['direction'])%(2*math.pi)<=arc['span']+1e-10


def _arc_point_distance2(arc,point):
    distance=min(sum((point[i]-arc[k][i])**2 for i in range(2)) for k in ('a','b'))
    if _on_arc(arc,point):distance=min(distance,(math.dist(point,arc['center'])-arc['radius'])**2)
    return distance


def _arc_segment_distance2(arc,p,q):
    distance=min(_arc_point_distance2(arc,p),_arc_point_distance2(arc,q),_point_segment2(arc['a'],p,q),_point_segment2(arc['b'],p,q));dx,dy=q[0]-p[0],q[1]-p[1];size=dx*dx+dy*dy
    if size<1e-24:return distance
    cx,cy=arc['center'];projection=((cx-p[0])*dx+(cy-p[1])*dy)/size
    if 0<=projection<=1:
        point=(p[0]+projection*dx,p[1]+projection*dy)
        if _on_arc(arc,point):distance=min(distance,(math.dist(point,arc['center'])-arc['radius'])**2)
    px,py=p[0]-cx,p[1]-cy;bb=2*(px*dx+py*dy);cc=px*px+py*py-arc['radius']**2;disc=bb*bb-4*size*cc
    if disc>=0:
        for t in ((-bb-math.sqrt(disc))/(2*size),(-bb+math.sqrt(disc))/(2*size)):
            if -1e-10<=t<=1+1e-10 and _on_arc(arc,(p[0]+t*dx,p[1]+t*dy)):return 0.
    return distance


def _arc_arc_distance2(a,b):
    distance=min(*(_arc_point_distance2(a,b[k]) for k in ('a','b')),*(_arc_point_distance2(b,a[k]) for k in ('a','b')));ax,ay=a['center'];bx,by=b['center'];d=math.dist(a['center'],b['center']);ra,rb=a['radius'],b['radius']
    if d<1e-12:
        if any(_on_arc(a,b[k]) or _on_arc(b,a[k]) for k in ('a','b')):distance=min(distance,(ra-rb)**2)
        return distance
    ux,uy=(bx-ax)/d,(by-ay)/d
    for sa in (-1,1):
        p=(ax+sa*ra*ux,ay+sa*ra*uy)
        for sb in (-1,1):
            q=(bx+sb*rb*ux,by+sb*rb*uy)
            if _on_arc(a,p) and _on_arc(b,q):distance=min(distance,sum((p[i]-q[i])**2 for i in range(2)))
    if abs(ra-rb)-1e-10<=d<=ra+rb+1e-10:
        along=(ra*ra-rb*rb+d*d)/(2*d);height=math.sqrt(max(0,ra*ra-along*along))
        for side in (-1,1):
            p=(ax+along*ux-side*height*uy,ay+along*uy+side*height*ux)
            if _on_arc(a,p) and _on_arc(b,p):return 0.
    return distance


def _arc_points(arc):
    spec=_arc_spec(arc)
    if spec is None:return [arc['a'],arc['m'],arc['b']]
    x,y=spec['center'];radius=spec['radius'];start=spec['start'];direction=spec['direction'];span=spec['span'];middle=math.atan2(arc['m'][1]-y,arc['m'][0]-x);a,b=arc['a'],arc['b'];norm=lambda angle:angle%(2*math.pi)
    delta=max(1e-5,2*math.acos(max(-1,min(1,1-.001/max(radius,.001)))))
    count=min(2048,max(2,math.ceil(span/delta)))
    positions=sorted({i*span/count for i in range(count+1)}|{norm((middle-start)*direction)})
    points=[(x+radius*math.cos(start+direction*t),y+radius*math.sin(start+direction*t)) for t in positions]
    points[0],points[-1]=a,b
    return points


def _features(geo):
    by_net=defaultdict(list)
    layers=geo.get("layers") or ["F.Cu","B.Cu"]
    def add(net,feature,*,pad_id=None,copper_id=None):
        if isinstance(feature,list):
            for piece in feature:add(net,piece,pad_id=pad_id,copper_id=copper_id)
            return
        if net and feature:
            if pad_id is not None:feature['pad_id']=pad_id
            if copper_id is not None:feature['copper_id']=copper_id
            by_net[net].append(feature)
    for index,p in enumerate(geo.get("pads",[])):
        add(p.get("net"),_pad(p,layers),pad_id=p.get('id') or f'pad:{index}')
    for t in geo.get("tracks",[]):
        add(t.get("net"),_feature((t["a"],t["b"]),[t["layer"]],radius=t["w"]/2),copper_id=t.get('id'))
    for a in geo.get("arcs",[]):
        feature=_feature(_arc_points(a),[a["layer"]],radius=a["w"]/2,anchors=[a["a"],a["b"]]);arc=_arc_spec(a)
        if arc:
            feature['arc']=arc;cx,cy=arc['center'];r=arc['radius'];extrema=[arc['a'],arc['b']]+[(cx+r*math.cos(t),cy+r*math.sin(t)) for t in (0,math.pi/2,math.pi,3*math.pi/2) if _on_arc(arc,(cx+r*math.cos(t),cy+r*math.sin(t)))];feature['bounds']=_bounds(extrema,a['w']/2)
        add(a.get("net"),feature,copper_id=a.get('id'))
    for v in geo.get("vias",[]):
        span=v.get("layers") or ["F.Cu","B.Cu"]
        indices=[layers.index(layer) for layer in span if layer in layers]
        active=layers[min(indices):max(indices)+1] if indices else layers
        add(v.get("net"),_feature([v["p"]],active,radius=v["d"]/2,kind="via"),copper_id=v.get('id'))
    for z in geo.get("zones",[]):
        if len(z.get("pts",[]))>=3:
            add(z.get("net"),_feature(z["pts"],[z["layer"]],closed=True,kind="zone",anchors=[z["pts"][0]]))
    return by_net


def _island_features(geo):
    for net, features in _features(geo).items():
        parents=list(range(len(features)))
        def find(i):
            while parents[i]!=i:
                parents[i]=parents[parents[i]];i=parents[i]
            return i
        # Custom triangles have already been validated as one connected native region.
        pad_groups={}
        for i,feature in enumerate(features):
            key=feature.get('pad_id')
            if key is not None:
                if key in pad_groups:parents[i]=find(pad_groups[key])
                else:pad_groups[key]=i
        ordered=sorted(range(len(features)),key=lambda i:features[i]["bounds"][0])
        for k,i in enumerate(ordered):
            a=features[i]
            for j in ordered[k+1:]:
                b=features[j]
                if b["bounds"][0]>a["bounds"][2]+EPS:
                    break
                if find(i)!=find(j) and _touch(a,b):
                    parents[find(j)]=find(i)
        islands=defaultdict(list)
        for i,feature in enumerate(features):
            islands[find(i)].append(feature)
        yield net,list(islands.values())


def validate_pad_models(geo):
    """Reject unknown conductive pad models before routing jobs or proof."""
    layers=geo.get('layers') or ['F.Cu','B.Cu']
    for pad in geo.get('pads',[]):
        if pad.get('padstack_continuity_unknown'):raise ValueError('Native per-layer pad stack and plated barrel contacts require native review; automatic continuity is unknown. Use native DRC and manual routing.')
        if pad.get('npth_copper'):raise ValueError('Unplated surface copper is retained, but automatic cross-surface continuity requires explicit native review. Use native DRC and manual routing.')
        known=pad.get('shape') in {'rect','circle','oval','roundrect'} or pad.get('shape')=='custom' and bool(pad.get('copper_polygons')) and not pad.get('custom_geometry_unavailable')
        if pad.get('net') and not known and _pad(pad,layers) is not None:
            raise ValueError(f"Unsupported native pad shape {pad.get('shape')} at {pad.get('ref','?')}.{pad.get('name','?')}: routing connectivity is unknown. Use native DRC and manual routing.")


def electrical_islands(geo):
    """Pad/copper membership for routing proof; reject unknown pad contact models.

    The visual airwire overlay retains its legacy approximations for imported
    shapes. They must never establish automatic routing completeness or safety.
    """
    validate_pad_models(geo)
    return {net:[{'pads':sorted(f['pad_id'] for f in features if 'pad_id' in f),'copper':sorted(f['copper_id'] for f in features if 'copper_id' in f)} for features in islands] for net,islands in _island_features(geo)}


def airwires(geo, *, with_net=False):
    lines=[]
    for net,groups in _island_features(geo):
        islands=[]
        for features in groups:
            kinds=defaultdict(list)
            for feature in features:kinds[feature['kind']].extend(feature['anchors'])
            islands.append(kinds)
        candidates=[]
        for kinds in islands:
            # Isolated pour fragments are a DRC/zone policy concern, not terminals.
            points=kinds["pad"]+kinds["via"] or kinds["track"]
            if points:
                candidates.append(list(dict.fromkeys(tuple(p) for p in points)))
        if len(candidates)<2:
            continue
        remaining=set(range(1,len(candidates)));best={}
        def extend(i):
            for j in remaining:
                for a in candidates[i]:
                    for b in candidates[j]:
                        distance=(a[0]-b[0])**2+(a[1]-b[1])**2
                        if j not in best or distance<best[j][0]:
                            best[j]=(distance,a,b)
        extend(0)
        while remaining:
            j=min(remaining,key=lambda node:best[node][0])
            _,a,b=best.pop(j)
            lines.append({"net": net, "a": list(a), "b": list(b)} if with_net else [list(a),list(b)])
            remaining.remove(j);extend(j)
    return lines
