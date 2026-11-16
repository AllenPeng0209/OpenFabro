"""Trusted headless native CAD reader, also staged beside the modeling adapter."""
import json
import math
import os
from pathlib import Path
import traceback

import FreeCAD as App
import Import
import Part
from freecad_topology import body_topology, surface_samples, surface_summary
import mechanical_materials as materials


def color_hex(color):
    return '#'+''.join(f'{int(math.floor(max(0,min(1,float(n)))*255+.5)):02x}' for n in color[:3])


def measures(shape,allow_curves=False):
    if shape.isNull() or not shape.isValid() or (not shape.Faces and not (allow_curves and shape.Edges)):
        raise ValueError('Import requires valid native faces or closed solids.')
    box=shape.optimalBoundingBox(False,False)
    if len(shape.Faces)>20000 or len(shape.Solids)>256:
        raise ValueError('Import exceeds the native face/body budget.')
    if any(not math.isfinite(n) or abs(n)>20000 for n in (box.XMin,box.YMin,box.ZMin,box.XMax,box.YMax,box.ZMax)):
        raise ValueError('Import exceeds supported mechanical bounds.')
    return {'valid':True,'solids':len(shape.Solids),'faces':len(shape.Faces),
            'volume_mm3':shape.Volume if shape.Solids else 0,'area_mm2':shape.Area,
            'origin_mm':[box.XMin,box.YMin,box.ZMin],'size_mm':[box.XLength,box.YLength,box.ZLength]}


def drawing_edge(item):
    kind=item['kind']
    if kind=='line':result=Part.makeLine(App.Vector(*item['start']),App.Vector(*item['end']))
    elif kind=='bezier':
        curve=Part.BezierCurve();curve.setPoles([App.Vector(*p) for p in item['poles']]);result=curve.toShape()
    elif kind=='bspline':
        knots=[];mults=[]
        for knot in item['knots']:
            if knots and abs(knots[-1]-knot)<1e-12:mults[-1]+=1
            else:knots.append(knot);mults.append(1)
        curve=Part.BSplineCurve();args=[[App.Vector(*p) for p in item['poles']],mults,knots,False,item['degree']]
        if item['weights']:args.append(item['weights'])
        curve.buildFromPolesMultsKnots(*args);result=curve.toShape()
    elif kind=='ellipse':
        center=App.Vector(*item['center']);x=App.Vector(*item['axis_x']);y=App.Vector(*item['axis_y']);start=item['t0'];sweep=item['sweep'];normal=x.cross(y);normal.normalize()
        full=abs(abs(sweep)-math.tau)<1e-8
        if abs(x.Length-y.Length)<=max(1e-9,x.Length*1e-10):
            if full:result=Part.makeCircle((x.Length+y.Length)/2,center,normal)
            else:
                points=[center+x*math.cos(start+sweep*t)+y*math.sin(start+sweep*t) for t in (0,.5,1)];result=Part.Arc(*points).toShape()
        else:
            curve=Part.Ellipse(center+x,center+y,center)
            if full:result=curve.toShape()
            else:
                lower=min(start,start+sweep);result=curve.toShape(lower,lower+abs(sweep))
                if sweep<0:result.reverse()
    else:raise ValueError('Unsupported drawing edge type.')
    if item.get('reverse'):result.reverse()
    result.fixTolerance(1e-6)
    return result


def drawing_geometry(filename,body_indices=None):
    data=json.loads(Path(filename).read_text())
    if data.get('schema')!=1 or data.get('geometry_kind')!='planar-drawing' or data.get('units')!='mm':raise ValueError('Invalid staged drawing snapshot.')
    result=[]
    for profile in data['profiles']:
        wires=[Part.Wire([drawing_edge(edge) for edge in loop]) for loop in [profile['outer']]+profile['holes']]
        if any(not wire.isClosed() for wire in wires):raise ValueError('Drawing profile has an open wire after native reconstruction.')
        face=Part.makeFace(wires,'Part::FaceMakerCheese')
        if len(face.Faces)!=1:raise ValueError('Drawing did not resolve to one native planar face.')
        normal=App.Vector(*profile['normal']);native=face.Faces[0].normalAt(0,0)
        if native.dot(normal)<0:face.reverse()
        proof=measures(face)
        color=profile['color'];rgb=[int(color[i:i+2],16)/255 for i in (1,3,5)]+[1.]
        result.append({'shape':face,'name':profile['name'],'body_id':len(result),'kind':'surface','color':color,'face_colors':[rgb],
                       'source_geometry':'planar-drawing','can_extrude':True,'holes':len(profile['holes']),'normal':list(profile['normal']),
                       'layer':profile['layer'],'source_curve_types':sorted({edge['kind'] for loop in [profile['outer']]+profile['holes'] for edge in loop}),
                       'reference_only':False})
    groups={}
    for edge in data['references']:groups.setdefault(edge.get('layer','References'),[]).append(edge)
    for layer,edges in groups.items():
        shape=Part.makeCompound([drawing_edge(edge) for edge in edges]);measures(shape,allow_curves=True)
        result.append({'shape':shape,'name':layer+' · reference curves','body_id':len(result),'kind':'curve','color':edges[0].get('color','#9e9e9e'),
                       'face_colors':[],'source_geometry':'planar-drawing','can_extrude':False,'reference_only':True,'layer':layer})
    if not result or len(result)>256:raise ValueError('Drawing contains no supported geometry, or exceeds256 profile/reference groups.')
    return result if body_indices is None else [result[i] for i in body_indices]


def mesh_geometry(filename,body_indices=None):
    data=json.loads(Path(filename).read_text())
    if data.get('schema')!=1 or data.get('geometry_kind')!='triangle-mesh' or data.get('units')!='mm':raise ValueError('Invalid staged mesh snapshot.')
    sources=data['bodies'] if body_indices is None else [data['bodies'][i] for i in body_indices]
    result=[]
    for body in sources:
        triangles=body['indices'];vertices=body['vertices'];colors=body['face_colors']
        if len(triangles)>20000:raise ValueError('This mesh exceeds the 20000-triangle CAD conversion budget; the original remains available for reference.')
        points=[App.Vector(*p) for p in vertices];shape=Part.Shape();shape.makeShapeFromMesh((points,[tuple(f) for f in triangles]),1e-6)
        if body['watertight'] and body['winding_consistent']:
            if len(shape.Shells)!=1 or not shape.Shells[0].isClosed():raise ValueError('Mesh did not convert into a closed native shell.')
            shape=Part.makeSolid(shape.Shells[0])
            if shape.Volume<0:shape.reverse()
        uniform=len({tuple(color) for color in colors})==1
        if uniform:shape=shape.removeSplitter();native_colors=[colors[0]]*len(shape.Faces)
        else:
            lookup={}
            for indices,color in zip(triangles,colors):
                center=[sum(vertices[index][i] for index in indices)/3 for i in range(3)];lookup.setdefault(tuple(round(v,6) for v in center),[]).append((center,color))
            native_colors=[]
            for face in shape.Faces:
                center=face.CenterOfMass;key=tuple(round(v,6) for v in (center.x,center.y,center.z));candidates=lookup.get(key,[])
                matches=[color for point,color in candidates if math.dist(point,[center.x,center.y,center.z])<1e-5]
                if not matches or len({tuple(c) for c in matches})!=1:raise ValueError('Mesh face colors cannot be mapped unambiguously to the native shape.')
                native_colors.append(matches[0])
        measures(shape)
        result.append({'shape':shape,'name':body['name'],'body_id':body['body_id'],'kind':'solid' if shape.Solids else 'surface',
                       'color':color_hex(native_colors[0]),'face_colors':native_colors,'source_geometry':'triangle-mesh',
                       'conversion_tolerance_mm':1e-6,'preview_meshes':body['preview_meshes']})
    return result


def native_rows(document,by_name):
    """Resolve physical instances through the root, including LinkGroup placements.

    getGlobalPlacement on a STEP definition does not include its LinkGroup instance.
    getSubObject resolves the full instance path and supplies the transformed shape.
    """
    containers=('App::Part','App::LinkGroup','App::Link')
    candidates=[obj for obj in document.Objects if hasattr(obj,'Shape') and not obj.Shape.isNull()]
    roots=[obj for obj in candidates if not any(parent.TypeId in containers for parent in obj.InList)]
    rows=[]
    def visit(root,path,node,depth=0,label=None):
        if depth>32 or len(rows)>=256:raise ValueError('Native assembly exceeds the instance traversal budget.')
        children=node.getSubObjects() if node.TypeId in containers else []
        if children:
            if node.TypeId=='App::Link':label=node.Label
            for child in children:
                full=path+child;target=root.getSubObject(full,1)
                if target is None:raise ValueError('Native assembly instance path is unavailable.')
                visit(root,full,target,depth+1,label)
            return
        world=root.getSubObject(path) if path else root.Shape.copy()
        if world is None or world.isNull() or not world.Faces:return
        source=node.getLinkedObject() if node.TypeId=='App::Link' else node
        rows.append((source,by_name.get(source.Name,[]),world,label or node.Label,root.Name+'.'+path))
    for root in roots:visit(root,'',root)
    return rows


def load_geometry(filename,document,body_indices=None):
    """Return native world-space leaves, excluding aggregate assembly groups."""
    if str(filename).endswith('.mesh.json'):return mesh_geometry(filename,body_indices)
    if str(filename).endswith('.drawing.json'):return drawing_geometry(filename,body_indices)
    if Path(filename).suffix.lower()=='.brep':
        obj=document.addObject('Part::Feature','ImportedBREP');obj.Label='Imported BREP';obj.Shape=Part.read(filename)
        rows=[(obj,[],obj.Shape.copy(),obj.Label,obj.Name)]
    else:
        colors=Import.insert(filename,document.Name,merge=False,useLinkGroup=True) or []
        by_name={obj.Name:list(values) for obj,values in colors}
        rows=native_rows(document,by_name)
    bodies=[]
    for obj,colors,world,label,instance in rows:
        local=obj.Shape.copy()
        if len(colors)==1:colors=colors*len(local.Faces)
        if not local.Solids and len(local.Faces)>1:
            # IGES can encode the six faces of a watertight part as a compound.
            # Keep open/nonmanifold surfaces honest instead of forcing a solid.
            try:
                shell=Part.makeShell(local.Faces)
                solid=Part.makeSolid(shell) if shell.isClosed() else None
                if solid is not None and solid.isValid() and solid.Volume>1e-9:
                    local=solid
            except Exception:pass
        if not world.Solids and local.Solids:
            # Preserve a successfully sewn IGES solid in the same world placement.
            transform=world.Placement*obj.Shape.Placement.inverse();world=local.copy();world.transformShape(transform.toMatrix())
        pieces=world.Solids or [world]
        local_pieces=local.Solids or [local]
        for part_index,shape in enumerate(pieces):
            measures(shape)
            face_colors=[]
            for face in local_pieces[part_index].Faces:
                index=next((i for i,f in enumerate(local.Faces) if f.isSame(face)),None)
                face_colors.append(list(colors[index]) if index is not None and index<len(colors) else [.65,.71,.75,1])
            name=label+(f' / {part_index+1}' if len(pieces)>1 else '')
            bodies.append({'shape':shape,'name':name,'face_colors':face_colors,'color':color_hex(face_colors[0]),
                           'native_instance':instance+('/solid'+str(part_index) if len(pieces)>1 else ''),
                           'body_id':len(bodies),'kind':'solid' if shape.Solids else 'surface'})
    if not bodies or len(bodies)>256:
        raise ValueError('Import contains no supported native faces, or exceeds 256 bodies.')
    measures(Part.makeCompound([b['shape'] for b in bodies]))
    return bodies if body_indices is None else [bodies[i] for i in body_indices]


def describe(body):
    return {key:value for key,value in body.items() if key not in ('shape','preview_meshes','_selection')} | measures(body['shape'],allow_curves=body.get('kind')=='curve')


def make_scene(bodies,source):
    whole=Part.makeCompound([b['shape'] for b in bodies]);proof=measures(whole,allow_curves=True)
    origin=proof['origin_mm'];meshes=[];lines=[];triangle_count=0;line_points=0;topology=[];edge_points=0
    curvature_budget = {'remaining': 50000}
    surface_budget = {'remaining': 200000}
    event_budget = {'remaining':250000}
    for body in bodies:
        mapped = None
        if not body.get('preview_meshes'):
            mapped = body_topology(body, origin, curvature_budget,event_budget)
            topology.append(mapped)
            edge_points += sum(len(edge.get('v', []))//3 for edge in mapped['edges'])
            if edge_points > 500000:
                raise ValueError('Native reference preview exceeds the edge budget.')
        if body.get('kind')=='curve':
            values=[]
            for edge in body['shape'].Edges:
                points=edge.discretize(Deflection=.04)
                for a,b in zip(points,points[1:]):values.extend(round(n-origin[i],6) for p in (a,b) for i,n in enumerate((p.x,p.y,p.z)))
            line_points+=len(values)//3
            if line_points>500000:raise ValueError('Drawing exceeds the line preview budget.')
            lines.append({'name':body['name'],'body_id':body['body_id'],'group':'mechanical','color':body['color'],'v':values});continue
        if body.get('preview_meshes'):
            for mesh in body['preview_meshes']:
                meshes.append({**mesh,'v':[value-origin[i%3] for i,value in enumerate(mesh['v'])]});triangle_count+=len(mesh['t'])//3
            if triangle_count>500000:raise ValueError('Import exceeds the preview mesh budget.')
            continue
        groups={}
        for i,face in enumerate(body['shape'].Faces):
            color=color_hex(body['face_colors'][i]) if i<len(body['face_colors']) else body['color']
            material=(body.get('face_materials') or [body.get('material')]*len(body['shape'].Faces))[i];key=color+(':'+json.dumps(material,sort_keys=True) if material else '')
            group=groups.setdefault(key,{'name':body['name'],'body_id':body['body_id'],'group':body.get('group','mechanical'),'color':color,'v':[],'t':[],'face_ranges':[],'surface_samples':[],
                                          **({'material':material,**{k:material[k] for k in ('metalness','roughness','opacity','transmission','ior','clearcoat','clearcoat_roughness','pattern','repeat_mm')}} if material else {}),
                                          **{key:body[key] for key in ('component_id','component_label','source_name') if key in body}})
            vertices,triangles=face.tessellate(.08)
            samples=surface_samples(face,vertices,i,origin,surface_budget,faceted=body.get('source_geometry')=='triangle-mesh')
            group['surface_samples'].extend(samples)
            mapped['faces'][i]['surface_curvature']=surface_summary(samples)
            offset=len(group['v'])//3
            group['face_ranges'].append([i,len(group['t'])//3,len(triangles)])
            group['v'].extend(round(n-origin[j],6) for p in vertices for j,n in enumerate((p.x,p.y,p.z)))
            group['t'].extend(n+offset for triangle in triangles for n in triangle)
            triangle_count+=len(triangles)
            if triangle_count>500000:raise ValueError('Import exceeds the preview mesh budget.')
        meshes.extend(group for group in groups.values() if group['t'])
    if not meshes and not lines:raise ValueError('Import contains no displayable native geometry.')
    return {'size':proof['size_mm'],'origin':origin,'source':source,'meshes':meshes,'lines':lines,'topology':{'schema':1,'bodies':topology}},triangle_count


def main(job):
    doc=App.newDocument('OpenFabroImport')
    try:
        bodies=load_geometry(job['source'],doc)
        scene,triangles=make_scene(bodies,'native-freecad-import')
        (Path(job['directory'])/'scene.json').write_text(json.dumps(scene,separators=(',',':')))
        return {'ok':True,**measures(Part.makeCompound([b['shape'] for b in bodies]),allow_curves=True),
                'bodies':[describe(b) for b in bodies],'triangles':triangles,'freecad_version':'.'.join(App.Version()[:3]),
                'units':'mm','assembly_constraints_preserved':False}
    finally:App.closeDocument(doc.Name)


if os.environ.get('OPENFABRO_IMPORT_JOB'):
    job=json.loads(Path(os.environ['OPENFABRO_IMPORT_JOB']).read_text())
    try:result=main(job)
    except Exception as error:result={'ok':False,'error':str(error),'trace':traceback.format_exc()}
    (Path(job['directory'])/'report.json').write_text(json.dumps(result))
