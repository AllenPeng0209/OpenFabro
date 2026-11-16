"""Project-owned library assets must work natively without global-library mutation."""
from pathlib import Path
import json
import io
import zipfile

import pytest
from fastapi.testclient import TestClient

from wholeboard import config, design, enclosure, project, project_library, server, sim
from wholeboard.kicad import board, cli, geometry, libs, schematic


def custom_spec(spacing=4):
    return {
        "name":"custom_library_board", "board":{"width_mm":30,"height_mm":22,"layers":2},
        "components":[{"ref":"U1","value":"Custom part","symbol":"Project:Demo","footprint":"Project:DemoFP","placement":{"x_mm":15,"y_mm":11,"rotation":0}}],
        "nets":[{"name":"SIGNAL","pins":["U1.1"]},{"name":"GND","pins":["U1.2"]}],
        "library":{
            "symbols":{"Demo":{"name":"Demo","reference":"U","description":"Project symbol","footprint":"Project:DemoFP",
                "graphics":[{"kind":"rectangle","start":[-2.54,2.54],"end":[2.54,-2.54],"fill":"background"}],
                "pins":[{"number":"1","name":"IN","x":-5.08,"y":0,"angle":0,"length":2.54,"type":"input","unit":1},
                        {"number":"2","name":"GND","x":5.08,"y":0,"angle":180,"length":2.54,"type":"power_in","unit":1}]}},
            "footprints":{"DemoFP":{"name":"DemoFP","description":"Project footprint","mount":"smd","height_mm":2,
                "pads":[{"name":"1","x":-spacing/2,"y":0,"w":1,"h":1.5,"angle":0,"kind":"smd","shape":"roundrect","drill":0,"layer":"F.Cu"},
                        {"name":"2","x":spacing/2,"y":0,"w":1,"h":1.5,"angle":0,"kind":"smd","shape":"roundrect","drill":0,"layer":"F.Cu"}],
                "graphics":[{"kind":"rectangle","start":[-1,-1],"end":[1,1],"layer":"F.SilkS"}],"courtyard":[-4,-2,4,2]}},
            "parts":{}
        }
    }


def test_project_symbol_and_footprint_generate_real_native_designs(tmp_path):
    spec=custom_spec()
    report=design.validate(spec)
    assert report.ok, report.errors
    output=board.build(spec,tmp_path)
    scene=geometry.read(Path(output["pcb"]))
    assert {p["name"] for p in scene["pads"]}=={"1","2"}
    assert {p["net"] for p in scene["pads"]}=={"SIGNAL","GND"}
    sch=schematic.build(spec,tmp_path)
    assert 'Project:Demo' in Path(sch["sch"]).read_text()
    assert (tmp_path/'library/Project.pretty/DemoFP.kicad_mod').is_file()
    assert (tmp_path/'library/Project.kicad_sym').is_file()
    assert (tmp_path/'fp-lib-table').is_file()
    assert (tmp_path/'sym-lib-table').is_file()


def test_projects_with_identical_asset_ids_do_not_share_mutable_library_state():
    a,b=custom_spec(4),custom_spec(6)
    first=libs.load_footprint('Project:DemoFP',a)
    second=libs.load_footprint('Project:DemoFP',b)
    assert first.pads[0].x==-2
    assert second.pads[0].x==-3
    assert libs.load_footprint('Project:DemoFP') is None
    assert schematic.symbol_info('Project:Demo',a)['pins'][0]['name']=='IN'


def test_engineering_validation_rejects_a_custom_symbol_missing_a_connected_pin():
    spec=custom_spec();spec['library']['symbols']['Demo']['pins'].pop(0)
    report=design.validate(spec)
    assert not report.ok
    assert any('connected pin/pad 1' in error for error in report.errors)


def test_project_footprint_height_reaches_mechanical_clearance_context(tmp_path):
    spec=custom_spec();spec['library']['footprints']['DemoFP']['height_mm']=7.3
    normalized=design.normalise(spec)
    pcb=board.build(normalized,tmp_path)
    context=enclosure.context(geometry.read(Path(pcb['pcb'])),normalized)
    assert context['parts'][0]['height_mm']==7.3
    assert context['parts'][0]['height_estimated'] is False
    assert context['parts'][0]['height_source']=='project-library'
    spec['components'][0]['height_mm']=4
    override=design.normalise(spec)
    assert enclosure.context(geometry.read(Path(pcb['pcb'])),override)['parts'][0]['height_mm']==4


def test_custom_symbols_are_read_by_real_kicad_and_simulation(tmp_path):
    spec=custom_spec()
    sch=schematic.build(spec,tmp_path)
    if not cli.find_kicad_cli():
        pytest.skip('KiCad CLI is required for native library acceptance')
    parity=schematic.netlist_parity(spec,cli.schematic_nets(Path(sch['sch'])))
    assert parity['ok'], parity
    assert sim.Netlist(spec).symbol_pins('Project:Demo')[0]['name']=='IN'
    spec['library']['symbols']['Demo']['pins'][0]['name']='CHANGED'
    assert sim.Netlist(spec).symbol_pins('Project:Demo')[0]['name']=='CHANGED'


def test_installed_assets_can_be_copied_without_losing_pins_and_pads():
    assert hasattr(project_library,'copy_installed'),'Copying real installed library assets is missing'
    symbol=project_library.copy_installed('symbols','Device:R')
    footprint=project_library.copy_installed('footprints','Resistor_SMD:R_0603_1608Metric')
    assert {pin['number'] for pin in symbol['pins']}=={'1','2'}
    assert [pad['name'] for pad in footprint['pads']]==['1','2']
    assert footprint['pads'][0]['x']==-.825
    assert footprint['pads'][0]['w']==.8
    assert footprint['source_lib_id']=='Resistor_SMD:R_0603_1608Metric'
    project_library.validate_asset('symbols','Resistor',symbol)
    project_library.validate_asset('footprints','Resistor',footprint)


def test_native_library_import_preserves_geometry_and_drops_external_model_paths(tmp_path):
    assert hasattr(project_library,'import_native'),'Importing native KiCad library files is missing'
    spec=custom_spec();project_library.export(spec,tmp_path)
    symbol=project_library.import_native('symbols',(tmp_path/'library/Project.kicad_sym').read_text())['Demo']
    footprint_text=(tmp_path/'library/Project.pretty/DemoFP.kicad_mod').read_text().rstrip()
    footprint_text=footprint_text[:-1]+' (model "/private/not-portable.step" (offset (xyz 0 0 0))))'
    footprint=project_library.import_native('footprints',footprint_text)['DemoFP']
    assert symbol['pins'][0]['name']=='IN'
    assert symbol['pins'][0]['x']==-5.08
    assert footprint['pads'][0]['x']==-2
    assert footprint['pads'][0]['shape']=='roundrect'
    assert '/private/not-portable' not in json.dumps(footprint)


def test_library_identifiers_cannot_escape_installed_library_folders(tmp_path,monkeypatch):
    installed=tmp_path/'installed';installed.mkdir()
    private=tmp_path/'private.pretty';private.mkdir()
    (private/'Leak.kicad_mod').write_text('(footprint "Leak" (layer "F.Cu") (pad "1" smd rect (at 0 0) (size 1 1) (layers "F.Cu" "F.Mask")))')
    (tmp_path/'private.kicad_sym').write_text('(kicad_symbol_lib (symbol "Leak" (symbol "Leak_0_1" (rectangle (start 0 0) (end 1 1)))))')
    monkeypatch.setattr(libs,'locate',lambda *_:installed)
    assert libs.load_footprint('../private:Leak') is None
    assert schematic.load_symbol('../private:Leak') is None


@pytest.fixture
def library_client(tmp_path,monkeypatch):
    monkeypatch.setattr(config,'APP_DIR',tmp_path)
    monkeypatch.setattr(config,'CONFIG_FILE',tmp_path/'config.json')
    config.update({'projects_dir':str(tmp_path/'projects')})
    monkeypatch.setattr(server,'manager',project.Manager())
    return TestClient(server.app)


def test_project_library_info_and_portable_download(library_client):
    response=library_client.post('/api/workbench/projects',json={'title':'Custom library','spec':custom_spec()})
    assert response.status_code==201
    pid=response.json()['id']
    path=f'/api/workbench/projects/{pid}/library'
    info=library_client.get(path+'/symbol-info',params={'id':'Project:Demo'})
    assert info.status_code==200
    assert info.json()['pins'][0]['name']=='IN'
    footprint=library_client.get(path+'/footprint-info',params={'id':'Project:DemoFP'})
    assert footprint.status_code==200
    assert footprint.json()['pads']==['1','2']
    archive=library_client.get(path+'/export')
    assert archive.status_code==200
    with zipfile.ZipFile(io.BytesIO(archive.content)) as bundle:
        assert set(bundle.namelist())=={'library/Project.pretty/DemoFP.kicad_mod','library/Project.kicad_sym','fp-lib-table','sym-lib-table','library.json'}
        assert 'Project.kicad_sym' in bundle.read('sym-lib-table').decode()
    for kind in ('symbol-info','footprint-info'):
        bad=library_client.get(path+'/'+kind,params={'id':'../Device:../../private'})
        assert bad.status_code==422


def test_library_copy_and_native_import_are_reviewable_without_mutating_design(library_client,tmp_path):
    created=library_client.post('/api/workbench/projects',json={'spec':custom_spec()}).json()
    path=f"/api/workbench/projects/{created['id']}/library"
    copied=library_client.post(path+'/copy',json={'kind':'symbols','id':'Device:R'})
    assert copied.status_code==200
    assert {p['number'] for p in copied.json()['asset']['pins']}=={'1','2'}
    project_library.export(custom_spec(),tmp_path)
    imported=library_client.post(path+'/import-native',json={'kind':'footprints','content':(tmp_path/'library/Project.pretty/DemoFP.kicad_mod').read_text()})
    assert imported.status_code==200
    assert imported.json()['assets']['DemoFP']['pads'][0]['x']==-2
    assert server.mgr().get(created['id']).state['workbench']['version']==1


@pytest.mark.parametrize('mutation',['library_type','invalid_graphic_unit','pad_size','circle_pad','part_reference','missing_asset','connected_pin','connected_pad'])
def test_invalid_library_edit_cannot_replace_a_saved_connected_design(library_client,mutation):
    spec=custom_spec()
    response=library_client.post('/api/workbench/projects',json={'spec':spec})
    assert response.status_code==201
    pid=response.json()['id']
    if mutation=='library_type':spec['library']=[]
    elif mutation=='invalid_graphic_unit':spec['library']['symbols']['Demo']['graphics'][0]['unit']='wrong'
    elif mutation=='pad_size':spec['library']['footprints']['DemoFP']['pads'][0]['w']=-1
    elif mutation=='circle_pad':spec['library']['footprints']['DemoFP']['pads'][0]['shape']='circle'
    elif mutation=='part_reference':spec['library']['parts']['BadPart']={'reference':'u1','symbol':'Project:Demo','footprint':'Project:DemoFP'}
    elif mutation=='missing_asset':del spec['library']['symbols']['Demo']
    elif mutation=='connected_pin':spec['library']['symbols']['Demo']['pins'].pop(0)
    elif mutation=='connected_pad':spec['library']['footprints']['DemoFP']['pads'].pop(0)
    changed=library_client.put(f'/api/workbench/projects/{pid}/design',json={'base_version':1,'spec':spec})
    assert changed.status_code==422, changed.text
    assert server.mgr().get(pid).state['workbench']['version']==1
    assert server.mgr().get(pid).state['spec']['library']['symbols']['Demo']['pins'][0]['number']=='1'
