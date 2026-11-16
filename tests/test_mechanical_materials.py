"""Material intent and appearance must survive native edits without changing geometry."""
import copy,hashlib,json
import pytest
from wholeboard import mechanical,codex_bridge
from test_mechanical_workflow import workspace


def box(material=None):
    value={'schema':1,'name':'Material sample','units':'mm','parameters':{},'features':[{'id':'body','op':'box','size':[20,16,3]}],'result':'body'}
    if material is not None:value['features'][0]['material']=material
    return value


def build(p,code,path='cad/sample.cad.json'):
    try:return mechanical.rebuild(p,{'path':path,'program':code})
    except ValueError as error:pytest.fail('Editable native material assignments are missing: '+str(error))


def scene(p,model):return json.loads((p.root/next(f['path'] for f in model['files'] if f['name']=='scene.json')).read_text())


def test_material_source_is_resolved_without_mutating_editable_fields():
    source=box({'preset':'brass','grade':'C260'});before=copy.deepcopy(source)
    try:resolved=mechanical.resolve(source)
    except ValueError as error:pytest.fail('Part material source is missing: '+str(error))
    assert source==before and resolved['features'][0]['material']['preset']=='brass' and resolved['features'][0]['material']['metalness']>.8


def test_native_material_assignment_sets_scene_style_and_verified_step_colors(workspace):
    _,p,_=workspace;before=copy.deepcopy(p.state['spec']);model=build(p,box({'preset':'brass','grade':'C260'}));body=model['metrics']['bodies'][0];assert body['material']['preset']=='brass' and body['material']['grade']=='C260'
    meshes=scene(p,model)['meshes'];assert all(m['material']['preset']=='brass' and m['metalness']>.8 for m in meshes)
    assert model['metrics']['size_mm']==pytest.approx([20,16,3]) and model['metrics']['volume_mm3']==pytest.approx(960) and model['metrics']['step_face_colors_verified']
    assert p.state['spec']==before and p.state['workbench']['version']==1 and not (p.root/'native').exists()


def test_scoped_face_finish_does_not_relabel_the_bulk_material(workspace):
    _,p,_=workspace;code=box({'preset':'aluminum'});code['features'].append({'id':'finish','op':'material','target':'body','material':{'preset':'clear_acrylic'},'bodies':[0],'faces':[5]});code['result']='finish';model=build(p,code);body=model['metrics']['bodies'][0]
    assert body['material']['preset']=='aluminum' and body['face_materials'][5]['preset']=='clear_acrylic';meshes=scene(p,model)['meshes'];assert any(m['material']['preset']=='clear_acrylic' and m['opacity']<1 for m in meshes)
    assert model['metrics']['volume_mm3']==pytest.approx(960) and model['metrics']['step_face_colors_verified']


def test_material_inherits_through_native_geometry_edits(workspace):
    _,p,_=workspace;code=box({'preset':'copper'});code['features'].append({'id':'drill','op':'hole','target':'body','origin':[10,8,-1],'diameter':3,'depth':5});code['result']='drill';model=build(p,code)
    assert model['metrics']['bodies'][0]['material']['preset']=='copper' and all(m['material']['preset']=='copper' for m in scene(p,model)['meshes'])


def test_surface_finish_tracks_a_face_modified_by_a_hole(workspace):
    _,p,_=workspace;code=box({'preset':'aluminum'});code['features'] += [{'id':'coat','op':'material','target':'body','material':{'preset':'colored_glass'},'bodies':[0],'faces':[5]},{'id':'drill','op':'hole','target':'coat','origin':[10,8,-1],'diameter':3,'depth':5}];code['result']='drill';model=build(p,code)
    assert model['metrics']['bodies'][0]['material']['preset']=='aluminum'
    assert any(m['material']['preset']=='colored_glass' for m in scene(p,model)['meshes']),'A surviving coated plane lost its surface appearance during a hole edit'


def test_component_material_override_is_retained_by_the_assembly_solver(workspace):
    _,p,_=workspace;build(p,box({'preset':'glass'}),'cad/window.cad.json');code={'schema':1,'name':'Override assembly','units':'mm','parameters':{},'features':[{'id':'window','op':'component','source':{'kind':'model','path':'cad/window.cad.json'},'material':{'preset':'brass'}},{'id':'product','op':'assembly','members':['window'],'fixed':['window']}],'result':'product'};model=build(p,code,'cad/product.cad.json')
    assert model['metrics']['bodies'][0]['material']['preset']=='brass','Assembly solving discarded a component material override'


def test_linked_assembly_preserves_component_material_and_surface_assignments(workspace):
    _,p,_=workspace;child=build(p,box({'preset':'glass'}),'cad/window.cad.json');code={'schema':1,'name':'Window assembly','units':'mm','parameters':{},'features':[{'id':'window','op':'component','source':{'kind':'model','path':'cad/window.cad.json'},'translation':[10,20,3]},{'id':'product','op':'assembly','members':['window'],'fixed':['window']}],'result':'product'};model=build(p,code,'cad/product.cad.json')
    assert model['metrics']['bodies'][0]['material']['preset']=='glass' and all(m['transmission']>.5 for m in scene(p,model)['meshes'])
    assert model['metrics']['size_mm']==pytest.approx([20,16,3]) and model['metrics']['origin_mm']==pytest.approx([10,20,3])


def test_bad_material_values_preserve_the_saved_model_and_source(workspace):
    _,p,_=workspace;first=build(p,box({'preset':'plastic'}));source=p.root/'cad/sample.cad.json';before=source.read_bytes();code=box({'preset':'unknown-alloy'})
    with pytest.raises(ValueError,match='material|preset'):
        mechanical.rebuild(p,{'path':'cad/sample.cad.json','program':code,'expected_sha256':hashlib.sha256(before).hexdigest()})
    assert source.read_bytes()==before and p.state['workbench_mechanical']['cad/sample.cad.json']['asset_id']==first['asset_id']


def test_read_only_agent_reads_material_catalog_and_actual_saved_assignments(workspace):
    _,p,_=workspace;model=build(p,box({'preset':'brass','grade':'C260'}));assert 'list_mechanical_materials' in codex_bridge.READ_TOOLS and 'inspect_mechanical_materials' in codex_bridge.READ_TOOLS,'The Agent needs actual material evidence'
    catalog=codex_bridge.execute_tool(p,'list_mechanical_materials',{},'chat');assert {'brass','glass','plywood','carbon_fiber','fiberglass'}<=set(row['id'] for row in catalog['presets'])
    result=codex_bridge.execute_tool(p,'inspect_mechanical_materials',{'source':'cad/sample.cad.json'},'chat');assert result['asset_id']==model['asset_id'] and result['bodies'][0]['material']['grade']=='C260';assert 'density' not in result['bodies'][0]['material']
