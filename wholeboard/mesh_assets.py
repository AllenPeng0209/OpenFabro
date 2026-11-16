"""Offline mesh ingestion into a bounded, millimeter/Z-up interchange snapshot.

Original files remain authoritative. Mesh topology and a faceted BRep derived from
it are distinct from the analytic surfaces of a STEP/IGES original.
"""
from __future__ import annotations

import base64
import io
import json
import math
import posixpath
from pathlib import PurePosixPath
import re
import shlex
import struct
from urllib.parse import unquote,urlsplit

import numpy as np
from PIL import Image
import trimesh

FORMATS={'stl','obj','glb','gltf'}
TRIANGLE_LIMIT=500_000
SOLID_TRIANGLE_LIMIT=20_000
BODY_LIMIT=256
BYTE_LIMIT=20_000_000
UNIT_SCALE={'mm':1.,'cm':10.,'m':1000.,'in':25.4}


def resource_name(value):
    if not isinstance(value,str) or not value or len(value)>240 or any(c in value for c in '\\\0\r\n'):
        raise ValueError('Use a relative mesh resource path.')
    parsed=urlsplit(value)
    if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment:raise ValueError('External mesh resource URLs are not supported; include the file.')
    value=unquote(value);path=PurePosixPath(value)
    if path.is_absolute() or any(p in ('.','..') for p in value.split('/')) or ':' in value or not path.parts:
        raise ValueError('Mesh resource paths must remain relative to the uploaded files.')
    return path.as_posix()


def relative_resource(uri,entry_path):
    if not isinstance(uri,str) or urlsplit(uri).scheme or uri.startswith('/') or '\\' in uri or '\0' in uri:raise ValueError('Use a relative uploaded mesh resource path.')
    parsed=urlsplit(uri)
    if parsed.netloc or parsed.query or parsed.fragment:raise ValueError('Use a relative uploaded mesh resource path.')
    return resource_name(posixpath.normpath(str(PurePosixPath(entry_path).parent/unquote(uri))))


def _resource(uri,resources,entry_path='model'):
    if uri.startswith('data:'):
        if ';base64,' not in uri:raise ValueError('Use a base64 mesh data resource.')
        try:data=base64.b64decode(uri.split(',',1)[1],validate=True)
        except Exception as error:raise ValueError('Invalid mesh data resource.') from error
        if len(data)>BYTE_LIMIT:raise ValueError('Embedded mesh resource exceeds 20 MB.')
        return data
    name=relative_resource(uri,entry_path)
    if name not in resources:raise ValueError('Missing mesh resource: '+name)
    return resources[name]


def _gltf(raw,fmt,resources,entry_path):
    binary=None
    if fmt=='glb':
        if len(raw)<20:raise ValueError('GLB header is incomplete.')
        magic,version,length=struct.unpack_from('<III',raw)
        if magic!=0x46546c67 or version!=2 or length!=len(raw):raise ValueError('Use a valid glTF 2 GLB file.')
        offset=12;tree=None
        while offset<len(raw):
            if offset+8>len(raw):raise ValueError('GLB chunk header is incomplete.')
            size,kind=struct.unpack_from('<II',raw,offset);offset+=8
            if size%4 or offset+size>len(raw):raise ValueError('GLB chunk length is invalid.')
            chunk=raw[offset:offset+size];offset+=size
            if kind==0x4e4f534a:
                if tree is not None:raise ValueError('GLB contains duplicate JSON chunks.')
                tree=json.loads(chunk)
            elif kind==0x004e4942:
                if binary is not None:raise ValueError('GLB contains duplicate binary chunks.')
                binary=chunk
        if tree is None:raise ValueError('GLB has no JSON chunk.')
    else:tree=json.loads(raw)
    if not isinstance(tree,dict) or not isinstance(tree.get('asset'),dict) or tree['asset'].get('version')!='2.0':raise ValueError('Use a glTF 2.0 mesh asset.')
    for key in ('nodes','scenes','meshes','buffers','bufferViews','accessors','images','materials'):
        if key in tree and (not isinstance(tree[key],list) or any(not isinstance(item,dict) for item in tree[key])):raise ValueError('Invalid glTF '+key+' array.')
    if tree.get('skins') or tree.get('animations'):raise ValueError('Import a static mesh pose; skinned/animated geometry is not evaluated yet.')
    if tree.get('extensionsRequired'):raise ValueError('Mesh requires unsupported glTF extensions: '+', '.join(tree['extensionsRequired']))
    if len(tree.get('nodes',[]))>4096 or len(tree.get('materials',[]))>2048:raise ValueError('glTF exceeds the node/material budget.')
    elements=0
    widths={'SCALAR':1,'VEC2':2,'VEC3':3,'VEC4':4,'MAT2':4,'MAT3':9,'MAT4':16}
    for accessor in tree.get('accessors',[]):
        count=accessor.get('count');width=widths.get(accessor.get('type'))
        if type(count) is not int or not 0<count<=1_500_000 or width is None:raise ValueError('glTF accessor count exceeds the mesh budget.')
        elements+=count*width
        if elements>12_000_000:raise ValueError('glTF accessor data exceeds the mesh budget.')
    resolver=dict(resources)
    for i,buffer in enumerate(tree.get('buffers',[])):
        data=_resource(buffer['uri'],resources,entry_path) if 'uri' in buffer else binary if i==0 else None
        size=buffer.get('byteLength')
        if data is None or type(size) is not int or not 0<=size<=len(data):raise ValueError('Missing or truncated glTF buffer resource.')
        name='openfabro-buffer-'+str(i)+'.bin';resolver[name]=data[:size];buffer['uri']=name
    for i,image in enumerate(tree.get('images',[])):
        if 'uri' in image:
            data=_resource(image['uri'],resources,entry_path);_checked_image(data);name='openfabro-image-'+str(i);resolver[name]=data;image['uri']=name
        elif 'bufferView' in image:
            view=tree.get('bufferViews',[])[image['bufferView']];buffer=tree['buffers'][view['buffer']];data=resolver[buffer['uri']];start=view.get('byteOffset',0);_checked_image(data[start:start+view['byteLength']])
    original_materials={}
    for i,material in enumerate(tree.get('materials',[])):
        key='openfabro-material-'+str(i);original_materials[key]=dict(material);material['name']=key
    original_nodes={}
    for i,node in enumerate(tree.get('nodes',[])):
        if 'skin' in node or node.get('weights'):raise ValueError('Import a static mesh without skin or morph deformation.')
        key='openfabro-node-'+str(i);original_nodes[key]={'name':node.get('name') or 'Body '+str(i+1),'index':i};node['name']=key
    return json.dumps(tree).encode(),resolver,original_materials,original_nodes


def _checked_image(raw):
    try:
        image=Image.open(io.BytesIO(raw))
        if image.width*image.height>16_777_216:raise ValueError('Mesh texture exceeds 16 megapixels.')
        image.load();return image
    except (OSError,Image.DecompressionBombError) as error:raise ValueError('Invalid mesh texture resource.') from error


def _obj_resources(raw,resources,entry_path):
    try:text=raw.decode('utf-8-sig')
    except UnicodeError as error:raise ValueError('Use UTF-8 OBJ geometry.') from error
    result=[];resolver=dict(resources)
    for line in text.splitlines():
        if line.strip().startswith('mtllib '):
            replacements=[]
            for name in shlex.split(line.strip())[1:]:
                key=relative_resource(name,entry_path);material=_resource(key,resources)
                try:lines=material.decode('utf-8-sig').splitlines()
                except UnicodeError as error:raise ValueError('Use UTF-8 material resources.') from error
                rewritten=[]
                for entry in lines:
                    words=shlex.split(entry,comments=True)
                    if words and words[0].lower() in ('map_kd','map_ka','map_ks','map_d','map_bump','bump','norm'):
                        if len(words)<2:raise ValueError('Missing texture resource in OBJ material.')
                        texture=relative_resource(words[-1],key);data=_resource(texture,resources);_checked_image(data)
                        alias='openfabro-texture-'+str(len(resolver))+'.png';resolver[alias]=data;words[-1]=alias;entry=' '.join(words)
                    rewritten.append(entry)
                alias='openfabro-material-'+str(len(resolver))+'.mtl';resolver[alias]='\n'.join(rewritten).encode();replacements.append(alias)
            result.append('mtllib '+' '.join(replacements))
        else:result.append(line)
    return '\n'.join(result).encode(),resolver


def _srgb(value):
    return 12.92*value if value<=.0031308 else 1.055*value**(1/2.4)-.055


def _linear(value):return value/12.92 if value<=.04045 else ((value+.055)/1.055)**2.4


def _hex(rgb):return '#'+''.join(f'{int(math.floor(max(0,min(1,float(v)))*255+.5)):02x}' for v in rgb[:3])


def _material(material,originals,gltf):
    source=originals.get(getattr(material,'name',None),{})
    pbr=source.get('pbrMetallicRoughness',{})
    if gltf:factor=pbr.get('baseColorFactor',[1,1,1,1])
    elif hasattr(material,'baseColorFactor'):factor=np.asarray(material.baseColorFactor if material.baseColorFactor is not None else [255]*4,dtype=float)/255
    else:factor=getattr(material,'kwargs',{}).get('kd',np.asarray(getattr(material,'diffuse',[166,181,192,255]),dtype=float)[:3]/255)
    factor=[float(v) for v in factor]
    if len(factor)==3:factor.append(float(np.asarray(getattr(material,'diffuse',[255]*4))[3])/255)
    if len(factor)!=4 or any(not math.isfinite(v) or not 0<=v<=1 for v in factor):raise ValueError('Invalid mesh base color.')
    rgb=[_srgb(v) for v in factor[:3]] if gltf else factor[:3]
    image=getattr(material,'baseColorTexture',None) if gltf else getattr(material,'image',None)
    alpha_mode=source.get('alphaMode','OPAQUE') if gltf else 'BLEND'
    opacity=1. if alpha_mode=='OPAQUE' else factor[3]
    result={'color':_hex(rgb),'rgba':rgb+[opacity],'opacity':opacity,'transparent':alpha_mode=='BLEND' and (gltf or opacity<1),
            'alpha_test':float(source.get('alphaCutoff',.5)) if alpha_mode=='MASK' else 0.,
            'material_name':source.get('name') or getattr(material,'name',None),
            'roughness':float(pbr.get('roughnessFactor',1)) if gltf else float(getattr(material,'roughnessFactor',None) if getattr(material,'roughnessFactor',None) is not None else .72),
            'metalness':float(pbr.get('metallicFactor',1)) if gltf else float(getattr(material,'metallicFactor',0) or 0)}
    if image is not None:
        if image.width*image.height>16_777_216:raise ValueError('Mesh texture exceeds 16 megapixels.')
        stream=io.BytesIO();image.save(stream,format='PNG');data=stream.getvalue()
        if len(data)>BYTE_LIMIT:raise ValueError('Mesh preview texture exceeds 20 MB.')
        result['texture']='data:image/png;base64,'+base64.b64encode(data).decode()
        result['_image']=image.convert('RGBA')
    return result


def _components(vertices,faces):
    # Weld topology without changing the preview's separate UV/color vertices.
    mesh=trimesh.Trimesh(vertices=vertices,faces=faces,process=False);mesh.merge_vertices()
    parent=list(range(len(mesh.faces)));owner={}
    def find(n):
        while parent[n]!=n:parent[n]=parent[parent[n]];n=parent[n]
        return n
    for index,face in enumerate(mesh.faces):
        for start,end in zip(face,np.roll(face,-1)):
            edge=tuple(sorted((int(start),int(end))))
            old=owner.setdefault(edge,index);a,b=find(index),find(old)
            if a!=b:parent[a]=b
    groups={}
    for i in range(len(mesh.faces)):groups.setdefault(find(i),[]).append(i)
    return list(groups.values())


def convert(name,raw,*,resources=None,units='mm',entry_path=None):
    fmt=name.rsplit('.',1)[-1].lower();resources=dict(resources or {})
    if fmt not in FORMATS:raise ValueError('Supported mesh assets: STL, OBJ, GLB and GLTF.')
    if units not in UNIT_SCALE:raise ValueError('Mesh units must be mm, cm, m or in.')
    if not isinstance(raw,bytes) or not raw or len(raw)>BYTE_LIMIT:raise ValueError('Use a mesh file smaller than 20 MB.')
    if len(resources)>128 or sum(len(v) for v in resources.values())+len(raw)>BYTE_LIMIT:raise ValueError('Mesh and companion resources exceed 20 MB.')
    resources={resource_name(k):v for k,v in resources.items()}
    entry_path=resource_name(entry_path or name)
    materials={};nodes={};gltf=fmt in ('glb','gltf')
    try:
        if gltf:data,resolver,materials,nodes=_gltf(raw,fmt,resources,entry_path);loader_type='gltf'
        else:
            data,resolver=_obj_resources(raw,resources,entry_path) if fmt=='obj' else (raw,resources)
            loader_type=fmt
        scene=trimesh.load_scene(io.BytesIO(data),file_type=loader_type,resolver=resolver,allow_remote=False,
                                 process=False,merge_primitives=True,group_material=False,maintain_order=fmt!='obj',ignore_broken=False)
    except ValueError:raise
    except Exception as error:raise ValueError('Could not decode mesh geometry or resources: '+str(error)) from error
    conversion=np.array([[1000,0,0,0],[0,0,-1000,0],[0,1000,0,0],[0,0,0,1]],dtype=float) if gltf else np.diag([UNIT_SCALE[units]]*3+[1.])
    bodies=[];triangles=0;has_texture=False
    ordered=sorted(scene.graph.nodes_geometry,key=lambda node:(nodes.get(node,{}).get('index',10**9),str(node)))
    for node in ordered:
        transform,geometry=scene.graph.get(node);original=scene.geometry[geometry]
        if not isinstance(original,trimesh.Trimesh):raise ValueError('Import mesh faces, not point clouds or curves.')
        mesh=original.copy();mesh.apply_transform(conversion@transform)
        vertices=np.asarray(mesh.vertices,dtype=float);faces=np.asarray(mesh.faces,dtype=int)
        triangles+=len(faces)
        if not len(faces) or triangles>TRIANGLE_LIMIT or len(vertices)>1_500_000:raise ValueError('Mesh exceeds the preview budget or contains no triangles.')
        if not np.isfinite(vertices).all() or np.abs(vertices).max()>20000:raise ValueError('Mesh coordinates exceed supported millimeter bounds.')
        if np.any(np.linalg.norm(np.cross(vertices[faces[:,1]]-vertices[faces[:,0]],vertices[faces[:,2]]-vertices[faces[:,0]]),axis=1)<1e-12):raise ValueError('Mesh contains degenerate triangles.')
        visual=original.visual;material=getattr(visual,'material',None);available=getattr(material,'materials',None) or [material]
        appearances=[_material(m,materials,gltf) for m in available]
        face_materials=getattr(visual,'face_materials',None)
        if face_materials is None:face_materials=np.zeros(len(faces),dtype=int)
        else:face_materials=np.asarray(face_materials,dtype=int)
        uv=getattr(visual,'uv',None)
        vertex_colors=None
        if visual.kind=='vertex':vertex_colors=np.asarray(visual.vertex_colors,dtype=float)[:,:3]/255
        elif getattr(visual,'vertex_attributes',None) is not None and 'color' in visual.vertex_attributes:
            vertex_colors=np.asarray(visual.vertex_attributes['color'],dtype=float)[:,:3]
            if vertex_colors.max()>1:vertex_colors/=255
        if vertex_colors is not None and len(vertex_colors)!=len(vertices):raise ValueError('Mesh vertex color count differs from its vertices.')
        groups=_components(vertices,faces)
        for group in groups:
            if len(bodies)>=BODY_LIMIT:raise ValueError('Mesh exceeds 256 separate bodies.')
            ids=np.asarray(group,dtype=int);part_faces=faces[ids];topology=trimesh.Trimesh(vertices=vertices,faces=part_faces,process=False);topology.merge_vertices()
            used=np.unique(part_faces);bounds=np.array([vertices[used].min(axis=0),vertices[used].max(axis=0)])
            watertight=bool(topology.is_watertight);winding=bool(topology.is_winding_consistent)
            volume=abs(float(topology.volume)) if watertight and winding else None
            label=nodes.get(node,{}).get('name',str(node))+(f' / {len(bodies)+1}' if len(groups)>1 else '')
            used,remapped=np.unique(part_faces.reshape(-1),return_inverse=True)
            body={'body_id':len(bodies),'name':label,'kind':'mesh','geometry_kind':'triangle-mesh','watertight':watertight,'winding_consistent':winding,
                  'can_make_solid':watertight and winding and len(ids)<=SOLID_TRIANGLE_LIMIT,'volume_mm3':volume,
                  'origin_mm':bounds[0].tolist(),'size_mm':(bounds[1]-bounds[0]).tolist(),'area_mm2':float(topology.area),
                  'triangles':len(ids),'faces':len(ids),'color':appearances[0]['color'],'vertices':vertices[used].tolist(),'indices':remapped.reshape(-1,3).tolist(),
                  'preview_meshes':[],'face_colors':[]}
            for face_index in ids:
                appearance=appearances[int(face_materials[face_index])];rgba=list(appearance['rgba'])
                if appearance.get('_image') is not None:
                    if uv is None:raise ValueError('Textured mesh has no UV coordinates.')
                    image=appearance['_image'];u,v=np.asarray(uv)[faces[face_index]].mean(axis=0);pixel=np.asarray(image.getpixel((min(image.width-1,int((u%1)*image.width)),min(image.height-1,int(((1-v)%1)*image.height)))),dtype=float)/255
                    rgba[:3]=[_srgb(_linear(a)*_linear(b)) if gltf else a*b for a,b in zip(rgba[:3],pixel[:3])];rgba[3]*=pixel[3]
                if vertex_colors is not None:
                    values=vertex_colors[faces[face_index]].mean(axis=0)
                    if visual.kind=='vertex' and material is None:rgba=[1,1,1,1]
                    rgba[:3]=[_srgb(_linear(a)*b) if gltf else a*b for a,b in zip(rgba[:3],values)]
                body['face_colors'].append(rgba)
            body['color']=_hex(body['face_colors'][0])
            for material_index in sorted(set(int(face_materials[i]) for i in ids)):
                appearance=appearances[material_index];chosen=[i for i in ids if int(face_materials[i])==material_index]
                preview_used,preview_indices=np.unique(faces[chosen].reshape(-1),return_inverse=True)
                preview={'name':label,'body_id':body['body_id'],'group':'mechanical','v':vertices[preview_used].reshape(-1).tolist(),'t':preview_indices.tolist(),
                         **{k:v for k,v in appearance.items() if k!='rgba' and not k.startswith('_')}}
                if vertex_colors is not None:
                    preview['c']=(vertex_colors[preview_used] if gltf else np.vectorize(_linear)(vertex_colors[preview_used])).reshape(-1).tolist()
                    if visual.kind=='vertex' and material is None:preview['color']='#ffffff'
                if appearance.get('texture'):
                    if uv is None:raise ValueError('Textured mesh has no UV coordinates.')
                    preview['uv']=np.asarray(uv)[preview_used].reshape(-1).tolist();has_texture=True
                body['preview_meshes'].append(preview)
            bodies.append(body)
    if not bodies:raise ValueError('Mesh asset contains no displayable bodies.')
    return {'schema':1,'units':'mm','source_units':'m' if gltf else units,'units_assumed':not gltf,'source_up_axis':'Y' if gltf else 'Z',
            'geometry_kind':'triangle-mesh','loader':'trimesh '+trimesh.__version__,'bodies':bodies,
            'appearance':{'textures_preserved':has_texture,'native_edit_appearance':'per-face approximation'}}


def inspection(canonical):
    bodies=canonical['bodies'];minimum=[min(b['origin_mm'][i] for b in bodies) for i in range(3)];maximum=[max(b['origin_mm'][i]+b['size_mm'][i] for b in bodies) for i in range(3)];size=[maximum[i]-minimum[i] for i in range(3)]
    meshes=[]
    for body in bodies:
        for mesh in body['preview_meshes']:
            meshes.append({**mesh,'v':[value-minimum[i%3] for i,value in enumerate(mesh['v'])]})
    public=[{k:v for k,v in body.items() if k not in ('vertices','indices','preview_meshes','face_colors')} for body in bodies]
    volume=sum(b['volume_mm3'] for b in bodies) if all(b['volume_mm3'] is not None for b in bodies) else None
    return ({'ok':True,'valid':True,'validation':'mesh-topology','geometry_kind':'triangle-mesh','units':'mm','source_units':canonical['source_units'],
            'units_assumed':canonical['units_assumed'],'origin_mm':minimum,'size_mm':size,'solids':0,
            'closed_mesh_bodies':sum(b['watertight'] for b in bodies),'faces':sum(b['triangles'] for b in bodies),'triangles':sum(b['triangles'] for b in bodies),
            'volume_mm3':volume,'area_mm2':sum(b['area_mm2'] for b in bodies),'bodies':public,'assembly_constraints_preserved':False,'appearance':canonical['appearance']},
           {'size':size,'origin':minimum,'source':'imported-triangle-mesh','geometry_kind':'triangle-mesh','meshes':meshes})
