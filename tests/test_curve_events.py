"""Native event locations must be independent of viewport samples and comb density."""
import hashlib
import json
from pathlib import Path
import pytest
from wholeboard import mechanical, codex_bridge
from test_mechanical_workflow import workspace
from test_mechanical_topology import scene


def profile(jump=False):
    poles=[[0,0],[2,0],[4,2],[8,-2],[10,-2],[12,0]] if jump else [[0,0],[4,4],[8,-4],[12,0]]
    knots=[0,0,0,0,.5,.5,1,1,1,1] if jump else [0,0,0,0,1,1,1,1]
    return {'schema':1,'name':'Native event profile','units':'mm','parameters':{},'features':[
        {'id':'profile','op':'sketch','geometry':[
            {'id':'curve','type':'bspline','degree':3,'poles':poles,'knots':knots},
            {'id':'right','type':'line','start':[12,0],'end':[12,-6]},
            {'id':'bottom','type':'line','start':[12,-6],'end':[0,-6]},
            {'id':'left','type':'line','start':[0,-6],'end':[0,0]}],'constraints':[]},
        {'id':'body','op':'extrude_shape','target':'profile','vector':[0,0,2]}],'result':'body'}


def test_native_bezier_inflections_do_not_depend_on_sixty_five_display_samples(workspace):
    _,p,_=workspace;model=mechanical.rebuild(p,{'path':'cad/inflection.cad.json','program':profile()});data=scene(p,model)
    curves=[edge for body in data['topology']['bodies'] for edge in body['edges'] if edge['surface']=='BSplineCurve']
    assert len(curves)==2
    for edge in curves:
        assert 'curve_events' in edge,'Native curve event analysis is missing'
        events=[v for v in edge['curve_events']['events'] if v['kind']=='inflection'];assert len(events)==1
        assert events[0]['parameter']==pytest.approx(.5,abs=1e-8)
        world=[a+b for a,b in zip(events[0]['point'],data['origin'])]
        assert world[:2]==pytest.approx([6,0],abs=1e-7)
        assert events[0]['signed_left']*events[0]['signed_right']<0


def test_native_c1_knot_distinguishes_a_curvature_jump_from_an_inflection(workspace):
    _,p,_=workspace;model=mechanical.rebuild(p,{'path':'cad/jump.cad.json','program':profile(True)});data=scene(p,model)
    curves=[edge for body in data['topology']['bodies'] for edge in body['edges'] if edge['surface']=='BSplineCurve']
    for edge in curves:
        assert 'curve_events' in edge,'Native knot limits are missing'
        events=edge['curve_events']['events'];inflections=[e for e in events if e['kind']=='inflection'];jumps=[e for e in events if e['kind']=='curvature_jump']
        assert len(inflections)==1 and inflections[0]['parameter']==pytest.approx(1/6,abs=1e-8)
        assert len(jumps)==1 and jumps[0]['parameter']==pytest.approx(.5,abs=1e-12)
        assert jumps[0]['tangent_angle_deg']==pytest.approx(0,abs=1e-6)
        assert jumps[0]['curvature_left']==pytest.approx(2**.5/6,abs=1e-8)
        assert jumps[0]['curvature_right']==pytest.approx(2**.5/12,abs=1e-8)


def test_native_wire_line_arc_joins_report_curvature_jumps_without_promoting_corners(workspace):
    _,p,_=workspace
    code={'schema':1,'name':'Tangent arc profile','units':'mm','parameters':{},'features':[
        {'id':'profile','op':'sketch','geometry':[
            {'id':'bottom','type':'line','start':[0,0],'end':[4,0]},
            {'id':'arc','type':'arc','center':[4,2],'radius':2,'start_angle':-90,'end_angle':0},
            {'id':'right','type':'line','start':[6,2],'end':[6,6]},
            {'id':'top','type':'line','start':[6,6],'end':[0,6]},
            {'id':'left','type':'line','start':[0,6],'end':[0,0]}],'constraints':[]},
        {'id':'body','op':'extrude_shape','target':'profile','vector':[0,0,2]}],'result':'body'}
    model=mechanical.rebuild(p,{'path':'cad/joins.cad.json','program':code});data=scene(p,model);body=data['topology']['bodies'][0]
    assert 'curve_events' in body,'Native wire adjacency analysis is missing'
    jumps=[e for e in body['curve_events']['events'] if e['kind']=='curvature_jump']
    assert len(jumps)==4
    points=sorted(tuple(round(a+b,6) for a,b in zip(e['point'],data['origin'])) for e in jumps)
    assert points==[(4,0,0),(4,0,2),(6,2,0),(6,2,2)]
    assert all(e['tangent_angle_deg']<1e-6 and e['curvature_delta']==pytest.approx(.5,abs=1e-8) for e in jumps)


def test_native_rational_inflections_and_spatial_unknowns_are_not_guessed(tmp_path):
    import os,subprocess
    from wholeboard import enclosure
    command=enclosure.find_freecad()
    if not command:pytest.skip('FreeCAD is not installed')
    script=tmp_path/'probe.py';output=tmp_path/'events.json'
    script.write_text('import sys\nsys.path.insert(0,'+repr(str(Path(mechanical.__file__).parent))+')\n'+'''import json
import FreeCAD as App
import Part
from freecad_curve_events import analyse_edge
doc=App.newDocument('Events')
def edge(poles,weights=None):
 c=Part.BSplineCurve();c.buildFromPolesMultsKnots([App.Vector(*p) for p in poles],[4,4],[0,1],False,3,weights or [1,1,1,1]);return c.toShape()
planar=edge([(0,0,0),(4,4,0),(8,-4,0),(12,0,0)],[1,2,2,1])
spatial=edge([(0,0,0),(4,4,0),(8,-4,1),(12,0,0)])
cusp=edge([(.25,-.125,0),(-1/12,.125,0),(-1/12,-.125,0),(.25,.125,0)])
b=Part.BezierCurve();b.setPoles([App.Vector(x,y,0) for x,y in [(0,0),(4,4),(8,-4),(12,0)]])
trimmed=b.toShape(.1,.7);excluded=b.toShape(.1,.4)
d=Part.BSplineCurve();d.buildFromPolesMultsKnots([App.Vector(x,y,z) for x,y,z in [(0,0,0),(2,0,0),(4,2,0),(8,-2,0),(10,-2,1),(12,0,2)]],[4,2,4],[0,.5,1],False,3)
planar_trim=d.toShape(0,.5)
result={name:analyse_edge(value,[0,0,0],{'remaining':100000}) for name,value in [('rational',planar),('spatial',spatial),('cusp',cusp),('trimmed',trimmed),('excluded',excluded),('planar_trim',planar_trim)]}
open('''+repr(str(output))+''','w').write(json.dumps(result))
App.closeDocument(doc.Name)
''')
    result=subprocess.run(command+[str(script)],cwd=tmp_path,env={**os.environ,'QT_QPA_PLATFORM':'offscreen'},capture_output=True,text=True,timeout=30)
    assert result.returncode==0 and output.exists(),result.stdout+result.stderr
    data=json.loads(output.read_text());roots=[e for e in data['rational']['events'] if e['kind']=='inflection'];assert len(roots)==1 and roots[0]['parameter']==pytest.approx(.5,abs=1e-8)
    assert not data['spatial']['inflections_available'] and not any(e['kind']=='inflection' for e in data['spatial']['events'])
    assert any(e['kind']=='singular' for e in data['cusp']['events']) and not any(e['kind']=='inflection' for e in data['cusp']['events'])
    trimmed=[e for e in data['trimmed']['events'] if e['kind']=='inflection'];assert len(trimmed)==1 and trimmed[0]['parameter']==pytest.approx(.5,abs=1e-8)
    assert not any(e['kind']=='inflection' for e in data['excluded']['events'])
    partial=[e for e in data['planar_trim']['events'] if e['kind']=='inflection'];assert data['planar_trim']['inflections_available'] and len(partial)==1 and partial[0]['parameter']==pytest.approx(1/6,abs=1e-8)


def test_curve_event_agent_pages_are_placed_hash_pinned_and_read_only(workspace):
    _,p,_=workspace;mechanical.rebuild(p,{'path':'cad/inflection.cad.json','program':profile()})
    assembly={'schema':1,'name':'Placed inflection','units':'mm','parameters':{},'features':[
        {'id':'part','op':'component','source':{'kind':'model','path':'cad/inflection.cad.json'},'translation':[100,200,10],'rotation':{'axis':[0,0,1],'angle':90}},
        {'id':'product','op':'assembly','members':['part'],'fixed':['part']}],'result':'product'}
    model=mechanical.rebuild(p,{'path':'cad/product.cad.json','program':assembly})
    assert 'inspect_mechanical_curve_events' in codex_bridge.READ_TOOLS,'Agent cannot inspect real curve events'
    before={f['path']:(hashlib.sha256((p.root/f['path']).read_bytes()).hexdigest(),(p.root/f['path']).stat().st_mtime_ns) for f in model['files']}
    args={'source':'cad/product.cad.json','kind':'inflection','limit':1}
    first=codex_bridge.execute_tool(p,'inspect_mechanical_curve_events',args,'chat')
    assert first['total']==2 and first['next_offset']==1
    event=first['events'][0];assert event['member_id']=='part'
    world=[a+b for a,b in zip(event['point'],first['origin_mm'])];assert world[:2]==pytest.approx([100,206],abs=1e-7)
    with pytest.raises(ValueError,match='changed|SHA|snapshot'):
        codex_bridge.execute_tool(p,'inspect_mechanical_curve_events',{**args,'expected_scene_sha256':'0'*64},'chat')
    for name,value in before.items():
        path=p.root/name;assert (hashlib.sha256(path.read_bytes()).hexdigest(),path.stat().st_mtime_ns)==value
    assert p.state['workbench']['version']==1 and not p.engine_busy
