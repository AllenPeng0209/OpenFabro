import copy,json
from pathlib import Path
import pytest
from wholeboard import server,sexpr,workbench_native
from wholeboard.kicad import board,geometry
from test_selective_routing import fixture
from test_workbench import client

def test_native_geometry_distinguishes_track_and_via_keepout_rules(tmp_path):
    pcb=Path(board.build(fixture('selective-routing-repair'),tmp_path)['pcb']);geo=geometry.read(pcb);keepout=next(z for z in geo['zone_definitions'] if z['keepout'])
    assert keepout.get('keepout_rules')=={'tracks':'allowed','vias':'not_allowed','pads':'allowed','copperpour':'allowed','footprints':'allowed'}


def test_no_net_keepout_roundtrips_through_browser_copper_adoption(tmp_path):
    spec=fixture('selective-routing-repair');pcb=Path(board.build(spec,tmp_path/'before')['pcb']);geo=geometry.read(pcb)
    assert geo['zone_sources'][0]['net']=='','Native net-code zero is not a literal electrical net name'
    restored=copy.deepcopy(spec);restored['fixed_zones']=geo['zone_sources'];board.build(restored,tmp_path/'after')


def test_a_quoted_literal_zero_net_remains_an_electrical_net_name(tmp_path):
    spec=fixture('selective-routing');spec['nets'][0]['name']='0';pcb=Path(board.build(spec,tmp_path)['pcb']);pads=geometry.read(pcb)['pads']
    assert sum(p['net']=='0' for p in pads)==2

def test_geometry_upgrade_preserves_older_board_schematic_and_geometry_bytes_and_mtimes(client,monkeypatch):
    spec=fixture('selective-routing-repair');pid=client.post('/api/workbench/projects',json={'title':'Interactive keepout migration','spec':spec}).json()['id'];p=server.mgr().get(pid)
    with monkeypatch.context() as old:old.setattr(geometry,'SCHEMA',5);native=workbench_native.generate(p)
    path=Path(native['geometry_file']);data=json.loads(path.read_text())
    for zone in data['zone_definitions']:zone.pop('keepout_rules',None)
    path.write_text(json.dumps(data));p.state['workbench_native']['geometry_schema']=5;p.save();source=copy.deepcopy(p.state['spec']);frozen={f:(f.read_bytes(),f.stat().st_mtime_ns) for f in path.parent.rglob('*') if f.is_file()}
    result=workbench_native.generate(p);assert result['geometry_schema']>5 and result['geometry_file']!=str(path) and result['pcb']==native['pcb'] and result['sch']==native['sch']
    actual=json.loads(Path(result['geometry_file']).read_text());assert next(z for z in actual['zone_definitions'] if z['keepout'])['keepout_rules']['tracks']=='allowed'
    assert all((f.read_bytes(),f.stat().st_mtime_ns)==v for f,v in frozen.items());assert p.state['spec']==source and p.state['workbench']['version']==1
