"""Bounded client display evidence captured with PCB pixels, never engineering validation."""
import hashlib
import json
import re
from pathlib import Path

APERTURES=('F.Mask','B.Mask','F.Paste','B.Paste')
FEATURES={'fills','polygons','pads','traces','vias'}
DISPLAY={'grid','ratsnest','refs','zoneOutlines','pads','vias','zones','outline','courtyards'}
COLLECTIONS={'footprints','pads','vias','tracks','arcs','drawings','outline','zone_definitions'}
MAX_BYTES=24_000


def encoded(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def validate(p,value,version,view,*,current=False):
    def require(ok,message='Use a valid frozen PCB layer context.'):
        if not ok:raise ValueError(message)
    def sha(value):return isinstance(value,str) and re.fullmatch('[0-9a-f]{64}',value)
    require(isinstance(value,dict))
    try:payload=encoded(value)
    except (TypeError,ValueError,RecursionError) as error:raise ValueError('Use a bounded JSON layer context.') from error
    require(len(payload)<=MAX_BYTES,'The frozen layer context is too large. Show more objects before capturing again.')
    require(set(value)=={'schema','project_id','design_version','view','native','focus','dim_opacity','layers','display','hidden_objects','apertures'})
    require(type(value['schema']) is int and value['schema']==1)
    require(view=='layout' and value['view']==view and value['project_id']==p.id and type(value['design_version']) is int and value['design_version']==version,
            'The frozen layer context belongs to another project, design version or view.')
    native=value['native'];require(isinstance(native,dict) and set(native)=={'source_version','pcb_sha256','render_inputs_sha256'})
    require(type(native['source_version']) is int and native['source_version']==version and sha(native['pcb_sha256']) and sha(native['render_inputs_sha256']))
    require(type(value['dim_opacity']) in (int,float) and value['dim_opacity']==0.2)
    layers=value['layers'];require(isinstance(layers,dict) and 1<=len(layers)<=96)
    for layer,row in layers.items():
        require(isinstance(layer,str) and re.fullmatch(r'[A-Za-z][A-Za-z0-9_.]{0,63}',layer) and isinstance(row,dict))
        copper=bool(re.fullmatch(r'(F|B|In\d+)\.Cu',layer))
        require(set(row)==({'visible','features'} if copper else {'visible'}) and type(row['visible']) is bool)
        if copper:require(isinstance(row['features'],dict) and set(row['features'])==FEATURES and all(type(v) is bool for v in row['features'].values()))
    display=value['display'];require(isinstance(display,dict) and set(display)==DISPLAY and all(type(v) is bool for v in display.values()))
    allowed_focus=set(layers)|DISPLAY|{'top','bottom','mechanical','filters'}|{l+'/'+f for l in layers if l.endswith('.Cu') for f in FEATURES}
    require(value['focus'] is None or isinstance(value['focus'],str) and value['focus'] in allowed_focus)
    hidden=value['hidden_objects'];require(isinstance(hidden,dict) and not set(hidden)-COLLECTIONS)
    count=0
    for ids in hidden.values():
        require(isinstance(ids,list) and all(isinstance(i,str) and 1<=len(i)<=128 for i in ids))
        require(ids==sorted(set(ids)));count+=len(ids)
    require(count<=256,'At most256 personally hidden native objects can be included in one marked image. Show more objects before capturing again.')
    apertures=value['apertures'];require(isinstance(apertures,list) and len(apertures)==4)
    require(all(isinstance(row,dict) for row in apertures))
    require([row.get('layer') for row in apertures]==list(APERTURES))
    for row in apertures:
        status=row.get('status');require(status in ('hidden','loading','waiting','error','unavailable','ready'))
        require(row['layer'] in layers and (status!='hidden')==layers[row['layer']]['visible'])
        if status=='ready':
            count_key='client_path_count' if 'client_path_count' in row else 'path_count'
            require(set(row)=={'layer','status',count_key,'svg_sha256','visibility_sha256'})
            require(type(row[count_key]) is int and 0<=row[count_key]<=1_000_000 and sha(row['svg_sha256']) and row['visibility_sha256']==digest(hidden))
        else:require(set(row)=={'layer','status'})
    if current:
        from . import workbench_native,design_identity
        final=workbench_native.final_pcb(p);cached=p.state.get('workbench_native') or {}
        path=final or Path(cached.get('pcb',''))
        require(path.is_file() and path.resolve().is_relative_to(p.root.resolve()) and (final or design_identity.matches(cached,p.state.get('spec'))),
                'The PCB behind this capture changed. Refresh Layout and start Markup again.')
        native_raw,inputs=workbench_native._plot_inputs(path)
        require(hashlib.sha256(native_raw['.kicad_pcb']).hexdigest()==native['pcb_sha256'] and inputs==native['render_inputs_sha256'],
                'The PCB behind this capture changed. Refresh Layout and start Markup again.')
        if hidden:
            from .kicad import geometry
            geo=geometry.read(path)
            require(all(set(ids)<={item['id'] for item in geo.get(kind,[])} for kind,ids in hidden.items()),
                    'A hidden object is not in this PCB. Refresh Layout and start Markup again.')
        for row in apertures:
            if row['status']=='ready':require(_export_exists(p,path,native,row),
                    'A captured aperture does not match an existing native export. Refresh Layout and start Markup again.')
    return json.loads(payload)


def _export_exists(p,pcb,native,row):
    try:
        cache=pcb.parent/'display-layers'/f'{native["render_inputs_sha256"]}-{row["visibility_sha256"]}-v1'
        if not cache.resolve().is_relative_to(p.root.resolve()):return False
        folders=sorted(cache.glob(row['layer'].replace('.','-')+'-*'),key=lambda f:f.stat().st_mtime_ns,reverse=True)[:32]
    except OSError:return False
    for folder in folders:
        svg=folder/'layer.svg';metadata=folder/'metadata.json'
        try:
            if folder.is_symlink() or any(f.is_symlink() or not f.is_file() for f in (svg,metadata)):continue
            if svg.stat().st_size>16_000_000 or metadata.stat().st_size>10_000:continue
            actual=json.loads(metadata.read_text());sha=hashlib.sha256(svg.read_bytes()).hexdigest()
            if not isinstance(actual,dict):continue
            if actual.get('schema')==1 and actual.get('plot_policy')=='absolute-no-drill-v1' and actual.get('coordinate_space')=='pcb-mm' and all(actual.get(k)==v for k,v in {**native,'layer':row['layer'],'svg_sha256':row['svg_sha256'],'visibility_sha256':row['visibility_sha256']}.items() if k!='source_version') and sha==row['svg_sha256']:return True
        except (OSError,ValueError):continue
    return False


def label(reference):
    context=reference.get('display_context')
    if context is None:return 'Frozen layer context unavailable; do not identify copper, mask or paste from color alone.'
    return ('Frozen client display context (same instant as these pixels; not engineering proof): '+encoded(context).decode()+
            '\nUse explicit layer IDs and hidden objects, not color alone. Copper pads remain copper even when a mask layer is focused. '
            'Only ready aperture rows identify plotted mask/paste vectors; loading, waiting, error and unavailable rows are unknown in this image, even if a later export succeeds. '
            'client_path_count (or legacy path_count) is a client-reported compiled drawable count, not an authenticated native object count. '
            'Visible overlapping layers can remain ambiguous; state uncertainty rather than assign every pad to the focused layer.')
