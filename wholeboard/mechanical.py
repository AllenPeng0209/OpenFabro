"""Editable, parameterized CAD programs backed by FreeCAD's exact solid kernel.

Programs are JSON, not executable Python. Only the trusted kernel adapter runs in
FreeCAD. Dimensions use bounded arithmetic over named scalar parameters.
"""
from __future__ import annotations

import ast
import hashlib
import json
import logging
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import signal
import shutil
import tempfile
import threading
import time
import uuid

from . import enclosure

SCHEMA = 1
_MODULE_BYTES = Path(__file__).read_bytes()
IDENTIFIER = re.compile(r'[A-Za-z][A-Za-z0-9_]{0,63}\Z')
OPERATIONS = {
    'material': {'target','material','bodies','faces'},
    'sketch': {'geometry','constraints','plane','require_fully_constrained'},
    'component': {'source','translation','rotation'},
    'assembly': {'members','fixed','mates','clearance_mm','rules'},
    'import': {'asset_id', 'bodies'}, 'extrude_shape': {'target', 'vector'},
    'box': {'size', 'origin'}, 'cylinder': {'radius', 'height', 'origin', 'axis'},
    'extrude': {'profile', 'vector'}, 'revolve': {'profile', 'axis', 'origin', 'angle'},
    'loft': {'profiles'}, 'sweep': {'profile', 'path'},
    'cut': {'target', 'tool'}, 'fuse': {'target', 'tool'}, 'common': {'target', 'tool'},
    'translate': {'target', 'vector'}, 'rotate': {'target', 'axis', 'origin', 'angle'},
    'shell': {'target', 'faces', 'thickness'}, 'fillet': {'target', 'edges', 'radius'},
    'chamfer': {'target', 'edges', 'distance'},
    'hole': {'target', 'origin', 'axis', 'diameter', 'depth'},
    'linear_pattern': {'target', 'count', 'step'},
    'circular_pattern': {'target', 'count', 'axis', 'origin', 'step_angle'},
}


def _number(value, parameters, *, positive=False):
    def evaluate(node):
        if isinstance(node, ast.Expression):
            return evaluate(node.body)
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            return node.value
        if isinstance(node, ast.Name) and node.id in parameters:
            return parameters[node.id]
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            answer = evaluate(node.operand)
            return answer if isinstance(node.op, ast.UAdd) else -answer
        if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div)):
            a, b = evaluate(node.left), evaluate(node.right)
            return a+b if isinstance(node.op, ast.Add) else a-b if isinstance(node.op, ast.Sub) else a*b if isinstance(node.op, ast.Mult) else a/b
        raise ValueError('Dimensions allow only numbers, named parameters and + - * / arithmetic.')

    try:
        if isinstance(value, str):
            if len(value) > 256:
                raise ValueError('Dimension expression is too long.')
            tree = ast.parse(value, mode='eval')
            if len(list(ast.walk(tree))) > 64:
                raise ValueError('Dimension expression is too complex.')
            value = evaluate(tree)
        if type(value) not in (int, float) or not math.isfinite(value) or abs(value) > 10000 or positive and value < 1e-6:
            raise ValueError('Use finite dimensions within 10000 mm, with positive sizes of at least 0.000001 mm.')
        return float(value)
    except (ArithmeticError, SyntaxError, TypeError, OverflowError, RecursionError) as error:
        raise ValueError('Invalid dimension expression.') from error


def resolve(program: dict) -> dict:
    """Resolve and validate a source program without changing its editable values."""
    if not isinstance(program, dict) or set(program)-{'schema', 'name', 'units', 'parameters', 'features', 'result', 'description','material'}:
        raise ValueError('A CAD program needs a supported object schema.')
    if type(program.get('schema')) is not int or program['schema'] != SCHEMA or program.get('units') != 'mm':
        raise ValueError('Use CAD program schema 1 and millimetre units (mm).')
    name = program.get('name')
    if not isinstance(name, str) or not name.strip() or len(name) > 100:
        raise ValueError('Name the mechanical part in at most 100 characters.')
    raw_parameters = program.get('parameters', {})
    if not isinstance(raw_parameters, dict) or len(raw_parameters) > 64:
        raise ValueError('Use at most 64 named scalar parameters.')
    parameters = {}
    for key, raw in raw_parameters.items():
        if not isinstance(key, str) or not IDENTIFIER.fullmatch(key):
            raise ValueError('Parameter names must use ASCII letters, digits and underscores.')
        if isinstance(raw, dict):
            if set(raw)-{'value', 'unit', 'label'} or raw.get('unit', 'mm') not in ('mm', 'deg', 'number'):
                raise ValueError('Parameters use value, unit (mm/deg/number) and optional label.')
            raw = raw.get('value')
        if type(raw) not in (int, float):
            raise ValueError('Parameter values must be finite numbers.')
        parameters[key] = _number(raw, {})
    number = lambda value, positive=False: _number(value, parameters, positive=positive)

    def vector(value, *, positive=False, direction=False):
        if not isinstance(value, list) or len(value) != 3:
            raise ValueError('CAD vectors need three dimensions.')
        result = [number(v, positive) for v in value]
        if direction and math.hypot(*result) < 1e-9:
            raise ValueError('Use a nonzero CAD direction.')
        return result

    def profile(raw):
        if not isinstance(raw, dict) or set(raw)-{'kind', 'width', 'height', 'radius', 'points', 'origin', 'normal'}:
            unknown = ', '.join(sorted(set(raw)-{'kind','width','height','radius','points','origin','normal'})) if isinstance(raw, dict) else 'non-object profile'
            raise ValueError('A profile uses kind, width/height/radius/points, optional origin:[x,y,z] and normal:[x,y,z]. Unknown fields: '+unknown+'. Example: {"kind":"rectangle","width":"width","height":"depth"}.')
        out = {'kind': raw.get('kind'), 'origin': vector(raw.get('origin', [0,0,0])), 'normal': vector(raw.get('normal', [0,0,1]), direction=True)}
        if out['kind'] == 'rectangle':
            out.update(width=number(raw.get('width'), True), height=number(raw.get('height'), True))
        elif out['kind'] == 'circle':
            out['radius'] = number(raw.get('radius'), True)
        elif out['kind'] == 'polygon':
            points = raw.get('points')
            if not isinstance(points, list) or not 3 <= len(points) <= 256 or any(not isinstance(p, list) or len(p) != 2 for p in points):
                raise ValueError('A polygon profile needs 3 to 256 two-dimensional points.')
            out['points'] = [[number(n) for n in p] for p in points]
        else:
            raise ValueError('Use a rectangle, circle or closed polygon profile.')
        return out

    raw_features = program.get('features')
    if not isinstance(raw_features, list) or not 1 <= len(raw_features) <= 64:
        raise ValueError('A CAD program needs 1 to 64 solid features.')
    features, identifiers = [], set()
    for raw in raw_features:
        if not isinstance(raw, dict) or not isinstance(raw.get('op'), str) or raw['op'] not in OPERATIONS:
            raise ValueError('Unknown CAD modeling operation.')
        op, identifier = raw['op'], raw.get('id')
        if not isinstance(identifier, str) or not IDENTIFIER.fullmatch(identifier) or identifier in identifiers:
            raise ValueError('Use unique feature identifiers with ASCII letters, digits and underscores.')
        if set(raw)-({'id', 'op', 'label','material'} | OPERATIONS[op]):
            raise ValueError('Unknown fields in feature ' + identifier)
        item = {'id': identifier, 'op': op}
        if 'material' in raw:
            from . import mechanical_materials
            if op=='sketch':raise ValueError('Assign material to a solid feature, not sketch geometry.')
            item['material']=mechanical_materials.resolve(raw['material'])
        if op=='material':
            if 'material' not in item:raise ValueError('A material operation needs an explicit material preset.')
            for key in ('bodies','faces'):
                if key in raw:
                    if not isinstance(raw[key],list) or not raw[key] or any(type(n) is not int or not 0<=n<20000 for n in raw[key]) or len(set(raw[key]))!=len(raw[key]):raise ValueError('Use unique nonnegative material selection indices.')
                    item[key]=list(raw[key])
            if 'faces' in item and len(item.get('bodies',[]))!=1:raise ValueError('A face finish needs exactly one selected body.')
        if 'label' in raw:
            if not isinstance(raw['label'],str) or not raw['label'].strip() or len(raw['label'])>100:raise ValueError('Feature labels use at most100 characters.')
            item['label']=raw['label']
        if op=='sketch':
            from . import sketch_program
            item.update(sketch_program.resolve(raw,number,vector))
        if op=='component':
            from . import assemblies
            item['source']=assemblies.validate_source(raw.get('source'))
            item['translation']=vector(raw.get('translation',[0,0,0]))
            rotation=raw.get('rotation',{})
            if not isinstance(rotation,dict) or set(rotation)-{'axis','angle','origin'}:raise ValueError('Component rotation uses axis,angle and optional origin.')
            item['rotation']={'axis':vector(rotation.get('axis',[0,0,1]),direction=True),'origin':vector(rotation.get('origin',[0,0,0])),'angle':number(rotation.get('angle',0))}
        if op=='assembly':
            members=raw.get('members')
            if not isinstance(members,list) or not 1<=len(members)<=64 or any(not isinstance(n,str) or n not in identifiers for n in members) or len(set(members))!=len(members):raise ValueError('Assembly members name unique earlier features.')
            fixed=raw.get('fixed',members[:1])
            if not isinstance(fixed,list) or not fixed or any(n not in members for n in fixed) or len(set(fixed))!=len(fixed):raise ValueError('Fix at least one assembly member.')
            item.update(members=list(members),fixed=list(fixed),clearance_mm=number(raw.get('clearance_mm',0)),mates=[],rules=[])
            if item['clearance_mm']<0:raise ValueError('Assembly clearance must be nonnegative.')
            def anchor(value):
                if not isinstance(value,dict) or set(value)-{'kind','normal','extreme','point','index','body_index','body_name','body_instance','radius','reference'}:raise ValueError('Use a supported assembly anchor selector.')
                kind=value.get('kind')
                if kind not in ('plane','axis','edge','datum'):raise ValueError('Anchor kind is plane,axis,edge or datum.')
                out={'kind':kind,'normal':vector(value.get('normal',[0,0,1]),direction=True),'extreme':value.get('extreme','max')}
                if out['extreme'] not in ('min','max','nearest'):raise ValueError('Anchor extreme is min,max or nearest.')
                if 'point' in value:out['point']=vector(value['point'])
                if 'radius' in value:out['radius']=number(value['radius'],True)
                for key in ('index','body_index'):
                    if key in value:
                        if type(value[key]) is not int or not 0<=value[key]<20000:raise ValueError('Use a nonnegative native anchor index.')
                        out[key]=value[key]
                if 'body_name' in value:
                    if not isinstance(value['body_name'],str) or len(value['body_name'])>300:raise ValueError('Use an inspected source body name.')
                    out['body_name']=value['body_name']
                if 'body_instance' in value:
                    if not isinstance(value['body_instance'],str) or not 1<=len(value['body_instance'])<=2048 or 'body_index' not in out:raise ValueError('Use an inspected physical body instance and body index.')
                    out['body_instance']=value['body_instance']
                if 'reference' in value:
                    ref=value['reference'];keys={'schema','entity','surface','position','direction','edges','wires'}
                    if not isinstance(ref,dict) or set(ref)!=keys or type(ref['schema']) is not int or ref['schema']!=1 or ref['entity'] not in ('face','edge') or not isinstance(ref['surface'],str) or not 1<=len(ref['surface'])<=64:raise ValueError('Use an inspected native reference signature.')
                    if 'index' not in out or 'body_index' not in out or kind=='datum' or kind=='plane' and ref['entity']!='face' or kind=='edge' and ref['entity']!='edge':raise ValueError('Selected reference needs matching native body and element indices.')
                    for key in ('position','direction'):
                        if not isinstance(ref[key],list) or len(ref[key])!=3 or any(type(v) not in (int,float) or not math.isfinite(v) or abs(v)>1e6 for v in ref[key]):raise ValueError('Native reference coordinates must be finite inspected numbers.')
                    if any(type(ref[key]) is not int or not 0<=ref[key]<=20000 for key in ('edges','wires')):raise ValueError('Native reference topology counts are invalid.')
                    out['reference']={**ref,'position':list(ref['position']),'direction':list(ref['direction'])}
                return out
            mates=raw.get('mates',[])
            if not isinstance(mates,list) or len(mates)>128:raise ValueError('Assembly supports at most128 mates.')
            mate_ids=set()
            for mate in mates:
                if not isinstance(mate,dict) or set(mate)-{'id','type','target','reference','target_anchor','reference_anchor','offset','flip'}:raise ValueError('Unsupported assembly mate fields.')
                mid=mate.get('id')
                if not isinstance(mid,str) or not IDENTIFIER.fullmatch(mid) or mid in mate_ids:raise ValueError('Use unique mate identifiers.')
                target,reference=mate.get('target'),mate.get('reference')
                if target not in members or reference not in members or target==reference or target in fixed:raise ValueError('Mate target must be a movable member and reference another member.')
                if mate.get('type') not in ('coincident','concentric','aligned','offset'):raise ValueError('Mate type is coincident,concentric,aligned or offset.')
                if 'flip' in mate and type(mate['flip']) is not bool:raise ValueError('Mate flip must be boolean.')
                item['mates'].append({'id':mid,'type':mate['type'],'target':target,'reference':reference,'target_anchor':anchor(mate.get('target_anchor')),'reference_anchor':anchor(mate.get('reference_anchor')),'offset':number(mate.get('offset',0)),'flip':mate.get('flip',mate['type']=='coincident')});mate_ids.add(mid)
            rules=raw.get('rules',[])
            if not isinstance(rules,list) or len(rules)>256:raise ValueError('Use at most256 assembly pair rules.')
            for rule in rules:
                if not isinstance(rule,dict) or set(rule)-{'a','b','minimum_mm','allow_overlap_mm3'} or rule.get('a') not in members or rule.get('b') not in members or rule['a']==rule['b']:raise ValueError('Pair rule names two assembly members.')
                minimum=number(rule.get('minimum_mm',item['clearance_mm']));overlap=number(rule.get('allow_overlap_mm3',0))
                if minimum<0 or overlap<0:raise ValueError('Pair clearance and allowed overlap are nonnegative.')
                item['rules'].append({'a':rule['a'],'b':rule['b'],'minimum_mm':minimum,'allow_overlap_mm3':overlap})
        if op == 'import':
            asset_id = raw.get('asset_id')
            if not isinstance(asset_id,str) or not re.fullmatch('[0-9a-f]{64}',asset_id):
                raise ValueError('Import requires an inspected project CAD asset identifier, not a file path.')
            item['asset_id'] = asset_id
            if 'bodies' in raw:
                bodies = raw['bodies']
                if not isinstance(bodies,list) or not 1<=len(bodies)<=256 or any(type(n) is not int or not 0<=n<256 for n in bodies) or len(set(bodies))!=len(bodies):
                    raise ValueError('Choose unique imported body indices from 0 to 255.')
                item['bodies'] = bodies
        for key in ('target', 'tool'):
            if key in OPERATIONS[op]:
                if not isinstance(raw.get(key), str) or raw[key] not in identifiers:
                    raise ValueError('Feature references must name an earlier solid.')
                item[key] = raw[key]
        if 'origin' in OPERATIONS[op]:
            item['origin'] = vector(raw.get('origin', [0,0,0]))
        if 'axis' in OPERATIONS[op]:
            item['axis'] = vector(raw.get('axis', [0,0,1]), direction=True)
        for key in ('size', 'vector', 'step'):
            if key in OPERATIONS[op]:
                item[key] = vector(raw.get(key), positive=key == 'size', direction=key != 'size')
        for key in ('radius', 'height', 'thickness', 'distance', 'diameter', 'depth'):
            if key in OPERATIONS[op]:
                item[key] = number(raw.get(key), True)
        for key in ('angle', 'step_angle'):
            if key in OPERATIONS[op]:
                item[key] = number(raw.get(key, 360 if op == 'revolve' else None))
                if not 0 < abs(item[key]) <= 360 or op == 'revolve' and item[key] < 0:
                    raise ValueError('Use a nonzero angle of at most 360 degrees.')
        if 'profile' in OPERATIONS[op]:
            item['profile'] = profile(raw.get('profile'))
        if op == 'loft':
            rows = raw.get('profiles')
            if not isinstance(rows, list) or not 2 <= len(rows) <= 16:
                raise ValueError('Loft needs 2 to 16 ordered profiles.')
            item['profiles'] = [profile(p) for p in rows]
        if op == 'sweep':
            rows = raw.get('path')
            if not isinstance(rows, list) or not 2 <= len(rows) <= 128:
                raise ValueError('Sweep needs 2 to 128 path points.')
            item['path'] = [vector(p) for p in rows]
        if 'count' in OPERATIONS[op]:
            count = number(raw.get('count'))
            if not count.is_integer() or not 1 <= count <= 64:
                raise ValueError('Patterns need an integer count from 1 to 64, including the original.')
            item['count'] = int(count)
        for key, choices in [('edges', ('all', 'vertical')), ('faces', ('top', 'bottom'))]:
            if key in OPERATIONS[op] and op!='material':
                selection = raw.get(key, choices[0])
                if not (isinstance(selection, str) and selection in choices or isinstance(selection, list) and 0 < len(selection) <= 256 and all(type(n) is int and 0 <= n < 10000 for n in selection)):
                    raise ValueError('Use a supported ' + key + ' selector or nonnegative indices.')
                item[key] = selection
        features.append(item)
        identifiers.add(identifier)
    if not isinstance(program.get('result'), str) or program['result'] not in identifiers:
        raise ValueError('Choose an existing result feature.')
    result={'schema': SCHEMA, 'name': name.strip(), 'units': 'mm', 'parameters': parameters, 'features': features, 'result': program['result']}
    if 'material' in program:
        from . import mechanical_materials
        result['material']=mechanical_materials.resolve(program['material'])
    return result


def build(program: dict, folder: Path, *, command=None, cancel=None, log=lambda text: None, source_bytes=None, adapter_bytes=None, imports=None, import_adapter=None,assembly_adapter=None,topology_adapter=None,sketch_adapter=None,material_adapter=None,curve_adapter=None) -> dict:
    """Build into a caller-owned staging directory; publication is a separate step."""
    resolved = resolve(program)
    command = command or enclosure.find_freecad()
    if not command:
        raise RuntimeError('Install FreeCAD to build exact mechanical parts.')
    folder = Path(folder).resolve()
    folder.mkdir(parents=True, exist_ok=True)
    if any(folder.iterdir()):
        raise ValueError('Build exact models in a new empty staging directory.')
    source = source_bytes if source_bytes is not None else json.dumps(program, ensure_ascii=False, indent=2).encode()
    (folder / 'source.cad.json').write_bytes(source)
    job = folder / 'job.json'
    imported = {}
    for asset_id,value in (imports or {}).items():
        dependency = folder/('import-'+asset_id+'.'+value['format'])
        dependency.write_bytes(value['bytes'])
        imported[asset_id] = str(dependency)
    (folder/'freecad_import.py').write_bytes(import_adapter if import_adapter is not None else Path(__file__).with_name('freecad_import.py').read_bytes())
    (folder/'freecad_assembly.py').write_bytes(assembly_adapter if assembly_adapter is not None else Path(__file__).with_name('freecad_assembly.py').read_bytes())
    (folder/'freecad_topology.py').write_bytes(topology_adapter if topology_adapter is not None else Path(__file__).with_name('freecad_topology.py').read_bytes())
    (folder/'freecad_curve_events.py').write_bytes(curve_adapter if curve_adapter is not None else Path(__file__).with_name('freecad_curve_events.py').read_bytes())
    (folder/'freecad_sketch.py').write_bytes(sketch_adapter if sketch_adapter is not None else Path(__file__).with_name('freecad_sketch.py').read_bytes())
    (folder/'mechanical_materials.py').write_bytes(material_adapter if material_adapter is not None else Path(__file__).with_name('mechanical_materials.py').read_bytes())
    from . import assemblies
    component_files={item['id']:imported.get(assemblies.dependency_key(item)) for item in resolved['features'] if item['op']=='component'}
    component_evidence={item['id']:{key:value for key,value in (imports or {}).get(assemblies.dependency_key(item),{}).items() if key!='bytes'} for item in resolved['features'] if item['op']=='component'}
    job.write_text(json.dumps({'program': resolved, 'source': program, 'directory': str(folder), 'imports': imported,'component_files':component_files,'component_evidence':component_evidence}))
    script = folder/'kernel.py'
    script.write_bytes(adapter_bytes if adapter_bytes is not None else Path(__file__).with_name('freecad_model.py').read_bytes())
    _run_kernel(command,script,folder,{'OPENFABRO_MECHANICAL_JOB':str(job)},cancel,log)
    report_path = folder / 'report.json'
    if not report_path.is_file():
        raise RuntimeError('FreeCAD did not produce a mechanical verification report.')
    report = json.loads(report_path.read_text())
    if not report.get('ok'):
        raise RuntimeError(report.get('error') or 'FreeCAD mechanical build failed.')
    from . import cad_mass
    mass_script=folder/'mass_worker.py';mass_script.write_bytes(Path(cad_mass.__file__).read_bytes())
    mass_job=folder/'mass_job.json';mass_output=folder/'mass_report.json'
    mass_job.write_text(json.dumps({'report':str(report_path),'step':str(folder/'part.step'),'scene':str(folder/'scene.json'),'result_id':resolved['result'],'output':str(mass_output)}))
    try:_run_kernel([sys.executable],mass_script,folder,{'OPENFABRO_MASS_JOB':str(mass_job)},cancel,log,label='Checking adaptive span-aware mass properties')
    except RuntimeError:
        if mass_output.is_file() and not (cancel and cancel.is_set()):
            failure=json.loads(mass_output.read_text())
            if failure.get('error'):raise RuntimeError(failure['error']) from None
        raise
    report=json.loads(mass_output.read_text())
    if not report.get('ok'):raise RuntimeError(report.get('error') or 'Adaptive mass verification failed.')
    scene=json.loads((folder/'scene.json').read_text())
    for item in report['mass_properties']['face_areas']:
        body=next(b for b in scene['topology']['bodies'] if b['body_id']==item['body_id']);face=next(f for f in body['faces'] if f['index']==item['face_index'])
        face['kernel_default_area_mm2']=face['area_mm2'];face['area_mm2']=item['area_mm2'];face['mass_property_basis']='occt-adaptive-span-integration'
    (folder/'scene.json').write_text(json.dumps(scene,separators=(',',':')))
    report_path.write_text(json.dumps(report,indent=2))
    report['source_sha256'] = hashlib.sha256(source).hexdigest()
    return report


def _run_kernel(command,script,folder,extra_env,cancel,log,*,label='Checking exact mechanical geometry with FreeCAD'):
    env = {**os.environ, **extra_env}
    log(label)
    with (folder / 'freecad.log').open('w') as output:
        child = subprocess.Popen(command + [str(script)], cwd=folder, env=env, stdout=output, stderr=subprocess.STDOUT, start_new_session=os.name != 'nt')
        try:
            deadline = time.monotonic()+120
            while child.poll() is None:
                if cancel is not None and cancel.wait(.1):
                    raise RuntimeError('Mechanical build cancelled.')
                if cancel is None:
                    time.sleep(.1)
                if time.monotonic() > deadline:
                    raise RuntimeError('Mechanical build exceeded two minutes.')
            code = child.wait(timeout=5)
        finally:
            if child.poll() is None:
                try:
                    if os.name != 'nt':os.killpg(child.pid, signal.SIGKILL)
                    else:child.kill()
                except ProcessLookupError:pass
                child.wait(timeout=5)
    if code:raise RuntimeError('FreeCAD native process failed. Review the import or build findings.')


class MechanicalConflict(ValueError):
    """A source, asset or active operation changed before publication."""


EXPORTS = ('part.step', 'part.stl', 'part.FCStd', 'scene.json', 'report.json', 'source.cad.json')
OPTIONAL_EXPORTS = ('part.obj','part.3mf')


def _source_path(p, name):
    if not isinstance(name, str) or len(name) > 240:
        raise ValueError('Choose an editable project .cad.json source.')
    rel = Path(name)
    if rel.is_absolute() or not rel.parts or any(part.startswith('.') for part in rel.parts) or rel.parts[0] in ('native', 'history', 'mechanical', 'references') or not name.endswith('.cad.json'):
        raise ValueError('Choose a visible editable project .cad.json source, outside generated assets.')
    root = p.root.resolve()
    cursor = root
    for part in rel.parts:
        cursor = cursor/part
        if cursor.is_symlink():
            raise ValueError('CAD sources cannot use symbolic links.')
    if not cursor.resolve().is_relative_to(root):
        raise ValueError('CAD sources must remain inside their project.')
    from .project_paths import protected_output
    if protected_output(root, cursor, {'state.json','design.json','events.jsonl','config.json'}):
        raise ValueError('Choose an editable CAD source outside generated mechanical assets.')
    return cursor


def _source(p, name):
    cursor = _source_path(p, name)
    if not cursor.is_file() or cursor.stat().st_size > 256000:
        raise ValueError('Use an existing project CAD source smaller than 256 KB.')
    raw = cursor.read_bytes()
    if len(raw) > 256000:
        raise ValueError('CAD source exceeds 256 KB.')
    try:
        program = json.loads(raw.decode('utf-8'))
    except (UnicodeError, ValueError) as error:
        raise ValueError('The CAD source must contain UTF-8 JSON.') from error
    resolve(program)
    return cursor, raw, program


def _commit_record(p, name, record, path, before, candidate):
    """Caller holds p.lock; source, file undo metadata and current asset commit together."""
    if _source_path(p, name) != path or (path.read_bytes() if path.is_file() else None) != before:
        raise MechanicalConflict('The CAD source changed before asset publication.')
    from . import ai_changes, design_origin, mechanical_history
    from .workbench import _atomic_text
    writes = [(path, candidate.decode('utf-8'))] if candidate is not None and candidate != before else []
    origin = design_origin.current(p)
    request_id = origin.get('request_id') if origin else None
    receipt = ai_changes.prepare_files(p, request_id, writes)
    previous = mechanical_history.capture(p,name)
    with ai_changes.rollback_on_error(p, [target for target, _ in writes]):
        if writes:
            design_origin.note_files(p, [name])
            path.parent.mkdir(parents=True, exist_ok=True)
            _atomic_text(path, writes[0][1])
        p.state.setdefault('workbench_mechanical', {})[name] = record
        p.state.setdefault('mechanical_asset_receipts', {})[record['asset_id']] = record['manifest_sha256']
        ai_changes.record_files(p, request_id, receipt)
        mechanical_history.record(p,previous,mechanical_history.capture(p,name),'Created part' if previous['raw'] is None else 'Edited part' if writes else 'Rebuilt part')
        history = mechanical_history.summary(p)
        p.save()
    if writes:
        _notify(p, {'type': 'file_saved', 'path': name})
        if receipt is not None:
            _notify(p, {'type': 'ai_change_set', 'request_id': request_id, 'files': len(receipt['files']), 'version': p.state.get('workbench', {}).get('version', 0)})
    _notify(p, {'type': 'mechanical_asset', 'source': name, 'asset_id': record['asset_id'], 'source_sha256': record['source_sha256']})
    _notify(p, {'type':'mechanical_history_changed','history':history})
    return {**record,'mechanical_history':history}


def _notify(p, event):
    try:p.emit(event)
    except Exception as error:
        # Native/source persistence already committed; notification cannot revoke it.
        logging.getLogger(__name__).warning('Mechanical asset saved; notification failed: %s', error)


def _output_root(p):
    root = p.root.resolve()/'mechanical'
    if root.is_symlink() or not root.resolve().is_relative_to(p.root.resolve()):
        raise ValueError('Generated mechanical assets cannot use a symbolic output directory.')
    root.mkdir(exist_ok=True)
    return root


def _record(p, folder, *, manifest_sha256=None, source=None, source_bytes=None, implementation=None):
    manifest = folder/'manifest.json'
    if folder.is_symlink() or not folder.resolve().is_relative_to((p.root.resolve()/'mechanical').resolve()) or manifest.is_symlink():
        raise MechanicalConflict('The saved mechanical asset path changed.')
    manifest_bytes = manifest.read_bytes()
    accepted = manifest_sha256 or p.state.get('mechanical_asset_receipts', {}).get(folder.name)
    actual = hashlib.sha256(manifest_bytes).hexdigest()
    if not accepted or actual != accepted:
        raise MechanicalConflict('The saved mechanical asset manifest changed or lacks a trusted receipt. Build a new revision with force=true.')
    value = json.loads(manifest_bytes)
    if value.get('schema') != SCHEMA or value.get('asset_id') != folder.name:
        raise MechanicalConflict('The saved mechanical asset manifest changed.')
    names=set(value.get('hashes',{}))
    if not set(EXPORTS)<=names or names-set(EXPORTS)-set(OPTIONAL_EXPORTS):
        raise MechanicalConflict('The saved mechanical asset is incomplete.')
    if source is not None and (value.get('source') != source or value.get('source_sha256') != hashlib.sha256(source_bytes).hexdigest() or value.get('implementation_sha256') != implementation):
        raise MechanicalConflict('The saved mechanical asset does not match the requested CAD source or implementation.')
    if source_bytes is not None and (folder/'source.cad.json').read_bytes() != source_bytes:
        raise MechanicalConflict('The saved mechanical asset source copy changed.')
    files = []
    for name in EXPORTS+tuple(name for name in OPTIONAL_EXPORTS if name in names):
        file = folder/name
        if file.is_symlink() or not file.is_file() or hashlib.sha256(file.read_bytes()).hexdigest() != value['hashes'][name]:
            raise MechanicalConflict('The saved mechanical asset changed: '+name+'. Build a new revision with force=true.')
        files.append({'name': name, 'path': file.relative_to(p.root.resolve()).as_posix(), 'url': p.file_url(file),
                      'sha256': value['hashes'][name], 'size': file.stat().st_size})
    return {key: value[key] for key in ('asset_id', 'source', 'source_sha256', 'name', 'created_at', 'metrics', 'implementation_sha256')} | {
        'manifest_sha256': actual,
        'files': files, 'scene_url': p.file_url(folder/'scene.json'), 'report_url': p.file_url(folder/'report.json'),
        'source_copy': (folder/'source.cad.json').relative_to(p.root.resolve()).as_posix(), 'imports':value.get('imports',{})}


def listing(p):
    """Inspect source freshness and all preserved model revisions without writing."""
    parts = []
    with p.lock:
        current = dict(p.state.get('workbench_mechanical') or {})
    root = p.root.resolve()/'mechanical'
    folders = [path.parent for path in root.glob('*/manifest.json')] if root.is_dir() and not root.is_symlink() else []
    for source, stored in current.items():
        row = dict(stored)
        try:
            _, raw, program = _source(p, source)
            current_sha = hashlib.sha256(raw).hexdigest()
            row['editable_parameters'] = program.get('parameters', {})
        except (OSError, ValueError) as error:
            current_sha = None
            row.update(source_error=str(error), editable_parameters=None)
        row.update(current_source_sha256=current_sha, stale=current_sha != row['source_sha256'])
        try:
            if current_sha is not None:
                from . import mechanical_assets
                from . import assemblies
                dependencies=mechanical_assets.dependencies(p,program)|assemblies.dependencies(p,program,source)
                receipts={key:{k:v for k,v in value.items() if k!='bytes'} for key,value in dependencies.items()}
                changed=bool(receipts) and receipts!=row.get('imports',{})
                row['dependency_changed']=changed
                if changed:row['stale']=True
        except (ValueError,OSError) as error:row.update(dependency_error=str(error),stale=True)
        versions = []
        for folder in folders:
            try:
                value = json.loads((folder/'manifest.json').read_text())
                if value.get('source') == source:
                    versions.append(_record(p, folder))
            except (OSError, ValueError, KeyError) as error:
                if folder.name == row.get('asset_id'):
                    row['asset_error'] = str(error)
        row['available'] = any(value['asset_id'] == row['asset_id'] for value in versions)
        row['versions'] = sorted(versions, key=lambda value: value['created_at'])
        parts.append(row)
    from . import mechanical_history
    return {'schema': SCHEMA, 'parts': parts, 'operations': sorted(OPERATIONS), 'program_units': 'mm','history':mechanical_history.summary(p)}


def inspect_topology(p,arguments):
    """Read a bounded page of sealed native references without regenerating geometry."""
    allowed={'source','asset_id','member_id','body_id','entity','offset','limit','expected_scene_sha256'}
    if not isinstance(arguments,dict) or set(arguments)-allowed:raise ValueError('Use source, optional model/filter/pagination and expected scene SHA.')
    source=arguments.get('source');_source_path(p,source);entity=arguments.get('entity','face');offset=arguments.get('offset',0);limit=arguments.get('limit',100)
    if entity not in ('face','edge') or type(offset) is not int or not 0<=offset<=100000 or type(limit) is not int or not 1<=limit<=100:raise ValueError('Choose face/edge, nonnegative offset and limit1..100.')
    if 'body_id' in arguments and (type(arguments['body_id']) is not int or not 0<=arguments['body_id']<256):raise ValueError('Choose an inspected native body index.')
    if 'member_id' in arguments and (not isinstance(arguments['member_id'],str) or not IDENTIFIER.fullmatch(arguments['member_id'])):raise ValueError('Choose an inspected assembly member.')
    with p.lock:
        current=p.state.get('workbench_mechanical',{}).get(source);asset_id=arguments.get('asset_id') or (current or {}).get('asset_id')
        if not isinstance(asset_id,str) or not re.fullmatch('[0-9a-f]{64}(?:-[0-9a-f]{12})?',asset_id):raise ValueError('Choose an existing verified model revision.')
        record=_record(p,p.root.resolve()/'mechanical'/asset_id)
        if record['source']!=source:raise MechanicalConflict('The native reference model belongs to a different source.')
        scene=next(file for file in record['files'] if file['name']=='scene.json')
        from .document_context import verify_hash
        verify_hash(arguments.get('expected_scene_sha256'),scene['sha256'],'native reference snapshot')
        if scene['size']>100_000_000:raise ValueError('The native reference scene exceeds the inspection budget.')
        data=json.loads((p.root/scene['path']).read_text());topology=data.get('topology');common={'asset_id':asset_id,'source':source,'source_sha256':record['source_sha256'],'scene_sha256':scene['sha256'],'active_model_pointer':bool(current and current['asset_id']==asset_id),'units':'mm','freshness_note':'Inspect mechanical parts for source/dependency freshness before editing.','origin_mm':data.get('origin'),'size_mm':data['size']}
        if not topology or topology.get('schema')!=1:return {**common,'available':False,'reason':'This retained model has no native pick map. Build a new revision to add selectable geometry.','elements':[],'total':0,'offset':offset,'next_offset':None,'truncated':False}
        rows=[]
        for body in topology['bodies']:
            if 'member_id' in arguments and body['member_id']!=arguments['member_id'] or 'body_id' in arguments and body['body_id']!=arguments['body_id']:continue
            for element in body['faces' if entity=='face' else 'edges']:
                row={**{key:value for key,value in element.items() if key not in ('v','curvature','curve_events')},'entity':entity,'body_id':body['body_id'],'member_id':body['member_id'],'body_name':body['source_body_name']}
                if 'curvature' in element:row['curvature']={key:value for key,value in element['curvature'].items() if key!='samples'}
                if 'curve_events' in element:row['curve_events']={key:value for key,value in element['curve_events'].items() if key!='events'}|{'event_count':len(element['curve_events'].get('events',[]))}
                rows.append(row)
        page=rows[offset:offset+limit];end=offset+len(page)
        return {**common,'available':True,'total':len(rows),'offset':offset,'elements':page,'next_offset':end if end<len(rows) else None,'truncated':end<len(rows)}


def inspect_curvature(p,arguments):
    """Read a bounded derivative page of one sealed, placed native edge."""
    allowed={'source','asset_id','body_id','edge_index','offset','limit','expected_scene_sha256'}
    if not isinstance(arguments,dict) or set(arguments)-allowed:raise ValueError('Use source, body_id, edge_index and optional retained model/pagination/scene SHA.')
    body_id=arguments.get('body_id');edge_index=arguments.get('edge_index');offset=arguments.get('offset',0);limit=arguments.get('limit',32)
    if type(body_id) is not int or not 0<=body_id<256 or type(edge_index) is not int or not 0<=edge_index<100000:raise ValueError('Choose an inspected native body and edge index.')
    if type(offset) is not int or not 0<=offset<=100000 or type(limit) is not int or not 1<=limit<=100:raise ValueError('Use nonnegative sample offset and limit1..100.')
    with p.lock:
        topology=inspect_topology(p,{key:value for key,value in arguments.items() if key in ('source','asset_id','body_id','expected_scene_sha256')}|{'entity':'edge','offset':edge_index,'limit':1})
        common={key:topology[key] for key in ('asset_id','source','source_sha256','scene_sha256','active_model_pointer','origin_mm','size_mm','freshness_note')}
        if not topology['available']:return {**common,'available':False,'reason':topology['reason'],'samples':[],'total':0,'offset':offset,'next_offset':None,'truncated':False}
        element=next(iter(topology['elements']),None)
        if element is None or element['index']!=edge_index:raise ValueError('That native edge is unavailable.')
        # The same lock and sealed scene identity protect summary and sample bytes.
        record=_record(p,p.root.resolve()/'mechanical'/topology['asset_id'])
        scene=next(file for file in record['files'] if file['name']=='scene.json')
        data=json.loads((p.root/scene['path']).read_text())
        body=next(b for b in data['topology']['bodies'] if b['body_id']==body_id)
        edge=next(e for e in body['edges'] if e['index']==edge_index)
        curvature=edge.get('curvature',{'available':False,'reason':'This retained revision has no native curvature samples; keep its files unchanged.'})
        samples=curvature.get('samples',[]);page=samples[offset:offset+limit];end=offset+len(page)
        return {**common,**{key:value for key,value in curvature.items() if key!='samples'},'body_id':body_id,'member_id':body['member_id'],'edge_index':edge_index,'surface':edge['surface'],
                'coordinate_note':'Sample points are scene-local millimeters; add origin_mm for placed world coordinates. Normals and tangents use placed world axes.',
                'scope':'Native edge curvature only, not a surface continuity or stress analysis. Singular derivative samples remain null; finite sampling cannot prove absence of inflections or jumps.',
                'samples':page,'total':len(samples),'offset':offset,'next_offset':end if end<len(samples) else None,'truncated':end<len(samples)}


def inspect_curve_events(p,arguments):
    allowed={'source','asset_id','body_id','edge_index','kind','offset','limit','expected_scene_sha256'}
    if not isinstance(arguments,dict) or set(arguments)-allowed:raise ValueError('Use source, optional retained model/body/edge/kind/pagination and scene SHA.')
    offset=arguments.get('offset',0);limit=arguments.get('limit',32);kind=arguments.get('kind','all')
    if type(offset) is not int or not 0<=offset<=1000000 or type(limit) is not int or not 1<=limit<=100:raise ValueError('Use nonnegative offset and limit1..100.')
    if kind not in ('all','inflection','curvature_jump','tangent_break','singular'):raise ValueError('Choose a curve event kind.')
    if 'edge_index' in arguments and ('body_id' not in arguments or type(arguments['edge_index']) is not int or not 0<=arguments['edge_index']<100000):raise ValueError('Choose a body and native edge index.')
    with p.lock:
        topology=inspect_topology(p,{k:v for k,v in arguments.items() if k in ('source','asset_id','body_id','expected_scene_sha256')}|{'entity':'edge','limit':1})
        common={key:topology[key] for key in ('asset_id','source','source_sha256','scene_sha256','active_model_pointer','origin_mm','size_mm','freshness_note')}
        if not topology['available']:return {**common,'available':False,'reason':topology['reason'],'events':[],'total':0,'offset':offset,'next_offset':None,'truncated':False}
        record=_record(p,p.root.resolve()/'mechanical'/topology['asset_id']);file=next(f for f in record['files'] if f['name']=='scene.json');data=json.loads((p.root/file['path']).read_text());rows=[];available=0;unavailable=0
        for body in data['topology']['bodies']:
            if 'body_id' in arguments and body['body_id']!=arguments['body_id']:continue
            for edge in body['edges']:
                if 'edge_index' in arguments and edge['index']!=arguments['edge_index']:continue
                analysis=edge.get('curve_events',{});available+=bool(analysis.get('available'));unavailable+=not analysis.get('complete',False)
                rows.extend({**e,'body_id':body['body_id'],'member_id':body['member_id'],'edge_index':edge['index']} for e in analysis.get('events',[]))
            for event in body.get('curve_events',{}).get('events',[]):
                if 'edge_index' not in arguments or arguments['edge_index'] in event['edge_indices']:rows.append({**event,'body_id':body['body_id'],'member_id':body['member_id']})
        rows=[row for row in rows if kind=='all' or row['kind']==kind];page=rows[offset:offset+limit];end=offset+len(page)
        return {**common,'available':available>0,'analyzed_edges':available,'incomplete_edges':unavailable,'events':page,'total':len(rows),'offset':offset,'next_offset':end if end<len(rows) else None,'truncated':end<len(rows),
                'scope':'Native planar polynomial inflections, one-sided knot and wire limits. Corners/singularities are separate; unsupported spatial curves and legacy data stay unknown. Numerical analysis is not a formal global continuity proof.'}


def inspect_surfaces(p,arguments):
    """Read native oriented surface derivatives of one sealed, placed face."""
    allowed={'source','asset_id','body_id','face_index','offset','limit','expected_scene_sha256'}
    if not isinstance(arguments,dict) or set(arguments)-allowed:raise ValueError('Use source, body_id, face_index and optional retained model/pagination/scene SHA.')
    body_id=arguments.get('body_id');face_index=arguments.get('face_index');offset=arguments.get('offset',0);limit=arguments.get('limit',32)
    if type(body_id) is not int or not 0<=body_id<256 or type(face_index) is not int or not 0<=face_index<20000:raise ValueError('Choose an inspected native body and face index.')
    if type(offset) is not int or not 0<=offset<=1000000 or type(limit) is not int or not 1<=limit<=100:raise ValueError('Use nonnegative sample offset and limit1..100.')
    with p.lock:
        topology=inspect_topology(p,{key:value for key,value in arguments.items() if key in ('source','asset_id','body_id','expected_scene_sha256')}|{'entity':'face','offset':face_index,'limit':1})
        common={key:topology[key] for key in ('asset_id','source','source_sha256','scene_sha256','active_model_pointer','origin_mm','size_mm','freshness_note')}
        if not topology['available']:return {**common,'available':False,'reason':topology['reason'],'samples':[],'total':0,'offset':offset,'next_offset':None,'truncated':False}
        element=next(iter(topology['elements']),None)
        if element is None or element['index']!=face_index:raise ValueError('That native face is unavailable.')
        record=_record(p,p.root.resolve()/'mechanical'/topology['asset_id'])
        scene=next(file for file in record['files'] if file['name']=='scene.json')
        data=json.loads((p.root/scene['path']).read_text());rows=[]
        for mesh_index,mesh in enumerate(data['meshes']):
            if mesh.get('body_id')!=body_id:continue
            for vertex,sample in enumerate(mesh.get('surface_samples',[])):
                if sample is not None and sample['face_index']==face_index:rows.append({**sample,'mesh_index':mesh_index,'vertex_index':vertex})
        summary=element.get('surface_curvature',{'available':False,'reason':'This retained revision has no native surface samples; its files remain unchanged.'})
        page=rows[offset:offset+limit];end=offset+len(page)
        return {**common,**summary,'body_id':body_id,'member_id':element['member_id'],'face_index':face_index,'surface':element['surface'],
                'coordinate_note':'Points are scene-local millimeters; add origin_mm for placed world coordinates. Normals use placed world axes.',
                'scope':'Samples at tessellation vertices, not a proof of surface continuity or a stress/manufacturing result. Unavailable/singular samples are not zero curvature.',
                'samples':page,'total':len(rows),'offset':offset,'next_offset':end if end<len(rows) else None,'truncated':end<len(rows)}


def inspect_materials(p,arguments):
    if not isinstance(arguments,dict) or set(arguments)-{'source','asset_id'}:raise ValueError('Use source and optional retained material model ID.')
    source=arguments.get('source');_source_path(p,source)
    with p.lock:
        current=p.state.get('workbench_mechanical',{}).get(source);asset_id=arguments.get('asset_id') or (current or {}).get('asset_id')
        if not isinstance(asset_id,str) or not re.fullmatch('[0-9a-f]{64}(?:-[0-9a-f]{12})?',asset_id):raise ValueError('Choose a verified material model.')
        record=_record(p,p.root.resolve()/'mechanical'/asset_id)
        if record['source']!=source:raise MechanicalConflict('The material model belongs to another source.')
        bodies=[]
        for index,body in enumerate(record['metrics']['bodies']):
            styles={}
            for face,material in enumerate(body.get('face_materials') or [body.get('material')]*body['faces']):
                key=json.dumps(material,sort_keys=True);entry=styles.setdefault(key,{'material':material,'faces':[]});entry['faces'].append(face)
            bodies.append({'body_index':index,'name':body['name'],'material':body.get('material'),'surface_groups':list(styles.values())})
        return {'asset_id':asset_id,'source':source,'source_sha256':record['source_sha256'],'active_model_pointer':bool(current and current['asset_id']==asset_id),'bodies':bodies,'report':next(f for f in record['files'] if f['name']=='report.json'),'scope':'Declared material intent and visual presets, not validated engineering properties. Inspect source/dependency freshness before editing.'}


def inspect_sketches(p,arguments):
    if not isinstance(arguments,dict) or set(arguments)-{'source','asset_id','feature_id'}:raise ValueError('Use source, optional model revision and sketch feature ID.')
    source=arguments.get('source');_source_path(p,source)
    with p.lock:
        current=p.state.get('workbench_mechanical',{}).get(source);asset_id=arguments.get('asset_id') or (current or {}).get('asset_id')
        if not isinstance(asset_id,str) or not re.fullmatch('[0-9a-f]{64}(?:-[0-9a-f]{12})?',asset_id):raise ValueError('Choose an existing verified model revision.')
        record=_record(p,p.root.resolve()/'mechanical'/asset_id)
        if record['source']!=source:raise MechanicalConflict('The sketch model belongs to another source.')
        values=record['metrics'].get('sketches',{});feature=arguments.get('feature_id')
        if feature is not None and (not isinstance(feature,str) or not IDENTIFIER.fullmatch(feature)):raise ValueError('Use an inspected sketch feature ID.')
        if feature is not None and feature not in values:raise ValueError('The selected model has no such native sketch.')
        sketches={key:{**value,'geometry':[{k:v for k,v in geometry.items() if k!='points'} for geometry in value['geometry']]} for key,value in values.items() if feature is None or key==feature}
        return {'asset_id':asset_id,'source':source,'source_sha256':record['source_sha256'],'active_model_pointer':bool(current and current['asset_id']==asset_id),'sketches':sketches,'report':next(f for f in record['files'] if f['name']=='report.json'),'tessellation_omitted':True,'freshness_note':'Inspect mechanical parts for current source and dependency freshness.'}


def preview_sketch(p,arguments):
    """Solve an unsaved sketch in a private temporary document; never publish the draft."""
    if not isinstance(arguments,dict) or set(arguments)-{'path','feature_id','program','expected_sha256','expected_asset_id'}:raise ValueError('Use path, feature_id, optional draft program and expected source/model identities.')
    from .document_context import verify_hash
    from . import mechanical_history
    with p.lock:
        if p.engine_busy or p.worker and p.worker.is_alive() and p.worker is not threading.current_thread():raise MechanicalConflict('Wait for the active operation before previewing a sketch.')
        if p.worker is threading.current_thread() and (p.cancel.is_set() or p.inbox):raise MechanicalConflict('Sketch preview canceled before starting.')
        name=mechanical_history.canonical_source(p,arguments.get('path'));path=_source_path(p,name)
        if path.exists() and (not path.is_file() or path.stat().st_size>256000):raise ValueError('Use a bounded regular sketch source.')
        before=path.read_bytes() if path.is_file() else None
        verify_hash(arguments.get('expected_sha256'),hashlib.sha256(before).hexdigest() if before is not None else '', 'CAD source')
        current=p.state.get('workbench_mechanical',{}).get(name);expected=arguments.get('expected_asset_id')
        if expected is not None and (not current or current['asset_id']!=expected):raise MechanicalConflict('The sketch preview model changed.')
        program=arguments.get('program')
        if program is None:
            if before is None:raise ValueError('Provide a draft program for a new sketch.')
            program=json.loads(before)
        raw=json.dumps(program,ensure_ascii=False).encode()
        if len(raw)>256000:raise ValueError('Sketch draft exceeds the source budget.')
        resolved=resolve(program);feature=next((f for f in resolved['features'] if f['id']==arguments.get('feature_id') and f['op']=='sketch'),None)
        if feature is None:raise ValueError('Choose a native sketch feature to preview.')
        source_feature=next(f for f in program['features'] if f['id']==feature['id']);adapter=Path(__file__).with_name('freecad_sketch.py').read_bytes();command=enclosure.find_freecad()
        if not command:raise RuntimeError('Install FreeCAD to solve native sketch constraints.')
        p.engine_busy=True;p.cancel.clear()
    try:
        with tempfile.TemporaryDirectory(prefix='openfabro-sketch-preview-') as temporary:
            folder=Path(temporary);script=folder/'sketch.py';script.write_bytes(adapter);output=folder/'result.json';job=folder/'job.json';job.write_text(json.dumps({'source':program,'feature':feature,'source_feature':source_feature,'result':str(output)}));_run_kernel(command,script,folder,{'OPENFABRO_SKETCH_JOB':str(job)},p.cancel,lambda text:p.log('sketch',text));result=json.loads(output.read_text())
            if not result.get('ok'):raise ValueError(result.get('error','Native sketch preview failed.'))
            with p.lock:
                if p.cancel.is_set() or p.inbox:raise MechanicalConflict('Sketch preview canceled before completion.')
                current_path=_source_path(p,name)
                if current_path!=path or (current_path.read_bytes() if current_path.is_file() else None)!=before:raise MechanicalConflict('The CAD source changed while the sketch was solving.')
            return {**result,'preview_only':True,'source':name,'feature_id':feature['id'],'source_sha256':hashlib.sha256(before).hexdigest() if before is not None else None}
    finally:
        with p.lock:p.engine_busy=False


def rebuild(p, arguments):
    """Guard a source snapshot, build privately, then publish an immutable asset."""
    if not isinstance(arguments, dict) or set(arguments)-{'path', 'expected_sha256', 'force', 'program','expected_asset_id'}:
        raise ValueError('Use path, optional program, expected_sha256 and force for a CAD rebuild.')
    name = arguments.get('path')
    from .document_context import verify_hash
    with p.lock:
        if p.engine_busy or p.worker and p.worker.is_alive() and p.worker is not threading.current_thread():
            raise MechanicalConflict('Wait for the active run before rebuilding a mechanical part.')
        if p.worker is threading.current_thread() and (p.cancel.is_set() or p.inbox):
            raise MechanicalConflict('Mechanical build canceled before it started.')
        candidate = None
        from . import mechanical_history
        name = mechanical_history.canonical_source(p,name)
        if 'program' in arguments:
            path = _source_path(p, name)
            if path.exists() and (not path.is_file() or path.stat().st_size > 256000):
                raise ValueError('Use a bounded editable CAD source file.')
            before = path.read_bytes() if path.is_file() else None
            if before is not None and arguments.get('expected_sha256') is None:
                raise MechanicalConflict('Read the existing CAD source and provide its expected SHA before editing.')
            if before is None and arguments.get('expected_sha256') is not None:
                raise MechanicalConflict('The expected CAD source changed or is missing.')
            if before is not None:
                verify_hash(arguments.get('expected_sha256'), hashlib.sha256(before).hexdigest(), 'CAD source')
            program = arguments['program']
            resolve(program)
            raw = json.dumps(program, ensure_ascii=False, indent=2).encode()
            if len(raw) > 256000:
                raise ValueError('CAD source exceeds 256 KB.')
            candidate = raw
        else:
            path, raw, program = _source(p, name)
            before = raw
            verify_hash(arguments.get('expected_sha256'), hashlib.sha256(raw).hexdigest(), 'CAD source')
        digest = hashlib.sha256(raw).hexdigest()
        preview=arguments.get('expected_asset_id');preview_record=None
        if preview is not None:
            preview_record=p.state.get('workbench_mechanical',{}).get(name)
            if not isinstance(preview,str) or not preview_record or preview_record['asset_id']!=preview or before is None or hashlib.sha256(before).hexdigest()!=preview_record['source_sha256']:
                raise MechanicalConflict('The selected model preview or source changed. Rebuild it before choosing a mate.')
        command = enclosure.find_freecad()
        if not command:raise RuntimeError('Install FreeCAD to build exact mechanical parts.')
        adapter_bytes = Path(__file__).with_name('freecad_model.py').read_bytes()
        import_adapter = Path(__file__).with_name('freecad_import.py').read_bytes()
        assembly_adapter=Path(__file__).with_name('freecad_assembly.py').read_bytes()
        topology_adapter=Path(__file__).with_name('freecad_topology.py').read_bytes()
        sketch_adapter=Path(__file__).with_name('freecad_sketch.py').read_bytes()
        material_adapter=Path(__file__).with_name('mechanical_materials.py').read_bytes()
        curve_adapter=Path(__file__).with_name('freecad_curve_events.py').read_bytes()
        from . import cad_mass
        mass_implementation=Path(cad_mass.__file__).read_bytes()+cad_mass.version().encode()
        from . import sketch_program
        from . import mechanical_assets
        from . import assemblies
        imports = mechanical_assets.dependencies(p,resolve(program))|assemblies.dependencies(p,resolve(program),name)
        import_receipts = {key:{k:v for k,v in value.items() if k!='bytes'} for key,value in imports.items()}
        if preview_record is not None and preview_record.get('imports',{})!=import_receipts:raise MechanicalConflict('The selected preview source dependencies changed. Rebuild before choosing a mate.')
        implementation = hashlib.sha256(_MODULE_BYTES+adapter_bytes+import_adapter+assembly_adapter+topology_adapter+sketch_adapter+material_adapter+curve_adapter+mass_implementation+Path(sketch_program.__file__).read_bytes()+Path(assemblies.__file__).read_bytes()).hexdigest()
        kernel_version = enclosure.freecad_version(command) or 'unknown'
        root = _output_root(p)
        asset_id = hashlib.sha256(f'mechanical:{SCHEMA}:{name}:{implementation}:{kernel_version}:'.encode()+raw+json.dumps(import_receipts,sort_keys=True).encode()).hexdigest()
        if arguments.get('force') is True:
            asset_id += '-'+uuid.uuid4().hex[:12]
        folder = root/asset_id
        if folder.exists():
            if p.inbox:raise MechanicalConflict('Mechanical build canceled by a pending instruction.')
            record = _record(p, folder, source=name, source_bytes=raw, implementation=implementation)
            return _commit_record(p, name, record, path, before, candidate)
        p.engine_busy = True
        p.cancel.clear()
    try:
        p.set_status('running', 'Building exact mechanical part: '+program['name'])
        with tempfile.TemporaryDirectory(prefix='openfabro-mechanical-') as temporary:
            stage = Path(temporary)/'native'
            report = build(program, stage, command=command, cancel=p.cancel, source_bytes=raw, adapter_bytes=adapter_bytes, imports=imports, import_adapter=import_adapter,assembly_adapter=assembly_adapter,topology_adapter=topology_adapter,sketch_adapter=sketch_adapter,material_adapter=material_adapter,curve_adapter=curve_adapter, log=lambda text: p.log('mechanical', text))
            with p.lock:
                if p.cancel.is_set() or p.inbox:
                    raise MechanicalConflict('Mechanical build canceled before publication.')
                current_path = _source_path(p, name)
                current_bytes = current_path.read_bytes() if current_path.is_file() else None
                if current_path != path or current_bytes != before:
                    raise MechanicalConflict('The CAD source changed while its model was being built. Rebuild the current file.')
                current_imports = mechanical_assets.dependencies(p,resolve(program))|assemblies.dependencies(p,resolve(program),name)
                if {key:{k:v for k,v in value.items() if k!='bytes'} for key,value in current_imports.items()} != import_receipts:
                    raise MechanicalConflict('An imported CAD dependency changed during the build.')
                if _output_root(p) != root or folder.exists():
                    raise MechanicalConflict('The mechanical asset destination changed during the build.')
                publication = root/('.publish-'+uuid.uuid4().hex)
                publication.mkdir()
                try:
                    hashes = {}
                    exports=EXPORTS+(OPTIONAL_EXPORTS if report.get('mesh_exports') else ())
                    for filename in exports:
                        artifact = stage/filename
                        if not artifact.is_file() or artifact.stat().st_size < 20:
                            raise RuntimeError('A native mechanical export is missing: '+filename)
                        data = artifact.read_bytes()
                        hashes[filename] = hashlib.sha256(data).hexdigest()
                        (publication/filename).write_bytes(data)
                    manifest = {'schema': SCHEMA, 'asset_id': asset_id, 'source': name, 'source_sha256': digest,
                                'name': program['name'], 'created_at': time.time(), 'metrics': report, 'hashes': hashes,
                                'implementation_sha256': implementation, 'freecad_version': kernel_version, 'imports':import_receipts}
                    (publication/'manifest.json').write_text(json.dumps(manifest, indent=2))
                    accepted_manifest_sha = hashlib.sha256((publication/'manifest.json').read_bytes()).hexdigest()
                    publication.rename(folder)
                finally:
                    if publication.exists():
                        shutil.rmtree(publication)
                try:
                    record = _record(p, folder, manifest_sha256=accepted_manifest_sha, source=name, source_bytes=raw, implementation=implementation)
                    return _commit_record(p, name, record, path, before, candidate)
                except Exception:
                    shutil.rmtree(folder)
                    raise
    finally:
        with p.lock:
            p.engine_busy = False
        status = 'running' if p.worker is threading.current_thread() else 'idle'
        try:p.set_status('stopped' if p.cancel.is_set() else status, 'Mechanical build stopped.' if p.cancel.is_set() else 'Mechanical build finished; review the source and native findings.')
        except Exception as error:logging.getLogger(__name__).warning('Mechanical busy state released; status notification failed: %s', error)
