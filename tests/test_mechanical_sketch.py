"""Native constraint solving must drive editable solid features, not just display seeds."""
import copy,hashlib,json,math,subprocess
from pathlib import Path
import pytest
from wholeboard import mechanical,enclosure,codex_bridge
from test_mechanical_workflow import workspace


def plate(width=30,height=20,depth=4):
    geometry=[{'id':'bottom','type':'line','start':[0,0],'end':[29,0]},{'id':'right','type':'line','start':[29,0],'end':[29,19]},{'id':'top','type':'line','start':[29,19],'end':[0,19]},{'id':'left','type':'line','start':[0,19],'end':[0,0]},{'id':'hole','type':'circle','center':[15,10],'radius':2}]
    constraints=[{'id':'join_'+str(i),'type':'coincident','refs':[{'entity':a,'point':'end'},{'entity':b,'point':'start'}]} for i,(a,b) in enumerate([('bottom','right'),('right','top'),('top','left'),('left','bottom')])]
    constraints += [{'id':'horizontal_'+name,'type':'horizontal','refs':[{'entity':name}]} for name in ('bottom','top')]
    constraints += [{'id':'vertical_'+name,'type':'vertical','refs':[{'entity':name}]} for name in ('right','left')]
    constraints += [{'id':'anchor','type':'coincident','refs':[{'entity':'bottom','point':'start'},{'entity':'origin'}]},
                    {'id':'width_dim','type':'distance','refs':[{'entity':'bottom'}],'value':'width'},
                    {'id':'height_dim','type':'distance','refs':[{'entity':'right'}],'value':'height'},
                    {'id':'hole_x','type':'distance_x','refs':[{'entity':'hole','point':'center'}],'value':'width/2'},
                    {'id':'hole_y','type':'distance_y','refs':[{'entity':'hole','point':'center'}],'value':'height/2'},
                    {'id':'hole_radius','type':'radius','refs':[{'entity':'hole'}],'value':'hole_radius'}]
    return {'schema':1,'name':'Constrained plate','units':'mm','parameters':{'width':{'value':width,'unit':'mm'},'height':{'value':height,'unit':'mm'},'depth':{'value':depth,'unit':'mm'},'hole_radius':{'value':2,'unit':'mm'}},'features':[{'id':'profile','op':'sketch','geometry':geometry,'constraints':constraints,'require_fully_constrained':True},{'id':'pad','op':'extrude_shape','target':'profile','vector':[0,0,'depth']}],'result':'pad'}


def test_native_sketch_dimensions_override_seed_geometry_and_keep_the_cutout(workspace):
    _,p,_=workspace
    try:built=mechanical.rebuild(p,{'path':'cad/sketch.cad.json','program':plate()})
    except ValueError as error:pytest.fail('Native constrained sketch modeling is missing: '+str(error))
    proof=built['metrics']['sketches']['profile'];assert proof['dof']==0 and proof['fully_constrained'] and proof['solver_code']==0
    assert built['metrics']['size_mm']==pytest.approx([30,20,4]) and built['metrics']['volume_mm3']==pytest.approx((600-4*math.pi)*4)
    hole=next(g for g in proof['geometry'] if g['id']=='hole');assert hole['center']==pytest.approx([15,10]) and hole['radius']==pytest.approx(2)
    assert built['metrics']['step_metadata_verified'] and len(proof['constraints'])==14 and p.state['workbench']['version']==1 and not (p.root/'native').exists()


def test_parameter_change_resolves_the_same_sketch_constraints_and_preserves_old_assets(workspace):
    _,p,_=workspace
    try:first=mechanical.rebuild(p,{'path':'cad/sketch.cad.json','program':plate()})
    except ValueError as error:pytest.fail('Native sketch dimensions are missing: '+str(error))
    files={f['path']:(hashlib.sha256((p.root/f['path']).read_bytes()).hexdigest(),(p.root/f['path']).stat().st_mtime_ns) for f in first['files']};source=p.root/'cad/sketch.cad.json';code=plate(40)
    second=mechanical.rebuild(p,{'path':'cad/sketch.cad.json','program':code,'expected_sha256':hashlib.sha256(source.read_bytes()).hexdigest()});assert second['metrics']['size_mm']==pytest.approx([40,20,4]);proof=second['metrics']['sketches']['profile'];assert proof['dof']==0
    assert next(g for g in proof['geometry'] if g['id']=='hole')['center']==pytest.approx([20,10])
    assert all((hashlib.sha256((p.root/n).read_bytes()).hexdigest(),(p.root/n).stat().st_mtime_ns)==v for n,v in files.items())


def test_conflicting_sketch_dimensions_do_not_replace_the_saved_source(workspace):
    _,p,_=workspace
    try:first=mechanical.rebuild(p,{'path':'cad/sketch.cad.json','program':plate()})
    except ValueError as error:pytest.fail('Native sketch solver is missing: '+str(error))
    source=p.root/'cad/sketch.cad.json';before=source.read_bytes();code=plate();code['features'][0]['constraints'].append({'id':'contradict_width','type':'distance','refs':[{'entity':'bottom'}],'value':40})
    with pytest.raises((ValueError,RuntimeError),match='conflict|redundant|constraint|solve') as error:
        mechanical.rebuild(p,{'path':'cad/sketch.cad.json','program':code,'expected_sha256':hashlib.sha256(before).hexdigest()})
    assert 'width_dim' in str(error.value) or 'contradict_width' in str(error.value),'Constraint conflicts must name source dimensions'
    assert source.read_bytes()==before and p.state['workbench_mechanical']['cad/sketch.cad.json']['asset_id']==first['asset_id']


def test_exported_fcstd_retains_native_sketch_to_extrusion_dependency(workspace,tmp_path):
    _,p,_=workspace
    try:built=mechanical.rebuild(p,{'path':'cad/sketch.cad.json','program':plate()})
    except ValueError as error:pytest.fail('Native sketch feature chain is missing: '+str(error))
    filename=str(p.root/next(f['path'] for f in built['files'] if f['name']=='part.FCStd'));script=tmp_path/'native_edit.py';output=tmp_path/'proof.json'
    script.write_text('''import FreeCAD as App,json
from pathlib import Path
doc=App.openDocument(FILE);sketch=next(o for o in doc.Objects if o.TypeId=='Sketcher::SketchObject');pad=next(o for o in doc.Objects if o.TypeId=='Part::Extrusion');parameters=next(o for o in doc.Objects if 'p_width' in o.PropertiesList);parameters.p_width=40;parameters.p_depth=6;doc.recompute();circle=next(g for g in sketch.Geometry if type(g).__name__=='Circle');Path(OUTPUT).write_text(json.dumps({'width':pad.Shape.BoundBox.XLength,'depth':pad.Shape.BoundBox.ZLength,'volume':pad.Shape.Volume,'linked':pad.Base==sketch,'hole_x':circle.Center.x}))
'''.replace('FILE',repr(filename)).replace('OUTPUT',repr(str(output))))
    result=subprocess.run(enclosure.find_freecad()+[str(script)],cwd=tmp_path,capture_output=True,text=True,timeout=30);assert result.returncode==0 and output.is_file(),result.stdout+result.stderr;proof=json.loads(output.read_text());assert proof['linked'] and proof['width']==pytest.approx(40) and proof['depth']==pytest.approx(6) and proof['volume']==pytest.approx((800-4*math.pi)*6) and proof['hole_x']==pytest.approx(20)


def test_underconstrained_and_reference_dimensions_report_real_remaining_freedom(workspace):
    _,p,_=workspace;code={'schema':1,'name':'Free circle','units':'mm','parameters':{},'features':[{'id':'profile','op':'sketch','geometry':[{'id':'circle','type':'circle','center':[0,0],'radius':2}],'constraints':[{'id':'measured_radius','type':'radius','refs':[{'entity':'circle'}],'value':2,'driving':False}]},{'id':'pad','op':'extrude_shape','target':'profile','vector':[0,0,3]}],'result':'pad'}
    built=mechanical.rebuild(p,{'path':'cad/free.cad.json','program':code});proof=built['metrics']['sketches']['profile'];assert proof['dof']==3 and not proof['fully_constrained'];assert not proof['constraints'][0]['driving'] and proof['constraints'][0]['solved_value']==pytest.approx(2)
    source=p.root/'cad/free.cad.json';code['features'][0]['require_fully_constrained']=True
    with pytest.raises((ValueError,RuntimeError),match='underconstrained|freedom'):
        mechanical.rebuild(p,{'path':'cad/free.cad.json','program':code,'expected_sha256':hashlib.sha256(source.read_bytes()).hexdigest()})
    assert p.state['workbench_mechanical']['cad/free.cad.json']['asset_id']==built['asset_id']


@pytest.mark.parametrize('geometry,expected_volume',[
    ([{'id':'ellipse','type':'ellipse','center':[0,0],'major_radius':5,'minor_radius':3,'angle':30}],30*math.pi),
    ([{'id':'top','type':'line','start':[-5,2],'end':[5,2]},{'id':'right','type':'arc','center':[5,0],'radius':2,'start_angle':-90,'end_angle':90},{'id':'bottom','type':'line','start':[-5,-2],'end':[5,-2]},{'id':'left','type':'arc','center':[-5,0],'radius':2,'start_angle':90,'end_angle':270}],(40+4*math.pi)*2)
])
def test_native_curved_sketch_profiles_extrude_exact_material(workspace,geometry,expected_volume):
    _,p,_=workspace;constraints=[{'id':'fixed_'+g['id'],'type':'block','refs':[{'entity':g['id']}]} for g in geometry];code={'schema':1,'name':'Curved profile','units':'mm','parameters':{},'features':[{'id':'profile','op':'sketch','geometry':geometry,'constraints':constraints,'require_fully_constrained':True},{'id':'pad','op':'extrude_shape','target':'profile','vector':[0,0,2]}],'result':'pad'}
    built=mechanical.rebuild(p,{'path':'cad/curved.cad.json','program':code});assert built['metrics']['sketches']['profile']['dof']==0 and built['metrics']['volume_mm3']==pytest.approx(expected_volume,rel=1e-7)


def test_unsaved_sketch_preview_solves_without_publishing_source_models_or_history(workspace):
    _,p,_=workspace;built=mechanical.rebuild(p,{'path':'cad/sketch.cad.json','program':plate()});source=p.root/'cad/sketch.cad.json';before=source.read_bytes();history=copy.deepcopy(p.state['mechanical_history']);models=copy.deepcopy(p.state['workbench_mechanical'])
    assert hasattr(mechanical,'preview_sketch'),'A native draft solve must precede saving a sketch edit'
    result=mechanical.preview_sketch(p,{'path':'cad/sketch.cad.json','feature_id':'profile','program':plate(40),'expected_sha256':hashlib.sha256(before).hexdigest()})
    assert result['sketch']['dof']==0 and next(g for g in result['sketch']['geometry'] if g['id']=='hole')['center']==pytest.approx([20,10])
    assert source.read_bytes()==before and p.state['mechanical_history']==history and p.state['workbench_mechanical']==models and len(p.state['mechanical_asset_receipts'])==1 and not p.engine_busy


def test_read_only_agent_inspects_native_sketch_solution_with_immutable_report_identity(workspace):
    _,p,_=workspace;built=mechanical.rebuild(p,{'path':'cad/sketch.cad.json','program':plate()});assert 'inspect_mechanical_sketches' in codex_bridge.READ_TOOLS,'The Agent needs bounded native sketch evidence'
    result=codex_bridge.execute_tool(p,'inspect_mechanical_sketches',{'source':'cad/sketch.cad.json'},'chat');assert result['asset_id']==built['asset_id'] and result['sketches']['profile']['dof']==0 and len(result['sketches']['profile']['constraints'])==14
    assert result['report']['sha256']==next(f['sha256'] for f in built['files'] if f['name']=='report.json')


def test_closed_bspline_and_construction_geometry_stay_distinct_from_material(workspace):
    _,p,_=workspace;geometry=[{'id':'curve','type':'bspline','poles':[[0,0],[10,0],[10,10],[0,10],[0,0]],'degree':3,'knots':[0,0,0,0,.5,1,1,1,1]},{'id':'axis','type':'line','start':[-20,0],'end':[20,0],'construction':True}];code={'schema':1,'units':'mm','name':'Spline profile','parameters':{},'features':[{'id':'profile','op':'sketch','geometry':geometry,'constraints':[{'id':'lock_curve','type':'block','refs':[{'entity':'curve'}]},{'id':'lock_axis','type':'block','refs':[{'entity':'axis'}]}],'require_fully_constrained':True},{'id':'pad','op':'extrude_shape','target':'profile','vector':[0,0,2]}],'result':'pad'}
    built=mechanical.rebuild(p,{'path':'cad/spline.cad.json','program':code});proof=built['metrics']['sketches']['profile'];assert proof['dof']==0 and built['metrics']['solids']==1 and 1<built['metrics']['volume_mm3']<200
    assert built['metrics']['size_mm'][0]<10 and next(g for g in proof['geometry'] if g['id']=='axis')['construction']
