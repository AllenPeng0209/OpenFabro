"""Different-net schematic crossings must stay independent in the actual KiCad netlist."""
import copy
import hashlib
import itertools
import json
from pathlib import Path

import pytest
from shapely.geometry import LineString
from shapely.ops import unary_union

from wholeboard import schematic_view,sexpr
from wholeboard.kicad import schematic,schematic_wires as wires,cli
from test_workbench import client


def raw_cross(second):
    pins={'a':{'point':(-20,0),'net':'H','free':True},'b':{'point':(20,0),'net':'H','free':True},
          'c':{'point':tuple(second[0]),'net':'V','free':True},'d':{'point':tuple(second[-1]),'net':'V','free':True}}
    return wires.routes([{'id':'horizontal','from':'a','to':'b','fixed_points':[[-20,0],[20,0]]},
        {'id':'vertical','from':'c','to':'d','fixed_points':second}],pins,{},scale=1,origin=0)


def test_proper_fixed_interior_crossing_routes_both_nets_without_a_junction():
    routes,geometry=raw_cross([[0,-20],[0,20]])
    assert [r['status'] for r in routes]==['routed','routed']
    assert not geometry['junctions']
    assert {s['net'] for s in geometry['segments']}=={'H','V'}


@pytest.mark.parametrize('path',[
    [[0,-20],[0,0]],             # New endpoint on the other wire.
    [[20,-20],[20,20]],          # Other wire endpoint on the new wire.
    [[-10,0],[30,0]],            # Collinear overlap.
    [[0,-20],[0,0],[10,0],[10,20]], # Bend/overlap at the crossing.
])
def test_fixed_endpoint_contacts_and_overlaps_never_become_a_false_independent_route(path):
    routes,_=raw_cross(path)
    # The first route can also be refused because it would pass through a known foreign pin.
    assert not all(route['status']=='routed' for route in routes)


def test_minimal_two_headers_do_not_block_the_next_net_pin_exit(tmp_path):
    spec={'name':'routing_minimal','board':{'width_mm':40,'height_mm':30,'layers':2},
        'components':[{'ref':f'J{i}','value':'Header','symbol':'Connector_Generic:Conn_01x02',
            'footprint':'Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical'} for i in (1,2)],
        'nets':[{'name':f'SIG{i}','pins':[f'J1.{i}',f'J2.{i}']} for i in (1,2)],
        'editor':{'positions':{'J1':[100,100],'J2':[400,200]},'connection_guides':[
            {'id':f'sig{i}','from':f'J1.{i}','to':f'J2.{i}'} for i in (1,2)]}}
    scene=schematic_view.scene(spec)
    assert all(r['status']=='routed' for r in scene['routes']),scene['routes']
    native=schematic.build(spec,tmp_path)
    assert schematic.netlist_parity(spec,cli.schematic_nets(Path(native['sch'])))['ok']


@pytest.mark.parametrize('aligned',[False,True])
def test_all_six_real_header_guides_are_drawn_as_native_wires_with_unchanged_nets(tmp_path,aligned):
    spec=json.loads((Path(__file__).parent/'fixtures/schematic-routing-headers.json').read_text());before=copy.deepcopy(spec)
    if aligned:
        spec['editor']['positions']['J2'][1]=100;spec['editor']['positions']['J3'][1]=100
    scene=schematic_view.scene(spec)
    assert len(scene['routes'])==6 and all(r['status']=='routed' for r in scene['routes']),[(r['id'],r['status']) for r in scene['routes']]
    for route in scene['routes']:
        actual=unary_union([LineString(w['points']) for w in scene['wires'] if w['net']==route['net']])
        assert LineString(route['points']).difference(actual.buffer(.001)).length<.001,'Guide metadata is not backed by native wire geometry'
    native=schematic.build(spec,tmp_path)
    proof=schematic.netlist_parity(spec,cli.schematic_nets(Path(native['sch'])))
    assert proof['ok'] and proof['nets']==3 and proof['pins']==9
    assert spec['components']==before['components'] and spec['fixed_copper']==before['fixed_copper']


def test_real_kicad_crossing_is_independent_until_an_explicit_junction_is_added(tmp_path):
    spec={'name':'native_cross_rule','board':{'width_mm':40,'height_mm':30,'layers':2},
        'components':[{'ref':f'J{i}','value':'Port','symbol':'Connector_Generic:Conn_01x01',
            'footprint':'Connector_PinHeader_2.54mm:PinHeader_1x01_P2.54mm_Vertical'} for i in range(1,5)],
        'nets':[{'name':'H','pins':['J1.1','J2.1']},{'name':'V','pins':['J3.1','J4.1']}],
        'editor':{'positions':{'J1':[140,100],'J2':[540,100],'J3':[340,-100],'J4':[340,300]}}}
    scene=schematic_view.scene(spec);anchors={a['anchor']:a['position'] for a in scene['anchors']}
    point=lambda p:[round(schematic.EDITOR_ORIGIN_MM+v*schematic.EDITOR_MM_PER_UNIT,5) for v in p]
    path=Path(schematic.build(spec,tmp_path)['sch']);tree=sexpr.parse(path.read_text());S=sexpr.S;Sym=sexpr.Sym
    for a,b in [('J1.1','J2.1'),('J3.1','J4.1')]:
        tree.append([Sym('wire'),[Sym('pts'),S(Sym('xy'),*point(anchors[a])),S(Sym('xy'),*point(anchors[b]))],
            [Sym('stroke'),S(Sym('width'),0),S(Sym('type'),Sym('default'))],[Sym('uuid'),schematic.uid()]])
    path.write_text(sexpr.dumps(tree));assert schematic.netlist_parity(spec,cli.schematic_nets(path))['ok']
    crossing=point([anchors['J3.1'][0],anchors['J1.1'][1]])
    tree.append([Sym('junction'),S(Sym('at'),*crossing),S(Sym('diameter'),0),S(Sym('color'),0,0,0,0),[Sym('uuid'),schematic.uid()]])
    path.write_text(sexpr.dumps(tree));assert not schematic.netlist_parity(spec,cli.schematic_nets(path))['ok']


def test_all_720_guide_orders_route_the_real_native_pin_geometry(tmp_path,monkeypatch):
    spec=json.loads((Path(__file__).parent/'fixtures/schematic-routing-headers.json').read_text());captured={};original=wires.routes
    def collect(guides,pins,boxes,**kwargs):
        captured.update(guides=copy.deepcopy(guides),pins=copy.deepcopy(pins),boxes=copy.deepcopy(boxes),kwargs=kwargs)
        return original(guides,pins,boxes,**kwargs)
    with monkeypatch.context() as context:
        context.setattr(wires,'routes',collect);schematic.build(spec,tmp_path)
    for guides in itertools.permutations(captured['guides']):
        routes,geometry=original(list(guides),captured['pins'],captured['boxes'],**captured['kwargs'])
        assert len(routes)==6 and all(route['status']=='routed' for route in routes),[g['id'] for g in guides]
        for index,a in enumerate(geometry['segments']):
            for b in geometry['segments'][index+1:]:
                if a['net']==b['net']:continue
                intersection=LineString([a['a'],a['b']]).intersection(LineString([b['a'],b['b']]))
                if intersection.is_empty:continue
                assert intersection.geom_type=='Point','Different nets overlap instead of crossing'
                at=tuple(intersection.coords[0])
                assert at not in (a['a'],a['b'],b['a'],b['b'])
                assert not any(j['point']==at for j in geometry['junctions'])


def test_old_native_cache_is_preserved_when_routing_generation_advances(client,monkeypatch):
    from wholeboard import server,workbench_native
    spec=json.loads((Path(__file__).parent/'fixtures/schematic-routing-headers.json').read_text())
    pid=client.post('/api/workbench/projects',json={'title':'Routing cache migration','spec':spec}).json()['id'];p=server.mgr().get(pid)
    with monkeypatch.context() as context:
        context.setattr(workbench_native,'NATIVE_SCHEMA',18);previous=workbench_native.generate(p)
    # An old cache may contain labels but incomplete wire geometry. Keep this historical artifact.
    path=Path(previous['sch']);tree=sexpr.parse(path.read_text());tree[:]=[node for node in tree if sexpr.tag(node)!='wire'];path.write_text(sexpr.dumps(tree))
    old={f:(hashlib.sha256(f.read_bytes()).hexdigest(),f.stat().st_mtime_ns) for f in Path(previous['pcb']).parent.rglob('*') if f.is_file()}
    current=workbench_native.generate(p)
    assert Path(current['sch']).parent!=path.parent,'An obsolete routing cache was reused'
    assert current['schematic_routing']['routes']==6 and current['schematic_routing']['routed']==6 and current['schematic_routing']['unroutable']==0
    assert current['schematic_parity']['ok'] and p.state['workbench']['version']==1
    for f,identity in old.items():assert (hashlib.sha256(f.read_bytes()).hexdigest(),f.stat().st_mtime_ns)==identity


def test_a_search_budget_failure_is_distinguished_from_an_impossible_wire_path():
    pins={'a':{'point':(-10,-10),'net':'SIG','free':True},'b':{'point':(-5,-5),'net':'SIG','free':True}}
    boxes={f'block{i}':(10+i*4,10+i*4,11+i*4,11+i*4) for i in range(400)}
    routes,_=wires.routes([{'id':'limited','from':'a','to':'b'}],pins,boxes)
    assert routes[0]['status']=='unroutable'
    assert 'budget' in routes[0]['reason'].lower()
    assert routes[0]['search']['grid_points']>routes[0]['search']['grid_limit']==90000
