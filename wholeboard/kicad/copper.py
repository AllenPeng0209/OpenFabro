"""Preserve native copper identity and zone rules while editing routed boards."""
from __future__ import annotations

import copy
import math
import uuid

from .. import sexpr
from ..sexpr import S,Sym,find,find_all,tag

ZONE_FIELDS={'net','net_name','layer','layers','uuid','name','hatch','priority','connect_pads','min_thickness','filled_areas_thickness','fill','polygon','keepout','placement','attr','locked','teardrop','filled_polygon','fill_segments'}


def identity(item):
    value=item.get('id')
    return str(uuid.UUID(value)) if isinstance(value,str) else str(uuid.uuid4())


def capture_zone(node,net,origin):
    clean=copy.deepcopy(node)
    clean[:]=[child for child in clean if tag(child) not in {'filled_polygon','fill_segments'}]
    n=find(clean,'net')
    if n and net:n[1:]=[net]
    layer=find(clean,'layer');layers=find(clean,'layers')
    return {'net':net,'origin':list(origin),'layers':[str(layer[1])] if layer else [str(x) for x in (layers or [])[1:]],'source':sexpr.dumps(clean)}


def parse_zone(item,layers,nets):
    if not isinstance(item,dict) or not isinstance(item.get('source'),str) or len(item['source'])>2_000_000:
        raise ValueError('A preserved copper zone needs bounded native zone data.')
    origin=item.get('origin')
    if not isinstance(origin,list) or len(origin)!=2 or any(not isinstance(v,(int,float)) or isinstance(v,bool) or not math.isfinite(v) for v in origin):
        raise ValueError('A preserved copper zone needs a finite board origin.')
    node=sexpr.parse(item['source'])
    if item.get('id') is not None:
        try:uuid.UUID(item['id'])
        except (ValueError,TypeError,AttributeError):raise ValueError('A preserved zone needs a valid UUID.') from None
    if tag(node)!='zone' or any(tag(child) not in ZONE_FIELDS for child in node[1:] if isinstance(child,list)):
        raise ValueError('Preserved zone data must contain only a native copper zone.')
    net=item.get('net','')
    if not isinstance(net,str) or (net not in nets and not (not net and find(node,'keepout'))):
        raise ValueError('A copper zone must belong to an existing net.')
    layer=find(node,'layer');span=find(node,'layers')
    selected=[str(layer[1])] if layer else [str(x) for x in (span or [])[1:]]
    if not selected or any(layer not in layers for layer in selected):
        raise ValueError('A copper zone must use layers in the board stackup.')
    polygons=list(find_all(node,'polygon'))
    if not polygons:raise ValueError('A copper zone needs its original polygon outline.')
    for polygon in polygons:
        points=find(polygon,'pts') or []
        if len(points)<4:raise ValueError('A copper zone needs at least three polygon vertices.')
    for part in sexpr.walk(node):
        if tag(part)=='xy':
            if len(part)!=3 or any(not math.isfinite(float(v)) or abs(float(v))>1_000_000 for v in part[1:]):
                raise ValueError('Zone coordinates must be finite points.')
    return node


def zones(spec,origin):
    from .board import copper_layers
    out=[]
    for item in spec.get('fixed_zones') or []:
        node=parse_zone(item,set(copper_layers(int(spec['board']['layers']))),{n['name'] for n in spec['nets']})
        node[:]=[child for child in node if tag(child) not in {'filled_polygon','fill_segments'}]
        net=find(node,'net');name=find(node,'net_name')
        if net:net[1:]=[item['net']] if item['net'] else [Sym('0')]
        if name:name[1:]=[item['net']]
        if item.get('id'):
            identifier=find(node,'uuid')
            if identifier:identifier[1:]=[item['id']]
            else:node.append(S(Sym('uuid'),item['id']))
        delta=[origin[i]-item['origin'][i] for i in range(2)]
        for part in sexpr.walk(node):
            if tag(part)=='xy':part[1:]=[Sym(sexpr.fmt(round(float(v)+delta[i],6))) for i,v in enumerate(part[1:])]
        out.append(node)
    return out


def validate(spec):
    items=spec.get('fixed_zones') or []
    if not isinstance(items,list) or len(items)>1000:raise ValueError('Preserved copper zones must be a bounded list.')
    from .board import copper_layers
    layers=set(copper_layers(int(spec['board'].get('layers',2))))
    nets={n['name'] for n in spec.get('nets',[])}
    for item in items:parse_zone(item,layers,nets)
