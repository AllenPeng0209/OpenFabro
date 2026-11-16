#!/usr/bin/env python3
"""Build a wheel outside the checkout, install it, and smoke its isolated web server.

Uses the current interpreter's installed runtime dependencies. It does not install
native engineering tools or call an AI provider. Build dependencies are isolated.
"""
from __future__ import annotations

import hashlib
import base64
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
REQUIRED = [
    "openfabro/__main__.py", "wholeboard/document_context.py",
    "wholeboard/file_catalog.py", "wholeboard/project_paths.py", "wholeboard/object_groups.py", "wholeboard/parametric_symbols.py", "wholeboard/design_identity.py",
    "wholeboard/canvas_references.py", "wholeboard/canvas_layer_context.py", "wholeboard/web/workbench-markup.mjs", "wholeboard/web/workbench-markup.css",
    "wholeboard/design_origin.py", "wholeboard/web/workbench-ai-changes.mjs",
    "wholeboard/ai_changes.py", "wholeboard/web/workbench-ai-files.mjs",
    "wholeboard/arrange.py", "wholeboard/transforms.py", "wholeboard/web/workbench-transforms.mjs", "wholeboard/web/workbench-viewports.mjs",
    "wholeboard/kicad/schematic_wires.py", "wholeboard/workbench_native.py",
    "wholeboard/web/workbench-component-hotkeys.mjs",
    "wholeboard/web/workbench-layers.mjs", "wholeboard/web/workbench-layers-ui.mjs", "wholeboard/web/workbench-native-layers.mjs",
    "wholeboard/web/workbench-pane-dock.mjs",
    "wholeboard/web/workbench-display.mjs",
    "wholeboard/web/workbench-symbol.mjs", "wholeboard/web/workbench-collab.mjs",
    "wholeboard/web/workbench-cad.mjs", "wholeboard/web/workbench-cad-model.mjs", "wholeboard/web/workbench-cad-ui.mjs", "wholeboard/web/mesh3d.js",
    "wholeboard/web/workbench-camera.mjs", "wholeboard/web/workbench-navigation.mjs", "wholeboard/web/workbench-navigation.css",
    "wholeboard/routing_pairs.py", "wholeboard/web/workbench-diff-pair.mjs",
    "wholeboard/tuning_geometry.py", "wholeboard/route_tuning.py", "wholeboard/web/workbench-route-tuning.mjs",
    "wholeboard/selective_routing.py", "wholeboard/web/workbench-native-routing.mjs",
    "wholeboard/web/workbench-route-obstacles.mjs",
    "wholeboard/mechanical.py", "wholeboard/freecad_model.py", "wholeboard/mechanical_history.py", "wholeboard/web/workbench-mechanical-parts.mjs",
    "wholeboard/mechanical_assets.py", "wholeboard/freecad_import.py", "wholeboard/web/workbench-mechanical-assets.mjs",
    "wholeboard/mesh_assets.py", "wholeboard/web/workbench-mesh-files.mjs",
    "wholeboard/drawing_assets.py",
    "wholeboard/assemblies.py", "wholeboard/freecad_assembly.py", "wholeboard/web/workbench-mechanical-assembly.mjs",
    "wholeboard/freecad_topology.py", "wholeboard/web/workbench-cad-topology.mjs", "wholeboard/web/workbench-mechanical-picker.mjs",
    "wholeboard/freecad_curve_events.py",
    "wholeboard/cad_mass.py",
    "wholeboard/interface_presets.py", "wholeboard/web/workbench-interface-presets.mjs",
    "wholeboard/stackup.py", "wholeboard/web/workbench-stackup.mjs", "wholeboard/web/workbench-stackup.css",
    "wholeboard/pad_shapes.py", "wholeboard/web/workbench-pad-shapes.mjs",
    "wholeboard/pad_edits.py", "wholeboard/web/workbench-pad-editor.mjs",
    "wholeboard/jlc/capabilities.json",
    "wholeboard/sketch_program.py", "wholeboard/freecad_sketch.py", "wholeboard/web/workbench-sketch-model.mjs", "wholeboard/web/workbench-mechanical-features.mjs",
    "wholeboard/mechanical_materials.py", "wholeboard/web/workbench-material-model.mjs", "wholeboard/web/workbench-material-renderer.mjs",
    "wholeboard/web/workbench-curve-analysis.mjs",
    "wholeboard/web/workbench-surface-analysis.mjs",
    "wholeboard/web/workbench.css",
    "wholeboard/web/workbench-objects.css", "wholeboard/web/workbench-objects.mjs",
    "wholeboard/web/workbench-objects-model.mjs",
    "wholeboard/web/workbench-object-groups.mjs", "wholeboard/web/workbench-object-groups-model.mjs",
    "wholeboard/web/workbench-parametric.mjs", "wholeboard/web/workbench-parametric-model.mjs", "wholeboard/web/workbench-parametric.css",
    "wholeboard/web/workbench-files.css", "wholeboard/web/workbench-files.mjs",
    "wholeboard/web/workbench-files-model.mjs",
    "wholeboard/web/workbench-drafts.mjs", "wholeboard/web/workbench-draft-recovery.mjs",
    "wholeboard/web/workbench-shortcuts.css", "wholeboard/web/workbench-shortcuts.mjs",
    "wholeboard/web/workbench-markdown.mjs", "wholeboard/web/vendor/purify.mjs",
    "wholeboard/web/fonts/roboto-regular.ttf",
    "wholeboard/production/api.py", "wholeboard/production/service.py",
    "wholeboard/production/estimate.py", "wholeboard/production/suppliers.py",
    "wholeboard/web/production.html", "wholeboard/web/production.mjs", "wholeboard/web/production.css",
]


def command(arguments: list[str], log: Path) -> None:
    result = subprocess.run(arguments, capture_output=True, text=True, timeout=180)
    log.write_text(result.stdout + result.stderr)
    if result.returncode:
        raise RuntimeError(f"Command failed; see {log}:\n{(result.stdout + result.stderr)[-1500:]}")


def main() -> None:
    output = REPO / "test-results" / f"selfhost-package-{int(time.time())}"
    output.mkdir(parents=True)
    with tempfile.TemporaryDirectory(prefix="openfabro-package-") as temporary:
        root = Path(temporary)
        source = root / "source"
        source.mkdir()
        for name in ("pyproject.toml", "README.md", "LICENSE"):
            shutil.copy2(REPO / name, source / name)
        for name in ("wholeboard", "openfabro"):
            shutil.copytree(REPO / name, source / name, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        command([sys.executable, "-m", "pip", "wheel", "--no-deps", str(source), "-w", str(output)], output / "build.log")
        wheel = next(output.glob("openfabro-*.whl"))
        installed = root / "installed"
        command([sys.executable, "-m", "pip", "install", "--no-deps", "--target", str(installed), str(wheel)], output / "install.log")
        with zipfile.ZipFile(wheel) as archive:
            missing = set(REQUIRED) - set(archive.namelist())
            assert not missing, f"Missing wheel assets: {sorted(missing)}"
        configuration = root / "configuration"
        configuration.mkdir()
        # OPENFABRO_HOME alone does not isolate the default Projects directory.
        (configuration / "config.json").write_text(json.dumps({"projects_dir": str(root / "projects")}))
        env = {**os.environ, "OPENFABRO_HOME": str(configuration), "PYTHONPATH": str(installed)}
        module = subprocess.check_output([sys.executable, "-c", "import wholeboard;print(wholeboard.__file__)"], env=env, cwd=root, text=True).strip()
        assert module.startswith(str(installed)), f"Imported checkout instead of installed wheel: {module}"
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        with (output / "server.log").open("w") as log:
            child = subprocess.Popen([sys.executable, "-m", "openfabro", "--host", "127.0.0.1", "--port", str(port), "--no-browser"], env=env, cwd=root, stdout=log, stderr=subprocess.STDOUT)
            try:
                origin = f"http://127.0.0.1:{port}"
                for _ in range(100):
                    assert child.poll() is None, "Installed server exited"
                    try:
                        html = urllib.request.urlopen(origin + "/", timeout=2).read().decode()
                        break
                    except (OSError, TimeoutError):
                        time.sleep(.1)
                else:
                    raise AssertionError("Installed server startup timed out")
                assert 'id="shortcutsDialog"' in html and "OpenFabro" in html
                assert json.load(urllib.request.urlopen(origin + "/api/projects")) == []
                assert json.load(urllib.request.urlopen(origin + "/api/workbench/example"))["components"]
                production = urllib.request.urlopen(origin + "/production").read().decode()
                assert 'id="productionApp"' in production, "Installed production workspace is missing"
                for name in ("production.mjs", "production.css"):
                    assert len(urllib.request.urlopen(origin + "/static/" + name).read()) > 100
                paths = re.findall(r'(?:src|href)="(/assets/[^\"]+\.(?:css|js|mjs))"', html)
                assert {"workbench.css", "workbench-shortcuts.css", "workbench-objects.css", "workbench-files.css", "workbench.mjs", "board.js"}.issubset({path.rsplit("/", 1)[1] for path in paths}), "Versioned app assets are missing from installed HTML"
                prefix = paths[0].rsplit("/", 1)[0]
                paths.extend(prefix + "/" + name for name in ("workbench-shortcuts.mjs", "workbench-objects.mjs", "workbench-objects-model.mjs", "workbench-canvas.mjs", "workbench-routing.mjs", "workbench-files.mjs", "workbench-files-model.mjs", "workbench-object-groups.mjs", "workbench-object-groups-model.mjs", "workbench-parametric.mjs", "workbench-parametric-model.mjs", "workbench-markup.mjs", "workbench-ai-changes.mjs", "workbench-ai-files.mjs", "workbench-transforms.mjs", "workbench-viewports.mjs", "workbench-component-hotkeys.mjs", "workbench-layers.mjs", "workbench-layers-ui.mjs", "workbench-native-layers.mjs"))
                paths.append(prefix+'/workbench-pane-dock.mjs')
                paths.append(prefix+'/workbench-display.mjs')
                paths.extend(prefix+'/'+name for name in ('workbench-symbol.mjs','workbench-collab.mjs'))
                paths.extend(prefix+'/'+name for name in ('workbench-cad.mjs','workbench-cad-model.mjs','workbench-cad-ui.mjs','workbench-icons.mjs'))
                paths.extend(prefix+'/'+name for name in ('workbench-camera.mjs','workbench-navigation.mjs','workbench-navigation.css'))
                paths.append(prefix+'/workbench-diff-pair.mjs')
                paths.append(prefix+'/workbench-route-tuning.mjs')
                paths.append(prefix+'/workbench-native-routing.mjs')
                paths.append(prefix+'/workbench-route-obstacles.mjs')
                paths.extend(prefix+'/'+name for name in ('workbench-mechanical-parts.mjs','workbench-mechanical-assets.mjs','workbench-mesh-files.mjs'))
                paths.extend(prefix+'/'+name for name in ('workbench-mechanical-assembly.mjs','workbench-cad-topology.mjs','workbench-mechanical-picker.mjs'))
                paths.extend(prefix+'/'+name for name in ('workbench-sketch-model.mjs','workbench-mechanical-features.mjs'))
                paths.extend(prefix+'/'+name for name in ('workbench-material-model.mjs','workbench-material-renderer.mjs'))
                paths.append(prefix+'/workbench-curve-analysis.mjs')
                paths.append(prefix+'/workbench-surface-analysis.mjs')
                paths.append(prefix+'/workbench-interface-presets.mjs')
                paths.extend(prefix+'/'+name for name in ('workbench-stackup.mjs','workbench-stackup.css'))
                paths.append(prefix+'/workbench-pad-shapes.mjs')
                paths.append(prefix+'/workbench-pad-editor.mjs')
                paths.extend(prefix+'/'+name for name in ('workbench-drafts.mjs','workbench-draft-recovery.mjs'))
                paths = list(dict.fromkeys(paths))
                assets = {}
                for path in paths:
                    response = urllib.request.urlopen(origin + path)
                    raw = response.read()
                    assert response.status == 200 and len(raw) > 100, path
                    assets[path.rsplit("/", 1)[1]] = {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
                native_cad = None
                if '--native-cad' in sys.argv:
                    def api(path,body=None):
                        request=urllib.request.Request(origin+path,data=json.dumps(body).encode() if body is not None else None,
                                                       headers={'Content-Type':'application/json'})
                        return json.load(urllib.request.urlopen(request,timeout=150))
                    made=api('/api/workbench/projects',{'title':'Installed CAD import','spec':{'name':'installed_import','board':{'width_mm':40,'height_mm':30,'layers':2},'components':[],'nets':[]}})
                    pid=made['id'];endpoint=f'/api/workbench/projects/{pid}/mechanical'
                    assert api(endpoint+'/assets')['assets']==[]
                    original=(REPO/'tests/fixtures/mechanical-import/colored_assembly.step').read_bytes()
                    imported=api(endpoint+'/assets',{'name':'assembly.step','data':base64.b64encode(original).decode()})
                    assert imported['metrics']['solids']==3 and imported['metrics']['size_mm']==[31,21,6]
                    assert urllib.request.urlopen(origin+imported['original']['url']).read()==original
                    built=api(endpoint+'/assets/part',{'asset_id':imported['asset_id'],'path':'cad/installed.cad.json','name':'Installed native import'})
                    assert built['metrics']['solids']==3 and built['metrics']['step_metadata_verified']
                    assert [body['name'] for body in built['metrics']['bodies']]==['Blue bracket','Red spacer A','Red spacer B']
                    state=api('/api/projects/'+pid)['state']
                    assert state['workbench']['version']==1 and not state.get('workbench_native') and not any(state['runtime'].values())
                    native_cad={'passed':True,'original_sha256':hashlib.sha256(original).hexdigest(),'asset_id':imported['asset_id'],
                                'model_asset_id':built['asset_id'],'metrics':built['metrics'],'electrical_version':1,
                                'electrical_native_absent':True,'original_byte_exact':True}
                    mesh_bytes=(REPO/'tests/fixtures/mesh-import/assembly.glb').read_bytes()
                    mesh_asset=api(endpoint+'/assets',{'name':'assembly.glb','data':base64.b64encode(mesh_bytes).decode()})
                    assert mesh_asset['geometry_kind']=='triangle-mesh' and len(mesh_asset['bodies'])==2
                    mesh_part=api(endpoint+'/assets/part',{'asset_id':mesh_asset['asset_id'],'path':'cad/installed_mesh.cad.json','name':'Installed mesh'})
                    assert mesh_part['metrics']['solids']==2 and abs(mesh_part['metrics']['volume_mm3']-1680)<1e-3 and mesh_part['metrics']['geometry_provenance']=='faceted-mesh-input'
                    assert mesh_part['metrics']['step_face_colors_verified']
                    native_cad['mesh_import']={'passed':True,'original_sha256':hashlib.sha256(mesh_bytes).hexdigest(),'asset_id':mesh_asset['asset_id'],'model_asset_id':mesh_part['asset_id'],'volume_mm3':mesh_part['metrics']['volume_mm3'],'geometry_provenance':mesh_part['metrics']['geometry_provenance']}
                    drawing_bytes=(REPO/'tests/fixtures/drawing-import/rounded_plate.dxf').read_bytes()
                    drawing=api(endpoint+'/assets',{'name':'plate.dxf','data':base64.b64encode(drawing_bytes).decode()})
                    assert drawing['geometry_kind']=='planar-drawing' and drawing['bodies'][0]['holes']==2
                    extruded=api(endpoint+'/assets/extrude',{'asset_id':drawing['asset_id'],'path':'cad/installed_drawing.cad.json','thickness':3,'name':'Installed drawing'})
                    assert extruded['metrics']['solids']==1 and {'part.obj','part.3mf'}<={file['name'] for file in extruded['files']}
                    assert abs(extruded['metrics']['volume_mm3']-2794.3008881569226)<1e-5 and extruded['metrics']['step_face_colors_verified']
                    native_cad['drawing_import']={'passed':True,'asset_id':drawing['asset_id'],'model_asset_id':extruded['asset_id'],'volume_mm3':extruded['metrics']['volume_mm3'],'cutouts':2,'OBJ_3MF_present':True}
                    assembly={'schema':1,'units':'mm','name':'Installed assembly','parameters':{'gap':{'value':1,'unit':'mm'}},'features':[
                        {'id':'base','op':'component','source':{'kind':'model','path':'cad/installed_drawing.cad.json'}},
                        {'id':'top','op':'component','source':{'kind':'model','path':'cad/installed_drawing.cad.json'}},
                        {'id':'product','op':'assembly','members':['base','top'],'fixed':['base'],'clearance_mm':.5,'mates':[{'id':'height','type':'coincident','target':'top','reference':'base','target_anchor':{'kind':'plane','normal':[0,0,-1],'extreme':'max'},'reference_anchor':{'kind':'plane','normal':[0,0,1],'extreme':'max'},'offset':'gap'}]}],'result':'product'}
                    assembled=api(endpoint+'/build',{'path':'cad/installed_product.cad.json','program':assembly});fit=assembled['metrics']['assembly']['fit']
                    assert fit['complete'] and fit['pass'] and abs(fit['pairs'][0]['distance_mm']-1)<1e-6 and abs(fit['pairs'][0]['overlap_mm3'])<1e-6
                    native_cad['assembly']={'passed':True,'model_asset_id':assembled['asset_id'],'fit':fit,'installed_native_solver':True}
                    topology=api(endpoint+'/topology?source=cad/installed_product.cad.json&member_id=top&entity=face&limit=1')
                    assert topology['available'] and len(topology['elements'])==1 and topology['elements'][0]['selector']['body_instance']
                    native_cad['native_picking']={'passed':True,'model_asset_id':assembled['asset_id'],'scene_sha256':topology['scene_sha256'],'native_signature':topology['elements'][0]['selector']['reference']}
                    sketch_program=json.loads((REPO/'tests/fixtures/sketch/plate.cad.json').read_text())
                    sketch_part=api(endpoint+'/build',{'path':'cad/installed_sketch.cad.json','program':sketch_program})
                    assert sketch_part['metrics']['sketches']['profile']['dof']==0 and abs(sketch_part['metrics']['volume_mm3']-(600-4*3.141592653589793)*4)<1e-5
                    sketch_program['parameters']['width']['value']=40
                    draft=api(endpoint+'/sketch-preview',{'path':'cad/installed_sketch.cad.json','program':sketch_program,'feature_id':'profile','expected_sha256':sketch_part['source_sha256']})
                    assert draft['preview_only'] and draft['sketch']['dof']==0 and next(g for g in draft['sketch']['geometry'] if g['id']=='hole')['center'][0]==20
                    retained=api('/api/projects/'+pid)['state']['workbench_mechanical']['cad/installed_sketch.cad.json'];assert retained['asset_id']==sketch_part['asset_id']
                    native_cad['sketch']={'passed':True,'asset_id':sketch_part['asset_id'],'fully_constrained':True,'linked_native_extrusion':True,'unsaved_preview_no_publication':True}
                    material_source={'schema':1,'units':'mm','name':'Installed brass','parameters':{},'features':[{'id':'body','op':'box','size':[20,16,3],'material':{'preset':'brass','grade':'C260'}}],'result':'body'}
                    painted=api(endpoint+'/build',{'path':'cad/installed_material.cad.json','program':material_source});assert painted['metrics']['bodies'][0]['material']['preset']=='brass' and painted['metrics']['step_face_colors_verified'] and abs(painted['metrics']['volume_mm3']-960)<1e-6
                    native_cad['material']={'passed':True,'asset_id':painted['asset_id'],'grade':'C260','native_colors_verified':True,'geometry_unchanged':True}
                    curve_scene=api(sketch_part['scene_url']);curves=[edge['curvature'] for body in curve_scene['topology']['bodies'] for edge in body['edges']]
                    assert all(c['available'] and c['complete'] for c in curves)
                    assert any(abs(c['maximum']-.5)<1e-9 for c in curves) and any(c['maximum']==0 for c in curves)
                    native_cad['curvature']={'passed':True,'asset_id':sketch_part['asset_id'],'native_circle_curvature_per_mm':.5,'straight_curvature':0,'native_derivatives_not_mesh_estimates':True}
                    face_samples=[s for mesh in curve_scene['meshes'] for s in mesh['surface_samples'] if s is not None]
                    assert face_samples and any(abs(s['principal'][1]-.5)<1e-8 for s in face_samples)
                    assert all(len(s['normal'])==3 and len(s['principal'])==2 for s in face_samples)
                    native_cad['surface']={'passed':True,'asset_id':sketch_part['asset_id'],'oriented_inner_hole_curvature_per_mm':.5,'native_face_normals_and_principals':True}
                    events_program={'schema':1,'name':'Installed event profile','units':'mm','parameters':{},'features':[
                        {'id':'profile','op':'sketch','geometry':[{'id':'curve','type':'bspline','degree':3,'poles':[[0,0],[2,0],[4,2],[8,-2],[10,-2],[12,0]],'knots':[0,0,0,0,.5,.5,1,1,1,1]},
                            {'id':'right','type':'line','start':[12,0],'end':[12,-6]},{'id':'bottom','type':'line','start':[12,-6],'end':[0,-6]},{'id':'left','type':'line','start':[0,-6],'end':[0,0]}],'constraints':[]},
                        {'id':'body','op':'extrude_shape','target':'profile','vector':[0,0,2]}],'result':'body'}
                    events_part=api(endpoint+'/build',{'path':'cad/installed_events.cad.json','program':events_program});events_scene=api(events_part['scene_url']);events=[e for b in events_scene['topology']['bodies'] for edge in b['edges'] for e in edge['curve_events']['events']]
                    assert len([e for e in events if e['kind']=='inflection'])==2 and len([e for e in events if e['kind']=='curvature_jump'])==2
                    assert abs(events_part['metrics']['volume_mm3']-138)<1e-7 and events_part['metrics']['mass_properties']['volume_relative_error']<=1e-8
                    native_cad['curve_events']={'passed':True,'asset_id':events_part['asset_id'],'inflections':2,'internal_curvature_jumps':2,'native_polynomial_and_limit_analysis':True}
                    profiles=api('/api/workbench/interface-presets')['profiles'];assert len(profiles)==13
                    interface_spec=json.loads((REPO/'tests/fixtures/interface-presets.json').read_text())
                    interface_project=api('/api/workbench/projects',{'title':'Installed interface setup','spec':interface_spec})
                    interface=api('/api/workbench/projects/'+interface_project['id']+'/buses/prepare',{'action':'interface','ref':'J1','part_type':'USB C','base_version':1})
                    assert interface['native_parity']['ok'] and interface['interface_setup']['ready'] and interface['interface_setup']['matched_pins']==2
                    assert interface['spec']['components'][0]['pin_properties']['1']['impedance_ohms']==90
                    assert interface['spec']['nets']==interface_spec['nets'] and api('/api/projects/'+interface_project['id'])['state']['workbench']['version']==1
                    native_cad['interface_presets']={'passed':True,'profiles':13,'matched_pins':2,'native_parity':True,'explicit_unsaved_preview':True}
                    stack=api('/api/workbench/projects/'+interface_project['id']+'/stackup')
                    assert stack['inferred'] and len(stack['templates'])>=9
                    physical=api('/api/workbench/projects/'+interface_project['id']+'/stackup/prepare',{'base_version':1,'template':'jlc-3313'})
                    assert physical['native_parity']['ok'] and physical['stackup_report']['native_probe']['ok']
                    assert physical['spec']['board']['layers']==4 and abs(physical['spec']['board']['thickness_mm']-1.59468)<1e-6
                    assert api('/api/projects/'+interface_project['id'])['state']['workbench']['version']==1
                    native_cad['stackup']={'passed':True,'published_template':'jlc-3313','copper_count':4,'native_IPC_consumed':True,'explicit_unsaved_preview':True}
                    drilled={'name':'installed_hole','board':{'width_mm':30,'height_mm':22,'layers':2,'ground_pour':None},'components':[{'ref':'J1','value':'Slot','symbol':'Connector_Generic:Conn_01x02','footprint':'Project:Slot','placement':{'x_mm':15,'y_mm':11}}],'nets':[{'name':'SIG','pins':['J1.1']},{'name':'GND','pins':['J1.2']}],'library':{'footprints':{'Slot':{'name':'Slot','mount':'through_hole','pads':[{'name':'1','kind':'thru_hole','shape':'rect','x':-2,'y':0,'w':4,'h':3,'drill':.8,'drill_shape':'oval','drill_size':[.8,1.6],'drill_offset':[.3,-.2]},{'name':'2','kind':'smd','shape':'rect','x':4,'y':0,'w':1,'h':1,'drill':0}],'graphics':[]}}}}
                    hole_project=api('/api/workbench/projects',{'title':'Installed native slot','spec':drilled});api('/api/workbench/projects/'+hole_project['id']+'/native',{})
                    hole_geo=api('/api/workbench/projects/'+hole_project['id']+'/layout-geometry')['geometry'];pad=next(p for p in hole_geo['pads'] if p['name']=='1')
                    assert hole_geo['schema']>=8 and [pad['x'],pad['y']]==[113,111] and pad['drill_size']==[.8,1.6] and pad['drill_offset']==[.3,-.2]
                    native_cad['pad_holes']={'passed':True,'copper_center':[113,111],'drill_size':[.8,1.6],'relative_hole_offset':[.3,-.2],'geometry_schema':hole_geo['schema']}
                    custom=json.loads(json.dumps(drilled));p=custom['library']['footprints']['Slot']['pads'][0];p.update(kind='smd',drill=0)
                    for key in ('drill_shape','drill_size','drill_offset'):p.pop(key,None)
                    custom_project=api('/api/workbench/projects',{'title':'Installed SVG copper','spec':custom});endpoint='/api/workbench/projects/'+custom_project['id']
                    candidate=api(endpoint+'/library/pad-shape/prepare',{'base_version':1,'footprint':'Slot','pad_index':0,'custom_shape':{'path':'M-2 -2 L2 -2 L2 -1 L-1 -1 L-1 2 L-2 2 Z','units':'mm','tolerance_mm':.001}})
                    assert candidate['native_parity']['ok'] and candidate['shape_report']['native_probe']['ok'] and abs(candidate['shape_report']['area_mm2']-7)<1e-6
                    assert api('/api/projects/'+custom_project['id'])['state']['workbench']['version']==1
                    native_cad['custom_pads']={'passed':True,'profile_area_mm2':7,'retained_notch':True,'interior_anchor':candidate['shape_report']['anchor'],'native_plot_and_DRC':True,'unsaved_candidate':True}
                    instance=api('/api/workbench/projects/'+hole_project['id']+'/pads/prepare',{'base_version':1,'ref':'J1','pad_id':pad['id'],'patch':{'w':4.5,'mask_margin_mm':.1}})
                    assert instance['native_parity']['ok'] and instance['pad_report']['native_probe']['ok'] and instance['spec']['library']==drilled['library']
                    assert next(p for p in instance['geometry']['pads'] if p['id']==pad['id'])['w']==4.5
                    body={'base_version':1,'spec':instance['spec'],'native_source':instance['native_source']};req=urllib.request.Request(origin+'/api/workbench/projects/'+hole_project['id']+'/design',data=json.dumps(body).encode(),headers={'Content-Type':'application/json'},method='PUT')
                    assert json.load(urllib.request.urlopen(req))['version']==2
                    regenerated=api('/api/workbench/projects/'+hole_project['id']+'/native',{});saved=api('/api/workbench/projects/'+hole_project['id']+'/layout-geometry')['geometry']
                    assert regenerated['pad_instance_policy']=='native-pad-instances-v1' and next(p for p in saved['pads'] if p['id']==pad['id'])['w']==4.5
                    native_cad['layout_pad_instances']={'passed':True,'retained_native_UUID':pad['id'],'actual_native_width_mm':4.5,'shared_library_unchanged':True,'private_review_and_guarded_save':True}
                    zone_spec=json.loads(json.dumps(drilled));zone_spec['fixed_zones']=[{'net':'GND','origin':[100,100],'layers':['F.Cu'],'source':'(zone (net "GND") (net_name "GND") (layer "F.Cu") (uuid "66666666-6666-4666-8666-000000000777") (name "Installed ground") (hatch edge 0.5) (connect_pads (clearance 0.2)) (min_thickness 0.2) (fill yes (thermal_gap 0.3) (thermal_bridge_width 0.4)) (polygon (pts (xy 101 101) (xy 129 101) (xy 129 121) (xy 101 121))))'}]
                    zone_project=api('/api/workbench/projects',{'title':'Installed authored zone preservation','spec':zone_spec});endpoint='/api/workbench/projects/'+zone_project['id'];api(endpoint+'/native',{});zone_geo=api(endpoint+'/layout-geometry')['geometry'];zone_pad=next(p for p in zone_geo['pads'] if p['name']=='1');zone_draft=api(endpoint+'/pads/prepare',{'base_version':1,'ref':'J1','pad_id':zone_pad['id'],'patch':{'w':4.5}})
                    assert zone_draft['spec']['fixed_zones']==zone_spec['fixed_zones'] and zone_draft['pad_report']['native_probe']['ok']
                    native_cad['layout_pad_instances']['authored_zone_after_native_refill_preserved']=True


            finally:
                child.terminate()
                try:
                    child.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=5)
        receipt = {
            "passed": True, "wheel": str(wheel.relative_to(REPO)),
            "wheel_sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
            "required_package_members": REQUIRED, "imported_installed_copy": True,
            "isolated_empty_projects": True, "root_and_example_api": True,
            "versioned_assets": assets, "server_stopped_after_smoke": True,
            "native_cad":native_cad,
            "dependency_environment": "Existing virtualenv runtime dependencies; no clean dependency install."+(' Existing FreeCAD exercised for native CAD import/build.' if native_cad else ' No native engineering run.'),
            "source_copy_build": "Temporary directory; shared checkout/build tree untouched.",
        }
        (output / "acceptance.json").write_text(json.dumps(receipt, indent=2) + "\n")
        print(json.dumps({"passed": True, "receipt": str((output / "acceptance.json").relative_to(REPO))}))


if __name__ == "__main__":
    main()
