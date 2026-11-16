"""Serialize the actual native schematic's library geometry for the web editor.

Using the emitted KiCad document shares symbol fallback, units, fields and pin
numbering with export rather than maintaining a second hand-drawn circuit model.
"""
from __future__ import annotations

import hashlib
import json
import re
import tempfile
from collections import OrderedDict
from pathlib import Path

from . import sexpr
from . import sheets as hierarchy
from . import design_identity
from .kicad import schematic
from .sexpr import find, find_all, num, tag

_cache: OrderedDict[str, dict] = OrderedDict()


def _point(node: list) -> list[float]:
    return [num(node[1]), num(node[2])]


def _definition(node: list, unit: int) -> dict:
    graphics, shapes = [], {}
    for sub in find_all(node, "symbol"):
        match = re.search(r"_(\d+)_(\d+)$", str(sub[1]))
        if not match or int(match[1]) not in (0, unit) or int(match[2]) != 1:
            continue
        for g in sub:
            kind = tag(g)
            if kind == "pin":
                number = find(g, "number")
                if number:
                    shapes[str(number[1])] = {"shape": str(g[2]), "hidden": any(x == "hide" for x in g if isinstance(x, str)) or bool(find(g,"hide") and str(find(g,"hide")[1])=="yes")}
            if kind not in ("rectangle", "polyline", "circle", "arc", "bezier", "text"):
                continue
            item = {"kind": kind}
            for name in ("start", "end", "mid", "center"):
                point = find(g, name)
                if point:
                    item[name] = _point(point)
            points = find(g, "pts")
            if points:
                item["points"] = [_point(p) for p in points[1:] if tag(p) == "xy"]
            radius = find(g, "radius")
            if radius:
                item["radius"] = num(radius[1])
            fill = find(g, "fill")
            if fill and find(fill, "type"):
                item["fill"] = str(find(fill, "type")[1])
            if kind == "text":
                item["text"] = str(g[1])
                at = find(g, "at")
                item["position"] = _point(at) if at else [0, 0]
                item["angle"] = num(at[3]) if at and len(at) > 3 else 0
                effects=find(g,'effects');font=find(effects,'font') if effects else None;size=find(font,'size') if font else None
                item['size']=num(size[2]) if size and len(size)>2 else 1.27
            graphics.append(item)
    pins = schematic.symbol_pins(node)
    def hidden(value):
        return any(x=='hide' for x in (value or []) if isinstance(x,str)) or bool(value and find(value,'hide') and str(find(value,'hide')[1])=='yes')
    visible_names = not hidden(find(node,'pin_names'))
    visible_numbers = not hidden(find(node,'pin_numbers'))
    from .parametric_symbols import native_metadata
    metadata = native_metadata(node)
    return {"lib_id": str(node[1]), "unit": unit, "unit_count": schematic.unit_count(node),
            **({'parametric': metadata['by_unit'][str(unit)]} if metadata else {}),
            "bbox": schematic._bbox(node, unit), "graphics": graphics,
            "pins": [{**p, **shapes.get(p["number"], {})} for p in pins.get(0, []) + pins.get(unit, [])],
            "show_pin_names": visible_names, "show_pin_numbers": visible_numbers}


def scene(spec: dict) -> dict:
    fingerprint = design_identity.fingerprint(spec)
    if fingerprint in _cache:
        return _cache[fingerprint]
    result = {"fingerprint":fingerprint,"fingerprint_policy":design_identity.POLICY,"mm_per_unit": schematic.EDITOR_MM_PER_UNIT, "origin_mm": schematic.EDITOR_ORIGIN_MM,
              "symbols": [], "label_symbols": [], "definitions": {}, "sheets": [], "sheet_nodes": [], "wires":[],"junctions":[],"routes":[],"anchors":[],"wire_nodes":[{'id':key,**value} for key,value in spec.get('editor',{}).get('wire_nodes',{}).items()]}
    boundaries=hierarchy.boundaries(spec)
    definitions=hierarchy.definitions(spec)
    contained={key:{key} for key in definitions}
    for key in reversed(hierarchy.order(spec)):
        parent=definitions[key].get('parent','')
        if parent:contained[parent]|=contained[key]
    with tempfile.TemporaryDirectory(prefix="wholeboard-schematic-") as directory:
        output = schematic.build(spec, Path(directory))
        for page in output["pages"]:
            path = Path(directory) / page["file"]
            tree = sexpr.parse(path.read_text())
            library = find(tree, "lib_symbols") or []
            definitions = {str(node[1]): node for node in library[1:] if tag(node) == "symbol"}
            scale, origin = schematic.EDITOR_MM_PER_UNIT, schematic.EDITOR_ORIGIN_MM
            wiring=page.get("wiring") or {}
            for anchor in wiring.get('anchors',[]):
                result['anchors'].append({'anchor':anchor['anchor'],'sheet':page['name'],
                    'position':[(v-origin)/scale for v in anchor['point']],
                    'escape':[(v-origin)/scale for v in anchor['escape']]})
            wire_nets={wire["uuid"]:wire["net"] for wire in wiring.get("segments",[])}
            junction_nets={junction["uuid"]:junction["net"] for junction in wiring.get("junctions",[])}
            for wire in find_all(tree,"wire"):
                pts=find(wire,"pts");wire_id=str(find(wire,"uuid")[1])
                result["wires"].append({"id":wire_id,"sheet":page["name"],"net":wire_nets.get(wire_id,""),
                    "points":[[(num(p[1])-origin)/scale,(num(p[2])-origin)/scale] for p in pts[1:] if tag(p)=="xy"]})
            for junction in find_all(tree,"junction"):
                at=find(junction,"at");jid=str(find(junction,"uuid")[1]);diameter=find(junction,"diameter")
                result["junctions"].append({"id":jid,"sheet":page["name"],"net":junction_nets.get(jid,""),
                    "position":[(num(at[1])-origin)/scale,(num(at[2])-origin)/scale],"diameter":num(diameter[1])/scale})
            for route in wiring.get("routes",[]):
                result["routes"].append({**route,"sheet":page["name"],
                    "joins":{key:{**join,"point":[(join['point'][0]-origin)/scale,(join['point'][1]-origin)/scale]} for key,join in route.get('joins',{}).items()},
                    "points":[[(p[0]-origin)/scale,(p[1]-origin)/scale] for p in route["points"]]})
            result["sheets"].append({"name": page["name"], "title": page["title"], "parent": page.get("parent", ""),
                "extent": [(v-origin)/scale for v in page["extent"]] if page.get("extent") else None})
            for sheet in find_all(tree, "sheet"):
                props = {str(p[1]): str(p[2]) for p in find_all(sheet, "property")}
                target = next((p["name"] for p in output["pages"] if p["file"] == props.get("Sheetfile")), props.get("Sheetname", ""))
                at, size = find(sheet, "at"), find(sheet, "size")
                ports = []
                for pin in find_all(sheet, "pin"):
                    point = find(pin, "at")
                    net=boundaries.get(target,{}).get(str(pin[1]),{}).get('net',str(pin[1]))
                    refs={c['ref'] for c in spec.get('components',[]) if hierarchy.component_sheet(c) in contained.get(target,set())}
                    metadata=boundaries.get(target,{}).get(str(pin[1]),{})
                    terminal=(metadata['terminal_ref']+'.1') if metadata.get('terminal_ref') else next((p for n in spec.get('nets',[]) if n['name']==net for p in n['pins'] if p.split('.',1)[0] in refs),None)
                    ports.append({**metadata,"net":net,"pin":terminal, "label":str(pin[1]), "position": [(num(point[1])-origin)/scale,(num(point[2])-origin)/scale],
                                  "angle": num(point[3]) if len(point)>3 else 0})
                result["sheet_nodes"].append({"name": props.get("Sheetname", target), "target": target, "sheet": page["name"],
                    "position": [round((num(at[1])-origin)/scale,4),round((num(at[2])-origin)/scale,4)],
                    "size": [round(num(size[1])/scale,4),round(num(size[2])/scale,4)], "ports": ports})
            for instance in find_all(tree, "symbol"):
                lib = str(find(instance, "lib_id")[1])
                unit = int(num(find(instance, "unit")[1]))
                definition_key = f"{lib}#{unit}"
                if definition_key not in result["definitions"]:
                    result["definitions"][definition_key] = _definition(definitions[lib], unit)
                at = find(instance, "at")
                fields = []
                ref = ""
                for prop in find_all(instance, "property"):
                    if prop[1] == "Reference":
                        ref = str(prop[2])
                    if prop[1] not in ("Reference", "Value"):
                        continue
                    p = find(prop, "at")
                    effects = find(prop, "effects")
                    justify = find(effects, "justify") if effects else None
                    fields.append({"name": str(prop[1]), "value": str(prop[2]), "position_mm": _point(p),
                                   "angle": num(p[3]) if len(p) > 3 else 0, "left": bool(justify and str(justify[1]) == "left")})
                scale, origin = schematic.EDITOR_MM_PER_UNIT, schematic.EDITOR_ORIGIN_MM
                destination='label_symbols' if ref in output.get('annotation_refs',{}) else 'symbols'
                result[destination].append({**({'id':output['annotation_refs'][ref]} if destination=='label_symbols' else {}),"ref": ref, "key": ref if unit == 1 else f"{ref}#{unit}", "unit": unit,
                    "definition": definition_key, "position": [(num(at[1])-origin)/scale, (num(at[2])-origin)/scale],
                    "rotation": num(at[3]) if len(at) > 3 else 0, "mirror":str(find(instance,'mirror')[1]) if find(instance,'mirror') else '', "fields": fields, "sheet": page["name"]})
    _cache[fingerprint] = result
    if len(_cache) > 8:
        _cache.popitem(last=False)
    return result
