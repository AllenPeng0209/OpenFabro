"""Native-aware rigid selection transforms; electrical net membership never changes."""
from __future__ import annotations

import copy
import math
from collections import defaultdict


def _number(value):
    return isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value) and abs(value)<=1_000_000


def _pair(value):
    return isinstance(value,(list,tuple)) and len(value)==2 and all(_number(v) for v in value)


def _point(point,pivot,action,angle):
    x,y=point[0]-pivot[0],point[1]-pivot[1]
    if action=='rotate':
        a=math.radians(angle);x,y=x*math.cos(a)-y*math.sin(a),x*math.sin(a)+y*math.cos(a)
    elif action=='flip_horizontal':x=-x
    elif action=='flip_vertical':y=-y
    return [round(pivot[0]+x,6),round(pivot[1]+y,6)]


def _pose(rotation,mirror,action,angle):
    from .kicad.schematic import _symbol_point
    original=[_symbol_point(0,0,*point,rotation,mirror) for point in ((1,0),(0,1))]
    target=[_point(point,[0,0],action,angle) for point in original]
    # Preserve the existing native mirror representation whenever possible.
    for candidate in dict.fromkeys((mirror,'','x','y')):
        for turn in (0,90,180,270):
            basis=[_symbol_point(0,0,*point,turn,candidate) for point in ((1,0),(0,1))]
            if all(abs(a-b)<1e-5 for pa,pb in zip(target,basis) for a,b in zip(pa,pb)):return turn,candidate
    raise ValueError('The requested symbol transform is not representable by KiCad.')


def _internal_nodes(editor,keys):
    nodes=editor.get('wire_nodes',{});adj=defaultdict(set)
    for guide in editor.get('connection_guides',[]):
        a,b=guide['from'],guide['to'];adj[a].add(b);adj[b].add(a)
    moved=set();seen=set()
    for identifier in nodes:
        start='node:'+identifier
        if start in seen:continue
        pending=[start];group=set();anchors=set()
        while pending:
            current=pending.pop()
            if current in seen:continue
            seen.add(current);group.add(current)
            for other in adj[current]:
                if other.startswith('node:'):pending.append(other)
                else:anchors.add(other.split('.',1)[0])
        if anchors and anchors<=keys:moved.update(a[5:] for a in group)
    return moved


def _zone(zone,pivot,angle):
    from . import sexpr
    out=copy.deepcopy(zone);node=sexpr.parse(out['source']);origin=out['origin']
    for part in sexpr.walk(node):
        if sexpr.tag(part) in ('xy','start','mid','end') and len(part)>=3:
            point=_point([float(part[1])-origin[0],float(part[2])-origin[1]],pivot,'rotate',angle)
            part[1:3]=[sexpr.Sym(str(round(point[i]+origin[i],6))) for i in range(2)]
        elif sexpr.tag(part)=='hatch_orientation' and len(part)>1:part[1]=sexpr.Sym(str((float(part[1])-angle)%180))
    out['source']=sexpr.dumps(node);return out


def prepare(spec,args,*,native_geometry=None):
    from . import schematic_view
    from .kicad import schematic
    if not isinstance(args,dict):raise ValueError('Selection transforms need an object of options.')
    if args.get('action') in ('align','distribute','translate'):
        from . import arrange
        return arrange.prepare(spec,args,native_geometry=native_geometry)
    mode=args.get('mode');action=args.get('action');keys=args.get('keys')
    if mode not in ('schematic','layout'):raise ValueError('Open Schematic or Layout to transform objects.')
    if not isinstance(keys,list) or not keys or len(keys)>1000 or any(not isinstance(key,str) for key in keys):raise ValueError('Choose actual symbol units or footprints.')
    keys=list(dict.fromkeys(keys));individual=args.get('individual',False)
    if not isinstance(individual,bool):raise ValueError('Individual rotation must be true or false.')
    allowed={'rotate','flip_horizontal','flip_vertical'} if mode=='schematic' else {'rotate','flip_layer'}
    if action not in allowed:raise ValueError('Choose a supported transform for the current editor.')
    angle=args.get('angle',90)
    if action=='rotate' and (not _number(angle) or angle%90 or abs(angle)>360):raise ValueError('Rotation must be a finite multiple of90 degrees, at most one full turn.')
    components={c['ref']:c for c in spec['components']};out=copy.deepcopy(spec);scene=None;bounds=[];positions={};skipped=[]
    if mode=='schematic':
        scene=schematic_view.scene(spec);symbols={s['key']:s for s in scene['symbols']}
        if any(key not in symbols for key in keys):raise ValueError('Choose existing schematic symbol units.')
        if len({symbols[key]['sheet'] for key in keys})!=1:raise ValueError('Transform one schematic sheet at a time.')
        positions={key:copy.deepcopy(spec.get('editor',{}).get('positions',{}).get(key)) if _pair(spec.get('editor',{}).get('positions',{}).get(key)) else [round(v,6) for v in symbols[key]['position']] for key in keys}
        for key in keys:
            symbol=symbols[key];box=scene['definitions'][symbol['definition']]['bbox']
            for x in (box[0],box[2]):
                for y in (box[1],box[3]):
                    px,py=schematic._symbol_point(0,0,x,y,symbol['rotation'],symbol.get('mirror',''))
                    bounds.append([positions[key][0]+px/schematic.EDITOR_MM_PER_UNIT,positions[key][1]+py/schematic.EDITOR_MM_PER_UNIT])
    else:
        if native_geometry is None:raise ValueError('Read actual native PCB geometry before transforming footprints.')
        footprints={f['ref']:f for f in native_geometry['footprints']};origin=native_geometry['bbox'][:2]
        if any(key not in components or key not in footprints for key in keys):raise ValueError('Choose existing physical footprints.')
        skipped=[key for key in keys if components[key].get('placement',{}).get('locked')];keys=[key for key in keys if key not in skipped]
        positions={key:[round(footprints[key][axis]-origin[i],6) for i,axis in enumerate(('x','y'))] for key in keys}
        for key in keys:
            box=footprints[key].get('court')
            bounds.extend([[box[i]-origin[0],box[i+1]-origin[1]] for i in (0,2)] if box else [positions[key]])
    pivot=args.get('pivot')
    if pivot is not None and not _pair(pivot):raise ValueError('The pivot needs two finite coordinates.')
    if pivot is None:
        pivot=copy.deepcopy(positions[keys[0]]) if len(keys)==1 else [(min(p[i] for p in bounds)+max(p[i] for p in bounds))/2 for i in range(2)] if bounds else [0,0]
        if mode=='schematic' and len(keys)>1:pivot=[round(v/10)*10 for v in pivot]
    summary={'mode':mode,'action':action,'angle':angle if action=='rotate' else None,'individual':individual,'keys':keys,'pivot':pivot,'pivot_basis':"Each object's own origin" if individual else 'Single object origin; otherwise selected component bounds excluding text, with schematic group pivot snapped to10 units','skipped_locked':skipped,'cleared_nets':[],'preserved_nets':[],'unchanged_copper_nets':[],'cleared_copper':[],'cleared_copper_count':0,'cleared_copper_truncated':False,'transformed_copper':{kind:0 for kind in ('tracks','arcs','vias','zones')},'requires_review':False,'changed':False,'preserved_wire_paths':{}}
    if not keys or action=='rotate' and angle%360==0:return {'spec':out,'summary':summary}
    if mode=='schematic':
        editor=out.setdefault('editor',{});editor.setdefault('positions',{});editor.setdefault('rotations',{})
        for key in keys:
            symbol=symbols[key];r,m=_pose(symbol['rotation'],symbol.get('mirror',''),action,angle)
            editor['positions'][key]=positions[key] if individual else _point(positions[key],pivot,action,angle)
            editor['rotations'][key]=r
            if m:editor.setdefault('mirrors',{})[key]=m
            elif key in editor.get('mirrors',{}):del editor['mirrors'][key]
        nodes=set() if individual else _internal_nodes(editor,set(keys))
        for identifier in nodes:
            node=editor['wire_nodes'][identifier];node['position']=_point(node['position'],pivot,action,angle)
            if node.get('label'):
                from .net_labels import kind
                label=node['label'];power=kind(out,node)!='net';r,m=_pose(label.get('rotation',0),label.get('mirror','') if power else '',action,angle);label['rotation']=r
                if power and m:label['mirror']=m
                else:label.pop('mirror',None)
        moved=lambda anchor:anchor[5:] in nodes if anchor.startswith('node:') else anchor.split('.',1)[0] in keys
        routes={route.get('id',f'wire-{route["index"]}'):route for route in scene['routes']}
        for index,guide in enumerate(editor.get('connection_guides',[])):
            ends=[moved(guide[key]) for key in ('from','to')]
            if not any(ends):continue
            if all(ends) and not individual:
                route=routes.get(guide.get('id',f'wire-{index}'));points=route.get('points',[]) if route else guide.get('fixed_points',[])
                if points:
                    guide['fixed_points']=[_point(p,pivot,action,angle) for p in points];summary['preserved_wire_paths'][guide.get('id',f'wire-{index}')]=guide['fixed_points']
                if guide.get('waypoints'):guide['waypoints']=[_point(p,pivot,action,angle) for p in guide['waypoints']]
            else:guide.pop('fixed_points',None)
    else:
        chosen=set(keys)
        for component in out['components']:
            if component['ref'] not in chosen:continue
            ref=component['ref'];fp=footprints[ref];pose=component.setdefault('placement',{});x,y=positions[ref]
            if action=='rotate':
                if not individual:x,y=_point([x,y],pivot,action,angle)
                rotation=(fp.get('rot',0)-angle)%360;side='bottom' if fp.get('side')=='B.Cu' else 'top'
            else:rotation=(-fp.get('rot',0))%360;side='top' if fp.get('side')=='B.Cu' else 'bottom'
            if not 0<=x<=out['board']['width_mm'] or not 0<=y<=out['board']['height_mm']:raise ValueError('The transformed footprint origin leaves the board. Choose another pivot or enlarge the board.')
            pose.update(x_mm=x,y_mm=y,rotation=rotation,side=side)
        pads=[p for p in native_geometry['pads'] if p.get('net') and p.get('kind')!='np_thru_hole']
        affected={p['net'] for p in pads if p['ref'] in chosen};preserved={}
        for net in affected:
            refs={p['ref'] for p in pads if p['net']==net}
            if action=='rotate' and refs<=chosen and (not individual or len(refs)==1):preserved[net]=positions[next(iter(refs))] if individual else pivot
        def unchanged_pad(p):
            if p['ref'] not in chosen:return True
            point=[p['x']-origin[0],p['y']-origin[1]];rot=p.get('rot',0)
            if action=='flip_layer':
                if p.get('kind')!='thru_hole':return False
                target=[point[0],2*positions[p['ref']][1]-point[1]];rotation=-rot
            else:target=_point(point,positions[p['ref']] if individual else pivot,'rotate',angle);rotation=rot-angle
            if any(abs(a-b)>1e-6 for a,b in zip(point,target)) or any(p.get('drill_offset',[0,0])):return False
            shape=p.get('shape')
            if shape=='circle' or shape=='oval' and abs(p['w']-p['h'])<1e-6:return True
            if shape not in ('rect','roundrect','oval'):return False
            period=90 if abs(p['w']-p['h'])<1e-6 else 180;difference=(rotation-rot)%period
            return min(difference,period-difference)<1e-6
        unchanged={net for net in affected if all(unchanged_pad(p) for p in pads if p['net']==net)}
        routed={g['net'] for g in out.get('fixed_copper',[])}|{z['net'] for z in out.get('fixed_zones',[])}
        summary['unchanged_copper_nets']=sorted((unchanged-preserved.keys())&routed)
        clear=affected-preserved.keys()-unchanged;removed=summary['cleared_copper'];cleared_actual=set()
        def removal(item,net,kind):
            cleared_actual.add(net)
            summary['cleared_copper_count']+=1
            if len(removed)<1000:
                identifier,layer,layers=item.get('id'),item.get('layer'),item.get('layers')
                if kind=='zones' and isinstance(item.get('source'),str):
                    from . import sexpr
                    raw=sexpr.parse(item['source']);native_id=sexpr.find(raw,'uuid');native_layer=sexpr.find(raw,'layer');native_layers=sexpr.find(raw,'layers')
                    identifier=identifier or (str(native_id[1]) if native_id else None);layer=layer or (str(native_layer[1]) if native_layer else None);layers=layers or ([str(v) for v in native_layers[1:]] if native_layers else None)
                removed.append({'id':identifier,'net':net,'kind':kind,'layer':layer,'layers':layers,'reason':'Board-side/individual transform' if action=='flip_layer' or individual else 'Connection crosses the movable selection'})
        if 'fixed_copper' in out:
            keep=[]
            for group in out['fixed_copper']:
                net=group['net']
                if net in clear:
                    for kind in ('tracks','arcs','vias'):
                        for item in group.get(kind,[]):removal(item,net,kind)
                    continue
                if net in preserved:
                    for kind,fields in (('tracks',('a','b')),('arcs',('a','m','b')),('vias',('p',))):
                        for item in group.get(kind,[]):
                            for field in fields:item[field]=_point(item[field],preserved[net],'rotate',angle)
                            summary['transformed_copper'][kind]+=1
                keep.append(group)
            out['fixed_copper']=keep
        if 'fixed_zones' in out:
            keep=[]
            for zone in out['fixed_zones']:
                if zone.get('net') in clear:removal(zone,zone['net'],'zones');continue
                if zone.get('net') in preserved:zone=_zone(zone,preserved[zone['net']],angle);summary['transformed_copper']['zones']+=1
                keep.append(zone)
            out['fixed_zones']=keep
        summary.update(cleared_nets=sorted(cleared_actual),preserved_nets=sorted(preserved),cleared_copper_truncated=summary['cleared_copper_count']>len(removed),requires_review=bool(summary['cleared_copper_count']))
    summary['changed']=out!=spec
    return {'spec':out,'summary':summary}


def project_draft(project,args):
    import tempfile
    import threading
    from pathlib import Path
    from fastapi import HTTPException
    from shapely.geometry import LineString
    from . import workbench_native,schematic_view,design
    from .workbench import validate_draft
    from .module_capture import native_copper
    from .kicad import board,geometry,schematic,cli
    with workbench_native._locks.setdefault(project.id,threading.RLock()):
        with project.lock:
            version=project.state.get('workbench',{}).get('version',0)
            if args.get('base_version',version)!=version:raise HTTPException(409,'The design changed before the selection transform.')
            if getattr(project,'engine_busy',False) or project.worker and project.worker.is_alive() and project.worker is not threading.current_thread():raise HTTPException(409,'Wait for the active run before transforming objects.')
            original=copy.deepcopy(project.state.get('spec') or {})
        final=workbench_native.final_pcb(project);pcb=final or Path(workbench_native.generate(project)['pcb']);actual=geometry.read(pcb);source=copy.deepcopy(original)
        if args.get('mode')=='layout' or final is not None:source['fixed_copper'],source['fixed_zones']=native_copper(actual)
        result=prepare(source,args,native_geometry=actual);draft=result['spec'];validate_draft(draft)
        with tempfile.TemporaryDirectory(prefix='wholeboard-transform-') as directory:
            folder=Path(directory);native=schematic.build(draft,folder);proof=schematic.netlist_parity(draft,cli.schematic_nets(Path(native['sch'])))
            if not proof['ok']:raise ValueError('The transformed schematic changes the native pin connections.')
            scene=schematic_view.scene(draft);routes={r.get('id',f'wire-{r["index"]}'):r for r in scene['routes']}
            for identifier,points in result['summary']['preserved_wire_paths'].items():
                after=routes.get(identifier,{}).get('points',[])
                if len(points)<2 or len(after)<2:raise ValueError('An internal wire is missing from the transformed native schematic.')
                before_line,after_line=LineString(points),LineString(after)
                if before_line.hausdorff_distance(after_line)>1e-3 or abs(before_line.length-after_line.length)>1e-3:raise ValueError('An internal wire did not retain its transformed native path.')
            emitted=board.build(draft,folder);preview=Path(emitted['pcb']);refill=bool(draft.get('fixed_zones'))
            drc=cli.drc(preview,refill=refill,save=refill)
            result.update(native_parity=proof,geometry=geometry.read(preview),before_geometry=actual,schematic=scene,drc=drc,validation=design.validate(draft).as_dict())
            if args.get('mode')=='layout' and args.get('action') in ('align','distribute','translate') and result['summary']['changed'] and drc['errors']:
                result['summary'].update(requires_review=True,drc_review_required=True)
            if args.get('mode')=='schematic':result['before_schematic']=schematic_view.scene(source)
        with project.lock:
            if project.state.get('workbench',{}).get('version',0)!=version:raise HTTPException(409,'The design changed during transform review.')
        result['base_version']=version;return result
