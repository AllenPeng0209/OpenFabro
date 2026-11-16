"""Custom copper must keep SVG voids and use a real native pad anchor inside copper."""
import copy,json,math
from pathlib import Path
import pytest
from shapely.geometry import Point,Polygon
from shapely import union_all
from wholeboard import project_library,server,sexpr
from wholeboard.kicad import board,cli,geometry,connectivity
from test_project_library import custom_spec
from test_workbench import client

L_PATH='M -2 -2 L 2 -2 L 2 -1 L -1 -1 L -1 2 L -2 2 Z'


def fixture():
    spec=custom_spec();pad=spec['library']['footprints']['DemoFP']['pads'][0]
    pad.update(shape='custom',w=4,h=4,custom_shape={'path':L_PATH,'units':'mm','tolerance_mm':.001})
    return spec


def copper(pad):return union_all([Polygon(points) for points in pad['copper_polygons']])


def test_custom_svg_notch_is_real_native_copper_with_an_interior_routing_anchor(tmp_path):
    spec=fixture();pcb=Path(board.build(spec,tmp_path)['pcb']);pad=next(p for p in geometry.read(pcb)['pads'] if p['name']=='1')
    shape=copper(pad);assert shape.area==pytest.approx(7,abs=1e-6)
    assert not shape.covers(Point(0,0)) and shape.covers(Point(-1.5,0))
    assert [pad['x'],pad['y']]==pytest.approx([113,111])
    anchor=pad['routing_anchor'];assert shape.covers(Point(anchor[0]-pad['x'],anchor[1]-pad['y']))
    assert sexpr.find(sexpr.find(sexpr.find(sexpr.parse(pcb.read_text()),'footprint'),'pad'),'primitives')


def test_external_native_edits_are_not_replaced_by_stale_svg_metadata(tmp_path):
    spec=fixture();node=project_library.footprint_node(spec,'Project:DemoFP');pad=sexpr.find(node,'pad')
    for primitive in sexpr.find(pad,'primitives')[1:]:
        for point in sexpr.find(primitive,'pts')[1:]:
            if abs(sexpr.num(point[1])+.5)<1e-7:point[1]=sexpr.fmt(sexpr.num(point[1])+.0005)
    from wholeboard import pad_shapes
    expected=union_all([Polygon(p) for p in pad_shapes.native_geometry(pad)['polygons']]);restored=project_library.import_native('footprints',sexpr.dumps(node))['DemoFP'];spec['library']['footprints']['DemoFP']=restored
    pcb=Path(board.build(spec,tmp_path)['pcb']);actual=copper(next(p for p in geometry.read(pcb)['pads'] if p['name']=='1'))
    assert expected.symmetric_difference(actual).area<1e-5,'Native edits take precedence over stale embedded SVG source'


def test_svg_evenodd_hole_survives_actual_native_export_and_portable_import(tmp_path):
    spec=fixture();pad=spec['library']['footprints']['DemoFP']['pads'][0]
    pad['custom_shape']={'svg':'<svg xmlns="http://www.w3.org/2000/svg"><path fill-rule="evenodd" d="M2 0 A2 2 0 1 0 -2 0 A2 2 0 1 0 2 0 Z M1 0 A1 1 0 1 0 -1 0 A1 1 0 1 0 1 0 Z"/></svg>','units':'mm','tolerance_mm':.0001}
    pcb=Path(board.build(spec,tmp_path)['pcb']);native=next(p for p in geometry.read(pcb)['pads'] if p['name']=='1');shape=copper(native)
    assert shape.area==pytest.approx(3*math.pi,abs=.005) and not shape.covers(Point(0,0)) and shape.covers(Point(1.5,0))
    text=sexpr.dumps(project_library.footprint_node(spec,'Project:DemoFP'));restored=project_library.import_native('footprints',text)['DemoFP']
    spec['library']['footprints']['DemoFP']=restored;roundtrip=Path(board.build(spec,tmp_path/'again')['pcb']);again=copper(next(p for p in geometry.read(roundtrip)['pads'] if p['name']=='1'))
    assert shape.symmetric_difference(again).area<1e-5
    exported=project_library.export(spec,tmp_path/'portable');assert any(p.name=='Project.library.json' for p in exported),'The editable custom source/declared approximation must travel with the native library'


def test_shape_preview_declares_units_and_never_saves_the_project(client):
    spec=custom_spec();pid=client.post('/api/workbench/projects',json={'title':'Private SVG pad','spec':spec}).json()['id']
    response=client.post(f'/api/workbench/projects/{pid}/library/pad-shape/prepare',json={'base_version':1,'footprint':'DemoFP','pad_index':0,'custom_shape':{'path':'M -.002 -.001 H .002 V .001 H -.002 Z','units':'m','tolerance_mm':.001}})
    assert response.status_code==200,response.text
    result=response.json();pad=result['spec']['library']['footprints']['DemoFP']['pads'][0]
    assert pad['w']==4 and pad['h']==2 and result['shape_report']['area_mm2']==pytest.approx(8)
    assert result['native_parity']['ok'] and result['native_source'] and result['shape_report']['native_probe']['ok']
    assert server.mgr().get(pid).state['workbench']['version']==1 and server.mgr().get(pid).state['spec']==spec


def test_native_drc_and_connectivity_do_not_bridge_the_notch(tmp_path):
    spec=fixture();spec['nets']=[{'name':'SIGNAL','pins':['U1.1','U1.2']}]
    for label,end,expected in [('copper',[11.5,11],0),('void',[13,11],1)]:
        pcb=Path(board.build(spec,tmp_path/label)['pcb']);tree=sexpr.parse(pcb.read_text());tree.append([sexpr.Sym('segment'),sexpr.S(sexpr.Sym('start'),117,111),sexpr.S(sexpr.Sym('end'),100+end[0],100+end[1]),sexpr.S(sexpr.Sym('width'),.2),sexpr.S(sexpr.Sym('layer'),'F.Cu'),sexpr.S(sexpr.Sym('net'),'SIGNAL'),sexpr.S(sexpr.Sym('uuid'),'11111111-1111-4111-8111-000000000001')]);pcb.write_text(sexpr.dumps(tree))
        native=cli.drc(pcb,refill=False,save=False);assert native['unconnected']==expected
        assert len(connectivity.airwires(geometry.read(pcb)))==expected


@pytest.mark.parametrize('custom',[False,True])
def test_edge_connector_pad_is_single_sided_with_no_drill_or_paste(tmp_path,custom):
    spec=fixture() if custom else custom_spec();spec['library']['footprints']['DemoFP']['pads'][0]['kind']='connect'
    pcb=Path(board.build(spec,tmp_path)['pcb']);pad=next(p for p in geometry.read(pcb)['pads'] if p['name']=='1')
    assert pad['kind']=='connect' and pad['drill']==0 and pad['layers']==['F.Cu','F.Mask']


@pytest.mark.parametrize('shape',[
    {'path':'M0 0 L1 1','units':'unknown'},
    {'path':'M0 0 L1 1','units':'mm','tolerance_mm':True},
    {'path':'M0 0 L1 1','units':'mm','tolerance_mm':float('nan')},
    {'svg':'<svg xmlns="http://www.w3.org/2000/svg"><image href="https://example.invalid/pad.png"/></svg>','units':'mm'},
    {'svg':'<!DOCTYPE svg [<!ENTITY x "bad">]><svg xmlns="http://www.w3.org/2000/svg"><path d="&x;"/></svg>','units':'mm'},
    {'path':'M0 0 Z','units':'mm'},
])
def test_invalid_or_external_custom_sources_are_rejected(shape):
    spec=fixture();asset=spec['library']['footprints']['DemoFP'];asset['pads'][0]['custom_shape']=shape
    with pytest.raises(ValueError):project_library.validate_asset('footprints','DemoFP',asset)


def test_cubic_profile_retains_analytic_area_and_true_bounds(tmp_path):
    spec=fixture();pad=spec['library']['footprints']['DemoFP']['pads'][0];pad.update(w=3,h=1.75,custom_shape={'path':'M0 0 C1 1 2 1 3 0 L3 -1 L0 -1 Z','units':'mm','tolerance_mm':.00001})
    pcb=Path(board.build(spec,tmp_path)['pcb']);actual=next(p for p in geometry.read(pcb)['pads'] if p['name']=='1')
    assert actual['w']==3 and actual['h']==1.75 and copper(actual).area==pytest.approx(4.5,abs=.0002)


def test_dxf_cad_y_up_is_converted_to_board_y_down(tmp_path):
    import ezdxf,io
    doc=ezdxf.new();doc.units=4;doc.modelspace().add_lwpolyline([(-2,-2),(2,-2),(2,-1),(-1,-1),(-1,2),(-2,2)],close=True);stream=io.StringIO();doc.write(stream)
    spec=fixture();spec['library']['footprints']['DemoFP']['pads'][0]['custom_shape']={'dxf':stream.getvalue(),'units':'mm','tolerance_mm':.001}
    pcb=Path(board.build(spec,tmp_path)['pcb']);shape=copper(next(p for p in geometry.read(pcb)['pads'] if p['name']=='1'))
    assert shape.area==pytest.approx(7) and shape.covers(Point(0,1.5)) and not shape.covers(Point(0,-1.5))


def test_disconnected_and_unknown_winding_are_not_silently_changed():
    from wholeboard import pad_shapes
    for shape in ({'path':'M0 0 H1 V1 H0 Z M3 0 H4 V1 H3 Z','units':'mm'}, {'path':L_PATH,'units':'mm','fill_rule':'unsupported'}):
        with pytest.raises(ValueError):pad_shapes.compile_shape(shape)


def test_old_native_digest_cannot_apply_a_reviewed_shape(client):
    spec=custom_spec();pid=client.post('/api/workbench/projects',json={'title':'Custom source guard','spec':spec}).json()['id'];p=server.mgr().get(pid)
    args={'base_version':1,'footprint':'DemoFP','pad_index':0,'custom_shape':{'path':L_PATH,'units':'mm'}};review=client.post(f'/api/workbench/projects/{pid}/library/pad-shape/prepare',json=args).json();pcb=Path(p.state['workbench_native']['pcb']);pcb.write_text(pcb.read_text()+'\n')
    response=client.put(f'/api/workbench/projects/{pid}/design',json={'base_version':1,'spec':review['spec'],'native_source':review['native_source']})
    assert response.status_code==409 and p.state['workbench']['version']==1


def test_readonly_shape_snapshot_never_reports_another_saved_version(client,monkeypatch):
    import concurrent.futures,threading
    from wholeboard import pad_shapes
    spec=fixture();pid=client.post('/api/workbench/projects',json={'title':'Shape snapshot race','spec':spec}).json()['id'];entered=threading.Event();release=threading.Event();first=[True];real=pad_shapes.compile_shape
    def hold(*args,**kwargs):
        if first[0]:first[0]=False;entered.set();assert release.wait(10)
        return real(*args,**kwargs)
    monkeypatch.setattr(pad_shapes,'compile_shape',hold)
    with concurrent.futures.ThreadPoolExecutor() as pool:
        task=pool.submit(client.get,f'/api/workbench/projects/{pid}/library/footprints/DemoFP/pads/0/shape');assert entered.wait(5)
        changed=copy.deepcopy(spec);changed['summary']='Peer save';assert client.put(f'/api/workbench/projects/{pid}/design',json={'base_version':1,'spec':changed}).status_code==200;release.set();response=task.result(10)
    assert response.status_code==409,'A compiled old pad must not be labeled with the newer design version'


def test_agent_custom_pad_tool_shares_preview_and_guarded_apply(client):
    from wholeboard import codex_bridge
    spec=custom_spec();pid=client.post('/api/workbench/projects',json={'title':'Agent native shape','spec':spec}).json()['id'];p=server.mgr().get(pid);args={'footprint':'DemoFP','pad_index':0,'custom_shape':{'path':L_PATH,'units':'mm'}}
    with pytest.raises(ValueError):codex_bridge.execute_tool(p,'edit_pad_shape',args,'chat')
    preview=codex_bridge.execute_tool(p,'edit_pad_shape',{**args,'preview_only':True},'agent');assert preview['preview_only'] and preview['shape_report']['native_probe']['ok'] and p.state['workbench']['version']==1
    result=codex_bridge.execute_tool(p,'edit_pad_shape',args,'agent');assert result['ok'] and result['version']==2


def test_bus_endpoint_geometry_retains_custom_notches(tmp_path):
    from wholeboard import buses
    pcb=Path(board.build(fixture(),tmp_path)['pcb']);pad=next(p for p in geometry.read(pcb)['pads'] if p['name']=='1');shape=buses._pad_shape(pad)
    assert shape.area==pytest.approx(7) and not shape.covers(Point(pad['x'],pad['y']))


def test_declared_mechanical_hole_has_no_hidden_surface_copper(tmp_path):
    spec=custom_spec();pad=spec['library']['footprints']['DemoFP']['pads'][0];pad.update(kind='np_thru_hole',shape='rect',w=4,h=4,drill=.8)
    pcb=Path(board.build(spec,tmp_path)['pcb']);data=geometry.read(pcb);actual=next(p for p in data['pads'] if p['name']=='1')
    assert not actual['front'] and not actual['back'],'Flux-style mechanical holes must not secretly generate copper on either surface'
    output=tmp_path/'gerber';result=cli.run(['pcb','export','gerbers','-l','F.Cu','-o',str(output)+'/',str(pcb)]);assert result.returncode==0,result.stderr
    text=next(output.glob('*.gtl')).read_text();assert 'X113000000Y-111000000D03*' not in text


def test_native_unplated_surface_copper_is_preserved_in_editable_import(tmp_path):
    raw='''(footprint "SurfaceHole" (layer "F.Cu") (attr through_hole)
      (pad "1" np_thru_hole rect (at 0 0) (size 4 4) (drill 1) (layers "*.Cu" "*.Mask")))'''
    asset=project_library.import_native('footprints',raw)['SurfaceHole'];assert asset['pads'][0]['npth_copper'] is True
    spec=custom_spec();asset['pads'].append(copy.deepcopy(spec['library']['footprints']['DemoFP']['pads'][1]));spec['library']['footprints']['DemoFP']=asset;spec['nets']=[{'name':'SIG','pins':['U1.1']}];spec['components'][0]['no_connect']=['2']
    pcb=Path(board.build(spec,tmp_path)['pcb']);pad=next(p for p in geometry.read(pcb)['pads'] if p['name']=='1')
    assert pad['npth_copper'] is True and pad['front'] and pad['back']


def test_chat_inspects_custom_material_without_generating_or_saving(client):
    from wholeboard import codex_bridge
    spec=fixture();pid=client.post('/api/workbench/projects',json={'title':'Read custom copper','spec':spec}).json()['id'];p=server.mgr().get(pid)
    result=codex_bridge.execute_tool(p,'inspect_pad_shape',{'footprint':'DemoFP','pad_index':0},'chat')
    assert result['shape_report']['area_mm2']==pytest.approx(7) and not p.state.get('workbench_native') and p.state['workbench']['version']==1


def test_one_sided_export_cannot_drop_unplated_back_surface_copper(tmp_path):
    spec=custom_spec();spec['board']['layers']=1;spec['library']['footprints']['DemoFP']['pads'][0].update(kind='np_thru_hole',shape='rect',w=4,h=4,drill=1,npth_copper=True,layer='B.Cu')
    pcb=Path(board.build(spec,tmp_path)['pcb']);data=geometry.read(pcb)
    assert 'B.Cu' in geometry.explicit_copper_layers(data)
    with pytest.raises(cli.KiCadError):cli.export_fab(pcb,tmp_path/'unsafe',1)


def test_custom_mechanical_profile_is_not_reported_as_conductive_copper(client):
    spec=custom_spec();spec['library']['footprints']['DemoFP']['pads'][0].update(kind='np_thru_hole',shape='rect',w=4,h=4,drill=.4,drill_offset=[-1.5,0])
    pid=client.post('/api/workbench/projects',json={'title':'Nonconductive custom profile','spec':spec}).json()['id'];response=client.post(f'/api/workbench/projects/{pid}/library/pad-shape/prepare',json={'base_version':1,'footprint':'DemoFP','pad_index':0,'custom_shape':{'path':L_PATH,'units':'mm'}})
    assert response.status_code==200,response.text
    data=response.json();assert data['shape_report']['conductive'] is False
    pad=next(p for p in data['geometry']['pads'] if p['name']=='1');assert not pad.get('copper_polygons') and pad.get('profile_polygons')
