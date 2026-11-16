"""Native KiCad previews for editor drafts; no router, supplier or model calls."""
from __future__ import annotations

import hashlib
import json
import threading
import time
import tempfile
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

from fastapi import HTTPException

from . import config, design, enclosure, ngspice, pipeline, router, sim, sexpr
from . import design_identity,project_library
from .kicad import board, cli, geometry, libs, schematic, schematic_wires

_locks: dict[str, threading.RLock] = {}
NATIVE_SCHEMA = 20
PHYSICAL_STACKUP_POLICY = 'declared-physical-stackup-v1'
PROJECT_HOLE_POLICY = 'declared-project-holes-v2'
PAD_INSTANCE_POLICY = 'native-pad-instances-v1'


def geometry_file(native) -> Path:
    return Path(native['geometry_file']) if native.get('geometry_file') else Path(native['pcb']).parent/'geometry.json'


def _refresh_geometry(p,native):
    """Upgrade parsed data without modifying an existing PCB/SCH or its old JSON."""
    pcb=Path(native['pcb']);source_hash=hashlib.sha256(pcb.read_bytes()).hexdigest()
    with p.lock:
        if not design_identity.matches(native,p.state.get('spec')):raise HTTPException(409,'The design changed before its cached native geometry was returned.')
        if native.get('geometry_schema')==geometry.SCHEMA and native.get('geometry_pcb_sha256')==source_hash and geometry_file(native).is_file():return native
    data=geometry.read(pcb)
    if hashlib.sha256(pcb.read_bytes()).hexdigest()!=source_hash:raise HTTPException(409,'The native PCB changed while its geometry was read.')
    target=pcb.parent/f'geometry-v{geometry.SCHEMA}-{source_hash[:12]}.json'
    from .workbench import _atomic_text
    _atomic_text(target,json.dumps(data))
    refreshed={**native,'geometry_schema':geometry.SCHEMA,'geometry_file':str(target),'geometry_pcb_sha256':source_hash,'geometry_url':p.file_url(target)}
    relative=target.resolve().relative_to(p.root.resolve()).as_posix();refreshed['files']=[f for f in native.get('files',[]) if f['path']!=relative]+[{'name':target.name,'path':relative,'url':p.file_url(target)}]
    with p.lock:
        if not design_identity.matches(native,p.state.get('spec')):raise HTTPException(409,'The design changed while its geometry was refreshed.')
        p.state['workbench_native']=refreshed;p.save()
    return refreshed


def generate(p) -> dict:
    if not libs.locate("footprints") or not libs.locate("symbols"):
        raise HTTPException(503, "Install the KiCad footprint and symbol libraries in Settings → Engineering tools.")
    with _locks.setdefault(p.id, threading.RLock()):
        if p.worker and p.worker.is_alive() and p.worker is not threading.current_thread():
            raise HTTPException(409, "The project is busy. Wait for the active design run to finish.")
        with p.lock:
            source = json.loads(json.dumps(p.state.get("spec")))
        fingerprint = design_identity.legacy_fingerprint(source)
        semantic = design_identity.fields(source)
        previous = p.state.get("workbench_native") or {}
        physical_needed=bool(source['board'].get('stackup')) or source['board'].get('layers')==1
        pad_instances=any(c.get('pad_overrides') for c in source.get('components',[]))
        declared_holes=any(any(p.get('kind','smd')!='smd' for p in (project_library.asset(source,'footprints',c.get('footprint','')) or {}).get('pads',[])) for c in source.get('components',[]))
        if design_identity.matches(previous,source) and previous.get("schema") == NATIVE_SCHEMA and (not physical_needed or previous.get('physical_stackup_policy')==PHYSICAL_STACKUP_POLICY) and (not declared_holes or previous.get('project_hole_policy')==PROJECT_HOLE_POLICY) and (not pad_instances or previous.get('pad_instance_policy')==PAD_INSTANCE_POLICY) and (previous.get('schematic_routing') or {}).get('policy')==schematic_wires.POLICY and Path(previous.get("pcb", "")).is_file() and Path(previous['pcb']).resolve().is_relative_to(p.root.resolve()):
            if any(previous.get(key)!=value for key,value in semantic.items()):
                with p.lock:
                    if not design_identity.matches(previous,p.state.get('spec')):raise HTTPException(409,'The design changed before its cached native identity was upgraded.')
                    previous={**previous,**semantic};p.state['workbench_native']=previous;p.save()
            return _refresh_geometry(p,previous)
        spec = design.normalise(source)
        folder = p.root / "native" / f"{fingerprint[:12]}-v{NATIVE_SCHEMA}"
        folder.parent.mkdir(parents=True, exist_ok=True)
        # Returning through undo/history must not overwrite an earlier native snapshot.
        # The current matching snapshot is reused above; a new generation gets its own folder.
        if folder.exists() and (not folder.is_dir() or any(folder.iterdir())):
            folder = Path(tempfile.mkdtemp(prefix=folder.name + "-", dir=folder.parent))
        else:
            folder.mkdir(parents=True, exist_ok=True)
        try:
            rep = design.validate(spec)
            result = board.build(spec, folder)
            zone_refill=None
            from . import stackup
            if (spec.get('fixed_zones') or (spec['board'].get('stackup') and stackup.plane_map(spec['board']))) and cli.find_kicad_cli():
                zone_refill=cli.drc(Path(result['pcb']),refill=True,save=True)
                stackup.write_report(spec,Path(result['pcb']))
            sch = schematic.build(spec, folder)
            geo = geometry.read(Path(result["pcb"]))
            parity = None
            if (spec.get("editor",{}).get("connection_guides") or spec.get('editor',{}).get('mirrors') or len(sch['pages'])>1 or any(c.get('terminal') or c.get('pin_properties') or c.get('symbol_layout') for c in spec['components'])) and cli.find_kicad_cli():
                parity = schematic.netlist_parity(spec,cli.schematic_nets(Path(sch["sch"])))
                if not parity["ok"]:
                    raise ValueError("The native schematic wiring does not match the saved pin connections. Separate the symbols or reset the wire route.")
        except (ValueError, KeyError, TypeError, cli.KiCadError) as e:
            raise HTTPException(422, str(e)) from None
        geometry_file = folder / "geometry.json"
        geometry_file.write_text(json.dumps(geo))
        pages = []
        if cli.find_kicad_cli():
            svg_dir = folder / "schematic-svg"
            try:
                cli.run(["sch", "export", "svg", "--exclude-drawing-sheet", "-o", str(svg_dir), sch["sch"]], cwd=folder)
                for f in sorted(svg_dir.glob("*.svg")):
                    pages.append({"title": f.stem, "url": p.file_url(f)})
            except (OSError, cli.KiCadError):
                pass
        files = [{"name": f.name, "path": f.relative_to(p.root).as_posix(), "url": p.file_url(f)}
                 for f in sorted(folder.rglob("*")) if f.is_file()]
        explicit=[{'sheet':page['name'],**route} for page in sch['pages'] for route in (page.get('wiring') or {}).get('routes',[])]
        reports={}
        for route in explicit:reports.setdefault(route['id'],[]).append(route)
        expected={guide.get('id',f'wire-{index}'):guide for index,guide in enumerate(spec.get('editor',{}).get('connection_guides',[]))}
        failed=[];routed=0;unavailable=0
        for identifier,guide in expected.items():
            results=reports.get(identifier,[])
            if any(route['status']=='routed' for route in results):routed+=1;continue
            if results:
                r=results[0];failed.append({'sheet':r['sheet'],'id':identifier,'from':r['from'],'to':r['to'],'net':r['net'],'reason':r.get('reason','No routed path')})
            else:
                unavailable+=1;failed.append({'sheet':None,'id':identifier,'from':guide['from'],'to':guide['to'],'reason':'Both wire anchors are not available on one schematic sheet; verify their IDs and sheet assignments.'})
        routing={'policy':schematic_wires.POLICY,'routes':len(expected),'routed':routed,'unroutable':len(failed),'unavailable':unavailable,'failures':failed[:100],'failures_truncated':len(failed)>100}
        native = {"fingerprint": fingerprint, **semantic, "schema": NATIVE_SCHEMA, **({'pad_instance_policy':PAD_INSTANCE_POLICY} if pad_instances else {}), **({'physical_stackup_policy':PHYSICAL_STACKUP_POLICY} if physical_needed else {}), **({'project_hole_policy':PROJECT_HOLE_POLICY} if declared_holes else {}), "pcb": result["pcb"], "sch": sch["sch"],
                  "geometry_schema":geometry.SCHEMA,"geometry_file":str(geometry_file),"geometry_pcb_sha256":hashlib.sha256(Path(result['pcb']).read_bytes()).hexdigest(),
                  "geometry_url": p.file_url(geometry_file), "pages": pages, "files": files,
                  "validation": rep.as_dict(), "manufacturing_ready": False,
                  "schematic_parity":parity,
                  "schematic_routing":routing,
                  "zone_refill":zone_refill,
                  "origin": geo.get("bbox", [100, 100])[:2]}
        with p.lock:
            if not design_identity.matches(native,p.state.get('spec')):
                raise HTTPException(409, "The design changed while native files were generated. Try again.")
            p.state["workbench_native"] = native
            p.save()
        return native


def final_pcb(p) -> Path | None:
    """The current native artifact shared by Layout, DRC, and native 3D."""
    path = Path((p.state.get("artifacts") or {}).get("pcb") or "")
    return path if path.is_file() and path.resolve().is_relative_to(p.root.resolve()) and not (p.state.get("workbench") or {}).get("checks_stale", True) else None


def _plot_inputs(pcb: Path):
    files={suffix:(pcb if suffix=='.kicad_pcb' else pcb.with_suffix(suffix)) for suffix in ('.kicad_pcb','.kicad_pro','.kicad_dru')}
    raw={suffix:path.read_bytes() if path.is_file() else None for suffix,path in files.items()}
    identity=hashlib.sha256(json.dumps({k:hashlib.sha256(v).hexdigest() if v is not None else None for k,v in raw.items()},sort_keys=True).encode()).hexdigest()
    return raw,identity


_VIEW_COLLECTIONS={'footprints','pads','vias','tracks','arcs','drawings','outline','zone_definitions'}


def _view_filter(value):
    if value is None:return {}
    if not isinstance(value,dict) or set(value)-_VIEW_COLLECTIONS:raise HTTPException(422,'Hidden objects must be native geometry collections.')
    count=0;result={}
    for kind,ids in value.items():
        if not isinstance(ids,list) or any(not isinstance(i,str) or not i or len(i)>128 for i in ids):raise HTTPException(422,'Hidden native IDs must be bounded strings.')
        count+=len(ids)
        if count>20000:raise HTTPException(422,'At most20000 hidden native objects can be viewed at once.')
        if ids:result[kind]=sorted(set(ids))
    return dict(sorted(result.items()))


def _filtered_plot(raw: bytes, hidden: dict) -> bytes:
    if not hidden:return raw
    tree=sexpr.parse(raw.decode('utf-8'));off={k:set(v) for k,v in hidden.items()}
    def omitted(kind,node,scope='board',fallback=None):return geometry._identity(node,scope,fallback) in off.get(kind,set())
    out=[]
    for node in tree[1:]:
        tag=sexpr.tag(node)
        if tag=='footprint':
            ref=next((str(v[2]) for v in sexpr.find_all(node,'property') if v[1]=='Reference'),'')
            if omitted('footprints',node,f'footprint:{ref}','component'):continue
            children=[]
            for child in node[2:]:
                kind=sexpr.tag(child)
                if kind=='pad' and omitted('pads',child,f'pad:{ref}'):continue
                if kind in {'fp_line','fp_rect','fp_poly','fp_circle','fp_arc','fp_curve','fp_text','property'} and omitted('drawings',child,f'graphic:{ref}'):
                    if kind=='property':
                        # Keep values used by rule expressions; move only this view's printed field.
                        layer=sexpr.find(child,'layer')
                        if layer:layer[1]='F.SilkS'
                        children.append(child)
                    continue
                children.append(child)
            node=node[:2]+children
        else:
            layer=sexpr.find(node,'layer') if isinstance(node,list) else None
            collection={'via':'vias','segment':'tracks','arc':'arcs','zone':'zone_definitions'}.get(tag)
            if tag in {'gr_line','gr_rect','gr_arc','gr_circle','gr_poly','gr_curve','gr_text'}:collection='outline' if layer and layer[1]=='Edge.Cuts' else 'drawings'
            if collection and omitted(collection,node,'graphic:' if collection=='drawings' else 'board'):continue
        out.append(node)
    tree[1:]=out;return sexpr.dumps(tree).encode('utf-8')


def layout_geometry(p) -> dict:
    """Bind display geometry to the exact saved source and native PCB being shown."""
    with _locks.setdefault(p.id,threading.RLock()):
        with p.lock:
            final=final_pcb(p)
        native=None if final else generate(p)
        with p.lock:
            source=json.loads(json.dumps(p.state['spec']));version=p.state.get('workbench',{}).get('version',0)
            selected=final_pcb(p);pcb=selected or (Path(native['pcb']) if native else None)
            if pcb is None:raise HTTPException(409,'The displayed PCB changed before its geometry was read.')
            digest=hashlib.sha256(pcb.read_bytes()).hexdigest()
            _,inputs=_plot_inputs(pcb)
            if not selected and (not design_identity.matches(native,source) or native.get('geometry_pcb_sha256')!=digest):
                raise HTTPException(409,'Native geometry no longer matches this saved design and PCB. Refresh the layout.')
        data=geometry.read(pcb) if selected else json.loads(geometry_file(native).read_text())
        from . import routing_pairs
        profiles=routing_pairs.hints(source)
        with p.lock:
            current=final_pcb(p) or Path((p.state.get('workbench_native') or {}).get('pcb',''))
            if p.state.get('workbench',{}).get('version',0)!=version or design_identity.fields(source)!=design_identity.fields(p.state['spec']) or current!=pcb or hashlib.sha256(pcb.read_bytes()).hexdigest()!=digest or _plot_inputs(pcb)[1]!=inputs:
                raise HTTPException(409,'The displayed PCB changed while its geometry was read. Refresh the layout.')
        return {'source':'routed' if selected else 'draft','geometry':data,'routing_profiles':profiles,'source_version':version,'pcb_sha256':digest,'render_inputs_sha256':inputs,**design_identity.fields(source),**({'native':native} if native else {})}


def layer_preview(p, layer, hidden=None) -> dict:
    """Plot true native mask/paste shapes in absolute PCB millimeters; never rewrite CAD."""
    if not isinstance(layer,str) or layer not in {'F.Mask','B.Mask','F.Paste','B.Paste'}:
        raise HTTPException(422,'Choose F.Mask, B.Mask, F.Paste or B.Paste.')
    hidden=_view_filter(hidden);visibility=hashlib.sha256(json.dumps(hidden,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
    with _locks.setdefault(p.id,threading.RLock()):
        native=generate(p)
        with p.lock:
            version=p.state.get('workbench',{}).get('version',0)
            final=final_pcb(p);pcb=final or Path(native['pcb'])
            frozen,inputs=_plot_inputs(pcb);digest=hashlib.sha256(frozen['.kicad_pcb']).hexdigest()
        if hidden:
            geo=geometry.read(pcb)
            for kind,ids in hidden.items():
                if not set(ids)<={item['id'] for item in geo.get(kind,[])}:raise HTTPException(422,'A hidden native object is not in the displayed PCB. Refresh the object tree.')
        def current():
            with p.lock:
                chosen=final_pcb(p) or Path((p.state.get('workbench_native') or {}).get('pcb',''))
                if p.state.get('workbench',{}).get('version',0)!=version or not design_identity.matches(native,p.state.get('spec')) or chosen!=pcb or _plot_inputs(pcb)[1]!=inputs:
                    raise HTTPException(409,'The displayed PCB changed while its native layer was plotted. Refresh the layer view.')
        cache=pcb.parent/'display-layers'/f'{inputs}-{visibility}-v1'
        if not cache.resolve().is_relative_to(p.root.resolve()):raise HTTPException(422,'Native layer cache must remain inside this project.')
        cache.mkdir(parents=True,exist_ok=True)
        prefix=layer.replace('.','-')+'-'
        candidates=sorted((f for f in cache.glob(prefix+'*') if f.is_dir() and not f.is_symlink()),key=lambda f:f.stat().st_mtime_ns,reverse=True)[:32]
        def record(folder):
            svg=folder/'layer.svg';meta=folder/'metadata.json'
            if svg.is_symlink() or meta.is_symlink():return None
            try:
                data=json.loads(meta.read_text());raw=svg.read_bytes()
                if len(raw)>16_000_000 or data.get('schema')!=1 or data.get('visibility_sha256')!=visibility or data.get('render_inputs_sha256')!=inputs or data.get('plot_policy')!='absolute-no-drill-v1' or data.get('coordinate_space')!='pcb-mm' or data.get('layer')!=layer or data.get('pcb_sha256')!=digest or data.get('svg_sha256')!=hashlib.sha256(raw).hexdigest():return None
                root=ET.fromstring(raw)
                if root.tag!='{http://www.w3.org/2000/svg}svg':return None
            except (OSError,ValueError,ET.ParseError):return None
            return {**data,'url':p.file_url(svg).split('?',1)[0]+'?v='+data['svg_sha256'][:16],'source_version':version,'pcb_source':'routed' if final else 'draft',**design_identity.fields(p.state['spec'])}
        for candidate in candidates:
            found=record(candidate)
            if found:current();return found
        folder=Path(tempfile.mkdtemp(prefix=prefix,dir=cache));svg=folder/'layer.svg'
        try:
            # Mode1 retains absolute PCB coordinates. Mode2 rebases each plot and cannot be overlaid.
            with tempfile.TemporaryDirectory(prefix='openfabro-layer-') as temporary:
                stage=Path(temporary);staged=stage/pcb.name
                for suffix,content in frozen.items():
                    if content is not None:staged.with_suffix(suffix).write_bytes(_filtered_plot(content,hidden) if suffix=='.kicad_pcb' else content)
                result=cli.run(['pcb','export','svg','--mode-single','--page-size-mode','1','--exclude-drawing-sheet','--drill-shape-opt','0','-l',layer,'-o',str(svg),str(staged)],cwd=stage,timeout=60)
            if result.returncode or not svg.is_file():raise ValueError(result.stderr.strip() or 'KiCad did not produce the requested layer.')
            raw=svg.read_bytes()
            if len(raw)>16_000_000:raise ValueError('This layer is too large for the interactive native preview.')
            tree=ET.fromstring(raw)
            if tree.tag!='{http://www.w3.org/2000/svg}svg':raise ValueError('KiCad returned an invalid SVG layer.')
            current()
            data={'schema':1,'plot_policy':'absolute-no-drill-v1','layer':layer,'coordinate_space':'pcb-mm','pcb_sha256':digest,'render_inputs_sha256':inputs,'visibility_sha256':visibility,'svg_sha256':hashlib.sha256(raw).hexdigest()}
            (folder/'metadata.json').write_text(json.dumps(data,sort_keys=True))
            found=record(folder)
            if not found:raise ValueError('The native layer cache could not be verified.')
            current();return found
        except subprocess.TimeoutExpired:
            raise HTTPException(504,'Native layer plotting timed out. Try a smaller design.') from None
        except (cli.KiCadError,OSError,ValueError,ET.ParseError) as error:
            raise HTTPException(422,'Native layer preview failed: '+str(error)[:400]) from None


def check(p) -> dict:
    with _locks.setdefault(p.id, threading.RLock()):
        return _check_locked(p)


def _check_locked(p) -> dict:
    native = generate(p)
    if not cli.find_kicad_cli():
        raise HTTPException(503, "KiCad CLI is not installed.")
    with p.lock:
        if not design_identity.matches(native,p.state.get('spec')):raise HTTPException(409,'The design changed before the native checks started.')
        source_spec=json.loads(json.dumps(p.state['spec']))
        source_version=(p.state.get('workbench') or {}).get('version',0)
        final = final_pcb(p)
        pcb = final or Path(native["pcb"])
    source_hash = hashlib.sha256(pcb.read_bytes()).hexdigest()
    erc = cli.erc(Path(native["sch"]))
    reports = Path(native["pcb"]).parent / "checks" / source_hash[:12]
    reports.mkdir(parents=True, exist_ok=True)
    drc_path = reports / "drc.json"
    drc = cli.drc(pcb, refill=False, save=False, report_path=drc_path)
    report = {"erc": erc, "drc": drc, "fingerprint": native["fingerprint"], **design_identity.fields(source_spec), "source_version":source_version,"manufacturing_ready": False,
              "erc_report_url": p.file_url(Path(native["sch"]).with_suffix(".erc.json")),
              "drc_report_url": p.file_url(drc_path), "pcb_source": "routed" if final else "draft",
              "pcb_sha256": source_hash}
    from . import buses
    if any(c.get('pin_properties') for c in source_spec.get('components',[])):report['buses']=buses.analyze(source_spec,geometry.read(pcb))
    with p.lock:
        if not design_identity.matches(native,p.state.get('spec')) or hashlib.sha256(pcb.read_bytes()).hexdigest() != source_hash:
            raise HTTPException(409, "The design changed during the checks. Run them again on the saved design.")
        report['design_version']=(p.state.get('workbench') or {}).get('version',0)
        p.state["workbench_checks"] = report
        p.save()
    p.emit({"type": "native_checks", "report": report})
    return report


def _adopt_geometry(p, geo: dict, copper=False) -> None:
    from .workbench import _write_spec
    spec = json.loads(json.dumps(p.state["spec"]))
    ox, oy = geo.get("bbox", [100, 100])[:2]
    for f in geo["footprints"]:
        c = next((c for c in spec["components"] if c["ref"] == f["ref"]), None)
        if c:
            c["placement"] = {**c.get("placement", {}), "x_mm": round(f["x"] - ox, 4),
                              "y_mm": round(f["y"] - oy, 4), "rotation": f.get("rot", 0),
                              "side": "bottom" if f["side"] == "B.Cu" else "top"}
    if copper:
        by_net = {}
        for t in geo.get("tracks", []):
            group = by_net.setdefault(t["net"], {"net": t["net"], "tracks": [], "vias": []})
            group["tracks"].append({**t, "a": [t["a"][0]-ox,t["a"][1]-oy], "b": [t["b"][0]-ox,t["b"][1]-oy]})
        for v in geo.get("vias", []):
            group = by_net.setdefault(v["net"], {"net": v["net"], "tracks": [], "vias": []})
            group["vias"].append({**v, "p": [v["p"][0]-ox, v["p"][1]-oy]})
        for arc in geo.get("arcs", []):
            group = by_net.setdefault(arc["net"], {"net": arc["net"], "tracks": [], "vias": []})
            group.setdefault("arcs", []).append({**arc, **{k: [arc[k][0]-ox, arc[k][1]-oy] for k in ("a", "m", "b")}})
        spec["fixed_copper"] = list(by_net.values())
        spec['fixed_zones']=json.loads(json.dumps(geo.get('zone_sources',[])))
    with p.lock:
        p.state["spec"] = spec
        version = (p.state.get("workbench") or {}).get("version", 0) + 1
        p.state["workbench"] = {"version": version, "checks_stale": True, "saved_at": time.time()}
        _write_spec(p)
        p.save()


def perform(p, kind: str, arguments: dict | None = None) -> dict:
    args = arguments or {}
    cfg = config.load()
    if kind == "simulate" and not ngspice.find(cfg):
        raise HTTPException(503, "Install ngspice to simulate this circuit.")
    if kind == "place" and not router.find("tracemaker-place", cfg):
        raise HTTPException(503, "Install TraceMaker to place components.")
    if kind == "route" and not router.find("tracemaker", cfg):
        raise HTTPException(503, "Install TraceMaker to route the PCB.")
    if kind in ("enclosure", "board3d") and not enclosure.find_freecad(cfg):
        raise HTTPException(503, "Install FreeCAD to generate enclosure CAD.")
    with _locks.setdefault(p.id, threading.RLock()):
        native = generate(p)
        p.engine_busy = True
        p.cancel.clear()
        labels = {"simulate": "Simulating with ngspice", "place": "Placing components with TraceMaker", "board3d": "Generating native STEP board geometry",
                  "route": "Routing with TraceMaker", "enclosure": "Building the enclosure with FreeCAD"}
        p.set_status("running", labels[kind])
        try:
            folder = Path(native["pcb"]).parent
            log = lambda message: p.log(kind, str(message))
            if kind == "board3d":
                from . import board_scene
                pcb = final_pcb(p) or Path(native["pcb"])
                result = board_scene.build(p, pcb, folder, log, force=bool(args.get("force")))
                p.state["workbench_board3d"] = result
            elif kind == "simulate":
                out = folder / "simulation"
                result = sim.simulate(design.normalise(p.state["spec"]), out, cfg, engine=ngspice.find(cfg), log=log, cancel=p.cancel)
                output = out / "results.json"
                output.write_text(json.dumps(result))
                p.state["workbench_simulation"] = {"fingerprint": native["fingerprint"],
                    "version": (p.state.get("workbench") or {}).get("version", 0), "url": p.file_url(output),
                    "ran": result.get("ran"), "ok": result.get("ok")}
                p.emit({"type": "simulation", **p.state["workbench_simulation"]})
            elif kind == "place":
                output = folder / "placed.kicad_pcb"
                result = router.place(Path(native["pcb"]), output, mode="full", scratch=False,
                                      seconds=min(120, max(3, float(args.get("seconds", 15)))), log=log, cancel=p.cancel)
                _adopt_geometry(p, geometry.read(output))
            elif kind == "route":
                output = folder / "routed.kicad_pcb"
                result = router.route(Path(native["pcb"]), output, seconds=min(300, max(5, float(args.get("seconds", 60)))), log=log, cancel=p.cancel)
                if output.exists():
                    _adopt_geometry(p, geometry.read(output), copper=True)
            else:
                pcb = final_pcb(p) or Path(native["pcb"])
                pcb_sha = hashlib.sha256(pcb.read_bytes()).hexdigest()
                geo = geometry.read(pcb)
                spec = design.normalise(p.state["spec"])
                enc = config._merge(enclosure.suggest(enclosure.context(geo, spec)), p.state.get("enclosure_spec") or {})
                enc = config._merge(enc, args.get("spec") or {})
                result = pipeline.run_enclosure(p, spec, enc, pcb)
                if hashlib.sha256(pcb.read_bytes()).hexdigest() != pcb_sha:
                    raise ValueError("The native PCB changed while the enclosure was being generated. Rebuild against the current board.")
                visual = p.state.get("visuals", {}).get("enclosure:enclosure")
                if visual:
                    p.state["workbench_enclosure"] = {"version": (p.state.get("workbench") or {}).get("version", 0),
                        "fingerprint": native["fingerprint"], "pcb_sha256": pcb_sha, **visual}
            p.save()
            p.engine_busy = False
            next_status = "running" if p.worker is threading.current_thread() else "idle"
            p.set_status("stopped" if p.cancel.is_set() else next_status, "Stopped" if p.cancel.is_set() else labels[kind] + ": completed; review the findings.")
            return {"completed": True, "ok": bool(result.get("ok", result.get("complete", True))), "result": result, "state": p.state}
        except Exception as e:
            p.engine_busy = False
            p.set_status("error", str(e)[:400])
            raise HTTPException(422, str(e)) from None
        finally:
            p.engine_busy = False
