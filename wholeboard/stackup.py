"""Declared physical PCB construction and native stackup parameters.

Layer materials are engineering inputs, not manufacturer approval or a field solver.
Legacy boards remain unchanged until a reviewed construction is saved.
"""
from __future__ import annotations

import copy
import math
import re

COUNTS=(1,2,4,6,8,10,12)
TYPES={'copper','dielectric','solder_mask','solder_paste','silkscreen'}
ROLES={'signal','plane','mixed'}


def _text(value,limit=100):
    return isinstance(value,str) and 0<len(value)<=limit and value.isprintable()


def _number(value,minimum=0,maximum=20):
    return not isinstance(value,bool) and isinstance(value,(int,float)) and math.isfinite(value) and minimum<=value<=maximum


def copper_names(count):
    count=int(count)
    return ['F.Cu',*[f'In{i}.Cu' for i in range(1,max(0,count-2)+1)],*(['B.Cu'] if count>1 else [])]


def validate(spec):
    board=spec.get('board',{});recipe=board.get('stackup')
    if isinstance(board.get('layers',2),bool):raise ValueError('Copper layer count must be a supported number, not a boolean.')
    presets=spec.get('library',{}).get('stackups',{})
    if not isinstance(presets,dict) or len(presets)>30:raise ValueError('Project stackup presets must be a bounded object.')
    for name,value in presets.items():
        if not _text(name,80) or name in ('__proto__','prototype','constructor') or not isinstance(value,dict) or not isinstance(value.get('layers'),list):raise ValueError('Choose a bounded project preset name and physical recipe.')
        count=sum(isinstance(r,dict) and r.get('type')=='copper' for r in value['layers'])
        validate({'board':{'layers':count,'thickness_mm':thickness(value),'stackup':value},'nets':spec.get('nets',[])})
    if recipe is None:return
    if not isinstance(recipe,dict) or isinstance(recipe.get('schema'),bool) or recipe.get('schema')!=1 or not _text(recipe.get('name')):raise ValueError('Stackup needs schema1 and a bounded name.')
    layers=recipe.get('layers')
    if not isinstance(layers,list) or not 2<=len(layers)<=100:raise ValueError('Stackup needs a bounded ordered layer list.')
    count=board.get('layers',2)
    if isinstance(count,bool) or count not in COUNTS:raise ValueError('Choose a supported physical copper count.')
    known=set();copper=[];core=[];total=0;first_core=None;last_core=None
    for index,row in enumerate(layers):
        if not isinstance(row,dict) or not _text(row.get('id'),64) or not re.fullmatch(r'[a-zA-Z0-9_.-]+',row['id']) or row['id'] in known:raise ValueError('Each stackup layer needs a unique bounded ID.')
        known.add(row['id']);kind=row.get('type')
        if kind not in TYPES or not _text(row.get('material')):raise ValueError('Choose a supported layer type and material.')
        row_thickness=row.get('thickness_mm',0)
        if not _number(row_thickness,0,10):raise ValueError('Layer thickness must be a finite nonnegative millimeter value.')
        if kind in ('copper','dielectric') and row_thickness<=0:raise ValueError('Copper and dielectric thickness must be positive.')
        if kind in ('solder_paste','silkscreen') and row_thickness!=0:raise ValueError('Overlay and paste thickness are not part of the KiCad bare-board stackup; use zero.')
        if kind in ('copper','dielectric','solder_mask'):total+=row_thickness
        if kind in ('dielectric','solder_mask'):
            if not _number(row.get('epsilon_r'),1,100) or not _number(row.get('loss_tangent'),0,1):raise ValueError('Dielectric/mask requires declared relative permittivity and loss tangent.')
        if kind=='dielectric' and row.get('kind') not in ('core','prepreg'):raise ValueError('Choose core or prepreg for a dielectric.')
        if kind=='copper':
            if row.get('role','signal') not in ROLES:raise ValueError('Copper role is signal, plane or mixed.')
            expected=copper_names(count)[len(copper)] if len(copper)<count else None
            if row.get('native_layer',expected)!=expected:raise ValueError('Copper identities must follow the physical stack order.')
            if 'name' in row and not _text(row['name']):raise ValueError('Layer name must be bounded single-line text.')
            if row.get('net') not in (None,'') and (not _text(row['net']) or row['net'] not in {n['name'] for n in spec.get('nets',[])}):raise ValueError('A stackup reference net must exist in the design.')
            copper.append(row)
        if kind in ('copper','dielectric'):
            core.append(kind);first_core=index if first_core is None else first_core;last_core=index
        elif row.get('side') not in ('front','back'):raise ValueError('Technical layers need a front/back side.')
        if 'color' in row and not _text(row['color'],64):raise ValueError('Layer color must be bounded text.')
    if len(copper)!=count:raise ValueError('Stackup copper count does not match board.layers.')
    if count==1:
        if len(core)<2 or core[0]!='copper' or any(v!='dielectric' for v in core[1:]):raise ValueError('One-sided stackup needs front copper over its dielectric substrate.')
    elif core[0]!='copper' or core[-1]!='copper' or any(a==b=='copper' for a,b in zip(core,core[1:])):raise ValueError('Place dielectric material between every copper layer.')
    technical=set()
    for i,row in enumerate(layers):
        if row['type'] in ('copper','dielectric'):continue
        key=(row['type'],row['side'])
        if key in technical:raise ValueError('Only one technical layer of each type is allowed per side.')
        technical.add(key)
        if row['side']=='front' and i>=first_core or row['side']=='back' and i<=last_core:raise ValueError('Technical coatings must be outside the laminate.')
    if not _number(board.get('thickness_mm'),.02,10) or abs(total-board['thickness_mm'])>1e-6:raise ValueError('Board thickness must equal copper, dielectric and mask thicknesses.')
    if not _text(recipe.get('copper_finish','None'),80):raise ValueError('Choose a bounded copper finish.')


def standard(count=2,thickness=1.6):
    if count not in COUNTS or not _number(thickness,.05,10):raise ValueError('Choose a supported layer count and thickness.')
    remaining=round(thickness-count*.035-.02,6)
    if remaining<=0:raise ValueError('Board is too thin for the declared copper and masks.')
    gaps=max(1,count-1);gap=round(remaining/gaps,6);rows=[]
    def mask(side):return{'id':side+'-mask','type':'solder_mask','side':side,'material':'Solder Mask','thickness_mm':.01,'epsilon_r':3.3,'loss_tangent':.02,'color':'Green'}
    rows.extend([{'id':'front-silk','name':'Top Silkscreen','type':'silkscreen','side':'front','material':'Silkscreen','thickness_mm':0,'color':'Cyan'},{'id':'front-paste','name':'Top Solder Paste','type':'solder_paste','side':'front','material':'PbSn','thickness_mm':0}]);rows.append(mask('front'))
    for i,name in enumerate(copper_names(count)):
        rows.append({'id':'copper-'+name.replace('.','_'),'type':'copper','native_layer':name,'name':'Top Copper' if i==0 else 'Bottom Copper' if i==count-1 else 'Inner Copper '+str(i),'role':'plane' if 0<i<count-1 else 'signal','material':'Copper','thickness_mm':.035})
        if i<count-1 or count==1:
            n=i+1;t=round(remaining-gap*(gaps-1),6) if n==gaps else gap
            rows.append({'id':'dielectric-'+str(n),'type':'dielectric','kind':'core' if count==2 or n%2==0 else 'prepreg','material':'FR4','thickness_mm':t,'epsilon_r':4.5,'loss_tangent':.02})
    rows.append(mask('back'));rows.extend([{'id':'back-paste','name':'Bottom Solder Paste','type':'solder_paste','side':'back','material':'PbSn','thickness_mm':0},{'id':'back-silk','name':'Bottom Silkscreen','type':'silkscreen','side':'back','material':'Silkscreen','thickness_mm':0,'color':'Magenta'}])
    return{'schema':1,'name':f'Standard {count} Layer','copper_finish':'None','layers':rows,'basis':'Generic declared material assumptions; verify the fabrication construction.'}


def parameters(board,layer='F.Cu'):
    """Nearest declared plane, without skipping intervening signal copper."""
    recipe=board.get('stackup')
    if not recipe:return None
    layers=recipe['layers'];cu=[(i,row) for i,row in enumerate(layers) if row['type']=='copper'];names=copper_names(len(cu))
    if layer not in ('F.Cu','B.Cu') or layer not in names or len(cu)<2:return None
    slot=names.index(layer);direction=1 if slot==0 else -1;start,trace=cu[slot];end,plane=cu[slot+direction]
    if plane.get('role') not in ('plane','mixed'):return None
    dielectric=[row for row in layers[min(start,end)+1:max(start,end)] if row['type']=='dielectric'];height=sum(row['thickness_mm'] for row in dielectric)
    if not height:return None
    er=height/sum(row['thickness_mm']/row['epsilon_r'] for row in dielectric)
    return{'name':recipe['name'],'h':height,'er':er,'copper_mm':trace['thickness_mm'],'reference_layer':names[slot+direction],
           'reference_net':plane.get('net'),'source':'declared_stackup','model':'Outer-layer IPC-2141; multilayer dielectric uses a series-capacitance effective permittivity, not a field solver.'}


def native_node(board):
    from .sexpr import S,Sym
    recipe=board.get('stackup')
    if recipe is None:
        if board.get('layers',2)!=1:return None
        recipe=standard(1,float(board.get('thickness_mm',1.6)))
    rows=recipe['layers'];result=[Sym('stackup')];dielectric=0;cu=0;seen=set()
    for row in rows:
        kind=row['type']
        if kind=='copper':name=copper_names(board['layers'])[cu];cu+=1;description='copper'
        elif kind=='dielectric':dielectric+=1;name='dielectric '+str(dielectric);description=row['kind']
        else:name=('F.' if row['side']=='front' else 'B.')+{'solder_mask':'Mask','solder_paste':'Paste','silkscreen':'SilkS'}[kind];description={'solder_mask':'soldermask','solder_paste':'solderpaste','silkscreen':'silkscreen'}[kind]
        if board['layers']==1 and kind=='solder_mask' and row['side']=='back' and 'B.Cu' not in seen:
            result.append([Sym('layer'),'B.Cu',S(Sym('type'),'copper'),S(Sym('thickness'),0)]);seen.add('B.Cu')
        node=[Sym('layer'),name,S(Sym('type'),description)];seen.add(name)
        if kind in ('copper','dielectric','solder_mask'):node.append(S(Sym('thickness'),row['thickness_mm']))
        if kind!='copper':node.append(S(Sym('material'),row['material']))
        for key in ('epsilon_r','loss_tangent','color'):
            if key in row:node.append(S(Sym(key),row[key]))
        result.append(node)
    if board['layers']==1 and 'B.Cu' not in seen:result.append([Sym('layer'),'B.Cu',S(Sym('type'),'copper'),S(Sym('thickness'),0)])
    for name in ('F.Mask','B.Mask'):
        if name not in seen:result.append([Sym('layer'),name,S(Sym('type'),'soldermask'),S(Sym('thickness'),0),S(Sym('epsilon_r'),1)])
    result.append(S(Sym('copper_finish'),recipe.get('copper_finish','None')))
    return result


def templates(spec=None):
    result=[{'id':f'standard-{n}','name':f'Standard {n} Layer','group':'Standard','stackup':standard(n)} for n in COUNTS]
    for code,prepreg,h,core in (('7628',4.4,.2104,1.065),('3313',4.1,.0994,1.265)):
        construction=standard(4);construction.update(name='JLC04161H-'+code,nominal_thickness_mm=1.6,source_url='https://jlcpcb.com/impedance',basis='Published copper/dielectric construction. Flat mask uses the published above-trace15.24um value; loss tangents are declared generic assumptions, not a supplier guarantee.')
        for row in construction['layers']:
            if row['type']=='copper':row['thickness_mm']=.035 if row['native_layer'] in ('F.Cu','B.Cu') else .0152
            elif row['type']=='solder_mask':row.update(thickness_mm=.01524,epsilon_r=3.8)
            elif row['type']=='dielectric' and row['kind']=='prepreg':row.update(thickness_mm=h,epsilon_r=prepreg,material=code+' prepreg')
            elif row['type']=='dielectric':row.update(thickness_mm=core,epsilon_r=4.6,material='FR4 core')
        result.append({'id':'jlc-'+code,'name':construction['name'],'group':'Published construction','stackup':construction})
    for name,construction in ((spec or {}).get('library',{}).get('stackups',{}) or {}).items():
        result.append({'id':'project:'+name,'name':name,'group':'Project presets','stackup':copy.deepcopy(construction)})
    return result


def thickness(recipe):
    return round(sum(r.get('thickness_mm',0) for r in recipe['layers'] if r['type'] in ('copper','dielectric','solder_mask')),6)


def canonical(recipe):
    out=copy.deepcopy(recipe);copper=[r for r in out.get('layers',[]) if isinstance(r,dict) and r.get('type')=='copper']
    for name,row in zip(copper_names(len(copper)),copper):row['native_layer']=name
    return out


def summary(board):
    construction=board.get('stackup') or standard(int(board.get('layers',2)),float(board.get('thickness_mm',1.6)))
    return {'name':construction['name'],'copper_count':sum(r['type']=='copper' for r in construction['layers']),'thickness_mm':thickness(construction),
            'source':'declared' if board.get('stackup') else 'generic_preview_only','front_parameters':parameters({**board,'stackup':construction},'F.Cu'),
            'back_parameters':parameters({**board,'stackup':construction},'B.Cu'),'physical_copper_layers':copper_names(int(board.get('layers',2))),
            'native_compatibility':'KiCad uses an unused zero-thickness B.Cu slot; one-sided fabrication excludes B.Cu.' if board.get('layers')==1 else None}


def plane_map(board):
    result=dict(board.get('planes',{}));rows=[r for r in board.get('stackup',{}).get('layers',[]) if r['type']=='copper']
    for name,row in zip(copper_names(len(rows)),rows):
        if 'net' in row:
            if row['net']:result[name]=row['net']
            else:result.pop(name,None)
    return result


def manual_zones(spec,zones):
    """Keep explicit/manual zones; generated planes remain generated declarations."""
    from .sexpr import parse,find
    from .kicad.board import uid
    def identifier(zone):
        value=find(parse(zone['source']),'uuid')
        return str(value[1]) if value else zone.get('id')
    explicit={identifier(z) for z in spec.get('fixed_zones',[])}
    generated={uid(f'generated-zone:{net}:{layer}') for layer,net in plane_map(spec['board']).items()}-explicit
    return [z for z in zones if identifier(z) not in generated]


def write_report(spec,pcb):
    import json,hashlib
    from pathlib import Path
    board=spec['board']
    if not board.get('stackup') and board.get('layers')!=1:return None
    construction=copy.deepcopy(board.get('stackup') or standard(1,float(board.get('thickness_mm',1.6))))
    target=Path(pcb).with_suffix('.stackup.json');value={'schema':1,'construction':construction,'summary':summary(board),'native_pcb_sha256':hashlib.sha256(Path(pcb).read_bytes()).hexdigest(),
            'limits':['Declared construction, not a supplier approval or measured SI result.','Copper process labels and application row IDs are retained in this portable recipe.','KiCad bare-board thickness includes copper, dielectric and mask; overlay/paste thickness does not contribute.']}
    target.write_text(json.dumps(value,indent=2,ensure_ascii=False),encoding='utf-8');return target


def inspect(spec):
    return {'stackup':copy.deepcopy(spec['board'].get('stackup') or standard(int(spec['board'].get('layers',2)),float(spec['board'].get('thickness_mm',1.6)))),
            'inferred':not bool(spec['board'].get('stackup')),'summary':summary(spec['board']),'templates':templates(spec),
            'rules':copy.deepcopy(spec.get('rules',{})),'nets':[n['name'] for n in spec.get('nets',[])]}


def _layer_use(spec):
    used={}
    def add(layer,kind,identifier):
        if isinstance(layer,str) and layer.endswith('.Cu'):used.setdefault(layer,[]).append({'kind':kind,'id':identifier})
    for group in spec.get('fixed_copper',[]):
        for kind in ('tracks','arcs','vias'):
            for item in group.get(kind,[]):
                for layer in item.get('layers',[item.get('layer')]):add(layer,kind,item.get('id'))
    for zone in spec.get('fixed_zones',[]):
        for layer in zone.get('layers',[zone.get('layer')]):add(layer,'zones',zone.get('id'))
    from .kicad import libs
    from .design import pcb_excluded
    for component in spec.get('components',[]):
        if pcb_excluded(component):continue
        footprint=libs.load_footprint(component.get('footprint',''),spec)
        if footprint:
            from .kicad import board
            from .sexpr import find_all,find
            instance=board.footprint_instance(footprint,component['ref'],component.get('value',''),0,0,bottom=component.get('placement',{}).get('side')=='bottom',pad_overrides=component.get('pad_overrides'))
            for pad in find_all(instance,'pad'):
                explicit=[str(v) for v in find(pad,'layers')[1:] if str(v).endswith('.Cu') and str(v)!='*.Cu']
                for layer in explicit:add(layer,'component pads' if str(pad[2]) in {'smd','connect'} else 'instance pad annuli',component['ref'])
    return used


def prepare(spec,args):
    if not isinstance(args,dict):raise ValueError('Stackup edits need an object.')
    chosen=args.get('stackup')
    if args.get('template'):
        entry=next((r for r in templates(spec) if r['id']==args['template']),None)
        if not entry:raise ValueError('Choose an available stackup template.')
        if chosen is not None:raise ValueError('Choose a template or an edited construction, not both.')
        chosen=entry['stackup']
    if not isinstance(chosen,dict):raise ValueError('Provide an editable stackup construction.')
    recipe=canonical(chosen);out=copy.deepcopy(spec);out['board'].update(stackup=recipe,layers=sum(r['type']=='copper' for r in recipe['layers']),thickness_mm=thickness(recipe));validate(out)
    original=spec['board'].get('stackup');old_names=copper_names(int(spec['board'].get('layers',2)));new_names=copper_names(out['board']['layers'])
    old_rows=[r for r in (original or {}).get('layers',[]) if r.get('type')=='copper'];new_by_id={r['id']:r['native_layer'] for r in recipe['layers'] if r['type']=='copper'};mapping={}
    for i,name in enumerate(old_names):
        by_id=new_by_id.get(old_rows[i]['id']) if original and not args.get('template') and i<len(old_rows) else None
        mapping[name]=by_id or (name if name in new_names else None)
    overrides=args.get('layer_map',{})
    if not isinstance(overrides,dict) or set(overrides)-set(old_names) or any(v is not None and v not in new_names for v in overrides.values()):raise ValueError('Layer mappings must refer to current and target copper layers; null explicitly removes that layer copper.')
    mapping.update(overrides);usage=_layer_use(spec);conflicts=[];issues=[];removed={key:0 for key in ('tracks','arcs','vias','zones')}
    for name,objects in usage.items():
        destination=mapping.get(name)
        if destination is None and name not in overrides:conflicts.append({'layer':name,'objects':objects,'message':'Choose a destination or explicitly remove this layer copper.'})
        if any(o['kind']=='component pads' for o in objects) and destination!=name:issues.append({'layer':name,'message':'Surface-mount components require this outer copper side. Move/flip the components explicitly before changing that side.'})
    from . import pad_edits
    from .sexpr import find,dumps
    from .kicad import board as pcb_board
    for component in out.get('components',[]):
        bottom=component.get('placement',{}).get('side')=='bottom'
        for entry in component.get('pad_overrides',{}).values():
            node=pad_edits.parsed(entry['source']);layers=find(node,'layers');mapped=[]
            for layer in layers[1:]:
                layer=str(layer)
                if layer.endswith('.Cu') and layer!='*.Cu':
                    physical=pcb_board._flip_layer(layer) if bottom else layer;destination=mapping.get(physical)
                    if destination is None:continue
                    layer=pcb_board._flip_layer(destination) if bottom else destination
                if layer not in mapped:mapped.append(layer)
            if str(node[2])=='thru_hole' and not any(v.endswith('.Cu') for v in mapped):issues.append({'layer':','.join(str(v) for v in layers[1:]),'message':'A plated instance pad would lose every annulus. Reset or edit that pad explicitly.'})
            layers[1:]=mapped
            if entry.get('annuli_policy')=='hole-profile-v1':pad_edits.annuli(node,[pcb_board._flip_layer(v) if bottom else v for v in new_names])
            entry['source']=dumps(node)
    for group in out.get('fixed_copper',[]):
        for kind in ('tracks','arcs','vias'):
            kept=[]
            for item in group.get(kind,[]):
                if kind=='vias':
                    original_layers=item.get('layers',['F.Cu','B.Cu']);span=[mapping.get(layer) for layer in original_layers]
                    if any(v is None for v in span):removed[kind]+=1;continue
                    if len(set(span))!=len(span):issues.append({'layer':','.join(original_layers),'message':'Via endpoints would collapse onto one layer. Resolve the via explicitly.'})
                    item['layers']=span
                else:
                    destination=mapping.get(item['layer'])
                    if destination is None:removed[kind]+=1;continue
                    item['layer']=destination
                kept.append(item)
            if kind in group:group[kind]=kept
    if 'fixed_copper' in out:out['fixed_copper']=[g for g in out['fixed_copper'] if any(g.get(k) for k in ('tracks','arcs','vias'))]
    zones=[]
    for zone in out.get('fixed_zones',[]):
        old=zone.get('layers',[zone.get('layer')]);mapped=list(dict.fromkeys(mapping.get(layer) for layer in old if mapping.get(layer)))
        if not mapped:removed['zones']+=1;continue
        if 'layers' in zone:zone['layers']=mapped
        else:zone['layer']=mapped[0]
        if 'source' in zone:
            from .sexpr import parse,find,dumps
            node=parse(zone['source']);one=find(node,'layer');many=find(node,'layers')
            if one:one[1]=mapped[0]
            if many:many[1:]=mapped
            zone['source']=dumps(node)
        zones.append(zone)
    if 'fixed_zones' in out:out['fixed_zones']=zones
    prior_planes={mapping.get(layer):net for layer,net in spec['board'].get('planes',{}).items() if mapping.get(layer)};planes={}
    for row in recipe['layers']:
        if row['type']!='copper':continue
        if 'net' not in row and row['native_layer'] in prior_planes:row['net']=prior_planes[row['native_layer']]
        if row.get('net'):planes[row['native_layer']]=row['net']
    out['board']['planes']=planes
    timing=out['board'].get('timing',{});delays=timing.get('track_ps_per_mm')
    if delays is not None:timing['track_ps_per_mm']={mapping[layer]:value for layer,value in delays.items() if mapping.get(layer)}
    for group in out.get('impedance',[]):
        if group.get('layer') in mapping:
            destination=mapping[group['layer']]
            if destination:group['layer']=destination
            else:issues.append({'layer':group['layer'],'message':'An explicit impedance layer target was removed; update it before applying.'})
    via=args.get('via')
    if via is not None:
        if not isinstance(via,dict) or set(via)!={'diameter_mm','drill_mm'} or not all(_number(v,.001,20) for v in via.values()) or via['drill_mm']>=via['diameter_mm']:raise ValueError('Through-via defaults need a positive drill smaller than the diameter.')
        out.setdefault('rules',{}).update(via_diameter_mm=via['diameter_mm'],via_drill_mm=via['drill_mm'])
    save=args.get('save_preset')
    if save:
        if not _text(save,80) or save in ('__proto__','prototype','constructor'):raise ValueError('Choose a bounded project preset name.')
        portable=copy.deepcopy(recipe)
        for row in portable['layers']:row.pop('net',None)
        out.setdefault('library',{}).setdefault('stackups',{})[save]=portable
    from . import buses
    validate(out);report={**summary(out['board']),'ready':not conflicts and not issues,'conflicts':conflicts,'issues':issues,'layer_map':mapping,'layer_usage':usage,'removed_copper':removed,
                         'warnings':['Existing propagation delays remain user-declared; review them for the changed construction.'] if delays else []}
    return {'spec':out if report['ready'] else None,'stackup_report':report,'buses':buses.compile(out)}


def native_probe(spec,pcb,folder):
    """Let the installed KiCad parser consume the construction in a private folder."""
    import xml.etree.ElementTree as ET
    from .kicad import cli
    target=folder/'stackup-ipc.xml';result=cli.run(['pcb','export','ipc2581','--units','mm','--precision','8','--output',str(target),str(pcb)])
    if result.returncode or not target.is_file():raise ValueError('KiCad could not read the proposed stackup: '+result.stderr[-1000:])
    tree=ET.parse(target).getroot();rows=[{'layer':r.attrib['layerOrGroupRef'],'thickness_mm':float(r.attrib['thickness'])} for r in tree.iter() if r.tag.rsplit('}',1)[-1]=='StackupLayer'];positive=[r for r in rows if r['layer'].endswith('.Cu') and r['thickness_mm']>0]
    if len(positive)!=spec['board']['layers']:raise ValueError('KiCad parsed a different active copper count.')
    return {'ok':True,'method':'Real KiCad IPC-2581 export from the private candidate','copper_count':len(positive),'layers':rows,'source':'declared_stackup','file':target.name,'precision_note':'IPC numeric formatting may round individual values; the native PCB and stackup recipe retain full declared precision.'}
