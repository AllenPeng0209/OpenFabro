import copy
import importlib
import json
import math
from pathlib import Path

import pytest


def tuning():return importlib.import_module('wholeboard.route_tuning')


def fixture():
    spec=json.loads((Path(__file__).parent/'fixtures/route-tuning.json').read_text())
    geo={'bbox':[100,100,160,145],'pads':[],'tracks':[],'arcs':[],'vias':[],'zones':[],'zone_sources':[],'layers':['F.Cu','In1.Cu','In2.Cu','B.Cu']}
    for ref,x in [('J1',108),('J2',150)]:
        for i,net in enumerate(['DP','DN','CLK','REF']):geo['pads'].append({'id':ref+'-'+str(i+1),'ref':ref,'name':str(i+1),'net':net,'x':x,'y':108+2.54*i,'w':1.7,'h':1.7,'kind':'thru_hole','shape':'rect' if i==0 else 'oval','layers':['*.Cu','*.Mask']})
    return spec,copper_geo(spec,geo)


def copper_geo(spec,geo):
    geo=copy.deepcopy(geo)
    for kind,keys in [('tracks',['a','b']),('arcs',['a','m','b']),('vias',['p'])]:
        geo[kind]=[]
        for group in spec['fixed_copper']:
            for primitive in group.get(kind,[]):
                item={**copy.deepcopy(primitive),'net':group['net']}
                for key in keys:item[key]=[item[key][i]+100 for i in range(2)]
                geo[kind].append(item)
    return geo


def test_measurement_trims_end_pads_and_reports_explicit_delay_only():
    spec,geo=fixture();rows={r['net']:r for r in tuning().inspect(spec,geo)['routes']}
    assert rows['CLK']['length_mm']==pytest.approx(40.3,abs=1e-6)
    assert rows['REF']['length_mm']==pytest.approx(59.06,abs=1e-6)
    assert rows['CLK']['delay_ps']==pytest.approx(282.1,abs=1e-6)
    assert rows['CLK']['ready']
    spec['board'].pop('timing');assert tuning().inspect(spec,geo)['routes'][2]['delay_ps'] is None


@pytest.mark.parametrize('style',['trombone','accordion','sawtooth'])
def test_tuning_to_absolute_length_creates_real_copper_and_keeps_other_routes(style):
    spec,geo=fixture();original=copy.deepcopy(spec)
    result=tuning().prepare(spec,geo,{'nets':['CLK'],'target_mm':55,'tolerance_mm':.01,'style':style,'radius_mm':.5})
    assert spec==original
    for key in ['board','rules','components','nets']:assert result['spec'][key]==original[key]
    after=copper_geo(result['spec'],geo);rows={r['net']:r for r in tuning().inspect(result['spec'],after)['routes']}
    assert rows['CLK']['length_mm']==pytest.approx(55,abs=.01)
    assert after['arcs'] and all(a['net']=='CLK' for a in after['arcs'])
    for net in ['DP','DN','REF']:
        for kind in ['tracks','arcs','vias']:assert [v for v in after[kind] if v['net']==net]==[v for v in geo[kind] if v['net']==net]
    assert '44444444-4444-4444-8444-000000000003' in {p['id'] for p in after['tracks']+after['arcs']}


def test_reference_matching_and_delay_targets_have_explicit_units():
    spec,geo=fixture()
    matched=tuning().prepare(spec,geo,{'nets':['CLK'],'reference_net':'REF','tolerance_mm':.01})
    assert matched['summary']['measurements'][0]['target_mm']==pytest.approx(59.06,abs=1e-6)
    assert matched['summary']['measurements'][0]['after_length_mm']==pytest.approx(59.06,abs=.01)
    delayed=tuning().prepare(spec,geo,{'nets':['CLK'],'target_delay_ps':420,'tolerance_mm':.01})
    assert delayed['summary']['measurements'][0]['after_delay_ps']==pytest.approx(420,abs=.07)
    spec['board'].pop('timing')
    with pytest.raises(ValueError,match='propagation|delay model'):tuning().prepare(spec,geo,{'nets':['CLK'],'target_delay_ps':420})


def test_declared_pair_tuning_retains_coupled_arcs_and_reaches_both_targets():
    spec,geo=fixture();result=tuning().prepare(spec,geo,{'nets':['DP','DN'],'target_mm':50,'tolerance_mm':.01})
    after=copper_geo(result['spec'],geo);rows={r['net']:r for r in tuning().inspect(result['spec'],after)['routes']}
    assert rows['DP']['length_mm']==pytest.approx(50,abs=.01)
    assert rows['DN']['length_mm']==pytest.approx(50,abs=.01)
    assert result['summary']['coupled_pairs']==[['DP','DN']]
    arcs=[[a for a in after['arcs'] if a['net']==net] for net in ['DP','DN']]
    assert len(arcs[0])==len(arcs[1])==4
    from wholeboard.tuning_geometry import arc_circle
    for a,b in zip(*arcs):assert arc_circle(a)[0]==pytest.approx(arc_circle(b)[0],abs=1e-5)
    assert not after['vias']


def test_selecting_one_physical_trace_can_tune_its_declared_pair_without_selecting_both_ids():
    spec,geo=fixture();result=tuning().prepare(spec,geo,{'nets':['DN','DP'],'track_ids':['44444444-4444-4444-8444-000000000002'],'target_mm':50,'tolerance_mm':.01})
    assert len(result['summary']['measurements'])==2 and result['summary']['coupled_pairs']==[['DP','DN']]


def test_ambiguous_branched_or_incomplete_paths_are_not_claimed_measurable():
    spec,geo=fixture();geo['tracks'].append({'id':'branch','net':'CLK','a':[129,113.08],'b':[129,120],'w':.25,'layer':'F.Cu'})
    row=next(r for r in tuning().inspect(spec,geo)['routes'] if r['net']=='CLK');assert not row['ready'] and row['length_mm'] is None
    with pytest.raises(ValueError,match='branched|ambiguous|simple'):tuning().prepare(spec,geo,{'nets':['CLK'],'target_mm':55})


def test_infeasible_target_and_bad_settings_leave_the_source_untouched():
    spec,geo=fixture();before=copy.deepcopy(spec)
    for patch in [{'target_mm':30},{'target_mm':55,'max_amplitude_mm':.01},{'target_mm':55,'style':'fake'},{'target_mm':True},{'target_mm':55,'tolerance_mm':0},{'target_mm':55,'reference_net':'REF'}]:
        with pytest.raises(ValueError):tuning().prepare(spec,geo,{'nets':['CLK'],**patch})
        assert spec==before


def test_a_route_reentering_its_endpoint_pad_cannot_count_a_shorted_detour():
    spec,geo=fixture();geo['pads']=[{**geo['pads'][2],'x':100,'y':100,'w':2,'h':2,'shape':'circle'},{**geo['pads'][6],'x':110,'y':100,'w':2,'h':2,'shape':'circle'}]
    points=[[100,100],[100,103],[98,103],[98,100.5],[102,100.5],[110,100]]
    geo['tracks']=[{'id':str(i),'net':'CLK','layer':'F.Cu','w':.25,'a':a,'b':b} for i,(a,b) in enumerate(zip(points,points[1:]))]
    row=next(r for r in tuning().inspect(spec,geo)['routes'] if r['net']=='CLK')
    assert not row['ready'] and row['length_mm'] is None,'The pad shorts this detour; it has no unique electrical length'


@pytest.mark.parametrize('flag',['true',1,None])
def test_preview_flag_is_a_strict_boolean_before_any_tuning(flag):
    spec,geo=fixture()
    with pytest.raises(ValueError,match='preview_only'):tuning().prepare(spec,geo,{'nets':['CLK'],'target_mm':55,'preview_only':flag})


def test_raw_drc_classification_keeps_changed_constraint_details_and_multiplicity(tmp_path):
    old={'type':'clearance','severity':'error','description':'clearance 0.15mm; requires0.2mm','items':[{'uuid':'a','description':'track','pos':{'x':1,'y':2}}]};new={**old,'description':'clearance 0.05mm; requires0.2mm'}
    a=tmp_path/'a.json';b=tmp_path/'b.json';a.write_text(json.dumps({'violations':[old]}));b.write_text(json.dumps({'violations':[new]}))
    assert tuning()._violation_keys(a)!=tuning()._violation_keys(b),'A worsened deficit was collapsed into the baseline key'
    b.write_text(json.dumps({'violations':[old,old]}));assert tuning()._violation_keys(a)!=tuning()._violation_keys(b),'A second native finding was collapsed into one key'


def test_preserved_track_keepout_is_not_treated_as_a_refillable_pour():
    spec,geo=fixture();geo['zone_sources']=[{'net':'','layers':['F.Cu'],'origin':[100,100],'source':'(zone (net 0) (layer "F.Cu") (keepout (tracks not_allowed)) (polygon (pts (xy 101 101) (xy 159 101) (xy 159 144) (xy 101 144))))'}]
    with pytest.raises(ValueError,match='No clear meander'):tuning().prepare(spec,geo,{'nets':['CLK'],'target_mm':55})


@pytest.mark.parametrize('points',[
 [[0,0],[0,3],[4,3],[4,3.2],[8,3.2],[8,0],[10,0]],
 [[0,0],[0,3],[6,3],[6,3.2],[2,3.2],[2,6],[10,6],[10,0]],
])
def test_nonadjacent_finite_width_contact_cannot_count_a_shorted_path(points):
    spec,geo=fixture();geo['pads']=[{**geo['pads'][2],'x':100,'y':100,'w':.8,'h':.8,'shape':'circle'},{**geo['pads'][6],'x':110,'y':100,'w':.8,'h':.8,'shape':'circle'}]
    geo['tracks']=[{'id':str(i),'net':'CLK','layer':'F.Cu','w':.5,'a':[a[0]+100,a[1]+100],'b':[b[0]+100,b[1]+100]} for i,(a,b) in enumerate(zip(points,points[1:]))];geo['arcs']=[]
    row=tuning()._route(spec,geo,'CLK');assert not row['ready'] and row['length_mm'] is None
    assert any(word in row['reason'] for word in ['contact','shortcut','overlap'])


def test_legitimate_tight_rounded_corners_keep_their_unique_measured_length():
    from wholeboard import tuning_geometry
    spec,geo=fixture();pattern=tuning_geometry.pattern(42,1,radius=.15,pitch=1,loops=1)
    geo['tracks']=[p for p in geo['tracks'] if p['net']!='CLK'];geo['arcs']=[]
    for index,p in enumerate(pattern['primitives']):
        value={**p,'id':str(index),'net':'CLK','w':.25,'layer':'F.Cu'}
        for key in ['a','m','b']:
            if key in p:value[key]=[p[key][0]+108,p[key][1]+113.08]
        geo[value.pop('kind')].append(value)
    row=tuning()._route(spec,geo,'CLK');assert row['ready'],row
    assert row['length_mm']==pytest.approx(41.3,abs=.001)


def test_a_via_bridging_nonadjacent_trace_bodies_makes_length_unknown():
    spec,geo=fixture();geo['pads']=[{**geo['pads'][2],'x':100,'y':100,'w':.8,'h':.8,'shape':'circle'},{**geo['pads'][6],'x':110,'y':100,'w':.8,'h':.8,'shape':'circle'}];points=[[0,0],[0,3],[6,3],[6,3.7],[2,3.7],[2,6],[10,6],[10,0]]
    geo['tracks']=[{'id':str(i),'net':'CLK','layer':'F.Cu','w':.25,'a':[a[0]+100,a[1]+100],'b':[b[0]+100,b[1]+100]} for i,(a,b) in enumerate(zip(points,points[1:]))];geo['arcs']=[];geo['vias']=[{'id':'via-bridge','net':'CLK','p':[104,103.35],'d':1,'drill':.3,'layers':['F.Cu','B.Cu']}]
    row=tuning()._route(spec,geo,'CLK');assert not row['ready'] and row['length_mm'] is None


def test_intended_short_landing_segments_at_a_through_via_remain_one_path():
    spec,geo=fixture();geo['tracks']=[p for p in geo['tracks'] if p['net']!='CLK']
    for index,(a,b,layer) in enumerate([([108,113.08],[120,113.08],'F.Cu'),([120,113.08],[120,112.93],'F.Cu'),([120,112.93],[120,113.08],'B.Cu'),([120,113.08],[150,113.08],'B.Cu')]):geo['tracks'].append({'id':'landing-'+str(index),'net':'CLK','a':a,'b':b,'w':.25,'layer':layer})
    geo['vias']=[{'id':'landing-via','net':'CLK','p':[120,112.93],'d':.6,'drill':.3,'layers':['F.Cu','B.Cu']}]
    row=tuning()._route(spec,geo,'CLK');assert row['ready'],row
    assert row['length_mm']==pytest.approx(40.6,abs=.001)


@pytest.mark.parametrize('side,expected',[('left',-1),('right',1)])
def test_explicit_side_matches_native_pcb_screen_direction(side,expected):
    spec,geo=fixture();geo['tracks']=[p for p in geo['tracks'] if p['net']=='CLK']
    result=tuning().prepare(spec,geo,{'nets':['CLK'],'target_mm':55,'side':side})
    points=[p[key] for kind in ['tracks','arcs'] for p in result['geometry'][kind] if p['net']=='CLK' for key in ['a','m','b'] if key in p]
    # Native PCB Y grows down: left of an eastbound trace is above it.
    assert all((p[1]-113.08)*expected>=-.0001 for p in points)
    assert any((p[1]-113.08)*expected>.5 for p in points)
