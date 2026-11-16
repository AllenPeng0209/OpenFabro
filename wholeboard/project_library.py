"""Portable, project-owned symbols, footprints and reusable part records.

Assets are structured geometry in the design JSON. No global KiCad library is
modified, and arbitrary executable/native-model paths are not accepted.
"""
from __future__ import annotations

import copy
import json
import hashlib
import math
from pathlib import Path
import re

from . import sexpr
from .sexpr import S, Sym, find, find_all, num, tag

NAMESPACE = "Project:"
PIN_TYPES = {"input","output","bidirectional","tri_state","passive","free","unspecified","power_in","power_out","open_collector","open_emitter","no_connect"}
PIN_SHAPES = {"line","inverted","clock","inverted_clock","input_low","clock_low","output_low","edge_clock_high","non_logic"}
LAYERS = {"F.SilkS","B.SilkS","F.Fab","B.Fab","F.CrtYd","B.CrtYd","F.Mask","B.Mask","F.Paste","B.Paste","Dwgs.User","Cmts.User","Edge.Cuts","F.Cu","B.Cu"}


def finite(value, maximum=2000):
    return isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value) and abs(value)<=maximum


def text(value, limit=2000):
    return isinstance(value,str) and len(value)<=limit and all(c.isprintable() or c=='\t' for c in value)


def point(value):
    return isinstance(value,list) and len(value)==2 and all(finite(v) for v in value)


def identifier(value):
    return isinstance(value,str) and re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}",value) is not None


def pad_drill(item):
    """Hole size and offset from the copper center, in the pad's unrotated frame."""
    diameter=item.get('drill',0);shape=item.get('drill_shape','circle');size=item.get('drill_size',[diameter,diameter]);offset=item.get('drill_offset',[0,0])
    if shape not in {'circle','oval'} or not finite(diameter,100) or diameter<0 or not point(size) or not point(offset):raise ValueError('Choose a finite circular or oval hole size and a two-coordinate hole offset.')
    if item.get('kind','smd') in {'smd','connect'}:
        if diameter or any(size) or any(offset):raise ValueError('SMD pads cannot have a drilled hole.')
        return shape,size,offset
    if not all(0<v<=100 for v in size) or abs(min(size)-diameter)>1e-6:raise ValueError('Hole width/height must be positive; drill diameter must equal their minimum.')
    if shape=='circle' and abs(size[0]-size[1])>1e-6:raise ValueError('A circular hole needs equal width and height.')
    if item.get('shape')=='custom':
        from . import pad_shapes
        from shapely.geometry import Polygon,LineString
        region=pad_shapes.material(item);outer=Polygon(region.exterior);radius=min(size)/2;ends=[max(0,v/2-radius) for v in size]
        hole=LineString([[offset[i]+sign*ends[i] for i in range(2)] for sign in (-1,1)]).buffer(radius,quad_segs=128)
        if not outer.buffer(1e-6).covers(hole):raise ValueError('The drilled hole must fit inside the custom pad outer outline.')
        return shape,size,offset
    # A drilled capsule must fit within the actual rounded copper outline, not just its box.
    radius=min(size)/2;ends=[max(0,v/2-radius) for v in size];kind=item.get('shape','rect');rounding=min(item['w'],item['h'])*(0.5 if kind in {'oval','circle'} else item.get('rratio',.25) if kind=='roundrect' else 0)
    for sign in (-1,1):
        p=[offset[i]+sign*ends[i] for i in range(2)];q=[abs(p[i])-([item['w'],item['h']][i]/2-rounding) for i in range(2)]
        distance=math.hypot(max(q[0],0),max(q[1],0))+min(max(q),0)-rounding
        if distance+radius>1e-6:raise ValueError('The drilled hole and its offset must fit inside the pad outline.')
    return shape,size,offset


def _rotate_pad(point,angle):
    a=math.radians(angle);c,s=math.cos(a),math.sin(a)
    return [point[0]*c+point[1]*s,-point[0]*s+point[1]*c]


def library(spec):
    value=(spec or {}).get("library",{})
    return {} if value is None else value


def asset(spec, kind, lib_id):
    lib=library(spec)
    collection=lib.get(kind,{}) if isinstance(lib,dict) else {}
    return collection.get(lib_id[len(NAMESPACE):]) if isinstance(collection,dict) and lib_id.startswith(NAMESPACE) else None


def validate_asset(kind, key, value):
    if not identifier(key) or not isinstance(value,dict):
        raise ValueError("Project asset IDs must be 1–64 letters, digits, underscores or dashes, starting with a letter.")
    for field in ("name","description"):
        if not text(value.get(field,"")):
            raise ValueError(f"{key}: {field} must contain bounded printable text.")
    if kind=="parts":
        for field in ("symbol","footprint","value","reference","mpn","lcsc"):
            if not text(value.get(field,""),256):
                raise ValueError(f"{key}: invalid part field {field}.")
        if not re.fullmatch(r"[A-Z][A-Z_]*",value.get("reference") or "U"):
            raise ValueError(f"{key}: choose an uppercase reference prefix without a number.")
        return
    graphics=value.get("graphics",[])
    if not isinstance(graphics,list) or len(graphics)>2000:
        raise ValueError(f"{key}: graphics must be a list with at most 2000 primitives.")
    for g in graphics:
        if not isinstance(g,dict) or g.get("kind") not in {"line","rectangle","polyline","circle","arc","text"}:
            raise ValueError(f"{key}: unsupported graphic primitive.")
        if not finite(g.get("width",.1524),10) or g.get("width",.1524)<=0:
            raise ValueError(f"{key}: graphic stroke width must be positive and finite.")
        required={"line":["start","end"],"rectangle":["start","end"],"circle":["center"],"arc":["start","mid","end"],"text":["position"],"polyline":[]}[g["kind"]]
        if not all(point(g.get(field)) for field in required):
            raise ValueError(f"{key}: graphic coordinates must be finite 2D points.")
        if g["kind"]=="circle" and (not finite(g.get("radius")) or g["radius"]<=0):
            raise ValueError(f"{key}: circle radius must be positive.")
        if g["kind"]=="polyline" and (not isinstance(g.get("points"),list) or not 2<=len(g["points"])<=2000 or not all(point(p) for p in g["points"])):
            raise ValueError(f"{key}: a polyline needs finite points.")
        if g["kind"]=="text" and (not text(g.get("text","")) or not finite(g.get("size",1.27),100) or g.get("size",1.27)<=0 or not finite(g.get("angle",0),3600)):
            raise ValueError(f"{key}: invalid text primitive.")
        if kind=="footprints" and g.get("layer","F.SilkS") not in LAYERS:
            raise ValueError(f"{key}: choose a supported technical drawing layer.")
        if kind=="symbols" and (type(g.get("unit",0)) is not int or not 0<=g.get("unit",0)<=26):
            raise ValueError(f"{key}: graphic units must be integers between 0 and 26.")
        if g.get("fill","none") not in {"none","solid","background"}:
            raise ValueError(f"{key}: unsupported graphic fill.")
    entries=value.get("pins" if kind=="symbols" else "pads",[])
    if not isinstance(entries,list) or len(entries)>2000:
        raise ValueError(f"{key}: pins/pads must be a bounded list.")
    names=set()
    for item in entries:
        if not isinstance(item,dict):
            raise ValueError(f"{key}: each pin/pad must be an object.")
        name=item.get("number" if kind=="symbols" else "name","")
        if not text(name,32) or (not name and item.get("kind")!="np_thru_hole"):
            raise ValueError(f"{key}: a pin/pad needs a printable identifier.")
        if not all(finite(item.get(field,0)) for field in ("x","y","angle")):
            raise ValueError(f"{key}: pin/pad positions and rotation must be finite.")
        if kind=="symbols":
            unit=item.get("unit",1)
            if type(unit) is not int or not 0<=unit<=26 or (unit,name) in names:
                raise ValueError(f"{key}: pin numbers must be unique within each symbol unit.")
            names.add((unit,name))
            if item.get("type","passive") not in PIN_TYPES or item.get("shape","line") not in PIN_SHAPES or not text(item.get("name",""),128) or not finite(item.get("length",2.54),100) or item.get("length",2.54)<0:
                raise ValueError(f"{key}: invalid pin type, shape, name or length.")
        else:
            if item.get("kind","smd") not in {"smd","thru_hole","np_thru_hole","connect"} or item.get("shape","rect") not in {"rect","roundrect","circle","oval","custom"}:
                raise ValueError(f"{key}: unsupported pad kind or shape.")
            if any(not finite(item.get(field),100) or item[field]<=0 for field in ("w","h")):
                raise ValueError(f"{key}: pad sizes must be finite and positive.")
            if item.get("shape")=="circle" and not math.isclose(item['w'],item['h'],abs_tol=.00001):
                raise ValueError(f"{key}: circular pads must have equal width and height.")
            if item.get("layer","F.Cu") not in {"F.Cu","B.Cu","*.Cu"}:
                raise ValueError(f"{key}: invalid pad copper layer.")
            if 'paste' in item and type(item['paste']) is not bool:raise ValueError(f'{key}: solder paste inclusion must be boolean.')
            if 'npth_copper' in item and type(item['npth_copper']) is not bool:raise ValueError(f'{key}: unplated surface copper must be an explicit boolean.')
            if not finite(item.get("rratio",.25),.5) or item.get("rratio",.25)<0:
                raise ValueError(f"{key}: rounded-corner ratio must be between 0 and 0.5.")
            if item.get('shape')=='custom':
                from . import pad_shapes
                pad_shapes.compile_shape(item.get('custom_shape'),item['w'],item['h'])
            pad_drill(item)
    if kind=="footprints":
        if value.get("mount","smd") not in {"smd","through_hole"}:
            raise ValueError(f"{key}: choose SMD or through-hole mounting.")
        court=value.get("courtyard")
        if court is not None and (not isinstance(court,list) or len(court)!=4 or not all(finite(v) for v in court) or court[0]>=court[2] or court[1]>=court[3]):
            raise ValueError(f"{key}: courtyard must be a finite bounding rectangle.")
        if value.get("height_mm") is not None and (not finite(value["height_mm"],1000) or value["height_mm"]<=0):
            raise ValueError(f"{key}: height must be finite and positive.")
    elif not re.fullmatch(r"[A-Z][A-Z_]*",str(value.get("reference","U"))):
        raise ValueError(f"{key}: choose an uppercase reference prefix.")


def validate(spec):
    lib=library(spec)
    if not isinstance(lib,dict):
        raise ValueError("Project library must be an object.")
    modules=lib.get('modules',{})
    if not isinstance(modules,dict) or len(modules)>100:raise ValueError('Module libraries must be bounded objects.')
    if modules:
        from .modules import validate_asset as validate_module
        for key,value in modules.items():validate_module(key,value)
    for kind in ("symbols","footprints","parts"):
        assets=lib.get(kind,{})
        if not isinstance(assets,dict) or len(assets)>1000:
            raise ValueError("Project library collections must be bounded objects.")
        for key,value in assets.items():
            validate_asset(kind,key,value)
    for kind,field,target in (("symbols","footprint","footprints"),("parts","symbol","symbols"),("parts","footprint","footprints")):
        for key,value in lib.get(kind,{}).items():
            identifier_=value.get(field,"")
            if not text(identifier_,256) or (identifier_.startswith(NAMESPACE) and asset(spec,target,identifier_) is None):
                raise ValueError(f"{key}: linked {field} {identifier_} is missing or invalid.")
    connected={pin for net in spec.get("nets",[]) for pin in net.get("pins",[])}
    for component in spec.get("components",[]):
        for field,kind in (("symbol","symbols"),("footprint","footprints")):
            value=component.get(field,"")
            if not isinstance(value,str):
                raise ValueError(f"{component['ref']}: {field} must be a library identifier.")
            if value and not re.fullmatch(r"[^/\\:]+:[^/\\]+",value):
                raise ValueError(f"{component['ref']}: {field} must be a Library:Item identifier without file paths.")
            if value.startswith(NAMESPACE) and asset(spec,kind,value) is None:
                raise ValueError(f"{component['ref']}: project library asset {value} is missing.")
            if value.startswith(NAMESPACE):
                item=asset(spec,kind,value)
                names={entry['number' if kind=='symbols' else 'name'] for entry in item.get('pins' if kind=='symbols' else 'pads',[])}
                required={p.split('.',1)[1] for p in connected if p.startswith(component['ref']+'.')}
                required.update(str(p) for p in component.get('no_connect',[]))
                missing=required-names
                if missing:
                    raise ValueError(f"{component['ref']}: {value} is missing connected pin/pad {', '.join(sorted(missing))}. Disconnect it before editing the library.")


def _graphic(g, *, footprint=False):
    kind=g["kind"];prefix="fp_" if footprint else ""
    stroke=[Sym("stroke"),S(Sym("width"),g.get("width",.1524)),S(Sym("type"),Sym("solid" if footprint else "default"))]
    layer=[Sym("layer"),g.get("layer","F.SilkS")]
    fill=g.get("fill","none")
    fill_node=S(Sym("fill"),Sym("solid" if fill=="solid" else "none")) if footprint else [Sym("fill"),S(Sym("type"),Sym("outline" if fill=="solid" else "background" if fill=="background" else "none"))]
    if kind=="text":
        effects=[Sym("effects"),[Sym("font"),S(Sym("size"),g.get("size",1.27),g.get("size",1.27))]]
        return [[Sym("fp_text"),Sym("user"),g.get("text",""),S(Sym("at"),*g["position"],g.get("angle",0)),layer,effects]] if footprint else [[Sym("text"),g.get("text",""),S(Sym("at"),*g["position"],g.get("angle",0)),effects]]
    if kind=="line" and not footprint:
        kind="polyline";g={**g,"points":[g["start"],g["end"]]}
    if kind=="polyline":
        pts=list(g["points"])
        if footprint and not g.get("closed") and fill!="solid":
            return [[Sym("fp_line"),S(Sym("start"),*a),S(Sym("end"),*b),copy.deepcopy(stroke),copy.deepcopy(layer)] for a,b in zip(pts,pts[1:])]
        if g.get("closed") and pts[-1]!=pts[0]:pts.append(pts[0])
        node=[Sym("fp_poly" if footprint else "polyline"),[Sym("pts"),*[S(Sym("xy"),*p) for p in pts]],stroke,fill_node]
    elif kind=="circle":
        node=[Sym(prefix+kind),S(Sym("center"),*g["center"]),S(Sym("end"),g["center"][0]+g["radius"],g["center"][1]) if footprint else S(Sym("radius"),g["radius"]),stroke,fill_node]
    else:
        fields=("start","mid","end") if kind=="arc" else ("start","end")
        node=[Sym(prefix+("rect" if kind=="rectangle" and footprint else kind)),*[S(Sym(field),*g[field]) for field in fields],stroke]
        if kind!="line":node.append(fill_node)
    if footprint:node.append(layer)
    return [node]


def symbol_node(spec, lib_id):
    value=asset(spec,"symbols",lib_id)
    if value is None:return None
    key=lib_id[len(NAMESPACE):];validate_asset("symbols",key,value)
    node=[Sym("symbol"),lib_id,S(Sym("pin_names"),S(Sym("offset"),.635)),S(Sym("in_bom"),Sym("yes")),S(Sym("on_board"),Sym("yes"))]
    for i,(name,text_) in enumerate((("Reference",value.get("reference","U")),("Value",value.get("name",key)),("Footprint",value.get("footprint","")),("Datasheet",""),("Description",value.get("description","")))):
        prop=[Sym("property"),name,text_,S(Sym("at"),0,5.08+i*1.27,0),[Sym("effects"),[Sym("font"),S(Sym("size"),1.27,1.27)]]]
        if i>1:prop.append(S(Sym("hide"),Sym("yes")))
        node.append(prop)
    units={0:[Sym("symbol"),f"{key}_0_1"]}
    for graphic in value.get("graphics",[]):
        unit=int(graphic.get("unit",0));units.setdefault(unit,[Sym("symbol"),f"{key}_{unit}_1"]).extend(_graphic(graphic))
    for pin in value.get("pins",[]):
        unit=pin.get("unit",1);units.setdefault(unit,[Sym("symbol"),f"{key}_{unit}_1"])
        item=[Sym("pin"),Sym(pin.get("type","passive")),Sym(pin.get("shape","line")),S(Sym("at"),pin.get("x",0),pin.get("y",0),pin.get("angle",0)),S(Sym("length"),pin.get("length",2.54))]
        if pin.get("hidden"):item.append(Sym("hide"))
        for name,text_ in (("name",pin.get("name","")),("number",pin["number"])):
            item.append([Sym(name),text_,[Sym("effects"),[Sym("font"),S(Sym("size"),1.27,1.27)]]])
        units[unit].append(item)
    node.extend(units[unit] for unit in sorted(units))
    return node


def footprint_node(spec, lib_id):
    value=asset(spec,"footprints",lib_id)
    if value is None:return None
    key=lib_id[len(NAMESPACE):];validate_asset("footprints",key,value)
    node=[Sym("footprint"),key,S(Sym("version"),Sym("20241229")),S(Sym("generator"),"wholeboard"),S(Sym("layer"),"F.Cu"),S(Sym("descr"),value.get("description","")),S(Sym("attr"),Sym("smd" if value.get("mount","smd")=="smd" else "through_hole"))]
    pads=value.get("pads",[])
    court=value.get("courtyard") or ([min(p.get("x",0)-p["w"]/2 for p in pads)-.25,min(p.get("y",0)-p["h"]/2 for p in pads)-.25,max(p.get("x",0)+p["w"]/2 for p in pads)+.25,max(p.get("y",0)+p["h"]/2 for p in pads)+.25] if pads else [-1,-1,1,1])
    for name,label,y,hidden in (("Reference","REF**",court[1]-1.27,False),("Value",value.get("name",key),court[3]+1.27,True)):
        prop=[Sym("property"),name,label,S(Sym("at"),0,y,0),S(Sym("layer"),"F.SilkS" if name=="Reference" else "F.Fab"),[Sym("effects"),[Sym("font"),S(Sym("size"),1,1),S(Sym("thickness"),.15)]]]
        if hidden:prop.append(S(Sym("hide"),Sym("yes")))
        node.append(prop)
    graphics=list(value.get("graphics",[]))
    if not any(g.get('layer') in {'F.CrtYd','B.CrtYd'} for g in graphics):
        graphics.append({"kind":"rectangle","start":court[:2],"end":court[2:],"layer":"F.CrtYd","width":.05})
    for graphic in graphics:node.extend(_graphic(graphic,footprint=True))
    custom_sources={str(i):p['custom_shape'] for i,p in enumerate(pads) if p.get('shape')=='custom'}
    if custom_sources:
        node.append([Sym('property'),'WB Custom Pad Shapes',json.dumps(custom_sources,ensure_ascii=False,separators=(',',':')),S(Sym('at'),0,0,0),S(Sym('layer'),'Dwgs.User'),S(Sym('hide'),Sym('yes')),[Sym('effects'),[Sym('font'),S(Sym('size'),1,1),S(Sym('thickness'),.15)]]])
    for pad in pads:
        kind=pad.get("kind","smd");shape=pad.get("shape","rect");layer=pad.get("layer","F.Cu")
        layers=["*.Cu","*.Mask"] if kind in {'thru_hole','np_thru_hole'} or layer=="*.Cu" else [layer,*([layer.replace('Cu','Paste')] if kind=='smd' else []),layer.replace("Cu","Mask")]
        if kind=='np_thru_hole':layers=[layer,'*.Mask'] if pad.get('npth_copper') else ['*.Mask']
        if pad.get('paste') is False:layers=[name for name in layers if not name.endswith('Paste')]
        hole_shape,hole_size,hole_offset=pad_drill(pad);drilled=kind in {'thru_hole','np_thru_hole'};native_offset=[-v for v in hole_offset];size=[pad['w'],pad['h']];anchor=hole_offset;custom=None
        if shape=='custom':
            from . import pad_shapes
            custom=pad_shapes.compile_shape(pad['custom_shape'],pad['w'],pad['h']);interior=custom['anchor'];anchor=hole_offset if drilled else interior;native_offset=[interior[i]-hole_offset[i] for i in range(2)] if drilled else [0,0];size=[custom['anchor_diameter_mm']]*2
        delta=_rotate_pad(anchor,pad.get('angle',0));item=[Sym("pad"),pad.get("name",""),Sym(kind),Sym(shape),S(Sym("at"),pad.get("x",0)+delta[0],pad.get("y",0)+delta[1],pad.get("angle",0)),S(Sym("size"),*size),S(Sym("layers"),*layers)]
        if drilled:
            drill=S(Sym('drill'),*([Sym('oval'),*hole_size] if hole_shape=='oval' else [hole_size[0]]))
            if any(native_offset):drill.append(S(Sym('offset'),*native_offset))
            item.append(drill)
        if shape=="roundrect":item.append(S(Sym("roundrect_rratio"),pad.get("rratio",.25)))
        if custom:
            item.append([Sym('options'),S(Sym('clearance'),Sym('outline')),S(Sym('anchor'),Sym('circle'))]);primitives=[Sym('primitives')]
            for polygon in custom['polygons']:primitives.append([Sym('gr_poly'),[Sym('pts'),*[S(Sym('xy'),x-custom['anchor'][0],y-custom['anchor'][1]) for x,y in polygon]],S(Sym('width'),0),S(Sym('fill'),Sym('yes'))])
            item.append(primitives)
        node.append(item)
    return node


def _read_graphic(node,footprint=False):
    kind=tag(node)
    if footprint:
        if kind=='fp_text' and str(node[1])!='user':return None
        kind={'fp_line':'line','fp_rect':'rectangle','fp_poly':'polyline','fp_arc':'arc','fp_circle':'circle','fp_text':'text'}.get(kind)
    if kind not in {'line','rectangle','polyline','arc','circle','text'}:
        raise ValueError(f'This asset uses an unsupported drawing primitive: {tag(node)}.')
    value={'kind':kind};stroke=find(node,'stroke');width=find(stroke,'width') if stroke else find(node,'width')
    value['width']=num(width[1]) if width and num(width[1])>0 else .1524
    for name in ('start','end','mid','center'):
        p=find(node,name)
        if p:value[name]=[num(p[1]),num(p[2])]
    points=find(node,'pts')
    if points:value['points']=[[num(p[1]),num(p[2])] for p in points[1:] if tag(p)=='xy']
    if kind=='polyline' and footprint:value['closed']=True
    if kind=='circle':
        radius=find(node,'radius')
        value['radius']=num(radius[1]) if radius else math.dist(value['center'],value['end'])
        value.pop('end',None)
    fill=find(node,'fill');fill_type=find(fill,'type') if fill else None
    value['fill']={'outline':'solid','background':'background','solid':'solid'}.get(str(fill_type[1]) if fill_type else str(fill[1]) if fill else 'none','none')
    if footprint:
        layer=find(node,'layer');value['layer']=str(layer[1]) if layer else 'F.SilkS'
        if value['layer'] not in LAYERS:raise ValueError('This footprint draws on unsupported copper or technical layers.')
    if kind=='text':
        at=find(node,'at');value.update(text=str(node[2] if footprint else node[1]),position=[num(at[1]),num(at[2])] if at else [0,0],angle=num(at[3]) if at and len(at)>3 else 0)
        effects=find(node,'effects');font=find(effects,'font') if effects else None;size=find(font,'size') if font else None
        value['size']=num(size[1]) if size else 1.27
    return value


def _read_symbol(node):
    props={str(p[1]):str(p[2]) for p in find_all(node,'property')}
    value={'name':str(node[1]).split(':')[-1],'reference':props.get('Reference','U'),'description':props.get('Description',''),'footprint':props.get('Footprint',''),'pins':[],'graphics':[]}
    for sub in find_all(node,'symbol'):
        match=re.search(r'_(\d+)_(\d+)$',str(sub[1]))
        if not match:continue
        unit,style=map(int,match.groups())
        if style>1:continue
        for item in sub[2:]:
            if tag(item)=='pin':
                at=find(item,'at');length=find(item,'length');name=find(item,'name');number=find(item,'number')
                value['pins'].append({'number':str(number[1]),'name':str(name[1]) if name else '', 'x':num(at[1]),'y':num(at[2]),'angle':num(at[3]) if len(at)>3 else 0,'length':num(length[1]) if length else 2.54,'type':str(item[1]),'shape':str(item[2]),'unit':unit,'hidden':any(str(x)=='hide' for x in item if not isinstance(x,list)) or bool(find(item,'hide') and str(find(item,'hide')[1])=='yes')})
            elif isinstance(item,list):
                graphic=_read_graphic(item)
                if graphic:value['graphics'].append({**graphic,'unit':unit})
    return value


def _read_footprint(node):
    description=find(node,'descr');attr=find(node,'attr') or []
    value={'name':str(node[1]).split(':')[-1],'description':str(description[1]) if description else '', 'mount':'through_hole' if any(str(x)=='through_hole' for x in attr) else 'smd','pads':[],'graphics':[]}
    metadata={}
    for prop in find_all(node,'property'):
        if len(prop)>2 and prop[1]=='WB Custom Pad Shapes' and len(str(prop[2]))<500000:
            try:metadata=json.loads(prop[2])
            except (ValueError,TypeError):pass
    for item in node[2:]:
        if tag(item)=='pad':
            kind,shape=str(item[2]),str(item[3]);at=find(item,'at');size=find(item,'size');drill=find(item,'drill');layers=find(item,'layers') or [];rr=find(item,'roundrect_rratio')
            if shape not in {'rect','roundrect','circle','oval','custom'}:
                raise ValueError('Trapezoidal pads are not yet supported by the project library editor.')
            oval=bool(drill and len(drill)>1 and str(drill[1])=='oval');numbers=[num(v) for v in (drill[2:] if oval else drill[1:] if drill else []) if not isinstance(v,list)];hole_size=[numbers[0],numbers[1] if oval and len(numbers)>1 else numbers[0]] if numbers else [0,0]
            off=find(drill,'offset') if drill else None;native_offset=[num(off[1]),num(off[2])] if off else [0,0];angle=num(at[3]) if at and len(at)>3 else 0;custom=None;dimensions=[num(size[1]),num(size[2])]
            if shape=='custom':
                from . import pad_shapes
                from shapely.geometry import Polygon
                from shapely import union_all
                custom=pad_shapes.native_geometry(item);native_offset=[native_offset[i]+custom['source_center_mm'][i] for i in range(2)];dimensions=[custom['width_mm'],custom['height_mm']];source={'polygons':custom['polygons'],'units':'mm','tolerance_mm':custom['approximation_tolerance_mm']}
                candidate=metadata.get(str(len(value['pads']))) if isinstance(metadata,dict) else None;metadata_mismatch=False
                if isinstance(candidate,dict):
                    try:
                        original=pad_shapes.compile_shape(candidate,*dimensions);a=union_all([Polygon(p) for p in original['polygons']]);b=union_all([Polygon(p) for p in custom['polygons']])
                        if a.symmetric_difference(b).area<=max(1e-5,a.length*2e-6):source=candidate
                        else:metadata_mismatch=True
                    except ValueError:metadata_mismatch=True
            delta=_rotate_pad(native_offset,angle)
            extra={**({'drill_shape':'oval','drill_size':hole_size} if oval else {}),**({'drill_offset':[-v for v in native_offset]} if drill and any(native_offset) else {})}
            if custom and metadata_mismatch:extra['native_shape_note']='Embedded SVG metadata differs from the current native copper. The editable shape uses the actual native polygons.'
            if kind=='np_thru_hole':
                from . import pad_shapes
                if pad_shapes.unplated_surface(item,custom)['has_copper']:extra['npth_copper']=True
            value['pads'].append({'name':str(item[1]),'kind':kind,'shape':shape,'x':round((num(at[1]) if at else 0)+delta[0],6),'y':round((num(at[2]) if at else 0)+delta[1],6),'angle':angle,'w':dimensions[0],'h':dimensions[1],'drill':min(hole_size),'layer':'*.Cu' if any(str(x)=='*.Cu' for x in layers) else 'B.Cu' if any(str(x)=='B.Cu' for x in layers) else 'F.Cu','rratio':num(rr[1]) if rr else .25,**({'custom_shape':source} if custom else {}),**extra,**({'paste':any(str(x).endswith('Paste') for x in layers)} if kind in {'smd','connect'} else {})})
        elif tag(item).startswith('fp_'):
            graphic=_read_graphic(item,True)
            if graphic:value['graphics'].append(graphic)
    return value


def copy_installed(kind,lib_id,spec=None):
    if not re.fullmatch(r'[^/\\:]+:[^/\\]+',lib_id):raise ValueError('Use a Library:Item identifier.')
    if kind=='symbols':
        from .kicad import schematic
        node=schematic.load_symbol(lib_id,spec)
        if node is None:raise ValueError('Symbol not found in the installed libraries.')
        value=_read_symbol(node)
    elif kind=='footprints':
        from .kicad import libs
        footprint=libs.load_footprint(lib_id,spec)
        if footprint is None:raise ValueError('Footprint not found in the installed libraries.')
        value=_read_footprint(footprint.node)
    else:raise ValueError('Choose a symbol or footprint to copy.')
    value['source_lib_id']=lib_id
    return value


def import_native(kind,content):
    if not isinstance(content,str) or len(content)>5_000_000:raise ValueError('Choose a native library smaller than 5 MB.')
    tree=sexpr.parse(content);assets={}
    if kind=='footprints' and tag(tree) in {'footprint','module'}:
        value=_read_footprint(tree);key=re.sub('[^A-Za-z0-9_-]','_',str(tree[1]).split(':')[-1]);assets[key]=value
    elif kind=='symbols' and tag(tree)=='kicad_symbol_lib':
        from .kicad import schematic
        definitions={str(node[1]):node for node in find_all(tree,'symbol')}
        def flattened(name,seen):
            if name in seen:raise ValueError('The symbol library contains cyclic inheritance.')
            if name not in definitions:raise ValueError('Import the parent symbols in the same library file.')
            node=definitions[name];parent=find(node,'extends')
            return schematic._flatten(node,flattened(str(parent[1]),seen|{name}),name,str(parent[1])) if parent else node
        for name in definitions:
            key=re.sub('[^A-Za-z0-9_-]','_',name)
            if key in assets:raise ValueError('Two imported symbols resolve to the same project ID.')
            assets[key]=_read_symbol(flattened(name,set()))
    else:raise ValueError('Choose a .kicad_sym symbol library or a .kicad_mod footprint.')
    if not assets:raise ValueError('The native library contains no editable assets.')
    for key,value in assets.items():validate_asset(kind,key,value)
    return assets


def export(spec, directory: Path):
    lib=library(spec)
    if not lib:return []
    validate(spec);files=[]
    if lib.get("footprints"):
        folder=directory/'library/Project.pretty';folder.mkdir(parents=True,exist_ok=True)
        for key in lib["footprints"]:
            path=folder/f'{key}.kicad_mod';path.write_text(sexpr.dumps(footprint_node(spec,NAMESPACE+key))+"\n");files.append(path)
    if lib.get("symbols"):
        folder=directory/'library';folder.mkdir(parents=True,exist_ok=True)
        symbols=[]
        for key in lib["symbols"]:
            node=symbol_node(spec,NAMESPACE+key);node[1]=key;symbols.append(node)
        path=folder/'Project.kicad_sym';path.write_text(sexpr.dumps([Sym("kicad_symbol_lib"),S(Sym("version"),Sym("20241209")),S(Sym("generator"),"wholeboard"),*symbols])+"\n");files.append(path)
    for kind,uri in (("fp_lib_table","library/Project.pretty"),("sym_lib_table","library/Project.kicad_sym")):
        if not lib.get("footprints" if kind.startswith("fp") else "symbols"):continue
        path=directory/('fp-lib-table' if kind.startswith('fp') else 'sym-lib-table')
        path.write_text(sexpr.dumps([Sym(kind),S(Sym("version"),7),[Sym("lib"),S(Sym("name"),"Project"),S(Sym("type"),"KiCad"),S(Sym("uri"),"${KIPRJMOD}/"+uri),S(Sym("options"),""),S(Sym("descr"),"Project-owned library")]])+"\n");files.append(path)
    if any(p.get('shape')=='custom' for asset in lib.get('footprints',{}).values() for p in asset.get('pads',[])):
        path=directory/'library/Project.library.json';path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps({'schema':1,'library':lib,'native_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in files if p.suffix in {'.kicad_mod','.kicad_sym'}},'limits':['Curve coordinates use each custom source tolerance; native output rounds to micrometers.']},ensure_ascii=False,indent=2));files.append(path)
    return files
