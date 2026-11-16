"""Immutable project CAD originals and native import inspection receipts."""
from __future__ import annotations

import base64
import binascii
import copy
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import tempfile
import threading
import time
import uuid
import zipfile

from . import enclosure, mechanical

LIMIT=20_000_000
FORMATS={'.step':'step','.stp':'step','.stpz':'stpz','.iges':'iges','.igs':'iges','.brep':'brep'}
FORMATS.update({'.'+name:name for name in ('stl','obj','glb','gltf')})
FORMATS.update({'.dxf':'dxf','.svg':'svg'})
_MODULE_BYTES=Path(__file__).read_bytes()


def sha(raw):return hashlib.sha256(raw).hexdigest()


def _payload(arguments):
    if not isinstance(arguments,dict) or set(arguments)-{'name','data','resources','units','entry_path','drawing_mode','layers'}:
        raise ValueError('Import a CAD file using name and base64 data.')
    name=arguments.get('name')
    if not isinstance(name,str) or not name.strip() or len(name)>200 or name in ('.','..') or any(c in name for c in '/\\\0'):
        raise ValueError('Choose a CAD file name without directory components.')
    fmt=FORMATS.get(Path(name).suffix.lower())
    if not fmt:raise ValueError('Supported imports: STEP/STP/STPZ, IGES/IGS, BREP, STL, OBJ, GLB/GLTF, DXF and SVG.')
    encoded=arguments.get('data')
    if not isinstance(encoded,str) or len(encoded)>(LIMIT+2)//3*4:
        raise ValueError('Import a CAD original smaller than 20 MB.')
    try:raw=base64.b64decode(encoded,validate=True)
    except (binascii.Error,ValueError) as error:raise ValueError('CAD upload must contain valid base64 data.') from error
    if not raw or len(raw)>LIMIT:raise ValueError('Import a nonempty CAD original smaller than 20 MB.')
    return name,fmt,raw


def _unpack(fmt,raw):
    if fmt!='stpz':return fmt,raw
    try:
        if zipfile.is_zipfile(io.BytesIO(raw)):
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                entries=[entry for entry in archive.infolist() if not entry.is_dir()]
                if len(entries)!=1:raise ValueError('Compressed STEP must contain exactly one STEP file.')
                entry=entries[0];rel=Path(entry.filename)
                if rel.is_absolute() or any(n.startswith('.') for n in rel.parts) or '\\' in entry.filename or entry.file_size>LIMIT:
                    raise ValueError('Invalid compressed STEP entry or expanded size.')
                with archive.open(entry) as handle:expanded=handle.read(LIMIT+1)
        else:
            with gzip.GzipFile(fileobj=io.BytesIO(raw)) as handle:expanded=handle.read(LIMIT+1)
        if not expanded or len(expanded)>LIMIT:raise ValueError('Expanded STEP exceeds 20 MB.')
        return 'step',expanded
    except (OSError,EOFError,zipfile.BadZipFile,RuntimeError) as error:raise ValueError('Invalid compressed STEP archive.') from error


def _root(p):
    folder=mechanical._output_root(p)/'assets'
    if folder.is_symlink():raise ValueError('CAD assets cannot use a symbolic directory.')
    folder.mkdir(exist_ok=True)
    return folder


def read(p,asset_id):
    if not isinstance(asset_id,str) or not re.fullmatch('[0-9a-f]{64}',asset_id):raise ValueError('Choose a valid imported CAD asset identifier.')
    folder=p.root.resolve()/'mechanical/assets'/asset_id
    if any(path.is_symlink() for path in (folder.parent.parent,folder.parent,folder,folder/'manifest.json')):
        raise mechanical.MechanicalConflict('Imported CAD asset path changed.')
    try:
        raw=(folder/'manifest.json').read_bytes()
        if sha(raw)!=p.state.get('mechanical_import_receipts',{}).get(asset_id):raise ValueError('manifest hash changed')
        value=json.loads(raw)
        if value.get('schema')!=1 or value.get('asset_id')!=asset_id:raise ValueError('manifest identity changed')
        required={'source.'+value['format'],'native.'+value['native_format'],'scene.json','report.json'}|set(value.get('resource_hashes',{}))|({value['bundle_file']} if value.get('bundle_file') else set())
        if set(value['hashes'])!=required:raise ValueError('asset file inventory changed')
        files=[]
        for name,digest in value['hashes'].items():
            path=folder/name
            if any(part.is_symlink() for part in path.parents if part!=folder.parent):raise ValueError('asset resource directory changed')
            if path.is_symlink() or not path.is_file() or path.stat().st_size>LIMIT*5 or sha(path.read_bytes())!=digest:raise ValueError('asset file hash changed: '+name)
            files.append({'name':name,'path':path.relative_to(p.root.resolve()).as_posix(),'sha256':digest,'url':p.file_url(path),'size':path.stat().st_size})
        original=next(f for f in files if f['name']=='source.'+value['format'])
        native=next(f for f in files if f['name']=='native.'+value['native_format'])
        return {**value,'manifest_sha256':sha(raw),'files':files,'original':original,'native':native,
                'resources':[f for f in files if f['name'] in value.get('resource_hashes',{})],
                'original_bundle':next((f for f in files if f['name']==value.get('bundle_file')),None),
                'scene_url':p.file_url(folder/'scene.json'),'report_url':p.file_url(folder/'report.json')}
    except (OSError,KeyError,ValueError,TypeError) as error:
        raise mechanical.MechanicalConflict('Imported CAD asset integrity changed: '+str(error)) from error


def listing(p):
    values=[]
    with p.lock:
        for asset_id in p.state.get('mechanical_import_receipts',{}):
            try:values.append({**read(p,asset_id),'available':True})
            except (OSError,ValueError) as error:values.append({'asset_id':asset_id,'available':False,'error':str(error)})
    return {'schema':1,'assets':values,'formats':list(FORMATS),'max_bytes':LIMIT}


def inspect_native(source,folder,*,command,cancel,adapter_bytes,log,topology_adapter=None,material_adapter=None,curve_adapter=None):
    folder=Path(folder);folder.mkdir()
    script=folder/'import_kernel.py';script.write_bytes(adapter_bytes)
    (folder/'freecad_topology.py').write_bytes(topology_adapter if topology_adapter is not None else Path(__file__).with_name('freecad_topology.py').read_bytes())
    (folder/'freecad_curve_events.py').write_bytes(curve_adapter if curve_adapter is not None else Path(__file__).with_name('freecad_curve_events.py').read_bytes())
    (folder/'mechanical_materials.py').write_bytes(material_adapter if material_adapter is not None else Path(__file__).with_name('mechanical_materials.py').read_bytes())
    job=folder/'job.json';job.write_text(json.dumps({'source':str(source),'directory':str(folder)}))
    mechanical._run_kernel(command,script,folder,{'OPENFABRO_IMPORT_JOB':str(job)},cancel,log)
    report_path=folder/'report.json'
    if not report_path.is_file():raise RuntimeError('FreeCAD produced no native import report.')
    report=json.loads(report_path.read_text())
    if not report.get('ok'):raise RuntimeError(report.get('error') or 'Native CAD import failed.')
    return report


def ingest(p,arguments):
    name,fmt,raw=_payload(arguments)
    native_fmt,native=_unpack(fmt,raw)
    from . import mesh_assets
    mesh=fmt in mesh_assets.FORMATS
    drawing=fmt in ('dxf','svg')
    resources={}
    if arguments.get('resources'):
        if not mesh or not isinstance(arguments['resources'],dict) or len(arguments['resources'])>128:raise ValueError('Use companion resources only for mesh assets.')
        for path,encoded in arguments['resources'].items():
            resource=mesh_assets.resource_name(path)
            if not isinstance(encoded,str) or len(encoded)>(LIMIT+2)//3*4:raise ValueError('Mesh resource exceeds 20 MB.')
            try:resources[resource]=base64.b64decode(encoded,validate=True)
            except (binascii.Error,ValueError) as error:raise ValueError('Mesh resources must be valid base64.') from error
        if sum(map(len,resources.values()))+len(raw)>LIMIT:raise ValueError('Mesh and companion resources exceed 20 MB.')
    units=arguments.get('units','auto' if drawing else 'mm')
    if fmt in ('glb','gltf'):units='m'
    entry_path=mesh_assets.resource_name(arguments.get('entry_path') or name)
    if entry_path in resources:raise ValueError('A companion resource duplicates the main model path.')
    if not mesh and not drawing and units!='mm':raise ValueError('Native CAD files contain their own units.')
    with p.lock:
        if p.engine_busy or p.worker and p.worker.is_alive() and p.worker is not threading.current_thread():
            raise mechanical.MechanicalConflict('Wait for the active run before importing CAD.')
        if p.inbox or p.worker is threading.current_thread() and p.cancel.is_set():raise mechanical.MechanicalConflict('CAD import canceled before starting.')
        command=enclosure.find_freecad()
        if not command and not mesh:raise RuntimeError('Install FreeCAD to import exact CAD geometry.')
        adapter=Path(__file__).with_name('freecad_import.py').read_bytes()
        topology_adapter=Path(__file__).with_name('freecad_topology.py').read_bytes()
        material_adapter=Path(__file__).with_name('mechanical_materials.py').read_bytes()
        curve_adapter=Path(__file__).with_name('freecad_curve_events.py').read_bytes()
        version=(enclosure.freecad_version(command) or 'unknown') if not mesh else 'mesh-topology'
        extra=Path(mesh_assets.__file__).read_bytes()+mesh_assets.trimesh.__version__.encode() if mesh else b''
        if drawing:
            from . import drawing_assets
            extra=Path(drawing_assets.__file__).read_bytes()+drawing_assets.ezdxf.__version__.encode()+drawing_assets.version('svgelements').encode()
        implementation=sha(_MODULE_BYTES+adapter+topology_adapter+material_adapter+curve_adapter+extra)
        inputs=json.dumps({'units':units,'entry_path':entry_path,'resources':{k:sha(v) for k,v in resources.items()},'drawing_mode':arguments.get('drawing_mode'),'layers':arguments.get('layers')},sort_keys=True).encode()
        asset_id=sha(f'cad-import:1:{fmt}:{implementation}:{version}:'.encode()+raw+inputs)
        root=_root(p);folder=root/asset_id
        if folder.exists():return read(p,asset_id)
        p.engine_busy=True;p.cancel.clear()
    try:
        p.set_status('running','Importing model: '+name)
        with tempfile.TemporaryDirectory(prefix='openfabro-import-') as temporary:
            staging=Path(temporary)
            output=staging/'inspection'
            if mesh:
                canonical=mesh_assets.convert(name,raw,resources=resources,units=units,entry_path=entry_path)
                native_fmt='mesh.json';native=json.dumps(canonical,separators=(',',':')).encode()
                report,scene=mesh_assets.inspection(canonical)
                output.mkdir();(output/'report.json').write_text(json.dumps(report));(output/'scene.json').write_text(json.dumps(scene,separators=(',',':')))
            else:
                if drawing:
                    canonical=drawing_assets.convert(name,raw,units=units,drawing_mode=arguments.get('drawing_mode'),layers=arguments.get('layers'))
                    native_fmt='drawing.json';native=json.dumps(canonical,separators=(',',':')).encode()
                source=staging/('native.'+native_fmt);source.write_bytes(native)
                report=inspect_native(source,output,command=command,cancel=p.cancel,adapter_bytes=adapter,topology_adapter=topology_adapter,material_adapter=material_adapter,curve_adapter=curve_adapter,log=lambda s:p.log('mechanical',s))
            with p.lock:
                if p.cancel.is_set() or p.inbox:raise mechanical.MechanicalConflict('CAD import canceled before publication.')
                if _root(p)!=root or folder.exists():raise mechanical.MechanicalConflict('CAD import destination changed.')
                publication=root/('.publish-'+uuid.uuid4().hex);publication.mkdir()
                state=copy.deepcopy(p.state)
                try:
                    payloads={'source.'+fmt:raw,'native.'+native_fmt:native,
                              'report.json':(output/'report.json').read_bytes(),'scene.json':(output/'scene.json').read_bytes()}
                    payloads.update({'resources/'+key:data for key,data in resources.items()})
                    if resources:
                        bundle=io.BytesIO()
                        with zipfile.ZipFile(bundle,'w',compression=zipfile.ZIP_DEFLATED) as archive:
                            archive.writestr(entry_path,raw)
                            for key,data in resources.items():archive.writestr(key,data)
                        payloads['originals.zip']=bundle.getvalue()
                    for filename,data in payloads.items():
                        target=publication/filename;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
                    value={'schema':1,'asset_id':asset_id,'name':name,'format':fmt,'native_format':native_fmt,'created_at':time.time(),
                           'source_sha256':sha(raw),'implementation_sha256':implementation,'freecad_version':version,
                           'metrics':{key:value for key,value in report.items() if key!='bodies'},'bodies':report['bodies'],
                           'hashes':{filename:sha(data) for filename,data in payloads.items()}}
                    if mesh:value.update(geometry_kind='triangle-mesh',entry_path=entry_path,bundle_file='originals.zip' if resources else None,resource_hashes={k:sha(v) for k,v in payloads.items() if k.startswith('resources/')},source_units=canonical['source_units'],units_assumed=canonical['units_assumed'],appearance=canonical['appearance'])
                    if drawing:value.update(geometry_kind='planar-drawing',source_units=canonical['source_units'],units_assumed=canonical['units_assumed'],drawing_mode=canonical['drawing_mode'],layers=canonical['layers'],diagnostics=canonical['diagnostics'])
                    (publication/'manifest.json').write_text(json.dumps(value,indent=2))
                    seal=sha((publication/'manifest.json').read_bytes())
                    publication.rename(folder)
                    p.state.setdefault('mechanical_import_receipts',{})[asset_id]=seal
                    record=read(p,asset_id);p.save()
                except Exception:
                    p.state=state
                    if folder.exists():shutil.rmtree(folder)
                    raise
                finally:
                    if publication.exists():shutil.rmtree(publication)
        mechanical._notify(p,{'type':'mechanical_imported','asset_id':asset_id})
        return record
    finally:
        with p.lock:p.engine_busy=False
        try:p.set_status('running' if p.worker is threading.current_thread() else 'idle','CAD import stopped.' if p.cancel.is_set() else 'CAD import finished.')
        except Exception:pass


def dependencies(p,program):
    """Pin both the trusted receipt and bytes, before cache lookup or execution."""
    result={}
    for feature in program['features']:
        if feature['op']=='import':
            asset=read(p,feature['asset_id'])
            if 'bodies' in feature and any(n>=len(asset['bodies']) for n in feature['bodies']):raise ValueError('An imported body index does not exist.')
            data=(p.root/asset['native']['path']).read_bytes()
            if sha(data)!=asset['native']['sha256']:raise mechanical.MechanicalConflict('Imported CAD dependency bytes changed after inspection.')
            result[asset['asset_id']]={'manifest_sha256':asset['manifest_sha256'],'native_sha256':asset['native']['sha256'],
                                      'format':asset['native_format'],'bytes':data}
    return result


def create_part(p,arguments):
    if not isinstance(arguments,dict) or set(arguments)-{'asset_id','path','name','bodies'}:raise ValueError('Use asset_id, new CAD path, optional name and body indices.')
    with p.lock:
        asset=read(p,arguments.get('asset_id'))
        target=mechanical._source_path(p,arguments.get('path'))
        if target.exists():raise mechanical.MechanicalConflict('Create the imported part at a new CAD source path.')
    feature={'id':'imported','op':'import','asset_id':asset['asset_id']}
    if 'bodies' in arguments:feature['bodies']=arguments['bodies']
    program={'schema':1,'units':'mm','name':arguments.get('name') or Path(asset['name']).stem,
             'parameters':{},'features':[feature],'result':'imported'}
    return mechanical.rebuild(p,{'path':arguments['path'],'program':program})


def extrude(p,arguments):
    if not isinstance(arguments,dict) or set(arguments)-{'asset_id','path','name','thickness','profiles'}:raise ValueError('Use asset_id,new CAD path,thickness,optional profile indices and name.')
    height=arguments.get('thickness')
    if type(height) not in (int,float) or not 1e-6<=height<=10000:raise ValueError('Use a positive drawing thickness within10000 mm.')
    with p.lock:
        asset=read(p,arguments.get('asset_id'))
        if asset.get('geometry_kind')!='planar-drawing':raise ValueError('Choose an imported DXF or SVG drawing.')
        target=mechanical._source_path(p,arguments.get('path'))
        if target.exists():raise mechanical.MechanicalConflict('Create the extruded drawing at a new CAD source path.')
        indices=arguments.get('profiles',[body['body_id'] for body in asset['bodies'] if body.get('can_extrude')])
        if not isinstance(indices,list) or not indices or len(set(indices))!=len(indices) or any(type(i) is not int or not 0<=i<len(asset['bodies']) or not asset['bodies'][i].get('can_extrude') for i in indices):raise ValueError('Select one or more closed drawing profiles; open curves are references.')
        normals=[asset['bodies'][i]['normal'] for i in indices];normal=normals[0]
        if any(sum((a-b)**2 for a,b in zip(normal,n))>1e-10 for n in normals):raise ValueError('Select profiles in parallel drawing planes for one extrusion.')
    program={'schema':1,'units':'mm','name':arguments.get('name') or Path(asset['name']).stem[:100],
             'parameters':{'thickness':{'value':height,'unit':'mm'}},
             'features':[{'id':'drawing','op':'import','asset_id':asset['asset_id'],'bodies':indices},
                         {'id':'solid','op':'extrude_shape','target':'drawing','vector':[f'thickness * {n:.15g}' for n in normal]}],'result':'solid'}
    return mechanical.rebuild(p,{'path':arguments['path'],'program':program})
