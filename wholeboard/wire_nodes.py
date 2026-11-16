"""Schematic-only wire endpoints: never represented as components or PCB pads."""
from __future__ import annotations
import copy
import math
import re
from . import sheets

def validate(spec):
    editor=spec.get('editor') or {};nodes=editor.get('wire_nodes',{})
    if not isinstance(nodes,dict) or len(nodes)>10000:raise ValueError('Wire nodes must be a bounded object.')
    pages={'',*sheets.definitions(spec)};nets={n['name'] for n in spec.get('nets',[])}
    for key,node in nodes.items():
        if not isinstance(key,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',key) or not isinstance(node,dict):raise ValueError('A wire node needs a valid ID and properties.')
        pos=node.get('position')
        if not isinstance(pos,list) or len(pos)!=2 or any(not isinstance(v,(int,float)) or isinstance(v,bool) or not math.isfinite(v) or abs(v)>1_000_000 for v in pos):raise ValueError('Wire nodes need bounded finite coordinates.')
        if node.get('net') not in nets:raise ValueError('A wire node needs an existing electrical net.')
        if node.get('sheet','') not in pages:raise ValueError('A wire node belongs to an existing schematic sheet.')
        if 'label' in node:
            from . import net_labels
            net_labels.validate_label(node['label'])
    components={c['ref']:sheets.component_sheet(c) for c in spec.get('components',[])};defs=sheets.definitions(spec)
    def page(anchor):
        if anchor.startswith('node:'):
            if anchor[5:] not in nodes:raise ValueError('A wire route refers to a missing node.')
            return nodes[anchor[5:]].get('sheet','')
        if anchor.startswith('sheet:'):return defs.get(anchor[6:].split('.',1)[0],{}).get('parent','')
        return components.get(re.split(r'[.#]',anchor,maxsplit=1)[0])
    for guide in editor.get('connection_guides',[]):
        if not isinstance(guide,dict) or not all(isinstance(guide.get(k),str) for k in ('from','to')):raise ValueError('Wire routes need valid endpoint anchors.')
        if any(guide[k].startswith('node:') for k in ('from','to')):
            a,b=page(guide['from']),page(guide['to'])
            if a is None or b is None or a!=b:raise ValueError('Wire endpoints must be on the same schematic sheet.')

def selected_geometry(spec,refs):
    chosen=set(refs);nodes=(spec.get('editor') or {}).get('wire_nodes',{})
    def allowed(a):return a[5:] in nodes if a.startswith('node:') else re.split(r'[.#]',a,maxsplit=1)[0] in chosen
    candidates=[g for g in spec.get('editor',{}).get('connection_guides',[]) if all(allowed(g[k]) for k in ('from','to'))]
    included=set();active=set();changed=True
    while changed:
        changed=False
        for index,g in enumerate(candidates):
            if index not in included and any(a[5:] in active if a.startswith('node:') else re.split(r'[.#]',a,maxsplit=1)[0] in chosen for a in (g['from'],g['to'])):
                included.add(index);active.update(a[5:] for a in (g['from'],g['to']) if a.startswith('node:'));changed=True
    return {'connection_guides':copy.deepcopy([g for i,g in enumerate(candidates) if i in included]),'wire_nodes':copy.deepcopy({k:v for k,v in nodes.items() if k in active})}

def floating_labels(routes,pins):
    """Name native wire islands that have no existing symbol or sheet-pin label."""
    parent={}
    def root(a):
        parent.setdefault(a,a)
        while a!=parent[a]:parent[a]=parent[parent[a]];a=parent[a]
        return a
    def join(a,b):parent[root(a)]=root(b)
    routed={r['id']:r for r in routes if r['status']=='routed'}
    for route in routed.values():
        join(route['from'],route['to'])
        for value in route.get('joins',{}).values():
            if value['wire'] in routed:join(route['from'],routed[value['wire']]['from'])
    groups={}
    for anchor in parent:groups.setdefault(root(anchor),[]).append(anchor)
    return [pins[anchors[0]] for anchors in groups.values() if all(a.startswith('node:') for a in anchors) and not any(pins[a].get('labeled') for a in anchors)]
