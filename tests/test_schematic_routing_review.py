"""Review regressions at generator and native-emission boundaries, not just path search."""
import copy
import json
from pathlib import Path

import pytest
from shapely.geometry import LineString

from wholeboard import server,workbench_native
from wholeboard.kicad import schematic,schematic_wires as wires
from test_workbench import client


def test_cross_sheet_guide_is_not_silently_omitted_from_native_routing_totals(client):
    spec=json.loads((Path(__file__).parent/'fixtures/schematic-routing-headers.json').read_text())
    spec['components'][2]['sheet']='Child';spec['editor']['sheets']={'Child':{'title':'Child','parent':''}}
    spec['editor']['connection_guides']=[{'id':'off-page','from':'J1.1','to':'J3.1'}]
    response=client.post('/api/workbench/projects',json={'title':'Cross-sheet route accounting','spec':spec});assert response.status_code==201,response.text
    p=server.mgr().get(response.json()['id']);native=workbench_native.generate(p);routing=native['schematic_routing']
    assert routing['routes']==1 and routing['routed']==0 and routing['unroutable']==1
    assert routing['unavailable']==1 and routing['failures'][0]['id']=='off-page'
    assert native['schematic_parity']['ok'] and p.state['workbench']['version']==1


def test_hierarchical_label_stub_is_reserved_before_explicit_paths_are_routed():
    editor={'wire_nodes':{'a':{'position':[-20,0],'net':'H','label':{'kind':'net'}},
                          'b':{'position':[20,0],'net':'H'},'c':{'position':[0,-20],'net':'V','label':{'kind':'net'}}},
            'connection_guides':[{'id':'h','from':'node:a','to':'node:b'}]}
    at=lambda x,y:(schematic.EDITOR_ORIGIN_MM+x*schematic.EDITOR_MM_PER_UNIT,schematic.EDITOR_ORIGIN_MM+y*schematic.EDITOR_MM_PER_UNIT)
    before=copy.deepcopy(editor);stub={'net':'V','a':at(0,-20),'b':at(0,0)}
    geometry=schematic._wires([],[],[],editor,{},extra_segments=[stub])
    assert geometry['routes'][0]['status']=='routed' and editor==before
    h=[segment for segment in geometry['segments'] if segment['net']=='H'];v=[segment for segment in geometry['segments'] if segment['net']=='V']
    for a in h:
        for b in v:
            intersection=LineString([a['a'],a['b']]).intersection(LineString([b['a'],b['b']]))
            if intersection.is_empty:continue
            assert intersection.geom_type=='Point'
            p=tuple(intersection.coords[0]);assert p not in (a['a'],a['b'],b['a'],b['b']),'A terminal stub endpoint touched another net'


def test_conflicting_preexisting_terminal_stubs_are_not_exported_as_independent_nets():
    extras=[{'net':'H','a':(0,0),'b':(20,0)},{'net':'V','a':(10,0),'b':(30,0)}]
    with pytest.raises(ValueError,match='net|terminal|stub|Stub'):
        schematic._wires([],[],[],{}, {},extra_segments=extras)


def test_native_waypoint_budget_matches_the_editing_api_limit():
    pins={'a':{'point':(0,0),'net':'H','free':True},'b':{'point':(20,0),'net':'H','free':True}}
    with pytest.raises(ValueError,match='100|waypoint|bend'):
        wires.routes([{'id':'long','from':'a','to':'b','waypoints':[[0,0]]*101}],pins,{})


def test_routing_policy_change_refreshes_a_schema19_cache_without_overwriting_it(client):
    import hashlib
    spec=json.loads((Path(__file__).parent/'fixtures/schematic-routing-headers.json').read_text())
    pid=client.post('/api/workbench/projects',json={'title':'Routing policy migration','spec':spec}).json()['id'];p=server.mgr().get(pid)
    old=workbench_native.generate(p);p.state['workbench_native']['schematic_routing']['policy']='orthogonal-interior-crossings-v1';p.save()
    path=Path(old['sch']);before={f:(hashlib.sha256(f.read_bytes()).hexdigest(),f.stat().st_mtime_ns) for f in path.parent.rglob('*') if f.is_file()}
    fresh=workbench_native.generate(p)
    assert fresh['schematic_routing']['policy']==wires.POLICY and Path(fresh['sch']).parent!=path.parent
    for f,identity in before.items():assert (hashlib.sha256(f.read_bytes()).hexdigest(),f.stat().st_mtime_ns)==identity
    assert p.state['workbench']['version']==1
