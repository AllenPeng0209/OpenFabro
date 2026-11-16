"""Reviewable electrical cuts derived from the actual native schematic geometry."""
from __future__ import annotations
import copy
import math
import re
import tempfile
import threading
import uuid
from collections import defaultdict
from pathlib import Path
from urllib.parse import quote,unquote
from shapely.geometry import LineString,Point
from shapely.ops import unary_union
from shapely.strtree import STRtree
from . import sheets,schematic_view
from .kicad import schematic

EPS=1e-5

def _parts(value):
    if value.is_empty:return []
    if value.geom_type=='LineString':return [value]
    return [line for part in getattr(value,'geoms',[]) for line in _parts(part)]

def _point(value):return tuple(round(float(v),5) for v in value)

class Graph:
    def __init__(self,lines,links=()):
        self.parent={};self.edges=[]
        for line in _parts(unary_union(lines)):
            for a,b in zip(line.coords,list(line.coords)[1:]):
                a,b=_point(a),_point(b)
                if a!=b:self.join(a,b);self.edges.append((a,b))
        if len(self.edges)>100000:raise ValueError('The wire network is too large for one cut.')
        self.shapes=[LineString(edge) for edge in self.edges];self.tree=STRtree(self.shapes)
        for points in links:
            roots=[self.at(p) for p in points]
            for root in roots[1:]:self.join(roots[0],root)
    def root(self,p):
        p=_point(p);self.parent.setdefault(p,p)
        while self.parent[p]!=p:self.parent[p]=self.parent[self.parent[p]];p=self.parent[p]
        return p
    def join(self,a,b):self.parent[self.root(a)]=self.root(b)
    def at(self,p):
        p=_point(p)
        if p in self.parent:return self.root(p)
        target=Point(p)
        for index in self.tree.query(target.buffer(EPS)):
            if self.shapes[index].distance(target)<EPS:return self.root(self.edges[index][0])
        return self.root(p)
    def on_wire(self,p):return any(self.shapes[i].distance(Point(p))<EPS for i in self.tree.query(Point(p).buffer(EPS)))

def _pick(route,at,mode,gap):
    if not isinstance(at,list) or len(at)!=2 or any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in at):raise ValueError('Choose a finite point on the native wire.')
    best=None
    for a,b in zip(route['points'],route['points'][1:]):
        length=math.dist(a,b)
        if not length:continue
        t=max(0,min(1,sum((at[i]-a[i])*(b[i]-a[i]) for i in range(2))/length**2));p=[a[i]+t*(b[i]-a[i]) for i in range(2)];distance=math.dist(p,at)
        if best is None or distance<best[0]:best=(distance,list(a),list(b),p,length)
    if not best or best[0]>10:raise ValueError('Choose a point on the selected native wire.')
    _,a,b,p,length=best
    if mode=='segment':return a,b
    axis=0 if abs(b[0]-a[0])>abs(b[1]-a[1]) else 1;p[axis]=round(p[axis]/10)*10
    if abs(gap/10-round(gap/10))>EPS:raise ValueError('Wire gaps use whole connection-grid steps.')
    lo,hi=sorted((a[axis],b[axis]));left=p[axis]-math.floor(gap/20)*10;right=left+gap
    if left<lo+EPS or right>hi-EPS:raise ValueError('Choose a longer segment or use Remove segment near a bend or pin.')
    x,y=list(p),list(p);x[axis]=left;y[axis]=right
    return (x,y) if b[axis]>a[axis] else (y,x)

def prepare(spec,arguments,*,scene_data=None):
    if not isinstance(arguments,dict):raise ValueError('Wire cutting needs an object of properties.')
    scene=scene_data if scene_data is not None else schematic_view.scene(spec);page=arguments.get('sheet','');identifier=arguments.get('wire')
    route=next((r for r in scene['routes'] if r['id']==identifier and r['sheet']==page),None)
    if not route or route['status']!='routed':raise ValueError('The native wire changed. Select a routed wire again.')
    guides=spec.get('editor',{}).get('connection_guides',[])
    if not any(g.get('id')==identifier for g in guides):raise ValueError('The saved wire no longer exists.')
    mode=arguments.get('mode','gap');gap=arguments.get('gap_units',20)
    if mode not in ('gap','segment') or mode=='gap' and (isinstance(gap,bool) or not isinstance(gap,(int,float)) or not math.isfinite(gap) or not 0<gap<=1000):raise ValueError('Choose a bounded positive wire gap or segment deletion.')
    net=next(n for n in spec['nets'] if n['name']==route['net']);name=net['name'];scale=scene.get('mm_per_unit',.127);origin=scene.get('origin_mm',20.32)
    mm=lambda p:_point(origin+float(v)*scale for v in p)
    editor=lambda p:[round((v-origin)/scale,6) for v in p]
    start,end=_pick(route,arguments.get('point'),mode,gap);cut=LineString([mm(start),mm(end)])
    lines=[LineString([mm(p) for p in wire['points']]) for wire in scene['wires'] if wire['sheet']==page and wire['net']==name]
    if not lines:raise ValueError('The selected wire has no native geometry.')
    defs=sheets.definitions(spec);subtrees={key:{key} for key in defs}
    for key in reversed(sheets.order(spec)):
        if defs[key].get('parent'):subtrees[defs[key]['parent']]|=subtrees[key]
    subtrees['']={'',*defs}
    locations={c['ref']:sheets.component_sheet(c) for c in spec['components']};pin_net={pin:n['name'] for n in spec['nets'] for pin in n['pins']};nodes=spec.get('editor',{}).get('wire_nodes',{})
    ports={};links=defaultdict(list)
    for node in scene.get('sheet_nodes',[]):
        if node['sheet']!=page:continue
        for port in node['ports']:
            if port['net']==name:
                anchor='sheet:'+node['target']+'.'+quote(port.get('label',name),safe="~()*!.'-");ports[anchor]=(node['target'],port)
                links[node['target']].append(mm(port['position']))
    def net_of(a):
        if a.startswith('node:'):return nodes.get(a[5:],{}).get('net')
        if a.startswith('sheet:'):return ports.get(a,('',{}))[1].get('net')
        return pin_net.get(re.sub(r'#\d+(?=\.)','',a))
    anchors=[a for a in scene['anchors'] if a['sheet']==page and net_of(a['anchor'])==name]
    pin_occurrences=defaultdict(list)
    for anchor in anchors:
        if not anchor['anchor'].startswith(('node:','sheet:')):pin_occurrences[re.sub(r'#\d+(?=\.)','',anchor['anchor'])].append(mm(anchor['position']))
    label_points=[mm(a['position']) for a in anchors if a['anchor'].startswith('node:') and nodes[a['anchor'][5:]].get('label')]
    for sid,points in links.items():
        if any(n.get('label') and n['net']==name and n.get('sheet','') in subtrees[sid] for n in nodes.values()):label_points.extend(points)
    connections=[*links.values(),*[points for points in pin_occurrences.values() if len(points)>1],*([label_points] if len(label_points)>1 else [])]
    before=Graph(lines,connections);target=before.at(mm(route['points'][0]));target_lines=[LineString(edge) for edge in before.edges if before.root(edge[0])==target]
    old_shape=unary_union(target_lines);remaining=old_shape.difference(cut)
    if abs(old_shape.length-remaining.length)<EPS:raise ValueError('The selected span no longer belongs to this wire.')
    relevant_links=[points for points in connections if any(before.at(p)==target for p in points)]
    after=Graph(_parts(remaining),relevant_links)
    affected=[a for a in anchors if before.at(mm(a['position']))==target]
    affected_routes=[r for r in scene['routes'] if r['sheet']==page and r['net']==name and r['status']=='routed' and before.at(mm(r['points'][0]))==target]
    affected_ids={r['id'] for r in affected_routes}
    if any(r['sheet']==page and r['net']==name and r['status']!='routed' for r in scene['routes']):raise ValueError('Resolve the other unroutable drawings on this net before cutting it.')
    pins_by_root=defaultdict(set);nodes_by_root=defaultdict(set);anchor_root={};port_root={}
    for a in affected:
        root=after.at(mm(a['position']));anchor=a['anchor'];anchor_root[anchor]=root
        if anchor.startswith('node:'):
            if after.on_wire(mm(a['position'])):nodes_by_root[root].add(anchor[5:])
        elif anchor.startswith('sheet:'):
            sid,_=ports[anchor];port_root[sid]=root
            pins_by_root[root].update(pin for pin in net['pins'] if locations.get(pin.split('.')[0],'') in subtrees[sid])
        else:pins_by_root[root].add(re.sub(r'#\d+(?=\.)','',anchor))
    roots={after.root(a) for a,b in after.edges}|{root for root,pins in pins_by_root.items() if pins}
    def root_point(root):
        points=[a for a in after.parent if after.root(a)==after.root(root)];return min(points) if points else root
    ordered=sorted(roots,key=root_point);ids={root:f'g{i}' for i,root in enumerate(ordered)}
    groups=[{'id':ids[root],'pins':sorted(pins_by_root[root]),'position':editor(root_point(root))} for root in ordered];binding_groups=copy.deepcopy(groups)
    labeled_roots=[after.at(p) for p in label_points if after.on_wire(p) and before.at(p)==target]
    required=[];forced=list(dict.fromkeys(labeled_roots));interface_forced=False;choices=arguments.get('port_bindings') or {}
    if not isinstance(choices,dict):raise ValueError('Module port bindings must be an object.')
    upward=[(label,p) for label,p in sheets.boundaries(spec).get(page,{}).items() if p['net']==name] if page else []
    for label,port in upward:
        pin=port.get('terminal_ref','')+'.1';bound=next((root for root in ordered if pin in pins_by_root[root]),None);key=page+'.'+label
        if bound is None:
            if choices.get(key) is not None:
                bound=next((root for root in ordered if ids[root]==choices[key]),None)
                if bound is None:raise ValueError('Choose an existing resulting group for the module port.')
            elif forced:bound=forced[0]
            elif len(ordered)==1:bound=ordered[0]
            else:required.append({'id':key,'label':label,'sheet':page})
        if bound is not None:forced.append(bound);interface_forced=True
    if required:return {'spec':None,'groups':groups,'required_bindings':required,'summary':{'net':name,'cut':[start,end]}}
    if forced:
        for root in forced[1:]:after.join(forced[0],root)
        forced=[after.root(forced[0])]
    # A shared external module interface is a genuine alternate electrical path.
    merged=defaultdict(set)
    for root,pins in pins_by_root.items():merged[after.root(root)]|=pins
    pins_by_root=merged;roots={after.root(root) for root in ordered};ordered=sorted(roots,key=root_point);ids={root:f'g{i}' for i,root in enumerate(ordered)}
    source_root=after.at(mm(route['points'][0]));keep=forced[0] if forced else next((r for r in ordered if ids[r]==arguments.get('retain_group')),source_root if source_root in roots else next(iter(ordered),None))
    if arguments.get('retain_group') is not None and not forced and not any(ids[r]==arguments['retain_group'] for r in ordered):raise ValueError('Choose an existing group to keep the original name.')
    assigned={pin:root for root,pins in pins_by_root.items() for pin in pins}
    if forced:
        outside=[pin for pin in net['pins'] if locations.get(pin.split('.')[0],'') not in subtrees[page]]
        pins_by_root[keep].update(outside);assigned.update({pin:keep for pin in outside})
    unrouted=[pin for pin in net['pins'] if pin not in assigned]
    if keep is not None:pins_by_root[keep].update(unrouted);assigned.update({pin:keep for pin in unrouted})
    claimed={n['name'] for n in spec['nets']};base=arguments.get('new_name',name+'_CUT')
    if not isinstance(base,str) or not base.strip() or not base.isprintable() or len(base)>240:raise ValueError('The new net name needs bounded printable text.')
    group_name={};new_nets=[];index=1
    for root in ordered:
        if root==keep:group_name[root]=name;continue
        candidate=base if index==1 else base+'_'+str(index)
        while candidate in claimed:index+=1;candidate=base+'_'+str(index)
        index+=1;claimed.add(candidate);group_name[root]=candidate
        row={**copy.deepcopy(net),'name':candidate,'pins':sorted(pins_by_root[root])};row.pop('placeholder_ref',None);row.pop('wire_only',None)
        if not row['pins']:row['wire_only']=True
        new_nets.append(row)
    out=copy.deepcopy(spec);out_editor=out.setdefault('editor',{});out_nodes=out_editor.setdefault('wire_nodes',{})
    for row in out['nets']:
        if row['name']==name:row['pins']=[p for p in row['pins'] if p not in assigned or group_name[assigned[p]]==name]
    out['nets']+=new_nets
    pin_names={pin:group_name[root] for pin,root in assigned.items()}
    def domain_name(sid):
        if sid==page:return None
        root=next((root for child,root in port_root.items() if sid in subtrees[child]),None)
        if root is not None:return group_name[after.root(root)]
        return name
    for key,node in list(out_nodes.items()):
        if node['net']!=name:continue
        if node.get('sheet','')==page and before.at(mm(node['position']))==target:
            if not after.on_wire(mm(node['position'])):
                if not node.get('label'):del out_nodes[key]
            else:node['net']=group_name[after.at(mm(node['position']))]
        elif node.get('sheet','')!=page:node['net']=domain_name(node.get('sheet','')) or name
    # Keep interface labels stable when inferred canonical names change.
    pages=out_editor.setdefault('sheets',{})
    for sheet_node in scene.get('sheet_nodes',[]):
        sid=sheet_node['target'];inside=[p for p in net['pins'] if locations.get(p.split('.')[0],'') in subtrees.get(sid,{sid})]
        for port in sheet_node['ports']:
            if port['net']!=name:continue
            values={pin_names.get(p,name) for p in inside};terminal=port.get('terminal_ref','')+'.1';mapped=pin_names.get(terminal,next(iter(values)) if len(values)==1 else name)
            d=pages.setdefault(sid,copy.deepcopy(defs[sid]));label=port.get('label',name);d.setdefault('ports',{})[label]={**d.get('ports',{}).get(label,{}),**{k:v for k,v in port.items() if k in ('terminal_ref','direction','side','number','order','group','section')},'net':mapped}
    # Rebuild the affected physical wire island as exact, checked native spans.
    retained=[g for g in out_editor.get('connection_guides',[]) if g.get('id') not in affected_ids]
    for g in retained:
        for key in ('from_join','to_join'):
            if g.get(key,{}).get('wire') in affected_ids:raise ValueError('A dependent drawing could not be included in the cut.')
    named_at=defaultdict(list)
    for a in affected:
        if not a['anchor'].startswith('node:') or a['anchor'][5:] in out_nodes:named_at[mm(a['position'])].append(a['anchor'])
    for key,node in out_nodes.items():
        if node.get('sheet','')==page and node['net'] in set(group_name.values()):named_at[mm(node['position'])].append('node:'+key)
    def anchor_at(p,root):
        choices=named_at[p]
        if choices:return sorted(choices,key=lambda a:(a.startswith('node:'),a))[0]
        identifier=str(uuid.uuid4());out_nodes[identifier]={'position':editor(p),'sheet':page,'net':group_name[root]};choices.append('node:'+identifier);return choices[0]
    anchor_points=list(named_at);point_tree=STRtree([Point(p) for p in anchor_points])
    for a,b in after.edges:
        root=after.root(a);line=LineString([a,b]);points={a,b}
        for i in point_tree.query(line.buffer(EPS)):
            if line.distance(Point(anchor_points[i]))<EPS:points.add(anchor_points[i])
        ordered_points=sorted(points,key=lambda p:line.project(Point(p)))
        for x,y in zip(ordered_points,ordered_points[1:]):
            if math.dist(x,y)<EPS:continue
            retained.append({'id':str(uuid.uuid4()),'from':anchor_at(x,root),'to':anchor_at(y,root),'fixed_points':[editor(x),editor(y)]})
    out_editor['connection_guides']=retained
    changed=sorted(pin for pin in net['pins'] if pin_names.get(pin,name)!=name)
    physical=[pin for pin in changed if not next((c.get('terminal',{}).get('exclude_from_pcb') for c in spec['components'] if c['ref']==pin.split('.')[0]),False)]
    removed={'tracks':0,'arcs':0,'vias':0,'zones':0};cleared=[]
    if physical:
        for group in out.get('fixed_copper',[]):
            if group['net']==name:
                for kind in ('tracks','arcs','vias'):removed[kind]+=len(group.get(kind,[]))
        removed['zones']=sum(z.get('net')==name for z in out.get('fixed_zones',[]))
        if 'fixed_copper' in out:out['fixed_copper']=[g for g in out['fixed_copper'] if g['net']!=name]
        if 'fixed_zones' in out:out['fixed_zones']=[z for z in out['fixed_zones'] if z.get('net')!=name]
        board=out['board']
        if board.get('ground_pour','GND')==name:board['ground_pour']=None;cleared.append('ground pour')
        for layer,value in list(board.get('planes',{}).items()):
            if value==name:del board['planes'][layer];cleared.append(layer)
    for instance in out_editor.get('module_instances',{}).values():
        for key,value in list(instance.get('nets',{}).items()):
            if value!=name:continue
            values={pin_names.get(p,name) for p in net['pins'] if p.split('.')[0] in instance.get('refs',[])}
            if len(values)==1:instance['nets'][key]=next(iter(values))
            elif len(values)>1:instance.setdefault('net_splits',{})[key]=sorted(values);instance['modified']=True
    used_names={n['net'] for n in out_nodes.values()}|{g['net'] for g in out.get('fixed_copper',[])}|{z.get('net') for z in out.get('fixed_zones',[])}|set(out['board'].get('planes',{}).values())|{out['board'].get('ground_pour')}
    out['nets']=[n for n in out['nets'] if n['name']!=name or n['pins'] or not n.get('wire_only') or name in used_names]
    groups=[{'id':ids[root],'name':group_name[root],'pins':sorted(pins_by_root[root]),'position':editor(root_point(root)),'retained':root==keep} for root in ordered]
    return {'spec':out,'groups':groups,'binding_groups':binding_groups,'required_bindings':[],'summary':{'net':name,'cut':[start,end],'mode':mode,'changed_pins':changed,'unrouted_pins':unrouted,'removed_copper':removed,'cleared_planes':cleared,'replaced_guides':sorted(affected_ids),'electrically_split':bool(new_nets),'retained_group':ids.get(keep),'retained_by_interface':interface_forced,'retained_by_label':bool(labeled_roots)}}

def project_draft(project,arguments):
    from fastapi import HTTPException
    from . import workbench_native
    with workbench_native._locks.setdefault(project.id,threading.RLock()):
        if getattr(project,'engine_busy',False):raise HTTPException(409,'Wait for the engineering run before cutting a wire.')
        return _project_draft(project,arguments)

def _project_draft(project,arguments):
    from fastapi import HTTPException
    from . import workbench_native
    from .module_capture import native_copper
    from .kicad import geometry,libs,cli
    from .workbench import validate_draft
    with project.lock:
        version=project.state.get('workbench',{}).get('version',0)
        if arguments.get('base_version')!=version:raise HTTPException(409,'The design changed before the wire cut.')
        spec=copy.deepcopy(project.state.get('spec') or {})
    pcb=workbench_native.final_pcb(project)
    if pcb is None and libs.locate('footprints') and libs.locate('symbols'):pcb=Path(workbench_native.generate(project)['pcb'])
    if pcb:spec['fixed_copper'],spec['fixed_zones']=native_copper(geometry.read(pcb))
    result=prepare(spec,arguments)
    if result['spec'] is not None:
        validate_draft(result['spec'])
        with tempfile.TemporaryDirectory(prefix='wholeboard-wire-cut-') as folder:
            native=schematic.build(result['spec'],Path(folder))
            if any(r['status']!='routed' for page in native['pages'] for r in page['wiring']['routes']):raise ValueError('The cut conflicts with a symbol or another net. Choose another span or resolve its interface binding.')
            proof=schematic.netlist_parity(result['spec'],cli.schematic_nets(Path(native['sch'])))
        if not proof['ok']:raise ValueError('The cut would not produce the proposed native electrical connections.')
        result['native_parity']=proof;result['preview']=schematic_view.scene(result['spec'])
    with project.lock:
        if project.state.get('workbench',{}).get('version',0)!=version:raise HTTPException(409,'The design changed while preparing the wire cut.')
    return {**result,'base_version':version}
