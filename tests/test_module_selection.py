"""Selection conversion must keep the source PCB and capture real clipped native copper."""
import copy
from pathlib import Path
import math
import pytest
from wholeboard import modules,sexpr,project_library
from wholeboard.kicad import board,geometry,schematic,cli


def specimen():
    spec={'name':'selected_module','board':{'width_mm':40,'height_mm':24,'layers':2,'ground_pour':None},
          'components':[{'ref':ref,'value':'10k','symbol':'Device:R','footprint':'Resistor_SMD:R_0603_1608Metric','placement':{'x_mm':x,'y_mm':10}} for ref,x in [('R1',8),('R2',12),('R3',30)]],
          'nets':[{'name':'SIGNAL','pins':['R1.1','R2.1','R3.1']},{'name':'GND','class':'power','pins':['R1.2','R2.2','R3.2']}],
          'editor':{'positions':{'R1':[200,220],'R2':[500,220],'R3':[800,220]},'connection_guides':[{'id':'inside','from':'R1.1','to':'R2.1'},{'id':'outside','from':'R2.1','to':'R3.1'}]},
          'fixed_copper':[{'net':'SIGNAL','tracks':[{'a':[5,8],'b':[35,8],'w':.25,'layer':'F.Cu'}]}]}
    return spec


def native(spec,tmp_path):return geometry.read(Path(board.build(spec,tmp_path)['pcb']))


def test_convert_selection_wraps_a_real_hierarchy_and_keeps_source_connections_and_native_copper(tmp_path):
    spec=specimen();before=copy.deepcopy(spec);geo=native(spec,tmp_path/'source')
    assert hasattr(modules,'convert_selection'),'Selection to component conversion is missing'
    result=modules.convert_selection(spec,['R1','R2'],'Divider','M1',name='Divider',native_geometry=geo,bounds=[5,6,15,14])
    out=result['spec'];asset=out['library']['modules']['Divider']
    assert spec==before
    assert out['nets']==spec['nets']
    assert [c['placement'] for c in out['components']]==[c['placement'] for c in spec['components']]
    assert [c.get('sheet','') for c in out['components']]==['M1','M1','']
    assert {c['ref'] for c in asset['design']['components']}=={'R1','R2'}
    assert {p['net'] for p in asset['ports'].values()}=={'SIGNAL','GND'}
    assert 'R3.1' not in asset['design']['nets'][0]['pins']
    assert out['editor']['connection_guides'][1]['from']=='sheet:M1.SIGNAL'
    assert out['editor']['connection_guides'][0]['from']=='R1.1'
    assert out['fixed_copper'][0]['tracks'][0]['a']==[5,8]
    rebuilt=native(out,tmp_path/'converted');assert rebuilt['tracks']==geo['tracks']
    sch=schematic.build(out,tmp_path/'sch')
    if cli.find_kicad_cli():assert schematic.netlist_parity(out,cli.schematic_nets(Path(sch['sch'])))['ok']


def test_selection_clips_cross_boundary_lines_and_arcs_without_importing_external_copper(tmp_path):
    spec=specimen();spec['fixed_copper'][0]['arcs']=[{'a':[5,10],'m':[10,5],'b':[15,10],'w':.25,'layer':'F.Cu'}]
    geo=native(spec,tmp_path/'source')
    assert hasattr(modules,'convert_selection'),'Selection capture is missing'
    result=modules.convert_selection(spec,['R1','R2'],'ArcBlock','M1',name='Arc block',native_geometry=geo,bounds=[6,4,14,12])
    design=result['spec']['library']['modules']['ArcBlock']['design'];copper=design['fixed_copper'][0]
    assert copper['tracks'][0]['a']==[0,4] and copper['tracks'][0]['b']==[8,4]
    arc=copper['arcs'][0]
    assert arc['a']==pytest.approx([0,3],abs=1e-5) and arc['b']==pytest.approx([8,3],abs=1e-5)
    assert arc['m']==pytest.approx([4,1],abs=1e-5)
    assert len(copper['arcs'])==1 and result['capture']['clipped_arcs']==1
    assert result['capture']['bounds']==[6,4,14,12]


def test_clipped_zone_preserves_holes_priority_and_avoids_unselected_footprints(tmp_path):
    spec=specimen();spec['components'][2]['placement']['x_mm']=10;spec['components'][2]['placement']['y_mm']=12
    zone=board.zone('GND','F.Cu',40,24,.5,.25,priority=4)
    # The second polygon is a native zone cutout, not a second filled island.
    zone.append(sexpr.S(sexpr.Sym('polygon'),sexpr.S(sexpr.Sym('pts'),*[sexpr.S(sexpr.Sym('xy'),x,y) for x,y in [(107.5,107),(108.5,107),(108.5,108),(107.5,108)]])))
    spec['fixed_zones']=[{'net':'GND','origin':[100,100],'source':sexpr.dumps(zone)}]
    geo=native(spec,tmp_path/'source')
    assert hasattr(modules,'convert_selection'),'Zone clipping is missing'
    out=modules.convert_selection(spec,['R1','R2'],'WithPour','M1',name='With pour',native_geometry=geo,bounds=[5,6,15,14])
    template=out['spec']['library']['modules']['WithPour']['design'];assert template['fixed_zones']
    nodes=[sexpr.parse(z['source']) for z in template['fixed_zones']]
    assert all(str(sexpr.find(node,'priority')[1])=='4' for node in nodes)
    # Native round-trip must retain the hole near [8,7.5] and exclusion around R3.
    copied=native(template,tmp_path/'copy');assert copied['zone_sources']
    polygons=[[(float(p[1])-100,float(p[2])-100) for p in sexpr.find(poly,'pts')[1:] if sexpr.tag(p)=='xy'] for z in copied['zone_sources'] for poly in sexpr.find_all(sexpr.parse(z['source']),'polygon')]
    assert all(0<=x<=10 and 0<=y<=8 for polygon in polygons for x,y in polygon)
    assert sum(len(list(sexpr.find_all(node,'polygon'))) for node in nodes)>=2
    assert out['capture']['excluded_components']==['R3']
    if cli.find_kicad_cli():
        path=tmp_path/'copy'/'WithPour.kicad_pcb';cli.drc(path,refill=True,save=True);filled=geometry.read(path)['zones']
        from wholeboard.kicad.connectivity import _inside
        assert filled and any(_inside((101,103),item['pts']) for item in filled)
        assert not any(_inside((103,101.5),item['pts']) for item in filled),'The original hole was filled'
        assert not any(_inside((105,106),item['pts']) for item in filled),'The unselected footprint exclusion was filled'


def test_default_capture_keeps_an_internal_route_that_detours_outside_the_footprint_bounds(tmp_path):
    spec=specimen();spec['nets'][0]['pins']=['R1.1','R2.1'];spec['editor']['connection_guides']=spec['editor']['connection_guides'][:1];spec['fixed_copper'][0]['tracks']=[{'a':a,'b':b,'w':.25,'layer':'F.Cu'} for a,b in [([8,10],[8,2]),([8,2],[12,2]),([12,2],[12,10])]]
    geo=native(spec,tmp_path/'source');out=modules.convert_selection(spec,['R1','R2'],'Detour','M1',name='Detour',native_geometry=geo)
    tracks=out['spec']['library']['modules']['Detour']['design']['fixed_copper'][0]['tracks']
    assert len(tracks)==3 and sum(math.dist(t['a'],t['b']) for t in tracks)==pytest.approx(20)


def test_selection_package_contains_only_its_reachable_project_library_assets(tmp_path):
    import json
    spec=specimen();symbol=project_library.copy_installed('symbols','Device:R');symbol['footprint']='Project:Shared'
    unused=copy.deepcopy(symbol);unused['description']='PRIVATE_UNUSED_LIBRARY_ASSET'
    spec['library']={'symbols':{'Chosen':symbol,'Private':unused},'footprints':{'Shared':project_library.copy_installed('footprints','Resistor_SMD:R_0603_1608Metric')},'parts':{}}
    spec['components'][0].update(symbol='Project:Chosen',footprint='Project:Shared')
    geo=native(spec,tmp_path/'source');out=modules.convert_selection(spec,['R1'],'PrivateSafe','M1',name='Selected resistor',native_geometry=geo)
    asset=out['spec']['library']['modules']['PrivateSafe'];assert set(asset['design']['library']['symbols'])=={'Chosen'}
    assert 'PRIVATE_UNUSED_LIBRARY_ASSET' not in json.dumps(asset)
    assert 'Private' in out['spec']['library']['symbols']


def test_conversion_keeps_an_implicit_legacy_parent_when_all_its_parts_move_to_the_module(tmp_path):
    spec=specimen();spec['components'][0]['block']='Legacy';geo=native(spec,tmp_path/'source')
    out=modules.convert_selection(spec,['R1'],'LegacyBlock','M1',name='Nested block',native_geometry=geo)['spec']
    assert out['editor']['sheets']['M1']['parent']=='Legacy'
    sch=schematic.build(out,tmp_path/'sch');assert {p['name'] for p in sch['pages']}=={'','Legacy','M1'}
    if cli.find_kicad_cli():assert schematic.netlist_parity(out,cli.schematic_nets(Path(sch['sch'])))['ok']


def test_nested_conversion_preserves_a_parent_terminal_even_without_external_component_pins(tmp_path):
    spec=specimen();spec['nets'][0]['pins']=['R1.1','R2.1'];spec['editor']['connection_guides']=spec['editor']['connection_guides'][:1]
    for c in spec['components'][:2]:c['sheet']='Power'
    spec['editor']['sheets']={'Power':{'ports':{'OUT':{'net':'SIGNAL'}}}}
    geo=native(spec,tmp_path/'source');out=modules.convert_selection(spec,['R1','R2'],'Nested','M1',name='Nested',native_geometry=geo)['spec']
    assert 'SIGNAL' in {p['net'] for p in out['library']['modules']['Nested']['ports'].values()}
    sch=schematic.build(out,tmp_path/'sch')
    if cli.find_kicad_cli():assert cli.schematic_nets(Path(sch['sch']))['/SIGNAL']=={'R1.1','R2.1'}


def test_an_outdated_crossing_drawing_is_reported_without_changing_the_electrical_nets(tmp_path):
    spec=specimen();spec['nets'][0]['pins']=['R1.1','R2.1'];geo=native(spec,tmp_path/'source')
    result=modules.convert_selection(spec,['R1','R2'],'OldDrawing','M1',name='Old drawing',native_geometry=geo)
    assert result['spec']['nets']==spec['nets']
    assert result['capture']['omitted_guide_ids']==['outside']
    assert all(g['id']!='outside' for g in result['spec']['editor']['connection_guides'])
