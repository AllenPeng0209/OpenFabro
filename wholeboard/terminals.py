"""Single-pin schematic/module interfaces, optionally backed by a bare PCB pad."""
from __future__ import annotations
import copy
import math
from . import project_library

DIRECTIONS={'passive','input','output','bidirectional','tri_state'}
SIDES={'left','right','top','bottom'}


def ordered_ports(values):
    if not any(any(key in value for key in ('number','order','group','section')) for value in values.values()):return list(values.items())
    def key(item):
        label,value=item;number=value.get('number','')
        return (value.get('section',''),value.get('group',''),value.get('order',0),(0,int(number)) if str(number).isdigit() else (1,str(number)),label)
    return sorted(values.items(),key=key)


def excluded(component):
    terminal=component.get('terminal')
    return isinstance(terminal,dict) and terminal.get('exclude_from_pcb') is True


def port(component,net):
    value=component.get('terminal') or {}
    return {'net':net,'terminal_ref':component['ref'],'direction':value.get('direction','passive'),'number':value.get('number','1'),'side':value.get('side','left'),'order':value.get('order',0),'group':value.get('group',''),'section':value.get('section',''),**component.get('pin_properties',{}).get('1',{}),**({'bus_type':component['bus_type']} if component.get('bus_type') and not component.get('pin_properties',{}).get('1',{}).get('bus_type') else {})}


def declarations(spec,*,sheet=None):
    from .sheets import component_sheet
    mapping={pin:net['name'] for net in spec.get('nets',[]) for pin in net.get('pins',[])};result={}
    for component in spec.get('components',[]):
        cfg=component.get('terminal')
        if not isinstance(cfg,dict) or cfg.get('expose',True) is False or sheet is not None and component_sheet(component)!=sheet:continue
        net=mapping.get(component['ref']+'.1')
        if net is None:continue
        label=component.get('value',component['ref']);page=component_sheet(component)
        previous=result.setdefault(page,{}).get(label)
        if previous and previous.get('terminal_ref')!=component['ref']:raise ValueError('Terminal designators must be unique within each sheet.')
        result[page][label]=port(component,net)
    return result


def validate(spec):
    from . import sheets
    terms=[c for c in spec.get('components',[]) if c.get('terminal') is not None]
    if not terms:return
    numbers={};mapping={pin:net['name'] for net in spec.get('nets',[]) for pin in net.get('pins',[])}
    for component in terms:
        cfg=component['terminal'];ref=component.get('ref','')
        if not isinstance(cfg,dict) or not cfg:raise ValueError('Terminal properties must be a nonempty object.')
        name=component.get('value','')
        if not isinstance(name,str) or not name.strip() or len(name)>100 or not name.isprintable():raise ValueError('A terminal designator needs 1–100 printable characters.')
        if cfg.get('direction','passive') not in DIRECTIONS or cfg.get('side','left') not in SIDES:raise ValueError('Choose a supported terminal direction and pin orientation.')
        number=cfg.get('number','1')
        if not isinstance(number,str) or not number.strip() or len(number)>32 or not number.isprintable():raise ValueError('A terminal pin number needs 1–32 printable characters.')
        key=(sheets.component_sheet(component),number)
        if key in numbers:raise ValueError('Terminal pin numbers must be unique within each sheet.')
        numbers[key]=ref
        for field in ('exclude_from_pcb','expose'):
            if field in cfg and type(cfg[field]) is not bool:raise ValueError('Terminal PCB exclusion and exposure must be boolean values.')
        diameter=cfg.get('diameter_mm',1.5);order=cfg.get('order',0)
        if isinstance(diameter,bool) or not isinstance(diameter,(int,float)) or not math.isfinite(diameter) or not 0<diameter<=100:raise ValueError('A terminal pad diameter must be above zero and at most 100 mm.')
        if isinstance(order,bool) or not isinstance(order,(int,float)) or not math.isfinite(order) or abs(order)>1000000:raise ValueError('Terminal order must be a bounded finite number.')
        for field in ('group','section'):
            value=cfg.get(field,'')
            if not isinstance(value,str) or len(value)>80 or value and not value.isprintable():raise ValueError('Terminal groups and sections need bounded printable text.')
        if ref+'.1' not in mapping:raise ValueError('A terminal must have a canonical connection or its isolated placeholder net.')
        from .kicad import schematic,libs
        info=schematic.symbol_info(component.get('symbol',''),spec)
        if info and {pin['number'] for pin in info['pins']}!={'1'}:raise ValueError('A terminal symbol must have only logical pin 1.')
        footprint=libs.load_footprint(component.get('footprint',''),spec)
        if footprint and set(footprint.pad_names)!={'1'}:raise ValueError('A terminal footprint must have only logical pad 1.')
    defs=sheets.definitions(spec);ports=sheets.boundaries(spec);page_nets={key:set() for key in ['',*defs]}
    locations={c['ref']:sheets.component_sheet(c) for c in spec.get('components',[])}
    for net in spec.get('nets',[]):
        for pin in net.get('pins',[]):page_nets.setdefault(locations.get(pin.split('.',1)[0],''),set()).add(net['name'])
    for key,values in ports.items():
        for value in values.values():page_nets[key].add(value['net']);page_nets[defs[key].get('parent','')].add(value['net'])
    for page,nets in page_nets.items():
        values=ports.get(page,{});first={}
        for name,value in values.items():first.setdefault(value['net'],name)
        owners={}
        for net in nets:
            name=first.get(net,net)
            if name in owners and owners[name]!=net:raise ValueError(f'Terminal name {name} conflicts with a different net on its sheet.')
            owners[name]=net
        for name,value in values.items():
            if name in owners and owners[name]!=value['net']:raise ValueError(f'Terminal name {name} conflicts with a different net on its sheet.')
            owners[name]=value['net']


def pad_asset(spec,diameter):
    """Use a portable project footprint without overwriting an existing asset."""
    r=diameter/2+.25
    value={'name':f'Terminal pad {diameter:g} mm','mount':'smd','height_mm':.035,'courtyard':[-r,-r,r,r],'graphics':[],'pads':[{'name':'1','kind':'smd','shape':'circle','x':0,'y':0,'w':diameter,'h':diameter,'layer':'F.Cu','paste':False}]}
    assets=spec.setdefault('library',{}).setdefault('footprints',{});base='TerminalPad'+str(round(diameter*1000000));key=base;index=2
    while key in assets and assets[key]!=value:key=base+'_'+str(index);index+=1
    assets[key]=copy.deepcopy(value);return 'Project:'+key


def prepare(spec,arguments):
    """Return a validated authoring draft; the caller controls versioned persistence."""
    from . import sheets
    from urllib.parse import quote
    out=copy.deepcopy(spec);action=arguments.get('action');refs={c['ref'] for c in out.get('components',[])};ref=arguments.get('ref');patch=arguments.get('patch',{})
    if not isinstance(patch,dict):raise ValueError('Terminal edits must contain properties.')
    if action=='materialize':
        page=arguments.get('sheet','');label=arguments.get('label');definition=sheets.boundaries(out).get(page,{}).get(label)
        if not definition:raise ValueError('Choose an existing sheet port.')
        if definition.get('terminal_ref'):return {'spec':out,'ref':definition['terminal_ref']}
        arguments={**definition,**arguments,'name':label,'net':definition['net'],'exclude_from_pcb':True};action='add'
        raw=(out.get('editor') or {}).get('sheets',{}).get(page,{}).get('ports',{});raw.pop(label,None)
    if action=='add':
        page=arguments.get('sheet','');defs=sheets.definitions(out)
        if page and page not in defs:raise ValueError('Choose an existing sheet for the terminal.')
        index=1
        while 'TP'+str(index) in refs:index+=1
        ref='TP'+str(index);siblings=[c for c in out['components'] if c.get('terminal') and sheets.component_sheet(c)==page]
        reserved={str(value.get('number')) for value in defs.get(page,{}).get('ports',{}).values() if value.get('number') is not None}
        number=1
        while str(number) in reserved or any(str(c['terminal'].get('number'))==str(number) for c in siblings):number+=1
        name=arguments.get('name')
        if name is None:
            value=1;name='P'+str(value)
            while any(c.get('value')==name for c in siblings) or any(n['name']==name for n in out['nets']):value+=1;name='P'+str(value)
        diameter=arguments.get('diameter_mm',1.5)
        cfg={'direction':'passive','number':str(number),'side':'left','order':0,'group':'','section':'','expose':True,'exclude_from_pcb':False,'diameter_mm':diameter}
        for key in cfg:
            if key in arguments:cfg[key]=arguments[key]
        # Validate scalar properties before using dimensions to construct geometry.
        if not project_library.finite(diameter,100) or diameter<=0:raise ValueError('A terminal pad diameter must be above zero and at most 100 mm.')
        component={'ref':ref,'value':name,'symbol':'Connector:TestPoint','footprint':pad_asset(out,diameter),'sheet':page,'terminal':cfg,
                   'placement':{'x_mm':max(diameter/2+.5,float(out['board']['width_mm'])-diameter/2-1),'y_mm':diameter/2+1+number*2,'rotation':0,'locked':False,'side':'top'}}
        out['components'].append(component);patch={'net':arguments.get('net')}
        if 'position' in arguments:patch['position']=arguments['position']
    else:
        component=next((c for c in out.get('components',[]) if c['ref']==ref and c.get('terminal')),None)
        if component is None:raise ValueError('Choose an existing terminal.')
    old_name=component['value'];page=sheets.component_sheet(component);pin=ref+'.1';old_net=next((n['name'] for n in out['nets'] if pin in n['pins']),None);was_excluded=excluded(component)
    if action=='delete':
        out['components']=[c for c in out['components'] if c['ref']!=ref]
        patch={'net':None}
    elif action not in {'add','update'}:raise ValueError('Choose add, update, materialize or delete for a terminal.')
    if action!='delete':
        if 'name' in patch:component['value']=patch['name']
        for key in ('direction','number','side','order','group','section','expose','exclude_from_pcb','diameter_mm'):
            if key in patch:component['terminal'][key]=patch[key]
        if 'diameter_mm' in patch:
            diameter=patch['diameter_mm']
            if not project_library.finite(diameter,100) or diameter<=0:raise ValueError('A terminal pad diameter must be above zero and at most 100 mm.')
            component['footprint']=pad_asset(out,diameter)
        if 'position' in patch:
            point=patch['position']
            if not isinstance(point,list) or len(point)!=2 or any(not project_library.finite(value,1000000) for value in point):raise ValueError('A terminal needs finite schematic coordinates.')
            out.setdefault('editor',{}).setdefault('positions',{})[ref]=[round(value/10)*10 for value in point]
    new_net=old_net
    if 'net' in patch and (patch['net']!=old_net or action in {'add','delete'}):
        target=patch['net']
        if target is not None and not any(n['name']==target for n in out['nets']):raise ValueError('Choose an existing network or an isolated terminal.')
        for net in out['nets']:net['pins']=[value for value in net['pins'] if value!=pin]
        out['nets']=[net for net in out['nets'] if net['pins']]
        if action!='delete':
            if target is None:
                base='PORT_'+ref;target=base;index=2
                while any(net['name']==target for net in out['nets']):target=base+'_'+str(index);index+=1
                out['nets'].append({'name':target,'class':'signal','pins':[pin],'placeholder_ref':ref})
            else:
                net=next(net for net in out['nets'] if net['name']==target);net['pins'].append(pin)
                if len(net['pins'])>1:net.pop('placeholder_ref',None)
        new_net=target
        if old_net and old_net!=new_net and not was_excluded:out['fixed_copper']=[g for g in out.get('fixed_copper',[]) if g['net']!=old_net]
    names={net['name'] for net in out['nets']}
    if out.get('fixed_copper') is not None:out['fixed_copper']=[g for g in out['fixed_copper'] if g['net'] in names]
    if out.get('fixed_zones') is not None:out['fixed_zones']=[z for z in out['fixed_zones'] if not z['net'] or z['net'] in names]
    old_anchor='sheet:'+page+'.'+quote(old_name,safe="~()*!.'-");new_anchor='sheet:'+page+'.'+quote(component['value'],safe="~()*!.'-")
    guides=[]
    for guide in (out.get('editor') or {}).get('connection_guides',[]):
        references=[guide['from'],guide['to']]
        if (action=='delete' or old_net!=new_net) and any(value in (pin,old_anchor) for value in references):continue
        for key in ('from','to'):
            if guide[key]==old_anchor:guide[key]=new_anchor
        guides.append(guide)
    ids={g.get('id') for g in guides}
    for guide in guides:
        for key in ('from_join','to_join'):
            if guide.get(key) and guide[key]['wire'] not in ids:guide.pop(key,None)
    if out.get('editor') is not None:out['editor']['connection_guides']=guides
    for definition in (out.get('editor') or {}).get('sheets',{}).values():
        ports=definition.get('ports',{})
        for label,value in list(ports.items()):
            if value.get('terminal_ref')==ref:
                del ports[label]
                if action!='delete':ports[component['value']]={**value,'net':new_net}
    if action=='delete':
        for field in ('positions','rotations','mirrors'):
            values=(out.get('editor') or {}).get(field,{})
            for key in list(values):
                if key==ref or key.startswith(ref+'#'):values.pop(key,None)
        for instance in (out.get('editor') or {}).get('module_instances',{}).values():instance['refs']=[value for value in instance.get('refs',[]) if value!=ref]
    validate(out);sheets.validate(out);return {'spec':out,'ref':None if action=='delete' else ref}


def project_draft(project,arguments):
    """Share current native-copper capture and optimistic guards across UI and Agent."""
    from pathlib import Path
    from fastapi import HTTPException
    from . import workbench_native
    from .workbench import validate_draft
    from .module_capture import native_copper
    from .kicad import geometry,libs
    with project.lock:
        version=(project.state.get('workbench') or {}).get('version',0)
        if arguments.get('base_version',version)!=version:raise HTTPException(409,'The design changed before terminal editing.')
        spec=copy.deepcopy(project.state.get('spec') or {})
    pcb=workbench_native.final_pcb(project)
    if pcb is None and libs.locate('footprints') and libs.locate('symbols'):pcb=Path(workbench_native.generate(project)['pcb'])
    if pcb:spec['fixed_copper'],spec['fixed_zones']=native_copper(geometry.read(pcb))
    result=prepare(spec,arguments);validate_draft(result['spec'])
    with project.lock:
        if (project.state.get('workbench') or {}).get('version',0)!=version:raise HTTPException(409,'The design changed during terminal editing.')
    return {**result,'base_version':version}
