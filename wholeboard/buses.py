"""Pin-scoped interface groups, native rules and explicitly modelled bus timing."""
from __future__ import annotations
import copy
import hashlib
import json
import math
import re
from collections import defaultdict
from . import project_library

TEXT_FIELDS={'bus_group','bus_type','pair','pair_role','polarity'}
NUMBER_FIELDS={'impedance_ohms','impedance_tolerance_pct','pn_skew_ps','pin_delay_ps','pair_skew_ps','max_length_mm','max_match_mm'}
FIELDS=TEXT_FIELDS|NUMBER_FIELDS

def _text(value):return isinstance(value,str) and len(value)<=100 and (not value or value.isprintable())

def pin_numbers(component,spec):
    from .kicad import schematic,libs
    info=schematic.symbol_info(component.get('symbol',''),spec) if component.get('symbol') else None
    if info:return {str(p['number']):p.get('name','') for p in info['pins']}
    footprint=libs.load_footprint(component.get('footprint',''),spec)
    return {name:name for name in footprint.pad_names} if footprint else {}

def validate(spec):
    for c in spec.get('components',[]):
        if not _text(c.get('part_type','')):raise ValueError('Part Type needs bounded single-line text.')
        if not _text(c.get('bus_type','')):raise ValueError('Bus Type needs bounded single-line text.')
        props=c.get('pin_properties',{})
        if not isinstance(props,dict) or len(props)>10000:raise ValueError('Pin properties must be a bounded object.')
        if not props:continue
        known=pin_numbers(c,spec)
        for pin,values in props.items():
            if pin not in known:raise ValueError(f'{c["ref"]}.{pin} is not a real symbol pin.')
            if not isinstance(values,dict) or set(values)-FIELDS:raise ValueError('Choose supported terminal bus properties.')
            for key,value in values.items():
                if key in TEXT_FIELDS:
                    if not _text(value):raise ValueError(f'{key} needs bounded single-line text.')
                    if key=='polarity' and value not in ('','P','N'):raise ValueError('Pair polarity is P or N.')
                elif isinstance(value,bool) or not isinstance(value,(int,float)) or abs(value)>1000000 or not math.isfinite(value) or value<0 or key in ('impedance_ohms','max_length_mm') and value==0:
                    raise ValueError(f'{key} needs a bounded nonnegative number in the displayed units.')
                elif key=='pin_delay_ps' and value>(2**31-11)/1000000:
                    raise ValueError('Pin Delay exceeds the KiCad pad time range (2147.483637ps).')
                if key=='impedance_tolerance_pct' and value>100:raise ValueError('Impedance tolerance is at most100 percent.')
    timing=spec.get('board',{}).get('timing',{})
    if not isinstance(timing,dict):raise ValueError('Board timing needs layer propagation data.')
    layers=timing.get('track_ps_per_mm',{})
    if not isinstance(layers,dict) or len(layers)>32:raise ValueError('Propagation delay must map copper layers to ps/mm.')
    for layer,value in layers.items():
        if not isinstance(layer,str) or not re.fullmatch(r'(?:F|B|In\d+)\.Cu',layer) or isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not 0<value<=10000:raise ValueError('Layer propagation delay needs a positive finite ps/mm value.')
    if 'via_ps_per_mm' in timing:
        v=timing['via_ps_per_mm']
        if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or not 0<=v<=1000000:raise ValueError('Via delay needs bounded finite ps/mm.')

def prepare(spec,args):
    if not isinstance(args,dict) or not isinstance(args.get('patch',{}),dict):raise ValueError('Bus edits need an object of properties.')
    if args.get('action')=='stackup':
        from . import stackup
        return stackup.prepare(spec,args)
    if args.get('action')=='pad_shape':
        from . import pad_shapes
        return pad_shapes.prepare(spec,args)
    if args.get('action')=='interface':
        from . import interface_presets
        c=next((c for c in spec['components'] if c['ref']==args.get('ref')),None)
        if not c:raise ValueError('Choose an existing component for interface setup.')
        result=interface_presets.prepare(spec,args,pin_numbers(c,spec));validate(result['spec']);result['buses']=compile(result['spec']);return result
    out=copy.deepcopy(spec);action=args.get('action','pins');patch=args.get('patch',{});components={c['ref']:c for c in out['components']}
    if action=='component':
        c=components.get(args.get('ref'))
        if not c or set(patch)-{'bus_type','part_type'}:raise ValueError('Choose a component and its Part Type or Bus Type.')
        for key,value in patch.items():
            if value is None or value=='':c.pop(key,None)
            else:c[key]=value
    elif action=='timing':
        if set(patch)-{'track_ps_per_mm','via_ps_per_mm'}:raise ValueError('Choose explicit propagation-delay properties.')
        out['board']['timing']={**out['board'].get('timing',{}),**{k:copy.deepcopy(v) for k,v in patch.items() if v is not None}}
        for key,value in patch.items():
            if value is None:out['board']['timing'].pop(key,None)
    elif action=='pins':
        pins=args.get('pins',[])
        if not isinstance(pins,list) or not pins or len(pins)>1000 or any(not isinstance(pin,str) or '.' not in pin for pin in pins) or set(patch)-FIELDS:raise ValueError('Choose real pins and supported bus properties.')
        for full in dict.fromkeys(pins):
            ref,pin=full.split('.',1);c=components.get(ref)
            if not c or pin not in pin_numbers(c,out):raise ValueError(f'{full} is not a real terminal.')
            values=c.setdefault('pin_properties',{}).setdefault(pin,{})
            for key,value in patch.items():
                if value is None or value=='':values.pop(key,None)
                else:values[key]=copy.deepcopy(value)
            if not values:c['pin_properties'].pop(pin)
            if not c['pin_properties']:c.pop('pin_properties',None)
    else:raise ValueError('Choose pins, component or timing for a bus edit.')
    validate(out)
    return {'spec':out,'buses':compile(out)}

def _limits(members,issues,identifier):
    result={}
    for key in NUMBER_FIELDS-{'pin_delay_ps'}:
        values={m['properties'][key] for m in members if key in m['properties']}
        if key=='impedance_ohms' and len(values)>1:issues.append({'severity':'error','bus_id':identifier,'message':'Conflicting impedance targets on one pair.'});return None
        if values:result[key]=min(values)
    return result

def compile(spec):
    validate(spec);nets={p:n['name'] for n in spec.get('nets',[]) for p in n.get('pins',[])};order={n['name']:i for i,n in enumerate(spec.get('nets',[]))};by={};issues=[];groups=[];pins=[]
    for c in spec.get('components',[]):
        for number,properties in c.get('pin_properties',{}).items():
            row={'pin':c['ref']+'.'+number,'ref':c['ref'],'number':number,'net':nets.get(c['ref']+'.'+number),'properties':copy.deepcopy(properties),'bus_type':properties.get('bus_type') or c.get('bus_type','')};pins.append(row)
            group=properties.get('bus_group')
            if not group:continue
            from .sheets import component_sheet
            scope='@'+(component_sheet(c) or 'Main') if c.get('terminal') else c['ref']
            identifier=scope+':'+group;bus=by.setdefault(identifier,{'id':identifier,'ref':scope,'group':group,'members':[]});bus['members'].append(row)
    for identifier,bus in by.items():
        members=bus['members'];types={m['bus_type'] for m in members if m['bus_type']};bus['bus_type']=next(iter(types)) if len(types)==1 else '';bus['nets']=sorted({m['net'] for m in members if m['net']},key=order.get)
        if len(types)>1:issues.append({'severity':'error','bus_id':identifier,'message':'Bus members specify different interface types.'});continue
        if any(not m['net'] for m in members):issues.append({'severity':'pending','bus_id':identifier,'message':'Connect every bus member before deriving routing constraints.'});continue
        pairs=defaultdict(list)
        for m in members:
            if m['properties'].get('pair'):pairs[m['properties']['pair']].append(m)
        unpaired=[m['pin'] for m in members if not m['properties'].get('pair')]
        if pairs and unpaired:issues.append({'severity':'pending','bus_id':identifier,'message':'Put unpaired members in a separate Bus Group before deriving their constraints: '+', '.join(unpaired)})
        if not pairs:
            common=[{**m,'properties':{k:v for k,v in m['properties'].items() if k not in ('impedance_ohms','impedance_tolerance_pct','pn_skew_ps')}} for m in members];limits=_limits(common,issues,identifier)
            if len(bus['nets'])>=2:groups.append({'bus_id':identifier,'bus_type':bus['bus_type'],'pair':None,'kind':'bus','nets':bus['nets'],'members':[m['pin'] for m in members],**(limits or {})})
            else:issues.append({'severity':'pending','bus_id':identifier,'message':'Bus matching needs at least two connected nets.'})
            for net in bus['nets']:
                rows=[m for m in members if m['net']==net];limits=_limits(rows,issues,identifier)
                if limits and 'impedance_ohms' in limits:groups.append({'bus_id':identifier,'bus_type':bus['bus_type'],'pair':None,'kind':'single','nets':[net],'members':[m['pin'] for m in rows],**{k:v for k,v in limits.items() if k not in ('pn_skew_ps','pair_skew_ps','max_match_mm')}})
            if any('pn_skew_ps' in m['properties'] for m in members):issues.append({'severity':'pending','bus_id':identifier,'message':'Assign a Controlled Impedance Pair before applying PN skew.'})
            continue
        for pair,rows in pairs.items():
            names=sorted({m['net'] for m in rows},key=order.get);limits=_limits(rows,issues,identifier)
            if limits is None:continue
            if len(names)<2 or pair and len(names)!=2:issues.append({'severity':'pending','bus_id':identifier,'message':'A pair needs two distinct connected nets; a bus needs at least two.'});continue
            row={'bus_id':identifier,'bus_type':bus['bus_type'],'pair':pair,'kind':'diff' if pair else 'bus','nets':names,'members':[m['pin'] for m in rows],**limits}
            groups.append(row)
    # Both ends may describe the same physical pair. Retain identities but do not duplicate constraints.
    merged={}
    for row in groups:
        key=(row['kind'],tuple(row['nets']));old=merged.get(key)
        if old is None:merged[key]={**row,'bus_ids':[row['bus_id']]};continue
        if row.get('impedance_ohms') is not None and old.get('impedance_ohms') is not None and row['impedance_ohms']!=old['impedance_ohms']:
            issues.append({'severity':'error','bus_id':row['bus_id'],'message':'Opposite bus ends disagree on impedance.'});old['invalid']=True;continue
        old['bus_ids'].append(row['bus_id'])
        for name in NUMBER_FIELDS-{'pin_delay_ps'}:
            if name in row:old[name]=min(old[name],row[name]) if name in old else row[name]
    for row in merged.values():
        for manual in spec.get('impedance') or []:
            if not isinstance(manual,dict) or set(manual.get('nets',[]))!=set(row['nets']):continue
            from .impedance import profiled
            value=profiled(manual).get('ohms')
            if value is not None and row.get('impedance_ohms') is not None and value!=row['impedance_ohms']:
                issues.append({'severity':'error','bus_id':row['bus_id'],'message':'Manual and terminal impedance targets disagree.'});row['invalid']=True
    for bus in by.values():
        if any('pair_skew_ps' in m['properties'] for m in bus['members']):
            lanes=[row for row in merged.values() if row['kind']=='diff' and not row.get('invalid') and bus['id'] in row['bus_ids']]
            if len(lanes)<2:issues.append({'severity':'pending','bus_id':bus['id'],'message':'Pair-to-pair skew needs at least two complete differential pairs.'})
    return {'buses':list(by.values()),'groups':[row for row in merged.values() if not row.get('invalid')],'issues':issues,'pins':pins}

def impedance_groups(spec):
    result=[]
    for row in compile(spec)['groups']:
        if row['kind']=='diff' and row.get('impedance_ohms') is None:continue
        result.append({'source':'terminal_bus','kind':row['kind'],'nets':row['nets'],**({'ohms':row['impedance_ohms']} if row.get('impedance_ohms') is not None else {}),**{k:row[k] for k in ('max_length_mm','max_match_mm') if k in row}})
    return result

def native_rules(spec):
    rules=[]
    for row in compile(spec)['groups']:
        identifier=hashlib.sha256(json.dumps([row['kind'],row['nets']],sort_keys=True).encode()).hexdigest()[:12]
        def quoted(net):return "'"+net.replace('\\','\\\\').replace("'","\\'")+"'"
        condition=' || '.join('A.NetName == '+quoted(net) for net in row['nets'])
        for key,constraint,unit in [('max_length_mm','length','mm'),('max_match_mm','skew','mm'),('pn_skew_ps','skew','ps')]:
            if key not in row:continue
            label=f'BUS {identifier} {key}'
            rules.append(f'(rule {json.dumps(label)} (condition {json.dumps(condition,ensure_ascii=False)}) (constraint {constraint} (max {row[key]:g}{unit})))')
    return rules

def native_timing_profiles(spec,project,controlled=()):
    """KiCad10's serialized tuning-profile table, using attoseconds/mm and nm."""
    timing=spec.get('board',{}).get('timing',{});models=timing.get('track_ps_per_mm',{})
    if not models:return
    profiles=[]
    differential={c['name']:c.get('diff',False) for c in controlled}
    for netclass in project['net_settings']['classes']:
        name='WBTiming_'+hashlib.sha256(netclass['name'].encode()).hexdigest()[:10]
        netclass['tuning_profile']=name
        target=re.fullmatch(r'Impedance\d+_([\d.]+)R',netclass['name'])
        profiles.append({'profile_name':name,'type':1 if differential.get(netclass['name']) else 0,'target_impedance':float(target[1]) if target else 0,'enable_time_domain_tuning':True,
          'layer_entries':[{'signal_layer':layer,'top_reference_layer':'Undefined','bottom_reference_layer':'Undefined','width':round(netclass['track_width']*1000000),'diff_pair_gap':round(netclass['diff_pair_gap']*1000000),'delay':round(delay*1000000)} for layer,delay in models.items()],
          'via_prop_delay':round(timing.get('via_ps_per_mm',0)*1000000),'via_overrides':[]})
    project['tuning_profiles']={'meta':{'version':0},'tuning_profiles_impedance_geometric':profiles}

def pin_properties(spec,ref,pin):
    c=next((c for c in spec['components'] if c['ref']==ref),None)
    return (c or {}).get('pin_properties',{}).get(pin,{})

def _pad_shape(p):
    from shapely.geometry import Point,LineString,box
    from shapely.affinity import rotate,translate
    w,h=p['w'],p['h'];r=min(w,h)/2
    if p['shape']=='custom' and p.get('copper_polygons'):
        from shapely.geometry import Polygon
        from shapely import union_all
        shape=union_all([Polygon(r) for r in p['copper_polygons']])
    elif p['shape']=='circle':shape=Point(0,0).buffer(w/2,quad_segs=64)
    elif p['shape']=='oval':shape=LineString([[-w/2+r,0],[w/2-r,0]] if w>=h else [[0,-h/2+r],[0,h/2-r]]).buffer(r,quad_segs=64)
    elif p['shape']=='roundrect':
        r=min(w,h)*p.get('rratio',.25);shape=box(-w/2+r,-h/2+r,w/2-r,h/2-r).buffer(r,quad_segs=64)
    else:shape=box(-w/2,-h/2,w/2,h/2)
    return translate(rotate(shape,-p.get('rot',0),origin=(0,0)),p['x'],p['y'])

def _track_lengths(subset):
    from shapely.geometry import LineString
    from shapely.ops import unary_union
    result=[]
    for track in subset['tracks']:
        pads=[_pad_shape(p) for p in subset['pads'] if p.get('kind')!='np_thru_hole' and ('*.Cu' in p.get('layers',[]) or track['layer'] in p.get('layers',[]) or not p.get('layers'))]
        line=LineString([track['a'],track['b']]);trimmed=line.difference(unary_union(pads)) if pads else line
        result.append((track['layer'],trimmed.length))
    return result

def _impedance_estimate(spec,group,geo):
    from . import impedance
    from shapely.geometry import LineString
    target=group.get('impedance_ohms');tolerance=group.get('impedance_tolerance_pct');result={'target_ohms':target,'tolerance_pct':tolerance,'estimate_ohms':None,'status':'unknown','model':'Approximate outer-layer IPC-2141 model using OpenFabro nominal stackup; not a field solver or measurement.'}
    if target is None:return result
    selected=[[t for t in geo.get('tracks',[]) if t['net']==net] for net in group['nets']]
    if not all(selected):return result
    tracks=[t for rows in selected for t in rows];layers={t['layer'] for t in tracks};widths={round(t['w'],6) for t in tracks}
    if len(layers)!=1 or not layers<={'F.Cu','B.Cu'} or len(widths)!=1 or any(a['net'] in group['nets'] for a in geo.get('arcs',[])):return result
    if spec['board'].get('stackup'):
        from . import stackup as physical
        st=physical.parameters(spec['board'],next(iter(layers)))
        if st is None:return result
    else:st=impedance.stackup(int(spec['board'].get('layers',2)),float(spec['board'].get('thickness_mm',1.6)))
    if st['h'] is None or st['er'] is None:return {**result,'stackup':st,'source':'unspecified_stackup'}
    width=next(iter(widths));gap=None;t=st.get('copper_mm',impedance.COPPER_MM)
    if group['kind']=='diff':
        a,b=selected
        axis=[a[0]['b'][i]-a[0]['a'][i] for i in range(2)]
        if any(abs(axis[0]*(t['b'][1]-t['a'][1])-axis[1]*(t['b'][0]-t['a'][0]))>.0001 for t in tracks):return result
        gap=min(LineString([p['a'],p['b']]).distance(LineString([n['a'],n['b']]))-(p['w']+n['w'])/2 for p in a for n in b)
        if gap<=0:return result
        estimate=impedance.diff_microstrip(width,gap,st['h'],st['er'],t)
    elif group['kind']=='single':estimate=impedance.microstrip(width,st['h'],st['er'],t)
    else:return result
    result.update(estimate_ohms=round(estimate,3),width_mm=width,gap_mm=gap,stackup=st,source=st.get('source','nominal_stackup'),status='unknown' if tolerance is None else 'pass' if abs(estimate-target)<=target*tolerance/100 else 'fail')
    if st.get('source')=='declared_stackup':
        result.update(model_status=result['status'],status='unknown',reference_verified=False,model=st['model']+' Reference continuity/coverage has not been verified.')
    return result

def native_pad_metadata(spec,component,footprint):
    from .sexpr import find_all,find,Sym,S
    props=component.get('pin_properties',{})
    if not props:return
    for pad in find_all(footprint,'pad'):
        values=props.get(str(pad[1]),{})
        if 'pin_delay_ps' in values:
            old=find(pad,'die_delay')
            if old:pad.remove(old)
            # PCB text uses ps; KiCad converts it to internal attoseconds on load.
            pad.append(S(Sym('die_delay'),Sym(str(round(values['pin_delay_ps'],6)))))

def analyze(spec,geo):
    from . import route_tuning
    compiled=compile(spec);rows=[]
    for group in compiled['groups']:
        delays={};lengths={};unknown=[issue['message'] for issue in compiled['issues'] if issue['severity']=='pending' and issue.get('bus_id') in group['bus_ids']];violations=[]
        for net in group['nets']:
            subset={key:[v for v in geo.get(key,[]) if v.get('net')==net] for key in ('pads','tracks','arcs','vias','zones')};subset['layers']=geo.get('layers',[])
            measured=route_tuning._route(spec,subset,net);lengths[net]=measured['length_mm'];delays[net]=measured['delay_ps']
            if not measured['ready'] or measured['delay_ps'] is None:unknown.append(net+': '+(measured.get('reason') or measured.get('delay_reason') or 'complete path and propagation model required'))
        skew=max(delays.values())-min(delays.values()) if delays and all(v is not None for v in delays.values()) else None
        if 'max_length_mm' in group:
            for net,length in lengths.items():
                if length is not None and length>group['max_length_mm']:violations.append(f'{net}: {length:g}mm exceeds {group["max_length_mm"]:g}mm')
        if 'pn_skew_ps' in group and skew is not None and skew>group['pn_skew_ps']:violations.append(f'Pair skew {skew:g}ps exceeds {group["pn_skew_ps"]:g}ps')
        if 'max_match_mm' in group and not unknown and max(lengths.values())-min(lengths.values())>group['max_match_mm']:violations.append('Bus length mismatch exceeds its configured limit.')
        estimate=_impedance_estimate(spec,group,geo)
        if group.get('impedance_ohms') is not None:
            if estimate['status']=='fail':violations.append('Nominal-stackup impedance estimate exceeds the configured tolerance.')
            elif estimate['status']=='unknown':unknown.append('Controlled impedance requires a tolerance and supported stackup/route verification.')
        timing_unknown=any(v is None for v in delays.values())
        rows.append({**group,'length_mm':lengths,'delay_ps':delays,'skew_ps':skew,'impedance':estimate,'timing_status':'unknown' if timing_unknown else 'fail' if group.get('pn_skew_ps') is not None and skew is not None and skew>group['pn_skew_ps'] else 'pass','status':'fail' if violations else 'unknown' if unknown else 'pass','unknown':unknown,'violations':violations,'model':'User-supplied layer/via ps/mm and pin delays (through-via barrel length uses board thickness); copper inside endpoint pads is excluded. Unspecified pin delays are zero. Only complete point-to-point paths are evaluated. Not a signal-integrity or physical measurement.'})
    matching=[]
    for bus in compiled['buses']:
        lanes=[row for row in rows if row['kind']=='diff' and bus['id'] in row['bus_ids']];limits=[m['properties']['pair_skew_ps'] for m in bus['members'] if 'pair_skew_ps' in m['properties']]
        if len(lanes)<2 or not limits:continue
        means={row['pair']:round(sum(row['delay_ps'].values())/2,6) if all(v is not None for v in row['delay_ps'].values()) else None for row in lanes}
        skew=round(max(means.values())-min(means.values()),6) if all(v is not None for v in means.values()) else None;limit=min(limits)
        matching.append({'bus_id':bus['id'],'pair_mean_delay_ps':means,'skew_ps':skew,'limit_ps':limit,'status':'unknown' if skew is None else 'fail' if skew>limit else 'pass','native_rule':False,'model':'Lane-mean timing comparison in this IDE, not a native all-net skew constraint.'})
    return {'pairs':[row for row in rows if row['kind']=='diff'],'singles':[row for row in rows if row['kind']=='single'],'buses':[row for row in rows if row['kind']=='bus'],'bus_matching':matching,'issues':compiled['issues']}

def project_draft(project,args):
    import tempfile,threading
    from pathlib import Path
    from fastapi import HTTPException
    from . import workbench_native,schematic_view,design
    from .workbench import validate_draft
    from .module_capture import native_copper
    from .kicad import board,geometry,schematic,cli
    with workbench_native._locks.setdefault(project.id,threading.RLock()):
        with project.lock:
            version=project.state.get('workbench',{}).get('version',0)
            if args.get('base_version',version)!=version:raise HTTPException(409,'The design changed before editing bus properties.')
            if getattr(project,'engine_busy',False) or project.worker and project.worker.is_alive() and project.worker is not threading.current_thread():raise HTTPException(409,'Wait for the active run before editing buses.')
            original=copy.deepcopy(project.state.get('spec') or {})
        if args.get('action')=='interface':
            preliminary=prepare(original,args)
            if not preliminary['interface_setup']['ready']:
                return{**preliminary,'spec':None,'base_version':version,'native_parity':None,'geometry':None,'analysis':None,'native_rules':[],'validation':None}
        pcb=workbench_native.final_pcb(project)
        if pcb is None:pcb=Path(workbench_native.generate(project)['pcb'])
        native_source=None
        if args.get('action') in {'stackup','pad_shape'}:
            from . import design_identity
            native_source={'source_identity':design_identity.fields(original),'source_pcb_sha256':hashlib.sha256(pcb.read_bytes()).hexdigest(),'source_render_inputs_sha256':workbench_native._plot_inputs(pcb)[1]}
        actual=geometry.read(pcb);spec=copy.deepcopy(original);spec['fixed_copper'],spec['fixed_zones']=native_copper(actual)
        if args.get('action')=='stackup' or original['board'].get('stackup'):
            from . import stackup
            spec['fixed_zones']=stackup.manual_zones(original,spec['fixed_zones'])
        ox,oy=actual.get('bbox',[100,100])[:2]
        for f in actual['footprints']:
            c=next((c for c in spec['components'] if c['ref']==f['ref']),None)
            if c:c['placement']={**c.get('placement',{}),'x_mm':round(f['x']-ox,6),'y_mm':round(f['y']-oy,6),'rotation':f.get('rot',0),'side':'bottom' if f.get('side')=='B.Cu' else 'top'}
        result=prepare(spec,args);draft=result['spec']
        if draft is None:return {**result,'base_version':version,'native_parity':None,'geometry':None,'analysis':None,'native_rules':[],'validation':None}
        validate_draft(draft)
        with tempfile.TemporaryDirectory(prefix='wholeboard-bus-') as folder:
            folder=Path(folder);native=schematic.build(draft,folder);proof=schematic.netlist_parity(draft,cli.schematic_nets(Path(native['sch'])))
            if not proof['ok']:raise ValueError('Bus properties changed the native pin connections.')
            emitted=board.build(draft,folder);preview=Path(emitted['pcb'])
            if draft.get('fixed_zones') or (draft['board'].get('stackup') and draft['board'].get('planes')):cli.drc(preview,refill=True,save=True)
            if draft['board'].get('stackup'):
                from . import stackup
                stackup.write_report(draft,preview)
            data=geometry.read(preview);result.update(native_parity=proof,geometry=data,analysis=analyze(draft,data),native_rules=native_rules(draft),validation=design.validate(draft).as_dict(),schematic=schematic_view.scene(draft))
            if args.get('action')=='stackup':
                from . import stackup
                result['stackup_report']['native_probe']=stackup.native_probe(draft,preview,folder)
            if args.get('action')=='pad_shape':
                import shutil
                baseline=folder/'baseline';shutil.copytree(pcb.parent,baseline);before=cli.drc(baseline/pcb.name,refill=False,save=False)
                after=cli.drc(preview,refill=False,save=False);plot=cli.export_svg(preview,folder/'custom-pad-plot.svg','F.Cu,B.Cu')
                result['shape_report'].update(native_probe={'ok':plot.is_file(),'method':'Actual KiCad SVG plot and DRC from the private candidate','before_drc':before,'after_drc':after},needs_review=bool(after['errors'] or after['unconnected']),native_instances=[{k:p[k] for k in ('id','ref','name','x','y','w','h','routing_anchor') if k in p} for p in data['pads'] if p['shape']=='custom'])
        with project.lock:
            if project.state.get('workbench',{}).get('version',0)!=version:raise HTTPException(409,'The design changed during bus review.')
        if native_source is not None:
            from . import route_tuning
            route_tuning.assert_source(project,native_source);result['native_source']=native_source
        result['base_version']=version;return result
