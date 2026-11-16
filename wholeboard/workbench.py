"""Editing APIs for the Flux-style workbench, using OpenFabro's on-disk projects.

Saving a draft never starts an agent, calls a supplier, or builds a board. Native
builds still go through the original OpenFabro pipeline and its checks.
"""
from __future__ import annotations

import csv
import copy
import base64
import binascii
import io
import json
import math
import re
import time
import uuid
import asyncio
import hashlib
import shutil
import tempfile
import zipfile
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response

from . import collaboration, config, design, project_library
from .kicad import cli, libs


def validate_draft(spec: dict) -> None:
    """Validate edit integrity without requiring a local KiCad installation."""
    if not isinstance(spec, dict):
        raise HTTPException(422, "A design must be a JSON object.")
    from . import design_identity
    try:design_identity.normalized(spec)
    except (ValueError, TypeError) as error:raise HTTPException(422,str(error)) from None
    editor = spec.get("editor") or {}
    if not isinstance(editor, dict):
        raise HTTPException(422, "Schematic editor metadata must be an object.")
    guides = editor.get("connection_guides", [])
    if not isinstance(guides, list) or any(not isinstance(g, dict) or not all(isinstance(g.get(k), str) for k in ("from", "to")) for g in guides):
        raise HTTPException(422, "Connection guides must contain from and to pin references.")
    from .kicad.schematic_wires import validate_guides
    try:validate_guides(guides)
    except ValueError as error:raise HTTPException(422,str(error)) from None
    for guide in guides:
        bends=guide.get("waypoints",[])
        if not isinstance(bends,list) or len(bends)>100 or any(not isinstance(p,list) or len(p)!=2 or any(not isinstance(v,(int,float)) or not math.isfinite(v) or abs(v)>1_000_000 for v in p) for p in bends):
            raise HTTPException(422,"Wire bends must contain at most 100 finite 2D points.")
    if any(not isinstance(editor.get(field) or {}, dict) for field in ("positions", "rotations")):
        raise HTTPException(422, "Schematic positions and rotations must be objects.")
    for key, position in (editor.get("positions") or {}).items():
        try:
            valid = isinstance(position, list) and len(position) == 2 and all(math.isfinite(float(v)) for v in position)
        except (ValueError, TypeError):
            valid = False
        if not valid:
            raise HTTPException(422, f"Schematic position {key} needs two finite coordinates.")
    for key, rotation in (editor.get("rotations") or {}).items():
        try:
            valid = math.isfinite(float(rotation)) and float(rotation) % 90 == 0
        except (ValueError, TypeError):
            valid = False
        if not valid:
            raise HTTPException(422, f"Schematic rotation {key} must be a finite multiple of 90 degrees.")
    if not isinstance(editor.get('mirrors',{}),dict) or any(value not in ('','x','y') for value in editor.get('mirrors',{}).values()):
        raise HTTPException(422,'Schematic mirrors must map symbol units to x or y.')
    board = spec.get("board")
    if not isinstance(board, dict):
        raise HTTPException(422, "A design needs board dimensions.")
    for key in ("width_mm", "height_mm"):
        try:
            value = float(board.get(key, 0))
        except (TypeError, ValueError):
            value = 0
        if not math.isfinite(value) or not 0 < value <= 2000:
            raise HTTPException(422, "Board dimensions must be finite and between 0 and 2000 mm.")
    if board.get("layers", 2) not in (1, 2, 4, 6, 8, 10, 12):
        raise HTTPException(422, "Choose a supported copper layer count.")
    components = spec.get("components", [])
    nets = spec.get("nets", [])
    if not isinstance(components, list) or not isinstance(nets, list):
        raise HTTPException(422, "Components and nets must be lists.")
    refs = set()
    for component in components:
        if not isinstance(component, dict):
            raise HTTPException(422, "Each component must be an object.")
        ref = component.get("ref", "")
        if not isinstance(ref, str) or not re.fullmatch(r"[A-Z][A-Z_]*\d+", ref) or ref in refs:
            raise HTTPException(422, f"Invalid or duplicate designator: {ref}.")
        refs.add(ref)
        for key, value in (component.get("placement") or {}).items():
            if key in ("x_mm", "y_mm", "rotation"):
                try:
                    valid = math.isfinite(float(value))
                except (TypeError, ValueError):
                    valid = False
                if not valid:
                    raise HTTPException(422, f"{ref} placement must use finite numbers.")
    names, pins = set(), set()
    for net in nets:
        if not isinstance(net, dict) or not isinstance(net.get("name"), str) or not net["name"].strip():
            raise HTTPException(422, "Every net needs a name.")
        if net["name"] in names:
            raise HTTPException(422, f"Duplicate net: {net['name']}.")
        names.add(net["name"])
        if not isinstance(net.get("pins", []), list):
            raise HTTPException(422, "Net pins must be a list.")
        for pin in net.get("pins", []):
            if not isinstance(pin, str) or "." not in pin or pin.split(".", 1)[0] not in refs:
                raise HTTPException(422, f"Connection refers to a missing component: {pin}.")
            if pin in pins:
                raise HTTPException(422, f"Pin belongs to more than one net: {pin}.")
            pins.add(pin)
    try:
        project_library.validate(spec)
        from . import pad_edits
        pad_edits.validate(spec)
        from . import object_groups
        object_groups.validate(spec)
        from . import parametric_symbols
        parametric_symbols.validate(spec)
        from . import terminals
        terminals.validate(spec)
        from . import sheets
        sheets.validate(spec)
        from . import wire_nodes
        wire_nodes.validate(spec)
        from . import buses
        buses.validate(spec)
        from . import stackup
        stackup.validate(spec)
        from .kicad import copper as copper_data
        copper_data.validate(spec)
    except (ValueError,TypeError,KeyError) as error:
        raise HTTPException(422,str(error)) from None
    count = board.get("layers", 2)
    copper_layers = {"F.Cu", *[f"In{i}.Cu" for i in range(1, max(0, count-2)+1)]}
    if count > 1:
        copper_layers.add("B.Cu")
    copper = spec.get("fixed_copper") or []
    if not isinstance(copper, list):
        raise HTTPException(422, "Manual copper must be a list of net groups.")
    finite = lambda value: isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
    point = lambda value: isinstance(value, list) and len(value) == 2 and all(finite(v) for v in value)
    for group in copper:
        if not isinstance(group, dict) or not isinstance(group.get("net"), str) or group["net"] not in names:
            raise HTTPException(422, "Manual copper must belong to an existing net.")
        for kind, points in (("tracks", ("a", "b")), ("arcs", ("a", "m", "b")), ("vias", ("p",))):
            items = group.get(kind) or []
            if not isinstance(items, list):
                raise HTTPException(422, f"Copper {kind} must be a list.")
            for item in items:
                if not isinstance(item, dict) or not all(point(item.get(key)) for key in points):
                    raise HTTPException(422, "Copper coordinates must contain two finite numbers.")
                if 'locked' in item and type(item['locked']) is not bool:raise HTTPException(422,'Copper protection must be a boolean.')
                if kind == "vias":
                    diameter, drill = item.get("d"), item.get("drill")
                    if count < 2 or not finite(diameter) or not finite(drill) or not 0 < drill < diameter <= 2000:
                        raise HTTPException(422, "A via needs two copper layers and a positive drill smaller than its diameter.")
                    span = item.get("layers", ["F.Cu", "B.Cu"])
                    if not isinstance(span, list) or len(span) != 2 or span[0] == span[1] or any(not isinstance(layer, str) or layer not in copper_layers for layer in span):
                        raise HTTPException(422, "Via layers must be two distinct copper layers in this board.")
                    if item.get("type", "through") not in ("through", "blind", "micro"):
                        raise HTTPException(422, "Choose a through, blind, or micro via.")
                elif not isinstance(item.get("layer"), str) or item["layer"] not in copper_layers or not finite(item.get("w")) or not 0 < item["w"] <= 2000:
                    raise HTTPException(422, "Copper tracks need a positive finite width and a layer in this board.")


def _atomic_text(target: Path, content: str) -> None:
    """Replace a document without reusing someone else's editor temporary file."""
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=target.parent, prefix=".wholeboard-", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(content)
        temporary.replace(target)
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)


def _write_spec(p) -> None:
    target = p.root / "design.json"
    tmp = target.with_suffix(".tmp")
    tmp.write_text(json.dumps(p.state["spec"], ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(target)
    meta = p.state.get("workbench") or {}
    version = meta.get("version", 0)
    history = p.root / "history"
    history.mkdir(exist_ok=True)
    snapshot = history / f"design-v{version}.json"
    if not snapshot.exists():
        from . import design_origin
        origin=design_origin.metadata(p,version)
        snapshot.write_text(json.dumps({"version": version, "saved_at": meta.get("saved_at", time.time()),
            "spec": p.state["spec"],**({'origin':origin} if origin else {})}, ensure_ascii=False, indent=2), encoding="utf-8")
        design_origin.committed(p,origin,snapshot)


def _csv_cell(value) -> str:
    value = str(value or "")
    return "'" + value if value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")) else value


def attach_workbench(app: FastAPI, get_manager) -> None:
    def project(pid):
        p = get_manager().get(pid)
        if not p:
            raise HTTPException(404, "Project not found.")
        return p

    @app.get("/api/workbench/codex/status")
    def codex_status():
        from . import codex_bridge
        return codex_bridge.status()

    @app.post("/api/workbench/projects/{pid}/codex")
    async def codex_message(pid: str, request: Request):
        from . import codex_bridge
        body = await request.json()
        try:
            from . import canvas_references
            p=project(pid)
            def submit(mark_started=lambda:None):
                reference=canvas_references.validate_for_send(p,body.get('canvas_ref'))
                mark_started()
                codex_bridge.start(p,str(body.get('text') or ''),body.get('mode','agent'),**({'canvas_reference':reference} if reference else {}),**({'request_id':body['request_id']} if body.get('request_id') else {}))
                return {'ok':True}
            return canvas_references.submit_once(p,body.get('request_id'),{'endpoint':'codex',**body},submit)
        except ValueError as e:
            raise HTTPException(409, str(e)) from None

    @app.post('/api/workbench/projects/{pid}/canvas-reference',status_code=201)
    async def canvas_reference(pid: str,request: Request):
        from . import canvas_references
        try:return canvas_references.create(project(pid),await request.json())
        except canvas_references.StaleCanvasReference as error:raise HTTPException(409,str(error)) from None
        except ValueError as error:raise HTTPException(422,str(error)) from None

    @app.post("/api/workbench/projects/{pid}/steer")
    async def steer_agent(pid: str, request: Request):
        p = project(pid)
        body=await request.json();text = str(body.get("text") or "").strip()
        if not text or len(text) > 150_000:
            raise HTTPException(422, "Send a non-empty message shorter than 150,000 characters.")
        from . import canvas_references
        def submit(mark_started=lambda:None):
            with p.lock:
                if not p.worker or not p.worker.is_alive() or p.state.get('status') in ('idle','error','stopped','done'):raise HTTPException(409,'The active run has finished. Send this as a new message.')
                reference=canvas_references.validate_for_send(p,body.get('canvas_ref'))
                mode=body.get('mode')
                if mode is not None and mode not in ('agent','chat'):raise ValueError('Choose Agent or Chat mode.')
                if reference and p.state.get('driver')=='claude-code':raise ValueError('The external driver cannot receive canvas images. Use the local Codex or an image-capable provider.')
                mark_started()
                source=body.get('request_id')
                p.inbox.append({'text':text,**({'canvas_reference':reference} if reference else {}),**({'mode':mode} if mode else {}),**({'source_request_id':source} if source else {})} if reference or mode or source else text)
                p.chat('user',text,**({'canvas_reference':reference} if reference else {}))
            return {'queued':True}
        try:return canvas_references.submit_once(p,body.get('request_id'),{'endpoint':'steer',**body},submit)
        except ValueError as error:raise HTTPException(409,str(error)) from None

    @app.post("/api/workbench/projects/{pid}/native")
    async def native_preview(pid: str):
        from . import workbench_native
        return await asyncio.to_thread(workbench_native.generate, project(pid))

    @app.get("/api/workbench/projects/{pid}/layout-geometry")
    async def layout_geometry(pid: str):
        from . import workbench_native
        return await asyncio.to_thread(workbench_native.layout_geometry,project(pid))

    @app.post('/api/workbench/projects/{pid}/layer-preview')
    async def native_layer_preview(pid: str, request: Request):
        from . import workbench_native
        body=await request.json()
        if not isinstance(body,dict):raise HTTPException(422,'A layer preview request must be an object.')
        return await asyncio.to_thread(workbench_native.layer_preview,project(pid),body.get('layer'),body.get('hidden'))

    @app.post("/api/workbench/projects/{pid}/native-checks")
    async def native_checks(pid: str):
        from . import workbench_native
        return await asyncio.to_thread(workbench_native.check, project(pid))

    @app.post("/api/workbench/projects/{pid}/simulate")
    async def simulate_draft(pid: str, request: Request):
        from . import workbench_native
        body = await request.json() if await request.body() else {}
        return await asyncio.to_thread(workbench_native.perform, project(pid), "simulate", body)

    @app.post("/api/workbench/projects/{pid}/engineering/{kind}")
    async def engineering_action(pid: str, kind: str, request: Request):
        from . import workbench_native
        if kind not in ("place", "route", "enclosure", "board3d"):
            raise HTTPException(404, "Unknown engineering action.")
        body = await request.json() if await request.body() else {}
        return await asyncio.to_thread(workbench_native.perform, project(pid), kind, body)

    @app.get('/api/workbench/mechanical-materials')
    def mechanical_material_catalog():
        from . import mechanical_materials
        return mechanical_materials.library()

    @app.get("/api/workbench/projects/{pid}/mechanical")
    def mechanical_parts(pid: str):
        from . import mechanical
        return mechanical.listing(project(pid))

    @app.get('/api/workbench/projects/{pid}/mechanical/assembly-sources')
    def assembly_sources(pid: str):
        from . import assemblies
        return assemblies.inventory(project(pid))

    @app.get('/api/workbench/projects/{pid}/mechanical/topology')
    def native_topology(pid: str,request: Request):
        from . import mechanical
        try:
            arguments=dict(request.query_params)
            for key in ('body_id','offset','limit'):
                if key in arguments:arguments[key]=int(arguments[key])
            return mechanical.inspect_topology(project(pid),arguments)
        except mechanical.MechanicalConflict as error:raise HTTPException(409,str(error)) from None
        except (ValueError,OSError) as error:raise HTTPException(422,str(error)) from None

    @app.post("/api/workbench/projects/{pid}/mechanical/build")
    async def build_mechanical_part(pid: str, request: Request):
        from . import mechanical
        try:
            body = await request.json()
            return await asyncio.to_thread(mechanical.rebuild, project(pid), body)
        except mechanical.MechanicalConflict as error:
            raise HTTPException(409, str(error)) from None
        except (ValueError, RuntimeError, OSError) as error:
            raise HTTPException(422, str(error)) from None

    @app.post('/api/workbench/projects/{pid}/mechanical/sketch-preview')
    async def preview_mechanical_sketch(pid: str,request: Request):
        from . import mechanical
        try:return await asyncio.to_thread(mechanical.preview_sketch,project(pid),await request.json())
        except mechanical.MechanicalConflict as error:raise HTTPException(409,str(error)) from None
        except (ValueError,RuntimeError,OSError) as error:raise HTTPException(422,str(error)) from None

    @app.get('/api/workbench/projects/{pid}/mechanical/assets')
    def imported_mechanical_assets(pid: str):
        from . import mechanical_assets
        return mechanical_assets.listing(project(pid))

    @app.post('/api/workbench/projects/{pid}/mechanical/assets')
    async def import_mechanical_asset(pid: str,request: Request):
        from . import mechanical_assets,mechanical
        try:return await asyncio.to_thread(mechanical_assets.ingest,project(pid),await request.json())
        except mechanical.MechanicalConflict as error:raise HTTPException(409,str(error)) from None
        except (ValueError,RuntimeError,OSError) as error:raise HTTPException(422,str(error)) from None

    @app.post('/api/workbench/projects/{pid}/mechanical/assets/part')
    async def imported_asset_part(pid: str,request: Request):
        from . import mechanical_assets,mechanical
        try:return await asyncio.to_thread(mechanical_assets.create_part,project(pid),await request.json())
        except mechanical.MechanicalConflict as error:raise HTTPException(409,str(error)) from None
        except (ValueError,RuntimeError,OSError) as error:raise HTTPException(422,str(error)) from None

    @app.post('/api/workbench/projects/{pid}/mechanical/assets/extrude')
    async def extrude_drawing_asset(pid: str,request: Request):
        from . import mechanical_assets,mechanical
        try:return await asyncio.to_thread(mechanical_assets.extrude,project(pid),await request.json())
        except mechanical.MechanicalConflict as error:raise HTTPException(409,str(error)) from None
        except (ValueError,RuntimeError,OSError) as error:raise HTTPException(422,str(error)) from None

    @app.get('/api/workbench/projects/{pid}/mechanical/history')
    def mechanical_edit_history(pid: str):
        from . import mechanical_history
        return mechanical_history.summary(project(pid))

    @app.post('/api/workbench/projects/{pid}/mechanical/history/restore')
    async def restore_mechanical_history(pid: str, request: Request):
        from . import mechanical,mechanical_history
        try:return await asyncio.to_thread(mechanical_history.restore,project(pid),await request.json())
        except mechanical.MechanicalConflict as error:raise HTTPException(409,str(error)) from None
        except (ValueError,OSError) as error:raise HTTPException(422,str(error)) from None

    @app.get("/api/workbench/projects/{pid}/pins")
    def project_pins(pid: str):
        from .kicad import schematic
        spec = project(pid).state.get("spec") or {}
        mapping = design.pin_net_map(spec)
        rows = []
        for c in spec.get("components", []):
            footprint = libs.load_footprint(c.get("footprint", ""),spec)
            symbol = schematic.symbol_info(c.get("symbol", ""),spec) if c.get("symbol") else None
            symbols = {p["number"]: p for p in (symbol or {}).get("pins", [])}
            from . import parametric_symbols
            try:symbol_props = {p['number']:p for p in parametric_symbols.settings(c,spec)['pins']} if symbol and symbols and not c.get('terminal') else {}
            except (ValueError,TypeError,KeyError):symbol_props = {}
            names = {p.name for p in footprint.pads} if footprint else {p.split(".", 1)[1] for p in mapping if p.startswith(c["ref"] + ".")}
            for name in sorted(names):
                pin = symbols.get(name, {})
                key = f"{c['ref']}.{name}"
                rows.append({"id": key, "ref": c["ref"], "number": name, "name": pin.get("name", name),
                    "symbol_properties": {k:v for k,v in symbol_props.get(name,{}).items() if k in {'side','group','section','order','subsymbol','name'}},
                    "symbol_available": name in symbols and not c.get('terminal'),
                    "type": pin.get("type", "unspecified"), "net": mapping.get(key, ""),
                    "properties":c.get('pin_properties',{}).get(name,{}),"bus_type":c.get('pin_properties',{}).get(name,{}).get('bus_type') or c.get('bus_type',''),"component_bus_type":c.get('bus_type',''),
                    "no_connect": name in [str(n) for n in c.get("no_connect", [])]})
        return {"pins": rows}

    @app.get("/api/workbench/library")
    async def search_library(q: str = "", kind: str = "footprints"):
        from .jlc import parts
        q = q.strip()[:120]
        if len(q) < 2:
            return {"results": []}
        if kind == "parts":
            try:
                results = await asyncio.to_thread(parts.search, q, 20)
            except Exception as e:
                raise HTTPException(502, f"Supplier search failed: {str(e)[:150]}") from None
        elif kind == "symbols":
            results = await asyncio.to_thread(libs.search_symbols, q, 50)
        else:
            results = await asyncio.to_thread(libs.search_footprints, q, 50)
        return {"kind": kind, "results": results}

    @app.get("/api/workbench/parts/{code}")
    async def lookup_part(code: str):
        from .jlc import parts
        if not re.fullmatch(r"C\d+", code, re.I):
            raise HTTPException(422, "Use an LCSC number such as C25804.")
        try:
            part = await asyncio.to_thread(parts.lookup, code.upper(), True)
        except Exception as e:
            raise HTTPException(502, f"Part lookup failed: {str(e)[:150]}") from None
        if not part:
            raise HTTPException(404, "Part not found at the supplier.")
        return part

    @app.get("/api/workbench/library/footprint-info")
    def footprint_details(id: str):
        if not re.fullmatch(r"[^/\\:]+:[^/\\]+", id):
            raise HTTPException(422, "Use a KiCad Library:Footprint identifier.")
        fp = libs.load_footprint(id)
        if not fp:
            raise HTTPException(404, "Footprint not found in the installed KiCad libraries.")
        return {"id": id, "courtyard": fp.courtyard, "pads": sorted({p.name for p in fp.pads})}

    @app.get("/api/workbench/library/symbol-info")
    def symbol_details(id: str):
        from .kicad import schematic
        if not re.fullmatch(r"[^/\\:]+:[^/\\]+", id):
            raise HTTPException(422, "Use a KiCad Library:Symbol identifier.")
        result = schematic.symbol_info(id)
        if not result:
            raise HTTPException(404, "Symbol not found in the installed KiCad libraries.")
        return result

    @app.get("/api/workbench/projects/{pid}/library/symbol-info")
    def project_symbol_details(pid: str, id: str):
        from .kicad import schematic
        if not re.fullmatch(r"[^/\\:]+:[^/\\]+",id):
            raise HTTPException(422,"Use a Library:Symbol identifier.")
        result=schematic.symbol_info(id,project(pid).state.get("spec"))
        if not result:raise HTTPException(404,"Symbol not found in this project's libraries.")
        return result

    @app.get("/api/workbench/projects/{pid}/library/footprint-info")
    def project_footprint_details(pid: str, id: str):
        if not re.fullmatch(r"[^/\\:]+:[^/\\]+",id):
            raise HTTPException(422,"Use a Library:Footprint identifier.")
        fp=libs.load_footprint(id,project(pid).state.get("spec"))
        if not fp:raise HTTPException(404,"Footprint not found in this project's libraries.")
        return {"id":id,"courtyard":fp.courtyard,"pads":sorted({p.name for p in fp.pads if p.name})}

    @app.get("/api/workbench/projects/{pid}/library/export")
    def export_project_library(pid: str):
        p=project(pid)
        with p.lock:spec=json.loads(json.dumps(p.state.get("spec") or {}))
        output=io.BytesIO()
        with tempfile.TemporaryDirectory(prefix="wholeboard-library-") as folder:
            root=Path(folder)
            files=project_library.export(spec,root)
            with zipfile.ZipFile(output,"w",zipfile.ZIP_DEFLATED) as archive:
                for path in files:archive.write(path,path.relative_to(root).as_posix())
                archive.writestr("library.json",json.dumps(project_library.library(spec),indent=2))
        return Response(output.getvalue(),media_type="application/zip",headers={"Content-Disposition":'attachment; filename="project-library.zip"'})

    def module_snapshot(pid,body):
        p=project(pid)
        with p.lock:
            version=(p.state.get('workbench') or {}).get('version',0)
            if body.get('base_version')!=version:raise HTTPException(409,'The design changed. Save or reload it before editing.')
            if p.worker and p.worker.is_alive():raise HTTPException(409,'Wait for the active run before editing modules.')
            return p,version,json.loads(json.dumps(p.state.get('spec') or {}))

    @app.get('/api/workbench/projects/{pid}/symbols/{ref}')
    def symbol_layout_info(pid: str, ref: str):
        from . import parametric_symbols, schematic_view
        p = project(pid)
        with p.lock:
            spec = copy.deepcopy(p.state.get('spec') or {})
            version = p.state.get('workbench', {}).get('version', 0)
        component = next((c for c in spec.get('components', []) if c['ref'] == ref), None)
        if not component:raise HTTPException(404, 'Component not found.')
        try:
            info = parametric_symbols.settings(component, spec)
            scene = schematic_view.scene(spec)
        except (ValueError, TypeError, KeyError) as error:raise HTTPException(422, str(error)) from None
        symbols = [s for s in scene['symbols'] if s['ref'] == ref]
        return {'ref': ref, 'version': version, 'layout': {k:v for k,v in info.items() if k != 'source'},
                'scene': {**scene, 'symbols': symbols, 'definitions': {s['definition']:scene['definitions'][s['definition']] for s in symbols}}}

    @app.post('/api/workbench/projects/{pid}/symbols/prepare')
    async def prepare_symbol_layout(pid: str, request: Request):
        from . import parametric_symbols
        body = await request.json()
        if not isinstance(body, dict):raise HTTPException(422, 'Symbol layout edits need an object.')
        p, version, _ = module_snapshot(pid, body)
        try:
            result = await asyncio.to_thread(parametric_symbols.project_draft, p, body)
            module_snapshot(pid, body)
        except (ValueError, TypeError, KeyError, cli.KiCadError) as error:raise HTTPException(422, str(error)) from None
        return {**result, 'base_version': version}

    @app.get('/api/workbench/interface-presets')
    def interface_profiles():
        from . import interface_presets
        return {'profiles':interface_presets.catalog()}

    @app.get('/api/workbench/projects/{pid}/stackup')
    def inspect_stackup(pid: str):
        from . import stackup
        p=project(pid)
        with p.lock:return {**stackup.inspect(p.state['spec']),'base_version':p.state.get('workbench',{}).get('version',0)}

    @app.post('/api/workbench/projects/{pid}/stackup/prepare')
    async def prepare_stackup(pid: str,request: Request):
        from . import buses
        body=await request.json()
        if not isinstance(body,dict):raise HTTPException(422,'Stackup edits need an object.')
        p,version,_=module_snapshot(pid,body)
        try:result=await asyncio.to_thread(buses.project_draft,p,{**body,'action':'stackup'});module_snapshot(pid,body)
        except (ValueError,TypeError,KeyError,cli.KiCadError) as error:raise HTTPException(422,str(error)) from None
        return {**result,'base_version':version}

    @app.post('/api/workbench/projects/{pid}/library/pad-shape/prepare')
    async def prepare_pad_shape(pid: str,request: Request):
        from . import buses
        body=await request.json()
        if not isinstance(body,dict):raise HTTPException(422,'Custom pad edits need a vector-source object.')
        p,version,_=module_snapshot(pid,body)
        try:result=await asyncio.to_thread(buses.project_draft,p,{**body,'action':'pad_shape'});module_snapshot(pid,body)
        except (ValueError,TypeError,KeyError,cli.KiCadError) as error:raise HTTPException(422,str(error)) from None
        return {**result,'base_version':version}

    @app.post('/api/workbench/projects/{pid}/pads/prepare')
    async def prepare_layout_pad(pid: str,request: Request):
        from . import pad_edits
        body=await request.json()
        if not isinstance(body,dict):raise HTTPException(422,'Pad edits need a selected native pad and physical properties.')
        p,version,_=module_snapshot(pid,body)
        try:result=await asyncio.to_thread(pad_edits.project_draft,p,body);module_snapshot(pid,body)
        except (ValueError,TypeError,KeyError,cli.KiCadError) as error:raise HTTPException(422,str(error)) from None
        return {**result,'base_version':version}

    @app.get('/api/workbench/projects/{pid}/pads/{ref}/{pad_id}')
    def inspect_layout_pad(pid: str,ref: str,pad_id: str):
        from . import pad_edits
        try:return pad_edits.inspect(project(pid),ref,pad_id)
        except (ValueError,KeyError) as error:raise HTTPException(422,str(error)) from None

    @app.get('/api/workbench/projects/{pid}/library/footprints/{footprint}/pads/{index}/shape')
    def inspect_pad_shape(pid: str,footprint: str,index: int):
        from . import pad_shapes
        p=project(pid)
        with p.lock:
            asset=project_library.asset(p.state.get('spec'),'footprints','Project:'+footprint)
            if not asset or not 0<=index<len(asset.get('pads',[])):raise HTTPException(404,'This footprint pad is unavailable.')
            pad=copy.deepcopy(asset['pads'][index]);version=p.state.get('workbench',{}).get('version',0)
        if pad.get('shape')!='custom':raise HTTPException(422,'This pad has a standard copper shape.')
        try:report=pad_shapes.describe_pad(pad)
        except ValueError as error:raise HTTPException(422,str(error)) from None
        with p.lock:
            if p.state.get('workbench',{}).get('version',0)!=version:raise HTTPException(409,'The saved pad changed while its shape was compiled.')
        return {'shape_report':report,'version':version}

    @app.post('/api/workbench/projects/{pid}/buses/prepare')
    async def prepare_bus_properties(pid: str,request: Request):
        from . import buses
        body=await request.json()
        if not isinstance(body,dict):raise HTTPException(422,'Bus edits need an object.')
        p,version,_=module_snapshot(pid,body)
        try:result=await asyncio.to_thread(buses.project_draft,p,body);module_snapshot(pid,body)
        except (ValueError,TypeError,KeyError,cli.KiCadError) as error:raise HTTPException(422,str(error)) from None
        return {**result,'base_version':version}

    @app.get('/api/workbench/projects/{pid}/route-tuning')
    def inspect_route_lengths(pid: str):
        from . import route_tuning
        try:return route_tuning.project_inspect(project(pid))
        except (ValueError,TypeError,KeyError,cli.KiCadError) as error:raise HTTPException(422,str(error)) from None

    @app.get('/api/workbench/projects/{pid}/routing')
    def selected_routing_info(pid: str):
        from . import selective_routing
        try:return selective_routing.project_info(project(pid))
        except (ValueError,TypeError,KeyError,cli.KiCadError) as error:raise HTTPException(422,str(error)) from None

    @app.post('/api/workbench/projects/{pid}/routing/prepare')
    async def prepare_selected_routing(pid: str,request: Request):
        import threading
        from contextlib import suppress
        from . import selective_routing,route_tuning
        body=await request.json()
        if not isinstance(body,dict):raise HTTPException(422,'Selected routing needs an object of options.')
        p,version,_=module_snapshot(pid,body);cancel=threading.Event()
        async def disconnected():
            while not cancel.is_set():
                if await request.is_disconnected():cancel.set();return
                await asyncio.sleep(.1)
        watcher=asyncio.create_task(disconnected())
        try:
            result=await asyncio.to_thread(selective_routing.project_prepare,p,body,cancel)
            module_snapshot(pid,body);route_tuning.assert_source(p,result['native_source'])
            return {**result,'base_version':version}
        except asyncio.CancelledError:cancel.set();raise
        except InterruptedError:raise HTTPException(409,'The routing review was canceled.') from None
        except (ValueError,TypeError,KeyError,cli.KiCadError) as error:raise HTTPException(422,str(error)) from None
        except RuntimeError as error:raise HTTPException(502,str(error)) from None
        finally:
            watcher.cancel()
            with suppress(asyncio.CancelledError):await watcher

    @app.post('/api/workbench/projects/{pid}/route-tuning/prepare')
    async def prepare_route_tuning(pid: str,request: Request):
        from . import route_tuning
        body=await request.json()
        if not isinstance(body,dict):raise HTTPException(422,'Route tuning needs an object of options.')
        p,version,_=module_snapshot(pid,body)
        try:
            result=await asyncio.to_thread(route_tuning.project_draft,p,body);module_snapshot(pid,body)
            route_tuning.assert_source(p,result['native_source'])
        except (ValueError,TypeError,KeyError,cli.KiCadError) as error:raise HTTPException(422,str(error)) from None
        return {**result,'base_version':version}

    @app.post('/api/workbench/projects/{pid}/transforms/prepare')
    async def prepare_selection_transform(pid: str,request: Request):
        from . import transforms
        body=await request.json()
        if not isinstance(body,dict):raise HTTPException(422,'Selection transforms need an object of options.')
        p,version,_=module_snapshot(pid,body)
        try:result=await asyncio.to_thread(transforms.project_draft,p,body);module_snapshot(pid,body)
        except (ValueError,TypeError,KeyError,cli.KiCadError) as error:raise HTTPException(422,str(error)) from None
        return {**result,'base_version':version}

    @app.get('/api/workbench/projects/{pid}/buses')
    async def inspect_bus_properties(pid: str):
        from . import buses,workbench_native
        from .kicad import geometry
        p=project(pid);spec=p.state.get('spec') or {};compiled=buses.compile(spec)
        if p.worker and p.worker.is_alive() or getattr(p,'engine_busy',False):return {**compiled,'analysis':None,'pending':'The current engineering run is active.'}
        if not compiled['groups']:return {**compiled,'analysis':{'pairs':[],'buses':[],'bus_matching':[],'issues':compiled['issues']},'native_rules':[],'version':p.state.get('workbench',{}).get('version',0)}
        pcb=workbench_native.final_pcb(p)
        if pcb is None:pcb=Path((await asyncio.to_thread(workbench_native.generate,p))['pcb'])
        return {**compiled,'analysis':buses.analyze(spec,geometry.read(pcb)),'native_rules':buses.native_rules(spec),'version':p.state.get('workbench',{}).get('version',0)}

    @app.post('/api/workbench/projects/{pid}/net-labels/prepare')
    async def prepare_net_label(pid: str,request: Request):
        from . import net_labels
        body=await request.json()
        if not isinstance(body,dict):raise HTTPException(422,'Net label edits need an object.')
        p,version,_=module_snapshot(pid,body)
        try:
            result=await asyncio.to_thread(net_labels.project_draft,p,body);module_snapshot(pid,body)
        except (ValueError,TypeError,KeyError,cli.KiCadError) as error:raise HTTPException(422,str(error)) from None
        return {**result,'base_version':version}

    @app.post('/api/workbench/projects/{pid}/terminals/prepare')
    async def prepare_terminal(pid: str,request: Request):
        from . import terminals
        body=await request.json()
        if not isinstance(body,dict):raise HTTPException(422,'Terminal editing needs an object of properties.')
        p,version,_=module_snapshot(pid,body)
        try:
            result=await asyncio.to_thread(terminals.project_draft,p,body);module_snapshot(pid,body)
        except (ValueError,KeyError,TypeError,cli.KiCadError) as error:raise HTTPException(422,str(error)) from None
        return {**result,'base_version':version}

    @app.post('/api/workbench/projects/{pid}/wire-cuts/prepare')
    async def prepare_wire_cut(pid: str,request: Request):
        from . import wire_cuts
        body=await request.json()
        if not isinstance(body,dict):raise HTTPException(422,'Wire cutting needs an object of properties.')
        p,version,_=module_snapshot(pid,body)
        if getattr(p,'engine_busy',False):raise HTTPException(409,'Wait for the active engineering run before cutting a wire.')
        try:
            result=await asyncio.to_thread(wire_cuts.project_draft,p,body);module_snapshot(pid,body)
        except (ValueError,KeyError,TypeError,cli.KiCadError) as error:raise HTTPException(422,str(error)) from None
        return {**result,'base_version':version}

    @app.post('/api/workbench/projects/{pid}/modules/publish')
    async def publish_module(pid: str,request: Request):
        from . import modules,workbench_native
        from .kicad import geometry
        body=await request.json();p,version,spec=module_snapshot(pid,body)
        try:
            pcb=workbench_native.final_pcb(p)
            if pcb is None:pcb=Path((await asyncio.to_thread(workbench_native.generate,p))['pcb'])
            asset=modules.publish(spec,name=body.get('name','Module'),description=body.get('description',''),ports=body.get('ports',{}),native_geometry=geometry.read(pcb))
            module_snapshot(pid,body)
        except (ValueError,KeyError,TypeError) as error:raise HTTPException(422,str(error)) from None
        return {'module':asset,'base_version':version,'fingerprint':modules.fingerprint(asset)}

    @app.post('/api/workbench/projects/{pid}/modules/instantiate')
    async def instantiate_module(pid: str,request: Request):
        from . import modules
        body=await request.json();_,version,spec=module_snapshot(pid,body)
        try:
            result=modules.instantiate(spec,body.get('module'),body.get('instance'),offset=body.get('offset'),position=body.get('position'),parent=body.get('parent',''),connections=body.get('connections'))
            validate_draft(result)
        except (ValueError,KeyError,TypeError) as error:raise HTTPException(422,str(error)) from None
        return {'spec':result,'base_version':version}

    @app.get('/api/workbench/projects/{pid}/modules/catalog')
    def module_catalog_listing(pid: str,request: Request):
        from . import module_catalog
        project(pid);return {'entries':module_catalog.listing(get_manager(),collaboration.identity(request.scope)),'workspace':module_catalog.workspace_id()}

    @app.get('/api/workbench/projects/{pid}/modules/updates')
    def module_update_listing(pid: str,request: Request):
        from . import module_catalog
        p=project(pid)
        with p.lock:spec=json.loads(json.dumps(p.state.get('spec') or {}))
        return {'updates':module_catalog.updates(get_manager(),collaboration.identity(request.scope),spec)}

    @app.post('/api/workbench/projects/{pid}/modules/catalog/install')
    async def install_catalog_module(pid: str,request: Request):
        from . import module_catalog,module_updates
        body=await request.json()
        if not isinstance(body,dict):raise HTTPException(422,'Module installation needs an object.')
        _,version,spec=module_snapshot(pid,body)
        try:
            asset=module_catalog.resolve(get_manager(),collaboration.identity(request.scope),body.get('catalog_id'),version=body.get('version'))
            result=module_updates.install(spec,body.get('module'),asset);validate_draft(result);module_snapshot(pid,body)
        except (ValueError,KeyError,TypeError) as error:raise HTTPException(422,str(error)) from None
        return {'spec':result,'base_version':version}

    @app.post('/api/workbench/projects/{pid}/modules/package')
    async def import_module_versions(pid: str,request: Request):
        from . import module_updates
        body=await request.json()
        if not isinstance(body,dict) or not isinstance(body.get('modules'),dict) or not body['modules']:raise HTTPException(422,'Choose a module revision package.')
        _,version,spec=module_snapshot(pid,body)
        try:
            for module_id,asset in body['modules'].items():
                current=spec.get('library',{}).get('modules',{}).get(module_id)
                if current and module_updates.version(asset)<=module_updates.version(current):raise ValueError('That module revision is already installed. Import a newer release or choose another library ID.')
                spec=module_updates.install(spec,module_id,asset)
            validate_draft(spec);module_snapshot(pid,body)
        except (ValueError,TypeError,KeyError) as error:raise HTTPException(422,str(error)) from None
        return {'spec':spec,'base_version':version}

    @app.post('/api/workbench/projects/{pid}/modules/releases/publish')
    async def publish_module_release(pid: str,request: Request):
        from . import modules,module_catalog,workbench_native
        from .kicad import geometry
        body=await request.json()
        if not isinstance(body,dict):raise HTTPException(422,'Publishing a module needs an object.')
        p,version,spec=module_snapshot(pid,body)
        try:
            pcb=workbench_native.final_pcb(p)
            if pcb is None:pcb=Path((await asyncio.to_thread(workbench_native.generate,p))['pcb'])
            candidate=modules.publish(spec,name=body.get('name','Module'),description=body.get('description',''),ports=body.get('ports',{}),native_geometry=geometry.read(pcb))
            asset=module_catalog.publish(p,body.get('module'),candidate,base_version=version,expected_version=body.get('expected_version',0),note=body.get('note',''))
            uid=asset['origin']['catalog_id']
            for row in get_manager().list():
                target=get_manager().get(row['id'])
                if target is p:continue
                if any(value.get('origin',{}).get('catalog_id')==uid for value in (target.state.get('spec') or {}).get('library',{}).get('modules',{}).values()):target.emit({'type':'module_catalog_changed'})
        except (ValueError,KeyError,TypeError,cli.KiCadError) as error:raise HTTPException(422,str(error)) from None
        return {'module':asset,'base_version':version,'published':True}

    @app.post('/api/workbench/projects/{pid}/modules/updates/prepare')
    async def prepare_module_updates(pid: str,request: Request):
        from . import module_updates
        body=await request.json()
        if not isinstance(body,dict):raise HTTPException(422,'Module updates need an object.')
        p,version,_=module_snapshot(pid,body)
        try:
            result=await asyncio.to_thread(module_updates.project_draft,p,body,manager=get_manager(),actor=collaboration.identity(request.scope));module_snapshot(pid,body)
        except (ValueError,KeyError,TypeError,cli.KiCadError) as error:raise HTTPException(422,str(error)) from None
        return {**result,'base_version':version}

    @app.post('/api/workbench/projects/{pid}/modules/source')
    async def create_module_source(pid: str,request: Request):
        from . import module_catalog,module_updates,modules
        body=await request.json()
        if not isinstance(body,dict):raise HTTPException(422,'Module source creation needs an object.')
        actor=collaboration.identity(request.scope)
        if actor.get('mode')=='share':raise HTTPException(403,'Sign in with a workspace account to own a source project.')
        _,version,spec=module_snapshot(pid,body);module_id=body.get('module')
        if not project_library.identifier(module_id):raise HTTPException(422,'Choose a valid module library ID.')
        asset=spec.get('library',{}).get('modules',{}).get(module_id)
        try:modules.validate_asset(module_id,asset)
        except (ValueError,KeyError,TypeError) as error:raise HTTPException(422,str(error)) from None
        origin=asset.get('origin',{});existing=get_manager().get(origin.get('project_id'))
        if not body.get('copy') and existing and origin.get('workspace') in (None,module_catalog.workspace_id()) and collaboration.ROLES.get(collaboration.project_role(actor,existing),0)>=10:return {'spec':spec,'source_project':existing.id,'base_version':version}
        title=asset['name']+' source';source=get_manager().create(title)
        origin={'catalog_id':module_catalog.identifier(source.id,module_id),'workspace':module_catalog.workspace_id(),'project_id':source.id,'module_id':module_id,'source_version':1,'pending':True}
        local=json.loads(json.dumps(asset));local['origin']=origin;source_spec=json.loads(json.dumps(asset['design']));source_spec.setdefault('library',{}).setdefault('modules',{})[module_id]=local
        source.state.update(custom_title=title,spec=source_spec,owner_id=actor['id'],module_source={'project':pid,'module':module_id,'fingerprint':module_updates.digest(asset)},workbench={'version':1,'checks_stale':True,'saved_at':time.time()})
        validate_draft(source_spec);_write_spec(source);source.save();module_snapshot(pid,body)
        spec['library']['modules'][module_id]=local
        return {'spec':spec,'source_project':source.id,'base_version':version}

    @app.post('/api/workbench/projects/{pid}/modules/convert')
    async def convert_module(pid: str,request: Request):
        from . import modules,workbench_native
        from .kicad import board,geometry
        body=await request.json();p,version,spec=module_snapshot(pid,body)
        def prepare():
            pcb=workbench_native.final_pcb(p)
            if pcb is None:pcb=Path(workbench_native.generate(p)['pcb'])
            result=modules.convert_selection(spec,body.get('refs'),body.get('module'),body.get('instance'),name=body.get('name','Module'),ports=body.get('ports'),bounds=body.get('bounds'),position=body.get('position'),native_geometry=geometry.read(pcb))
            validate_draft(result['spec'])
            template=result['spec']['library']['modules'][result['module']]['design']
            with tempfile.TemporaryDirectory(prefix='wholeboard-module-preview-') as folder:
                native=board.build(template,Path(folder));preview=Path(native['pcb'])
                if template.get('fixed_zones') and cli.find_kicad_cli():cli.drc(preview,refill=True,save=True)
                result['capture_geometry']=geometry.read(preview)
            return result
        try:
            result=await asyncio.to_thread(prepare);module_snapshot(pid,body)
        except (ValueError,KeyError,TypeError,cli.KiCadError) as error:raise HTTPException(422,str(error)) from None
        return {**result,'base_version':version}

    @app.post("/api/workbench/projects/{pid}/library/validate")
    async def validate_project_library(pid: str, request: Request):
        project(pid)
        body=await request.json()
        validate_draft(body.get("spec"))
        return {"ok":True}

    @app.post("/api/workbench/projects/{pid}/library/copy")
    async def copy_library_asset(pid: str, request: Request):
        p=project(pid);body=await request.json()
        try:
            asset=project_library.copy_installed(str(body.get("kind","")),str(body.get("id","")),p.state.get("spec"))
        except (ValueError,TypeError,KeyError) as error:
            raise HTTPException(422,str(error)) from None
        return {"asset":asset,"note":"Copied editable geometry. External 3D model files are not included."}

    @app.post("/api/workbench/projects/{pid}/library/import-native")
    async def import_native_library(pid: str, request: Request):
        project(pid);body=await request.json()
        try:
            assets=project_library.import_native(str(body.get("kind","")),body.get("content"))
        except (ValueError,TypeError,KeyError,IndexError,RecursionError) as error:
            raise HTTPException(422,f"The native library could not be imported: {str(error)[:200]}") from None
        return {"assets":assets,"note":"Imported editable geometry. External 3D model files are not included."}

    @app.get("/api/workbench/example")
    def example():
        return json.loads((Path(__file__).with_name("web") / "workbench-example.json").read_text())

    @app.post("/api/workbench/schematic-view")
    async def schematic_view(request: Request):
        from . import schematic_view as view
        spec = await request.json()
        validate_draft(spec)
        try:
            return await asyncio.to_thread(view.scene, spec)
        except (ValueError, KeyError, TypeError) as e:
            raise HTTPException(422, str(e)) from None

    @app.post("/api/workbench/projects", status_code=201)
    async def create(request: Request):
        body = await request.json()
        spec = example() if body.get("example") else body.get("spec") or {
            "name": "untitled_board", "summary": "", "board": {"width_mm": 50, "height_mm": 35, "layers": 2},
            "components": [], "nets": [],
        }
        validate_draft(spec)
        title = re.sub(r"\s+", " ", str(body.get("title") or "Untitled project")).strip()[:80]
        p = get_manager().create(body.get("prompt") or title)
        p.state.update(custom_title=title, spec=spec, owner_id=collaboration.identity(request.scope)["id"],
                       workbench={"version": 1, "checks_stale": True, "saved_at": time.time()})
        _write_spec(p)
        p.save()
        return {**p.summary(), "spec": spec, "version": 1}

    @app.patch("/api/workbench/projects/{pid}/metadata")
    async def project_metadata(pid: str, request: Request):
        p = project(pid)
        body = await request.json()
        if "tags" in body and not isinstance(body["tags"], list):
            raise HTTPException(422, "Tags must be a list.")
        with p.lock:
            if "starred" in body:
                p.state["starred"] = bool(body["starred"])
            if "tags" in body:
                p.state["tags"] = list(dict.fromkeys(str(t).strip()[:30] for t in body["tags"] if str(t).strip()))[:12]
            p.save()
        p.emit({"type": "project_metadata", **p.summary()})
        return p.summary()

    @app.post("/api/workbench/projects/{pid}/clone", status_code=201)
    async def clone_project(pid: str, request: Request):
        source = project(pid)
        body = await request.json() if await request.body() else {}
        with source.lock:
            spec = json.loads(json.dumps(source.state.get("spec")))
        validate_draft(spec)
        title = str(body.get("title") or (source.display_title() + " copy"))[:80]
        clone = get_manager().create(title)
        clone.state.update(custom_title=title, spec=spec, tags=list(source.state.get("tags", [])), owner_id=collaboration.identity(request.scope)["id"],
                           cloned_from={"id": source.id, "title": source.display_title()},
                           workbench={"version": 1, "checks_stale": True, "saved_at": time.time()})
        clone.state["prompt"] = source.state.get("prompt") or title
        if source.state.get("enclosure_spec"):
            clone.state["enclosure_spec"] = json.loads(json.dumps(source.state["enclosure_spec"]))
        root = source.root.resolve()
        for f in source.root.rglob("*"):
            rel = f.relative_to(source.root)
            resolved = f.resolve().relative_to(root) if f.resolve().is_relative_to(root) else None
            if not f.is_file() or resolved is None or any(s.startswith(".") for s in (*rel.parts,*resolved.parts)):
                continue
            if any(path.parts[0] in {"native", "history"} or re.fullmatch(r"rev\d+", path.parts[0]) or path.as_posix() in {"state.json", "events.jsonl", "design.json"} for path in (rel,resolved)):
                continue
            target = clone.root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, target)
        _write_spec(clone)
        clone.save()
        clone.chat("system", f"Cloned the design and project files from {source.display_title()}.")
        return {**clone.summary(), "version": 1}

    @app.put("/api/workbench/projects/{pid}/design")
    async def save_design(pid: str, request: Request):
        p = project(pid)
        body = await request.json()
        spec = body.get("spec")
        validate_draft(spec)
        from contextlib import nullcontext
        from . import route_tuning,workbench_native
        import threading
        native_lock=workbench_native._locks.setdefault(p.id,threading.RLock()) if 'native_source' in body or 'routing_proposal' in body else nullcontext()
        with native_lock,p.lock:
            if (p.worker and p.worker.is_alive()) or getattr(p, "engine_busy", False):
                raise HTTPException(409, "The agent is working. Stop it before editing the design.")
            meta = p.state.get("workbench") or {"version": 0}
            if body.get("base_version") != meta["version"]:
                raise HTTPException(409, "Another editor has saved this project. Reload before saving your changes.")
            if 'native_source' in body:route_tuning.assert_source(p,body['native_source'])
            if 'routing_proposal' in body:
                from . import selective_routing
                selective_routing.validate_proposal(p,body['routing_proposal'],spec)
            from . import design_identity
            unchanged=design_identity.equal(p.state.get('spec'),spec)
            p.state["spec"] = spec
            p.state["workbench"] = {"version": meta["version"] + 1, "checks_stale": meta.get('checks_stale',True) if unchanged else True, "saved_at": time.time()}
            p.state["updated"] = time.time()
            _write_spec(p)
            p.save()
        p.emit({"type": "design_saved", "version": p.state["workbench"]["version"]})
        return {"ok": True, **p.state["workbench"]}

    @app.get("/api/workbench/projects/{pid}/history")
    def edit_history(pid: str):
        p = project(pid)
        if p.state.get("spec"):
            _write_spec(p)  # capture the current version for projects created before edit history existed
        rows = []
        for f in (p.root / "history").glob("design-v*.json"):
            try:
                data = json.loads(f.read_text())
                spec = data.pop("spec")
                rows.append({**data, "components": len(spec.get("components", [])),
                             "nets": len(spec.get("nets", [])), "board": spec.get("board", {})})
            except (OSError, ValueError, KeyError):
                continue
        return {"current_version":(p.state.get('workbench') or {}).get('version',0),"versions": sorted(rows, key=lambda r: -r["version"])}

    @app.get("/api/workbench/projects/{pid}/history/{version}")
    def edit_snapshot(pid: str, version: int):
        p = project(pid)
        f = p.root / "history" / f"design-v{version}.json"
        if not f.is_file():
            raise HTTPException(404, "Design version not found.")
        from . import design_identity
        payload=f.read_bytes();data=json.loads(payload);return {**data,'snapshot_sha256':hashlib.sha256(payload).hexdigest(),'semantic_sha256':design_identity.fingerprint(data.get('spec'))}

    @app.get("/api/workbench/projects/{pid}/history/{version}/compare")
    def compare_edit(pid: str, version: int, to_version: int | None = None):
        from . import revisions
        p=project(pid)
        with p.lock:
            if to_version is not None:
                try:return revisions.design_history(p,{'from_version':version,'to_version':to_version})
                except ValueError as error:raise HTTPException(422,str(error)) from None
            snapshot=edit_snapshot(pid,version)
            return {"version":version,"from_version":version,"to_version":p.state.get('workbench',{}).get('version',0),
                    "from_snapshot_sha256":hashlib.sha256((p.root/'history'/f'design-v{version}.json').read_bytes()).hexdigest(),
                    **revisions.compare(snapshot['spec'],p.state.get('spec') or {})}

    @app.post("/api/workbench/projects/{pid}/history/{version}/restore")
    async def restore_snapshot(pid: str, version: int, request: Request):
        p = project(pid)
        body = await request.json()
        snapshot = edit_snapshot(pid, version)
        with p.lock:
            if (p.worker and p.worker.is_alive()) or getattr(p, "engine_busy", False):
                raise HTTPException(409, "Stop the active run before restoring a design.")
            current = (p.state.get("workbench") or {}).get("version", 0)
            if body.get("base_version") != current:
                raise HTTPException(409, "Another editor has changed this project. Reload before restoring.")
            from . import design_identity
            stale=(p.state.get('workbench') or {}).get('checks_stale',True) if design_identity.equal(p.state.get('spec'),snapshot['spec']) else True
            p.state["spec"] = snapshot["spec"]
            p.state["workbench"] = {"version": current + 1, "checks_stale": stale, "saved_at": time.time()}
            _write_spec(p)
            p.save()
        p.chat("system", f"Restored design version {version} as version {current + 1}.")
        return {"ok": True, "version": current + 1, "spec": p.state["spec"],"workbench":dict(p.state['workbench'])}

    def ai_change_response(operation):
        from .ai_changes import ChangeConflict
        try:return operation()
        except FileNotFoundError as error:raise HTTPException(404,str(error)) from None
        except ChangeConflict as error:raise HTTPException(409,str(error)) from None
        except ValueError as error:raise HTTPException(422,str(error)) from None

    @app.get('/api/workbench/projects/{pid}/ai-changes/{request_id}')
    def review_ai_change(pid: str, request_id: str):
        from . import ai_changes
        return ai_change_response(lambda:ai_changes.review(project(pid),request_id))

    @app.get('/api/workbench/projects/{pid}/ai-changes/{request_id}/file')
    def review_ai_file(pid: str, request_id: str, path: str):
        from . import ai_changes
        return ai_change_response(lambda:ai_changes.file_diff(project(pid),request_id,path))

    @app.post('/api/workbench/projects/{pid}/ai-changes/{request_id}/restore')
    async def restore_ai_change(pid: str, request_id: str, request: Request):
        from . import ai_changes
        body=await request.json()
        return ai_change_response(lambda:ai_changes.restore(project(pid),request_id,body))

    def text_path(p, path: str) -> Path:
        from .project_paths import protected_output
        rel = Path(path)
        root = p.root.resolve()
        target = (root / rel).resolve()
        protected = {"state.json", "events.jsonl", "design.json"}
        resolved = target.relative_to(root) if target.is_relative_to(root) else Path("/")
        if not rel.parts or rel.is_absolute() or not target.is_relative_to(root) or any(s.startswith(".") for s in (*rel.parts,*resolved.parts)) or protected_output(root,target,protected) or rel.suffix.lower() not in {".md", ".txt", ".json", ".py", ".cpp", ".c", ".h", ".hpp", ".ini", ".scad", ".csv"}:
            raise HTTPException(422, "This path is not an editable project text file.")
        return target

    @app.get("/api/workbench/projects/{pid}/text/{path:path}")
    def get_text(pid: str, path: str, allow_missing: bool = False):
        target = text_path(project(pid), path)
        if allow_missing and not target.exists():
            return {'exists': False, 'content': '', 'sha': None}
        if not target.is_file() or target.stat().st_size > 2_000_000:
            raise HTTPException(404, "Text file not found or too large to edit.")
        raw = target.read_bytes()
        if len(raw)>2_000_000:
            raise HTTPException(404, "Text file not found or too large to edit.")
        return {"content": raw.decode('utf-8'), "sha": hashlib.sha256(raw).hexdigest()}

    @app.put("/api/workbench/projects/{pid}/text/{path:path}")
    async def put_text(pid: str, path: str, request: Request):
        p = project(pid)
        target = text_path(p, path)
        body = await request.json()
        content = body.get("content")
        if not isinstance(content, str) or len(content) > 1_000_000:
            raise HTTPException(422, "Use a text file smaller than 1 MB.")
        with p.lock:
            if (p.worker and p.worker.is_alive()) or getattr(p, "engine_busy", False):
                raise HTTPException(409, "Wait for the active run before editing project files.")
            current = hashlib.sha256(target.read_bytes()).hexdigest() if target.exists() else None
            if current != body.get("base_sha"):
                raise HTTPException(409, "This file changed in another editor. Reload it before saving.")
            if path.endswith('.cad.json'):
                from . import ai_changes,mechanical_history,mechanical
                try:
                    before = mechanical_history.capture(p,path)
                    target = mechanical._source_path(p,before['source'])
                    with ai_changes.rollback_on_error(p,[target]):
                        target.parent.mkdir(parents=True,exist_ok=True)
                        _atomic_text(target,content)
                        mechanical_history.record(p,before,mechanical_history.capture(p,before['source']),'Saved CAD code')
                        next_history = mechanical_history.summary(p)
                        p.save()
                except (ValueError,OSError) as error:raise HTTPException(422,str(error)) from None
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                _atomic_text(target, content)
        if path.endswith('.cad.json'):mechanical._notify(p,{"type":"file_saved","path":path})
        else:p.emit({"type": "file_saved", "path": path})
        result = {"ok": True, "sha": hashlib.sha256(content.encode()).hexdigest(), "url": p.file_url(target)}
        if path.endswith('.cad.json'):
            result['mechanical_history'] = next_history
            mechanical._notify(p,{'type':'mechanical_history_changed','history':result['mechanical_history']})
        return result

    @app.get("/api/workbench/projects/{pid}/files")
    def files(pid: str, offset: int = 0, limit: int = 1000, expected_index_sha256: str | None = None):
        from .file_catalog import listing
        p = project(pid)
        try:
            return listing(p, offset, limit, expected_index_sha256)
        except ValueError as error:
            raise HTTPException(422, str(error)) from None
        except RuntimeError as error:
            raise HTTPException(409, str(error)) from None

    @app.get("/api/workbench/projects/{pid}/bom.csv")
    def bom(pid: str):
        p = project(pid)
        stream = io.StringIO(newline="")
        writer = csv.writer(stream)
        writer.writerow(["Designator", "Value", "Footprint", "Manufacturer part number", "LCSC", "Description", "Unit price", "Currency", "Stock"])
        quote = p.state.get("quote") or {}
        prices = (p.state.get("stock") or {}).get("lines", []) + (quote.get("components") or {}).get("lines", [])
        for c in (p.state.get("spec") or {}).get("components", []):
            price = next((r for r in prices if c["ref"] in r.get("refs", []) and c.get("lcsc") == r.get("lcsc")), {})
            writer.writerow([_csv_cell(c.get(k)) for k in ("ref", "value", "footprint", "mpn", "lcsc", "description")] +
                            [price.get("unit", ""), quote.get("currency", "USD") if price.get("unit") is not None else "", price.get("stock", "")])
        return Response("\ufeff" + stream.getvalue(), media_type="text/csv",
                        headers={"Content-Disposition": 'attachment; filename="bill-of-materials.csv"'})

    @app.post("/api/workbench/projects/{pid}/attachments", status_code=201)
    async def attachment(pid: str, request: Request):
        p = project(pid)
        body = await request.json()
        name = re.sub(r"[^\w. -]", "_", Path(str(body.get("name") or "attachment.txt")).name)[:120]
        try:
            encoded = body.get("data", "")
            if not isinstance(encoded, str) or len(encoded) > 12_000_000:
                raise ValueError("Use an attachment smaller than 8 MB.")
            data = base64.b64decode(encoded, validate=True)
            if len(data) > 8_000_000:
                raise ValueError("Use an attachment smaller than 8 MB.")
            if name.lower().endswith(".pdf"):
                from pypdf import PdfReader
                reader = PdfReader(io.BytesIO(data))
                context = "\n".join(page.extract_text() or "" for page in reader.pages[:20])[:50_000]
                if not context.strip():
                    raise ValueError("This PDF has no extractable text. Attach a text version of the datasheet.")
            else:
                context = data.decode("utf-8")[:50_000]
        except (ValueError, TypeError, binascii.Error, UnicodeDecodeError) as e:
            raise HTTPException(422, str(e)) from None
        except Exception:
            raise HTTPException(422, "This PDF could not be read.") from None
        folder = p.root / "attachments"
        folder.mkdir(exist_ok=True)
        path = folder / (uuid.uuid4().hex[:8] + "-" + name)
        path.write_bytes(data)
        return {"name": name, "url": p.file_url(path), "text": context}

    @app.post("/api/workbench/projects/{pid}/checks")
    def checks(pid: str):
        p = project(pid)
        with p.lock:
            spec = json.loads(json.dumps(p.state.get("spec")))
            version = (p.state.get("workbench") or {}).get("version", 0)
        validate_draft(spec)
        have_kicad = bool(cli.find_kicad_cli(config.load()))
        have_libs = bool(libs.locate("footprints") and libs.locate("symbols"))
        checks = [{"id": "integrity", "title": "Design integrity", "status": "passed",
                   "detail": f"{len(spec.get('components', []))} unique components; all net references resolve."}]
        if have_libs:
            try:
                rep = design.validate(spec)
                checks.append({"id": "libraries", "title": "KiCad library validation",
                               "status": "passed" if rep.ok else "error",
                               "detail": "\n".join(rep.errors + rep.warnings) or "Footprints and pins resolved."})
            except (ValueError, KeyError, TypeError) as e:
                checks.append({"id": "libraries", "title": "KiCad library validation", "status": "error", "detail": str(e)})
        else:
            checks.append({"id": "libraries", "title": "Symbols and footprints", "status": "unavailable",
                           "detail": "Install the KiCad symbol and footprint libraries in Settings → Tools."})
        for key, title in (("erc", "Electrical rule check"), ("drc", "PCB design rule check")):
            checks.append({"id": key, "title": title, "status": "not_run" if have_kicad else "unavailable",
                           "detail": "Build the current design to run this check." if have_kicad else "KiCad CLI is not installed."})
        return {"checks": checks, "manufacturing_ready": False, "version": version}
