"""The editable pad center and drilled hole must agree with real KiCad exports."""
import copy
import math
from pathlib import Path

import pytest
from test_project_library import custom_spec
from wholeboard import project_library,sexpr
from wholeboard.kicad import board,cli,geometry,libs
from wholeboard import server,workbench_native
from test_workbench import client


def slotted_spec():
    spec=custom_spec();asset=spec['library']['footprints']['DemoFP'];asset['mount']='through_hole'
    asset['pads'][0].update(kind='thru_hole',shape='rect',w=4,h=3,drill=.8,
        drill_shape='oval',drill_size=[.8,1.6],drill_offset=[.3,-.2])
    return spec


def native_offset_board(tmp_path,angle=0,side='top'):
    spec=custom_spec();spec['components'][0]['placement'].update(rotation=angle,side=side)
    path=Path(board.build(spec,tmp_path)['pcb']);tree=sexpr.parse(path.read_text());fp=sexpr.find(tree,'footprint');pad=sexpr.find(fp,'pad');pad[2]=sexpr.Sym('thru_hole')
    sexpr.find(pad,'size')[1:]=[sexpr.fmt(4),sexpr.fmt(4)]
    sexpr.find(pad,'layers')[1:]=['*.Cu','*.Mask']
    pad.append([sexpr.Sym('drill'),sexpr.Sym('oval'),sexpr.fmt(.8),sexpr.fmt(2),sexpr.S(sexpr.Sym('offset'),.6,-.2)])
    path.write_text(sexpr.dumps(tree));return path


@pytest.mark.parametrize('angle',[0,90,37])
@pytest.mark.parametrize('side',['top','bottom'])
def test_native_offset_copper_center_matches_actual_gerber_and_excellon(tmp_path,angle,side):
    path=native_offset_board(tmp_path,angle,side);gerbers=tmp_path/'gerber'
    result=cli.run(['pcb','export','gerbers','-l','F.Cu','-o',str(gerbers)+'/',str(path)]);assert result.returncode==0,result.stderr
    plot=next(gerbers.glob('*.gtl')).read_text();assert '%FSLAX46Y46*%' in plot and '%MOMM*%' in plot
    import re
    flash=re.search(r'%TO.P,U1,1\*%[\s\S]*?X([-\d]+)Y([-\d]+)D03',plot)
    assert flash,'Native Gerber must identify the first pad flash'
    pad=next(p for p in geometry.read(path)['pads'] if p['name']=='1')
    assert [pad['x'],pad['y']]==pytest.approx([int(flash[1])/1e6,-int(flash[2])/1e6],abs=.0001)
    assert pad['drill_offset']==pytest.approx([-.6,.2])
    a=math.radians(pad['rot']);u,v=pad['drill_offset'];hole=[pad['x']+u*math.cos(a)+v*math.sin(a),pad['y']-u*math.sin(a)+v*math.cos(a)]
    output=tmp_path/'drill';result=cli.run(['pcb','export','drill','--format','excellon','--excellon-units','mm','--excellon-zeros-format','decimal','-o',str(output)+'/',str(path)]);assert result.returncode==0,result.stderr
    record=next(line for p in output.glob('*.drl') for line in p.read_text().splitlines() if 'G85' in line)
    endpoints=[float(v) for v in re.match(r'X([-\d.]+)Y([-\d.]+)G85X([-\d.]+)Y([-\d.]+)',record).groups()]
    assert hole==pytest.approx([(endpoints[0]+endpoints[2])/2,-(endpoints[1]+endpoints[3])/2],abs=.0006)


def test_slotted_pad_native_import_export_preserves_copper_center_and_hole(tmp_path):
    spec=slotted_spec();asset=spec['library']['footprints']['DemoFP'];node=project_library.footprint_node(spec,'Project:DemoFP')
    first=sexpr.find(node,'pad');drill=sexpr.find(first,'drill')
    assert str(drill[1])=='oval' and [sexpr.num(v) for v in drill[2:4]]==[.8,1.6]
    assert [sexpr.num(v) for v in sexpr.find(drill,'offset')[1:]]==pytest.approx([-.3,.2])
    actual=project_library.import_native('footprints',sexpr.dumps(node))['DemoFP']['pads'][0]
    for key in ('x','y','w','h','angle','drill','drill_size','drill_offset','drill_shape'):assert actual[key]==asset['pads'][0][key]
    output=board.build(spec,tmp_path);pad=next(p for p in geometry.read(Path(output['pcb']))['pads'] if p['name']=='1')
    assert [pad['x'],pad['y']]==pytest.approx([113,111]) and pad['drill_size']==[.8,1.6]
    assert pad['drill_offset']==pytest.approx([.3,-.2])
    parsed=libs.load_footprint('Project:DemoFP',spec).pads[0]
    assert [parsed.x,parsed.y]==pytest.approx([-2,0]) and parsed.drill==.8


@pytest.mark.parametrize('patch',[
    {'drill_shape':'square'},{'drill_size':[0,1.6]},{'drill_size':[True,1.6]},
    {'drill_size':[.8]},{'drill_size':[.8,math.inf]}, {'drill_size':[.7,1.6]},
    {'drill_offset':[4,0]}, {'drill_offset':[0,0,1]}, {'drill_offset':[float('nan'),0]},
    {'drill_shape':'circle','drill_size':[.8,1.6]},
])
def test_unsafe_or_ambiguous_drilled_pad_fields_are_rejected(patch):
    asset=copy.deepcopy(slotted_spec()['library']['footprints']['DemoFP']);asset['pads'][0].update(patch)
    with pytest.raises(ValueError):project_library.validate_asset('footprints','DemoFP',asset)


def test_offset_geometry_upgrade_preserves_all_existing_native_files(client,monkeypatch):
    spec=slotted_spec();pid=client.post('/api/workbench/projects',json={'title':'Hole geometry cache','spec':spec}).json()['id'];p=server.mgr().get(pid)
    with monkeypatch.context() as old:old.setattr(geometry,'SCHEMA',7);native=workbench_native.generate(p)
    path=Path(native['geometry_file']);frozen={f:(f.read_bytes(),f.stat().st_mtime_ns) for f in path.parent.rglob('*') if f.is_file()}
    upgraded=workbench_native.generate(p);assert upgraded['pcb']==native['pcb'] and upgraded['geometry_schema']>=8 and upgraded['geometry_file']!=str(path)
    assert all((f.read_bytes(),f.stat().st_mtime_ns)==value for f,value in frozen.items())
    assert p.state['workbench']['version']==1 and p.state['spec']==spec


def test_declared_project_holes_are_not_silently_widened_to_a_fab_default(tmp_path):
    spec=slotted_spec();pad=spec['library']['footprints']['DemoFP']['pads'][0]
    pad.update(drill=.2,drill_shape='circle',drill_size=[.2,.2],drill_offset=[0,0])
    path=Path(board.build(spec,tmp_path)['pcb']);actual=next(p for p in geometry.read(path)['pads'] if p['name']=='1')
    assert actual['drill']==.2,'Keep the declared hole; native DRC should report process incompatibility instead of changing it.'


def test_legacy_widened_project_hole_cache_is_rebuilt_without_replacing_originals(client):
    spec=slotted_spec();pad=spec['library']['footprints']['DemoFP']['pads'][0];pad.update(drill=.2,drill_shape='circle',drill_size=[.2,.2],drill_offset=[0,0])
    pid=client.post('/api/workbench/projects',json={'title':'Legacy widened project pad','spec':spec}).json()['id'];p=server.mgr().get(pid);native=workbench_native.generate(p);pcb=Path(native['pcb']);tree=sexpr.parse(pcb.read_text());sexpr.find(sexpr.find(sexpr.find(tree,'footprint'),'pad'),'drill')[1]=sexpr.fmt(.3);pcb.write_text(sexpr.dumps(tree));p.state['workbench_native'].pop('project_hole_policy');p.save()
    before={f:(f.read_bytes(),f.stat().st_mtime_ns) for f in pcb.parent.rglob('*') if f.is_file()};rebuilt=workbench_native.generate(p)
    assert rebuilt['pcb']!=native['pcb'] and rebuilt['project_hole_policy']==workbench_native.PROJECT_HOLE_POLICY
    assert next(p for p in geometry.read(Path(rebuilt['pcb']))['pads'] if p['name']=='1')['drill']==.2
    assert all((f.read_bytes(),f.stat().st_mtime_ns)==value for f,value in before.items())


def test_agent_read_of_legacy_offset_geometry_marks_the_old_convention(client):
    import json
    from wholeboard import codex_bridge
    spec=slotted_spec();pid=client.post('/api/workbench/projects',json={'title':'Old offset evidence','spec':spec}).json()['id'];p=server.mgr().get(pid);native=workbench_native.generate(p);value=json.loads(Path(native['geometry_file']).read_text());value['schema']=7;value['pads'][0]['drill_offset']=[.6,-.2];path=Path(native['pcb']).parent/'geometry-v7-111111111111.json';path.write_text(json.dumps(value))
    result=codex_bridge.execute_tool(p,'read_file',{'path':str(path.relative_to(p.root)),'limit':20000},'chat')
    assert 'copper' in result['native_geometry']['legacy_offset_warning']
