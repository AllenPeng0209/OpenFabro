"""Native bounds, per-object translation and connected-geometry effects for arrange commands."""
from __future__ import annotations

import copy
import math
from collections import defaultdict


def _arc_points(start, middle, end):
    (ax,ay),(bx,by),(cx,cy)=start,middle,end
    determinant=2*(ax*(by-cy)+bx*(cy-ay)+cx*(ay-by))
    if abs(determinant)<1e-12:return [start,middle,end]
    a,b,c=ax*ax+ay*ay,bx*bx+by*by,cx*cx+cy*cy
    center=[(a*(by-cy)+b*(cy-ay)+c*(ay-by))/determinant,(a*(cx-bx)+b*(ax-cx)+c*(bx-ax))/determinant]
    radius=math.dist(start,center);angles=[math.atan2(p[1]-center[1],p[0]-center[0]) for p in (start,middle,end)]
    first,mid,last=angles;tau=2*math.pi;ccw=(mid-first)%tau<=(last-first)%tau+1e-10
    result=[start,middle,end]
    for angle in (0,math.pi/2,math.pi,3*math.pi/2):
        inside=(angle-first)%tau<=(last-first)%tau+1e-10 if ccw else (first-angle)%tau<=(first-last)%tau+1e-10
        if inside:result.append([center[0]+radius*math.cos(angle),center[1]+radius*math.sin(angle)])
    return result


def _bezier_points(points):
    if len(points)!=4:return points
    times={0.,1.}
    for axis in (0,1):
        p,q,r,s=[point[axis] for point in points];a=-p+3*q-3*r+s;b=2*(p-2*q+r);c=q-p
        if abs(a)<1e-12:
            if abs(b)>1e-12:times.add(-c/b)
        elif b*b-4*a*c>=0:
            root=math.sqrt(b*b-4*a*c);times.update(((-b+root)/(2*a),(-b-root)/(2*a)))
    return [[sum(math.comb(3,i)*(1-t)**(3-i)*t**i*points[i][axis] for i in range(4)) for axis in (0,1)] for t in times if 0<=t<=1]


def symbol_bounds(symbol, definition):
    """Visible native graphics and pin segments, excluding all text, in schematic editor units."""
    from .kicad import schematic
    pose=lambda point:schematic._symbol_point(0,0,*point,symbol.get('rotation',0),symbol.get('mirror',''))
    points=[]
    for shape in definition.get('graphics',[]):
        kind=shape['kind']
        if kind=='text':continue
        if kind=='circle':
            center=pose(shape['center']);radius=shape['radius'];points.extend([[center[0]-radius,center[1]-radius],[center[0]+radius,center[1]+radius]])
        elif kind=='arc':points.extend(_arc_points(*(pose(shape[key]) for key in ('start','mid','end'))))
        elif kind=='bezier':points.extend(_bezier_points([pose(p) for p in shape.get('points',[])]))
        elif kind=='rectangle':
            start,end=shape['start'],shape['end'];points.extend(pose([x,y]) for x in (start[0],end[0]) for y in (start[1],end[1]))
        else:points.extend(pose(p) for p in shape.get('points',[]))
    for pin in definition.get('pins',[]):
        if pin.get('hidden'):continue
        point=[pin['x'],pin['y']];angle=math.radians(pin.get('angle',0));length=pin.get('length',0)
        points.extend([pose(point),pose([point[0]+length*math.cos(angle),point[1]+length*math.sin(angle)])])
    if not points:
        box=definition.get('bbox',[-2.54,-2.54,2.54,2.54]);points=[pose([x,y]) for x in (box[0],box[2]) for y in (box[1],box[3])]
    x,y=symbol['position'];scale=schematic.EDITOR_MM_PER_UNIT
    return [x+min(p[0] for p in points)/scale,y+min(p[1] for p in points)/scale,x+max(p[0] for p in points)/scale,y+max(p[1] for p in points)/scale]


def _pad_bounds(pad):
    angle=math.radians(pad.get('rot',0));w,h=pad['w']/2,pad['h']/2
    if pad.get('shape')=='circle':dx,dy=w,h
    elif pad.get('shape')=='oval':
        radius=min(w,h);segment=abs(w-h)
        dx=radius+segment*abs(math.cos(angle) if w>=h else math.sin(angle));dy=radius+segment*abs(math.sin(angle) if w>=h else math.cos(angle))
    else:dx,dy=abs(w*math.cos(angle))+abs(h*math.sin(angle)),abs(w*math.sin(angle))+abs(h*math.cos(angle))
    return [pad['x']-dx,pad['y']-dy,pad['x']+dx,pad['y']+dy]


def _footprint_bounds(footprint,geometry):
    points=[]
    for shape in geometry.get('drawings',[]):
        if shape.get('ref')!=footprint['ref'] or shape.get('layer') not in ('F.CrtYd','B.CrtYd') or shape['kind']=='text':continue
        kind=shape['kind']
        if kind=='circle' and shape.get('center') and shape.get('end'):
            x,y=shape['center'];radius=math.dist(shape['center'],shape['end']);points.extend([[x-radius,y-radius],[x+radius,y+radius]])
        elif kind=='arc' and all(shape.get(key) for key in ('start','mid','end')):points.extend(_arc_points(shape['start'],shape['mid'],shape['end']))
        elif kind in ('curve','bezier'):points.extend(_bezier_points(shape.get('points',[])))
        elif shape.get('points'):points.extend(shape['points'])
        else:points.extend(shape[key] for key in ('start','end') if shape.get(key))
    if points:return [min(p[0] for p in points),min(p[1] for p in points),max(p[0] for p in points),max(p[1] for p in points)]
    if footprint.get('court'):return footprint['court']
    pads=[_pad_bounds(p) for p in geometry.get('pads',[]) if p['ref']==footprint['ref']]
    return [min(p[0] for p in pads),min(p[1] for p in pads),max(p[2] for p in pads),max(p[3] for p in pads)] if pads else [footprint['x'],footprint['y']]*2


def _deltas(keys,positions,bounds,args):
    from .transforms import _pair
    action=args['action'];axis=args.get('axis','auto' if action=='distribute' else 'x');basis=args.get('basis','bounds')
    if basis not in ('bounds','origins'):raise ValueError('Align using native bounds or origins.')
    if action!='translate' and axis not in (('x','y','auto') if action=='distribute' else ('x','y')):raise ValueError('Choose a horizontal or vertical arrangement axis.')
    boxes={key:[*positions[key],*positions[key]] if basis=='origins' else bounds[key] for key in keys};moves={key:[0,0] for key in keys}
    if action=='translate':
        delta=args.get('delta')
        if not _pair(delta):raise ValueError('Nudge displacement needs two bounded finite coordinates.')
        return {key:list(delta) for key in keys},axis,None
    edge=args.get('edge','min')
    if action=='align' and edge not in ('min','center','max'):raise ValueError('Choose minimum, center or maximum alignment.')
    if not keys:return moves,axis,None
    if axis=='auto':axis='x' if max(positions[k][0] for k in keys)-min(positions[k][0] for k in keys)>=max(positions[k][1] for k in keys)-min(positions[k][1] for k in keys) else 'y'
    i=0 if axis=='x' else 1
    if action=='align':
        start,end=min(boxes[k][i] for k in keys),max(boxes[k][i+2] for k in keys);target={'min':start,'center':(start+end)/2,'max':end}[edge]
        for key in keys:
            box=boxes[key];current={'min':box[i],'center':(box[i]+box[i+2])/2,'max':box[i+2]}[edge];moves[key][i]=round(target-current,6)
        return moves,axis,None
    if len(keys)<3:return moves,axis,None
    ordered=sorted(keys,key=lambda k:((boxes[k][i]+boxes[k][i+2])/2,k));first,last=ordered[0],ordered[-1]
    gap=(boxes[last][i+2]-boxes[first][i]-sum(boxes[k][i+2]-boxes[k][i] for k in ordered))/(len(keys)-1)
    cursor=boxes[first][i]
    for key in ordered:
        if key not in (first,last):moves[key][i]=round(cursor-boxes[key][i],6)
        cursor+=boxes[key][i+2]-boxes[key][i]+gap
    return moves,axis,round(gap,6)


def _schematic_wires(out,scene,moves,summary):
    editor=out.get('editor',{});nodes=editor.get('wire_nodes',{});owners={}
    for symbol in scene['symbols']:
        for pin in scene['definitions'][symbol['definition']]['pins']:
            number=str(pin['number']);owners[symbol['key']+'.'+number]=symbol['key'];owners.setdefault(symbol['ref']+'.'+number,symbol['key'])
    zero=[0,0];delta=lambda anchor:moves.get(owners.get(anchor),zero)
    graph=defaultdict(set)
    for guide in editor.get('connection_guides',[]):a,b=guide['from'],guide['to'];graph[a].add(b);graph[b].add(a)
    node_moves={};visited=set()
    for identifier in nodes:
        start='node:'+identifier
        if start in visited:continue
        pending=[start];group=set();anchors=[]
        while pending:
            current=pending.pop()
            if current in visited:continue
            visited.add(current);group.add(current)
            for other in graph[current]:
                if other.startswith('node:'):pending.append(other)
                else:anchors.append(delta(other))
        common=anchors[0] if anchors and all(v==anchors[0] for v in anchors) else zero
        for node in group:
            key=node[5:];node_moves[node]=common
            if any(common):nodes[key]['position']=[round(nodes[key]['position'][i]+common[i],6) for i in (0,1)]
    at=lambda anchor:node_moves.get(anchor,zero) if anchor.startswith('node:') else delta(anchor)
    routes={r.get('id',f'wire-{r["index"]}'):r for r in scene['routes']}
    for index,guide in enumerate(editor.get('connection_guides',[])):
        a,b=at(guide['from']),at(guide['to']);identifier=guide.get('id',f'wire-{index}')
        if not any(a) and not any(b):continue
        if a==b:
            points=routes.get(identifier,{}).get('points',guide.get('fixed_points',[]))
            if points:guide['fixed_points']=[[round(p[i]+a[i],6) for i in (0,1)] for p in points];summary['preserved_wire_paths'][identifier]=guide['fixed_points']
            if guide.get('waypoints'):guide['waypoints']=[[round(p[i]+a[i],6) for i in (0,1)] for p in guide['waypoints']]
        else:
            if guide.get('fixed_points') or guide.get('waypoints'):summary['requires_review']=True
            guide.pop('fixed_points',None);guide.pop('waypoints',None);summary['rerouted_wires'].append(identifier)


def _pcb_copper(out,geometry,moves,summary):
    from . import sexpr
    pads=[p for p in geometry.get('pads',[]) if p.get('net') and p.get('kind')!='np_thru_hole'];zero=[0,0]
    affected={p['net'] for p in pads if any(moves.get(p['ref'],zero))};uniform={}
    for net in affected:
        deltas=[moves.get(p['ref'],zero) for p in pads if p['net']==net]
        if all(d==deltas[0] for d in deltas):uniform[net]=deltas[0]
    cleared=affected-uniform.keys();cleared_actual=set();routed={g['net'] for g in out.get('fixed_copper',[])}|{z['net'] for z in out.get('fixed_zones',[])}
    summary['preserved_nets']=sorted(uniform);summary['unchanged_copper_nets']=sorted(routed-affected)
    def removed(item,net,kind):
        cleared_actual.add(net)
        identifier,layer,layers=item.get('id'),item.get('layer'),item.get('layers')
        if kind=='zones':
            raw=sexpr.parse(item['source']);uid=sexpr.find(raw,'uuid');ly=sexpr.find(raw,'layer');identifier=identifier or (str(uid[1]) if uid else None);layer=layer or (str(ly[1]) if ly else None)
        summary['cleared_copper_count']+=1
        if len(summary['cleared_copper'])<1000:summary['cleared_copper'].append({'id':identifier,'net':net,'kind':kind,'layer':layer,'layers':layers,'reason':'Connected pads have different displacements'})
    def outside(item,net,kind,points,padding=0):
        if not points:return
        box=[min(p[0] for p in points)-padding,min(p[1] for p in points)-padding,max(p[0] for p in points)+padding,max(p[1] for p in points)+padding]
        if box[0]>=-1e-6 and box[1]>=-1e-6 and box[2]<=out['board']['width_mm']+1e-6 and box[3]<=out['board']['height_mm']+1e-6:return
        summary['outside_copper_count']+=1;summary['requires_review']=True
        if len(summary['outside_copper'])<1000:summary['outside_copper'].append({'id':item.get('id'),'net':net,'kind':kind,'layer':item.get('layer'),'bounds':box})
    if 'fixed_copper' in out:
        keep=[]
        for group in out['fixed_copper']:
            net=group['net']
            if net in cleared:
                for kind in ('tracks','arcs','vias'):
                    for item in group.get(kind,[]):removed(item,net,kind)
                continue
            if net in uniform:
                for kind,fields in (('tracks',('a','b')),('arcs',('a','m','b')),('vias',('p',))):
                    for item in group.get(kind,[]):
                        for field in fields:item[field]=[round(item[field][i]+uniform[net][i],6) for i in (0,1)]
                        points=_arc_points(item['a'],item['m'],item['b']) if kind=='arcs' else [item[field] for field in fields]
                        outside(item,net,kind,points,item.get('d',item.get('w',0))/2)
                        summary['transformed_copper'][kind]+=1
            keep.append(group)
        out['fixed_copper']=keep
    if 'fixed_zones' in out:
        keep=[]
        for zone in out['fixed_zones']:
            net=zone['net']
            if net in cleared:removed(zone,net,'zones');continue
            if net in uniform:
                node=sexpr.parse(zone['source']);delta=uniform[net]
                for part in sexpr.walk(node):
                    if sexpr.tag(part) in ('xy','start','mid','end') and len(part)>=3:part[1:3]=[sexpr.Sym(str(round(float(part[i+1])+delta[i],6))) for i in (0,1)]
                zone['source']=sexpr.dumps(node);summary['transformed_copper']['zones']+=1
                uid=sexpr.find(node,'uuid');ly=sexpr.find(node,'layer');origin=zone.get('origin',geometry['bbox'][:2])
                points=[[float(part[1])-origin[0],float(part[2])-origin[1]] for part in sexpr.walk(node) if sexpr.tag(part) in ('xy','start','mid','end') and len(part)>=3]
                outside({'id':str(uid[1]) if uid else None,'layer':str(ly[1]) if ly else None},net,'zones',points)
            keep.append(zone)
        out['fixed_zones']=keep
    summary['cleared_nets']=sorted(cleared_actual)
    summary['cleared_copper_truncated']=summary['cleared_copper_count']>len(summary['cleared_copper'])
    summary['requires_review']|=bool(summary['cleared_copper_count'])


def prepare(spec,args,*,native_geometry=None):
    from . import schematic_view
    from .transforms import _pair
    mode,action=args.get('mode'),args['action'];keys=args.get('keys')
    if mode not in ('schematic','layout') or not isinstance(keys,list) or not keys or len(keys)>1000 or any(not isinstance(k,str) for k in keys):raise ValueError('Choose real objects in Schematic or Layout.')
    keys=list(dict.fromkeys(keys));out=copy.deepcopy(spec);positions={};bounds={};skipped=[];scene=None
    if mode=='schematic':
        scene=schematic_view.scene(spec);symbols={s['key']:s for s in scene['symbols']}
        if any(k not in symbols for k in keys):raise ValueError('Choose existing symbol units.')
        if len({symbols[k]['sheet'] for k in keys})!=1:raise ValueError('Arrange one schematic sheet at a time.')
        for key in keys:
            symbol=symbols[key];positions[key]=copy.deepcopy(spec.get('editor',{}).get('positions',{}).get(key,symbol['position']));bounds[key]=symbol_bounds(symbol,scene['definitions'][symbol['definition']])
    else:
        if native_geometry is None:raise ValueError('Load actual native footprint geometry before arranging.')
        components={c['ref']:c for c in out['components']};footprints={f['ref']:f for f in native_geometry['footprints']};origin=native_geometry['bbox'][:2]
        if any(k not in components or k not in footprints for k in keys):raise ValueError('Choose existing physical footprints.')
        skipped=[k for k in keys if components[k].get('placement',{}).get('locked')];keys=[k for k in keys if k not in skipped]
        for key in keys:
            footprint=footprints[key];positions[key]=[round(footprint[axis]-origin[i],6) for i,axis in enumerate(('x','y'))];box=_footprint_bounds(footprint,native_geometry);bounds[key]=[box[i]-origin[i%2] for i in range(4)]
    moves,axis,gap=_deltas(keys,positions,bounds,args)
    summary={'mode':mode,'action':action,'axis':axis,'edge':args.get('edge'),'basis':args.get('basis','bounds'),'gap':gap,'keys':keys,'skipped_locked':skipped,
        'individual':False,'pivot':[0,0],'pivot_basis':'Native symbol graphics and pins, excluding text; PCB courtyard or pad bounds' if args.get('basis','bounds')=='bounds' else 'Selected object origins',
        'moves':moves,'cleared_nets':[],'preserved_nets':[],'unchanged_copper_nets':[],'cleared_copper':[],'cleared_copper_count':0,'cleared_copper_truncated':False,
        'transformed_copper':{kind:0 for kind in ('tracks','arcs','vias','zones')},'preserved_wire_paths':{},'rerouted_wires':[],'body_outside':[],'outside_copper':[],'outside_copper_count':0,
        'requires_review':gap is not None and gap<0,'changed':False}
    for key,delta in moves.items():
        if not any(delta):continue
        point=[round(positions[key][i]+delta[i],6) if delta[i] else positions[key][i] for i in (0,1)]
        if not _pair(point):raise ValueError('The arranged coordinates are outside the supported range.')
        if mode=='schematic':out.setdefault('editor',{}).setdefault('positions',{})[key]=point
        else:
            if not 0<=point[0]<=out['board']['width_mm'] or not 0<=point[1]<=out['board']['height_mm']:raise ValueError('The footprint origin leaves the board.')
            pose=components[key].setdefault('placement',{})
            for i,field in enumerate(('x_mm','y_mm')):
                if delta[i] or field not in pose:pose[field]=point[i]
            box=[bounds[key][i]+delta[i%2] for i in range(4)]
            if box[0]<0 or box[1]<0 or box[2]>out['board']['width_mm'] or box[3]>out['board']['height_mm']:summary['body_outside'].append(key);summary['requires_review']=True
    if mode=='schematic':_schematic_wires(out,scene,moves,summary)
    else:_pcb_copper(out,native_geometry,moves,summary)
    summary['changed']=out!=spec
    return {'spec':out,'summary':summary}
