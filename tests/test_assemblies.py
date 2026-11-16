"""Product assemblies use real part revisions, native mates and pairwise geometry."""
import copy,hashlib,importlib,json
from pathlib import Path
import pytest
from wholeboard import mechanical,codex_bridge
from test_mechanical_workflow import workspace
from test_mechanical_parts import program


def module():
    try:return importlib.import_module('wholeboard.assemblies')
    except ModuleNotFoundError:pytest.fail('Native product assemblies and fit checks are missing')


def make_box(p,path,name,size):
    return mechanical.rebuild(p,{'path':path,'program':{'schema':1,'units':'mm','name':name,'parameters':{},'features':[{'id':'body','op':'box','size':size}],'result':'body'}})


def assembly_program(gap=1):
    return {'schema':1,'units':'mm','name':'Product assembly','parameters':{'gap':{'value':gap,'unit':'mm'}},'features':[
      {'id':'base','op':'component','label':'Base','source':{'kind':'model','path':'cad/base.cad.json'}},
      {'id':'board','op':'component','label':'Board','source':{'kind':'model','path':'cad/board.cad.json'},'translation':[0,0,0]},
      {'id':'product','op':'assembly','members':['base','board'],'fixed':['base'],
       'mates':[{'id':'board_height','type':'coincident','target':'board','reference':'base',
                 'target_anchor':{'kind':'plane','normal':[0,0,-1],'extreme':'min'},
                 'reference_anchor':{'kind':'plane','normal':[0,0,1],'extreme':'max'},'offset':'gap'}],
       'clearance_mm':.5}],'result':'product'}


def test_component_assembly_mates_resolve_dimensions_without_modifying_editable_expressions():
    source=assembly_program();before=copy.deepcopy(source)
    try:resolved=mechanical.resolve(source)
    except ValueError as error:pytest.fail('CAD component/assembly operations are missing: '+str(error))
    assert source==before and resolved['features'][-1]['mates'][0]['offset']==1
    assert resolved['features'][0]['source']['path']=='cad/base.cad.json'


def test_model_components_and_face_mate_create_verified_named_native_assembly(workspace):
    _,p,_=workspace;module();before=copy.deepcopy(p.state['spec']);base=make_box(p,'cad/base.cad.json','Base',[20,16,3]);board=make_box(p,'cad/board.cad.json','Board',[20,16,2])
    result=mechanical.rebuild(p,{'path':'cad/product.cad.json','program':assembly_program()})
    assert result['metrics']['solids']==2 and result['metrics']['volume_mm3']==pytest.approx(1600)
    proof=result['metrics']['assembly'];assert proof['solver']['satisfied'] and proof['fit']['pass'] and proof['fit']['complete']
    assert [m['id'] for m in proof['members']]==['base','board']
    assert proof['members'][1]['origin_mm']==pytest.approx([0,0,4]) and proof['members'][1]['size_mm']==pytest.approx([20,16,2])
    pair=proof['fit']['pairs'][0];assert pair['distance_mm']==pytest.approx(1) and pair['overlap_mm3']==pytest.approx(0) and pair['status']=='clear'
    assert all(b['name'].startswith(('Base /','Board /')) for b in result['metrics']['bodies'])
    assert result['metrics']['step_face_colors_verified'] and len(result['files'])==8
    assert p.state['spec']==before and p.state['workbench']['version']==1 and not (p.root/'native').exists()
    source=next(row for row in module().inventory(p)['sources'] if row['label']=='Base')
    assert source['source']=={'kind':'model','path':'cad/base.cad.json'} and source['available']


def test_agent_inspection_keeps_compact_retained_revisions_and_report_pointers(workspace):
    _,p,_=workspace;make_box(p,'cad/base.cad.json','Base',[20,16,3]);make_box(p,'cad/board.cad.json','Board',[20,16,2]);first=mechanical.rebuild(p,{'path':'cad/product.cad.json','program':assembly_program(-1)});source=p.root/'cad/product.cad.json'
    final=mechanical.rebuild(p,{'path':'cad/product.cad.json','program':assembly_program(1),'expected_sha256':hashlib.sha256(source.read_bytes()).hexdigest()})
    value=codex_bridge.execute_tool(p,'inspect_mechanical_parts',{'source':'cad/product.cad.json'},'chat');assert len(value['parts'])==1
    row=value['parts'][0];assert row['asset_id']==final['asset_id'] and row['details_omitted']
    old=next(v for v in row['versions'] if v['asset_id']==first['asset_id']);assert old['metrics']['assembly']['fit']['pass'] is False and old['report']['path'].endswith('/report.json')
    assert 'face_colors' not in row['metrics']['bodies'][0]


def test_native_intersection_is_recorded_and_parameter_edit_resolves_it(workspace):
    _,p,_=workspace;module();make_box(p,'cad/base.cad.json','Base',[20,16,3]);make_box(p,'cad/board.cad.json','Board',[20,16,2])
    first=mechanical.rebuild(p,{'path':'cad/product.cad.json','program':assembly_program(-1)})
    fit=first['metrics']['assembly']['fit'];assert not fit['pass'] and fit['complete'];assert fit['pairs'][0]['overlap_mm3']==pytest.approx(320) and fit['pairs'][0]['status']=='interference'
    source=p.root/'cad/product.cad.json';old_files={f['path']:(hashlib.sha256((p.root/f['path']).read_bytes()).hexdigest(),(p.root/f['path']).stat().st_mtime_ns) for f in first['files']}
    second=mechanical.rebuild(p,{'path':'cad/product.cad.json','program':assembly_program(1),'expected_sha256':hashlib.sha256(source.read_bytes()).hexdigest()})
    assert second['metrics']['assembly']['fit']['pass'] and len(mechanical.listing(p)['parts'][-1]['versions'])==2
    assert all((hashlib.sha256((p.root/n).read_bytes()).hexdigest(),(p.root/n).stat().st_mtime_ns)==v for n,v in old_files.items())


def test_latest_model_dependency_marks_assembly_stale_and_rebuild_keeps_the_face_relationship(workspace):
    _,p,_=workspace;module();make_box(p,'cad/base.cad.json','Base',[20,16,3]);make_box(p,'cad/board.cad.json','Board',[20,16,2])
    first=mechanical.rebuild(p,{'path':'cad/product.cad.json','program':assembly_program()});source=p.root/'cad/base.cad.json';code=json.loads(source.read_text());code['features'][0]['size'][2]=5
    mechanical.rebuild(p,{'path':'cad/base.cad.json','program':code,'expected_sha256':hashlib.sha256(source.read_bytes()).hexdigest()})
    row=next(part for part in mechanical.listing(p)['parts'] if part['source']=='cad/product.cad.json');assert row['stale'] and row['dependency_changed']
    second=mechanical.rebuild(p,{'path':'cad/product.cad.json'});assert second['asset_id']!=first['asset_id'];assert second['metrics']['assembly']['members'][1]['origin_mm']==pytest.approx([0,0,6])
    assert second['metrics']['assembly']['fit']['pairs'][0]['distance_mm']==pytest.approx(1)


def test_nested_model_source_rejects_changed_link_but_keeps_explicit_retained_revision(workspace):
    _,p,_=workspace;make_box(p,'cad/base.cad.json','Base',[20,16,3]);make_box(p,'cad/board.cad.json','Board',[20,16,2]);built=mechanical.rebuild(p,{'path':'cad/product.cad.json','program':assembly_program()})
    source=p.root/'cad/base.cad.json';code=json.loads(source.read_text());code['features'][0]['size'][2]=5
    mechanical.rebuild(p,{'path':'cad/base.cad.json','program':code,'expected_sha256':hashlib.sha256(source.read_bytes()).hexdigest()})
    with pytest.raises((ValueError,RuntimeError),match='changed|stale|rebuild'):
        module().resolve_source(p,{'kind':'model','path':'cad/product.cad.json'})
    retained=module().resolve_source(p,{'kind':'model','path':'cad/product.cad.json','asset_id':built['asset_id']});assert retained['asset_id']==built['asset_id']


def test_conflicting_mates_fail_without_replacing_the_existing_source_or_model(workspace):
    _,p,_=workspace;module();make_box(p,'cad/base.cad.json','Base',[20,16,3]);make_box(p,'cad/board.cad.json','Board',[20,16,2]);first=mechanical.rebuild(p,{'path':'cad/product.cad.json','program':assembly_program()});source=p.root/'cad/product.cad.json';before=source.read_bytes();code=assembly_program();duplicate=copy.deepcopy(code['features'][-1]['mates'][0]);duplicate.update(id='contradiction',offset=2);code['features'][-1]['mates'].append(duplicate)
    with pytest.raises((ValueError,RuntimeError),match='mate|constraint|satisf'):
        mechanical.rebuild(p,{'path':'cad/product.cad.json','program':code,'expected_sha256':hashlib.sha256(before).hexdigest()})
    assert source.read_bytes()==before and p.state['workbench_mechanical']['cad/product.cad.json']['asset_id']==first['asset_id'] and not p.engine_busy


def test_assembly_sources_cannot_escape_project_or_reuse_corrupt_native_dependencies(workspace,tmp_path):
    _,p,_=workspace;module();make_box(p,'cad/base.cad.json','Base',[20,16,3]);make_box(p,'cad/board.cad.json','Board',[20,16,2]);code=assembly_program();code['features'][0]['source']['path']='../outside.cad.json'
    with pytest.raises((ValueError,RuntimeError)):mechanical.rebuild(p,{'path':'cad/product.cad.json','program':code})
    base=p.state['workbench_mechanical']['cad/base.cad.json'];(p.root/next(f['path'] for f in base['files'] if f['name']=='part.step')).write_bytes(b'corrupt')
    with pytest.raises((ValueError,RuntimeError),match='changed|hash|integrity'):mechanical.rebuild(p,{'path':'cad/product.cad.json','program':assembly_program()})
    assert not (p.root/'cad/product.cad.json').exists()


def test_read_only_agent_can_inspect_source_and_fit_but_cannot_build_an_assembly(workspace):
    _,p,_=workspace;module()
    value=codex_bridge.execute_tool(p,'inspect_assembly_sources',{},'chat');assert value['sources']==[]
    with pytest.raises(ValueError,match='Chat mode'):codex_bridge.execute_tool(p,'build_mechanical_part',{'path':'cad/p.cad.json','program':assembly_program()},'chat')


def test_concentric_native_cylinder_and_offset_mates_preserve_radial_gap(workspace):
    _,p,_=workspace;module()
    ring={'schema':1,'units':'mm','name':'Ring','parameters':{},'features':[{'id':'outside','op':'cylinder','radius':5,'height':3},{'id':'bore','op':'cylinder','radius':2,'height':3},{'id':'ring','op':'cut','target':'outside','tool':'bore'}],'result':'ring'}
    shaft={'schema':1,'units':'mm','name':'Shaft','parameters':{},'features':[{'id':'shaft','op':'cylinder','radius':1.5,'height':5}],'result':'shaft'}
    mechanical.rebuild(p,{'path':'cad/ring.cad.json','program':ring});mechanical.rebuild(p,{'path':'cad/shaft.cad.json','program':shaft})
    code={'schema':1,'units':'mm','name':'Axis assembly','parameters':{},'features':[
       {'id':'ring','op':'component','source':{'kind':'model','path':'cad/ring.cad.json'}},
       {'id':'shaft','op':'component','source':{'kind':'model','path':'cad/shaft.cad.json'},'translation':[8,4,1],'rotation':{'axis':[0,1,0],'angle':90}},
       {'id':'assembly','op':'assembly','members':['ring','shaft'],'fixed':['ring'],'clearance_mm':.4,'mates':[
         {'id':'axis','type':'concentric','target':'shaft','reference':'ring','target_anchor':{'kind':'axis','radius':1.5},'reference_anchor':{'kind':'axis','radius':2}},
         {'id':'height','type':'offset','target':'shaft','reference':'ring','target_anchor':{'kind':'datum'},'reference_anchor':{'kind':'datum'},'offset':1}]}],'result':'assembly'}
    result=mechanical.rebuild(p,{'path':'cad/axis.cad.json','program':code});proof=result['metrics']['assembly']
    assert proof['solver']['satisfied'] and proof['fit']['pass'] and proof['fit']['pairs'][0]['distance_mm']==pytest.approx(.5,abs=1e-6)
    assert proof['members'][1]['origin_mm']==pytest.approx([-1.5,-1.5,1],abs=1e-6)


def test_native_populated_board_and_enclosure_are_verified_component_sources(workspace,tmp_path):
    client,_,_=workspace;module()
    from wholeboard import server,workbench_native
    made=client.post('/api/workbench/projects',json={'title':'Assembly ECAD source','example':True}).json();p=server.mgr().get(made['id'])
    workbench_native.perform(p,'board3d');workbench_native.perform(p,'enclosure')
    before=copy.deepcopy(p.state['spec']);version=p.state['workbench']['version'];sources=module().inventory(p)['sources']
    assert next(s for s in sources if s['source']['kind']=='board')['available']
    assert len([s for s in sources if s['source']['kind']=='enclosure' and s['available']])==2
    code={'schema':1,'units':'mm','name':'Real board assembly','parameters':{},'features':[{'id':'pcb','op':'component','label':'PCB','source':{'kind':'board'}},{'id':'product','op':'assembly','members':['pcb'],'fixed':['pcb']}],'result':'product'}
    built=mechanical.rebuild(p,{'path':'cad/pcb_assembly.cad.json','program':code});assert built['metrics']['assembly']['fit']['complete']
    scene=json.loads((p.root/p.state['workbench_board3d']['scene_path']).read_text());size=scene['size'];origin=scene['origin']
    assert built['metrics']['size_mm']==pytest.approx(size,abs=1e-5)
    assert built['metrics']['origin_mm']==pytest.approx([origin[0],-origin[1]-size[1],origin[2]],abs=1e-5)
    # A matching outer box alone can hide misplaced components inside the board.
    # Compare every native solid against a separately read original STEP.
    import subprocess
    from wholeboard.enclosure import find_freecad
    probe=tmp_path/'worlds.py';answer=tmp_path/'worlds.json';step=p.root/Path(p.state['workbench_board3d']['scene_path']).parent/'board.step'
    probe.write_text('''import sys,json
from pathlib import Path
sys.path.insert(0,SOURCE)
import FreeCAD as App,Part
from freecad_import import load_geometry
doc=App.newDocument('IndependentWorlds');bodies=load_geometry(STEP,doc);expected=Part.read(STEP)
def signature(shape):
 b=shape.optimalBoundingBox(False,False);c=shape.CenterOfMass
 return [shape.Volume,shape.Area,c.x,c.y,c.z,b.XMin,b.YMin,b.ZMin,b.XMax,b.YMax,b.ZMax]
pending=[signature(s) for s in expected.Solids]
for body in bodies:
 for shape in body['shape'].Solids:
  row=signature(shape);match=next((i for i,v in enumerate(pending) if max(abs(a-b) for a,b in zip(row,v))<1e-5),None)
  assert match is not None;pending.pop(match)
assert not pending
Path(ANSWER).write_text(json.dumps({'passed':True,'solids':len(expected.Solids)}))
'''.replace('SOURCE',repr(str(Path(__file__).parents[1]/'wholeboard'))).replace('STEP',repr(str(step))).replace('ANSWER',repr(str(answer))))
    process=subprocess.run(find_freecad()+[str(probe)],cwd=tmp_path,capture_output=True,text=True,timeout=30)
    assert process.returncode==0 and answer.is_file(),process.stdout+process.stderr
    assert json.loads(answer.read_text())['passed']
    assert built['metrics']['assembly']['members'][0]['source']['pcb_sha256']==p.state['workbench_board3d']['source_sha']
    assert p.state['spec']==before and p.state['workbench']['version']==version


def test_missing_board_component_models_cannot_be_reported_as_complete_fit(workspace):
    _,p,_=workspace;module();base=make_box(p,'cad/base.cad.json','Base',[10,8,2]);step=next(f for f in base['files'] if f['name']=='part.step');pcb=p.root/'board.kicad_pcb';pcb.write_text('(kicad_pcb)');p.state['artifacts']={'pcb':str(pcb)};p.state['workbench']['checks_stale']=False
    folder=p.root/'native/source/board3d';folder.mkdir(parents=True);(folder/'board.step').write_bytes((p.root/step['path']).read_bytes())
    p.state['workbench_board3d']={'version':1,'source_sha':hashlib.sha256(pcb.read_bytes()).hexdigest(),'step_sha':hashlib.sha256((folder/'board.step').read_bytes()).hexdigest(),'scene_path':'native/source/board3d/scene.json','unmatched_components':['J1']}
    from wholeboard import design_identity
    p.state['workbench_native']={'pcb':str(pcb),'fingerprint':design_identity.legacy_fingerprint(p.state['spec']),**design_identity.fields(p.state['spec'])}
    code={'schema':1,'units':'mm','name':'Incomplete board geometry','parameters':{},'features':[{'id':'pcb','op':'component','source':{'kind':'board'}},{'id':'product','op':'assembly','members':['pcb'],'fixed':['pcb']}],'result':'product'}
    result=mechanical.rebuild(p,{'path':'cad/incomplete.cad.json','program':code});fit=result['metrics']['assembly']['fit'];assert fit['complete'] is False and fit['pass'] is None and fit['coverage_warnings'][0]['unmatched_components']==['J1']
    retained=module().resolve_source(p,{'kind':'model','path':'cad/incomplete.cad.json','asset_id':result['asset_id']});assert retained['coverage_complete'] is False
