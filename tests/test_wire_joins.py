"""Native drawing endpoints attach to actual parent wires, independent of net labels."""
from wholeboard.kicad import schematic_wires
from wholeboard.kicad import schematic,cli
from wholeboard import schematic_view,sexpr
from pathlib import Path
import json
import pytest


def anchors():
    return ({'A1.1':{'point':(0,0),'angle':0,'symbol':'A','net':'SIG'},'B1.1':{'point':(20.32,0),'angle':180,'symbol':'B','net':'SIG'},'C1.1':{'point':(10.16,10.16),'angle':270,'symbol':'C','net':'SIG'}},
        {'A':(-1.016,-1.016,1.016,1.016),'B':(19.304,-1.016,21.336,1.016),'C':(9.144,9.144,11.176,11.176)})


def test_native_branch_ends_at_parent_wire_and_exports_the_clicked_junction():
    pins,boxes=anchors();guides=[{'id':'trunk','from':'A1.1','to':'B1.1'},{'id':'branch','from':'C1.1','to':'A1.1','to_join':{'wire':'trunk','offset':.5}}]
    paths,geo=schematic_wires.routes(guides,pins,boxes)
    branch=next(route for route in paths if route['index']==1)
    assert branch['status']=='routed',branch
    assert branch['points'][-1]==(10.16,0),'A branch still routes to the hidden label pin instead of the clicked wire'
    assert any(j['point']==(10.16,0) for j in geo['junctions'])


def test_join_attachment_tracks_parent_geometry_and_supports_dependency_order():
    pins,boxes=anchors();pins['B1.1']['point']=(30.48,0);boxes['B']=(29.464,-1.016,31.496,1.016)
    guides=[{'id':'branch','from':'C1.1','to':'A1.1','to_join':{'wire':'trunk','offset':.5}},{'id':'trunk','from':'A1.1','to':'B1.1'}]
    paths,_=schematic_wires.routes(guides,pins,boxes)
    branch=next(route for route in paths if route['index']==0)
    assert branch['status']=='routed',branch
    assert branch['points'][-1]==(15.24,0)


def test_deep_allowed_wire_dependencies_do_not_exhaust_the_python_stack():
    guides=[{'id':'w0','from':'A1.1','to':'B1.1'}]
    guides.extend({'id':f'w{i}','from':'C1.1','to':'A1.1','to_join':{'wire':f'w{i-1}','offset':.5}} for i in range(1,1500))
    try:ids=schematic_wires.validate_guides(list(reversed(guides)))
    except RecursionError:pytest.fail('Allowed junction metadata exhausts the Python recursion stack')
    assert len(ids)==1500


def test_branch_tries_the_other_side_when_the_near_side_is_enclosed():
    pins,boxes=anchors();boxes.update(A=(-1.016,-1.016,1.016,10.16),B=(19.304,-1.016,21.336,10.16),C=(9.144,19.304,11.176,21.336));pins['C1.1']['point']=(10.16,20.32)
    pins.update({'A1.2':{'point':(0,10.16),'angle':270,'symbol':'A','net':'GND'},'B1.2':{'point':(20.32,10.16),'angle':270,'symbol':'B','net':'GND'}})
    guides=[{'id':'signal','from':'A1.1','to':'B1.1'},{'id':'ground','from':'A1.2','to':'B1.2'},{'id':'branch','from':'C1.1','to':'A1.1','to_join':{'wire':'signal','offset':.5}}]
    routes,_=schematic_wires.routes(guides,pins,boxes);branch=next(route for route in routes if route['id']=='branch')
    assert branch['status']=='routed',branch
    assert branch['points'][-1]==(10.16,0)


def test_real_native_branch_scene_and_netlist_are_consistent(tmp_path):
    spec=json.loads((Path(__file__).parents[1]/'wholeboard/web/workbench-example.json').read_text())
    spec['editor']['connection_guides']=[{'id':'trunk','from':'R1.2','to':'R2.2'},{'id':'branch','from':'D1.1','to':'R1.2','to_join':{'wire':'trunk','offset':.5}}]
    scene=schematic_view.scene(spec);branch=next(route for route in scene['routes'] if route['id']=='branch')
    assert branch['status']=='routed',branch
    assert branch['joins']['to']['point']==branch['points'][-1],'The join uses a different coordinate system from its visible wire'
    assert any(abs(j['position'][0]-branch['points'][-1][0])<.001 and abs(j['position'][1]-branch['points'][-1][1])<.001 for j in scene['junctions'])
    result=schematic.build(spec,tmp_path);sch=Path(result['sch'])
    assert list(sexpr.find_all(sexpr.parse(sch.read_text()),'junction'))
    proof=schematic.netlist_parity(spec,cli.schematic_nets(sch));assert proof['ok'],proof


def test_automatically_generated_branch_detours_stay_on_the_native_connection_grid(tmp_path):
    spec=json.loads((Path(__file__).parent/'fixtures/schematic-junction-spec.json').read_text())
    output=schematic.build(spec,tmp_path);report=cli.erc(Path(output['sch']))
    findings=report.get('ignored_list',[])+report.get('errors',[])+report.get('warnings',[])
    off_grid=[row for row in findings if row['type']=='endpoint_off_grid']
    assert off_grid==[],'The auto-router itself generated off-grid wire endpoints'
    proof=schematic.netlist_parity(spec,cli.schematic_nets(Path(output['sch'])));assert proof['ok'],proof


def test_a_wire_join_reuses_an_existing_parent_span_instead_of_reporting_no_path():
    spec=json.loads((Path(__file__).parent/'fixtures/schematic-junction-spec.json').read_text());spec['editor']['positions']['R2']=[600,200]
    spec['nets']=[{'name':'GND','pins':[f'R{i}.{pin}' for i in (1,2,3) for pin in (1,2)]}]
    spec['editor']['connection_guides']=[{'id':'signal','from':'R1.1','to':'R2.1'},{'id':'ground','from':'R1.2','to':'R2.2'},{'id':'branch','from':'R1.1','to':'R3.1','from_join':{'wire':'signal','offset':.5}},{'id':'bridge','from':'R1.1','to':'R1.2','from_join':{'wire':'branch','offset':0},'to_join':{'wire':'ground','offset':.5}}]
    scene=schematic_view.scene(spec);bridge=next(route for route in scene['routes'] if route['id']=='bridge')
    assert bridge['status']=='routed',bridge
    assert abs(bridge['points'][0][0]-400)<.001 and abs(bridge['points'][0][1]-160)<.001
    assert abs(bridge['points'][-1][0]-400)<.001 and abs(bridge['points'][-1][1]-240)<.001
