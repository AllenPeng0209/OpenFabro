"""Automatic interface metadata must use actual names without altering circuits."""
import copy
import pytest
from wholeboard import buses
from test_workbench import client


def fixture(names):
    pins=[{'number':str(i),'name':name,'x':-5.08,'y':-i*2.54,'angle':0,'type':'passive'} for i,name in enumerate(names,1)]
    return {'name':'interface_setup','board':{'width_mm':40,'height_mm':30,'layers':2,'ground_pour':None},
            'components':[{'ref':'J1','value':'Interface','symbol':'Project:Interface','footprint':'Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical','placement':{'x_mm':8,'y_mm':8}}],
            'nets':[{'name':'N'+str(i),'class':'signal','pins':['J1.'+str(i)]} for i in range(1,len(names)+1)],
            'library':{'symbols':{'Interface':{'name':'Interface','reference':'J','pins':pins,'graphics':[]}},'footprints':{},'parts':{}}}


def setup(spec,part_type,**settings):
    return buses.prepare(spec,{'action':'interface','ref':'J1','part_type':part_type,**settings})


def test_usb_part_type_creates_real_named_data_pair_and_leaves_power_alone():
    spec=fixture(['D+','D-','VBUS','GND']);original=copy.deepcopy(spec)
    result=setup(spec,'USB C');component=result['spec']['components'][0];props=component['pin_properties']
    assert component['part_type']=='USB C' and component['bus_type']=='USB'
    assert props['1']=={'bus_group':'USB2','bus_type':'USB 2.0','pair':'USB2_DATA','pair_role':'DATA','polarity':'P','impedance_ohms':90}
    assert props['2']=={**props['1'],'polarity':'N'}
    assert '3' not in props and '4' not in props
    assert spec==original and result['spec']['nets']==original['nets'] and component['placement']==original['components'][0]['placement']
    assert result['interface_setup']['ready'] and result['interface_setup']['matched_pins']==2


@pytest.mark.parametrize('part_type,names,pair,target',[
    ('USB A',['dp','dm','VBUS','GND'],'USB2_DATA',90),
    ('USB B',['SSTXP1','SSTXN1','SSRX2+','SSRX2-'],'USB3_TX1',90),
    ('HDMI',['TMDS Data0+','TMDS Data0-','CK+','CK-'],'HDMI_D0',100),
    ('MIPI CSI',['data_p0','data_n0','clock_p','clock_n'],'CSI_D0',100),
    ('MIPI DSI',['DP0+','DP0-','CLK+','CLK-'],'DSI_D0',100),
    ('PCIe x1',['PETp0','PETn0','PERp0','PERn0'],'PCIe_TX0',85),
    ('PCIe x2',['TX1P','TX1N','RX1P','RX1N'],'PCIe_TX1',85),
    ('PCIe x4',['TX3P','TX3N','RX3P','RX3N'],'PCIe_TX3',85),
    ('PCIe x8',['TX7P','TX7N','RX7P','RX7N'],'PCIe_TX7',85),
    ('PCIe x16',['TX15P','TX15N','RX15P','RX15N'],'PCIe_TX15',85),
    ('DDR3',['DQS0','~{DQS0}','DQ0','DQ8'],'DDR3_DQS0',100),
    ('DDR4',['DQS0_t','DQS0_c','DQ0','DQ8'],'DDR4_DQS0',100),
])
def test_supported_part_types_derive_roles_from_native_pin_names(part_type,names,pair,target):
    result=setup(fixture(names),part_type);pins=result['spec']['components'][0]['pin_properties']
    assert pins['1']['pair']==pair and pins['1']['polarity']=='P' and pins['2']['polarity']=='N'
    assert pins['1']['impedance_ohms']==target and result['interface_setup']['ready']


def test_saved_aliases_are_not_used_as_electrical_pin_names():
    spec=fixture(['1','2','VBUS','GND']);spec['components'][0]['symbol_layout']={'style':'parametric','pins':{'1':{'name':'D+'},'2':{'name':'D-'}}}
    result=setup(spec,'USB C');assert result['interface_setup']['matched_pins']==0
    assert not result['interface_setup']['ready'] and not result['spec']['components'][0].get('pin_properties')


def test_conflicting_manual_parameters_require_explicit_resolution_and_keep_pin_delay():
    spec=fixture(['D+','D-','VBUS','GND']);spec['components'][0]['pin_properties']={'1':{'impedance_ohms':100,'pin_delay_ps':22}}
    unresolved=setup(spec,'USB C');assert not unresolved['interface_setup']['ready']
    assert unresolved['interface_setup']['conflicts'][0]['field']=='impedance_ohms'
    kept=setup(spec,'USB C',conflict_policy='keep')['spec']['components'][0]['pin_properties']
    assert kept['1']['impedance_ohms']==100 and kept['2']['impedance_ohms']==100 and kept['1']['pin_delay_ps']==22
    replaced=setup(spec,'USB C',conflict_policy='replace')['spec']['components'][0]['pin_properties']
    assert replaced['1']['impedance_ohms']==90 and replaced['2']['impedance_ohms']==90 and replaced['1']['pin_delay_ps']==22


def test_incomplete_and_duplicate_differential_roles_are_reported_without_guessing():
    for names in (['TX0P','VBUS','GND','NC'],['D+','D+','D-','GND']):
        result=setup(fixture(names),'USB C');assert not result['interface_setup']['ready']
        assert result['interface_setup']['issues']


def test_different_usb_ports_never_collapse_into_one_pair():
    result=setup(fixture(['USB1_DP','USB1_DM','USB2_DP','USB2_DM']),'USB C');pins=result['spec']['components'][0]['pin_properties']
    assert pins['1']['pair']==pins['2']['pair'] and pins['3']['pair']==pins['4']['pair'] and pins['1']['pair']!=pins['3']['pair']


def test_typed_numeric_overrides_are_used_without_inventing_timing_or_tolerance():
    result=setup(fixture(['D+','D-','VBUS','GND']),'USB C',targets={'differential_ohms':95,'tolerance_pct':10})
    props=result['spec']['components'][0]['pin_properties']['1'];assert props['impedance_ohms']==95 and props['impedance_tolerance_pct']==10
    assert 'pn_skew_ps' not in props and 'pair_skew_ps' not in props and 'pin_delay_ps' not in props
    with pytest.raises(ValueError):setup(fixture(['D+','D-','VBUS','GND']),'USB C',targets={'differential_ohms':True})


def test_catalog_exposes_the_supported_profiles_to_the_web_editor(client):
    response=client.get('/api/workbench/interface-presets');assert response.status_code==200
    names={p['part_type'] for p in response.json()['profiles']}
    assert names=={'USB A','USB B','USB C','HDMI','PCIe x1','PCIe x2','PCIe x4','PCIe x8','PCIe x16','MIPI CSI','MIPI DSI','DDR3','DDR4'}


def test_native_interface_review_is_unsaved_and_preserves_real_connectivity(client):
    spec=fixture(['D+','D-','VBUS','GND']);pid=client.post('/api/workbench/projects',json={'title':'Interface preview','spec':spec}).json()['id']
    response=client.post(f'/api/workbench/projects/{pid}/buses/prepare',json={'base_version':1,'action':'interface','ref':'J1','part_type':'USB C'})
    assert response.status_code==200,response.text
    proposal=response.json();assert proposal['interface_setup']['ready'] and proposal['native_parity']['ok']
    assert proposal['spec']['nets']==spec['nets'] and proposal['base_version']==1
    saved=client.get('/api/projects/'+pid).json()['state'];assert saved['workbench']['version']==1 and 'part_type' not in saved['spec']['components'][0]


def test_unresolved_interface_conflicts_do_not_expose_an_applicable_native_proposal(client):
    spec=fixture(['D+','D-','VBUS','GND']);spec['components'][0]['pin_properties']={'1':{'impedance_ohms':100}}
    pid=client.post('/api/workbench/projects',json={'title':'Interface conflicts','spec':spec}).json()['id']
    response=client.post(f'/api/workbench/projects/{pid}/buses/prepare',json={'base_version':1,'action':'interface','ref':'J1','part_type':'USB C'})
    assert response.status_code==200,response.text
    assert response.json()['spec'] is None and response.json()['interface_setup']['conflicts']
    assert response.json()['validation'] is None,'Unexecuted draft validation must not look like zero findings'
    assert client.get('/api/projects/'+pid).json()['state']['workbench']['version']==1


def test_agent_does_not_apply_an_interface_before_conflict_resolution(client):
    from wholeboard import server,codex_bridge
    spec=fixture(['D+','D-','VBUS','GND']);spec['components'][0]['pin_properties']={'1':{'impedance_ohms':100}}
    pid=client.post('/api/workbench/projects',json={'title':'Agent interface conflicts','spec':spec}).json()['id'];p=server.mgr().get(pid)
    result=codex_bridge.execute_tool(p,'edit_bus_properties',{'action':'interface','ref':'J1','part_type':'USB C'},'agent')
    assert result['ok'] is False and result['needs_interface_review'] and p.state['workbench']['version']==1


def test_generic_part_type_does_not_clear_an_existing_interface_type():
    spec=fixture(['D+','D-','VBUS','GND']);spec['components'][0]['bus_type']='Custom'
    result=buses.prepare(spec,{'action':'component','ref':'J1','patch':{'part_type':'Connector'}})
    assert result['spec']['components'][0]['part_type']=='Connector' and result['spec']['components'][0]['bus_type']=='Custom'


def test_shorted_positive_negative_nets_cannot_be_accepted_as_a_pair():
    spec=fixture(['D+','D-','VBUS','GND']);spec['nets'][0]['pins'].append('J1.2');spec['nets'][1]['pins']=[]
    result=setup(spec,'USB C');assert not result['interface_setup']['ready'] and result['interface_setup']['issues']


def test_ddr_lower_upper_strobes_and_masks_keep_byte_lane_identity():
    result=setup(fixture(['LDQS','~{LDQS}','UDQS','~{UDQS}','LDM','UDM']),'DDR3');pins=result['spec']['components'][0]['pin_properties']
    assert result['interface_setup']['ready']
    assert pins['1']['pair']=='DDR3_DQS0' and pins['2']['polarity']=='N' and pins['3']['pair']=='DDR3_DQS1' and pins['4']['polarity']=='N'
    assert pins['5']['bus_group']=='DDR3_DATA0' and pins['6']['bus_group']=='DDR3_DATA1'


def test_zero_tolerance_is_explicit_rather_than_treated_as_missing():
    result=setup(fixture(['D+','D-','VBUS','GND']),'USB C',targets={'tolerance_pct':0})
    assert result['spec']['components'][0]['pin_properties']['1']['impedance_tolerance_pct']==0


def test_real_usb_c_symbol_mirrored_data_contacts_need_no_pin_name_guesses():
    spec=fixture(['D+','D-','VBUS','GND']);spec['components'][0]['symbol']='Connector:USB_C_Receptacle_USB2.0_16P'
    spec['nets']=[{'name':'DP','pins':['J1.A6','J1.B6']},{'name':'DN','pins':['J1.A7','J1.B7']}]
    result=setup(spec,'USB C');props=result['spec']['components'][0]['pin_properties']
    assert result['interface_setup']['ready'] and result['interface_setup']['matched_pins']==4
    assert set(props)=={'A6','B6','A7','B7'} and props['A6']['pair']==props['B6']['pair']==props['A7']['pair']
    assert props['B7']['polarity']=='N'


def test_pcie_lane_outside_selected_width_is_not_silently_configured():
    result=setup(fixture(['TX1P','TX1N','GND','VBUS']),'PCIe x1')
    assert not result['interface_setup']['ready'] and result['interface_setup']['issues']
    assert not result['spec']['components'][0].get('pin_properties')
