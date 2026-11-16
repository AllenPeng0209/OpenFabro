"""Planar DXF/SVG originals become exact-curve profile snapshots, not board outlines.

Sampling is used to determine nesting only. Native CAD reconstructs the original
lines/conics/Bezier/NURBS, so a round cutout stays round after extrusion.
"""
from __future__ import annotations

import collections
import io
import itertools
from importlib.metadata import version
import math
from pathlib import Path
import re
import tempfile
import xml.etree.ElementTree as ET

from defusedxml import ElementTree as SafeXML
import ezdxf
from ezdxf import colors as dxf_colors,units as dxf_units
from ezdxf.math import BSpline
import numpy as np
from shapely.geometry import Polygon
import svgelements as svg

LIMIT=20_000_000
EDGE_LIMIT=20_000
POINT_LIMIT=300_000
JOIN_TOL=1e-6
FLAT_TOL=1e-4
UNIT_SCALE={'mm':1.,'cm':10.,'m':1000.,'in':25.4,'px':25.4/96}


def _vec(value,scale=1.):
    result=[float(v)*scale for v in value]
    if len(result)!=3 or any(not math.isfinite(v) or abs(v)>20000 for v in result):raise ValueError('Drawing coordinates must be finite and within 20000 mm.')
    return result


def _hex(rgb):return '#'+''.join(f'{max(0,min(255,int(v))):02x}' for v in rgb[:3])


def _ellipse(center,xaxis,yaxis,t0,sweep,info):
    # SVD retains conics under nonuniform scale, skew, reflection and nested transforms.
    matrix=np.array([xaxis,yaxis],dtype=float).T;u,s,vt=np.linalg.svd(matrix,full_matrices=False)
    if min(s)<1e-9:raise ValueError('Drawing contains a degenerate ellipse.')
    q=vt@np.array([math.cos(t0),math.sin(t0)])
    return {'kind':'ellipse','center':_vec(center),'axis_x':_vec(u[:,0]*s[0]),'axis_y':_vec(u[:,1]*s[1]),
            't0':math.atan2(q[1],q[0]),'sweep':float(np.linalg.det(vt))*sweep,**info}


def _samples(edge):
    kind=edge['kind']
    if kind=='line':return [edge['start'],edge['end']]
    if kind=='ellipse':
        radius=max(math.hypot(*edge['axis_x']),math.hypot(*edge['axis_y']));angle=2*math.acos(max(-1.,1-min(FLAT_TOL/radius,1.)))
        n=max(4,math.ceil(abs(edge['sweep'])/max(angle,1e-5)))
        if n>POINT_LIMIT:raise ValueError('Drawing exceeds the curve sampling budget.')
        return [[edge['center'][j]+edge['axis_x'][j]*math.cos(edge['t0']+edge['sweep']*i/n)+edge['axis_y'][j]*math.sin(edge['t0']+edge['sweep']*i/n) for j in range(3)] for i in range(n+1)]
    if kind=='bspline':
        curve=BSpline(edge['poles'],order=edge['degree']+1,knots=edge['knots'],weights=edge['weights'] or None)
        points=[_vec(v) for v in itertools.islice(curve.flattening(FLAT_TOL,segments=4),POINT_LIMIT+1)]
        if len(points)>POINT_LIMIT:raise ValueError('Drawing exceeds the spline sampling budget.')
        return points
    if kind=='bezier':
        points=[]
        def split(poles,depth=0):
            a,b=np.array(poles[0]),np.array(poles[-1]);chord=b-a;length=np.linalg.norm(chord)
            error=max((np.linalg.norm(np.cross(np.array(p)-a,chord))/length if length>1e-12 else np.linalg.norm(np.array(p)-a)) for p in poles)
            if error<=FLAT_TOL:
                points.append(list(poles[0]));return
            if depth>=24 or len(points)>POINT_LIMIT:raise ValueError('Drawing exceeds the Bezier sampling budget.')
            levels=[np.asarray(poles,dtype=float)]
            while len(levels[-1])>1:levels.append((levels[-1][:-1]+levels[-1][1:])/2)
            split([row[0].tolist() for row in levels],depth+1);split([row[-1].tolist() for row in reversed(levels)],depth+1)
        split(edge['poles']);points.append(edge['poles'][-1]);return points
    raise ValueError('Unsupported drawing curve.')


def _assemble(edges):
    if len(edges)>EDGE_LIMIT:raise ValueError('Drawing exceeds the edge budget.')
    sampled=[_samples(edge) for edge in edges]
    if sum(map(len,sampled))>POINT_LIMIT:raise ValueError('Drawing exceeds the point budget.')
    positions=[];grid={}
    def vertex(point):
        key=tuple(round(v/JOIN_TOL) for v in point)
        for delta in itertools.product((-1,0,1),repeat=3):
            for i in grid.get(tuple(key[j]+delta[j] for j in range(3)),[]):
                if math.dist(positions[i],point)<=JOIN_TOL:return i
        i=len(positions);positions.append(point);grid.setdefault(key,[]).append(i);return i
    ends=[(vertex(points[0]),vertex(points[-1])) for points in sampled];adj={}
    for i,(a,b) in enumerate(ends):adj.setdefault(a,[]).append(i);adj.setdefault(b,[]).append(i)
    remaining=set(range(len(edges)));loops=[];references=[]
    while remaining:
        seed=min(remaining);component=set();stack=[seed]
        while stack:
            i=stack.pop()
            if i in component:continue
            component.add(i)
            for end in ends[i]:stack.extend(j for j in adj[end] if j not in component)
        remaining-=component
        if any(len(adj[v])!=2 for i in component for v in ends[i]):references.extend(edges[i] for i in sorted(component));continue
        start=ends[seed][0];current=start;unused=set(component);chain=[];points=[]
        while unused:
            index=next((i for i in adj[current] if i in unused),None)
            if index is None:break
            unused.remove(index);a,b=ends[index];reverse=a!=current;edge={**edges[index],'reverse':reverse};chain.append(edge)
            values=sampled[index][::-1] if reverse else sampled[index];points.extend(values if not points else values[1:]);current=a if reverse else b
        if unused or current!=start:references.extend(edges[i] for i in sorted(component))
        else:loops.append({'edges':chain,'points':points})
    return loops,references


def _profiles(edges,rule,label):
    loops,open_edges=_assemble(edges)
    if not loops:return [],open_edges
    points=np.asarray([p for loop in loops for p in loop['points']],dtype=float);origin=points.mean(axis=0);_,singular,basis=np.linalg.svd(points-origin,full_matrices=False)
    normal=basis[-1]
    if max(abs((points-origin)@normal))>JOIN_TOL:raise ValueError('Closed drawing outlines must be coplanar; select separate layers or parts.')
    priority=next((i for i in (2,1,0) if abs(normal[i])>1e-8),2)
    if normal[priority]<0:normal=-normal
    u=basis[0];v=np.cross(normal,u);polygons=[];signs=[]
    for loop in loops:
        local=(np.asarray(loop['points'])-origin)@np.array([u,v]).T
        # BLAS tail rows can differ by1ulp even for equal closing coordinates.
        # The native endpoint graph already proved closure within JOIN_TOL.
        local[-1]=local[0];polygon=Polygon(local)
        if not polygon.is_valid or polygon.area<1e-10:raise ValueError('A closed drawing outline self-intersects or has no area.')
        polygons.append(polygon);signs.append(1 if sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(local,np.roll(local,-1,axis=0)))>0 else -1)
    # Remove duplicated boundary entities rather than canceling their parity.
    unique=[]
    for i,p in enumerate(polygons):
        if not any(p.equals(polygons[j]) for j in unique):unique.append(i)
    parents={};depths={};winding={}
    for i in sorted(unique,key=lambda n:polygons[n].area,reverse=True):
        candidates=[]
        for j in unique:
            if i==j or polygons[j].area<=polygons[i].area:continue
            if polygons[j].contains(polygons[i]):candidates.append(j)
            elif polygons[j].intersects(polygons[i]):raise ValueError('Drawing outlines intersect or touch ambiguously.')
        parent=min(candidates,key=lambda j:polygons[j].area) if candidates else None;parents[i]=parent;depths[i]=0 if parent is None else depths[parent]+1
        winding[i]=signs[i]+(winding[parent] if parent is not None else 0)
    transitions={}
    for i in unique:
        parent=parents[i];outside=False if parent is None else depths[parent]%2==0 if rule=='evenodd' else winding[parent]!=0
        inside=depths[i]%2==0 if rule=='evenodd' else winding[i]!=0
        transitions[i]='outer' if inside and not outside else 'hole' if outside and not inside else 'ignore'
    results=[]
    for i in unique:
        if transitions[i]!='outer':continue
        holes=[]
        for j in unique:
            if transitions[j]!='hole':continue
            ancestor=parents[j]
            while ancestor is not None and transitions[ancestor]=='ignore':ancestor=parents[ancestor]
            if ancestor==i:holes.append(j)
        first=loops[i]['edges'][0]
        results.append({'name':label or first.get('layer') or 'Profile','color':first.get('color','#a6b5c0'),'layer':first.get('layer',''),
                        'outer':loops[i]['edges'],'holes':[loops[j]['edges'] for j in holes],'normal':normal.tolist(),
                        'topology_area_mm2':polygons[i].area-sum(polygons[j].area for j in holes),'fill_rule':rule})
    return results,open_edges


def _dxf(raw,units,layers,diagnostics):
    with tempfile.TemporaryDirectory(prefix='openfabro-dxf-') as folder:
        path=Path(folder)/'source.dxf';path.write_bytes(raw);doc=ezdxf.readfile(path)
    code=int(doc.header.get('$INSUNITS',0));assumed=code==0
    scale=dxf_units.conversion_factor(code,4) if code else UNIT_SCALE['mm' if units=='auto' else units]
    source_units={1:'in',2:'ft',4:'mm',5:'cm',6:'m'}.get(code,'DXF unit '+str(code)) if code else ('mm' if units=='auto' else units)
    edges=[];all_layers=set();count=0
    def visit(entity,parent_layer='0',stack=()):
        nonlocal count
        count+=1
        if count>EDGE_LIMIT:raise ValueError('Drawing exceeds the entity budget.')
        kind=entity.dxftype();layer=entity.dxf.get('layer','0');layer=parent_layer if layer=='0' else layer;all_layers.add(layer)
        if layers is not None and layer not in layers and kind!='INSERT':return
        definition=doc.layers.get(layer) if layer in doc.layers else None
        if layers is None and definition is not None and (definition.is_off() or definition.is_frozen()):return
        rgb=entity.rgb or (definition.rgb if definition is not None else None)
        if rgb is None:
            index=abs(entity.dxf.get('color',256));index=abs(definition.dxf.color) if index in (0,256) and definition is not None else index
            rgb=dxf_colors.aci2rgb(index if 1<=index<=255 else 7)
        info={'layer':layer,'color':_hex(rgb),'source_id':str(entity.dxf.get('handle') or count),'source_type':kind}
        if kind=='INSERT':
            name=entity.dxf.name
            if name in stack or len(stack)>32:raise ValueError('Drawing has a cyclic or too-deep block reference.')
            if entity.mcount>256:raise ValueError('Drawing block array exceeds256 instances.')
            for instance in entity.multi_insert() if entity.mcount>1 else [entity]:
                for child in instance.virtual_entities(skipped_entity_callback=lambda e,reason:diagnostics['ignored'].append({'type':e.dxftype(),'reason':str(reason)})):visit(child,layer,stack+(name,))
        elif kind in ('LWPOLYLINE','POLYLINE'):
            if len(entity)>EDGE_LIMIT:raise ValueError('Drawing polyline exceeds the vertex budget.')
            for child in entity.virtual_entities():visit(child,layer,stack)
        elif kind=='LINE':edges.append({'kind':'line','start':_vec(entity.dxf.start,scale),'end':_vec(entity.dxf.end,scale),**info})
        elif kind in ('CIRCLE','ARC'):
            ocs=entity.ocs();center=ocs.to_wcs(entity.dxf.center);radius=float(entity.dxf.radius)*scale
            t0=math.radians(entity.dxf.start_angle) if kind=='ARC' else 0.;sweep=math.radians((entity.dxf.end_angle-entity.dxf.start_angle)%360) if kind=='ARC' else math.tau
            edges.append(_ellipse(_vec(center,scale),_vec(ocs.ux,radius),_vec(ocs.uy,radius),t0,sweep,info))
        elif kind=='ELLIPSE':
            curve=entity.construction_tool();sweep=(curve.end_param-curve.start_param)%math.tau or math.tau
            edges.append(_ellipse(_vec(curve.center,scale),_vec(curve.major_axis,scale),_vec(curve.minor_axis,scale),curve.start_param,sweep,info))
        elif kind=='SPLINE':
            curve=entity.construction_tool();poles=[_vec(p,scale) for p in curve.control_points];knots=[float(k) for k in curve.knots()];weights=[float(w) for w in curve.weights()]
            if len(poles)>4096 or len(knots)>8192 or not 1<=curve.degree<=25:raise ValueError('Drawing spline exceeds supported bounds.')
            edges.append({'kind':'bspline','poles':poles,'knots':knots,'weights':weights,'degree':curve.degree,**info})
        else:diagnostics['ignored'].append({'type':kind,'layer':layer,'reason':'Not an outline curve.'})
    for entity in doc.modelspace():visit(entity)
    profiles,references=_profiles(edges,'evenodd',None)
    return profiles,references,sorted(all_layers),source_units,assumed


_LENGTH=re.compile(r'^\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\s*(mm|cm|in|pt|pc|q)\s*$',re.I)
_CSS_UNITS={'mm':96/25.4,'cm':96/2.54,'in':96.,'pt':96/72,'pc':16.,'q':96/101.6}


def _svg(raw,units,mode,diagnostics):
    try:root=SafeXML.fromstring(raw,forbid_dtd=True,forbid_entities=True,forbid_external=True)
    except Exception as error:raise ValueError('Unsafe or invalid SVG XML: '+str(error)) from error
    if root.tag.rsplit('}',1)[-1]!='svg':raise ValueError('Use an SVG root element.')
    physical=any(_LENGTH.fullmatch(root.get(key,'')) for key in ('width','height'))
    count=0;path_values=0;identifiers={node.get('id'):node for node in root.iter() if node.get('id')}
    for node in root.iter():
        count+=1
        if count>EDGE_LIMIT:raise ValueError('SVG exceeds the element budget.')
        tag=node.tag.rsplit('}',1)[-1]
        if tag in ('text','image','foreignObject','filter','script'):
            diagnostics['ignored'].append({'type':tag,'source_id':node.get('id'),'reason':'Not an outlined vector profile; retained in the original SVG.'})
        for attribute in ('d','points'):
            for _ in re.finditer(r'[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?',node.get(attribute,'')):
                path_values+=1
                if path_values>200000:raise ValueError('SVG path data exceeds the geometry budget.')
        for key,value in list(node.attrib.items()):
            local=key.rsplit('}',1)[-1]
            if local=='href' and value and not value.startswith('#'):raise ValueError('SVG external references are not loaded; use embedded vector paths.')
            if local in ('x','y','x1','y1','x2','y2','cx','cy','r','rx','ry','width','height'):
                match=_LENGTH.fullmatch(value)
                if match:node.set(key,repr(float(match[1])*_CSS_UNITS[match[2].lower()]))
            if local in ('clip-path','mask') and value!='none':raise ValueError('SVG clipping/masks must be converted to outline paths first.')
    expanded=0
    def guard_references(node,active,depth=0,referenced=False):
        nonlocal expanded
        expanded+=1
        if expanded>EDGE_LIMIT or depth>128:raise ValueError('SVG expanded references exceed the geometry budget.')
        tag=node.tag.rsplit('}',1)[-1]
        if tag in ('defs','symbol') and not referenced:return
        identifier=node.get('id')
        if identifier and identifier in active:raise ValueError('SVG contains a cyclic use reference.')
        active=active|({identifier} if identifier else set())
        if tag=='use':
            target=node.get('href') or node.get('{http://www.w3.org/1999/xlink}href')
            if target:
                if target[1:] not in identifiers:raise ValueError('SVG use references a missing vector definition.')
                guard_references(identifiers[target[1:]],active,depth+1,True)
        for child in node:guard_references(child,active,depth+1,referenced)
    guard_references(root,set())
    scale=25.4/96 if physical or units=='auto' else UNIT_SCALE[units]
    document=svg.SVG.parse(io.BytesIO(ET.tostring(root)),reify=False,ppi=96,on_error='raise')
    profiles=[];references=[];all_edges=[];layer_names=[]
    for i,shape in enumerate(document.elements()):
        if not isinstance(shape,svg.Shape):continue
        path=svg.Path(shape);transform=shape.transform
        # Matrix has no bounded iterator; access its six documented scalar fields.
        a,b,c,d,e,f=(float(getattr(transform,key)) for key in ('a','b','c','d','e','f'))
        def point(p):return _vec([(a*p.x+c*p.y+e)*scale,-(b*p.x+d*p.y+f)*scale,0])
        def vector(p):return _vec([(a*p.x+c*p.y)*scale,-(b*p.x+d*p.y)*scale,0])
        label=shape.id or 'SVG profile '+str(i+1);layer_names.append(label)
        fill=shape.fill;stroke=shape.stroke;color=fill if fill is not None and fill.value is not None else stroke
        rgb=[color.red,color.green,color.blue] if color is not None and color.value is not None else [166,181,192]
        info={'layer':label,'color':_hex(rgb),'source_id':label,'source_type':type(shape).__name__};edges=[];start=None
        for segment in path:
            if isinstance(segment,svg.Move):start=segment.end;continue
            if isinstance(segment,(svg.Line,svg.Close)):
                if abs(segment.start-segment.end)>1e-12:edges.append({'kind':'line','start':point(segment.start),'end':point(segment.end),**info})
            elif isinstance(segment,svg.Arc):
                if abs(segment.sweep)>1e-12:edges.append(_ellipse(point(segment.center),vector(segment.prx-segment.center),vector(segment.pry-segment.center),segment.get_start_t(),segment.sweep,info))
            elif isinstance(segment,svg.CubicBezier):edges.append({'kind':'bezier','poles':[point(p) for p in [segment.start,segment.control1,segment.control2,segment.end]],**info})
            elif isinstance(segment,svg.QuadraticBezier):edges.append({'kind':'bezier','poles':[point(p) for p in [segment.start,segment.control,segment.end]],**info})
            else:raise ValueError('Unsupported SVG path segment.')
        if mode=='outline':all_edges.extend(edges)
        elif fill is None or fill.value is None:references.extend(edges)
        else:
            # SVG fills implicitly close open subpaths; explicit Close is already retained.
            groups=[];current=[]
            for edge in edges:
                if current and math.dist(_samples(current[-1])[-1],_samples(edge)[0])>JOIN_TOL:groups.append(current);current=[]
                current.append(edge)
            if current:groups.append(current)
            closed=[]
            for group in groups:
                first,last=_samples(group[0])[0],_samples(group[-1])[-1];closed.extend(group)
                if math.dist(first,last)>JOIN_TOL:closed.append({'kind':'line','start':last,'end':first,**info})
            made,open_edges=_profiles(closed,shape.values.get('fill-rule','nonzero'),label);profiles.extend(made);references.extend(open_edges)
    if mode=='outline':profiles,references=_profiles(all_edges,'evenodd',None)
    return profiles,references,layer_names,'document' if physical else ('css-px' if units=='auto' else units),not physical


def convert(name,raw,*,units='auto',drawing_mode=None,layers=None):
    fmt=name.rsplit('.',1)[-1].lower()
    if fmt not in ('dxf','svg') or not isinstance(raw,bytes) or not 0<len(raw)<=LIMIT:raise ValueError('Use a DXF or SVG drawing smaller than20 MB.')
    if units not in {'auto',*UNIT_SCALE}:raise ValueError('Drawing units must be auto,mm,cm,m,in or px.')
    if layers is not None and (not isinstance(layers,list) or len(layers)>256 or any(not isinstance(v,str) or len(v)>200 for v in layers)):raise ValueError('Select drawing layer names from the source.')
    mode=drawing_mode or ('outline' if fmt=='dxf' else 'fill')
    if mode not in ('fill','outline'):raise ValueError('SVG regions use fill or outline interpretation.')
    diagnostics={'ignored':[],'issues':[]}
    try:
        profiles,references,names,source_units,assumed=_dxf(raw,units,layers,diagnostics) if fmt=='dxf' else _svg(raw,units,mode,diagnostics)
    except ValueError:raise
    except Exception as error:raise ValueError('Could not read drawing geometry: '+str(error)) from error
    if not profiles and not references:raise ValueError('The drawing has no supported outline or reference curves.')
    if len(profiles)>256:raise ValueError('Drawing exceeds256 closed profiles.')
    labels=collections.Counter(p['name'] for p in profiles)
    for i,p in enumerate(profiles):
        if labels[p['name']]>1:p['name']+=' / '+str(i+1)
    return {'schema':1,'geometry_kind':'planar-drawing','units':'mm','source_units':source_units,'units_assumed':assumed,'format':fmt,
            'drawing_mode':mode,'profiles':profiles,'references':references,'layers':names,'diagnostics':diagnostics,
            'topology_sampling_tolerance_mm':FLAT_TOL,'join_tolerance_mm':JOIN_TOL,
            'loader':'ezdxf '+ezdxf.__version__+' / svgelements '+version('svgelements')}
