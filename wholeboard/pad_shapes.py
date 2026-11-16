"""Bounded SVG/DXF copper profiles and native custom-pad geometry.

The editable origin is the copper bounds center. Native custom pads need a small
interior anchor, which must never fill a notch or a hole in the requested shape.
"""
from __future__ import annotations
import copy,functools,hashlib,json,math
import xml.etree.ElementTree as XML
from pathlib import Path
import numpy as np
from shapely import constrained_delaunay_triangles,union_all
from shapely.geometry import Polygon,Point,LineString
from shapely.affinity import scale,translate
from . import sexpr

POINT_LIMIT=12000
SOURCE_LIMIT=500000
UNITS={'mm','cm','m','in','px','auto'}


def finite(n,limit=20000):return isinstance(n,(int,float)) and not isinstance(n,bool) and math.isfinite(n) and abs(n)<=limit


def _bezier(poles,t):
    value=np.asarray(poles,dtype=float)
    while len(value)>1:value=value[:-1]*(1-t)+value[1:]*t
    return value[0].tolist()


def _edge_points(edge,tolerance):
    kind=edge['kind']
    if kind=='line':points=[edge['start'],edge['end']]
    elif kind=='ellipse':
        a,b=edge['axis_x'],edge['axis_y'];start,sweep=edge['t0'],edge['sweep'];radius=max(math.hypot(*a),math.hypot(*b));step=2*math.acos(max(-1,1-min(tolerance/max(radius,1e-12),1)));n=max(4,math.ceil(abs(sweep)/max(step,1e-6)))
        if n>POINT_LIMIT:raise ValueError('Custom pad exceeds the curve point budget.')
        values={i/n for i in range(n+1)}
        for axis in (0,1):
            critical=math.atan2(b[axis],a[axis])
            for k in range(-4,5):
                t=(critical+k*math.pi-start)/sweep
                if 0<t<1:values.add(t)
        points=[[edge['center'][j]+a[j]*math.cos(start+sweep*t)+b[j]*math.sin(start+sweep*t) for j in range(3)] for t in sorted(values)]
    elif kind=='bezier':
        poles=edge['poles'];values={0.,1.}
        def flatten(p,t0,t1,depth=0):
            first,last=np.asarray(p[0]),np.asarray(p[-1]);d=last-first;length=np.linalg.norm(d);error=max(np.linalg.norm(np.cross(np.asarray(v)-first,d))/length if length>1e-12 else np.linalg.norm(np.asarray(v)-first) for v in p)
            if error<=tolerance/2:values.add(t0);return
            if depth>=24 or len(values)>POINT_LIMIT:raise ValueError('Custom pad exceeds the Bezier point budget.')
            levels=[np.asarray(p)]
            while len(levels[-1])>1:levels.append((levels[-1][:-1]+levels[-1][1:])/2)
            middle=(t0+t1)/2;flatten([v[0].tolist() for v in levels],t0,middle,depth+1);flatten([v[-1].tolist() for v in reversed(levels)],middle,t1,depth+1)
        flatten(poles,0.,1.)
        for axis in (0,1):
            v=[p[axis] for p in poles]
            coefficients=[-v[0]+3*v[1]-3*v[2]+v[3],2*(v[0]-2*v[1]+v[2]),v[1]-v[0]] if len(v)==4 else [v[0]-2*v[1]+v[2],v[1]-v[0]]
            for t in np.roots(np.trim_zeros(coefficients,'f')):
                if abs(t.imag)<1e-10 and 0<t.real<1:values.add(float(t.real))
        points=[_bezier(poles,t) for t in sorted(values)]
    elif kind=='bspline':
        from ezdxf.math import BSpline
        points=[list(v) for v in BSpline(edge['poles'],order=edge['degree']+1,knots=edge['knots'],weights=edge.get('weights') or None).flattening(tolerance,segments=4)]
        if len(points)>POINT_LIMIT:raise ValueError('Custom pad exceeds the spline point budget.')
    else:raise ValueError('Unsupported custom pad curve: '+str(kind))
    return list(reversed(points)) if edge.get('reverse') else points


def _ring(edges,tolerance,flip_y):
    points=[]
    for edge in edges:
        values=_edge_points(edge,tolerance)
        for value in values[:-1]:points.append([value[0],-value[1] if flip_y else value[1]])
        if len(points)>POINT_LIMIT:raise ValueError('Custom pad exceeds the polygon point budget.')
    if len(points)<3:raise ValueError('A custom pad needs a closed nonzero area.')
    return points


def _polygons(value):
    if not isinstance(value,list) or not value or len(value)>POINT_LIMIT:raise ValueError('Custom pad polygons need bounded coordinate arrays.')
    out=[];count=0
    for item in value:
        rings=[item['outer'],*item.get('holes',[])] if isinstance(item,dict) and 'outer' in item else [item]
        for ring in rings:
            if not isinstance(ring,list) or len(ring)<3 or any(not isinstance(p,list) or len(p)!=2 or not all(finite(n) for n in p) for p in ring):raise ValueError('Custom pad vertices need finite two-coordinate points.')
            count+=len(ring)
        if count>POINT_LIMIT:raise ValueError('Custom pad exceeds the polygon point budget.')
        poly=Polygon(rings[0],rings[1:])
        if not poly.is_valid or poly.area<1e-10:raise ValueError('Custom pad polygons must have valid nonzero filled regions.')
        out.append(poly)
    return union_all(out)


def _finish(shape,tolerance):
    if shape.geom_type!='Polygon' or not shape.is_valid or shape.area<1e-10:raise ValueError('Use one connected copper region per custom pad; use separate pads for disconnected regions.')
    x0,y0,x1,y1=shape.bounds;center=[(x0+x1)/2,(y0+y1)/2];shape=translate(shape,-center[0],-center[1]);triangles=[g for g in constrained_delaunay_triangles(shape).geoms if not g.is_empty]
    if len(triangles)*3>POINT_LIMIT:raise ValueError('Custom pad triangulation exceeds the point budget.')
    polygons=[[[round(x,6),round(y,6)] for x,y in list(t.exterior.coords)[:-1]] for t in triangles]
    actual=_polygons(polygons)
    if shape.symmetric_difference(actual).area>max(1e-5,shape.length*1e-6):raise ValueError('Native coordinate precision cannot retain this custom pad.')
    anchor=actual.representative_point();clearance=anchor.distance(actual.boundary)
    if clearance<2e-6:raise ValueError('Custom pad has no interior room for a native anchor.')
    contours=[[[round(x,6),round(y,6)] for x,y in list(r.coords)[:-1]] for r in [actual.exterior,*actual.interiors]]
    return {'polygons':polygons,'contours':contours,'width_mm':round(x1-x0,6),'height_mm':round(y1-y0,6),'area_mm2':actual.area,'source_center_mm':center,'anchor':[round(anchor.x,6),round(anchor.y,6)],'anchor_diameter_mm':max(.000002,min(.05,clearance*.5)),'approximation_tolerance_mm':tolerance,'method':'SVG/DXF curves flattened within declared tolerance; constrained filled-region triangulation retains holes'}


@functools.lru_cache(maxsize=128)
def _compiled(encoded,width,height):
    source=json.loads(encoded);units=source.get('units','mm');tolerance=source.get('tolerance_mm',.001)
    if units not in UNITS or not finite(tolerance,1) or not .000001<=tolerance<=.1:raise ValueError('Choose declared drawing units and a curve tolerance from0.000001to0.1mm.')
    if source.get('fill_rule','nonzero') not in {'nonzero','evenodd'}:raise ValueError('Choose nonzero or evenodd SVG fill winding.')
    if (width is None)!=(height is None) or width is not None and (not finite(width,100) or not finite(height,100) or min(width,height)<=0):raise ValueError('Custom pad width/height must be finite and positive.')
    keys=[key for key in ('path','svg','dxf','polygons') if key in source]
    if len(keys)!=1:raise ValueError('Choose exactly one SVG path, SVG/DXF document or polygon source.')
    if keys[0]=='polygons':shape=_polygons(source['polygons']);profiles=None
    else:
        from . import drawing_assets
        key=keys[0];text=source[key]
        if not isinstance(text,str) or not text.strip() or len(text)>SOURCE_LIMIT:raise ValueError('Use a bounded vector source under500000characters.')
        if key=='path':
            root=XML.Element('svg',xmlns='http://www.w3.org/2000/svg');XML.SubElement(root,'path',d=text,**{'fill-rule':source.get('fill_rule','nonzero')});raw=XML.tostring(root)
        else:raw=text.encode()
        drawing=drawing_assets.convert('pad.'+('dxf' if key=='dxf' else 'svg'),raw,units=units,drawing_mode='outline' if key=='dxf' else 'fill')
        if drawing['diagnostics']['ignored'] or drawing['diagnostics']['issues'] or drawing['references']:raise ValueError('Convert visible strokes, text and unsupported drawing elements to closed filled outlines before using a pad shape.')
        profiles=drawing['profiles'];flip=True
        def sample(tol):return union_all([Polygon(_ring(p['outer'],tol,flip),[_ring(h,tol,flip) for h in p['holes']]) for p in profiles])
        shape=sample(.0001)
    if shape.geom_type!='Polygon' or not shape.is_valid:raise ValueError('Use one valid connected copper region per custom pad.')
    x0,y0,x1,y1=shape.bounds
    if min(x1-x0,y1-y0)<1e-8:raise ValueError('Custom copper must have positive width and height.')
    sx,sy=(width/(x1-x0),height/(y1-y0)) if width is not None else (1,1)
    if profiles is not None:shape=sample(min(.0001,tolerance/max(sx,sy)))
    shape=scale(shape,xfact=sx,yfact=sy,origin=(0,0));return _finish(shape,tolerance)


def compile_shape(source,width=None,height=None):
    if not isinstance(source,dict):raise ValueError('A custom pad needs a vector-source object.')
    try:encoded=json.dumps(source,sort_keys=True,allow_nan=False)
    except (ValueError,TypeError):raise ValueError('Custom shape values must be finite JSON data.') from None
    if len(encoded)>SOURCE_LIMIT:raise ValueError('Custom pad source exceeds its size budget.')
    return copy.deepcopy(_compiled(encoded,width,height))


def material(pad):return _polygons(compile_shape(pad.get('custom_shape'),pad['w'],pad['h'])['polygons'])


def describe_pad(pad):
    result=compile_shape(pad.get('custom_shape'),pad['w'],pad['h']);result['conductive']=pad.get('kind')!='np_thru_hole' or pad.get('npth_copper') is True
    return result


def unplated_surface(node,custom=None):
    """NPTH describes the barrel; a native washer can still carry surface copper."""
    find,num=sexpr.find,sexpr.num;layers=find(node,'layers') or []
    if not any(str(v).endswith('.Cu') for v in layers[1:]):return {'has_copper':False}
    size=find(node,'size');w,h=num(size[1]),num(size[2]);shape=str(node[3]);radius=min(w,h)/2
    if custom:region=_polygons(custom['polygons']);center=custom['source_center_mm']
    else:
        center=[0,0]
        if shape=='circle':region=Point(0,0).buffer(w/2,quad_segs=128)
        elif shape=='oval':region=LineString([[-w/2+radius,0],[w/2-radius,0]] if w>=h else [[0,-h/2+radius],[0,h/2-radius]]).buffer(radius,quad_segs=128)
        elif shape=='roundrect':
            ratio=find(node,'roundrect_rratio');r=min(w,h)*(num(ratio[1]) if ratio else .25);region=Polygon([[-w/2+r,-h/2+r],[w/2-r,-h/2+r],[w/2-r,h/2-r],[-w/2+r,h/2-r]]).buffer(r,quad_segs=128)
        else:region=Polygon([[-w/2,-h/2],[w/2,-h/2],[w/2,h/2],[-w/2,h/2]])
    drill=find(node,'drill');oval=drill and str(drill[1])=='oval';values=[num(v) for v in (drill[2:] if oval else drill[1:]) if not isinstance(v,list)];dimensions=[values[0],values[1] if oval else values[0]];off=find(drill,'offset');offset=[-num(off[i+1])-center[i] for i in range(2)] if off else [-v for v in center];r=min(dimensions)/2;ends=[max(0,v/2-r) for v in dimensions]
    hole=LineString([[offset[i]+sign*ends[i] for i in range(2)] for sign in (-1,1)]).buffer(r,quad_segs=128);copper=region.difference(hole)
    if copper.area<1e-9:return {'has_copper':False}
    point=copper.representative_point();return {'has_copper':True,'contact':[point.x,point.y],'area_mm2':copper.area,'disconnected':copper.geom_type!='Polygon'}


def native_geometry(pad):
    """Read physical custom copper primitives in the native pad-shape frame."""
    find,num=sexpr.find,sexpr.num;primitives=find(pad,'primitives')
    if primitives is None:raise ValueError('Custom pad has no native copper primitives.')
    regions=[]
    def point(node):return [num(node[1]),num(node[2])]
    for primitive in primitives[1:]:
        tag=sexpr.tag(primitive);width=find(primitive,'width');width=num(width[1]) if width else 0;fill=find(primitive,'fill');filled=fill is not None and str(fill[1]) in ('yes','true')
        if tag=='gr_poly':
            pts=find(primitive,'pts');region=Polygon([point(p) for p in pts[1:] if sexpr.tag(p)=='xy'])
            if not region.is_valid:raise ValueError('Native custom polygon has unsupported invalid topology.')
            regions.append(region if filled or not width else region.boundary.buffer(width/2,quad_segs=32))
        elif tag in ('gr_rect','gr_circle'):
            a=point(find(primitive,'start' if tag=='gr_rect' else 'center'));b=point(find(primitive,'end'))
            region=Polygon([a,[b[0],a[1]],b,[a[0],b[1]]]) if tag=='gr_rect' else Point(a).buffer(math.dist(a,b),quad_segs=128)
            regions.append(region if filled else region.boundary.buffer(width/2,quad_segs=32))
        elif tag in ('gr_line','gr_arc','gr_curve'):
            if tag=='gr_line':points=[point(find(primitive,'start')),point(find(primitive,'end'))]
            elif tag=='gr_curve':
                poles=[[*point(p),0] for p in find(primitive,'pts')[1:] if sexpr.tag(p)=='xy'];points=[v[:2] for v in _edge_points({'kind':'bezier','poles':poles},.0001)]
            else:
                from .kicad.connectivity import _arc_spec
                a,m,b=[point(find(primitive,k)) for k in ('start','mid','end')];arc=_arc_spec({'a':a,'m':m,'b':b})
                if arc is None:points=[a,m,b]
                else:
                    count=max(2,math.ceil(arc['span']/max(1e-6,2*math.acos(max(-1,1-.0001/arc['radius'])))))
                    if count>POINT_LIMIT:raise ValueError('Native custom arc exceeds its point budget.')
                    points=[[arc['center'][j]+arc['radius']*(math.cos if j==0 else math.sin)(arc['start']+arc['direction']*arc['span']*i/count) for j in range(2)] for i in range(count+1)]
            if width<=0:raise ValueError('Native stroked custom primitives need positive width.')
            regions.append(LineString(points).buffer(width/2,quad_segs=32))
        else:raise ValueError('Unsupported native custom pad primitive: '+str(tag))
    size=find(pad,'size');options=find(pad,'options');anchor=find(options,'anchor') if options else None;w,h=num(size[1]),num(size[2])
    regions.append(Polygon([[-w/2,-h/2],[w/2,-h/2],[w/2,h/2],[-w/2,h/2]]) if anchor and str(anchor[1])=='rect' else Point(0,0).buffer(w/2,quad_segs=32))
    return _finish(union_all(regions),.0001)


def prepare(spec,args):
    from . import project_library
    footprint=args.get('footprint');index=args.get('pad_index');asset=project_library.asset(spec,'footprints','Project:'+str(footprint))
    if asset is None or type(index) is not int or not 0<=index<len(asset.get('pads',[])):raise ValueError('Choose a current project footprint and pad index.')
    shape=compile_shape(args.get('custom_shape'));out=copy.deepcopy(spec);pad=out['library']['footprints'][footprint]['pads'][index]
    pad.update(shape='custom',w=shape['width_mm'],h=shape['height_mm'],custom_shape=copy.deepcopy(args['custom_shape']))
    project_library.validate_asset('footprints',footprint,out['library']['footprints'][footprint]);shape['conductive']=pad.get('kind')!='np_thru_hole' or pad.get('npth_copper') is True;return{'spec':out,'shape_report':shape}
