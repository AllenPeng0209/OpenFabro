"""Reviewed physical-pad instance overrides, independent of shared library assets."""
from __future__ import annotations
import copy,hashlib,json,math,re,tempfile,threading,shutil
from pathlib import Path
from . import sexpr,project_library,design_identity

FIELDS={'w','h','shape','kind','position','rotation','drill','drill_shape','drill_size','drill_offset','rratio','connected_layers','mask_margin_mm','paste_margin_mm','paste_ratio_pct','clearance_mm','zone_connect','thermal_gap_mm','thermal_spoke_mm','npth_copper','custom_shape','reset'}
GEOMETRY={'at','size','drill','layers','roundrect_rratio','rect_delta','options','primitives'}
RULES={'mask_margin_mm':'solder_mask_margin','paste_margin_mm':'solder_paste_margin','paste_ratio_pct':'solder_paste_margin_ratio','clearance_mm':'clearance','zone_connect':'zone_connect','thermal_gap_mm':'thermal_gap','thermal_spoke_mm':'thermal_bridge_width'}


def annuli(node,available):
    """Give skipped PTH layers only the drilled profile, not the default annulus.

    KiCad flashes PTH copper on drill-span layers even outside the pad layer mask.
    A custom stack makes that implicit copper exactly the drill opening. Its
    intentional zero-annulus warnings remain visible in native review.
    """
    node[:]=[q for q in node if sexpr.tag(q)!='padstack']
    if str(node[2])!='thru_hole':return
    selected={str(v) for v in sexpr.find(node,'layers')[1:] if str(v).endswith('.Cu')}
    if '*.Cu' in selected:return
    skipped=[layer for layer in available if layer not in selected]
    if not skipped:return
    drill=sexpr.find(node,'drill');oval=str(drill[1])=='oval';values=[sexpr.num(v) for v in drill[2:] if not isinstance(v,list)] if oval else [sexpr.num(drill[1])]*2
    node.append(sexpr.S(sexpr.Sym('padstack'),sexpr.S(sexpr.Sym('mode'),sexpr.Sym('custom')),*[sexpr.S(sexpr.Sym('layer'),layer,sexpr.S(sexpr.Sym('shape'),sexpr.Sym('oval' if oval else 'circle')),sexpr.S(sexpr.Sym('size'),*values[:2]),sexpr.S(sexpr.Sym('offset'),0,0)) for layer in skipped]))


def parsed(source):
    if not isinstance(source,str) or len(source)>1000000:raise ValueError('Pad snapshot must be bounded native pad text.')
    wrapper=sexpr.parse('(snapshot '+source+')')
    if len(wrapper)!=2 or sexpr.tag(wrapper[1])!='pad':raise ValueError('A pad snapshot must contain exactly one pad.')
    node=wrapper[1]
    if len(node)<4 or str(node[2]) not in {'smd','connect','thru_hole','np_thru_hole'}:raise ValueError('Unsupported instance pad type.')
    for field in ('at','size','layers'):
        if sexpr.find(node,field) is None:raise ValueError('Pad snapshot is missing '+field)
    return node


def entries(items):
    from .kicad import board
    seen={}
    for item in items:
        if sexpr.tag(item)!='pad':continue
        digest=hashlib.sha256(board._source_key(item).encode()).hexdigest();ordinal=seen.get(digest,0);seen[digest]=ordinal+1
        yield digest+':'+str(ordinal),item


def resolve_children(items,overrides,footprint):
    if not overrides:return items
    known={key:item for key,item in entries(items)};unknown=set(overrides)-set(known)
    if unknown:raise ValueError('A pad override no longer matches this footprint revision. Review or reset the affected instance overrides.')
    replaced={}
    for key,entry in overrides.items():
        if entry.get('footprint')!=footprint:raise ValueError('Instance pad override belongs to another footprint.')
        original=known[key];node=parsed(entry.get('source'));identifier=sexpr.find(original,'uuid')
        if str(node[1])!=str(original[1]):raise ValueError('Instance geometry cannot change the electrical pad number.')
        node[:]=[x for x in node if sexpr.tag(x) not in {'net','uuid','tstamp'}]
        if identifier:node.append(copy.deepcopy(identifier))
        replaced[id(original)]=node
    return [replaced.get(id(item),item) for item in items]


def validate(spec):
    from .kicad import board
    available=set(board.copper_layers(spec.get('board',{}).get('layers',2)))
    for component in spec.get('components',[]):
        overrides=component.get('pad_overrides',{})
        if not isinstance(overrides,dict) or len(overrides)>2048:raise ValueError('Pad overrides need a bounded keyed instance map.')
        for key,entry in overrides.items():
            if not isinstance(key,str) or not re.fullmatch('[a-f0-9]{64}:[0-9]{1,4}',key) or not isinstance(entry,dict):raise ValueError('Invalid source pad identity for an instance override.')
            if entry.get('footprint')!=component.get('footprint'):raise ValueError('Pad override footprint changed; review or reset the instance override.')
            node=parsed(entry.get('source'));layers=[str(v) for v in sexpr.find(node,'layers')[1:] if str(v).endswith('.Cu')]
            if any(v!='*.Cu' and v not in available for v in layers):raise ValueError('Instance pad refers to an inactive physical copper layer. Review the stackup mapping.')
            if str(node[2]) in {'smd','connect'} and (len(layers)!=1 or layers[0] not in {'F.Cu','B.Cu'}):raise ValueError('Surface pads need one outer copper layer.')
            if str(node[2])=='thru_hole' and not layers:raise ValueError('A plated pad needs a connected copper layer.')
            value=project_library._read_footprint([sexpr.Sym('footprint'),'Instance',*([sexpr.S(sexpr.Sym('attr'),sexpr.Sym('through_hole'))] if str(node[2]) in {'thru_hole','np_thru_hole'} else []),node])
            project_library.validate_asset('footprints','Instance',value)


def base_records(spec,ref):
    from .kicad import libs,board
    component=next((c for c in spec['components'] if c['ref']==ref),None)
    if component is None:raise ValueError('Choose an existing component pad.')
    fp=libs.load_footprint(component.get('footprint',''),spec)
    if fp is None:raise ValueError('The current footprint is unavailable.')
    children=board._stable_children(copy.deepcopy(fp.node)[2:],f'footprint:{ref}:{fp.lib_id}')
    return component,[(key,item) for key,item in entries(children)]


def selected(spec,pcb,ref,pad_id):
    from .kicad import board
    tree=sexpr.parse(Path(pcb).read_text());component,records=base_records(spec,ref)
    record=next(((key,node) for key,node in records if (sexpr.find(node,'uuid') or [None,None])[1]==pad_id),None)
    if record is None:raise ValueError('The selected native pad no longer matches its source footprint.')
    fp=next((f for f in sexpr.find_all(tree,'footprint') if any(p[1:3]==['Reference',ref] for p in sexpr.find_all(f,'property'))),None)
    if fp is None:raise ValueError('The selected native footprint is unavailable.')
    node=next((p for p in sexpr.find_all(fp,'pad') if (sexpr.find(p,'uuid') or [None,None])[1]==pad_id),None)
    if node is None:raise ValueError('The selected native pad is unavailable.')
    at=sexpr.find(fp,'at');rotation=sexpr.num(at[3]) if len(at)>3 else 0;bottom=str(sexpr.find(fp,'layer')[1])=='B.Cu';top=copy.deepcopy(node);board._rotate_at(top,-rotation)
    if bottom:board._flip_child(top)
    wrapper=[sexpr.Sym('footprint'),'Instance',top];model=project_library._read_footprint(wrapper)['pads'][0]
    return component,record[0],top,model,{'x':sexpr.num(at[1]),'y':sexpr.num(at[2]),'rotation':rotation,'bottom':bottom,'pad_id':pad_id}


def draft(spec,args,pcb,actual):
    from .kicad import board
    patch=args.get('patch',{})
    if not isinstance(patch,dict) or not patch or set(patch)-FIELDS:raise ValueError('Choose supported physical pad properties; net/number changes require connectivity editing.')
    component,key,top,model,frame=selected(spec,pcb,args.get('ref'),args.get('pad_id'));out=copy.deepcopy(spec);target=next(c for c in out['components'] if c['ref']==component['ref'])
    if patch.get('reset') is True:
        target.get('pad_overrides',{}).pop(key,None)
        if not target.get('pad_overrides'):target.pop('pad_overrides',None)
        return out,{'ref':component['ref'],'pad_id':frame['pad_id'],'override_key':key,'reset':True}
    for field in ('w','h','shape','kind','drill','drill_shape','drill_size','drill_offset','rratio','npth_copper','custom_shape'):
        if field in patch:model[field]=copy.deepcopy(patch[field])
    if 'kind' in patch:
        if model['kind'] in {'smd','connect'}:
            model['drill']=0
            for field in ('drill_shape','drill_size','drill_offset','npth_copper'):model.pop(field,None)
        elif not model.get('drill'):model['drill']=min(model['w'],model['h'])/2
    if 'drill_size' in patch:model['drill']=min(model['drill_size'])
    if 'drill' in patch and 'drill_size' not in patch and model.get('drill_shape')!='oval':model['drill_size']=[model['drill']]*2
    if 'position' in patch:
        value=patch['position']
        if not project_library.point(value):raise ValueError('Pad position needs two finite board coordinates.')
        ox,oy=actual.get('bbox',[100,100])[:2];local=project_library._rotate_pad([ox+value[0]-frame['x'],oy+value[1]-frame['y']],-frame['rotation']);model['x'],model['y']=local[0],-local[1] if frame['bottom'] else local[1]
    if 'rotation' in patch:
        if not project_library.finite(patch['rotation'],100000):raise ValueError('Pad rotation must be finite.')
        model['angle']=(patch['rotation']-frame['rotation'])*(-1 if frame['bottom'] else 1)
    if model['shape']=='circle':
        if 'w' in patch and 'h' not in patch:model['h']=model['w']
        if 'h' in patch and 'w' not in patch:model['w']=model['h']
    project_library.validate_asset('footprints','Instance',{'name':'Instance','pads':[model],'graphics':[]})
    generated=sexpr.find(project_library.footprint_node({'library':{'footprints':{'Instance':{'name':'Instance','pads':[model],'graphics':[]}}}},'Project:Instance'),'pad')
    candidate=copy.deepcopy(top);candidate[2:4]=generated[2:4];candidate[:]=[x for x in candidate if sexpr.tag(x) not in GEOMETRY|{'uuid','tstamp','net'}];candidate.extend(copy.deepcopy(x) for x in generated[4:] if sexpr.tag(x) in GEOMETRY)
    if not {'kind','npth_copper'} & set(patch):
        candidate[:]=[x for x in candidate if sexpr.tag(x)!='layers'];candidate.append(copy.deepcopy(sexpr.find(top,'layers')))
    if 'connected_layers' in patch:
        layers=patch['connected_layers'];available=set(board.copper_layers(spec['board'].get('layers',2)))
        if not isinstance(layers,list) or len(layers)!=len(set(layers)) or any(layer not in available for layer in layers):raise ValueError('Choose existing physical copper layers.')
        if model['kind'] in {'smd','connect'} and (len(layers)!=1 or layers[0] not in {'F.Cu','B.Cu'}):raise ValueError('Surface pads need one outer copper layer.')
        if model['kind']=='thru_hole' and not layers:raise ValueError('A plated pad needs a connected copper layer.')
        native=sexpr.find(candidate,'layers');technical=[v for v in native[1:] if not str(v).endswith('.Cu')];top_layers=[board._flip_layer(v) if frame['bottom'] else v for v in layers]
        if model['kind'] in {'smd','connect'}:technical=[str(top_layers[0]).replace('Cu',str(v).split('.')[-1]) if str(v).startswith(('F.','B.')) else v for v in technical]
        native[1:]=top_layers+technical
    for field,tag in RULES.items():
        if field not in patch:continue
        value=patch[field];candidate[:]=[x for x in candidate if sexpr.tag(x)!=tag]
        if value is None:continue
        if not project_library.finite(value,100) or field in {'clearance_mm','thermal_gap_mm','thermal_spoke_mm'} and value<0 or field=='paste_ratio_pct' and not -100<=value<=100 or field=='zone_connect' and (type(value) is not int or not 0<=value<=3):raise ValueError('Invalid pad mask, paste, clearance or thermal property.')
        candidate.append(sexpr.S(sexpr.Sym(tag),value/100 if field=='paste_ratio_pct' else value))
    existing=component.get('pad_overrides',{}).get(key,{})
    if sexpr.find(top,'padstack') and existing.get('annuli_policy')!='hole-profile-v1' and set(patch)&(FIELDS-set(RULES)-{'reset'}):raise ValueError('This native pad has a richer per-layer stack. Preserve it or reset its instance explicitly before editing geometry.')
    if 'connected_layers' in patch or 'kind' in patch or existing.get('annuli_policy')=='hole-profile-v1':annuli(candidate,board.copper_layers(spec['board'].get('layers',2)))
    target.setdefault('pad_overrides',{})[key]={'footprint':component['footprint'],'source':sexpr.dumps(candidate),**({'annuli_policy':'hole-profile-v1'} if sexpr.find(candidate,'padstack') and (existing.get('annuli_policy')=='hole-profile-v1' or 'connected_layers' in patch) else {})};validate(out)
    return out,{'ref':component['ref'],'pad_id':frame['pad_id'],'override_key':key,'pad_name':str(top[1]),'fields':list(patch),'scope':'Only this physical pad on this component instance; shared library and named connections are retained.'}


def inspect(project,ref,pad_id):
    from fastapi import HTTPException
    from . import design_identity,workbench_native
    from .kicad import geometry
    with project.lock:
        source=copy.deepcopy(project.state['spec']);version=project.state.get('workbench',{}).get('version',0);native=project.state.get('workbench_native') or {};pcb=workbench_native.final_pcb(project)
        if pcb is None and design_identity.matches(native,source) and native.get('pcb'):pcb=Path(native['pcb'])
        if pcb is None:raise HTTPException(409,'Wait for the current native layout before editing a pad.')
    digest=hashlib.sha256(pcb.read_bytes()).hexdigest();actual=geometry.read(pcb);component,key,top,model,frame=selected(source,pcb,ref,pad_id);pad=next(p for p in actual['pads'] if p['id']==pad_id and p['ref']==ref);ox,oy=actual.get('bbox',[100,100])[:2];properties={**model,'position':[pad['x']-ox,pad['y']-oy],'rotation':pad['rot'],'connected_layers':[layer for layer in actual['layers'] if (layer in pad['layers'] or '*.Cu' in pad['layers']) and (pad['kind']!='np_thru_hole' or pad.get('npth_copper'))]}
    for field,tag in RULES.items():
        node=sexpr.find(top,tag);properties[field]=sexpr.num(node[1])*(100 if field=='paste_ratio_pct' else 1) if node else None
    with project.lock:
        if project.state.get('workbench',{}).get('version',0)!=version or hashlib.sha256(pcb.read_bytes()).hexdigest()!=digest:raise HTTPException(409,'The selected pad changed while it was read.')
    return {'ref':ref,'pad_id':pad_id,'base_version':version,'properties':properties,'override_key':key,'overridden':key in component.get('pad_overrides',{}),'copper_layers':actual['layers'],'net':pad.get('net',''),'native_pad':pad}


def project_draft(project,args):
    from fastapi import HTTPException
    from . import workbench_native,design,route_tuning,stackup
    from .workbench import validate_draft
    from .module_capture import native_copper
    from .kicad import board,geometry,schematic,cli
    with workbench_native._locks.setdefault(project.id,threading.RLock()):
        with project.lock:
            version=project.state.get('workbench',{}).get('version',0)
            if type(args.get('base_version',version)) is not int or args.get('base_version',version)!=version:raise HTTPException(409,'The saved pad changed before review.')
            if getattr(project,'engine_busy',False) or project.worker and project.worker.is_alive() and project.worker is not threading.current_thread():raise HTTPException(409,'Wait for the active design run before editing pads.')
            original=copy.deepcopy(project.state.get('spec') or {})
        pcb=workbench_native.final_pcb(project)
        if pcb is None:pcb=Path(workbench_native.generate(project)['pcb'])
        actual=geometry.read(pcb);source={'source_identity':design_identity.fields(original),'source_pcb_sha256':hashlib.sha256(pcb.read_bytes()).hexdigest(),'source_render_inputs_sha256':workbench_native._plot_inputs(pcb)[1]}
        adopted=copy.deepcopy(original);captured_copper,captured_zones=native_copper(actual)
        # Compare physical source records in a private build. Keep the exact
        # authored representation when no native hand edit needs adoption.
        with tempfile.TemporaryDirectory(prefix='instance-pad-source-') as declared_dir:
            declared_pcb=Path(board.build(design.normalise(original),Path(declared_dir))['pcb'])
            if original.get('fixed_zones') or original['board'].get('stackup') and stackup.plane_map(original['board']):cli.drc(declared_pcb,refill=True,save=True)
            declared=geometry.read(declared_pcb)
            declared_copper,declared_zones=native_copper(declared)
        if original['board'].get('stackup'):
            captured_zones=stackup.manual_zones(original,captured_zones);declared_zones=stackup.manual_zones(original,declared_zones)
        def copper_signature(groups):
            return {group['net']:{kind:sorted(group.get(kind,[]),key=lambda item:item['id']) for kind in ('tracks','arcs','vias')} for group in groups}
        if copper_signature(captured_copper)!=copper_signature(declared_copper):adopted['fixed_copper']=captured_copper
        if sorted(captured_zones,key=lambda item:json.dumps(item,sort_keys=True))!=sorted(declared_zones,key=lambda item:json.dumps(item,sort_keys=True)):adopted['fixed_zones']=captured_zones
        ox,oy=actual.get('bbox',[100,100])[:2]
        for fp in actual['footprints']:
            c=next((c for c in adopted['components'] if c['ref']==fp['ref']),None)
            if c:
                placement=copy.deepcopy(c.get('placement',{}))
                for axis,value in (('x_mm',round(fp['x']-ox,6)),('y_mm',round(fp['y']-oy,6))):
                    if axis not in placement or not math.isclose(placement[axis],value,rel_tol=0,abs_tol=.000051):placement[axis]=value
                rotation=fp.get('rot',0)
                if abs((placement.get('rotation',0)-rotation+180)%360-180)>1e-6:placement['rotation']=rotation
                side='bottom' if fp.get('side')=='B.Cu' else 'top'
                if placement.get('side','top')!=side:placement['side']=side
                c['placement']=placement
        result,report=draft(adopted,args,pcb,actual);validate_draft(result)
        with tempfile.TemporaryDirectory(prefix='instance-pad-review-') as tmp:
            folder=Path(tmp);before=folder/'baseline';shutil.copytree(pcb.parent,before);baseline=cli.drc(before/pcb.name,refill=False,save=False)
            sch=schematic.build(result,folder);parity=schematic.netlist_parity(result,cli.schematic_nets(Path(sch['sch'])))
            if not parity['ok']:raise ValueError('The pad edit changed native schematic pin groups.')
            emitted=board.build(result,folder);candidate=Path(emitted['pcb']);data=geometry.read(candidate);after=cli.drc(candidate,refill=False,save=False);plot=cli.export_svg(candidate,folder/'pad-review.svg','F.Cu,B.Cu')
            report.update(native_probe={'ok':plot.is_file(),'method':'Real KiCad private SVG plot and baseline/candidate DRC','before_drc':baseline,'after_drc':after},needs_review=bool(after['errors'] or after['warnings'] or after['unconnected']))
        with project.lock:
            if project.state.get('workbench',{}).get('version',0)!=version:raise HTTPException(409,'The pad changed during review.')
        route_tuning.assert_source(project,source)
        return {'spec':result,'base_version':version,'pad_report':report,'native_parity':parity,'geometry':data,'validation':design.validate(result).as_dict(),'native_source':source}
