"""Analytic line/arc meanders and parallel offsets; no PCB or source mutations."""
from __future__ import annotations

import math

from .module_capture import _arc_circle as arc_circle

EPS=1e-9


def _add(a,b):return [a[i]+b[i] for i in range(2)]
def _sub(a,b):return [a[i]-b[i] for i in range(2)]
def _mul(a,k):return [v*k for v in a]
def _cross(a,b):return a[0]*b[1]-a[1]*b[0]
def _normal(a):return [-a[1],a[0]]
def _unit(a):return _mul(a,1/math.hypot(*a))
def _round(a):return [round(v,9) for v in a]


def primitive_length(item):
    if item['kind']=='tracks':return math.dist(item['a'],item['b'])
    _,radius,_,_,sweep=arc_circle(item)
    return radius*sweep


def _vertices(length,height,style,pitch,loops,side):
    width=pitch if style=='sawtooth' else pitch/2
    gap=pitch/2;span=loops*width+(loops-1)*gap;start=(length-span)/2
    points=[[0.,0.]]
    for index in range(loops):
        x=start+index*(width+gap);h=height*side*(-1 if style=='accordion' and index%2 else 1)
        points.append([x,0.])
        if style=='sawtooth':points.extend([[x+width/2,h],[x+width,0.]])
        else:points.extend([[x,h],[x+width,h],[x+width,0.]])
    points.append([length,0.])
    return [p for i,p in enumerate(points) if not i or math.dist(p,points[i-1])>EPS]


def _curves(points,radius,offset=0):
    directions=[_unit(_sub(b,a)) for a,b in zip(points,points[1:])]
    turns=[0.]+[math.atan2(_cross(a,b),sum(x*y for x,y in zip(a,b))) for a,b in zip(directions,directions[1:])]+[0.]
    shifted=[_add(points[0],_mul(_normal(directions[0]),offset))]
    for i,vertex in enumerate(points[1:-1],1):
        before,after=directions[i-1],directions[i];a=_add(vertex,_mul(_normal(before),offset));b=_add(vertex,_mul(_normal(after),offset));den=_cross(before,after)
        if abs(den)<EPS:
            if sum(x*y for x,y in zip(before,after))<0:raise ValueError('A meander cannot reverse directly.')
            shifted.append(a)
        else:shifted.append(_add(a,_mul(before,_cross(_sub(b,a),after)/den)))
    shifted.append(_add(points[-1],_mul(_normal(directions[-1]),offset)))
    radii=[radius-(1 if turn>0 else -1)*offset for turn in turns]
    distances=[r*math.tan(abs(turn)/2) if abs(turn)>EPS else 0. for r,turn in zip(radii,turns)]
    for i,(a,b) in enumerate(zip(shifted,shifted[1:])):
        if distances[i]+distances[i+1]>math.dist(a,b)+1e-7:raise ValueError('The selected radius does not fit the meander pitch or height.')
    out=[];cursor=shifted[0]
    def line(end):
        nonlocal cursor
        if math.dist(cursor,end)>EPS:out.append({'kind':'tracks','a':_round(cursor),'b':_round(end)})
        cursor=end
    for i,vertex in enumerate(shifted[1:-1],1):
        turn=turns[i];r=radii[i];distance=distances[i];entry=_sub(vertex,_mul(directions[i-1],distance));exit=_add(vertex,_mul(directions[i],distance));line(entry)
        if abs(turn)>EPS and r>EPS:
            centre=_add(entry,_mul(_normal(directions[i-1]),math.copysign(r,turn)));angle=math.atan2(entry[1]-centre[1],entry[0]-centre[0]);middle=_add(centre,[r*math.cos(angle+turn/2),r*math.sin(angle+turn/2)])
            out.append({'kind':'arcs','a':_round(entry),'m':_round(middle),'b':_round(exit)});cursor=exit
    line(shifted[-1]);return out


def pattern(length,extra,*,style='trombone',radius=.5,pitch=3.,loops=1,side=1,offset=0.):
    """Return a horizontal meander adding exactly extra; offsets retain concentric real arcs."""
    numbers=(length,extra,radius,pitch,offset)
    if any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in numbers):raise ValueError('Meander dimensions must be finite numbers.')
    if length<=0 or length>10000 or extra<=0 or extra>10000 or radius<0 or pitch<=0:raise ValueError('Use positive bounded meander length, extra length and pitch, and a nonnegative radius.')
    if style not in ('trombone','accordion','sawtooth'):raise ValueError('Choose trombone, accordion or sawtooth meanders.')
    if type(loops) is not int or not 1<=loops<=32 or type(side) is not int or side not in (-1,1):raise ValueError('Use 1 to32 meander cells and a left/right side.')
    if offset and abs(offset)>=radius:raise ValueError('The pair offset needs a larger centreline radius.')
    width=pitch if style=='sawtooth' else pitch/2;span=loops*width+(loops-1)*pitch/2
    if (length-span)/2<radius+1e-7 or pitch<4*radius-1e-7:raise ValueError('The selected radius/cell count does not fit this trace.')
    def build(height,shift=0):return _curves(_vertices(length,height,style,pitch,loops,side),radius,shift)
    low=0. if style=='sawtooth' else 2*radius
    minimum=sum(primitive_length(p) for p in build(low))-length
    if extra<minimum-1e-6:raise ValueError('The requested added length is too small for this style and radius.')
    high=max(low+1,extra+4*radius)
    if sum(primitive_length(p) for p in build(high))-length<extra:raise ValueError('The requested length does not fit this meander.')
    for _ in range(48):
        height=(low+high)/2;value=sum(primitive_length(p) for p in build(height))-length
        if value<extra:low=height
        else:high=height
    height=(low+high)/2;primitives=build(height,offset);total=sum(primitive_length(p) for p in primitives)
    if abs(total-length-extra)>1e-5:raise ValueError('The meander could not meet the requested geometric length.')
    return {'primitives':primitives,'length_mm':total,'amplitude_mm':height,'radius_mm':radius,'pitch_mm':pitch,'loops':loops,'side':side}
