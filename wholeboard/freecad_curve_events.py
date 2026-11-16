"""Bounded native Bézier-span roots and one-sided curvature limits, in millimeters."""
import math

def xyz(p):return [float(p.x),float(p.y),float(p.z)]
def add(a,b):return [x+y for x,y in zip(a,b)]
def sub(a,b):return [x-y for x,y in zip(a,b)]
def scale(a,s):return [x*s for x in a]
def dot(a,b):return sum(x*y for x,y in zip(a,b))
def cross(a,b):return [a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]]
def norm(a):return math.sqrt(dot(a,a))
def psum(a,b,sign=1):return [(a[i] if i<len(a) else 0)+sign*(b[i] if i<len(b) else 0) for i in range(max(len(a),len(b)))]
def pmul(a,b):
    result=[0.]*(len(a)+len(b)-1)
    for i,x in enumerate(a):
        for j,y in enumerate(b):result[i+j]+=x*y
    return result
def deriv(p):return [i*p[i] for i in range(1,len(p))] or [0.]
def value(p,t):
    result=0.
    for n in reversed(p):result=result*t+n
    return result
def power(control):
    n=len(control)-1
    return [sum(control[i]*math.comb(n,i)*math.comb(n-i,k-i)*(-1)**(k-i) for i in range(k+1)) for k in range(n+1)]
def unique(values,tolerance=1e-8):
    result=[]
    for v in sorted(values):
        if not result or abs(v-result[-1])>tolerance:result.append(v)
    return result
def roots(poly,budget):
    budget['remaining']-=1
    if budget['remaining']<0:raise ValueError('Curve event evaluation budget reached.')
    magnitude=max(abs(n) for n in poly)
    if magnitude<1e-20:return []
    p=[n/magnitude for n in poly]
    while len(p)>1 and abs(p[-1])<1e-13:p.pop()
    if len(p)==1:return []
    if len(p)==2:return [-p[0]/p[1]] if 0<=-p[0]/p[1]<=1 else []
    cuts=unique([0.,1.]+roots(deriv(p),budget));found=[t for t in cuts if abs(value(p,t))<1e-10]
    for a,b in zip(cuts,cuts[1:]):
        fa,fb=value(p,a),value(p,b)
        if fa*fb>=0:continue
        for _ in range(48):
            middle=(a+b)/2;fm=value(p,middle)
            if fa*fm<=0:b=middle
            else:a=middle;fa=fm
        found.append((a+b)/2)
    return unique(found)

def plane(poles):
    origin=poles[0];vectors=[sub(p,origin) for p in poles];length=max([norm(v) for v in vectors]+[1.])
    first=next((v for v in vectors if norm(v)>length*1e-12),None)
    if first is None:return True,None
    normal=next((cross(first,v) for v in vectors if norm(cross(first,v))>length*length*1e-12),None)
    if normal is None:return True,None
    normal=scale(normal,1/norm(normal));axis=max(range(3),key=lambda i:abs(normal[i]))
    if normal[axis]<0:normal=scale(normal,-1)
    return all(abs(dot(v,normal))<=length*1e-9 for v in vectors),normal

def span(curve,a,b):
    c=curve.copy()
    c.segment(a,b)
    poles=[xyz(p) for p in c.getPoles()];weights=list(c.getWeights()) if hasattr(c,'getWeights') else [1.]*len(poles)
    if not 2<=len(poles)<=11 or any(w<=0 or not math.isfinite(w) for w in weights):raise ValueError('Unsupported curve degree or homogeneous weights.')
    origin=poles[0];maximum=max(weights);weights=[w/maximum for w in weights]
    w=power(weights);p=[power([(point[j]-origin[j])*weight for point,weight in zip(poles,weights)]) for j in range(3)]
    velocity=[psum(pmul(deriv(axis),w),pmul(axis,deriv(w)),-1) for axis in p]
    return {'a':a,'b':b,'origin':origin,'w':w,'p':p,'velocity':velocity,'poles':poles}

def state(s,t):
    w=value(s['w'],t);dw=value(deriv(s['w']),t)
    if abs(w)<1e-14:return None
    a=[value(axis,t) for axis in s['velocity']];da=[value(deriv(axis),t) for axis in s['velocity']]
    v=scale(a,1/w**2);speed=norm(v)
    if speed<1e-9:return None
    acceleration=[(x*w-2*y*dw)/w**3 for x,y in zip(da,a)]
    tangent=scale(v,1/speed);curvature=scale(sub(acceleration,scale(tangent,dot(acceleration,tangent))),1/speed**2)
    return {'point':add(s['origin'],[value(axis,t)/w for axis in s['p']]),'tangent':tangent,'vector':curvature,'curvature':norm(curvature)}

def native_state(edge,t):
    point,v,a=edge.Curve.getD2(t);v=xyz(v);a=xyz(a);speed=norm(v)
    if speed<1e-9:return None
    tangent=scale(v,1/speed);curvature=scale(sub(a,scale(tangent,dot(a,tangent))),1/speed**2)
    return {'point':xyz(point),'tangent':tangent,'vector':curvature,'curvature':norm(curvature)}

def compare_limits(left,right,point,origin,**identity):
    if left is None or right is None:return {'kind':'singular','point':sub(point,origin),**identity}
    cosine=max(-1.,min(1.,dot(left['tangent'],right['tangent'])));angle=math.degrees(math.acos(cosine))
    delta=norm(sub(left['vector'],right['vector']));kind='tangent_break' if cosine<1-1e-10 else 'curvature_jump' if delta>1e-7*(1+max(left['curvature'],right['curvature'])) else None
    if kind is None:return None
    return {'kind':kind,'point':sub(point,origin),'tangent_angle_deg':angle,
            'curvature_left':left['curvature'],'curvature_right':right['curvature'],'curvature_delta':delta,
            'vector_left':left['vector'],'vector_right':right['vector'],**identity}

def analyse_edge(edge,origin,budget):
    result={'schema':1,'available':False,'complete':False,'method':'native-bezier-polynomial-and-one-sided-limits',
            'inflections_available':False,'jumps_available':False,'events':[],
            'scope':'Numerical planar Bézier-span roots and native knot limits, not a formal global continuity proof. Stationary points and corners are separate from inflections/jumps.'}
    try:
        curve=edge.Curve;kind=type(curve).__name__;a,b=edge.FirstParameter,edge.LastParameter
        if not math.isfinite(a+b) or b<=a:raise ValueError('Invalid native parameter interval.')
        if kind in ('Line','LineSegment','Circle','Ellipse','Hyperbola','Parabola'):
            result.update(available=True,complete=True,inflections_available=True,jumps_available=True,span_count=1)
            return result
        if kind not in ('BSplineCurve','BezierCurve'):raise ValueError('Curve type has no bounded Bézier analysis.')
        cuts=unique([a,b]+[k for k in curve.getKnots() if a<k<b]) if kind=='BSplineCurve' else [a,b]
        if len(cuts)>129:raise ValueError('Curve exceeds128 native knot spans.')
        spans=[span(curve,x,y) for x,y in zip(cuts,cuts[1:])]
        planar,normal=plane([point for s in spans for point in s['poles']])
        events=[]
        for s in spans:
            velocity=s['velocity'];axis=max(velocity,key=lambda p:max(abs(n) for n in p))
            stationary=roots(axis,budget)
            f=[0.]
            if planar and normal:
                d=[deriv(p) for p in velocity]
                cross_poly=[psum(pmul(velocity[1],d[2]),pmul(velocity[2],d[1]),-1),psum(pmul(velocity[2],d[0]),pmul(velocity[0],d[2]),-1),psum(pmul(velocity[0],d[1]),pmul(velocity[1],d[0]),-1)]
                for j in range(3):f=psum(f,[v*normal[j] for v in cross_poly[j]])
            candidates=unique(roots(f,budget)+stationary)
            for i,t in enumerate(candidates):
                if not 1e-9<t<1-1e-9:continue
                parameter=s['a']+(s['b']-s['a'])*t;at=state(s,t);point=xyz(edge.valueAt(parameter))
                if at is None:
                    events.append({'kind':'singular','parameter':parameter,'point':sub(point,origin)});continue
                if not planar or normal is None:continue
                gap=min(t,1-t,abs(t-candidates[i-1]) if i else 1,abs(candidates[i+1]-t) if i+1<len(candidates) else 1)
                step=min(1e-4,gap/4);left,right=state(s,t-step),state(s,t+step)
                if not left or not right:continue
                signed_left=dot(cross(left['tangent'],left['vector']),normal);signed_right=dot(cross(right['tangent'],right['vector']),normal)
                verified=native_state(edge,parameter)
                if signed_left*signed_right<0 and at['curvature']<1e-7 and verified and verified['curvature']<1e-7:
                    events.append({'kind':'inflection','parameter':parameter,'point':sub(point,origin),'signed_left':signed_left,'signed_right':signed_right,
                                   'bracket':[s['a']+(s['b']-s['a'])*(t-step),s['a']+(s['b']-s['a'])*(t+step)],'curvature_residual':verified['curvature'],'native_derivative_verified':True})
        for left,right in zip(spans,spans[1:]):
            t=left['b'];l,r=state(left,1),state(right,0);point=xyz(edge.valueAt(t));event=compare_limits(l,r,point,origin,parameter=t,location='internal-knot')
            if event:events.append(event)
            elif planar and normal and l and r and max(l['curvature'],r['curvature'])<1e-7:
                ll,rr=state(left,1-1e-4),state(right,1e-4)
                if ll and rr:
                    sl=dot(cross(ll['tangent'],ll['vector']),normal);sr=dot(cross(rr['tangent'],rr['vector']),normal)
                    if sl*sr<0:events.append({'kind':'inflection','parameter':t,'point':sub(point,origin),'signed_left':sl,'signed_right':sr,'location':'knot','curvature_residual':max(l['curvature'],r['curvature'])})
        if edge.isClosed():
            l,r=state(spans[-1],1),state(spans[0],0);event=compare_limits(l,r,xyz(edge.valueAt(a)),origin,parameter=a,location='closed-seam')
            if event:events.append(event)
        events.sort(key=lambda e:(e['parameter'],e['kind']))
        result.update(available=True,complete=planar,inflections_available=planar,jumps_available=True,plane_normal=normal if planar else None,span_count=len(spans),events=events)
        if not planar:result['reason']='Spatial curve inflections are not inferred from a projected curvature sign.'
    except Exception as error:result['reason']=str(error)
    return result

def analyse_joins(shape,origin,edges,budget):
    result={'schema':1,'available':True,'complete':True,'method':'native-wire-adjacency-and-endpoint-limits','events':[]}
    buckets={}
    for i,edge in enumerate(edges):buckets.setdefault(edge.hashCode(),[]).append((i,edge))
    seen=set()
    for wire in shape.Wires:
        items=wire.OrderedEdges
        if len(items)<2:continue
        pairs=list(zip(items,items[1:]))+([(items[-1],items[0])] if wire.isClosed() else [])
        for one,two in pairs:
            budget['remaining']-=1
            if budget['remaining']<0:result.update(complete=False,reason='Wire event budget reached.');return result
            i=next((i for i,e in buckets.get(one.hashCode(),[]) if e.isSame(one)),None);j=next((i for i,e in buckets.get(two.hashCode(),[]) if e.isSame(two)),None)
            if i is None or j is None or i==j:continue
            candidates=[]
            for side,t in enumerate((edges[i].FirstParameter,edges[i].LastParameter)):
                for other,u in enumerate((edges[j].FirstParameter,edges[j].LastParameter)):
                    p,q=xyz(edges[i].valueAt(t)),xyz(edges[j].valueAt(u));candidates.append((norm(sub(p,q)),side,other,t,u,p))
            distance,side,other,t,u,point=min(candidates,key=lambda c:c[0])
            if distance>1e-6:continue
            key=(min(i,j),max(i,j),tuple(round(n,6) for n in point))
            if key in seen:continue
            seen.add(key)
            try:
                l,r=native_state(edges[i],t),native_state(edges[j],u)
                if l and side==0:l={**l,'tangent':scale(l['tangent'],-1)}
                if r and other==1:r={**r,'tangent':scale(r['tangent'],-1)}
                event=compare_limits(l,r,point,origin,edge_indices=[i,j],location='wire-join')
                if event:result['events'].append(event)
            except Exception:result['complete']=False
    return result
