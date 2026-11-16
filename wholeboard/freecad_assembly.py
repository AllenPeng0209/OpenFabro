"""Trusted rigid assembly/mate and native inter-member fit computation."""
import math
import FreeCAD as App
import Part
from freecad_import import load_geometry,measures,color_hex
from freecad_topology import verify_reference,geometry as reference_geometry
import mechanical_materials as materials

V=App.Vector


def unit(value):
    result=V(*value) if isinstance(value,(list,tuple)) else V(value)
    if result.Length<1e-12:raise ValueError('Assembly reference direction is zero.')
    result.normalize();return result


def xyz(value):return [value.x,value.y,value.z]


def placed(shape,pose):
    value=shape.copy();value.transformShape(pose.toMatrix());return value


def component(item,filename,evidence):
    if not filename:raise ValueError('The assembly component dependency is unavailable.')
    doc=App.newDocument('OpenFabroAssemblySource')
    try:bodies=load_geometry(filename,doc,item['source'].get('bodies'))
    finally:App.closeDocument(doc.Name)
    bodies=materials.restore(bodies,evidence.get('appearance'))
    if evidence.get('geometry_provenance') in ('triangle-mesh','faceted-mesh-input'):
        bodies=[{**body,'source_geometry':'triangle-mesh'} for body in bodies]
    if any(not body['shape'].Solids for body in bodies):raise ValueError('Assembly components need native solids; open drawing/mesh references are not physical parts.')
    rotation=item['rotation'];pose=App.Placement(V(*item['translation']),App.Rotation(V(*rotation['axis']),rotation['angle']),V(*rotation['origin']))
    local=Part.makeCompound([body['shape'] for body in bodies]);measures(local)
    return {'id':item['id'],'label':item.get('label') or item['id'],'local':local,'bodies':bodies,'pose':pose,'evidence':evidence}


def anchor(member,selector):
    bodies=member['bodies']
    if 'body_index' in selector:
        if selector['body_index']>=len(bodies):raise ValueError('Assembly anchor body index is unavailable.')
        bodies=[bodies[selector['body_index']]]
    if 'body_name' in selector:
        bodies=[body for body in bodies if body['name']==selector['body_name']]
        if not bodies:raise ValueError('Assembly anchor body name is unavailable.')
    if 'body_instance' in selector and (len(bodies)!=1 or bodies[0].get('native_instance')!=selector['body_instance']):raise ValueError('The selected native body instance changed. Rebuild the preview and select it again.')
    shape=Part.makeCompound([body['shape'] for body in bodies]);direction=unit(selector['normal']);kind=selector['kind']
    if kind=='datum':return {'point':V(*selector.get('point',[0,0,0])),'axis':direction,'kind':'datum','index':None}
    entity=selector.get('reference',{}).get('entity','edge' if kind=='edge' else 'face')
    if 'reference' in selector:
        items=shape.Edges if entity=='edge' else shape.Faces;index=selector['index']
        if index>=len(items):raise ValueError('The selected native reference is unavailable. Select it again.')
        verify_reference(shape,items[index],entity,selector['reference'])
        if entity=='edge' and kind=='axis':
            details=reference_geometry(items[index],'edge')
            if details['mate_kind']!='axis':raise ValueError('Choose a circular edge for a concentric reference.')
            return {'point':V(*details['point']),'axis':unit(details['normal']),'kind':'axis','index':index,'entity':'edge','signature_verified':True}
    if kind=='edge':
        edges=shape.Edges
        if not edges:raise ValueError('Component has no reference edge.')
        index=selector.get('index',max(range(len(edges)),key=lambda i:edges[i].Length))
        if index>=len(edges):raise ValueError('Assembly edge anchor is unavailable.')
        edge=edges[index];parameter=(edge.FirstParameter+edge.LastParameter)/2
        return {'point':edge.valueAt(parameter),'axis':unit(edge.tangentAt(parameter)),'kind':'edge','index':index,'signature_verified':'reference' in selector}
    candidates=[]
    for index,face in enumerate(shape.Faces):
        surface=face.Surface
        if kind=='plane' and type(surface).__name__=='Plane':axis=unit(face.normalAt(0,0));point=face.CenterOfMass
        elif kind=='axis' and type(surface).__name__ in ('Cylinder','Cone'):
            axis=unit(surface.Axis);point=surface.Center
            if axis.dot(direction)<0:axis=-axis
            if 'radius' in selector and (not hasattr(surface,'Radius') or abs(surface.Radius-selector['radius'])>1e-5):continue
        else:continue
        if axis.dot(direction)<1-1e-7:continue
        candidates.append({'point':point,'axis':axis,'kind':kind,'index':index,'area':face.Area,'signature_verified':'reference' in selector})
    if 'index' in selector:candidates=[c for c in candidates if c['index']==selector['index']]
    if not candidates:raise ValueError('No native '+kind+' matches the assembly anchor selector.')
    if selector['extreme']=='nearest':
        if 'point' not in selector:raise ValueError('Nearest anchor selector needs a source-local point.')
        return min(candidates,key=lambda c:(c['point']-V(*selector['point'])).Length)
    chooser=min if selector['extreme']=='min' else max
    position=chooser(c['point'].dot(direction) for c in candidates)
    return max((c for c in candidates if abs(c['point'].dot(direction)-position)<1e-6),key=lambda c:c['area'])


def world(member,reference):return member['pose'].multVec(reference['point']),unit(member['pose'].Rotation.multVec(reference['axis']))


def residual(mate,members):
    target,reference=members[mate['target']],members[mate['reference']];a,ax=world(target,mate['_target']);b,bx=world(reference,mate['_reference']);desired=-bx if mate['flip'] else bx
    error=[]
    if mate['type'] in ('coincident','concentric','aligned'):error.extend(xyz(ax-desired))
    if mate['type'] in ('coincident','offset'):error.append((a-b).dot(bx)-mate['offset'])
    elif mate['type']=='concentric':error.extend(xyz((a-b)-bx*((a-b).dot(bx))))
    return error


def apply_mate(mate,members):
    target,reference=members[mate['target']],members[mate['reference']];a,ax=world(target,mate['_target']);b,bx=world(reference,mate['_reference']);desired=-bx if mate['flip'] else bx
    if mate['type'] in ('coincident','concentric','aligned'):
        rotation=App.Rotation(ax,desired);about=App.Placement(a-rotation.multVec(a),rotation);target['pose']=about*target['pose'];a,ax=world(target,mate['_target'])
    if mate['type'] in ('coincident','offset'):shift=bx*(mate['offset']-(a-b).dot(bx))
    elif mate['type']=='concentric':delta=b-a;shift=delta-bx*delta.dot(bx)
    else:shift=V(0,0,0)
    target['pose'].Base=target['pose'].Base+shift


def member_bodies(member):
    result=[]
    for index,body in enumerate(member['bodies']):
        result.append({**{k:v for k,v in body.items() if k not in ('shape','preview_meshes','_selection')},'shape':placed(body['shape'],member['pose']),
                       '_selection':{'shape':body['shape'],'body_index':index,'body_name':body['name'],'body_instance':body.get('native_instance')},
                       'source_name':body['name'],'name':member['label']+' / '+body['name'],'component_id':member['id'],'component_label':member['label'],
                       'group':'board' if member['evidence'].get('kind')=='board' else 'mechanical'})
    return result


def solve(item,shapes,metadata,components):
    members={}
    for name in item['members']:
        if name in components:
            source=components[name];members[name]={**source,'pose':App.Placement(source['pose'])}
        else:
            members[name]={'id':name,'label':name,'local':shapes[name],'bodies':metadata[name],'pose':App.Placement(),'evidence':{'kind':'feature','geometry_provenance':'native-brep','coverage_complete':True}}
    mates=[];parents={name:set() for name in members}
    for value in item['mates']:
        mate=dict(value);mate['_target']=anchor(members[mate['target']],mate['target_anchor']);mate['_reference']=anchor(members[mate['reference']],mate['reference_anchor']);mates.append(mate);parents[mate['target']].add(mate['reference'])
    order=[];remaining=set(members)
    while remaining:
        ready=[name for name in item['members'] if name in remaining and not (parents[name]&remaining)]
        if not ready:raise ValueError('Cyclic mate dependencies need a closed-loop constraint solver; no assembly was published.')
        order.extend(ready);remaining-=set(ready)
    for name in order:
        assigned=[mate for mate in mates if mate['target']==name]
        if not assigned:continue
        for iteration in range(32):
            for mate in assigned:apply_mate(mate,members)
            if all(max((abs(v) for v in residual(mate,members)),default=0)<1e-7 for mate in assigned):break
        else:raise ValueError('Cannot satisfy assembly mate constraints: '+', '.join(m['id'] for m in assigned))
    constraint_report=[]
    for mate in mates:
        error=residual(mate,members)
        if max((abs(v) for v in error),default=0)>1e-6:raise ValueError('Assembly constraint residual exceeds tolerance: '+mate['id'])
        constraint_report.append({'id':mate['id'],'type':mate['type'],'target':mate['target'],'reference':mate['reference'],'residual':error,'satisfied':True,
                                  'target_anchor':{k:xyz(v) if k in ('point','axis') else v for k,v in mate['_target'].items()},'reference_anchor':{k:xyz(v) if k in ('point','axis') else v for k,v in mate['_reference'].items()}})
    output=[];summaries=[];placed_shapes={}
    for name in item['members']:
        member=members[name];body_rows=member_bodies(member);placed_shapes[name]=Part.makeCompound([row['shape'] for row in body_rows]);proof=measures(placed_shapes[name]);pose=member['pose']
        for row in body_rows:row['body_id']=len(output);output.append(row)
        summaries.append({'id':name,'label':member['label'],'fixed':name in item['fixed'],'translation_mm':xyz(pose.Base),'quaternion_xyzw':list(pose.Rotation.Q),**proof,
                          'source':member['evidence'],'unconstrained_motion_possible':name not in item['fixed']})
    pairs=[];complete=all(member['evidence'].get('coverage_complete',True) for member in members.values())
    for index,a in enumerate(item['members']):
        for b in item['members'][index+1:]:
            first,second=placed_shapes[a],placed_shapes[b];distance,points,info=first.distToShape(second);overlap=first.common(second).Volume
            rule=next((r for r in item['rules'] if {r['a'],r['b']}=={a,b}),None);minimum=rule['minimum_mm'] if rule else item['clearance_mm'];allowed=rule['allow_overlap_mm3'] if rule else 0
            status='interference' if overlap>allowed+1e-7 else 'clearance' if distance+1e-6<minimum else 'contact' if distance<1e-6 else 'clear'
            pairs.append({'a':a,'b':b,'distance_mm':distance,'overlap_mm3':overlap,'minimum_mm':minimum,'allowed_overlap_mm3':allowed,'status':status,'pass':status in ('clear','contact'),
                          'nearest_points_mm':[xyz(p) for p in points[0]] if points else []})
    return Part.makeCompound(list(placed_shapes.values())),output,{'members':summaries,'solver':{'method':'sequential directed rigid mates','satisfied':True,'mates':constraint_report,'closed_loop_solver':False,'full_dof_lock_not_assumed':True},
          'fit':{'method':'FreeCAD native inter-member common volume and distToShape','scope':'Between declared assembly members; internal geometry within one member is not rechecked.','complete':complete,'pass':all(row['pass'] for row in pairs) if complete else None,'pairs':pairs,
                 'coverage_warnings':[{'member':m['id'],'unmatched_components':m['evidence'].get('unmatched_components',[]),**({'nested':m['evidence']['nested_coverage_warnings']} if m['evidence'].get('nested_coverage_warnings') else {})} for m in members.values() if not m['evidence'].get('coverage_complete',True)]}}
