"""Editable named-net annotations on real schematic wire nodes, never PCB parts."""
from __future__ import annotations
import copy
import hashlib
import math
import re
import tempfile
import threading
import uuid
from pathlib import Path
from . import sheets,project_library

KINDS=('auto','net','power','ground')

def validate_label(value):
    if not isinstance(value,dict) or value.get('kind') not in KINDS:raise ValueError('A net label needs a supported symbol kind.')
    rotation=value.get('rotation',0)
    if isinstance(rotation,bool) or not isinstance(rotation,(int,float)) or abs(rotation)>360000 or not math.isfinite(rotation) or rotation%90:raise ValueError('Label rotation must be a bounded finite multiple of 90 degrees.')
    if value.get('mirror','') not in ('','x','y'):raise ValueError('A power-symbol mirror needs x or y.')

def kind(spec,node):
    value=node['label'].get('kind','auto')
    if value!='auto':return value
    net=next(n for n in spec['nets'] if n['name']==node['net'])
    return ('ground' if net['name']=='GND' else 'power') if net.get('class')=='power' else 'net'

def native_spec(spec):
    """KiCad power symbols are native annotations, excluded by KiCad from netlist parts."""
    power_nodes=[(key,node) for key,node in spec.get('editor',{}).get('wire_nodes',{}).items() if node.get('label') and kind(spec,node)!='net']
    if not power_nodes:return spec,{}
    out=copy.deepcopy(spec);refs={}
    for identifier,node in power_nodes:
        ref='#PWR'+str(int(hashlib.sha256(identifier.encode()).hexdigest()[:12],16));refs[ref]=identifier
        out['components'].append({'ref':ref,'value':node['net'],'symbol':'power:GND' if kind(spec,node)=='ground' else 'power:VCC','footprint':'','sheet':node.get('sheet',''),
          'terminal':{'exclude_from_pcb':True,'expose':False},'_net_label':identifier})
        out['editor'].setdefault('positions',{})[ref]=copy.deepcopy(node['position']);out['editor'].setdefault('rotations',{})[ref]=node['label'].get('rotation',0)
        if node['label'].get('mirror'):out['editor'].setdefault('mirrors',{})[ref]=node['label']['mirror']
        next(n for n in out['nets'] if n['name']==node['net'])['pins'].append(ref+'.1')
    return out,refs

def _name(name):
    if not isinstance(name,str) or not name.strip() or not name.isprintable() or not project_library.text(name,100):raise ValueError('Net label names need 1–100 printable characters.')
    return name.strip()

def rename_references(spec,old,new,*,rebase=False):
    from . import object_groups
    object_groups.rename_net(spec,old,new)
    editor=spec.get('editor',{})
    for node in editor.get('wire_nodes',{}).values():
        if node['net']==old:node['net']=new
    for sheet in editor.get('sheets',{}).values():
        for port in sheet.get('ports',{}).values():
            if port['net']==old:port['net']=new
    for meta in editor.get('module_instances',{}).values():
        maps=[meta.get('nets',{}),meta.get('source_maps',{}).get('nets',{})]
        if rebase:maps.append(meta.get('baseline',{}).get('maps',{}).get('nets',{}))
        for mapping in maps:
            for key,value in mapping.items():
                if value==old:mapping[key]=new
        for key,values in meta.get('net_splits',{}).items():meta['net_splits'][key]=list(dict.fromkeys(new if name==old else name for name in values))
    for row in [*spec.get('fixed_copper',[]),*spec.get('fixed_zones',[])]:
        if row['net']==old:row['net']=new
    board=spec['board']
    if board.get('ground_pour')==old:board['ground_pour']=new
    for layer,name in board.get('planes',{}).items():
        if name==old:board['planes'][layer]=new
    sim=spec.get('simulation') or {}
    for row in [*sim.get('sources',[]),*sim.get('expect',[])]:
        if row.get('net')==old:row['net']=new
    if sim.get('probes'):sim['probes']=[new if name==old else name for name in sim['probes']]
    for row in spec.get('impedance',[]):
        if row.get('net')==old:row['net']=new
        if row.get('nets'):row['nets']=[new if name==old else name for name in row['nets']]

def _invalidate(spec,names):
    spec['fixed_copper']=[g for g in spec.get('fixed_copper',[]) if g['net'] not in names]
    spec['fixed_zones']=[g for g in spec.get('fixed_zones',[]) if g['net'] not in names]
    if spec['board'].get('ground_pour') in names:spec['board']['ground_pour']=None
    spec['board']['planes']={k:v for k,v in spec['board'].get('planes',{}).items() if v not in names}

def _temporary(spec,net):
    if net.get('class','signal')!='signal':return False
    placeholder=net.get('placeholder_ref')
    temporary=net.get('wire_only') and len(net['pins'])<=1 or placeholder and net['pins']==[placeholder+'.1'] and any(c['ref']==placeholder and c.get('terminal') for c in spec['components'])
    if not temporary:return False
    return not (any(g['net']==net['name'] and any(g.get(k) for k in ('tracks','arcs','vias')) for g in spec.get('fixed_copper',[])) or any(z['net']==net['name'] for z in spec.get('fixed_zones',[])) or spec['board'].get('ground_pour')==net['name'] or net['name'] in spec['board'].get('planes',{}).values())

def _anchor(spec,anchor):
    from . import schematic_view
    if not isinstance(anchor,str):raise ValueError('Choose a schematic pin or wire endpoint.')
    scene=schematic_view.scene(spec);found=next((a for a in scene['anchors'] if a['anchor']==anchor),None)
    if not found:raise ValueError('Choose a visible native pin or wire endpoint.')
    if anchor.startswith('node:'):net=spec['editor']['wire_nodes'][anchor[5:]]['net'];pin=None
    elif anchor.startswith('sheet:'):
        from urllib.parse import unquote
        page,label=anchor[6:].split('.',1);net=sheets.boundaries(spec)[page][unquote(label)]['net'];pin=None
    else:
        pin=re.sub(r'#\d+(?=\.)','',anchor);net=next((n['name'] for n in spec['nets'] if pin in n['pins']),None)
    return {**found,'net':net,'pin':pin}

def _split_wire(spec,wire,position,page):
    from . import schematic_view
    if not isinstance(position,list) or len(position)!=2 or any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in position):raise ValueError('Choose a finite label point on a native wire.')
    route=next((r for r in schematic_view.scene(spec)['routes'] if r['id']==wire and r['sheet']==page and r['status']=='routed'),None)
    if not route:raise ValueError('The native wire changed. Select it again.')
    points=route['points'];total=sum(math.dist(a,b) for a,b in zip(points,points[1:]));best=None;offset=0
    for index,(a,b) in enumerate(zip(points,points[1:])):
        length=math.dist(a,b)
        if not length:continue
        t=max(0,min(1,sum((position[i]-a[i])*(b[i]-a[i]) for i in range(2))/length**2));p=[a[i]+t*(b[i]-a[i]) for i in range(2)];distance=math.dist(p,position)
        if best is None or distance<best[0]:best=(distance,index,p,(offset+t*length)/total)
        offset+=length
    if best is None or best[0]>10 or not .00001<best[3]<.99999:raise ValueError('Place a label inside the native wire, away from its ends.')
    _,index,p,fraction=best;axis=0 if abs(points[index+1][0]-points[index][0])>=abs(points[index+1][1]-points[index][1]) else 1
    a,b=points[index:index+2];p[axis]=max(min(a[axis],b[axis]),min(max(a[axis],b[axis]),round(p[axis]/10)*10));t=(p[axis]-a[axis])/(b[axis]-a[axis]);p[1-axis]=a[1-axis]+t*(b[1-axis]-a[1-axis]);fraction=(sum(math.dist(a,b) for a,b in zip(points[:index+1],points[1:index+1]))+math.dist(a,p))/total
    if not .00001<fraction<.99999:raise ValueError('Place the label away from the wire ends.')
    editor=spec['editor'];guides=editor['connection_guides'];old=guides[route['index']];identifier=str(uuid.uuid4());right_id=str(uuid.uuid4())
    editor.setdefault('wire_nodes',{})[identifier]={'position':p,'sheet':page,'net':route['net']}
    def compact(values):return [copy.deepcopy(v) for i,v in enumerate(values) if not i or math.dist(v,values[i-1])>.0001]
    left={**copy.deepcopy(old),'to':'node:'+identifier,'fixed_points':compact([*points[:index+1],p])};right={**copy.deepcopy(old),'id':right_id,'from':'node:'+identifier,'fixed_points':compact([p,*points[index+1:]])}
    left.pop('to_join',None);right.pop('from_join',None);left.pop('waypoints',None);right.pop('waypoints',None);guides[route['index']:route['index']+1]=[left,right]
    for guide in guides:
        for key in ('from_join','to_join'):
            if guide.get(key,{}).get('wire')!=old['id']:continue
            offset=guide[key]['offset'];parent=left if offset<=fraction else right;guide[key]={'wire':parent['id'],'offset':offset/fraction if offset<=fraction else (offset-fraction)/(1-fraction)};guide[key[:-5]]=parent['from']
    return identifier

def prepare(spec,arguments):
    out=copy.deepcopy(spec);action=arguments.get('action');editor=out.setdefault('editor',{});nodes=editor.setdefault('wire_nodes',{});identifier=arguments.get('id');anchor=None;merge=None;invalid=[]
    if action not in ('add','update','delete'):raise ValueError('Choose add, update or delete for a net label.')
    if identifier is not None and not isinstance(identifier,str):raise ValueError('Choose a label or wire endpoint ID.')
    if 'confirm_merge' in arguments and not isinstance(arguments['confirm_merge'],bool):raise ValueError('Confirm a network merge explicitly.')
    if action!='add' and (identifier not in nodes or not nodes[identifier].get('label')):raise ValueError('Choose an existing net label.')
    if action=='delete':
        nodes[identifier].pop('label')
        if not any('node:'+identifier in (g['from'],g['to']) for g in editor.get('connection_guides',[])):nodes.pop(identifier)
        return {'spec':out,'id':identifier,'merge':None,'summary':{'invalidated_nets':[],'removed_labels':1}}
    patch=arguments.get('patch',{}) if action=='update' else arguments
    if not isinstance(patch,dict):raise ValueError('Label properties need an object.')
    if action=='add':
        if arguments.get('wire'):
            identifier=_split_wire(out,arguments['wire'],arguments.get('position'),arguments.get('sheet',''));patch={**patch,'position':nodes[identifier]['position']}
        if arguments.get('anchor'):anchor=_anchor(out,arguments['anchor'])
        if identifier is not None:
            if identifier not in nodes or nodes[identifier].get('label'):raise ValueError('Choose an unlabeled wire endpoint.')
            old=nodes[identifier]['net'];node=nodes[identifier]
        else:
            identifier=str(uuid.uuid4());old=anchor['net'] if anchor else None
            if anchor:
                delta=[anchor['escape'][i]-anchor['position'][i] for i in range(2)]
                position=[round((v+(math.copysign(100,delta[i]) if abs(delta[i])>.01 else -100 if i==1 and not any(abs(d)>.01 for d in delta) else 0))/10)*10 for i,v in enumerate(anchor['position'])]
            else:position=[180,160]
            node={'sheet':arguments.get('sheet',anchor['sheet'] if anchor else ''),'position':arguments.get('position',position),'net':old};nodes[identifier]=node
        cfg={'kind':patch.get('kind','auto'),'rotation':patch.get('rotation',0)}
    else:node=nodes[identifier];old=node['net'];cfg={**node['label'],**{k:patch[k] for k in ('kind','rotation') if k in patch}}
    validate_label(cfg)
    cfg['rotation']=cfg.get('rotation',0)%360
    new_ground=cfg['kind']=='ground' and (action=='add' or patch.get('kind')=='ground' and node.get('label',{}).get('kind')!='ground')
    name=_name(patch.get('net','GND' if new_ground else old or 'Net_1'))
    target=next((n for n in out['nets'] if n['name']==name),None);source=next((n for n in out['nets'] if n['name']==old),None)
    if source is not None and source is not target:
        if target is not None:
            binding=_temporary(out,source) or _temporary(out,target)
            if not binding:
                merge={'from':old,'to':name,'from_pins':copy.deepcopy(source['pins']),'to_pins':copy.deepcopy(target['pins'])}
                if not arguments.get('confirm_merge'):return {'spec':None,'id':identifier,'merge':merge,'summary':{'invalidated_nets':sorted([old,name])}}
                invalid=sorted([old,name]);_invalidate(out,set(invalid))
            rebase=binding and not _temporary(out,source)
            target['pins']=list(dict.fromkeys([*target['pins'],*source['pins']]));out['nets'].remove(source);rename_references(out,old,name,rebase=rebase)
        else:source['name']=name;target=source;rename_references(out,old,name,rebase=True)
    if target is None:target={'name':name,'class':'power' if cfg['kind'] in ('power','ground') else 'signal','pins':[]};out['nets'].append(target)
    if 'net_type' in patch:
        if patch['net_type'] not in ('signal','power'):raise ValueError('Choose signal or power for Net Type.')
        target['class']=patch['net_type']
    if cfg['kind'] in ('power','ground'):target['class']='power'
    target.pop('wire_only',None);target.pop('placeholder_ref',None)
    if anchor and anchor['pin']:
        if anchor['pin'] not in target['pins']:target['pins'].append(anchor['pin'])
        ref,pad=anchor['pin'].split('.',1);component=next(c for c in out['components'] if c['ref']==ref)
        if component.get('no_connect'):component['no_connect']=[p for p in component['no_connect'] if str(p)!=pad]
    node['net']=name;node['label']=cfg
    if 'position' in patch:node['position']=copy.deepcopy(patch['position'])
    if node.get('sheet','') not in {'',*sheets.definitions(out)}:raise ValueError('A label belongs to an existing sheet.')
    if anchor:
        if node.get('sheet','')!=anchor['sheet']:raise ValueError('A label wire must remain on its anchor sheet.')
        editor.setdefault('connection_guides',[]).append({'id':str(uuid.uuid4()),'from':arguments['anchor'],'to':'node:'+identifier})
    from . import wire_nodes
    wire_nodes.validate(out)
    return {'spec':out,'id':identifier,'merge':merge,'summary':{'invalidated_nets':invalid,'net':name,'kind':cfg['kind'],'pins':len(target['pins'])}}

def project_draft(project,arguments):
    from fastapi import HTTPException
    from . import workbench_native,schematic_view,design
    from .workbench import validate_draft
    from .module_capture import native_copper
    from .kicad import schematic,cli,board,geometry
    with workbench_native._locks.setdefault(project.id,threading.RLock()):
        with project.lock:
            version=project.state.get('workbench',{}).get('version',0)
            if arguments.get('base_version',version)!=version:raise HTTPException(409,'The design changed before preparing this label.')
            if getattr(project,'engine_busy',False) or project.worker and project.worker.is_alive() and project.worker is not threading.current_thread():raise HTTPException(409,'Wait for the active run before editing labels.')
            spec=copy.deepcopy(project.state.get('spec') or {})
        pcb=workbench_native.final_pcb(project) or Path(workbench_native.generate(project)['pcb']);spec['fixed_copper'],spec['fixed_zones']=native_copper(geometry.read(pcb))
        result=prepare(spec,arguments);result['base_version']=version
        if result['spec'] is not None:
            draft=result['spec'];validate_draft(draft)
            with tempfile.TemporaryDirectory(prefix='wholeboard-label-') as directory:
                folder=Path(directory);native=schematic.build(draft,folder);proof=schematic.netlist_parity(draft,cli.schematic_nets(Path(native['sch'])))
                if not proof['ok']:raise ValueError('Named labels do not match the native KiCad connections.')
                pcb=Path(board.build(draft,folder)['pcb'])
                if draft.get('fixed_zones'):cli.drc(pcb,refill=True,save=True)
                result['native_parity']=proof;result['geometry']=geometry.read(pcb)
            result['schematic']=schematic_view.scene(draft);result['validation']=design.validate(draft).as_dict()
        with project.lock:
            if project.state.get('workbench',{}).get('version',0)!=version:raise HTTPException(409,'The design changed while preparing this label.')
        return result
