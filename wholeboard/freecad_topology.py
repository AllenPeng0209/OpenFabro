"""Native face/edge identities for viewport selection and guarded assembly references."""
import math
import FreeCAD as App
from freecad_curve_events import analyse_edge, analyse_joins


def xyz(value):return [float(value.x),float(value.y),float(value.z)]


def direction(value):
    vector=App.Vector(value)
    if vector.Length<1e-12:raise ValueError('Selected geometry has no reference direction.')
    vector.normalize();return [0. if abs(n)<1e-12 else n for n in xyz(vector)]


def geometry(element,entity):
    surface=element.Surface if entity=='face' else element.Curve;kind=type(surface).__name__
    result={'surface':kind,'point':xyz(element.CenterOfMass),'normal':None,'mate_kind':None}
    if entity=='face' and kind=='Plane':result.update(normal=direction(element.normalAt(0,0)),mate_kind='plane')
    elif kind in ('Cylinder','Cone') or entity=='edge' and kind=='Circle':
        result.update(point=xyz(surface.Center),normal=direction(surface.Axis),mate_kind='axis')
    elif entity=='edge' and element.Length>1e-9:
        result.update(normal=direction(element.tangentAt((element.FirstParameter+element.LastParameter)/2)),mate_kind='edge')
    return result


def signature(shape,element,entity):
    box=shape.optimalBoundingBox(False,False);point=element.CenterOfMass;details=geometry(element,entity)
    lower=[box.XMin,box.YMin,box.ZMin];size=[box.XLength,box.YLength,box.ZLength]
    return {'schema':1,'entity':entity,'surface':details['surface'],
            'position':[(value-start)/length if length>1e-9 else 0. for value,start,length in zip(xyz(point),lower,size)],
            'direction':details['normal'] or [0.,0.,0.],
            'edges':len(element.Edges) if entity=='face' else 1,'wires':len(element.Wires) if entity=='face' else int(element.isClosed())}


def verify_reference(shape,element,entity,expected):
    actual=signature(shape,element,entity)
    exact=('schema','entity','surface','edges','wires')
    if any(actual[key]!=expected[key] for key in exact) or any(abs(a-b)>1e-5 for key in ('position','direction') for a,b in zip(actual[key],expected[key])):
        raise ValueError('The selected native reference changed topology. Rebuild the preview and select it again.')


def curvature_samples(edge, origin, budget):
    """Evaluate the placed BRep curve, never fit curvature to preview triangles."""
    result = {'schema': 1, 'available': False, 'method': 'native-parametric', 'units': '1/mm',
              'sampling': 'uniform native parameter, up to 65 samples per edge', 'samples': []}
    if edge.Length <= 1e-9:
        return {**result, 'reason': 'Degenerate native edge.'}
    count = 2 if type(edge.Curve).__name__ in ('Line', 'LineSegment') else 65
    if budget['remaining'] < count:
        return {**result, 'reason': 'Scene curvature sample budget reached.'}
    budget['remaining'] -= count
    failures = 0
    for i in range(count):
        parameter = edge.FirstParameter + (edge.LastParameter-edge.FirstParameter)*i/(count-1)
        try:
            point = [n-origin[j] for j,n in enumerate(xyz(edge.valueAt(parameter)))]
            tangent = direction(edge.tangentAt(parameter))
            value = float(edge.curvatureAt(parameter))
            normal = direction(edge.normalAt(parameter)) if value > 1e-12 else [0., 0., 0.]
            if not all(math.isfinite(n) for n in point+tangent+normal+[value]) or value < 0:
                raise ValueError('Nonfinite native curve derivative.')
            result['samples'].append({'parameter': parameter, 'point': point, 'tangent': tangent,
                                      'normal': normal, 'curvature': value})
        except Exception:
            # A singular native derivative is an explicit gap, not zero curvature.
            result['samples'].append(None)
            failures += 1
    values = [v['curvature'] for v in result['samples'] if v is not None]
    result.update(available=bool(values), complete=not failures, singular_samples=failures,
                  minimum=min(values) if values else None, maximum=max(values) if values else None)
    if not values:
        result['reason'] = 'Native curve derivatives are unavailable.'
    return result


def surface_samples(face, vertices, face_index, origin, budget, *, faceted=False):
    """Evaluate native surface derivatives at tessellation vertices, before rounding."""
    result=[]
    surface=face.Surface
    for point in vertices:
        if faceted or budget['remaining']<=0:
            result.append(None)
            continue
        budget['remaining']-=1
        try:
            u,v=surface.parameter(point)
            normal=direction(face.normalAt(u,v))
            intrinsic=direction(surface.normal(u,v))
            sign=1 if sum(a*b for a,b in zip(normal,intrinsic))>0 else -1
            # FreeCAD's principal values use the underlying surface normal;
            # reverse them when the topological face points the other way.
            principal=sorted(sign*float(n) for n in face.curvatureAt(u,v))
            native=[n-origin[j] for j,n in enumerate(xyz(face.valueAt(u,v)))]
            if len(principal)!=2 or not all(math.isfinite(n) for n in [u,v]+normal+principal+native):
                raise ValueError('Native surface derivatives are nonfinite.')
            result.append({'face_index':face_index,'uv':[u,v],'point':native,'normal':normal,'principal':principal})
        except Exception:
            result.append(None)
    return result


def surface_summary(samples):
    valid=[sample for sample in samples if sample is not None]
    result={'method':'native-parametric','available':bool(valid),'complete':len(valid)==len(samples),
            'samples':len(samples),'valid_samples':len(valid),'unavailable_samples':len(samples)-len(valid),
            'curvature_units':'1/mm','gaussian_units':'1/mm^2',
            'convention':'Signed principal curvatures relative to oriented native face normal; convex outward surfaces are negative.'}
    if valid:
        for key,values in [('principal',[k for s in valid for k in s['principal']]),
                           ('mean',[sum(s['principal'])/2 for s in valid]),
                           ('gaussian',[s['principal'][0]*s['principal'][1] for s in valid])]:
            result[key+'_min']=min(values);result[key+'_max']=max(values)
    else:result['reason']='Native surface derivatives unavailable, singular, faceted or beyond the scene sample budget.'
    return result


def body_topology(body,origin,budget=None,event_budget=None):
    budget = budget if budget is not None else {'remaining': 50000}
    event_budget = event_budget if event_budget is not None else {'remaining':250000}
    selection=body.get('_selection') or {};local=selection.get('shape',body['shape']);world=body['shape'];faces=[];edges=[]
    if len(local.Faces)!=len(world.Faces) or len(local.Edges)!=len(world.Edges):raise ValueError('Assembly placement changed native reference topology.')
    for entity,source_elements,world_elements,result in [('face',local.Faces,world.Faces,faces),('edge',local.Edges,world.Edges,edges)]:
        for index,(source,placed) in enumerate(zip(source_elements,world_elements)):
            original=geometry(source,entity);rendered=geometry(placed,entity);selector=None
            if original['mate_kind']:
                selector={'kind':original['mate_kind'],'normal':original['normal'],'point':original['point'],'extreme':'nearest',
                          'index':index,'body_index':selection.get('body_index',body['body_id']),
                          'body_name':selection.get('body_name',body['name']),'reference':signature(local,source,entity)}
                instance=selection.get('body_instance') or body.get('native_instance')
                if instance:selector['body_instance']=instance
            item={'index':index,'surface':rendered['surface'],'point':rendered['point'],'normal':rendered['normal'],'selector':selector}
            curve=placed.Surface if entity=='face' else placed.Curve
            if hasattr(curve,'Radius'):item['radius_mm']=float(curve.Radius)
            item['area_mm2' if entity=='face' else 'length_mm']=float(placed.Area if entity=='face' else placed.Length)
            if entity=='face':
                box=placed.optimalBoundingBox(False,False);item['mass_bounds_mm']=[box.XMin,box.YMin,box.ZMin,box.XLength,box.YLength,box.ZLength]
                item['mass_property_basis']='kernel-default-estimate'
            if entity=='edge':
                points=placed.discretize(Deflection=.08) if placed.Length>1e-9 else []
                item['v']=[round(n-origin[i],6) for a,b in zip(points,points[1:]) for point in (a,b) for i,n in enumerate(xyz(point))]
                item['curvature'] = ({'schema': 1, 'available': False, 'samples': [], 'reason': 'Faceted mesh input has no original smooth curve.'}
                                     if body.get('source_geometry') == 'triangle-mesh' else curvature_samples(placed, origin, budget))
                item['curve_events']=({'schema':1,'available':False,'complete':False,'events':[],'reason':'Faceted input has no original smooth curve.'}
                                      if body.get('source_geometry')=='triangle-mesh' else analyse_edge(placed,origin,event_budget))
            result.append(item)
    return {'body_id':body['body_id'],'member_id':body.get('component_id'),'label':body['name'],
            'source_body_index':selection.get('body_index',body['body_id']),'source_body_name':selection.get('body_name',body['name']),
            'faces':faces,'edges':edges,'curve_events':({'schema':1,'available':False,'events':[],'reason':'Faceted input.'} if body.get('source_geometry')=='triangle-mesh' else analyse_joins(world,origin,world.Edges,event_budget))}
