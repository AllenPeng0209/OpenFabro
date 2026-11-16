"""Write a KiCad 10 schematic (.kicad_sch) from a design spec.

Every component gets its library symbol (or a generated box symbol when the spec names none). Pins connect
through net labels, so the schematic is electrically identical to the board's netlist.

To make it readable:
- Each building block (or group named by a component's "sheet") gets a sheet of its own in a hierarchical
  schematic, with hierarchical labels for the nets it shares with the rest; the main sheet holds the other
  parts and a sheet symbol per block.
- On each sheet the parts are gathered round the IC or connector they share nets with, and the groups run in
  signal order: connectors, protection, regulators, the main parts, then indicators and controls.
- Supply nets use global labels; nets that stay on one sheet use local labels.
"""

from __future__ import annotations

import copy
import json
import math
import re
import uuid
from pathlib import Path

from .. import __version__, design, sexpr
from ..sexpr import S, Sym, find, find_all, num, tag
from . import libs

FORMAT_VERSION = "20260306"
GRID = 2.54
_NS = uuid.UUID("6f1b8d52-8c41-4b9e-9a77-3d0f2b9e5a10")
_SYM_CACHE: dict[str, list | None] = {}
_FILE_CACHE: dict[str, str] = {}


def symbol_uuid(project: str, ref: str) -> str:
    """Stable UUID shared by a schematic symbol and its footprint's path."""
    return str(uuid.uuid5(_NS, f"{project}/{ref}"))


def uid() -> str:
    return str(uuid.uuid4())


def _snap(v: float) -> float:
    return round(v / GRID) * GRID


# ---------------------------------------------------------------- symbol library access

def _extract(text: str, name: str) -> str | None:
    """Cut one top-level symbol out of a .kicad_sym file without parsing all of it."""
    m = re.search(r'^\t\(symbol "' + re.escape(name) + r'"', text, re.M)
    if not m:
        return None
    i = m.start() + 1
    depth, in_str, esc = 0, False, False
    for j in range(i, len(text)):
        ch = text[j]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return text[i:j + 1]
    return None


def load_symbol(lib_id: str, spec: dict | None = None) -> list | None:
    """The symbol node, with any `extends` resolved, named 'Lib:Name'."""
    if not isinstance(lib_id,str) or not re.fullmatch(r"[^/\\:]+:[^/\\]+",lib_id):
        return None
    if lib_id.startswith("Project:"):
        from ..project_library import symbol_node
        return symbol_node(spec,lib_id)
    if lib_id in _SYM_CACHE:
        return _SYM_CACHE[lib_id]
    if ":" not in lib_id:
        return None
    lib, name = lib_id.split(":", 1)
    root = libs.locate("symbols")
    node = None
    if root:
        path = root / f"{lib}.kicad_sym"
        if path.exists():
            key = str(path)
            if key not in _FILE_CACHE:
                _FILE_CACHE[key] = path.read_text(encoding="utf-8")
            snippet = _extract(_FILE_CACHE[key], name)
            if snippet:
                node = sexpr.parse(snippet)
                ext = find(node, "extends")
                if ext:
                    parent = load_symbol(f"{lib}:{ext[1]}")
                    node = _flatten(node, parent, name, str(ext[1])) if parent else None
    if node is not None:
        node = copy.deepcopy(node)
        node[1] = lib_id
    _SYM_CACHE[lib_id] = node
    return node


def _flatten(child: list, parent: list, name: str, parent_name: str) -> list:
    out = copy.deepcopy(parent)
    out[1] = name
    props = {p[1]: p for p in find_all(child, "property")}
    for i, c in enumerate(out):
        if tag(c) == "property" and c[1] in props:
            out[i] = copy.deepcopy(props.pop(c[1]))
        elif tag(c) == "symbol" and isinstance(c[1], str):
            c[1] = c[1].replace(parent_name, name, 1)
    out.extend(props.values())
    return out


def symbol_pins(node: list) -> dict[int, list[dict]]:
    """Pins per unit (unit 0 = shared by all units)."""
    units: dict[int, list[dict]] = {}
    base = str(node[1]).split(":")[-1]
    for sub in find_all(node, "symbol"):
        m = re.match(re.escape(base) + r"_(\d+)_(\d+)$", str(sub[1]))
        if not m:
            m = re.search(r"_(\d+)_(\d+)$", str(sub[1]))
        if not m or int(m.group(2)) > 1:
            continue
        unit = int(m.group(1))
        for p in find_all(sub, "pin"):
            at = find(p, "at")
            nm, no = find(p, "name"), find(p, "number")
            units.setdefault(unit, []).append({
                "x": num(at[1]), "y": num(at[2]), "angle": num(at[3]) if len(at) > 3 else 0,
                "length": num(find(p, "length")[1]) if find(p, "length") else 2.54,
                "name": str(nm[1]) if nm else "", "number": str(no[1]) if no else "",
                "type": str(p[1]),
                "hidden": any(v == "hide" for v in p if isinstance(v, str)) or bool(find(p, "hide") and str(find(p, "hide")[1]) == "yes"),
            })
    return units


def unit_count(node: list) -> int:
    from ..parametric_symbols import native_metadata
    metadata = native_metadata(node)
    if metadata:return len(metadata['units'])
    us = [u for u in symbol_pins(node) if u > 0]
    return max(us) if us else 1


def _bbox(node: list, unit: int) -> tuple[float, float, float, float]:
    xs, ys = [], []
    base = str(node[1]).split(":")[-1]
    for sub in find_all(node, "symbol"):
        m = re.search(r"_(\d+)_(\d+)$", str(sub[1]))
        if not m or int(m.group(1)) not in (0, unit) or int(m.group(2)) > 1:
            continue
        for g in sub:
            t = tag(g)
            if t == "pin":
                at = find(g, "at")
                xs.append(num(at[1])); ys.append(num(at[2]))
            elif t in ("rectangle", "polyline", "circle", "arc", "bezier"):
                for pt in sexpr.walk(g):
                    if tag(pt) in ("start", "end", "xy", "mid", "center"):
                        xs.append(num(pt[1])); ys.append(num(pt[2]))
    _ = base
    if not xs:
        return (-2.54, -2.54, 2.54, 2.54)
    return (min(xs), min(ys), max(xs), max(ys))


def symbol_info(lib_id: str, spec: dict | None = None) -> dict | None:
    node = load_symbol(lib_id,spec)
    if node is None:
        return None
    props = {p[1]: str(p[2]) for p in find_all(node, "property")}
    pins = []
    for unit, plist in sorted(symbol_pins(node).items()):
        for p in plist:
            pins.append({"number": p["number"], "name": p["name"], "type": p["type"], "unit": unit})
    return {"symbol": lib_id, "description": props.get("Description", ""),
            "default_footprint": props.get("Footprint", ""), "units": unit_count(node),
            "pins": pins}


# ---------------------------------------------------------------- generated box symbols

def generic_symbol(lib_id: str, pads: list[str], value: str) -> list:
    """A rectangle with one pin per pad, pins split between the left and right sides."""
    n = len(pads)
    left = pads[: math.ceil(n / 2)]
    right = pads[math.ceil(n / 2):]
    rows = max(len(left), len(right), 1)
    longest = max([len(p) for p in pads] + [2])
    half_w = _snap(max(5.08, longest * 1.6 + 2.54))
    top = _snap((rows - 1) * GRID / 2 + GRID)
    body = [Sym("symbol"), lib_id.split(":")[-1] + "_0_1",
            [Sym("rectangle"), S(Sym("start"), -half_w, top), S(Sym("end"), half_w, -top),
             [Sym("stroke"), S(Sym("width"), 0.254), S(Sym("type"), Sym("default"))],
             [Sym("fill"), S(Sym("type"), Sym("background"))]]]
    pins = [Sym("symbol"), lib_id.split(":")[-1] + "_1_1"]
    for side, plist in ((-1, left), (1, right)):
        for i, pad in enumerate(plist):
            y = top - GRID - i * GRID
            x = side * (half_w + GRID)
            pins.append([Sym("pin"), Sym("passive"), Sym("line"),
                         S(Sym("at"), x, y, 0 if side < 0 else 180), S(Sym("length"), GRID),
                         [Sym("name"), pad, [Sym("effects"), [Sym("font"), S(Sym("size"), 1.27, 1.27)]]],
                         [Sym("number"), pad, [Sym("effects"), [Sym("font"), S(Sym("size"), 1.27, 1.27)]]]])
    node = [Sym("symbol"), lib_id, S(Sym("pin_names"), S(Sym("offset"), 1.016)),
            S(Sym("exclude_from_sim"), Sym("no")), S(Sym("in_bom"), Sym("yes")),
            S(Sym("on_board"), Sym("yes"))]
    for key, val, y in (("Reference", "U", top + 1.27), ("Value", value, -top - 1.27)):
        node.append([Sym("property"), key, val, S(Sym("at"), 0, y, 0),
                     [Sym("effects"), [Sym("font"), S(Sym("size"), 1.27, 1.27)]]])
    for key in ("Footprint", "Datasheet", "Description"):
        node.append([Sym("property"), key, "", S(Sym("at"), 0, 0, 0),
                     [Sym("effects"), [Sym("font"), S(Sym("size"), 1.27, 1.27)], S(Sym("hide"), Sym("yes"))]])
    node += [body, pins, S(Sym("embedded_fonts"), Sym("no"))]
    return node


# ---------------------------------------------------------------- schematic writer

PAPERS = [("A4", 297, 210), ("A3", 420, 297), ("A2", 594, 420), ("A1", 841, 594), ("A0", 1189, 841)]
STAGES = ("connectors", "protection", "power", "main parts", "indicators and controls")
_ANCHOR = re.compile(r"^(U|IC|MOD|J|P|CN|USB|A)\d")


def stage(c: dict) -> int:
    """Where a part sits in the signal order: connector, protection, regulator, load."""
    ref = str(c.get("ref") or "")
    prefix = (re.match(r"[A-Z]+", ref) or re.match("", "")).group(0)
    fp, sym = str(c.get("footprint") or "").lower(), str(c.get("symbol") or "").lower()
    blob = " ".join(str(c.get(k) or "") for k in ("value", "description", "mpn", "symbol")).lower()
    if prefix in ("J", "P", "CN", "USB") or fp.startswith("connector"):
        return 0
    if prefix in ("F", "FB") or re.search(r"\b(tvs|esd|usblc|fuse|polyfuse|ptc|reverse|protect)", blob):
        return 1
    if prefix in ("U", "IC", "PS") and (sym.startswith(("regulator_", "power_management")) or re.search(
            r"\b(ldo|regulator|buck|boost|converter|ams1117|ap2112|xc6206|me6211|tps5|tps6|mp1584|ch224|charger)", blob)):
        return 2
    if prefix in ("U", "IC", "MOD", "A", "Y", "X"):
        return 3
    return 4


def _groups(items: list[dict], pin_net: dict, power: set[str]) -> list[list[dict]]:
    """Gather the parts round the ICs and connectors they share nets with; the IC or connector comes first."""
    refs = list(dict.fromkeys(it["c"]["ref"] for it in items))
    nets_of: dict[str, set[str]] = {r: set() for r in refs}
    for pin, net in pin_net.items():
        r = pin.split(".", 1)[0]
        if r in nets_of:
            nets_of[r].add(net)
    comp = {it["c"]["ref"]: it["c"] for it in items}
    anchors = [r for r in refs if _ANCHOR.match(r)]
    owner = {r: r for r in anchors}

    def score(r: str, a: str) -> tuple:
        sig = len((nets_of[r] & nets_of[a]) - power)
        pwr = len((nets_of[r] & nets_of[a]) - {"GND"})
        return (sig, pwr, stage(comp[a]) == 3)
    for r in refs:
        if r in owner:
            continue
        best = max(anchors, key=lambda a: score(r, a), default=None)
        if best and score(r, best)[0]:
            owner[r] = best
    # parts joined only through other parts (an LED behind its resistor) follow them
    for _ in range(4):
        for r in refs:
            if r in owner:
                continue
            for o in refs:
                if o in owner and (nets_of[r] & nets_of[o]) - power:
                    owner[r] = owner[o]
                    break
    # what is left goes with the IC whose supply it shares (decoupling capacitors), or stays on its own
    for r in refs:
        if r not in owner:
            best = max(anchors, key=lambda a: score(r, a), default=None)
            owner[r] = best if best and score(r, best)[1] else r
    groups: dict[str, list[dict]] = {}
    for it in items:
        groups.setdefault(owner[it["c"]["ref"]], []).append(it)
    for lead, g in groups.items():
        g.sort(key=lambda it: (it["c"]["ref"] != lead, stage(it["c"]), it["c"]["ref"], it["unit"]))
    return sorted(groups.values(), key=lambda g: (stage(g[0]["c"]), -len(g), g[0]["c"]["ref"]))


def _arrange(items: list[dict], pin_net: dict, power: set[str], side: list[tuple[float, float]] = ()) -> tuple:
    """Lay out one sheet: groups in columns by signal order, each group's parts beside its IC or connector.

    side: extra boxes (w, h), such as sheet symbols, put in a column of their own on the right.
    Returns (positions per item, positions per side box, paper, paper width, paper height)."""
    pos: dict[int, tuple[float, float]] = {}
    blocks = []                                     # (stage, w, h, [(item index, dx, dy)])
    index = {id(it): i for i, it in enumerate(items)}
    for g in _groups(items, pin_net, power):
        lead, rest = g[0], g[1:]
        # columns of parts beside the lead part, about as tall as the group is wide
        cap = max(lead["h"], 40.0, math.sqrt(sum(it["w"] * it["h"] for it in rest) * 1.2))
        col, cx, cy, colw = [], lead["w"], 0.0, 0.0
        for it in rest:
            if cy + it["h"] > cap and col:
                cx += colw
                cy, colw = 0.0, 0.0
            col.append((index[id(it)], cx, cy))
            cy += it["h"]
            colw = max(colw, it["w"])
        w = cx + colw if rest else lead["w"]
        h = max([lead["h"]] + [dy + items[i]["h"] for i, _, dy in col])
        blocks.append((stage(lead["c"]), w, h, [(index[id(lead)], 0.0, 0.0)] + col))
    # the groups run down the columns in signal order; a column is as tall as an A-paper-shaped sheet allows
    limit = max([b[2] for b in blocks] + [math.sqrt(sum((b[1] + 10) * (b[2] + 6) for b in blocks) / 1.4)])
    x = y = colw = width = height = 0.0
    for _, w, h, members in blocks:
        if y + h > limit and y > 0:
            x += colw + 12
            y, colw = 0.0, 0.0
        for i, dx, dy in members:
            pos[i] = (x + dx, y + dy)
        y += h + 6
        colw = max(colw, w)
        height = max(height, y)
        width = max(width, x + colw + 12)
    side_pos, y = [], 0.0
    for w, h in side:
        side_pos.append((width + 10, y))
        y += h + 12
        height = max(height, y)
    if side:
        width += 10 + max(w for w, _ in side)
    for paper, pw, ph in PAPERS:
        if width <= pw - 40 and height <= ph - 40:
            break
    else:
        paper, pw, ph = "User", max(1600.0, width + 40), max(1200.0, height + 40)
    return [pos[i] for i in range(len(items))], side_pos, paper, pw, ph


def sheets(spec: dict) -> list[dict]:
    """Main plus explicit/legacy sheets, ordered by their actual hierarchy."""
    from .. import sheets as hierarchy
    spec=design.normalise(spec);hierarchy.validate(spec);defs=hierarchy.definitions(spec);name=spec['name']
    out=[{'name':'','title':'Main','refs':[],'file':f'{name}.kicad_sch','path':'/','uuid':None,'parent':''}];by={'':out[0]}
    for key in hierarchy.order(spec):
        value=defs[key];parent=value.get('parent','');sid=symbol_uuid(name,f'#sheet/{key}')
        bid=next((b.get('block') for b in spec.get('blocks_used') or [] if b.get('name')==key),None)
        node={**value,'name':key,'title':value.get('title') or (f'{key} ({bid})' if bid else key),'refs':[],'file':f'{name}-{key}.kicad_sch','uuid':sid,'parent':parent,'path':by[parent]['path'].rstrip('/')+'/'+sid}
        by[key]=node;out.append(node)
    for component in spec['components']:by[hierarchy.component_sheet(component)]['refs'].append(component['ref'])
    return out


def board_links(spec: dict) -> dict[str, tuple[str, str, str]]:
    """ref -> (footprint path, sheet name, sheet file), linking each footprint to its schematic symbol."""
    name = design.normalise(spec)["name"]
    out = {};pages=sheets(spec);by={page['name']:page for page in pages}
    for sh in pages:
        titles=[];current=sh
        while current['name']:
            titles.append(current['title']);current=by[current.get('parent','')]
        sheetname='/'+'/'.join(reversed(titles))+'/' if titles else '/'
        for ref in sh["refs"]:
            path = sh['path'].rstrip('/') + f"/{symbol_uuid(name, ref)}"
            out[ref] = (path,sheetname,sh['file'])
    return out


def _header(uuid_: str, paper: str, pw: float, ph: float, title: str, lib_symbols: list) -> list:
    return [Sym("kicad_sch"), S(Sym("version"), Sym(FORMAT_VERSION)), S(Sym("generator"), "wholeboard"),
            S(Sym("generator_version"), __version__), [Sym("uuid"), uuid_],
            S(Sym("paper"), paper) if paper != "User" else S(Sym("paper"), "User", pw, ph),
            [Sym("title_block"), [Sym("title"), title[:80]], [Sym("company"), "Generated by OpenFabro"]],
            [Sym("lib_symbols"), *lib_symbols]]


def _label(kind: str, net: str, x: float, y: float, ang: float) -> list:
    just = "left" if ang in (0, 90) else "right"
    eff = [Sym("effects"), [Sym("font"), S(Sym("size"), 1.27, 1.27)], S(Sym("justify"), Sym(just))]
    if kind == "label":
        return [Sym("label"), net, S(Sym("at"), x, y, ang), S(Sym("fields_autoplaced"), Sym("yes")), eff,
                [Sym("uuid"), uid()]]
    return [Sym(kind), net, S(Sym("shape"), Sym("passive")), S(Sym("at"), x, y, ang),
            S(Sym("fields_autoplaced"), Sym("yes")), eff, [Sym("uuid"), uid()]]


EDITOR_MM_PER_UNIT = 0.127
EDITOR_ORIGIN_MM = 20.32


def _instance_pose(it: dict, ox: float, oy: float, editor: dict | None = None) -> tuple[float, float, float]:
    editor = editor or {}
    key = it["c"]["ref"] if it["unit"] == 1 else f"{it['c']['ref']}#{it['unit']}"
    position = (editor.get("positions") or {}).get(key)
    if position is not None:
        x, y = (round(EDITOR_ORIGIN_MM + float(v) * EDITOR_MM_PER_UNIT, 5) for v in position)
    else:
        x0, y0, x1, y1 = it["bbox"]
        x = _snap(20 + ox + it["rx"] - x0)
        y = _snap(20 + oy + it["ry"] + (0 if it["vertical"] else 3) + y1)
    rotation = float((editor.get("rotations") or {}).get(key, 0)) % 360
    return x, y, rotation


def _instance_mirror(it: dict, editor: dict | None = None) -> str:
    key=it['c']['ref'] if it['unit']==1 else f"{it['c']['ref']}#{it['unit']}"
    return ((editor or {}).get('mirrors') or {}).get(key,'')


def _pin_angle(angle: float, rotation: float, mirror: str = '') -> float:
    angle=(angle+rotation+180)%360
    if mirror=='x':angle=-angle
    elif mirror=='y':angle=180-angle
    return angle%360


def _symbol_point(x: float, y: float, px: float, py: float, rotation: float, mirror: str = '') -> tuple[float, float]:
    angle = math.radians(rotation)
    dx,dy=px*math.cos(angle)-py*math.sin(angle),-px*math.sin(angle)-py*math.cos(angle)
    if mirror=='x':dy=-dy
    elif mirror=='y':dx=-dx
    return round(x+dx,5),round(y+dy,5)


def _symbols(out: list, items: list[dict], placed: list, name: str, inst_path: str, pin_net: dict,
             label_kind, editor: dict | None = None, label_name=None) -> None:
    """Append the placed symbol instances, their labels and no-connect flags."""
    for it, (ox, oy) in zip(items, placed):
        c, node, unit = it["c"], it["node"], it["unit"]
        x0, y0, x1, y1 = it["bbox"]
        # symbol origin so that its bbox (y up) lands at the packed spot (y down)
        X, Y, rotation = _instance_pose(it, ox, oy, editor)
        mirror=_instance_mirror(it,editor)
        ref = c["ref"]
        sid = symbol_uuid(name, ref) if unit == 1 else symbol_uuid(name, f"{ref}#{unit}")
        inst = [Sym("symbol"), S(Sym("lib_id"), str(node[1])), S(Sym("at"), X, Y, rotation),
                S(Sym("unit"), unit), S(Sym("body_style"), 1),
                S(Sym("exclude_from_sim"), Sym("no")), S(Sym("in_bom"), Sym("no" if c.get('terminal') else "yes")),
                S(Sym("on_board"), Sym("no" if design.pcb_excluded(c) else "yes")), S(Sym("in_pos_files"), Sym("no" if c.get('terminal') else "yes")),
                S(Sym("dnp"), Sym("yes" if c.get("dnp") else "no")), [Sym("uuid"), sid]]
        if mirror:inst.append(S(Sym('mirror'),Sym(mirror)))
        if it["vertical"]:
            ref_at = (X + x1 + 1.5, Y - 1.27)
            val_at = (X + x1 + 1.5, Y + 1.27)
        else:
            has_v = any(p["angle"] in (90, 270) for p in it["pins"])
            gap = it["ry"] if has_v else 1.27
            ref_at = (X, Y - (y1 + gap))
            val_at = (X, Y - (y0 - gap))
        if rotation or mirror:
            corners = [_symbol_point(X, Y, px, py, rotation,mirror) for px in (x0, x1) for py in (y0, y1)]
            vertical = all((p["angle"] + rotation) % 360 in (90, 270) for p in it["pins"])
            if vertical:
                rx = max(p[0] for p in corners) + 1.5
                ref_at, val_at = (rx, Y - 1.27), (rx, Y + 1.27)
            else:
                ref_at, val_at = (X, min(p[1] for p in corners) - 2.54), (X, max(p[1] for p in corners) + 2.54)
        props = [("Reference", ref, *ref_at, bool(c.get('_net_label'))),
                 ("Value", str(c.get("value") or ""), *val_at, False),
                 ("Footprint", c["footprint"], X, Y, True), ("Datasheet", "", X, Y, True),
                 ("Description", str(c.get("description") or ""), X, Y, True),
                 ("LCSC", str(c.get("lcsc") or ""), X, Y, True)]
        if c.get('bus_type'):props.append(('Bus Type',c['bus_type'],X,Y,True))
        if c.get('pin_properties'):props.append(('WB Pin Properties',json.dumps(c['pin_properties'],ensure_ascii=False,separators=(',',':')),X,Y,True))
        for key, val, px, py, hide in props:
            eff = [Sym("effects"), [Sym("font"), S(Sym("size"), 1.27, 1.27)]]
            if it["vertical"] and key in ("Reference", "Value"):
                eff.append(S(Sym("justify"), Sym("left")))
            p = [Sym("property"), key, val, S(Sym("at"), px, py, 0)]
            if hide:
                p.append(S(Sym("hide"), Sym("yes")))
            p.append(eff)
            inst.append(p)
        for p in it["pins"]:
            inst.append([Sym("pin"), p["number"], [Sym("uuid"), uid()]])
        inst.append([Sym("instances"), [Sym("project"), name,
                     [Sym("path"), inst_path, S(Sym("reference"), ref), S(Sym("unit"), unit)]]])
        out.append(inst)
        nc = {str(x) for x in c.get("no_connect") or []}
        for p in it["pins"]:
            px, py = _symbol_point(X, Y, p["x"], p["y"], rotation,mirror)
            net = pin_net.get(f"{ref}.{p['number']}")
            if net:
                if not c.get('_net_label'):out.append(_label(label_kind(net), label_name(net) if label_name else net, px, py, _pin_angle(p['angle'],rotation,mirror)))
            elif p["number"] in nc or p["type"] != "no_connect":
                out.append([Sym("no_connect"), S(Sym("at"), px, py), [Sym("uuid"), uid()]])


def _wires(out: list, items: list[dict], placed: list, editor: dict, pin_net: dict, sheet_ports: dict | None = None,extra_segments: list | None = None,sheet: str = '',label_kind=None,label_name=None,label_kinds=None) -> dict:
    from . import schematic_wires
    from urllib.parse import quote
    pins, boxes = {}, {}
    for it, (ox, oy) in zip(items, placed):
        x, y, rotation = _instance_pose(it, ox, oy, editor)
        mirror=_instance_mirror(it,editor)
        ref = it["c"]["ref"]
        key = ref if it["unit"] == 1 else f"{ref}#{it['unit']}"
        x0,y0,x1,y1 = it["bbox"]
        corners = [_symbol_point(x,y,px,py,rotation,mirror) for px in (x0,x1) for py in (y0,y1)]
        boxes[key] = (min(p[0] for p in corners),min(p[1] for p in corners),max(p[0] for p in corners),max(p[1] for p in corners))
        for pin in it["pins"]:
            logical = f"{ref}.{pin['number']}"
            pins[f"{key}.{pin['number']}"] = {"point":_symbol_point(x,y,pin["x"],pin["y"],rotation,mirror),
                "angle":_pin_angle(pin['angle'],rotation,mirror),"symbol":key,"net":pin_net.get(logical),"hidden":pin.get("hidden",False)}
    # Module ports must remain clear too, even though cross-sheet nets use labels.
    for i, node in enumerate(find_all(out,"sheet")):
        metadata=(sheet_ports or {}).get(str(find(node,'uuid')[1]),{})
        identifier='sheet:'+metadata.get('name',str(i))
        at,size = find(node,"at"),find(node,"size")
        boxes[identifier]=(num(at[1]),num(at[2]),num(at[1])+num(size[1]),num(at[2])+num(size[2]))
        for port in find_all(node,"pin"):
            at=find(port,"at")
            net=metadata.get('ports',{}).get(str(port[1]),{}).get('net',str(port[1]))
            pins[identifier+'.'+quote(str(port[1]),safe="~()*!.'-")]={"point":(num(at[1]),num(at[2])),"net":net,
                "symbol":identifier,"angle":num(at[3]) if len(at)>3 else 180}
    for identifier,node in editor.get('wire_nodes',{}).items():
        if node.get('sheet','')==sheet:pins['node:'+identifier]={'point':schematic_wires.point(EDITOR_ORIGIN_MM+v*EDITOR_MM_PER_UNIT for v in node['position']),'net':node['net'],'free':True,'labeled':bool(node.get('label'))}
    paths, geometry = schematic_wires.routes(editor.get("connection_guides") or [],pins,boxes,
        scale=EDITOR_MM_PER_UNIT,origin=EDITOR_ORIGIN_MM,initial_segments=extra_segments or ())
    for segment in geometry["segments"]:
        segment["uuid"]=uid()
        out.append([Sym("wire"),[Sym("pts"),S(Sym("xy"),*segment["a"]),S(Sym("xy"),*segment["b"])],
                    [Sym("stroke"),S(Sym("width"),.1778),S(Sym("type"),Sym("default"))],[Sym("uuid"),segment["uuid"]]])
    for junction in geometry["junctions"]:
        junction["uuid"]=uid()
        out.append([Sym("junction"),S(Sym("at"),*junction["point"]),S(Sym("diameter"),.635),
                    S(Sym("color"),0,0,0,0),[Sym("uuid"),junction["uuid"]]])
    from .. import wire_nodes
    for pin in wire_nodes.floating_labels(paths,pins):out.append(_label(label_kind(pin['net']) if label_kind else 'label',label_name(pin['net']) if label_name else pin['net'],*pin['point'],0))
    for identifier,node in editor.get('wire_nodes',{}).items():
        if node.get('sheet','')==sheet and node.get('label') and (label_kinds or {}).get(identifier,'net')=='net':
            px,py=(round(EDITOR_ORIGIN_MM+v*EDITOR_MM_PER_UNIT,5) for v in node['position'])
            out.append(_label('global_label',node['net'],px,py,node['label'].get('rotation',0)%360))
    return {"routes":paths,**geometry,"anchors":[{"anchor":anchor,"point":pin['point'],
        "escape":pin['point'] if pin.get('free') else schematic_wires._escape(pin,boxes[pin['symbol']])} for anchor,pin in pins.items() if not pin.get('hidden')]}


def netlist_parity(spec: dict, actual: dict[str,set[str]]) -> dict:
    """Compare pin groups, including unexpected pins joined to a declared net."""
    desired={net["name"]:set(net["pins"]) for net in spec.get("nets",[]) if net.get("pins")}
    present=set().union(*actual.values()) if actual else set()
    missing=sorted(set().union(*desired.values())-present) if desired else []
    conflicts=[]
    for name,pins in desired.items():
        groups=[group for group in actual.values() if group & pins]
        if len(groups)!=1 or groups[0]!=pins:
            found=set().union(*groups) if groups else set()
            conflicts.append({"net":name,"missing":sorted(pins-found),"unexpected":sorted(found-pins),"native_groups":len(groups)})
    return {"ok":not missing and not conflicts,"nets":len(desired),"pins":sum(map(len,desired.values())),"missing_pins":missing,"conflicts":conflicts}


def _wire_extent(extent, wiring):
    points=[p for wire in wiring["segments"] for p in (wire["a"],wire["b"])]
    if not points:
        return extent
    box=[min(p[0] for p in points)-2,min(p[1] for p in points)-2,max(p[0] for p in points)+2,max(p[1] for p in points)+2]
    return [min(extent[0],box[0]),min(extent[1],box[1]),max(extent[2],box[2]),max(extent[3],box[3])] if extent else box


def _extent(items: list[dict], placed: list, side: list = (), side_pos: list = (), editor: dict | None = None) -> list[float] | None:
    if editor and (editor.get("positions") or editor.get("rotations") or editor.get('mirrors')):
        boxes = []
        for it, (ox, oy) in zip(items, placed):
            x, y, rotation = _instance_pose(it, ox, oy, editor)
            x0, y0, x1, y1 = it["bbox"]
            corners = [_symbol_point(x, y, px, py, rotation,_instance_mirror(it,editor)) for px in (x0, x1) for py in (y0, y1)]
            margin = max(it["rx"], it["ry"], 6)
            boxes.append((min(p[0] for p in corners)-margin, min(p[1] for p in corners)-margin,
                          max(p[0] for p in corners)+margin+12, max(p[1] for p in corners)+margin))
        boxes += [(20+x-14, 20+y-4, 20+x+w+14, 20+y+h+4) for (w,h),(x,y) in zip(side,side_pos)]
        return [min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)] if boxes else None
    boxes = [(ox, oy, ox + it["w"], oy + it["h"]) for it, (ox, oy) in zip(items, placed)]
    boxes += [(x - 14, y - 4, x + w + 14, y + h + 4) for (w, h), (x, y) in zip(side, side_pos)]
    if not boxes:
        return None
    return [20 + min(b[0] for b in boxes), 20 + min(b[1] for b in boxes),
            20 + max(b[2] for b in boxes), 20 + max(b[3] for b in boxes)]


def build(spec: dict, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True,exist_ok=True)
    """Write the schematic: <name>.kicad_sch, plus one sheet per building block when the design uses blocks."""
    spec = design.normalise(spec)
    from .. import net_labels,wire_nodes
    wire_nodes.validate(spec)
    spec,annotation_refs=net_labels.native_spec(spec)
    label_kinds={key:net_labels.kind(spec,node) for key,node in spec.get('editor',{}).get('wire_nodes',{}).items() if node.get('label')}
    name = spec["name"]
    pin_net = design.pin_net_map(spec)
    power = {n["name"] for n in spec["nets"] if n.get("class") == "power"}
    lib_symbols: dict[str, list] = {}
    items = []          # one per placed unit
    notes = []
    editor = spec.get("editor") or {}
    for c in spec["components"]:
        ref = c["ref"]
        fp = libs.load_footprint(c["footprint"],spec)
        pads = fp.pad_names if fp else []
        node = load_symbol(c["symbol"],spec) if c.get("symbol") else None
        if node is not None:
            sym_pins = {p["number"] for plist in symbol_pins(node).values() for p in plist}
            missing = [p for p in pads if p not in sym_pins and f"{ref}.{p}" in pin_net]
            if missing:
                notes.append(f"{ref}: symbol {c['symbol']} has no pin numbered "
                             f"{', '.join(missing[:8])}; used a generated symbol instead")
                node = None
        if node is None:
            lib_id = f"OpenFabro:{re.sub(r'[^A-Za-z0-9_]', '_', c['footprint'].split(':')[-1])}"
            if lib_id not in lib_symbols:
                lib_symbols[lib_id] = generic_symbol(lib_id, pads, c["footprint"].split(":")[-1])
            node = lib_symbols[lib_id]
        else:
            lib_symbols.setdefault(str(node[1]), node)
        from ..parametric_symbols import symbol_node
        node = symbol_node(c, spec, node)
        lib_symbols.setdefault(str(node[1]), node)
        pins_by_unit = symbol_pins(node)
        units = unit_count(node)
        for unit in range(1, units + 1):
            pins = pins_by_unit.get(0, []) + pins_by_unit.get(unit, [])
            x0, y0, x1, y1 = _bbox(node, unit)
            def room(horizontal: bool) -> float:
                lens = [len(pin_net.get(f"{ref}.{p['number']}", "")) for p in pins
                        if (p["angle"] in (0, 180)) == horizontal]
                return (max(lens) * 1.15 + 2.5) if lens and max(lens) else 2.5
            rx, ry = room(True), room(False)
            vertical = all(p["angle"] in (90, 270) for p in pins) and pins
            prop_w = (max(len(ref), len(str(c.get("value") or ""))) * 1.3 + 3) if vertical else 0
            items.append({"c": c, "node": node, "unit": unit, "pins": pins, "vertical": bool(vertical),
                          "bbox": (x0, y0, x1, y1), "w": (x1 - x0) + 2 * rx + prop_w + 6,
                          "h": (y1 - y0) + 2 * ry + (0 if vertical else 6), "rx": rx, "ry": ry})

    from .. import sheets as hierarchy,terminals,wire_nodes
    wire_nodes.validate(spec)
    shs=sheets(spec);root_uuid=symbol_uuid(name,'#root');by={sheet['name']:sheet for sheet in shs}
    ports=hierarchy.boundaries(spec);pages=[];notes_out=notes
    explicit_terminals=any(c.get('terminal') for c in spec['components']) or bool(editor.get('wire_nodes'))
    def port_names(sheet,net):return [label for label,value in ports.get(sheet,{}).items() if value['net']==net]
    def kind_for(sheet):
        def kind(net):
            if explicit_terminals:return 'label' if port_names(sheet,net) else 'global_label'
            if port_names(sheet,net):return 'hierarchical_label'
            return 'global_label' if net in power else 'label'
        return kind
    def name_for(sheet):return lambda net:(port_names(sheet,net) or [net])[0]
    for page_number,sh in enumerate(shs,start=1):
        current=sh['name'];sitems=[it for it in items if it['c']['ref'] in set(sh['refs']) and not it['c'].get('_net_label')];label_stubs=[]
        children=[child for child in shs[1:] if child.get('parent','')==current]
        sizes=[];minimums=[]
        for child in children:
            values=ports[child['name']];labels=list(values);counts={side:sum(port.get('side','left')==side for port in values.values()) for side in terminals.SIDES}
            minimum=(_snap(max(30.0,max([len(label) for label in labels]+[len(child['title'])])*1.4+10,(max(counts['top'],counts['bottom'])+1)*GRID)),_snap(max(10.16,(max(counts['left'],counts['right'])+1)*GRID)))
            requested=child.get('size') or [0,0];sizes.append(tuple(max(minimum[i],float(requested[i])*EDITOR_MM_PER_UNIT) for i in range(2)));minimums.append(minimum)
        placed,side_pos,paper,pw,ph=_arrange(sitems,pin_net,power,sizes)
        body=_header(root_uuid if not current else sh['uuid'],paper,pw,ph,sh['title'] if current else spec.get('summary',name) or name,list(lib_symbols.values()))
        inst_path=f"/{root_uuid}"+sh['path'].rstrip('/')
        _symbols(body,sitems,placed,name,inst_path,pin_net,kind_for(current),editor,name_for(current))
        annotations=[it for it in items if it['c'].get('_net_label') and hierarchy.component_sheet(it['c'])==current]
        _symbols(body,annotations,[(0,0)]*len(annotations),name,inst_path,pin_net,kind_for(current),editor,name_for(current))
        for label in find_all(body,'hierarchical_label'):
            declared=ports.get(current,{}).get(str(label[1]))
            if declared:find(label,'shape')[1]=Sym(declared.get('direction','passive'))
        for child,(w,h),(sx,sy),minimum in zip(children,sizes,side_pos,minimums):
            position=child.get('position');X,Y=(tuple(round(EDITOR_ORIGIN_MM+float(value)*EDITOR_MM_PER_UNIT,5) for value in position) if position else (_snap(20+sx),_snap(20+sy+4)))
            node=[Sym('sheet'),S(Sym('at'),X,Y),S(Sym('size'),w,h),S(Sym('exclude_from_sim'),Sym('no')),S(Sym('in_bom'),Sym('yes')),S(Sym('on_board'),Sym('yes')),S(Sym('dnp'),Sym('no')),S(Sym('fields_autoplaced'),Sym('yes')),
                  [Sym('stroke'),S(Sym('width'),.1524),S(Sym('type'),Sym('solid'))],[Sym('fill'),S(Sym('color'),0,0,0,0)],[Sym('uuid'),child['uuid']],
                  [Sym('property'),'Sheetname',child['title'],S(Sym('at'),X,Y-.7116,0),[Sym('effects'),[Sym('font'),S(Sym('size'),1.27,1.27)],S(Sym('justify'),Sym('left'),Sym('bottom'))]],
                  [Sym('property'),'Sheetfile',child['file'],S(Sym('at'),X,Y+h+.5846,0),[Sym('effects'),[Sym('font'),S(Sym('size'),1.27,1.27)],S(Sym('justify'),Sym('left'),Sym('top'))]]]
            slots={side:0 for side in terminals.SIDES}
            for label,port in terminals.ordered_ports(ports[child['name']]):
                side=port.get('side','left');slots[side]+=1;offset=GRID*slots[side];net=port['net']
                px,py,angle={'left':(X,Y+offset,180),'right':(X+w,Y+offset,0),'top':(X+offset,Y,90),'bottom':(X+offset,Y+h,270)}[side]
                node.append([Sym('pin'),label,Sym(port.get('direction','passive')),S(Sym('at'),px,py,angle),[Sym('uuid'),uid()],[Sym('effects'),[Sym('font'),S(Sym('size'),1.27,1.27)],S(Sym('justify'),Sym('left' if side=='left' else 'right'))]])
                lx,ly=px,py
                if explicit_terminals:
                    lx=round(px+math.cos(math.radians(angle))*GRID,5);ly=round(py-math.sin(math.radians(angle))*GRID,5)
                    label_stubs.append({'net':net,'a':(px,py),'b':(lx,ly)})
                body.append(_label(kind_for(current)(net),name_for(current)(net),lx,ly,angle))
            node.append([Sym('instances'),[Sym('project'),name,[Sym('path'),inst_path,S(Sym('page'),str(shs.index(child)+1))]]]);body.append(node)
        # Every declared upward terminal must have a matching native hierarchical label.
        for label,port in ports.get(current,{}).items():
            if any(str(node[1])==label for node in find_all(body,'hierarchical_label')):continue
            primary=name_for(current)(port['net']);anchor=next((node for node in body if tag(node) in {'label','global_label','hierarchical_label'} and str(node[1])==primary),None)
            at=find(anchor,'at') if anchor else None;px=num(at[1]) if at else 25.4;py=num(at[2]) if at else 25.4+2.54*list(ports[current]).index(label);angle=0
            if port.get('terminal_ref'):
                for item,(ox,oy) in zip(sitems,placed):
                    if item['c']['ref']==port['terminal_ref']:
                        pin=next((pin for pin in item['pins'] if pin['number']=='1'),None)
                        if pin:
                            x,y,rotation=_instance_pose(item,ox,oy,editor);mirror=_instance_mirror(item,editor);px,py=_symbol_point(x,y,pin['x'],pin['y'],rotation,mirror);angle=_pin_angle(pin['angle'],rotation,mirror)
            if explicit_terminals:
                retained=[]
                for value in body:
                    location=find(value,'at') if tag(value)=='label' else None
                    if location and str(value[1])==primary and abs(num(location[1])-px)<1e-5 and abs(num(location[2])-py)<1e-5:
                        if primary!=label:retained.append(_label('label',primary,px,py,(angle+180)%360))
                    else:retained.append(value)
                body[:]=retained
            node=_label('hierarchical_label',label,px,py,angle);find(node,'shape')[1]=Sym(port.get('direction','passive'));body.append(node)
        wiring=_wires(body,sitems,placed,editor,pin_net,{child['uuid']:{'name':child['name'],'ports':ports[child['name']]} for child in children},label_stubs,current,kind_for(current),name_for(current),label_kinds)
        notes_out.extend(f"Wire {route['from']} to {route['to']}: {route.get('reason','uses net labels')}" for route in wiring['routes'] if route['status']!='routed')
        if not current:body.append([Sym('sheet_instances'),[Sym('path'),'/',S(Sym('page'),'1')]])
        body.append(S(Sym('embedded_fonts'),Sym('no')));path=out_dir/sh['file'];path.write_text(sexpr.dumps(body)+'\n',encoding='utf-8')
        extent=_extent(sitems,placed,editor=editor)
        for child in find_all(body,'sheet'):
            at,size=find(child,'at'),find(child,'size');box=[num(at[1])-3,num(at[2])-5,num(at[1])+num(size[1])+3,num(at[2])+num(size[2])+5]
            extent=box if extent is None else [min(extent[0],box[0]),min(extent[1],box[1]),max(extent[2],box[2]),max(extent[3],box[3])]
        for node in editor.get('wire_nodes',{}).values():
            if node.get('sheet','')!=current or not node.get('label'):continue
            x,y=(EDITOR_ORIGIN_MM+v*EDITOR_MM_PER_UNIT for v in node['position']);box=[x-8,y-8,x+max(8,len(node['net'])*1.2),y+8]
            extent=box if extent is None else [min(extent[0],box[0]),min(extent[1],box[1]),max(extent[2],box[2]),max(extent[3],box[3])]
        pages.append({'name':current,'title':sh['title'],'parent':sh.get('parent',''),'file':sh['file'],'page':page_number,'extent':_wire_extent(extent,wiring),'parts':len(sh['refs'])-len(annotations),'wiring':wiring})
    return {'sch':str(out_dir/shs[0]['file']),'paper':pages and paper,'notes':notes_out,'extent':pages[0]['extent'],'pages':pages,'annotation_refs':annotation_refs}


def crop_svg(svg: Path, extent: list[float], margin: float = 6.0) -> None:
    """Crop an exported schematic SVG (units: mm) to the drawn area."""
    x0, y0, x1, y1 = extent[0] - margin, extent[1] - margin, extent[2] + margin, extent[3] + margin
    text = svg.read_text(encoding="utf-8")
    text = re.sub(r'width="[\d.]+mm" height="[\d.]+mm" viewBox="[\d. ]+"',
                  f'width="{x1 - x0:.4f}mm" height="{y1 - y0:.4f}mm" '
                  f'viewBox="{x0:.4f} {y0:.4f} {x1 - x0:.4f} {y1 - y0:.4f}"', text, count=1)
    svg.write_text(text, encoding="utf-8")


def _pack(items: list[dict], width: float, height: float) -> list[tuple[float, float]] | None:
    order = sorted(range(len(items)), key=lambda i: -items[i]["h"])
    pos: dict[int, tuple[float, float]] = {}
    x = y = shelf_h = 0.0
    for i in order:
        w, h = items[i]["w"], items[i]["h"]
        if w > width:
            return None
        if x + w > width:
            x, y, shelf_h = 0.0, y + shelf_h, 0.0
        if y + h > height:
            return None
        pos[i] = (x, y)
        x += w
        shelf_h = max(shelf_h, h)
    return [pos[i] for i in range(len(items))]
