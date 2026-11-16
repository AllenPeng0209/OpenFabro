"""Read a .kicad_pcb into simple JSON geometry for the browser board view."""

from __future__ import annotations

import math
import uuid
from pathlib import Path

from .. import sexpr
from ..sexpr import find, find_all, num, tag

SCHEMA = 9


def _locked(node):
    value=find(node,'locked')
    return value is not None and (len(value)==1 or str(value[1]) in ('yes','true','1'))


def _identity(node: list, scope="board", fallback_key=None) -> str:
    """Keep native UUIDs; old files get scoped, deterministic UUIDs without mutation."""
    native = find(node, "uuid")
    if native and len(native) > 1:
        return str(native[1])
    stamp = find(node, "tstamp")
    value = f"tstamp:{stamp[1]}" if stamp and len(stamp) > 1 else fallback_key or sexpr.dumps(node)
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"kicad:{scope}:{value}"))


def _rot(x: float, y: float, deg: float) -> tuple[float, float]:
    if not deg:
        return x, y
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    return x * c + y * s, -x * s + y * c


def _pt(node) -> list[float]:
    return [round(num(node[1]), 4), round(num(node[2]), 4)]


def read(pcb: Path) -> dict:
    tree = sexpr.parse(pcb.read_text(encoding="utf-8"))
    net_names = {str(n[1]): str(n[2]) for n in find_all(tree, "net") if len(n) > 2}
    out: dict = {"schema":SCHEMA,"outline": [], "footprints": [], "pads": [], "tracks": [], "arcs": [],
                 "vias": [], "zones": [], "zone_sources":[], "zone_definitions":[], "layers": [], "drawings": []}
    layers = find(tree, "layers")
    if layers:
        out["layers"] = [str(l[1]) for l in layers[1:] if isinstance(l, list) and str(l[1]).endswith(".Cu")]
    physical=find(find(tree,'setup') or [],'stackup');inactive=set()
    if physical:
        inactive={str(row[1]) for row in find_all(physical,'layer') if str(row[1]).endswith('.Cu') and find(row,'thickness') and num(find(row,'thickness')[1],math.nan)==0}
        out['native_copper_slots']=list(out['layers']);out['inactive_copper_slots']=sorted(inactive)
    for node in tree[1:]:
        t = tag(node)
        layer = find(node, "layer") if isinstance(node, list) else None
        lname = str(layer[1]) if layer else ""
        if t in ("gr_line", "gr_arc", "gr_rect", "gr_circle") and lname == "Edge.Cuts":
            item = {"id": _identity(node), "kind": t[3:]}
            for key in ("start", "mid", "end", "center"):
                k = find(node, key)
                if k:
                    item[key] = _pt(k)
            out["outline"].append(item)
        elif t == "segment":
            out["tracks"].append({"id":_identity(node),"a": _pt(find(node, "start")), "b": _pt(find(node, "end")),
                                  "w": num(find(node, "width")[1]), "layer": lname,
                                  "net": _net(node, net_names),"locked":_locked(node)})
        elif t == "arc":
            out["arcs"].append({"id":_identity(node),"a": _pt(find(node, "start")), "m": _pt(find(node, "mid")),
                                "b": _pt(find(node, "end")), "w": num(find(node, "width")[1]),
                                "layer": lname, "net": _net(node, net_names),"locked":_locked(node)})
        elif t == "via":
            via_layers = find(node, "layers")
            out["vias"].append({"id":_identity(node),"p": _pt(find(node, "at")), "d": num(find(node, "size")[1]),
                                "drill": num(find(node, "drill")[1]), "net": _net(node, net_names),
                                "type": "micro" if "micro" in node else "blind" if "blind" in node else "through",
                                "layers": [str(l) for l in via_layers[1:]] if via_layers else ["F.Cu", "B.Cu"],"locked":_locked(node)})
        elif t == "zone":
            net = _net(node, net_names)
            zone_id = _identity(node)
            layer_list = find(node, "layers")
            out["zone_definitions"].append({
                "id": zone_id, "net": net, "layers": [str(v) for v in layer_list[1:]] if layer_list else [lname],
                "keepout": find(node, "keepout") is not None,"locked":_locked(node),
                "keepout_rules": {str(rule[0]):str(rule[1]) for rule in (find(node,'keepout') or [])[1:] if isinstance(rule,list) and len(rule)>1},
                "polygons": [[_pt(p) for p in (find(polygon, "pts") or [])[1:] if tag(p) == "xy"] for polygon in find_all(node, "polygon")],
            })
            for fp_ in find_all(node, "filled_polygon"):
                fl = find(fp_, "layer")
                pts = find(fp_, "pts")
                if pts:
                    out["zones"].append({"id": _identity(fp_, f"zone:{zone_id}"), "zone_id": zone_id,
                                         "layer": str(fl[1]) if fl else lname, "net": net,
                                         "pts": [_pt(p) for p in pts[1:] if tag(p) == "xy"]})
        elif t == "footprint":
            _footprint(node, out, net_names)
        elif t in ("gr_line", "gr_arc", "gr_rect", "gr_circle", "gr_poly", "gr_curve", "gr_text", "gr_text_box"):
            _drawing(node, out)
    used=explicit_copper_layers(out);conflicts=inactive&used
    if conflicts:out['stackup_issues']=[{'layer':name,'message':'Zero-thickness copper slot has actual copper content and was kept visible.'} for name in sorted(conflicts)]
    out['layers']=[name for name in out['layers'] if name not in inactive or name in conflicts]
    from .connectivity import _arc_spec,_on_arc
    boundary=[]
    for item in out['outline']+[v for v in out['drawings'] if v['layer']=='Edge.Cuts']:
        points=[item[k] for k in ('start','end','mid') if k in item]+item.get('points',[])
        if item['kind']=='circle' and 'center' in item and 'end' in item:
            x,y=item['center'];radius=math.dist(item['center'],item['end']);points.extend([[x-radius,y],[x+radius,y],[x,y-radius],[x,y+radius]])
        elif item['kind']=='arc' and all(k in item for k in ('start','mid','end')):
            arc=_arc_spec({'a':item['start'],'m':item['mid'],'b':item['end']})
            if arc:
                x,y=arc['center'];radius=arc['radius'];points.extend(p for p in [[x-radius,y],[x+radius,y],[x,y-radius],[x,y+radius]] if _on_arc(arc,p))
        boundary.extend(points)
    if boundary:out['bbox']=[round(min(p[0] for p in boundary),4),round(min(p[1] for p in boundary),4),round(max(p[0] for p in boundary),4),round(max(p[1] for p in boundary),4)]
    from .copper import capture_zone
    out['zone_sources']=[capture_zone(node,_net(node,net_names),out.get('bbox',[100,100])[:2]) for node in find_all(tree,'zone')]
    from .connectivity import airwires
    out["airwire_objects"] = airwires(out, with_net=True)
    out["ratsnest"] = [[wire["a"], wire["b"]] for wire in out["airwire_objects"]]
    out["drawing_layers"] = sorted({g["layer"] for g in out["drawings"]})
    return out


def explicit_copper_layers(data):
    used=set()
    for key in ('tracks','arcs','vias','zones','zone_definitions','drawings'):
        for item in data.get(key,[]):
            used.update(item.get('layers',[]))
            if item.get('layer'):used.add(item['layer'])
    for pad in data.get('pads',[]):
        if pad.get('kind') in {'smd','connect'} or pad.get('npth_copper'):used.update(pad.get('layers',[]))
    return {name for name in used if name.endswith('.Cu')}


def _net(node, names=None) -> str:
    n = find(node, "net")
    if not n or len(n) < 2:
        return ""
    v = n[-1]
    if isinstance(v,sexpr.Sym) and str(v)=='0':return (names or {}).get('0','')
    if isinstance(v, sexpr.Sym) and names and str(v) in names:
        return names[str(v)]
    return str(v) if isinstance(v, str) else ""


def _drawing(node: list, out: dict, fx=0.0, fy=0.0, rotation=0.0, ref="") -> None:
    """Footprint graphic coordinates are local; text angles are already board angles."""
    layer = find(node, "layer")
    if not layer:
        return
    kind = tag(node)
    if kind in ('gr_text_box','fp_text_box'):
        out['drawings'].append({'id':_identity(node,f'graphic:{ref}'),'ref':ref,'layer':str(layer[1]),'kind':'unsupported','native_kind':kind})
        return
    text = kind in ("property", "fp_text", "gr_text")
    stroke, fill = find(node, "stroke"), find(node, "fill")
    width = find(stroke, "width") if stroke else find(node, "width")
    item = {"id": _identity(node, f"graphic:{ref}"), "ref": ref, "layer": str(layer[1]), "kind": "text" if text else kind[3:],
            "width": num(width[1]) if width else .12, "fill": bool(fill and str(fill[1]) in ("yes", "solid"))}

    def point(p):
        dx, dy = _rot(num(p[0]), num(p[1]), rotation)
        return [round(fx + dx, 4), round(fy + dy, 4)]

    if text:
        hidden = find(node, "hide")
        if (hidden and len(hidden) > 1 and str(hidden[1]) == "yes") or any(v == "hide" for v in node if isinstance(v, str)):
            return
        at, effects = find(node, "at"), find(node, "effects")
        if not at:
            return
        font = find(effects, "font") if effects else None
        size = find(font, "size") if font else None
        justify = find(effects, "justify") if effects else None
        field = str(node[1]).lower() if kind in ("property", "fp_text") else "user"
        item.update(text=str(node[2] if kind in ("property", "fp_text") else node[1]), role=field,
                    at=point(at[1:3]), angle=num(at[3]) if len(at) > 3 else 0,
                    size=[num(size[1]), num(size[2])] if size else [1, 1],
                    mirror=bool(justify and "mirror" in justify),
                    align="left" if justify and "left" in justify else "right" if justify and "right" in justify else "center")
    else:
        for key in ("start", "mid", "end", "center"):
            p = find(node, key)
            if p:
                item[key] = point(p[1:3])
        pts = find(node, "pts")
        if pts:
            item["points"] = [point(p[1:3]) for p in pts[1:] if tag(p) == "xy"]
        if item["kind"] == "rect":
            start, end = find(node, "start"), find(node, "end")
            if not start or not end:
                return
            x0, y0, x1, y1 = num(start[1]), num(start[2]), num(end[1]), num(end[2])
            item.update(kind="poly", points=[point(p) for p in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))])
    out["drawings"].append(item)


def _footprint(node: list, out: dict, net_names=None) -> None:
    at = find(node, "at")
    fx, fy = num(at[1]), num(at[2])
    frot = num(at[3]) if len(at) > 3 else 0.0
    ref = ""
    for p in find_all(node, "property"):
        if p[1] == "Reference":
            ref = str(p[2])
    xs, ys = [], []
    for g in node:
        if tag(g) in ("fp_line", "fp_rect", "fp_poly", "fp_circle", "fp_arc"):
            ly = find(g, "layer")
            if ly and str(ly[1]) in ("F.CrtYd", "B.CrtYd"):
                for pt in sexpr.walk(g):
                    if tag(pt) in ("start", "end", "xy", "mid"):
                        dx, dy = _rot(num(pt[1]), num(pt[2]), frot)
                        xs.append(fx + dx); ys.append(fy + dy)
    side = str(find(node, "layer")[1])
    fpid = {"id": _identity(node, f"footprint:{ref}", "component"), "ref": ref, "lib": str(node[1]), "x": fx, "y": fy, "rot": frot, "side": side}
    models = []
    for m in find_all(node, "model"):
        def xyz(name, d):
            n = find(m, name)
            v = find(n, "xyz") if n else None
            return [num(v[1]), num(v[2]), num(v[3])] if v else d
        hide = find(m, "hide")
        models.append({"path": str(m[1]), "offset": xyz("offset", [0, 0, 0]), "scale": xyz("scale", [1, 1, 1]),
                       "rotate": xyz("rotate", [0, 0, 0]),
                       "hide": "hide" in [str(x) for x in m] or bool(hide and str(hide[1]) == "yes")})
    if models:
        fpid["models"] = models
    if xs:
        fpid["court"] = [round(min(xs), 3), round(min(ys), 3), round(max(xs), 3), round(max(ys), 3)]
    out["footprints"].append(fpid)
    for graphic in node:
        if tag(graphic) in ("fp_line", "fp_rect", "fp_poly", "fp_circle", "fp_arc", "fp_curve", "fp_text", "fp_text_box", "property"):
            _drawing(graphic, out, fx, fy, frot, ref)
    for p in find_all(node, "pad"):
        pat = find(p, "at")
        px, py = num(pat[1]), num(pat[2])
        pang = num(pat[3]) if len(pat) > 3 else 0.0
        dx, dy = _rot(px, py, frot)
        size = find(p, "size")
        lay = find(p, "layers")
        lays = [str(x) for x in lay[1:]] if lay else []
        drill = find(p, "drill")
        oval=bool(drill and len(drill)>1 and str(drill[1])=='oval')
        values=[num(v) for v in (drill[2:] if oval else drill[1:] if drill else []) if not isinstance(v,list)]
        size_drill=([values[0],values[1] if oval and len(values)>1 else values[0]] if values else [0,0])
        offset=find(drill,'offset') if drill else None
        shape_offset=[num(offset[1]),num(offset[2])] if offset else [0,0]
        custom=None;custom_error=None
        if str(p[3])=='custom':
            from .. import pad_shapes
            try:custom=pad_shapes.native_geometry(p)
            except ValueError as error:custom_error=str(error)
        center=custom['source_center_mm'] if custom else [0,0];relative=[shape_offset[i]+center[i] for i in range(2)];shift=_rot(*relative,pang);anchor_shift=_rot(*shape_offset,pang)
        surface=None
        if str(p[2])=='np_thru_hole':
            from .. import pad_shapes
            surface=pad_shapes.unplated_surface(p,custom)
        die_delay=find(p,'die_delay')
        rr = find(p, "roundrect_rratio")
        out["pads"].append({
            "id": _identity(p, f"pad:{ref}"), "ref": ref, "name": str(p[1]), "x": round(fx + dx + shift[0], 4), "y": round(fy + dy + shift[1], 4),
            "w": custom['width_mm'] if custom else num(size[1]) if size else 0, "h": custom['height_mm'] if custom else num(size[2]) if size else 0,
            "rot": pang, "shape": str(p[3]), "kind": str(p[2]),
            "drill": min(size_drill),"drill_shape":"oval" if oval else "circle","drill_size":size_drill,
            "drill_offset":[-v for v in relative] if drill else [0,0],
            **({('profile_polygons' if surface is not None and not surface['has_copper'] else 'copper_polygons'):custom['polygons'],('profile_contours' if surface is not None and not surface['has_copper'] else 'copper_contours'):custom['contours'],'routing_anchor':[round(fx+dx+anchor_shift[0],6),round(fy+dy+anchor_shift[1],6)],'custom_geometry_tolerance_mm':custom['approximation_tolerance_mm']} if custom else {}),
            **({'custom_geometry_unavailable':custom_error} if custom_error else {}),
            **({'npth_copper':surface['has_copper'],'npth_copper_note':('Native unplated surface copper is retained. Automatic electrical continuity across its surfaces is not assumed.' if surface['has_copper'] else 'Mechanical unplated hole with no copper.')} if surface else {}),
            **({'padstack_continuity_unknown':True,'padstack_note':'Native per-layer pad stack retained. Annular copper and plated barrel contacts require native review; automatic routing continuity is not established.'} if find(p,'padstack') else {}),
            **({'pin_delay_ps':num(die_delay[1])} if die_delay else {}),
            "front": any(l in ("F.Cu", "*.Cu") for l in lays) and (surface is None or surface['has_copper']),
            "back": any(l in ("B.Cu", "*.Cu") for l in lays) and (surface is None or surface['has_copper']),
            "net": _net(p, net_names), "layers": lays,
            **({"rratio": num(rr[1])} if rr and str(p[3]) == "roundrect" else {}),
        })


def ratsnest(geo: dict) -> list[list[list[float]]]:
    """Connect actual same-net copper islands for the interactive overlay."""
    from .connectivity import airwires
    return airwires(geo)
