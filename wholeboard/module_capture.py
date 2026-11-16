"""Capture a PCB region without flattening circular traces or filling zone cutouts."""
from __future__ import annotations
import copy
import math
import uuid
from shapely.geometry import Polygon,LineString,Point,box
from . import sexpr
from .sexpr import S,Sym,find,find_all,num,tag

EPS=1e-7


def native_copper(geometry):
    groups={};origin=geometry.get('bbox',[100,100])[:2]
    for kind,coordinates in (('tracks',('a','b')),('arcs',('a','m','b')),('vias',('p',))):
        for item in geometry.get(kind,[]):
            group=groups.setdefault(item['net'],{'net':item['net'],'tracks':[],'arcs':[],'vias':[]});copied=copy.deepcopy(item)
            for field in coordinates:copied[field]=[round(item[field][i]-origin[i],6) for i in range(2)]
            group[kind].append(copied)
    return list(groups.values()),copy.deepcopy(geometry.get('zone_sources',[]))


def _parts(geometry,kind):
    if geometry.is_empty:return []
    if geometry.geom_type==kind:return [geometry]
    return [part for child in getattr(geometry,'geoms',[]) for part in _parts(child,kind)]


def _arc_circle(arc):
    (ax,ay),(mx,my),(bx,by)=arc['a'],arc['m'],arc['b'];d=2*(ax*(my-by)+mx*(by-ay)+bx*(ay-my))
    if abs(d)<1e-10:raise ValueError('A circular trace has collinear arc points; repair it before module capture.')
    aa,mm,bb=ax*ax+ay*ay,mx*mx+my*my,bx*bx+by*by
    center=((aa*(my-by)+mm*(by-ay)+bb*(ay-my))/d,(aa*(bx-mx)+mm*(ax-bx)+bb*(mx-ax))/d)
    radius=math.dist(center,arc['a']);angles=[math.atan2(p[1]-center[1],p[0]-center[0]) for p in (arc['a'],arc['m'],arc['b'])]
    norm=lambda angle:angle%(2*math.pi)
    start,middle,end=angles;direction=1 if norm(middle-start)<=norm(end-start) else -1
    return center,radius,start,direction,norm((end-start)*direction)


def clip_arc(arc,mask):
    """Split at exact circle/boundary intersections, retaining real arc primitives."""
    center,radius,start,direction,span=_arc_circle(arc);cuts=[0,span]
    for boundary in _parts(mask.boundary,'LineString')+_parts(mask.boundary,'LinearRing'):
        coords=list(boundary.coords)
        for a,b in zip(coords,coords[1:]):
            dx,dy=b[0]-a[0],b[1]-a[1];px,py=a[0]-center[0],a[1]-center[1]
            A=dx*dx+dy*dy;B=2*(px*dx+py*dy);C=px*px+py*py-radius*radius
            discriminant=B*B-4*A*C
            if A<EPS or discriminant<-EPS:continue
            for fraction in ((-B+math.sqrt(max(0,discriminant)))/(2*A),(-B-math.sqrt(max(0,discriminant)))/(2*A)):
                if -EPS<=fraction<=1+EPS:
                    angle=math.atan2(a[1]+fraction*dy-center[1],a[0]+fraction*dx-center[0]);t=((angle-start)*direction)%(2*math.pi)
                    if EPS<t<span-EPS:cuts.append(t)
    cuts=sorted(set(round(value,12) for value in cuts))
    point=lambda t:[center[0]+radius*math.cos(start+direction*t),center[1]+radius*math.sin(start+direction*t)]
    intervals=[]
    for lo,hi in zip(cuts,cuts[1:]):
        if hi-lo>EPS and mask.covers(Point(point((lo+hi)/2))):
            if intervals and abs(intervals[-1][1]-lo)<EPS:intervals[-1]=(intervals[-1][0],hi)
            else:intervals.append((lo,hi))
    out=[]
    for lo,hi in intervals:
        if abs(lo)<EPS and abs(hi-span)<EPS:out.append(copy.deepcopy(arc));continue
        item=copy.deepcopy(arc);item['id']=str(uuid.uuid4());item.update(a=point(lo),m=point((lo+hi)/2),b=point(hi));out.append(item)
    return out


def _zone_shape(node,origin):
    rings=[]
    for polygon in find_all(node,'polygon'):
        pts=find(polygon,'pts') or []
        if any(tag(p)!='xy' for p in pts[1:]):raise ValueError('Curved zone outlines need explicit conversion before selection clipping; the source PCB was not changed.')
        rings.append([(num(p[1])-origin[0],num(p[2])-origin[1]) for p in pts[1:]])
    shape=Polygon(rings[0],rings[1:]) if rings else Polygon()
    if not shape.is_valid:raise ValueError('A zone outline is invalid; repair its contours before module capture.')
    return shape


def clip_zone(zone,mask,anchor):
    node=sexpr.parse(zone['source']);shape=_zone_shape(node,zone['origin']);clipped=shape.intersection(mask);out=[]
    for polygon in _parts(clipped,'Polygon'):
        if polygon.area<EPS:continue
        tree=copy.deepcopy(node);tree[:]=[child for child in tree if tag(child) not in {'polygon','filled_polygon','fill_segments','uuid'}]
        identifier=str(uuid.uuid4());tree.append(S(Sym('uuid'),identifier))
        for ring in [polygon.exterior,*polygon.interiors]:
            points=[S(Sym('xy'),round(x-anchor[0],6),round(y-anchor[1],6)) for x,y in list(ring.coords)[:-1]]
            tree.append(S(Sym('polygon'),S(Sym('pts'),*points)))
        out.append({**copy.deepcopy(zone),'id':identifier,'origin':[0,0],'source':sexpr.dumps(tree)})
    return out,not shape.equals(clipped)


def capture(geometry,refs,nets,*,bounds=None,margin=.5,internal_nets=None):
    internal_nets=set(internal_nets or [])
    origin=geometry.get('bbox',[100,100])[:2];footprints={fp['ref']:fp for fp in geometry.get('footprints',[])}
    if set(refs)-footprints.keys():raise ValueError('Every selected component needs native footprint geometry before conversion.')
    courts={}
    for ref,fp in footprints.items():
        court=fp.get('court')
        if court:courts[ref]=[court[0]-origin[0],court[1]-origin[1],court[2]-origin[0],court[3]-origin[1]]
        else:
            pads=[p for p in geometry.get('pads',[]) if p['ref']==ref]
            courts[ref]=[min([p['x']-p['w']/2 for p in pads]+[fp['x']])-origin[0],min([p['y']-p['h']/2 for p in pads]+[fp['y']])-origin[1],max([p['x']+p['w']/2 for p in pads]+[fp['x']])-origin[0],max([p['y']+p['h']/2 for p in pads]+[fp['y']])-origin[1]]
    groups,zones=native_copper(geometry)
    if not refs:
        bounds=[0,0,5,5] if bounds is None else bounds;groups=[];zones=[]
    if bounds is None:
        extents=[courts[ref] for ref in refs]
        for group in groups:
            if group['net'] not in internal_nets:continue
            for item in group.get('tracks',[]):extents.append([min(item['a'][0],item['b'][0])-item['w']/2,min(item['a'][1],item['b'][1])-item['w']/2,max(item['a'][0],item['b'][0])+item['w']/2,max(item['a'][1],item['b'][1])+item['w']/2])
            for item in group.get('arcs',[]):
                (x,y),radius,*_=_arc_circle(item);radius+=item['w']/2;extents.append([x-radius,y-radius,x+radius,y+radius])
            for item in group.get('vias',[]):
                x,y=item['p'];r=item['d']/2;extents.append([x-r,y-r,x+r,y+r])
        for zone in zones:
            if zone['net'] in internal_nets:extents.append(list(_zone_shape(sexpr.parse(zone['source']),zone['origin']).bounds))
        bounds=[min(value[0] for value in extents)-margin,min(value[1] for value in extents)-margin,max(value[2] for value in extents)+margin,max(value[3] for value in extents)+margin]
        for axis in (0,1):
            if bounds[axis+2]-bounds[axis]<5:
                delta=(5-bounds[axis+2]+bounds[axis])/2;bounds[axis]-=delta;bounds[axis+2]+=delta
    if not isinstance(bounds,list) or len(bounds)!=4 or any(not isinstance(v,(int,float)) or isinstance(v,bool) or not math.isfinite(v) or abs(v)>10000 for v in bounds) or bounds[0]>=bounds[2] or bounds[1]>=bounds[3]:raise ValueError('Capture bounds need a finite rectangle [left,top,right,bottom].')
    bounds=[round(v,6) for v in bounds];region=box(*bounds);mask=region;anchor=bounds[:2]
    if any(not region.buffer(EPS).covers(box(*courts[ref])) for ref in refs):raise ValueError('Capture bounds must contain the selected footprints completely.')
    excluded=[]
    for ref,court in courts.items():
        if ref not in refs and region.intersection(box(*court)).area>EPS:
            mask=mask.difference(box(*court).buffer(.2,join_style=2));excluded.append(ref)
    external_mask=mask;kept=[];report={'bounds':bounds,'origin':anchor,'excluded_components':sorted(excluded),'clipped_tracks':0,'clipped_arcs':0,'clipped_zones':0,'omitted_vias':0}
    for group in groups:
        if group['net'] not in nets:continue
        mask=region if group['net'] in internal_nets else external_mask
        result={'net':group['net'],'tracks':[],'arcs':[],'vias':[]}
        for track in group.get('tracks',[]):
            line=LineString([track['a'],track['b']]);pieces=_parts(line.intersection(mask),'LineString')
            if not mask.covers(line):report['clipped_tracks']+=1
            for piece in sorted(pieces,key=lambda value:line.project(Point(value.coords[0]))):
                if piece.length<EPS:continue
                item=copy.deepcopy(track);item['a']=list(piece.coords[0]);item['b']=list(piece.coords[-1]);
                if len(pieces)!=1 or not mask.covers(line):item['id']=str(uuid.uuid4())
                result['tracks'].append(item)
        for arc in group.get('arcs',[]):
            pieces=clip_arc(arc,mask)
            if len(pieces)!=1 or any(pieces[0][k]!=arc[k] for k in ('a','m','b')):report['clipped_arcs']+=1
            result['arcs'].extend(pieces)
        for via in group.get('vias',[]):
            p=Point(via['p'])
            if mask.covers(p) and p.distance(mask.boundary)>=via['d']/2-EPS:result['vias'].append(copy.deepcopy(via))
            else:report['omitted_vias']+=1
        for kind,coordinates in (('tracks',('a','b')),('arcs',('a','m','b')),('vias',('p',))):
            for item in result[kind]:
                item['net']=group['net']
                for field in coordinates:item[field]=[round(item[field][i]-anchor[i],6) for i in (0,1)]
        if any(result[k] for k in ('tracks','arcs','vias')):kept.append(result)
    kept_zones=[]
    for zone in zones:
        if zone['net'] not in nets and zone['net']:continue
        mask=region if zone['net'] in internal_nets else external_mask
        pieces,clipped=clip_zone(zone,mask,anchor);kept_zones.extend(pieces);report['clipped_zones']+=int(clipped)
    report['counts']={kind:sum(len(group[kind]) for group in kept) for kind in ('tracks','arcs','vias')};report['counts']['zones']=len(kept_zones)
    return kept,kept_zones,report
