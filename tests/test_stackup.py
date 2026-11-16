"""Physical stackups must reach real native files and impedance inputs."""
import copy
from pathlib import Path
import pytest
from wholeboard import sexpr,impedance,design,server
from wholeboard import stackup
from wholeboard.kicad import board,cli,geometry
from test_workbench import client


def recipe():
    return {'schema':1,'name':'Asymmetric four layer','copper_finish':'ENIG','layers':[
        {'id':'fm','type':'solder_mask','side':'front','material':'Mask','thickness_mm':.01,'epsilon_r':3.3,'loss_tangent':.02,'color':'Green'},
        {'id':'c1','type':'copper','native_layer':'F.Cu','name':'Top','role':'signal','material':'Copper','thickness_mm':.035},
        {'id':'d1','type':'dielectric','kind':'prepreg','material':'Front prepreg','thickness_mm':.1,'epsilon_r':4.1,'loss_tangent':.015},
        {'id':'c2','type':'copper','native_layer':'In1.Cu','name':'Ground','role':'plane','material':'Copper','thickness_mm':.0175},
        {'id':'d2','type':'dielectric','kind':'core','material':'FR4 core','thickness_mm':1.175,'epsilon_r':4.3,'loss_tangent':.02},
        {'id':'c3','type':'copper','native_layer':'In2.Cu','name':'Power','role':'plane','material':'Copper','thickness_mm':.0175},
        {'id':'d3','type':'dielectric','kind':'prepreg','material':'Back prepreg','thickness_mm':.2,'epsilon_r':3.9,'loss_tangent':.018},
        {'id':'c4','type':'copper','native_layer':'B.Cu','name':'Bottom','role':'signal','material':'Copper','thickness_mm':.035},
        {'id':'bm','type':'solder_mask','side':'back','material':'Mask','thickness_mm':.01,'epsilon_r':3.3,'loss_tangent':.02,'color':'Blue'}]}


def fixture():
    return {'name':'stackup_qa','board':{'width_mm':40,'height_mm':30,'layers':4,'thickness_mm':1.6,'ground_pour':None,'stackup':recipe()},'components':[],
            'nets':[{'name':'DP','pins':[]},{'name':'DN','pins':[]}],'impedance':[{'kind':'diff','nets':['DP','DN'],'ohms':90}]}


def test_declared_physical_layers_materials_and_epsilon_reach_native_kicad(tmp_path):
    spec=fixture();out=board.build(spec,tmp_path);pcb=sexpr.parse(Path(out['pcb']).read_text());stack=sexpr.find(sexpr.find(pcb,'setup'),'stackup')
    assert stack is not None,'Native PCB ignores the declared physical stackup'
    rows={str(v[1]):v for v in sexpr.find_all(stack,'layer')}
    assert sexpr.num(sexpr.find(rows['F.Cu'],'thickness')[1])==.035
    assert sexpr.num(sexpr.find(rows['In1.Cu'],'thickness')[1])==.0175
    assert str(sexpr.find(rows['dielectric 1'],'material')[1])=='Front prepreg'
    assert sexpr.num(sexpr.find(rows['dielectric 1'],'epsilon_r')[1])==4.1
    assert sexpr.num(sexpr.find(rows['dielectric 3'],'epsilon_r')[1])==3.9
    assert str(sexpr.find(stack,'copper_finish')[1])=='ENIG'
    xml=tmp_path/'accepted.xml';result=cli.run(['pcb','export','ipc2581','--units','mm','--output',str(xml),out['pcb']]);assert result.returncode==0,result.stderr
    assert xml.is_file() and 'Front prepreg' in xml.read_text(),'Real KiCad did not consume the declared material'


@pytest.mark.parametrize('kind',['negative','epsilon','duplicate','missing_dielectric','count','total','native_name','nonfinite','boolean'])
def test_invalid_stackup_is_rejected_before_saved_design_changes(client,kind):
    initial=fixture();initial['board'].pop('stackup');initial['impedance']=[];pid=client.post('/api/workbench/projects',json={'title':'Stackup validation','spec':initial}).json()['id'];saved=copy.deepcopy(server.mgr().get(pid).state['spec']);candidate=copy.deepcopy(saved);candidate['board']['stackup']=recipe();rows=candidate['board']['stackup']['layers']
    if kind=='negative':rows[2]['thickness_mm']=-.1
    elif kind=='epsilon':rows[2]['epsilon_r']=0
    elif kind=='duplicate':rows[2]['id']='c1'
    elif kind=='missing_dielectric':rows.pop(2)
    elif kind=='count':candidate['board']['layers']=2
    elif kind=='total':candidate['board']['thickness_mm']=2
    elif kind=='native_name':rows[3]['native_layer']='In7.Cu'
    elif kind=='nonfinite':rows[2]['epsilon_r']='Infinity'
    elif kind=='boolean':rows[2]['thickness_mm']=True
    response=client.put(f'/api/workbench/projects/{pid}/design',json={'base_version':1,'spec':candidate});assert response.status_code==422,kind
    current=server.mgr().get(pid).state;assert current['workbench']['version']==1 and current['spec']==saved


def test_impedance_rule_uses_declared_front_reference_and_actual_copper_thickness():
    rule=impedance.rules(design.normalise(fixture()))[0]
    assert rule['h_mm']==.1 and rule['er']==4.1,'Route widths still use a hardcoded nominal four-layer stack'
    assert rule['reference_layer']=='In1.Cu' and rule['copper_mm']==.035


def test_eight_ten_and_twelve_layers_are_valid_board_counts():
    for count in (8,10,12):
        spec=fixture();spec['board'].pop('stackup');spec['board']['layers']=count;spec['impedance']=[]
        assert not any('board.layers' in v for v in design.validate(spec).errors)


def test_one_sided_native_board_is_parseable_by_real_kicad(tmp_path):
    spec=fixture();spec['board'].pop('stackup');spec['board']['layers']=1;spec['impedance']=[]
    out=board.build(spec,tmp_path);result=cli.run(['pcb','export','ipc2581','--units','mm','--output',str(tmp_path/'single.xml'),out['pcb']])
    assert result.returncode==0,result.stderr


def test_numeric_layer_count_formatting_does_not_change_a_declared_stackup():
    spec=fixture();spec['board']['layers']=4.0;stackup.validate(spec)
    assert stackup.parameters(spec['board'])['h']==.1


def test_boolean_schema_and_foil_without_substrate_are_rejected():
    spec=fixture();spec['board']['stackup']['schema']=True
    with pytest.raises(ValueError):stackup.validate(spec)
    spec=fixture();spec['board']['layers']=1;spec['board']['stackup']=stackup.standard(1)
    spec['board']['stackup']['layers']=[r for r in spec['board']['stackup']['layers'] if r['type']!='dielectric'];spec['board']['thickness_mm']=.055
    with pytest.raises(ValueError):stackup.validate(spec)


def test_standard_presets_cover_all_counts_with_finished_thickness_including_masks():
    for count in (1,2,4,6,8,10,12):
        spec=fixture();spec['board']['layers']=count;spec['board']['stackup']=stackup.standard(count);stackup.validate(spec)
        assert sum(r['thickness_mm'] for r in spec['board']['stackup']['layers'])==pytest.approx(1.6)


def test_single_sided_export_has_no_bottom_copper_gerber_or_active_layer(tmp_path):
    spec=fixture();spec['board'].pop('stackup');spec['board']['layers']=1;spec['impedance']=[]
    out=board.build(spec,tmp_path/'native');geo=geometry.read(Path(out['pcb']));assert geo['layers']==['F.Cu']
    fabrication=cli.export_fab(Path(out['pcb']),tmp_path/'fab',1)
    assert any('F_Cu' in name for name in fabrication['files']) and not any('B_Cu' in name for name in fabrication['files'])


def test_routed_back_layer_estimate_uses_its_own_declared_dielectric(tmp_path):
    from test_buses import example,pair
    from wholeboard import buses
    spec=pair(example());spec['board'].update(layers=4,thickness_mm=1.6,stackup=recipe())
    for group in spec['fixed_copper']:
        for track in group['tracks']:track['layer']='B.Cu'
    geo=geometry.read(Path(board.build(spec,tmp_path)['pcb']));estimate=buses.analyze(spec,geo)['pairs'][0]['impedance']
    assert estimate['stackup']['h']==pytest.approx(.2) and estimate['stackup']['er']==pytest.approx(3.9)
    assert estimate['stackup']['reference_layer']=='In2.Cu' and estimate['source']=='declared_stackup'


def test_native_copper_roles_are_exported_as_layer_roles(tmp_path):
    out=board.build(fixture(),tmp_path);tree=sexpr.parse(Path(out['pcb']).read_text());layers=sexpr.find(tree,'layers')
    role={str(r[1]):str(r[2]) for r in layers[1:] if isinstance(r,list)}
    assert role['In1.Cu']=='power' and role['In2.Cu']=='power' and role['F.Cu']=='signal'


def test_undeclared_eight_layer_stackup_does_not_borrow_four_layer_impedance():
    spec=fixture();spec['board'].pop('stackup');spec['board']['layers']=8
    rule=impedance.rules(design.normalise(spec))[0];assert rule['h_mm'] is None and not rule['practical']


def test_interactive_pair_hints_share_the_declared_stackup_model():
    from wholeboard import routing_pairs
    row=routing_pairs.hints(design.normalise(fixture()))['pairs'][0]
    assert row['width_mm']==.159 and row['gap_mm']==.2


def test_inactive_native_slot_does_not_hide_actual_imported_copper(tmp_path):
    spec=fixture();spec['board'].pop('stackup');spec['board']['layers']=1;spec['impedance']=[]
    out=board.build(spec,tmp_path);path=Path(out['pcb']);tree=sexpr.parse(path.read_text());tree.append([sexpr.Sym('segment'),sexpr.S(sexpr.Sym('start'),105,105),sexpr.S(sexpr.Sym('end'),110,105),sexpr.S(sexpr.Sym('width'),.2),sexpr.S(sexpr.Sym('layer'),'B.Cu'),sexpr.S(sexpr.Sym('net'),'DP'),sexpr.S(sexpr.Sym('uuid'),'11111111-1111-4111-8111-000000000001')]);path.write_text(sexpr.dumps(tree))
    geo=geometry.read(path);assert 'B.Cu' in geo['layers'] and geo['stackup_issues']
    with pytest.raises(cli.KiCadError):cli.export_fab(path,tmp_path/'unsafe-fab',1)


def test_non_impedance_bus_keeps_length_limits_without_a_reference_plane():
    spec=fixture();spec['board']['stackup']['layers'][3]['role']='signal';spec['impedance']=[{'kind':'bus','nets':['DP','DN'],'max_length_mm':40,'max_match_mm':.25}]
    rule=impedance.rules(design.normalise(spec))[0];assert rule['max_length_mm']==40 and rule['max_match_mm']==.25


def test_boolean_layer_count_is_not_a_one_sided_board(client):
    spec=fixture();spec['board'].pop('stackup');spec['board']['layers']=True;spec['impedance']=[]
    assert client.post('/api/workbench/projects',json={'title':'Invalid count','spec':spec}).status_code==422


def test_declared_plane_without_verified_copper_is_not_a_physical_impedance_pass(tmp_path):
    from test_buses import example,pair
    from wholeboard import buses
    spec=pair(example(),impedance_tolerance_pct=100);spec['board'].update(layers=4,thickness_mm=1.6,stackup=recipe())
    geo=geometry.read(Path(board.build(spec,tmp_path)['pcb']));estimate=buses.analyze(spec,geo)['pairs'][0]['impedance']
    assert estimate['estimate_ohms'] is not None and estimate['status']=='unknown' and estimate['reference_verified'] is False


def test_cached_legacy_one_sided_file_is_not_reused_without_construction_policy(client):
    from wholeboard import workbench_native
    spec=fixture();spec['board'].pop('stackup');spec['board']['layers']=1;spec['impedance']=[]
    pid=client.post('/api/workbench/projects',json={'title':'Legacy single-sided cache','spec':spec}).json()['id'];p=server.mgr().get(pid);native=workbench_native.generate(p);old=Path(native['pcb']);tree=sexpr.parse(old.read_text());layers=sexpr.find(tree,'layers');layers[:]=[v for v in layers if not isinstance(v,list) or str(v[1])!='B.Cu'];old.write_text(sexpr.dumps(tree));p.state['workbench_native'].pop('physical_stackup_policy',None)
    rebuilt=workbench_native.generate(p);assert Path(rebuilt['pcb'])!=old and old.exists()
    assert rebuilt['physical_stackup_policy']=='declared-physical-stackup-v1'


def test_declared_plane_net_is_present_in_native_copper_definitions(tmp_path):
    spec=fixture();spec['nets'].append({'name':'GND','pins':[]});spec['board']['stackup']['layers'][3]['net']='GND'
    geo=geometry.read(Path(board.build(spec,tmp_path)['pcb']))
    assert any(z['net']=='GND' and 'In1.Cu' in z.get('layers',[]) for z in geo['zone_definitions'])


def test_native_export_also_delivers_a_portable_construction_recipe(tmp_path):
    import json
    spec=fixture();out=board.build(spec,tmp_path);path=Path(out.get('stackup_report','missing'))
    assert path.is_file(),'Native export omitted its portable construction and assumptions'
    value=json.loads(path.read_text());assert value['construction']==recipe() and value['summary']['thickness_mm']==1.6
