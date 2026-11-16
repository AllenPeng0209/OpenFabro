"""Trusted FreeCADCmd adapter for validated OpenFabro mechanical JSON programs."""
import json
import math
import os
from pathlib import Path
import traceback
import xml.etree.ElementTree as ET
import zipfile

import FreeCAD as App
import Import
import Part
from freecad_import import load_geometry, measures, describe, make_scene, color_hex
from freecad_assembly import component as assembly_component,member_bodies,placed,solve as solve_assembly
import freecad_sketch
import mechanical_materials as materials

V = App.Vector


def wire(profile):
    if profile['kind'] == 'circle':
        result = Part.Wire([Part.makeCircle(profile['radius'])])
    else:
        points = profile.get('points') or [[0,0], [profile['width'],0], [profile['width'],profile['height']], [0,profile['height']]]
        vertices = [V(p[0], p[1], 0) for p in points]
        if (vertices[0]-vertices[-1]).Length > 1e-10:
            vertices.append(vertices[0])
        result = Part.Wire(Part.makePolygon(vertices).Edges)
    rotation = App.Rotation(V(0,0,1), V(*profile['normal']))
    result.Placement = App.Placement(V(*profile['origin']), rotation)
    return result


def selected_edges(shape, selection):
    if selection == 'all':
        return shape.Edges
    if selection == 'vertical':
        return [edge for edge in shape.Edges if len(edge.Vertexes) == 2 and
                abs((edge.Vertexes[-1].Point-edge.Vertexes[0].Point).z) > 1e-7 and
                math.hypot((edge.Vertexes[-1].Point-edge.Vertexes[0].Point).x, (edge.Vertexes[-1].Point-edge.Vertexes[0].Point).y) < 1e-7]
    return [shape.Edges[index] for index in selection]


def selected_faces(shape, selection):
    if selection in ('top', 'bottom'):
        chooser = max if selection == 'top' else min
        return [chooser(shape.Faces, key=lambda face: face.CenterOfMass.z)]
    return [shape.Faces[index] for index in selection]


def feature(item, shapes, imported=None):
    op = item['op']
    target = shapes.get(item.get('target'))
    if op=='material':return target.copy()
    if op == 'import':
        return Part.makeCompound([body['shape'] for body in imported[item['id']]])
    if op == 'extrude_shape':
        return target.extrude(V(*item['vector']))
    if op == 'box':
        return Part.makeBox(*item['size'], V(*item['origin']))
    if op == 'cylinder':
        return Part.makeCylinder(item['radius'], item['height'], V(*item['origin']), V(*item['axis']))
    if op == 'extrude':
        return Part.Face(wire(item['profile'])).extrude(V(*item['vector']))
    if op == 'revolve':
        return Part.Face(wire(item['profile'])).revolve(V(*item['origin']), V(*item['axis']), item['angle'])
    if op == 'loft':
        return Part.makeLoft([wire(p) for p in item['profiles']], True, False)
    if op == 'sweep':
        path = Part.Wire(Part.makePolygon([V(*p) for p in item['path']]).Edges)
        # Mitered polyline joins retain the full path and survive STEP roundtrip.
        return path.makePipeShell([wire(item['profile'])], True, False, 1)
    if op in ('cut', 'fuse', 'common'):
        return getattr(target, op)(shapes[item['tool']]).removeSplitter()
    if op in ('translate', 'rotate'):
        result = target.copy()
        if op == 'translate':
            result.translate(V(*item['vector']))
        else:
            result.rotate(V(*item['origin']), V(*item['axis']), item['angle'])
        return result
    if op == 'shell':
        return target.makeThickness(selected_faces(target, item['faces']), -item['thickness'], 1e-5)
    if op in ('fillet', 'chamfer'):
        edges = selected_edges(target, item['edges'])
        if not edges:
            raise ValueError('No edges match this feature selector.')
        return target.makeFillet(item['radius'], edges) if op == 'fillet' else target.makeChamfer(item['distance'], edges)
    if op == 'hole':
        tool = Part.makeCylinder(item['diameter']/2, item['depth'], V(*item['origin']), V(*item['axis']))
        result = target.cut(tool).removeSplitter()
        if target.Volume-result.Volume <= max(1e-9, abs(target.Volume)*1e-12):
            raise ValueError('Hole removes no material from its target. Check the origin, axis and depth.')
        return result
    if op in ('linear_pattern', 'circular_pattern'):
        if len(target.Solids)*item['count'] > 1024 or len(target.Faces)*item['count'] > 20000:
            raise ValueError('Pattern exceeds the native solid/face budget.')
        copies = []
        for index in range(item['count']):
            result = target.copy()
            if op == 'linear_pattern':
                result.translate(V(*(n*index for n in item['step'])))
            else:
                result.rotate(V(*item['origin']), V(*item['axis']), index*item['step_angle'])
            copies.append(result)
        return Part.makeCompound(copies)
    raise ValueError('Unsupported solid operation: '+op)


def metrics(shape):
    box = shape.optimalBoundingBox(False,False)
    if shape.isNull() or not shape.isValid() or not shape.Solids or not math.isfinite(shape.Volume) or shape.Volume <= 1e-9:
        raise ValueError('The feature is not a valid nonempty exact solid.')
    if any(not math.isfinite(n) or abs(n) > 20000 for n in (box.XMin, box.YMin, box.ZMin, box.XMax, box.YMax, box.ZMax)):
        raise ValueError('The feature exceeds the supported mechanical bounds.')
    if len(shape.Faces) > 20000:
        raise ValueError('The feature exceeds the mechanical face budget.')
    return {'valid': True, 'solids': len(shape.Solids), 'faces': len(shape.Faces),
            'volume_mm3': shape.Volume, 'area_mm2': shape.Area,
            'size_mm': [box.XLength, box.YLength, box.ZLength], 'origin_mm': [box.XMin, box.YMin, box.ZMin]}


def inherited_face_color(face,base):
    colors=base['face_colors']
    if len({color_hex(color) for color in colors})==1:return colors[0]
    # A cut replaces a painted planar face with a new face containing a hole.
    # Match surviving native surface area rather than repainting it as body color.
    overlaps=[]
    for index,old in enumerate(base['shape'].Faces):
        try:
            area=face.common(old).Area
            if area>max(1e-9,face.Area*1e-9):overlaps.append((area,index))
        except Exception:pass
    if overlaps:
        area,index=max(overlaps)
        candidates=[i for value,i in overlaps if abs(value-area)<max(1e-9,area*1e-7)]
        if len({color_hex(colors[i]) for i in candidates})==1:return colors[index]
    return colors[0]


def inherited_face_material(face,base):
    styles=base.get('face_materials')
    if not styles:return base.get('material')
    matches=[]
    for index,old in enumerate(base['shape'].Faces):
        area=face.common(old).Area
        if area>max(1e-9,face.Area*1e-9):matches.append((area,styles[index]))
    if not matches:return base.get('material')
    largest=max(area for area,style in matches);candidates=[style for area,style in matches if abs(area-largest)<max(1e-9,largest*1e-7)]
    if len({json.dumps(style,sort_keys=True) for style in candidates})!=1:raise ValueError('Surface material correspondence is ambiguous. Assign the finish after the geometry edit.')
    return candidates[0]


def body_metadata(shape,item,previous,program_name):
    """Keep native body identity when topology permits an unambiguous match."""
    pieces=shape.Solids or [shape]
    result=[]
    transformed=item['op'] in ('translate','rotate') and len(pieces)==len(previous)
    for index,piece in enumerate(pieces):
        exact=[body for body in previous if piece.isSame(body['shape'])]
        scores=[sum(any(face.isSame(old) for old in body['shape'].Faces) for face in piece.Faces) for body in previous]
        best=max(scores,default=0)
        matches=[body for body,score in zip(previous,scores) if score==best] if best else []
        base=previous[index] if transformed else exact[0] if len(exact)==1 else matches[0] if len(matches)==1 else previous[0] if len(previous)==1 and len(pieces)==1 else None
        colors=[];face_materials=[]
        for face_index,face in enumerate(piece.Faces):
            old_index=next((i for i,f in enumerate(base['shape'].Faces) if face.isSame(f)),None) if base else None
            if transformed and base and len(piece.Faces)==len(base['shape'].Faces):old_index=face_index
            colors.append(base['face_colors'][old_index] if base and old_index is not None and old_index<len(base['face_colors']) else inherited_face_color(face,base) if base else [.65,.71,.75,1])
            style=base.get('face_materials',[base.get('material')]*len(base['shape'].Faces))[old_index] if base and old_index is not None else inherited_face_material(face,base) if base else None
            face_materials.append(style)
        result.append({'shape':piece,'name':base['name'] if base else program_name if len(pieces)==1 else item['id']+' / '+str(index+1),
                       'body_id':index,'kind':'solid' if piece.Solids else 'surface','face_colors':colors,'color':color_hex(colors[0]),
                       'identity_preserved':bool(base),**({'material':base['material']} if base and base.get('material') else {}),**({'face_materials':face_materials} if any(face_materials) else {})})
    return result


def face_colors_match(expected,actual):
    """Compare appearance on corresponding native faces, independent of face order."""
    if len(expected['shape'].Faces)!=len(actual['shape'].Faces):return False
    remaining=list(enumerate(actual['shape'].Faces))
    for index,face in enumerate(expected['shape'].Faces):
        candidates=[(i,other) for i,other in remaining if abs(face.Area-other.Area)<=max(1e-5,abs(face.Area)*1e-7)
                    and (face.CenterOfMass-other.CenterOfMass).Length<1e-4
                    and color_hex(expected['face_colors'][index])==color_hex(actual['face_colors'][i])]
        if not candidates:return False
        remaining.remove(candidates[0])
    return True


def mesh_exports(directory,bodies):
    """Standard 3MF core package and OBJ with the common RGB vertex extension."""
    scene,total=make_scene(bodies,'native-freecad-mechanical');origin=scene['origin'];by_body={}
    for mesh in scene['meshes']:by_body.setdefault(mesh['body_id'],[]).append(mesh)
    namespace='http://schemas.microsoft.com/3dmanufacturing/core/2015/02';ET.register_namespace('',namespace)
    node=lambda name: '{'+namespace+'}'+name
    model=ET.Element(node('model'),{'unit':'millimeter','{http://www.w3.org/XML/1998/namespace}lang':'en-US'})
    resources=ET.SubElement(model,node('resources'));materials=ET.SubElement(resources,node('basematerials'),{'id':'1'})
    palette={};build=ET.SubElement(model,node('build'));obj_lines=['# OpenFabro native tessellation; coordinates in millimeters; RGB vertex extension.'];offset=1;volume=0.
    for index,body in enumerate(bodies):
        vertices=[];lookup={};triangles=[];obj_vertices=[];obj_lookup={};obj_faces=[]
        for mesh in by_body.get(body['body_id'],[]):
            color=mesh['color']
            if color not in palette:
                palette[color]=len(palette);ET.SubElement(materials,node('base'),{'name':'Display '+color,'displaycolor':color+'ff'})
            rgb=[int(color[i:i+2],16)/255 for i in (1,3,5)]
            positions=[tuple(mesh['v'][i+j]+origin[j] for j in range(3)) for i in range(0,len(mesh['v']),3)]
            for t in range(0,len(mesh['t']),3):
                triangle=[];obj_triangle=[]
                for source in mesh['t'][t:t+3]:
                    point=positions[source]
                    if point not in lookup:lookup[point]=len(vertices);vertices.append(point)
                    triangle.append(lookup[point]);key=point+tuple(rgb)
                    if key not in obj_lookup:obj_lookup[key]=len(obj_vertices);obj_vertices.append(key)
                    obj_triangle.append(obj_lookup[key]+offset)
                triangles.append((triangle,palette[color]));obj_faces.append(obj_triangle)
        if not triangles:raise ValueError('Native body has no exportable mesh triangles.')
        resource=ET.SubElement(resources,node('object'),{'id':str(index+2),'type':'model','name':body['name'],'pid':'1','pindex':'0'})
        mesh_xml=ET.SubElement(resource,node('mesh'));vertex_xml=ET.SubElement(mesh_xml,node('vertices'));face_xml=ET.SubElement(mesh_xml,node('triangles'))
        for point in vertices:ET.SubElement(vertex_xml,node('vertex'),{key:format(value,'.15g') for key,value in zip(('x','y','z'),point)})
        for (a,b,c),color in triangles:
            ET.SubElement(face_xml,node('triangle'),{'v1':str(a),'v2':str(b),'v3':str(c),'pid':'1','p1':str(color),'p2':str(color),'p3':str(color)})
            pa,pb,pc=(App.Vector(*vertices[i]) for i in (a,b,c));volume+=pa.dot(pb.cross(pc))/6
        ET.SubElement(build,node('item'),{'objectid':str(index+2)})
        label=body['name'].replace('\r',' ').replace('\n',' ');obj_lines.append('o '+label)
        obj_lines.extend('v '+' '.join(format(v,'.15g') for v in point) for point in obj_vertices)
        obj_lines.extend('f '+' '.join(map(str,face)) for face in obj_faces);offset+=len(obj_vertices)
    (directory/'part.obj').write_text('\n'.join(obj_lines)+'\n')
    types=b'<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/></Types>'
    relations=b'<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rel0" Target="/3D/3dmodel.model" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>'
    with zipfile.ZipFile(directory/'part.3mf','w',compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('[Content_Types].xml',types);archive.writestr('_rels/.rels',relations);archive.writestr('3D/3dmodel.model',ET.tostring(model,encoding='utf-8',xml_declaration=True))
    return {'triangles':total,'mesh_volume_mm3':volume,'units':'mm','OBJ_color':'RGB vertex extension','3MF_color':'core display materials, not a printer material assignment','texture_maps':False}


def main(job):
    directory, program = Path(job['directory']), job['program']
    doc = App.newDocument('OpenFabroMechanical')
    try:
        shapes, objects, findings, metadata, imported, components, assembly_reports, sketch_reports = {}, {}, [], {}, {}, {}, {}, {}
        parameter_object=freecad_sketch.parameters(doc,job['source']) if any(item['op']=='sketch' for item in program['features']) else None
        for item in program['features']:
            try:
                native_object=None
                if item['op']=='import':
                    filename=job.get('imports',{}).get(item['asset_id'])
                    if not filename:raise ValueError('The imported project CAD dependency is unavailable.')
                    source_doc=App.newDocument('OpenFabroDependency')
                    try:
                        imported[item['id']]=load_geometry(filename,source_doc,item.get('bodies'))
                    finally:App.closeDocument(source_doc.Name)
                special_metadata=None
                if item['op']=='sketch':
                    source=next(feature for feature in job['source']['features'] if feature['id']==item['id']);native_object,shape,sketch_reports[item['id']]=freecad_sketch.build(doc,item,source,parameter_object)
                elif item['op']=='extrude_shape' and objects[item['target']].TypeId=='Sketcher::SketchObject':
                    native_object=doc.addObject('Part::Extrusion',item['id']);native_object.Base=objects[item['target']];native_object.DirMode='Custom';native_object.Dir=V(*item['vector']);native_object.Solid=True
                    source=next(feature for feature in job['source']['features'] if feature['id']==item['id'])
                    for axis,value in zip('xyz',source['vector']):
                        formula=freecad_sketch.expression(value,parameter_object)
                        if formula:native_object.setExpression('Dir.'+axis,formula)
                    doc.recompute();shape=native_object.Shape
                elif item['op']=='component':
                    value=assembly_component(item,job.get('component_files',{}).get(item['id']),job.get('component_evidence',{}).get(item['id'],{}))
                    if 'material' in item:value['bodies']=materials.apply(value['bodies'],item['material'])
                    components[item['id']]=value
                    shape=placed(value['local'],value['pose']);special_metadata=member_bodies(value)
                elif item['op']=='assembly':shape,special_metadata,assembly_reports[item['id']]=solve_assembly(item,shapes,metadata,components)
                else:shape = feature(item, shapes, imported)
                proof = measures(shape,allow_curves=item['op']=='sketch') if item['op'] in ('import','sketch') else metrics(shape)
            except Exception as error:
                raise ValueError('Feature '+item['id']+' ('+item['op']+') failed: '+str(error)) from error
            obj = native_object or doc.addObject('Part::Feature', item['id'])
            obj.Label = item.get('label') or item['id']
            if native_object is None:obj.Shape = shape
            obj.addProperty('App::PropertyString', 'CADOperation', 'OpenFabro')
            obj.CADOperation = json.dumps(item, sort_keys=True)
            if obj.ViewObject:
                obj.ViewObject.Visibility = False
            shapes[item['id']], objects[item['id']] = shape, obj
            if item['op']=='sketch':metadata[item['id']]=[]
            elif special_metadata is not None:metadata[item['id']]=special_metadata
            elif item['op']=='import':metadata[item['id']]=imported[item['id']]
            elif item['op']=='material':metadata[item['id']]=metadata[item['target']]
            else:metadata[item['id']]=body_metadata(shape,item,metadata.get(item.get('target'),[]),program['name'])
            if 'material' in item:metadata[item['id']]=materials.apply(metadata[item['id']],item['material'],item.get('bodies'),item.get('faces'))
            findings.append({'id': item['id'], 'op': item['op'], **proof})
        final = objects[program['result']]
        shape, result = final.Shape, metrics(final.Shape)
        final.Label = program['name']
        final.addProperty('App::PropertyString', 'EditableCADSource', 'OpenFabro')
        final.EditableCADSource = json.dumps(job['source'], ensure_ascii=False, indent=2)
        if final.ViewObject:
            final.ViewObject.Visibility = True
        doc.recompute()
        bodies=metadata[program['result']]
        faceted_input=any(body.get('source_geometry')=='triangle-mesh' for rows in imported.values() for body in rows) or any(body.get('source_geometry')=='triangle-mesh' for body in bodies)
        if faceted_input:
            bodies=[{**body,'source_geometry':'triangle-mesh'} for body in bodies]
        if 'material' in program:bodies=materials.apply(bodies,program['material'])
        if materials.appearances(bodies):
            final.addProperty('App::PropertyString','MaterialAssignments','OpenFabro');final.MaterialAssignments=json.dumps(materials.appearances(bodies),sort_keys=True)
        scene,triangle_count=make_scene(bodies,'native-freecad-mechanical')
        (directory/'scene.json').write_text(json.dumps(scene, separators=(',', ':')))
        # Export names live in a separate document so existing feature labels
        # cannot silently add numeric suffixes to the final body names.
        export_doc=App.newDocument('OpenFabroExport')
        export_objects=[]
        for i,body in enumerate(bodies):
            obj=export_doc.addObject('Part::Feature','ExportBody'+str(i));obj.Label=body['name']
            # Translated partner cap faces can receive the same XCAF style target.
            # Give export faces independent topology; verify against original below.
            obj.Shape=Part.makeSolid(Part.makeShell([face.copy() for face in body['shape'].Faces]))
            export_objects.append((obj,[tuple(float(n) for n in color) for color in body['face_colors']]))
        try:Import.export(export_objects, str(directory/'part.step'),legacy=False,keepPlacement=True)
        finally:App.closeDocument(export_doc.Name)
        step = metrics(Part.read(str(directory/'part.step')))
        if step['solids'] != result['solids'] or abs(step['volume_mm3']-result['volume_mm3']) > max(1e-6, result['volume_mm3']*1e-7) or any(abs(a-b)>1e-4 for key in ('size_mm','origin_mm') for a,b in zip(step[key],result[key])):
            raise ValueError('Exported STEP geometry differs from the built solid.')
        check_doc=App.newDocument('OpenFabroRoundtrip')
        try:
            restored=load_geometry(str(directory/'part.step'),check_doc)
            if len(restored)!=len(bodies) or any(a['name']!=b['name'] or a['color']!=b['color'] or not face_colors_match(a,b) or
                    any(abs(x-y)>1e-4 for key in ('size_mm','origin_mm') for x,y in zip(measures(a['shape'])[key],measures(b['shape'])[key]))
                    for a,b in zip(bodies,restored)):
                raise ValueError('Exported STEP body names, colors or world positions differ from the model.')
        finally:App.closeDocument(check_doc.Name)
        shape.exportStl(str(directory/'part.stl'))
        mesh_proof=mesh_exports(directory,bodies)
        doc.saveAs(str(directory/'part.FCStd'))
        return {'ok': True, 'name': program['name'], 'parameters': program['parameters'], **result,
                'features': findings, 'triangles': triangle_count, 'step_roundtrip': step,
                'bodies':[describe(b) for b in bodies],'step_metadata_verified':True,'step_face_colors_verified':True,
                'geometry_provenance':'faceted-mesh-input' if faceted_input else 'native-brep',
                'mesh_exports':mesh_proof,
                **({'material_assignments':materials.appearances(bodies)} if materials.appearances(bodies) else {}),
                **({'assembly':assembly_reports[program['result']]} if program['result'] in assembly_reports else {}),
                **({'sketches':sketch_reports} if sketch_reports else {}),
                'freecad_version': '.'.join(App.Version()[:3])}
    finally:
        App.closeDocument(doc.Name)


if os.environ.get('OPENFABRO_MECHANICAL_JOB'):
    with open(os.environ['OPENFABRO_MECHANICAL_JOB'], encoding='utf-8') as handle:
        job = json.load(handle)
    try:
        result = main(job)
    except Exception as error:
        result = {'ok': False, 'error': str(error), 'trace': traceback.format_exc()}
    with open(Path(job['directory'])/'report.json', 'w', encoding='utf-8') as output:
        json.dump(result, output)
