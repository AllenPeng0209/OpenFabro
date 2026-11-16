"""Portable circuit modules with independent nets and translated native PCB copper."""
from __future__ import annotations
import copy
import hashlib
import json
import math
import re
import uuid
from . import design,sheets,project_library


def fingerprint(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()


def _pair(value):
    return isinstance(value,list) and len(value)==2 and all(isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) and abs(v)<=10000 for v in value)


def validate_asset(key,asset):
    if not project_library.identifier(key) or not isinstance(asset,dict) or asset.get('schema')!=1:
        raise ValueError('A module needs a valid library ID and supported schema.')
    if not project_library.text(asset.get('name'),120) or not asset['name'].strip() or not project_library.text(asset.get('description',''),2000):raise ValueError('A module needs a bounded printable name and description.')
    template=asset.get('design')
    allowed={'name','board','components','nets','editor','library','fixed_copper','fixed_zones'}
    if not isinstance(template,dict) or set(template)-allowed:raise ValueError('A module contains unsupported template settings.')
    if not isinstance(template.get('library',{}),dict) or not isinstance(template.get('editor',{}),dict):raise ValueError('Module editor metadata and dependencies must be objects.')
    if (template.get('library') or {}).get('modules'):raise ValueError('A portable module cannot contain recursive or nested module assets.')
    components=template.get('components');nets=template.get('nets');b=template.get('board')
    if not isinstance(components,list) or not 1<=len(components)<=5000 or not isinstance(nets,list) or len(nets)>10000:raise ValueError('A module needs bounded components and nets.')
    if not isinstance(b,dict) or not all(project_library.finite(b.get(k)) and b[k]>0 for k in ('width_mm','height_mm')) or b.get('layers') not in (1,2,4,6,8,10,12):raise ValueError('A module needs finite board dimensions and a supported stackup.')
    refs=set()
    for component in components:
        if not isinstance(component,dict) or not re.fullmatch(r'[A-Z][A-Z_]*\d+',str(component.get('ref',''))) or component['ref'] in refs:raise ValueError('Module component references must be valid and unique.')
        refs.add(component['ref'])
        placement=component.get('placement') or {}
        if not isinstance(placement,dict) or any(not project_library.finite(placement.get(k,0),10000) for k in ('x_mm','y_mm','rotation')):raise ValueError('Module PCB placements must be finite.')
    names=set();pins=set()
    for net in nets:
        if not isinstance(net,dict) or not project_library.text(net.get('name'),256) or not net['name'].strip() or net['name'] in names or not isinstance(net.get('pins'),list):raise ValueError('Module nets must have unique names and pin lists.')
        names.add(net['name'])
        for pin in net['pins']:
            if not isinstance(pin,str) or '.' not in pin or pin.split('.',1)[0] not in refs or pin in pins:raise ValueError('A module pin refers to a missing component or multiple nets.')
            pins.add(pin)
    ports=asset.get('ports',{})
    if not isinstance(ports,dict) or len(ports)>1000:raise ValueError('Module ports must be a bounded object.')
    for label,port in ports.items():
        if not project_library.text(label,100) or not label or not isinstance(port,dict) or port.get('net') not in names:raise ValueError('Every module port needs a name and an existing net.')
    from . import terminals
    project_library.validate(template);terminals.validate(template);sheets.validate(template)
    from . import wire_nodes
    wire_nodes.validate(template)
    from . import buses
    buses.validate(template)
    from . import module_updates
    module_updates.validate_history(asset)
    from .kicad.schematic_wires import validate_guides
    validate_guides(template.get('editor',{}).get('connection_guides',[]))
    for field in ('positions','rotations','mirrors'):
        values=template.get('editor',{}).get(field,{})
        if not isinstance(values,dict) or any(not (_pair(v) if field=='positions' else v in ('','x','y') if field=='mirrors' else project_library.finite(v,10000) and v%90==0) for v in values.values()):raise ValueError('Module schematic poses must be finite coordinates or right-angle rotations.')
    copper=template.get('fixed_copper',[])
    if not isinstance(copper,list) or len(copper)>10000:raise ValueError('Module copper must be bounded net groups.')
    for group in copper:
        if not isinstance(group,dict) or group.get('net') not in names:raise ValueError('Module copper must belong to an existing net.')
        for kind,coordinates in (('tracks',('a','b')),('arcs',('a','m','b')),('vias',('p',))):
            items=group.get(kind,[])
            if not isinstance(items,list) or len(items)>100000:raise ValueError('Module copper elements must be bounded lists.')
            for item in items:
                if not isinstance(item,dict) or not all(_pair(item.get(k)) for k in coordinates):raise ValueError('Module copper needs finite vertices.')
                if 'locked' in item and type(item['locked']) is not bool:raise ValueError('Module copper protection must be a boolean.')
                if kind=='vias':
                    d,drill=item.get('d'),item.get('drill')
                    if not project_library.finite(d) or not project_library.finite(drill) or not 0<drill<d:raise ValueError('A module via needs a drill smaller than its diameter.')
                elif not project_library.finite(item.get('w')) or item['w']<=0:raise ValueError('Module traces need positive widths.')
    from .kicad.copper import validate as validate_copper
    validate_copper(template)


def publish(spec,*,name,ports=None,description='',native_geometry=None):
    source=design.normalise(spec)
    board={k:copy.deepcopy(source['board'][k]) for k in ('width_mm','height_mm','layers','thickness_mm') if k in source['board']}
    template={'name':source['name'],'board':board,'components':copy.deepcopy(source['components']),'nets':copy.deepcopy(source['nets']),
              'editor':{k:copy.deepcopy(source.get('editor',{}).get(k,{} if k!='connection_guides' else [])) for k in ('positions','rotations','mirrors','sheets','connection_guides','wire_nodes')},
              'library':{kind:copy.deepcopy(project_library.library(source).get(kind,{})) for kind in ('symbols','footprints','parts')},
              'fixed_copper':copy.deepcopy(source.get('fixed_copper',[])),'fixed_zones':copy.deepcopy(source.get('fixed_zones',[]))}
    template['editor']['sheets']=sheets.definitions(source)
    # Freeze generated symbol positions too, so instantiation does not re-layout them.
    from .schematic_view import scene
    for symbol in scene(source)['symbols']:template['editor']['positions'].setdefault(symbol['key'],[round(v,4) for v in symbol['position']])
    if native_geometry is not None:
        from .module_capture import native_copper
        template['fixed_copper'],template['fixed_zones']=native_copper(native_geometry)
        origin=native_geometry.get('bbox',[100,100])[:2];poses={p['ref']:p for p in native_geometry.get('footprints',[])}
        for c in template['components']:
            if c['ref'] in poses:
                p=poses[c['ref']];c['placement']={'x_mm':round(p['x']-origin[0],6),'y_mm':round(p['y']-origin[1],6),'rotation':p.get('rot',0),'side':'bottom' if p.get('side')=='B.Cu' else 'top',**({'locked':c['placement']['locked']} if 'locked' in c.get('placement',{}) else {})}
    from . import terminals
    declared=terminals.declarations(source,sheet='').get('',{});chosen=dict(ports or {})
    for label,value in declared.items():
        if label in chosen and chosen[label]!=value['net']:raise ValueError('A terminal port is bound to a different published net.')
        chosen.setdefault(label,value['net'])
    asset={'schema':1,'name':name,'description':description,'ports':{label:{**(declared.get(label,{}) if declared.get(label,{}).get('net')==net else {}),'net':net} for label,net in chosen.items()},'design':template}
    from . import module_updates
    asset=module_updates.release(asset);validate_asset('Module',asset);return asset


def instantiate(spec,module_id,instance,*,offset=None,position=None,parent='',connections=None,_identity=None):
    from . import module_updates
    identity=copy.deepcopy(_identity or {});out=copy.deepcopy(spec);asset=project_library.library(out).get('modules',{}).get(module_id)
    validate_asset(module_id,asset)
    offset=[0,0] if offset is None else offset
    if position is None:
        occupied_positions=[value.get('position') for value in sheets.definitions(out).values() if value.get('parent','')==parent]
        position=[850,140]
        while any(p and abs(p[0]-position[0])<440 and abs(p[1]-position[1])<300 for p in occupied_positions):position[0]+=450
    if not _pair(offset) or not _pair(position):raise ValueError('Module positions need finite coordinate pairs.')
    defs=sheets.definitions(out)
    if not project_library.identifier(instance) or instance in defs:raise ValueError('Choose a unique module instance ID starting with a letter.')
    if parent and parent not in defs:raise ValueError('The parent sheet does not exist.')
    source=copy.deepcopy(asset['design']);source.setdefault('library',{});source.setdefault('editor',{})
    if source['board']['layers']!=out['board'].get('layers',2):raise ValueError('Module and target board need the same layer stackup.')
    connections={} if connections is None else connections
    if not isinstance(connections,dict) or set(connections)-set(asset['ports']):raise ValueError('Choose existing module ports for external connections.')
    existing={net['name']:net for net in out['nets']};net_map={};claimed=set(existing)
    for label,net in connections.items():
        if net not in existing:raise ValueError('Connect module ports to existing target nets.')
        internal=asset['ports'][label]['net']
        if internal in net_map and net_map[internal]!=net:raise ValueError('Ports on the same internal net cannot connect to different target nets.')
        net_map[internal]=net
    for net in source['nets']:
        if net['name'] in net_map:continue
        if net['name'] in identity.get('nets',{}):net_map[net['name']]=identity['nets'][net['name']];continue
        base=instance+'_'+net['name'];candidate=base;index=2
        while candidate in claimed:candidate=base+'_'+str(index);index+=1
        net_map[net['name']]=candidate;claimed.add(candidate)
    def child_id(key):
        value=instance+'_'+key
        return value if len(value)<=64 else value[:54]+'_'+hashlib.sha256(value.encode()).hexdigest()[:9]
    sheet_map={'':instance,**{key:identity.get('sheets',{}).get(key,child_id(key)) for key in sheets.definitions(source)}}
    for key,value in list(sheet_map.items()):
        if not key:continue
        suffix=2
        while value in defs or value in identity.get('reserved_sheets',[]):value=child_id(key)+'_'+str(suffix);suffix+=1
        sheet_map[key]=value
    if any(value in defs for value in sheet_map.values()):raise ValueError('A child sheet already uses this module instance ID.')
    refs={};occupied={c['ref'] for c in out['components']}|set(identity.get('reserved_refs',[]));promised=set(identity.get('refs',{}).values())-occupied
    for component in source['components']:
        desired=identity.get('refs',{}).get(component['ref'])
        if desired and desired not in occupied:refs[component['ref']]=desired;occupied.add(desired);promised.discard(desired);continue
        prefix=re.sub(r'\d+$','',component['ref']);number=1
        while prefix+str(number) in occupied or prefix+str(number) in promised:number+=1
        ref=prefix+str(number);occupied.add(ref);refs[component['ref']]=ref
    node_ids={key:identity.get('nodes',{}).get(key,str(uuid.uuid4())) for key in source.get('editor',{}).get('wire_nodes',{})}
    def pin(value):
        if value.startswith('node:'):return 'node:'+node_ids[value[5:]]
        if value.startswith('sheet:'):
            # Sheet anchors use stable sheet IDs and encoded terminal labels.
            sid,label=value[6:].split('.',1);return 'sheet:'+sheet_map[sid]+'.'+label
        reference=re.split(r'[.#]',value,maxsplit=1)[0]
        return refs[reference]+value[len(reference):]
    out.setdefault('library',{})
    for kind in ('symbols','footprints','parts'):
        target=out['library'].setdefault(kind,{})
        for key,value in source['library'].get(kind,{}).items():
            if key in target and target[key]!=value:raise ValueError(f'Project library asset {key} differs from the module dependency. Rename it before importing.')
            target[key]=copy.deepcopy(value)
    for component in source['components']:
        c=copy.deepcopy(component);c['ref']=refs[c['ref']];c['sheet']=sheet_map[sheets.component_sheet(c)];c['module_instance']=instance
        if c.get('placement'):
            for axis,key in enumerate(('x_mm','y_mm')):c['placement'][key]=round(c['placement'].get(key,0)+offset[axis],6)
        out['components'].append(c)
    for net in source['nets']:
        name=net_map[net['name']];pins=[pin(value) for value in net['pins']]
        if name in existing:existing[name]['pins']=list(dict.fromkeys(existing[name]['pins']+pins))
        else:
            row={**copy.deepcopy(net),'name':name,'pins':pins}
            if row.get('placeholder_ref'):row['placeholder_ref']=refs[row['placeholder_ref']]
            out['nets'].append(row);existing[name]=row
    editor=out.setdefault('editor',{});pages=editor.setdefault('sheets',{})
    for key,node in source.get('editor',{}).get('wire_nodes',{}).items():editor.setdefault('wire_nodes',{})[node_ids[key]]={**copy.deepcopy(node),'net':net_map[node['net']],'sheet':sheet_map[node.get('sheet','')]}
    def mapped_port(value):
        out={**copy.deepcopy(value),'net':net_map[value['net']]}
        if out.get('terminal_ref'):out['terminal_ref']=refs[out['terminal_ref']]
        return out
    pages[instance]={'title':asset['name']+' · '+instance,'parent':parent,'position':position,'size':[300,180],'ports':{label:mapped_port(value) for label,value in asset['ports'].items()}}
    for key,value in sheets.definitions(source).items():
        d=copy.deepcopy(value);d['parent']=sheet_map[d.get('parent','')];d['ports']={label:mapped_port(port) for label,port in d.get('ports',{}).items()};pages[sheet_map[key]]=d
    for field in ('positions','rotations','mirrors'):
        editor.setdefault(field,{}).update({pin(key):copy.deepcopy(value) for key,value in source['editor'].get(field,{}).items()})
    wire_ids={g.get('id',f'wire-{i}'):identity.get('wires',{}).get(g.get('id',f'wire-{i}'),str(uuid.uuid4())) for i,g in enumerate(source['editor'].get('connection_guides',[]))}
    for i,guide in enumerate(source['editor'].get('connection_guides',[])):
        g=copy.deepcopy(guide);g.update(id=wire_ids[g.get('id',f'wire-{i}')],**{key:pin(g[key]) for key in ('from','to')})
        for key in ('from_join','to_join'):
            if g.get(key):g[key]['wire']=wire_ids[g[key]['wire']]
        editor.setdefault('connection_guides',[]).append(g)
    copper_ids={};zone_ids={}
    for group in source.get('fixed_copper',[]):
        g=copy.deepcopy(group);g['net']=net_map[g['net']]
        for kind,coordinates in (('tracks',('a','b')),('arcs',('a','m','b')),('vias',('p',))):
            for i,item in enumerate(g.get(kind,[])):
                key=module_updates.item_key(kind,group['net'],i);item['id']=identity.get('copper',{}).get(key,str(uuid.uuid4()));copper_ids[key]=item['id'];item['net']=g['net']
                for field in coordinates:item[field]=[round(item[field][axis]+offset[axis],6) for axis in range(2)]
        out.setdefault('fixed_copper',[]).append(g)
    for i,zone in enumerate(source.get('fixed_zones',[])):
        key=module_updates.item_key('zones',zone['net'],i);z=copy.deepcopy(zone);z['net']=net_map.get(z['net'],z['net']);z['id']=identity.get('zones',{}).get(key,str(uuid.uuid4()));zone_ids[key]=z['id'];z['origin']=[z['origin'][i]-offset[i] for i in range(2)];out.setdefault('fixed_zones',[]).append(z)
    maps={'refs':refs,'nets':net_map,'sheets':sheet_map,'nodes':node_ids,'wires':wire_ids,'copper':copper_ids,'zones':zone_ids,'deps':identity.get('deps',{kind:{key:key for key in source['library'].get(kind,{})} for kind in ('symbols','footprints','parts')})}
    editor.setdefault('module_instances',{})[instance]={'module':module_id,'version':module_updates.version(asset),'fingerprint':module_updates.digest(asset),'refs':list(refs.values()),'nets':net_map,'board_offset':offset,'source_maps':maps,'baseline':{'version':module_updates.version(asset),'fingerprint':module_updates.digest(asset),'maps':copy.deepcopy(maps),'board_offset':offset,'position':position,'parent':parent}}
    from . import terminals
    terminals.validate(out);sheets.validate(out);return out


def convert_selection(spec,refs,module_id,instance,*,name,ports=None,native_geometry,bounds=None,position=None):
    """Wrap an existing selection in-place and save its clipped, portable layout."""
    from .module_capture import capture,native_copper
    from .schematic_view import scene
    source=design.normalise(spec);all_parts={c['ref']:c for c in source['components']}
    if not isinstance(refs,list) or not refs or any(not isinstance(ref,str) or ref not in all_parts for ref in refs):raise ValueError('Choose existing components to convert.')
    refs=list(dict.fromkeys(refs));selected=set(refs);parents={sheets.component_sheet(all_parts[ref]) for ref in refs}
    if len(parents)!=1:raise ValueError('Convert components from one schematic sheet at a time.')
    parent=next(iter(parents));defs=sheets.definitions(source)
    if not project_library.identifier(module_id) or module_id in project_library.library(source).get('modules',{}):raise ValueError('Choose a new module library ID starting with a letter.')
    if not project_library.identifier(instance) or instance in defs:raise ValueError('Choose a new module instance ID starting with a letter.')
    source_nets=[net for net in source['nets'] if any(pin.split('.',1)[0] in selected for pin in net['pins'])]
    physical_boundary={net['name'] for net in source_nets if any(pin.split('.',1)[0] not in selected for pin in net['pins'])}
    declared_nets={port['net'] for definition in defs.values() for port in definition.get('ports',{}).values()}
    boundary=physical_boundary|({net['name'] for net in source_nets}&declared_nets)
    ports={} if ports is None else copy.deepcopy(ports)
    if not isinstance(ports,dict):raise ValueError('Module terminals must map labels to selected nets.')
    from . import terminals
    declared={label:port for values in terminals.declarations(source).values() for label,port in values.items() if port.get('terminal_ref') in selected}
    for label,value in declared.items():
        if label in ports and ports[label]!=value['net']:raise ValueError('A selected terminal name is bound to a different module port.')
        ports[label]=value['net']
    for net in sorted(boundary):
        if net not in ports.values():
            label=net;number=2
            while label in ports:label=net+'_'+str(number);number+=1
            ports[label]=net
    if any(net not in {n['name'] for n in source_nets} for net in ports.values()):raise ValueError('Choose terminal nets connected to selected components.')
    selected_nets={net['name'] for net in source_nets}
    physical_refs={ref for ref in selected if not design.pcb_excluded(all_parts[ref])}
    copper,zones,report=capture(native_geometry,physical_refs,selected_nets,bounds=bounds,internal_nets=selected_nets-physical_boundary)
    anchor=report['origin'];editor=source.get('editor') or {};current_scene=scene(source)
    from . import wire_nodes
    captured=wire_nodes.selected_geometry(source,selected);internal_nodes=set(captured['wire_nodes'])
    def is_selected(anchor):return anchor[5:] in internal_nodes if anchor.startswith('node:') else anchor.split('.',1)[0].split('#',1)[0] in selected
    internal=captured['connection_guides']
    identifiers={guide.get('id') for guide in internal}
    for guide in internal:
        for field in ('from_join','to_join'):
            if guide.get(field) and guide[field]['wire'] not in identifiers:del guide[field]
    library={kind:{} for kind in ('symbols','footprints','parts')}
    needed={'symbols':set(),'footprints':set()}
    for ref in refs:
        for field,kind in (('symbol','symbols'),('footprint','footprints')):
            value=all_parts[ref].get(field,'')
            if value.startswith('Project:'):needed[kind].add(value[8:])
    original_library=project_library.library(source)
    for key in needed['symbols']:
        value=original_library.get('symbols',{})[key];fp=value.get('footprint','')
        if fp.startswith('Project:'):needed['footprints'].add(fp[8:])
    for kind,keys in needed.items():library[kind]={key:copy.deepcopy(original_library[kind][key]) for key in keys}
    template={'name':module_id,'board':{'width_mm':report['bounds'][2]-anchor[0],'height_mm':report['bounds'][3]-anchor[1],'layers':source['board']['layers'],'ground_pour':None},'components':[],
              'nets':[{**copy.deepcopy(net),'pins':[pin for pin in net['pins'] if pin.split('.',1)[0] in selected]} for net in source_nets],
              'editor':{'sheets':{},'positions':{},'rotations':{},'connection_guides':internal,'wire_nodes':{key:{**copy.deepcopy(value),'sheet':''} for key,value in captured['wire_nodes'].items()}},'library':library,'fixed_copper':copper,'fixed_zones':zones}
    for c in source['components']:
        if c['ref'] not in selected:continue
        part=copy.deepcopy(c);part['sheet']='';part.pop('module_instance',None)
        part['placement']={**part.get('placement',{}),'x_mm':round(part.get('placement',{}).get('x_mm',0)-anchor[0],6),'y_mm':round(part.get('placement',{}).get('y_mm',0)-anchor[1],6)}
        template['components'].append(part)
    for symbol in current_scene['symbols']:
        if symbol['ref'] in selected:template['editor']['positions'][symbol['key']]=[round(v,4) for v in symbol['position']]
    for field in ('rotations','mirrors'):
        template['editor'][field]={key:copy.deepcopy(value) for key,value in editor.get(field,{}).items() if key.split('#',1)[0] in selected}
    asset={'schema':1,'name':name,'description':'','ports':{label:{**(declared.get(label,{}) if declared.get(label,{}).get('net')==net else {}),'net':net} for label,net in ports.items()},'design':template}
    validate_asset(module_id,asset)
    out=copy.deepcopy(spec);out.setdefault('library',{}).setdefault('modules',{})[module_id]=asset
    out['fixed_copper'],out['fixed_zones']=native_copper(native_geometry)
    out_editor=out.setdefault('editor',{});out_editor.setdefault('sheets',{})
    if parent and parent not in out_editor['sheets']:out_editor['sheets'][parent]=copy.deepcopy(defs[parent])
    if position is None:
        extent=next((page.get('extent') for page in current_scene['sheets'] if page['name']==parent),None)
        position=[max(850,math.ceil((extent[2]+100)/10)*10) if extent else 850,140]
    if not _pair(position):raise ValueError('The module boundary needs a finite position.')
    out_editor['sheets'][instance]={'title':name,'parent':parent,'position':position,'size':[300,max(180,20*(len(ports)+1))],'ports':copy.deepcopy(asset['ports'])}
    for component in out['components']:
        if component['ref'] in selected:component['sheet']=instance;component['module_instance']=instance
    out_editor.setdefault('positions',{}).update(template['editor']['positions'])
    for key in internal_nodes:out_editor['wire_nodes'][key]['sheet']=instance
    from urllib.parse import quote
    pin_net=design.pin_net_map(source)
    report['omitted_guide_ids']=[];retained=[]
    def net_of(anchor):
        if anchor.startswith('node:'):return editor['wire_nodes'][anchor[5:]]['net']
        if anchor.startswith('sheet:'):
            from urllib.parse import unquote
            sheet,label=anchor[6:].split('.',1);return defs.get(sheet,{}).get('ports',{}).get(unquote(label),{}).get('net',unquote(label))
        return pin_net.get(re.sub(r'#\d+(?=\.)','',anchor))
    for index,guide in enumerate(out_editor.get('connection_guides',[])):
        inside=[is_selected(guide[key]) for key in ('from','to')]
        if inside[0]==inside[1]:retained.append(guide);continue
        if not net_of(guide['from']) or net_of(guide['from'])!=net_of(guide['to']):
            report['omitted_guide_ids'].append(guide.get('id',str(index)));continue
        for key,selected_end in zip(('from','to'),inside):
            if selected_end:
                net=net_of(guide[key]);label=next(label for label,value in ports.items() if value==net)
                guide[key]='sheet:'+instance+'.'+quote(label,safe="~()*!.'-");guide.pop(key+'_join',None)
        guide.pop('waypoints',None)
        guide.pop('fixed_points',None)
        retained.append(guide)
    out_editor['connection_guides']=retained
    def page_of(guide):
        a=guide['from']
        if a.startswith('node:'):return out_editor['wire_nodes'][a[5:]].get('sheet','')
        if a.startswith('sheet:'):return out_editor['sheets'].get(a[6:].split('.',1)[0],{}).get('parent','')
        ref=re.split(r'[.#]',a,maxsplit=1)[0];return instance if ref in selected else sheets.component_sheet(all_parts.get(ref,{}))
    guide_pages={g.get('id'):page_of(g) for g in out_editor.get('connection_guides',[]) if g.get('id')}
    for guide in out_editor.get('connection_guides',[]):
        for key in ('from_join','to_join'):
            if guide.get(key) and guide_pages.get(guide[key]['wire'])!=page_of(guide):guide.pop(key,None)
    instances=out_editor.setdefault('module_instances',{})
    for value in instances.values():value['refs']=[ref for ref in value.get('refs',[]) if ref not in selected]
    instances[instance]={'module':module_id,'fingerprint':fingerprint(asset),'refs':[c['ref'] for c in template['components']],'nets':{n['name']:n['name'] for n in template['nets']},'board_offset':anchor,'converted':True,'capture':copy.deepcopy(report)}
    terminals.validate(out);sheets.validate(out);wire_nodes.validate(out)
    return {'spec':out,'capture':report,'module':module_id,'instance':instance}
