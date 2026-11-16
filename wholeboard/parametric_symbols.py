"""Pin-driven native symbols. Physical pin numbers, types and PCB data are immutable."""
from __future__ import annotations
import copy
import json
import math
import re
import tempfile
import threading
from pathlib import Path
from . import project_library
from .sexpr import S, Sym, find, find_all

SIDES = {'left': 0, 'right': 180, 'top': 270, 'bottom': 90}
PIN_FIELDS = {'side', 'group', 'section', 'order', 'subsymbol', 'name'}
META = 'WB Parametric Layout'
PITCH, LEAD = 2.54, 3.81


def _text(value, limit=80):
    return isinstance(value, str) and len(value) <= limit and (not value or value.isprintable())


def source_pins(component, spec):
    from .kicad import schematic
    node = schematic.load_symbol(component.get('symbol', ''), spec)
    if node is None:
        raise ValueError('Choose a real source symbol before editing its parametric layout.')
    result = {}
    shapes = {}
    for part in find_all(node, 'symbol'):
        for pin in find_all(part, 'pin'):
            number = find(pin, 'number')
            if number:shapes.setdefault(str(number[1]), str(pin[2]))
    for unit, pins in sorted(schematic.symbol_pins(node).items()):
        for pin in pins:
            if pin['number'] not in result:
                result[pin['number']] = {**pin, 'unit': max(1, unit), 'shape': shapes.get(pin['number'], 'line')}
    if not result:
        raise ValueError('The source symbol has no physical pins to organize.')
    return node, list(result.values()), schematic.unit_count(node)


def settings(component, spec):
    node, pins, count = source_pins(component, spec)
    cfg = component.get('symbol_layout') or {}
    defaults = [''] if count == 1 else [chr(65+i) for i in range(count)]
    active = cfg.get('style', 'native') == 'parametric'
    units = cfg.get('units', defaults) if active else defaults
    sections = list(cfg.get('sections', [])) if active else []
    records = []
    for pin in pins:
        override = cfg.get('pins', {}).get(pin['number'], {}) if active else {}
        base = units[min(pin['unit']-1, len(units)-1)]
        value = {**pin, 'side': next((side for side, angle in SIDES.items() if angle == pin['angle']), 'left'),
                 'group': '', 'section': '', 'order': 0, 'subsymbol': base, **override}
        value['source_unit'] = pin['unit'];value['unit'] = units.index(value['subsymbol'])+1
        if value['section'] not in sections:
            sections.append(value['section'])
        records.append(value)
    issues = [{'number':p['number'], 'missing':[field for field in ('side','group','section') if field not in cfg.get('pins',{}).get(p['number'],{})]} for p in records] if active else []
    issues = [item for item in issues if item['missing']]
    return {'source': node, 'pins': records, 'units': units, 'sections': sections, 'style': cfg.get('style', 'native'), 'issues':issues}


def validate(spec):
    for component in spec.get('components', []):
        if 'symbol_layout' not in component:
            continue
        cfg = component['symbol_layout']
        if not isinstance(cfg, dict) or set(cfg)-{'style', 'pins', 'units', 'sections'} or cfg.get('style', 'native') not in ('native', 'parametric'):
            raise ValueError('Symbol layout needs Native or Parametric style and supported presentation fields.')
        _, real, count = source_pins(component, spec)
        known = {p['number'] for p in real}
        units = cfg.get('units', [''] if count == 1 else [chr(65+i) for i in range(count)])
        if not isinstance(units, list) or not 1 <= len(units) <= 26 or any(not isinstance(v, str) or not re.fullmatch(r'[A-Za-z0-9_]{0,24}', v) for v in units) or len(set(units)) != len(units):
            raise ValueError('Use up to26 distinct bounded sub-symbol suffixes.')
        sections = cfg.get('sections', [])
        if not isinstance(sections, list) or len(sections) > 256 or any(not _text(v) for v in sections) or len(set(sections)) != len(sections):
            raise ValueError('Section order needs distinct bounded section names.')
        props = cfg.get('pins', {})
        if not isinstance(props, dict) or len(props) > 2000:
            raise ValueError('Symbol pin layouts must be a bounded pin-number mapping.')
        for number, value in props.items():
            if number not in known or not isinstance(value, dict) or set(value)-PIN_FIELDS:
                raise ValueError('Edit actual source pins; physical pin numbers and electrical types cannot be changed here.')
            for key, field in value.items():
                if key == 'side' and field not in SIDES:
                    raise ValueError('Pin Orientation is Left, Right, Top or Bottom.')
                if key == 'order' and (isinstance(field, bool) or not isinstance(field, (int, float)) or not math.isfinite(field) or abs(field) > 1000000):
                    raise ValueError('Terminal Order needs a bounded finite number.')
                if key in ('group', 'section', 'name') and not _text(field, 100 if key == 'name' else 80):
                    raise ValueError('Pin names, groups and sections need bounded single-line text.')
                if key == 'subsymbol' and field not in units:
                    raise ValueError('Allocate a sub-symbol suffix before assigning its pins.')


def _number_key(pin):
    number = pin['number']
    return (pin.get('order', 0), (0, int(number)) if re.fullmatch(r'[0-9]+', number) else (1, number))


def _rows(pins):
    groups = {}
    for pin in sorted(pins, key=_number_key):
        key = pin['group'] or ('pin', pin['number'])
        groups.setdefault(key, []).append(pin)
    rows = []
    for index, (key, members) in enumerate(groups.items()):
        if index:
            rows.append(('gap', None))
        if isinstance(key, str):
            rows.append(('group', key))
        rows.extend(('pin', pin) for pin in members)
    return rows


def symbol_node(component, spec, original):
    cfg = component.get('symbol_layout') or {}
    if cfg.get('style', 'native') != 'parametric':
        return original
    info = settings(component, spec)
    key = 'Parametric_' + component['ref']
    asset = {'name': component.get('value', component['ref']), 'reference': re.sub(r'\d+$', '', component['ref']), 'pins': [], 'graphics': []}
    metadata = {'units': info['units'], 'by_unit': {}}
    for unit, suffix in enumerate(info['units'], 1):
        pins = [p for p in info['pins'] if p['subsymbol'] == suffix]
        names = [p.get('name', '') for p in pins]+[p.get('group', '') for p in pins]
        width = math.ceil(max(12.7, (max([len(n) for n in names]+[0])*1.0+4)*2,
                              max([sum(p['side'] == side for p in pins) for side in ('top', 'bottom')]+[0])*PITCH+2*PITCH,
                              max([len(s) for s in info['sections']]+[0])*1.0+2*PITCH)/PITCH)*PITCH
        sections = [s for s in info['sections'] if any(p['section'] == s for p in pins)] or ['']
        y, shapes, placed, panels = 0.0, [], [], [];previous_bottom = False
        for section in sections:
            members = [p for p in pins if p['section'] == section]
            if panels and (previous_bottom or any(p['side']=='top' for p in members)):y -= 2*LEAD+PITCH
            left, right = (_rows([p for p in members if p['side'] == side]) for side in ('left', 'right'))
            header = 2 if section else 1
            reserve = {}
            for side in ('top','bottom'):
                vertical = [p for p in members if p['side']==side]
                reserve[side] = math.ceil((max([len(p.get('name','')) for p in vertical]+[0])+2+(PITCH if any(p['group'] for p in vertical) else 0))/PITCH)*PITCH if vertical else 0
            height = max(4, max(len(left), len(right))+header+1)*PITCH+reserve['top']+reserve['bottom']
            top, bottom = y, y-height
            shapes.append({'kind': 'rectangle', 'start': [-width/2, bottom], 'end': [width/2, top], 'fill': 'background', 'unit': unit})
            if section:
                shapes.append({'kind': 'text', 'text': section, 'position': [0, top-reserve['top']-PITCH*.65], 'size': 1.27, 'unit': unit, 'semantic': {'kind': 'section', 'section': section}})
            for side, rows in [('left', left), ('right', right)]:
                for index, (kind, value) in enumerate(rows):
                    py = top-reserve['top']-(header+index)*PITCH
                    if kind == 'pin':
                        placed.append({**value, 'x': (-1 if side == 'left' else 1)*(width/2+LEAD), 'y': py, 'angle': SIDES[side], 'unit': unit, 'length': LEAD, 'hidden': False})
                    elif kind == 'group':
                        shapes.append({'kind': 'text', 'text': value, 'position': [(-1 if side == 'left' else 1)*width/4, py], 'size': 1.0, 'unit': unit, 'semantic': {'kind': 'group', 'group': value, 'section': section, 'side': side}})
            for side in ('top', 'bottom'):
                row = sorted([p for p in members if p['side'] == side], key=_number_key)
                for index, pin in enumerate(row):
                    placed.append({**pin, 'x': (index-(len(row)-1)/2)*PITCH, 'y': (top+LEAD if side == 'top' else bottom-LEAD), 'angle': SIDES[side], 'unit': unit, 'length': LEAD, 'hidden': False})
                for group in dict.fromkeys(p['group'] for p in row if p['group']):
                    shapes.append({'kind': 'text', 'text': group, 'position': [0, top-reserve['top']+.6*PITCH if side == 'top' else bottom+reserve['bottom']-.6*PITCH], 'size': 1.0, 'unit': unit, 'semantic': {'kind': 'group', 'group': group, 'section': section, 'side': side}})
            panels.append({'name': section, 'bounds': [-width/2, bottom, width/2, top]})
            y = bottom;previous_bottom = any(p['side']=='bottom' for p in members)
        shift = -(panels[-1]['bounds'][1]+panels[0]['bounds'][3])/2
        for shape in shapes:
            for field in ('start', 'end', 'position'):
                if field in shape:
                    shape[field][1] = round(shape[field][1]+shift, 6)
        for pin in placed:
            pin['y'] = round(pin['y']+shift, 6)
        for panel in panels:
            panel['bounds'][1] += shift;panel['bounds'][3] += shift
        asset['graphics'].extend(shapes)
        asset['pins'].extend({k: p[k] for k in ('number', 'name', 'x', 'y', 'angle', 'length', 'type', 'shape', 'unit', 'hidden')} for p in placed)
        metadata['by_unit'][str(unit)] = {'suffix': suffix, 'sections': panels, 'pins': placed, 'labels': [{'text': s['text'], 'position': s['position'], **s['semantic']} for s in shapes if s.get('semantic')]}
    temporary = {'library': {'symbols': {key: asset}}}
    project_library.validate_asset('symbols', key, asset)
    node = project_library.symbol_node(temporary, 'Project:'+key)
    node[1] = 'OpenFabroParametric:'+key
    node.append([Sym('property'), META, json.dumps(metadata, ensure_ascii=False, separators=(',', ':')), S(Sym('at'), 0, 0, 0), S(Sym('hide'), Sym('yes')), [Sym('effects'), [Sym('font'), S(Sym('size'), 1.27, 1.27)]]])
    return node


def native_metadata(node):
    prop = next((p for p in find_all(node, 'property') if p[1] == META), None)
    return json.loads(prop[2]) if prop else None


def prepare(spec, arguments):
    out = copy.deepcopy(spec);component = next((c for c in out['components'] if c['ref'] == arguments.get('ref')), None)
    if not component or component.get('terminal'):
        raise ValueError('Choose a component; module terminals use their terminal editor.')
    original = settings(component, out);cfg = component.setdefault('symbol_layout', {'style': 'parametric'})
    cfg.setdefault('units', copy.deepcopy(original['units']));cfg.setdefault('pins', {});cfg.setdefault('sections', copy.deepcopy(original['sections']))
    action = arguments.get('action');patch = arguments.get('patch', {})
    if action == 'style':
        cfg['style'] = arguments.get('style')
    elif action in ('pins', 'move'):
        if action == 'move':patch = {k: arguments[k] for k in ('side', 'section', 'group', 'subsymbol') if k in arguments}
        pins = arguments.get('pins')
        if not isinstance(pins, list) or not pins or len(pins) > 2000 or not isinstance(patch, dict) or set(patch)-PIN_FIELDS:
            raise ValueError('Select real pins and supported symbol properties.')
        known = {p['number'] for p in original['pins']}
        if any(pin not in known for pin in pins):
            raise ValueError('Choose actual source pin numbers.')
        suffix = patch.get('subsymbol')
        if suffix is not None and suffix not in cfg['units']:
            cfg['units'].append(suffix)
        if patch.get('section') is not None and patch['section'] not in cfg['sections']:
            cfg['sections'].append(patch['section'])
        cfg['style'] = 'parametric'
        for pin in pins:
            values = cfg['pins'].setdefault(pin, {})
            for key, value in patch.items():
                if value is None: values.pop(key, None)
                else: values[key] = copy.deepcopy(value)
            if not values: cfg['pins'].pop(pin)
        if action == 'move':
            resolved = settings(component, out)['pins'];by_number = {p['number']:p for p in resolved};first = by_number[pins[0]]
            peers = sorted([p for p in resolved if all(p[field] == first[field] for field in ('side', 'section', 'group', 'subsymbol'))], key=_number_key)
            order = [p['number'] for p in peers if p['number'] not in pins]
            before = arguments.get('before');selected = [p['number'] for p in sorted(resolved, key=_number_key) if p['number'] in pins]
            at = order.index(before) if before in order else len(order)
            order[at:at] = selected
            for index, number in enumerate(order):cfg['pins'].setdefault(number, {})['order'] = index
    elif action == 'sections':
        cfg['sections'] = arguments.get('sections')
    elif action == 'rename':
        field = arguments.get('field');old = arguments.get('from');new = arguments.get('to')
        if field not in ('group', 'section', 'subsymbol'):
            raise ValueError('Rename a group, section or sub-symbol.')
        cfg['style'] = 'parametric'
        for pin in original['pins']:
            if pin.get(field) == old and (field=='subsymbol' or 'pins' not in arguments or pin['number'] in arguments['pins']):cfg['pins'].setdefault(pin['number'], {})[field] = new
        if field == 'section':cfg['sections'] = list(dict.fromkeys(new if s == old else s for s in cfg['sections']))
        if field == 'subsymbol':cfg['units'] = [new if s == old else s for s in cfg['units']]
    elif action == 'remove_unit':
        suffix = arguments.get('suffix');old_units = list(cfg['units'])
        if cfg.get('style') != 'parametric' or suffix not in old_units or any(p['subsymbol'] == suffix for p in original['pins']):
            raise ValueError('Only an empty sub-symbol can be removed; move its pins first.')
        for pin in original['pins']:cfg['pins'].setdefault(pin['number'], {}).setdefault('subsymbol', pin['subsymbol'])
        cfg['units'] = [s for s in old_units if s != suffix]
        def remap(key, prefix=''):
            if not key.startswith(prefix+component['ref']):return key
            tail = key[len(prefix+component['ref']):]
            if tail and not re.fullmatch(r'#\d+', tail):return key
            index = int(tail[1:]) if tail else 1
            if not 1 <= index <= len(old_units):return key
            label = old_units[index-1]
            if label not in cfg['units']:return None
            new_index = cfg['units'].index(label)+1
            return prefix+component['ref']+('#'+str(new_index) if new_index > 1 else '')
        editor = out.get('editor', {})
        for field in ('positions', 'rotations', 'mirrors'):
            if field in editor:editor[field] = {new: value for key, value in editor[field].items() if (new := remap(key)) is not None}
        for state in (editor.get('object_tree') or {}).values():
            state['parents'] = {new: parent for key, parent in state.get('parents', {}).items() if (new := remap(key, 'symbol:')) is not None}
            state['order'] = {parent: list(dict.fromkeys(new for key in ids if (new := remap(key, 'symbol:')) is not None)) for parent, ids in state.get('order', {}).items()}
    else:
        raise ValueError('Choose style, pins, sections or rename for symbol editing.')
    validate(out)
    changed = out != spec
    return {'spec': out, 'ref': component['ref'], 'layout': {k: v for k, v in settings(component, out).items() if k != 'source'}, 'summary': {'changed': changed, 'physical_pins_unchanged': True, 'pcb_unchanged': True, 'rerouted_guides': []}}


def project_draft(project, arguments):
    from . import schematic_view
    from .workbench import validate_draft
    from .kicad import schematic, cli
    with project.lock:
        version = project.state.get('workbench', {}).get('version', 0)
        if arguments.get('base_version', version) != version:raise ValueError('The design changed before the symbol edit.')
        if getattr(project, 'engine_busy', False) or project.worker and project.worker.is_alive() and project.worker is not threading.current_thread():raise ValueError('Wait for the active run before editing symbols.')
        original = copy.deepcopy(project.state['spec'])
    before = schematic_view.scene(original)
    # Preserve every existing schematic pose while the symbol body grows or splits.
    frozen = copy.deepcopy(original);positions = frozen.setdefault('editor', {}).setdefault('positions', {})
    for symbol in before['symbols']:
        positions.setdefault(symbol['key'], [round(v, 6) for v in symbol['position']])
    result = prepare(frozen, arguments);out = result['spec'];ref = result['ref']
    updated = next(c for c in out['components'] if c['ref'] == ref);info = settings(updated, out)
    unit_of = {p['number']: info['units'].index(p['subsymbol'])+1 for p in info['pins']}
    result['summary']['released_exact_routes'] = []
    for guide in out.get('editor', {}).get('connection_guides', []):
        affected = False
        for field in ('from', 'to'):
            anchor = guide[field];head, _, number = anchor.partition('.')
            if head.split('#')[0] == ref and number in unit_of:
                unit = unit_of[number];guide[field] = (ref if unit == 1 else ref+'#'+str(unit))+'.'+number;affected = True
    # Keep an exact drawing whenever the emitted native endpoints and path are still valid.
    # Shape/name edits alone are not permission to discard a hand-routed path.
    candidate = schematic_view.scene(out);candidate_routes = {r['index']:r for r in candidate['routes']}
    for index, guide in enumerate(out.get('editor', {}).get('connection_guides', [])):
        if guide.get('fixed_points') and not candidate_routes.get(index, {}).get('fixed_path'):
            guide.pop('fixed_points', None);result['summary']['released_exact_routes'].append(guide.get('id', f'Wire {index+1}'))
    after = schematic_view.scene(out) if result['summary']['released_exact_routes'] else candidate
    old_routes = {r['index']:r for r in before['routes']};new_routes = {r['index']:r for r in after['routes']}
    lost = [r.get('id', f'Wire {index+1}') for index,r in old_routes.items() if r['status']=='routed' and new_routes.get(index,{}).get('status')!='routed']
    if lost:raise ValueError('Symbol layout makes an existing drawing unroutable: '+', '.join(lost)+'. Move the symbols apart or review the wire route first.')
    result['summary']['rerouted_guides'] = [r.get('id', f'Wire {index+1}') for index,r in new_routes.items() if r.get('points')!=old_routes.get(index,{}).get('points')]
    validate_draft(out)
    with tempfile.TemporaryDirectory(prefix='openfabro-symbol-') as folder:
        built = schematic.build(out, Path(folder));proof = schematic.netlist_parity(out, cli.schematic_nets(Path(built['sch'])))
        if not proof['ok']:
            raise ValueError('The symbol layout changed native pin connectivity. Separate the symbols or review affected wire routes.')
    result['summary']['requires_route_review'] = bool(result['summary']['released_exact_routes'])
    result['native_parity'] = proof;result['scene'] = after;result['base_version'] = version
    with project.lock:
        if project.state.get('workbench', {}).get('version', 0) != version:raise ValueError('The design changed while the symbol layout was checked.')
    return result
