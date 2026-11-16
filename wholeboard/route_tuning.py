"""Length-target edits on authoritative native copper, with explicit measurement and proof."""
from __future__ import annotations

import copy
import json
import math
import uuid
from collections import Counter,defaultdict

from shapely.geometry import LineString,Point,box
from shapely.ops import unary_union

from . import buses,routing_pairs,tuning_geometry
from .module_capture import clip_arc,native_copper

MODEL='Trace centreline outside endpoint copper pads; circular arcs are analytic. Via barrel is excluded from length. Delay requires explicit layer/via data; unspecified package delays are zero. Not measured timing or signal integrity.'
EPS=1e-6


def _layers(via,layers):
    span=via.get('layers',['F.Cu','B.Cu'])
    if '*.Cu' in span:return set(layers)
    indices=[layers.index(v) for v in span if v in layers]
    return set(layers[min(indices):max(indices)+1]) if indices else set()


def _curve(item):
    if 'm' not in item:return LineString([item['a'],item['b']])
    centre,radius,start,direction,sweep=tuning_geometry.arc_circle(item)
    step=math.sqrt(8*.00005/max(radius,.00005));count=max(8,min(4096,math.ceil(sweep/step)))
    return LineString([[centre[0]+radius*math.cos(start+direction*sweep*i/count),centre[1]+radius*math.sin(start+direction*sweep*i/count)] for i in range(count+1)])


def _route(spec,geo,net):
    pads=[p for p in geo.get('pads',[]) if p.get('net')==net and p.get('kind')!='np_thru_hole'];pieces=[{**t,'kind':kind} for kind in ('tracks','arcs') for t in geo.get(kind,[]) if t.get('net')==net];vias=[v for v in geo.get('vias',[]) if v.get('net')==net]
    def unavailable(reason):return {'net':net,'ready':False,'reason':reason,'length_mm':None,'delay_ps':None,'pad_count':len(pads)}
    if len(pads)!=2:return unavailable('Choose a simple point-to-point route with two unambiguous physical pads.')
    if not pieces:return unavailable('The point-to-point route is incomplete.')
    if len(pieces)>2000:return unavailable('This route exceeds the bounded tuning analysis size.')
    if any(z.get('net')==net for z in geo.get('zones',[])):return unavailable('A poured or branched copper path has no unique tunable trace length.')
    layers=geo.get('layers',[]);shapes=[buses._pad_shape(p) for p in pads];nodes=defaultdict(list);curves=[_curve(p) for p in pieces]
    def pad_on(p,layer):return not p.get('layers') or '*.Cu' in p['layers'] or layer in p['layers']
    def node(at,layer):
        contacts=[i for i,(p,shape) in enumerate(zip(pads,shapes)) if pad_on(p,layer) and shape.buffer(EPS).covers(Point(at))]
        if len(contacts)>1:raise ValueError('Ambiguous overlapping endpoint pads.')
        if contacts:return ('pad',contacts[0])
        links=[v for v in vias if math.dist(v['p'],at)<EPS and layer in _layers(v,layers)]
        if len(links)>1:raise ValueError('Ambiguous coincident vias.')
        if links:return ('via',links[0]['id'])
        return (layer,round(at[0],6),round(at[1],6))
    try:
        for i,piece in enumerate(pieces):
            a,b=node(piece['a'],piece['layer']),node(piece['b'],piece['layer'])
            for pad_index,(pad,shape) in enumerate(zip(pads,shapes)):
                if not pad_on(pad,piece['layer']):continue
                contact=curves[i].intersection(shape.buffer(piece['w']/2+EPS))
                if contact.is_empty:continue
                if ('pad',pad_index) not in (a,b):return unavailable('The path reenters an endpoint pad and shortcuts an ambiguous detour.')
                from .module_capture import _parts
                if len(_parts(contact,'LineString'))>1:return unavailable('The path reenters an endpoint pad and has no unique electrical length.')
            if a==b:
                if a[0]=='pad':continue
                return unavailable('The route contains an ambiguous loop or overlapping segment.')
            nodes[a].append(i);nodes[b].append(i)
        if not all(('pad',i) in nodes and len(nodes['pad',i])==1 for i in range(2)):return unavailable('The route is incomplete or branched at its endpoint pads.')
        if any(len(edges)!=2 for key,edges in nodes.items() if key[0]!='pad'):return unavailable('The route is branched or incomplete; choose a simple point-to-point path.')
        seen=set();pending=[('pad',0)];visited=set()
        while pending:
            key=pending.pop()
            if key in visited:continue
            visited.add(key)
            for i in nodes[key]:
                seen.add(i);piece=pieces[i]
                pending.extend([node(piece['a'],piece['layer']),node(piece['b'],piece['layer'])])
        if len(seen)!=sum(1 for p in pieces if node(p['a'],p['layer'])!=node(p['b'],p['layer'])):return unavailable('The route has disconnected or ambiguous copper.')
        ends=[{node(p['a'],p['layer']),node(p['b'],p['layer'])} for p in pieces];strokes={}
        def stroke(index):
            if index not in strokes:strokes[index]=curves[index].buffer(pieces[index]['w']/2+EPS)
            return strokes[index]
        for i,a in enumerate(pieces):
            for j in range(i):
                b=pieces[j]
                if a['layer']!=b['layer']:continue
                distance=curves[i].distance(curves[j])
                if distance>(a['w']+b['w'])/2+EPS:continue
                shared=ends[i]&ends[j]
                if distance<=EPS:
                    overlap=curves[i].intersection(curves[j])
                    if overlap.length>EPS:return unavailable('The route has overlapping or branched copper.')
                    if not shared and not any(shape.buffer(EPS).covers(overlap) for shape in shapes):return unavailable('The route is branched or has an ambiguous crossing.')
                contact=stroke(i).intersection(stroke(j))
                if contact.is_empty:continue
                allowed=[shape for pad,shape in zip(pads,shapes) if pad_on(pad,a['layer'])]
                for key in shared:
                    if key[0]=='pad':continue
                    at=next(v['p'] for v in vias if v['id']==key[1]) if key[0]=='via' else key[1:]
                    allowed.append(Point(at).buffer(2*max(a['w'],b['w'])))
                adjacent_i={k for key in ends[i] for k in nodes[key]};adjacent_j={k for key in ends[j] for k in nodes[key]}
                for k in (adjacent_i&adjacent_j)-{i,j}:
                    # Rounded corners and their short tangent joins form one intended bend.
                    if pieces[k]['kind']=='arcs' or a['kind']==b['kind']=='arcs':allowed.append(stroke(k).buffer(.0002))
                if not unary_union(allowed).buffer(.0002).covers(contact):return unavailable('Nonadjacent copper contact creates an ambiguous shortcut or overlapping path.')
        for via in vias:
            point=Point(via['p']);span=_layers(via,layers);touches=[i for i,p in enumerate(pieces) if p['layer'] in span and curves[i].distance(point)<via['d']/2+p['w']/2-EPS]
            # A declared via node also owns its short landing/fanout pieces inside the via collar.
            collar=point.buffer(via['d']/2+max((pieces[i]['w'] for i in touches),default=0)/2+EPS);connected=set();visited_nodes=set();pending_nodes=[('via',via['id'])] if ('via',via['id']) in nodes else []
            while pending_nodes:
                key=pending_nodes.pop()
                if key in visited_nodes:continue
                visited_nodes.add(key)
                for i in nodes[key]:
                    connected.add(i)
                    if collar.covers(curves[i]):pending_nodes.extend(ends[i])
            if connected:
                ambiguous=any(i not in connected for i in touches)
            else:ambiguous=any(not ends[i]&ends[j] for position,i in enumerate(touches) for j in touches[:position])
            if ambiguous:return unavailable('A via contacts nonadjacent copper and shortcuts the measured path.')
    except ValueError as error:return unavailable(str(error))
    trimmed=[]
    for piece in pieces:
        obstacles=unary_union([shape for p,shape in zip(pads,shapes) if pad_on(p,piece['layer'])]);outside=box(-10000,-10000,10000,10000).difference(obstacles)
        if piece['kind']=='tracks':length=curves[pieces.index(piece)].difference(obstacles).length
        else:length=sum(tuning_geometry.primitive_length({**v,'kind':'arcs'}) for v in clip_arc(piece,outside))
        trimmed.append((piece['layer'],length))
    length=math.fsum(v for _,v in trimmed);timing=spec.get('board',{}).get('timing',{});models=timing.get('track_ps_per_mm',{});delay=None;delay_reason='Explicit propagation data is missing for a routed layer.'
    if all(layer in models and isinstance(models[layer],(int,float)) and not isinstance(models[layer],bool) and math.isfinite(models[layer]) and models[layer]>=0 for layer,_ in trimmed):
        delay=math.fsum(models[layer]*length for layer,length in trimmed)
        for via in vias:
            incident={pieces[i]['layer'] for i in nodes.get(('via',via['id']),[])}
            if len(incident)>1:
                if incident!={'F.Cu','B.Cu'} or 'via_ps_per_mm' not in timing:delay=None;delay_reason='An explicit supported via barrel delay model is required.';break
                delay+=float(spec['board'].get('thickness_mm',1.6))*timing['via_ps_per_mm']
        if delay is not None:delay+=sum(p.get('pin_delay_ps',buses.pin_properties(spec,p['ref'],p['name']).get('pin_delay_ps',0)) for p in pads)
    return {'net':net,'ready':True,'reason':'','length_mm':round(length,6),'delay_ps':round(delay,6) if delay is not None else None,'delay_reason':delay_reason if delay is None else '', 'pad_count':2}


def inspect(spec,geo):return {'routes':[_route(spec,geo,n['name']) for n in spec.get('nets',[])],'model':MODEL}


def _number(args,key,default,low,high):
    value=args.get(key,default)
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not low<=value<=high:raise ValueError(f'{key} must be finite and between {low:g} and {high:g}.')
    return float(value)


def _geometry(spec,geo):
    result=copy.deepcopy(geo);ox,oy=geo.get('bbox',[100,100])[:2]
    for kind,keys in [('tracks',('a','b')),('arcs',('a','m','b')),('vias',('p',))]:
        result[kind]=[]
        for group in spec['fixed_copper']:
            for value in group.get(kind,[]):
                item={**copy.deepcopy(value),'net':group['net']}
                for key in keys:item[key]=[round(item[key][0]+ox,6),round(item[key][1]+oy,6)]
                result[kind].append(item)
    return result


def _clear(spec,geo,tracks,legs,widths):
    chosen={t['id'] for t in tracks};layer=tracks[0]['layer'];clearance=spec.get('rules',{}).get('clearance_mm',.2);edge=spec.get('rules',{}).get('edge_clearance_mm',.3);ox,oy=geo.get('bbox',[100,100])[:2];outline=box(ox+edge,oy+edge,ox+spec['board']['width_mm']-edge,oy+spec['board']['height_mm']-edge)
    paths=[LineString([point for i,p in enumerate(leg) for point in (list(_curve(p).coords) if not i else list(_curve(p).coords)[1:])]) for leg in legs]
    if any(not path.is_simple or not outline.covers(path.buffer(width/2+.0001)) for path,width in zip(paths,widths)):return False
    if len(paths)==2 and paths[0].distance(paths[1])<(widths[0]+widths[1])/2+clearance+.0001:return False
    zone_sources=geo.get('zone_sources',[])
    if any(z.get('layer')==layer for z in geo.get('zones',[])) and not zone_sources:return False
    for index,(path,width,source) in enumerate(zip(paths,widths,tracks)):
        exempt=unary_union([Point(source[k]).buffer(max(width,.25)+clearance+.001) for k in ('a','b')])
        for kind in ('tracks','arcs'):
            for other in geo.get(kind,[]):
                if other['id'] in chosen or other['layer']!=layer:continue
                obstacle=_curve(other)
                if other['net']==source['net']:obstacle=obstacle.difference(exempt)
                if not obstacle.is_empty and path.distance(obstacle)<(width+other['w'])/2+clearance+.0001:return False
        for pad in geo.get('pads',[]):
            if pad.get('net')==source['net'] or pad.get('layers') and '*.Cu' not in pad['layers'] and layer not in pad['layers']:continue
            if path.distance(buses._pad_shape(pad))<width/2+clearance+.0001:return False
        for via in geo.get('vias',[]):
            if layer not in _layers(via,geo.get('layers',[])):continue
            shape=Point(via['p'])
            if via['net']==source['net'] and exempt.covers(shape):continue
            if path.distance(shape)<width/2+via['d']/2+clearance+.0001:return False
        # Normal pours are preserved and refilled around the new copper by native review.
        # Track keepouts remain fixed obstacles; an unsupported contour cannot be ignored.
        from . import sexpr
        from .module_capture import _zone_shape
        for zone in zone_sources:
            if layer not in zone.get('layers',[]):continue
            node=sexpr.parse(zone['source']);keepout=sexpr.find(node,'keepout')
            if keepout:
                rule=sexpr.find(keepout,'tracks')
                if rule and str(rule[1])=='allowed':continue
                try:shape=_zone_shape(node,[0,0])
                except ValueError:return False
                if path.distance(shape)<width/2+clearance+.0001:return False
    return True


def _candidates(geo,nets,track_ids):
    chosen={net:{t['id'] for t in geo.get('tracks',[]) if t['net']==net and t['id'] in track_ids} for net in nets}
    first=sorted([t for t in geo.get('tracks',[]) if t['net']==nets[0] and (not chosen[nets[0]] or t['id'] in chosen[nets[0]])],key=lambda t:math.dist(t['a'],t['b']),reverse=True)
    for a in first[:24]:
        if len(nets)==1:yield [a];continue
        for b in geo.get('tracks',[]):
            if b['net']!=nets[1] or b['layer']!=a['layer'] or abs(b['w']-a['w'])>EPS or chosen[nets[1]] and b['id'] not in chosen[nets[1]]:continue
            b=copy.deepcopy(b)
            if sum((a['b'][i]-a['a'][i])*(b['b'][i]-b['a'][i]) for i in range(2))<0:b['a'],b['b']=b['b'],b['a']
            direction=[(a['b'][i]-a['a'][i])/math.dist(a['a'],a['b']) for i in range(2)];delta=[b['a'][i]-a['a'][i] for i in range(2)]
            if abs(sum(delta[i]*direction[i] for i in range(2)))>EPS or any(abs((b['b'][i]-b['a'][i])-(a['b'][i]-a['a'][i]))>EPS for i in range(2)):continue
            yield [a,b]


def _plan(spec,geo,nets,before,targets,args,style,tolerance):
    clearance=spec.get('rules',{}).get('clearance_mm',.2);models=spec.get('board',{}).get('timing',{}).get('track_ps_per_mm',{});limit=_number(args,'max_amplitude_mm',max(spec['board']['width_mm'],spec['board']['height_mm']),.001,10000)
    ids=args.get('track_ids',[])
    if not isinstance(ids,list) or len(ids)>64 or any(not isinstance(i,str) for i in ids):raise ValueError('track_ids must identify existing native traces.')
    if any(not any(t['id']==identifier and t['net'] in nets for t in geo.get('tracks',[])) for identifier in ids):raise ValueError('The selected native traces do not belong to these tuning nets.')
    for tracks in _candidates(geo,nets,ids):
        start=[sum(t['a'][i] for t in tracks)/len(tracks) for i in range(2)];end=[sum(t['b'][i] for t in tracks)/len(tracks) for i in range(2)];length=math.dist(start,end);direction=[(end[i]-start[i])/length for i in range(2)];normal=[-direction[1],direction[0]];offsets=[sum((t['a'][i]-start[i])*normal[i] for i in range(2)) for t in tracks];widths=[t['w'] for t in tracks];offset=max(abs(v) for v in offsets)
        target_lengths={net:targets[net] if targets[net] is not None else before[net]['length_mm']+(args['target_delay_ps']-before[net]['delay_ps'])/models[tracks[0]['layer']] if models.get(tracks[0]['layer'],0)>0 else None for net in nets}
        if any(v is None for v in target_lengths.values()):continue
        extras=[target_lengths[n]-before[n]['length_mm'] for n in nets]
        if len(nets)>1 and max(extras)-min(extras)>2*tolerance:raise ValueError('The pair has existing skew; match the shorter leg before a shared paired length target.')
        extra=sum(extras)/len(extras)
        if extra<=0:continue
        radius=_number(args,'radius_mm',max(.5,offset+max(widths)/2+.2),0,100)
        if offset>=radius and offset:continue
        gap=max(clearance,2*offset-max(widths))
        pitch=_number(args,'pitch_mm',max(4*radius+.05,2*(2*offset+max(widths)+gap+.01)),.001,10000)
        explicit=args.get('cells');cells=[explicit] if explicit is not None else list(range(3,13))+[1,2] if style!='trombone' else list(range(1,13))
        if any(type(c) is not int or not 1<=c<=32 for c in cells):raise ValueError('Use 1 to32 meander cells.')
        side=args.get('side','auto')
        if side not in ('auto','left','right'):raise ValueError('Choose automatic, left or right meander placement.')
        for count in cells:
            for sign in ([1,-1] if side=='auto' else [-1 if side=='left' else 1]):
                try:
                    patterns=[tuning_geometry.pattern(length,extra,style=style,radius=radius,pitch=pitch,loops=count,side=sign,offset=v) for v in offsets]
                except ValueError:continue
                if patterns[0]['amplitude_mm']>limit:continue
                legs=[]
                for pattern in patterns:
                    leg=[]
                    for value in pattern['primitives']:
                        primitive=copy.deepcopy(value)
                        for key in ('a','m','b'):
                            if key in value:primitive[key]=[round(start[i]+direction[i]*value[key][0]+normal[i]*value[key][1],6) for i in range(2)]
                        leg.append(primitive)
                    legs.append(leg)
                if _clear(spec,geo,tracks,legs,widths):return tracks,legs,target_lengths,patterns[0]
    raise ValueError('No clear meander fits this target, selected traces, radius/pitch or amplitude. Choose more space or adjust the settings; the design was not changed.')


def prepare(spec,geo,args):
    if not isinstance(args,dict):raise ValueError('Use route tuning options.')
    allowed={'nets','target_mm','target_delay_ps','reference_net','tolerance_mm','style','radius_mm','pitch_mm','cells','side','max_amplitude_mm','track_ids','base_version','preview_only'}
    if set(args)-allowed:raise ValueError('Unknown route tuning options.')
    if 'preview_only' in args and type(args['preview_only']) is not bool:raise ValueError('preview_only must be a boolean; malformed previews cannot apply changes.')
    names=args.get('nets');all_names={n['name'] for n in spec.get('nets',[])}
    if not isinstance(names,list) or not 1<=len(names)<=16 or len(set(names))!=len(names) or any(n not in all_names for n in names):raise ValueError('Choose 1 to16 distinct existing nets.')
    style=args.get('style','trombone')
    if style not in ('trombone','accordion','sawtooth'):raise ValueError('Choose trombone, accordion or sawtooth meanders.')
    tolerance=_number(args,'tolerance_mm',.05,.001,100);before={row['net']:row for row in inspect(spec,geo)['routes']};target_kinds=[k for k in ('target_mm','target_delay_ps','reference_net') if k in args]
    if len(target_kinds)>1 or not target_kinds and len(names)==1:raise ValueError('Choose one absolute length, reference net or explicit delay target.')
    for net in names:
        if not before[net]['ready']:raise ValueError(net+': '+before[net]['reason'])
    if 'reference_net' in args:
        reference=args['reference_net']
        if reference not in before or not before[reference]['ready']:raise ValueError('Choose a measurable reference net.')
        targets={n:before[reference]['length_mm'] for n in names}
    elif 'target_mm' in args:targets={n:_number(args,'target_mm',None,.001,10000) for n in names}
    elif 'target_delay_ps' in args:
        _number(args,'target_delay_ps',None,.001,1000000)
        if any(before[n]['delay_ps'] is None for n in names):raise ValueError('A complete explicit propagation delay model is required for a delay target.')
        targets={n:None for n in names}
    else:targets={n:max(before[m]['length_mm'] for m in names) for n in names}
    if any(target is not None and target<before[n]['length_mm']-tolerance for n,target in targets.items()):raise ValueError('This tuning operation adds length; shortening an existing route needs a routing edit.')
    if 'target_delay_ps' in args and any(args['target_delay_ps']<before[n]['delay_ps'] for n in names):raise ValueError('This tuning operation cannot shorten the existing delay.')
    draft=copy.deepcopy(spec);draft['fixed_copper'],draft['fixed_zones']=native_copper(geo);working=copy.deepcopy(geo);remaining=list(names);pairs=[];patterns=[];changed=[]
    profiles=routing_pairs.hints(spec)['pairs']
    while remaining:
        net=remaining[0];pair=next((p['nets'] for p in profiles if net in p['nets'] and all(n in remaining for n in p['nets'])),None);group=pair or [net]
        if all(targets[n] is not None and abs(targets[n]-before[n]['length_mm'])<=tolerance or targets[n] is None and abs(args['target_delay_ps']-before[n]['delay_ps'])<=.001 for n in group):
            for n in group:remaining.remove(n)
            continue
        tracks,legs,resolved,pattern=_plan(draft,working,group,before,targets,args,style,tolerance);ox,oy=geo.get('bbox',[100,100])[:2]
        for net,source,leg in zip(group,tracks,legs):
            target=next(g for g in draft['fixed_copper'] if g['net']==net);target['tracks']=[p for p in target['tracks'] if p['id']!=source['id']];changed.append(source['id'])
            for i,value in enumerate(leg):
                item={k:v for k,v in value.items() if k!='kind'};item.update(id=source['id'] if not i else str(uuid.uuid4()),w=source['w'],layer=source['layer'],locked=source.get('locked',True))
                for key in ('a','m','b'):
                    if key in item:item[key]=[round(item[key][0]-ox,6),round(item[key][1]-oy,6)]
                target[value['kind']].append(item)
            targets[net]=resolved[net]
        working=_geometry(draft,working)
        if pair:pairs.append(pair)
        patterns.append({key:pattern[key] for key in ('amplitude_mm','radius_mm','pitch_mm','loops','side')})
        for net in group:remaining.remove(net)
    after={row['net']:row for row in inspect(draft,working)['routes']};measurements=[]
    for net in names:
        row=after[net];target=targets[net] if targets[net] is not None else row['length_mm']
        if not row['ready'] or abs(row['length_mm']-target)>tolerance:raise ValueError('Native-precision meander geometry did not retain a simple connected path within tolerance.')
        measurements.append({'net':net,'before_length_mm':before[net]['length_mm'],'after_length_mm':row['length_mm'],'target_mm':target,'deviation_mm':row['length_mm']-target,'before_delay_ps':before[net]['delay_ps'],'after_delay_ps':row['delay_ps']})
    return {'spec':draft if changed else copy.deepcopy(spec),'summary':{'changed':bool(changed),'measurements':measurements,'coupled_pairs':pairs,'style':style,'patterns':patterns,'replaced_track_ids':changed,'model':MODEL},'geometry':working}


def _current(project,version,source,pcb,digest,inputs):
    import hashlib
    from pathlib import Path
    from fastapi import HTTPException
    from . import design_identity,workbench_native
    with project.lock:
        current=workbench_native.final_pcb(project) or Path((project.state.get('workbench_native') or {}).get('pcb',''))
        try:unchanged=current==pcb and hashlib.sha256(pcb.read_bytes()).hexdigest()==digest and workbench_native._plot_inputs(pcb)[1]==inputs
        except OSError:unchanged=False
        if project.state.get('workbench',{}).get('version',0)!=version or design_identity.fields(source)!=design_identity.fields(project.state.get('spec') or {}) or not unchanged:raise HTTPException(409,'The saved design or native PCB changed during route tuning. Review the current layout again.')


def project_inspect(project):
    """Read existing geometry only; a Chat inspection never generates a replacement cache."""
    import hashlib
    import threading
    from pathlib import Path
    from . import design_identity,workbench_native
    from .kicad import geometry
    with workbench_native._locks.setdefault(project.id,threading.RLock()):
        with project.lock:
            source=copy.deepcopy(project.state.get('spec') or {});version=project.state.get('workbench',{}).get('version',0);pcb=workbench_native.final_pcb(project);native=project.state.get('workbench_native') or {}
            if pcb is None:
                if not design_identity.matches(native,source) or not native.get('pcb'):return {'routes':[],'pending':'Open the current native Layout before inspecting routed lengths.','source_version':version,'model':MODEL}
                pcb=Path(native['pcb'])
            if not pcb.is_file() or not pcb.resolve().is_relative_to(project.root.resolve()):raise ValueError('Current native PCB is unavailable.')
            digest=hashlib.sha256(pcb.read_bytes()).hexdigest();inputs=workbench_native._plot_inputs(pcb)[1]
            if not workbench_native.final_pcb(project) and native.get('geometry_pcb_sha256')!=digest:raise ValueError('The native PCB differs from its source-bound geometry. Refresh Layout before inspecting lengths.')
        data=inspect(source,geometry.read(pcb));_current(project,version,source,pcb,digest,inputs)
        return {**data,'source_version':version,'pcb_sha256':digest,**design_identity.fields(source)}


def _violation_keys(path):
    import json
    raw=json.loads(path.read_text());result=Counter()
    for category in ('violations','unconnected_items'):
        for value in raw.get(category,[]):
            if category=='violations' and value.get('severity')!='error':continue
            result[json.dumps({'category':category,'finding':value},sort_keys=True,ensure_ascii=False)]+=1
    return result


def assert_source(project,guard):
    """Validate a reviewed native/source token while its acceptance lock remains held."""
    from pathlib import Path
    from fastapi import HTTPException
    from . import design_identity,workbench_native
    if not isinstance(guard,dict) or set(guard)!={'source_identity','source_pcb_sha256','source_render_inputs_sha256'}:raise HTTPException(422,'Use the complete native source token from route review.')
    import re
    if any(not isinstance(guard[k],str) or not re.fullmatch('[0-9a-f]{64}',guard[k]) for k in ('source_pcb_sha256','source_render_inputs_sha256')):raise HTTPException(422,'Native source digests must be complete SHA-256 values.')
    with project.lock:
        source=copy.deepcopy(project.state.get('spec') or {});version=project.state.get('workbench',{}).get('version',0)
        if guard['source_identity']!=design_identity.fields(source):raise HTTPException(409,'The saved design differs from the reviewed native source.')
        pcb=workbench_native.final_pcb(project) or Path((project.state.get('workbench_native') or {}).get('pcb',''))
        if not pcb.resolve().is_relative_to(project.root.resolve()):raise HTTPException(409,'The reviewed PCB is no longer available in this project.')
        _current(project,version,source,pcb,guard['source_pcb_sha256'],guard['source_render_inputs_sha256'])


def project_draft(project,args):
    import hashlib
    import tempfile
    import threading
    from pathlib import Path
    from fastapi import HTTPException
    from . import design,design_identity,workbench_native
    from .workbench import validate_draft
    from .kicad import board,cli,geometry,schematic
    with workbench_native._locks.setdefault(project.id,threading.RLock()):
        with project.lock:
            version=project.state.get('workbench',{}).get('version',0)
            if type(args.get('base_version',version)) is not int or args.get('base_version',version)!=version:raise HTTPException(409,'The saved design changed before route tuning.')
            if getattr(project,'engine_busy',False) or project.worker and project.worker.is_alive() and project.worker is not threading.current_thread():raise HTTPException(409,'Wait for the current run before tuning routes.')
            original=copy.deepcopy(project.state.get('spec') or {})
        captured=workbench_native.layout_geometry(project)
        if captured['source_version']!=version or design_identity.fields(original)!={k:captured[k] for k in design_identity.fields(original)}:raise HTTPException(409,'The displayed PCB source changed before tuning.')
        pcb=workbench_native.final_pcb(project) or Path(captured['native']['pcb']);digest=captured['pcb_sha256'];inputs=captured['render_inputs_sha256'];source=copy.deepcopy(original);actual=captured['geometry'];ox,oy=actual.get('bbox',[100,100])[:2];adopted=[]
        for footprint in actual.get('footprints',[]):
            component=next((c for c in source['components'] if c['ref']==footprint['ref']),None)
            if component is None:continue
            placement=component.get('placement',{});next_placement={'x_mm':round(footprint['x']-ox,6),'y_mm':round(footprint['y']-oy,6),'rotation':footprint.get('rot',0),'side':'bottom' if footprint.get('side')=='B.Cu' else 'top'}
            if any(abs(float(placement.get(k,0))-v)>1e-5 for k,v in next_placement.items() if k!='side') or placement.get('side','top')!=next_placement['side']:
                component['placement']={**placement,**next_placement};adopted.append(component['ref'])
        result=prepare(source,actual,args);draft=result['spec'];validate_draft(draft)
        with tempfile.TemporaryDirectory(prefix='openfabro-tuning-') as temporary:
            folder=Path(temporary);baseline_path=folder/'baseline.drc.json';baseline=cli.drc(pcb,refill=False,save=False,report_path=baseline_path);native=schematic.build(draft,folder/'preview');parity=schematic.netlist_parity(draft,cli.schematic_nets(Path(native['sch'])))
            if not parity['ok']:raise ValueError('Route tuning changed the native logical pin membership.')
            emitted=board.build(draft,folder/'preview');preview=Path(emitted['pcb']);report_path=folder/'tuned.drc.json';drc=cli.drc(preview,refill=bool(draft.get('fixed_zones')),save=bool(draft.get('fixed_zones')),report_path=report_path);data=geometry.read(preview);measured={row['net']:row for row in inspect(draft,data)['routes']};tolerance=args.get('tolerance_mm',.05)
            for row in result['summary']['measurements']:
                current=measured[row['net']]
                if not current['ready'] or abs(current['length_mm']-row['target_mm'])>tolerance:raise ValueError('The actual native route did not retain connectivity and target length.')
                row.update(after_length_mm=current['length_mm'],after_delay_ps=current['delay_ps'],deviation_mm=current['length_mm']-row['target_mm'])
            old_keys=_violation_keys(baseline_path);new_keys=_violation_keys(report_path);added=[json.loads(key) for key,count in (new_keys-old_keys).items() for _ in range(count)]
            result.update(geometry=data,native_parity=parity,baseline_drc=baseline,drc=drc,new_violations=added[:100],new_violation_count=len(added),drc_comparison_policy='exact-raw-record-multiset-v1',safe_to_apply=not added,validation=design.validate(draft).as_dict())
        _current(project,version,original,pcb,digest,inputs);result.update(base_version=version,source_pcb_sha256=digest,source_identity=design_identity.fields(original),native_source={'source_identity':design_identity.fields(original),'source_pcb_sha256':digest,'source_render_inputs_sha256':inputs});result['summary']['adopted_native_placements']=adopted
        return result
