"""Pair discovery uses the same saved terminal declarations as native constraints."""
import copy
import json
from pathlib import Path
from test_workbench import client
from wholeboard import design,routing_pairs

def fixture():
    spec={'name':'paired_routing','board':{'width_mm':45,'height_mm':30,'layers':4,'ground_pour':None},
      'components':[{'ref':f'J{i}','value':'Pair header','symbol':'Connector_Generic:Conn_01x04','footprint':'Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical','placement':{'x_mm':8+(i-1)*30,'y_mm':8},
       'pin_properties':{str(p):{'bus_group':'LINK','pair':'D0' if p<3 else 'D1','polarity':'P' if p%2 else 'N','bus_type':'USB 2.0','impedance_ohms':90} for p in range(1,5)}} for i in (1,2)],
      'nets':[{'name':n,'pins':[f'J1.{p}',f'J2.{p}']} for p,n in enumerate(['D0_P','D0_N','D1_P','D1_N'],1)]}
    return design.normalise(spec)

def test_both_native_ends_and_independent_same_type_lanes_are_retained():
    spec=fixture();before=copy.deepcopy(spec);result=routing_pairs.hints(spec)
    assert spec==before
    assert len(result['pairs'])==2,'Both independently declared pairs need routing hints'
    pair=next(p for p in result['pairs'] if set(p['nets'])=={'D0_P','D0_N'})
    assert {tuple(e['pins']) for e in pair['ends']}=={('J1.1','J1.2'),('J2.1','J2.2')}
    assert pair['gap_mm']>=spec['rules']['clearance_mm'] and pair['width_mm']>0
    assert pair['polarity']=={'D0_P':'P','D0_N':'N'}

def test_manual_differential_groups_resolve_real_component_endpoints_without_inventing_polarity():
    spec=fixture()
    for c in spec['components']:c.pop('pin_properties')
    spec['impedance']=[{'kind':'diff','nets':['D0_P','D0_N'],'ohms':90}]
    result=routing_pairs.hints(spec)
    assert len(result['pairs'])==1
    assert {tuple(e['pins']) for e in result['pairs'][0]['ends']}=={('J1.1','J1.2'),('J2.1','J2.2')}
    assert result['pairs'][0]['polarity']=={}

def test_conflicting_partner_and_opposite_endpoint_polarity_cannot_become_automatic_routes():
    spec=fixture();spec['components'][1]['pin_properties']['1']['polarity']='N'
    result=routing_pairs.hints(spec)
    assert all('D0_P' not in p['nets'] for p in result['pairs'])
    assert any('polarity' in i['message'].lower() for i in result['issues'])
    spec=fixture();spec['impedance']=[{'kind':'diff','nets':['D0_P','D1_N'],'ohms':90}]
    result=routing_pairs.hints(spec)
    assert all('D0_P' not in p['nets'] for p in result['pairs'])
    assert any('partner' in i['message'].lower() for i in result['issues'])

def test_plain_boards_do_not_require_pair_properties_or_guess_pairs_from_net_names():
    spec=fixture()
    for c in spec['components']:c.pop('pin_properties')
    assert routing_pairs.hints(spec)=={'schema':1,'pairs':[],'issues':[]}

def test_pair_declared_at_one_end_can_be_started_at_the_other_connected_component():
    spec=fixture();spec['components'][1].pop('pin_properties')
    row=next(p for p in routing_pairs.hints(spec)['pairs'] if p['nets']==['D0_P','D0_N'])
    assert {tuple(e['pins']) for e in row['ends']}=={('J1.1','J1.2'),('J2.1','J2.2')}

def test_manual_pair_retains_explicit_polarity_even_without_a_terminal_pair_name():
    spec=fixture()
    for c in spec['components']:
        c['pin_properties']={'1':{'polarity':'P'},'2':{'polarity':'N'}}
    spec['impedance']=[{'kind':'diff','nets':['D0_P','D0_N'],'ohms':90}]
    assert routing_pairs.hints(spec)['pairs'][0]['polarity']=={'D0_P':'P','D0_N':'N'}

def test_layout_returns_source_bound_pair_hints_without_rewriting_native_geometry(client):
    from wholeboard import server,workbench_native
    pid=client.post('/api/workbench/projects',json={'title':'Pair hints','spec':fixture()}).json()['id'];p=server.mgr().get(pid);native=workbench_native.generate(p)
    snapshots={f:(f.read_bytes(),f.stat().st_mtime_ns) for f in (p.root/'native').rglob('*') if f.is_file()}
    response=client.get(f'/api/workbench/projects/{pid}/layout-geometry');assert response.status_code==200,response.text
    data=response.json();assert len(data.get('routing_profiles',{}).get('pairs',[]))==2,'Native Layout does not deliver its declared pair metadata'
    assert data['source_version']==1 and data['geometry']==json.loads(Path(native['geometry_file']).read_text())
    assert all((f.read_bytes(),f.stat().st_mtime_ns)==value for f,value in snapshots.items())

def test_pair_hint_generation_cannot_return_after_the_captured_source_changes(client,monkeypatch):
    from wholeboard import server,workbench_native
    spec=fixture();pid=client.post('/api/workbench/projects',json={'title':'Pair hint race','spec':spec}).json()['id'];workbench_native.generate(server.mgr().get(pid));original=routing_pairs.hints;called=[]
    def changed(source):
        called.append(True);new=copy.deepcopy(spec);new['rules']['track_mm']=.35
        assert client.put(f'/api/workbench/projects/{pid}/design',json={'base_version':1,'spec':new}).status_code==200
        return original(source)
    monkeypatch.setattr(routing_pairs,'hints',changed)
    response=client.get(f'/api/workbench/projects/{pid}/layout-geometry')
    assert called,'Layout has not attached source-bound pair hints'
    assert response.status_code==409
