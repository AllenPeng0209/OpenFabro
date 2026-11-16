"""Version-pinned assembly sources; no implicit ECAD or component rebuilds."""
from __future__ import annotations
import hashlib,json,re
from pathlib import Path

def digest(raw):return hashlib.sha256(raw).hexdigest()


def validate_source(value):
    if not isinstance(value,dict):raise ValueError('A component needs a source object.')
    kind=value.get('kind');allowed={'model':{'kind','path','asset_id'},'asset':{'kind','asset_id','bodies'},'board':{'kind'},'enclosure':{'kind','part'}}
    if kind not in allowed or set(value)-allowed[kind]:raise ValueError('Component source kind is model,asset,board or enclosure.')
    if kind=='model':
        path=value.get('path')
        if not isinstance(path,str) or len(path)>240 or not path.endswith('.cad.json') or Path(path).is_absolute() or any(p.startswith('.') for p in Path(path).parts):raise ValueError('Model components reference visible project CAD source paths.')
    if kind=='asset' or kind=='model' and 'asset_id' in value:
        if not isinstance(value.get('asset_id'),str) or not re.fullmatch('[0-9a-f]{64}(?:-[0-9a-f]{12})?',value['asset_id']):raise ValueError('Use a verified component asset identifier.')
    if 'bodies' in value and (not isinstance(value['bodies'],list) or not value['bodies'] or len(set(value['bodies']))!=len(value['bodies']) or any(type(n) is not int or not 0<=n<256 for n in value['bodies'])):raise ValueError('Choose unique component body indices.')
    if kind=='enclosure' and value.get('part') not in ('base','lid'):raise ValueError('Choose enclosure part base or lid.')
    return dict(value)


def dependency_key(item):return digest(('assembly-component:'+item['id']+':'+json.dumps(item['source'],sort_keys=True)).encode())


def _path(p,name):
    root=p.root.resolve();path=Path(name)
    if path.is_absolute():
        try:path=path.relative_to(root)
        except ValueError:raise ValueError('Assembly geometry must remain inside its project.') from None
    if not path.parts or any(part in ('.','..') for part in path.parts):raise ValueError('Invalid assembly geometry path.')
    target=root
    for part in path.parts:
        target=target/part
        if target.is_symlink():raise ValueError('Assembly geometry cannot use symbolic links.')
    if not target.is_file() or target.stat().st_size>100_000_000:raise ValueError('Use an existing bounded native component file.')
    return target


def _model(p,source,chain):
    from . import mechanical
    name=source['path'];mechanical._source_path(p,name)
    if name in chain or len(chain)>32:raise mechanical.MechanicalConflict('Cyclic or too-deep assembly model reference.')
    if 'asset_id' in source:
        folder=p.root.resolve()/'mechanical'/source['asset_id'];record=mechanical._record(p,folder)
        if record['source']!=name:raise mechanical.MechanicalConflict('The pinned model belongs to another CAD source.')
    else:
        stored=p.state.get('workbench_mechanical',{}).get(name)
        if not stored:raise ValueError('Build the component source before assembling it: '+name)
        record=mechanical._record(p,p.root.resolve()/'mechanical'/stored['asset_id'])
        _,raw,program=mechanical._source(p,name)
        if digest(raw)!=record['source_sha256']:raise mechanical.MechanicalConflict('Component source changed; rebuild it before assembly: '+name)
        from . import mechanical_assets
        resolved=mechanical.resolve(program)
        linked=mechanical_assets.dependencies(p,resolved)
        for feature in resolved['features']:
            if feature['op']=='component':linked[dependency_key(feature)]=resolve_source(p,feature['source'],chain+(name,))
        receipts={key:{k:v for k,v in value.items() if k!='bytes'} for key,value in linked.items()}
        if receipts!=record.get('imports',{}):raise mechanical.MechanicalConflict('Component dependencies changed; rebuild the nested assembly first: '+name)
    file=next(file for file in record['files'] if file['name']=='part.step');data=_path(p,file['path']).read_bytes()
    if digest(data)!=file['sha256']:raise mechanical.MechanicalConflict('Native component bytes changed after inspection.')
    fit=record['metrics'].get('assembly',{}).get('fit',{});complete=fit.get('complete',True)
    return data,{'kind':'model','path':name,'asset_id':record['asset_id'],'manifest_sha256':record['manifest_sha256'],'source_sha256':record['source_sha256'],'file_sha256':file['sha256'],'geometry_provenance':record['metrics'].get('geometry_provenance','native-brep'),'coverage_complete':complete,**({'appearance':record['metrics']['material_assignments']} if record['metrics'].get('material_assignments') else {}),**({'nested_coverage_warnings':fit.get('coverage_warnings',[])} if not complete else {})}


def resolve_source(p,source,chain=()):
    from . import mechanical,mechanical_assets,workbench_native
    source=validate_source(source);kind=source['kind']
    if kind=='model':
        data,receipt=_model(p,source,chain);return {'format':'step','bytes':data,**receipt}
    if kind=='asset':
        asset=mechanical_assets.read(p,source['asset_id']);data=_path(p,asset['native']['path']).read_bytes()
        if digest(data)!=asset['native']['sha256']:raise mechanical.MechanicalConflict('Imported component bytes changed.')
        return {'format':asset['native_format'],'bytes':data,'kind':'asset','asset_id':asset['asset_id'],'manifest_sha256':asset['manifest_sha256'],'file_sha256':digest(data),'geometry_provenance':asset.get('geometry_kind','native-brep'),'coverage_complete':True}
    from . import design_identity
    native=p.state.get('workbench_native') or {}
    if not native or not design_identity.matches(native,p.state.get('spec')):raise mechanical.MechanicalConflict('Saved PCB geometry is missing or stale; generate it before assembly.')
    version=p.state.get('workbench',{}).get('version',0)
    record=p.state.get('workbench_board3d' if kind=='board' else 'workbench_enclosure') or {}
    expected=record.get('source_sha' if kind=='board' else 'pcb_sha256');pcb=None
    for candidate in [workbench_native.final_pcb(p),native.get('pcb'),(p.state.get('artifacts') or {}).get('pcb')]:
        if not candidate:continue
        try:possible=_path(p,str(candidate))
        except ValueError:continue
        if digest(possible.read_bytes())==expected:pcb=possible;break
    if pcb is None:raise mechanical.MechanicalConflict('The native PCB bytes used by this component changed or are missing.')
    pcb_sha=expected
    if kind=='board':
        record=p.state.get('workbench_board3d') or {}
        if record.get('version')!=version or record.get('source_sha')!=pcb_sha:raise mechanical.MechanicalConflict('Native board3D is missing or stale; generate it for the saved PCB first.')
        file=_path(p,str(Path(record.get('scene_path','')).parent/'board.step'));data=file.read_bytes()
        if digest(data)!=record.get('step_sha'):raise mechanical.MechanicalConflict('Native board STEP hash changed.')
        return {'format':'step','bytes':data,'kind':'board','design_version':version,'pcb_sha256':pcb_sha,'file_sha256':digest(data),'geometry_provenance':'native-kicad-step','coverage_complete':not record.get('unmatched_components'),'unmatched_components':record.get('unmatched_components',[])}
    record=p.state.get('workbench_enclosure') or {};part=source['part']
    if record.get('version')!=version or record.get('pcb_sha256')!=pcb_sha:raise mechanical.MechanicalConflict('Enclosure geometry is missing or stale for the saved PCB.')
    if record.get('spec')!=p.state.get('enclosure_spec'):raise mechanical.MechanicalConflict('Enclosure settings changed; rebuild it before assembly.')
    file=_path(p,record.get('summary',{}).get('files',{}).get(part+'_step',''));data=file.read_bytes()
    return {'format':'step','bytes':data,'kind':'enclosure','part':part,'design_version':version,'pcb_sha256':pcb_sha,'file_sha256':digest(data),'spec_sha256':digest(json.dumps(record['spec'],sort_keys=True).encode()),'geometry_provenance':'native-freecad-enclosure','coverage_complete':True}


def dependencies(p,program,own_source=None):
    values={}
    for item in program['features']:
        if item['op']=='component':values[dependency_key(item)]=resolve_source(p,item['source'],(own_source,) if own_source else ())
    return values


def inventory(p):
    from . import mechanical,mechanical_assets
    sources=[]
    with p.lock:
        candidates=[({'kind':'model','path':name},record.get('name',name)) for name,record in p.state.get('workbench_mechanical',{}).items()]
        candidates += [({'kind':'asset','asset_id':row['asset_id']},row.get('name','Asset')) for row in mechanical_assets.listing(p)['assets'] if row.get('available')]
        if p.state.get('workbench_board3d'):candidates.append(({'kind':'board'},'PCB with components'))
        if p.state.get('workbench_enclosure'):candidates.extend(({'kind':'enclosure','part':part},'Enclosure '+part) for part in ('base','lid'))
        for source,label in candidates:
            try:
                value=resolve_source(p,source);sources.append({'source':source,'label':label,'available':True,**{k:v for k,v in value.items() if k not in ('bytes','format')}})
            except (ValueError,OSError) as error:sources.append({'source':source,'label':label,'available':False,'error':str(error)})
    return {'schema':1,'sources':sources,'units':'mm','assembly_checks':'Native inter-member solid intersections and minimum distance; missing component geometry is explicit.'}
