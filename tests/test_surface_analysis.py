"""Native face normals and principal curvatures must not be inferred from triangles."""
import copy
import hashlib
import json
import pytest
from wholeboard import mechanical, codex_bridge
from test_mechanical_workflow import workspace
from test_mechanical_topology import scene


def test_edited_meshes_cannot_gain_false_smooth_surface_evidence(workspace):
    import base64
    from pathlib import Path
    from wholeboard import mechanical_assets
    client,p,_=workspace
    raw=(Path(__file__).parent/'fixtures/mesh-import/bracket.stl').read_bytes()
    response=client.post(f'/api/workbench/projects/{p.id}/mechanical/assets',json={'name':'bracket.stl','units':'mm','data':base64.b64encode(raw).decode()})
    assert response.status_code==200,response.text
    asset=response.json();model=mechanical_assets.create_part(p,{'asset_id':asset['asset_id'],'path':'cad/mesh.cad.json','name':'Faceted reference'})
    source=p.root/'cad/mesh.cad.json';code=json.loads(source.read_text());code['features'].append({'id':'hole','op':'hole','target':code['result'],'diameter':3.2,'depth':6,'origin':[10,7,-1]});code['result']='hole'
    model=mechanical.rebuild(p,{'path':'cad/mesh.cad.json','program':code,'expected_sha256':hashlib.sha256(source.read_bytes()).hexdigest()})
    assert model['metrics']['geometry_provenance']=='faceted-mesh-input'
    assert all(sample is None for mesh in scene(p,model)['meshes'] for sample in mesh.get('surface_samples',[])), 'Edited mesh facets gained false smooth derivatives'
    assembly={'schema':1,'name':'Faceted assembly','units':'mm','parameters':{},'features':[
        {'id':'part','op':'component','source':{'kind':'model','path':'cad/mesh.cad.json'}},
        {'id':'product','op':'assembly','members':['part'],'fixed':['part']}],'result':'product'}
    placed=mechanical.rebuild(p,{'path':'cad/placed_mesh.cad.json','program':assembly})
    assert all(sample is None for mesh in scene(p,placed)['meshes'] for sample in mesh.get('surface_samples',[])), 'Assembly STEP conversion lost faceted provenance'


def test_native_sphere_saddle_and_sample_budget_remain_distinct_from_zero_curvature(tmp_path):
    import os
    import subprocess
    from pathlib import Path
    from wholeboard import enclosure
    command=enclosure.find_freecad()
    if not command:pytest.skip('FreeCAD is not installed')
    folder=Path(mechanical.__file__).parent
    output=tmp_path/'samples.json';script=tmp_path/'surface_probe.py'
    script.write_text('import sys\nsys.path.insert(0,'+repr(str(folder))+')\n'+'''import json
import FreeCAD as App
import Part
from freecad_topology import surface_samples, surface_summary
doc=App.newDocument('SurfaceChecks')
sphere=Part.makeSphere(5);torus=Part.makeTorus(8,2)
f=sphere.Faces[0];g=torus.Faces[0]
one=surface_samples(f,[f.valueAt(.2,.4)],0,[0,0,0],{'remaining':10})
two=surface_samples(g,[g.valueAt(.2,3.141592653589793)],0,[0,0,0],{'remaining':10})
missing=surface_samples(f,[f.valueAt(.2,.4)],0,[0,0,0],{'remaining':0})
faceted=surface_samples(f,[f.valueAt(.2,.4)],0,[0,0,0],{'remaining':10},faceted=True)
result={'sphere':one,'saddle':two,'missing':missing,'faceted':faceted,'missing_summary':surface_summary(missing)}
open('''+repr(str(output))+''','w').write(json.dumps(result))
App.closeDocument(doc.Name)
''')
    result=subprocess.run(command+[str(script)],cwd=tmp_path,env={**os.environ,'QT_QPA_PLATFORM':'offscreen'},capture_output=True,text=True,timeout=30)
    assert result.returncode==0 and output.exists(),result.stdout+result.stderr
    data=json.loads(output.read_text());assert data['sphere'][0]['principal']==pytest.approx([-.2,-.2],abs=1e-9)
    assert data['saddle'][0]['principal']==pytest.approx([-.5,1/6],abs=1e-9)
    assert data['missing']==[None] and data['faceted']==[None]
    assert data['missing_summary']['available'] is False and data['missing_summary']['unavailable_samples']==1


def ring():
    return {'schema':1,'units':'mm','name':'Surface ring','parameters':{},'features':[
        {'id':'outer','op':'cylinder','radius':4,'height':3},
        {'id':'inner','op':'cylinder','radius':2,'height':3},
        {'id':'body','op':'cut','target':'outer','tool':'inner'}],'result':'body'}


def test_native_surface_samples_preserve_outer_inner_and_planar_curvature_signs(workspace):
    _,p,_=workspace
    built=mechanical.rebuild(p,{'path':'cad/ring.cad.json','program':ring()})
    data=scene(p,built);faces=data['topology']['bodies'][0]['faces'];seen=set()
    for mesh in data['meshes']:
        assert 'surface_samples' in mesh, 'Native surface samples are missing'
        assert len(mesh['surface_samples'])==len(mesh['v'])//3
        for i,sample in enumerate(mesh['surface_samples']):
            assert sample is not None
            face=faces[sample['face_index']];seen.add(face['index'])
            k=sample['principal'];assert k[0]<=k[1]
            if face['surface']=='Plane':assert k==pytest.approx([0,0],abs=1e-10)
            else:
                radius=face['radius_mm'];inner=radius==2
                assert k==pytest.approx([0,.5] if inner else [-.25,0],abs=1e-9)
                world=[a+b for a,b in zip(mesh['v'][i*3:i*3+3],data['origin'])]
                sign=-1 if inner else 1
                assert sample['normal']==pytest.approx([sign*world[0]/radius,sign*world[1]/radius,0],abs=1e-6)
    assert len(seen)==4


def test_surface_samples_follow_rotated_instances_and_read_only_pagination(workspace):
    _,p,_=workspace
    mechanical.rebuild(p,{'path':'cad/ring.cad.json','program':ring()})
    code={'schema':1,'units':'mm','name':'Placed surfaces','parameters':{},'features':[
        {'id':'ring','op':'component','source':{'kind':'model','path':'cad/ring.cad.json'},'translation':[100,200,10],'rotation':{'axis':[1,0,0],'angle':90}},
        {'id':'product','op':'assembly','members':['ring'],'fixed':['ring']}],'result':'product'}
    built=mechanical.rebuild(p,{'path':'cad/product.cad.json','program':code});data=scene(p,built)
    outer=next(f for f in data['topology']['bodies'][0]['faces'] if f.get('radius_mm')==4)
    assert 'inspect_mechanical_surfaces' in codex_bridge.READ_TOOLS, 'Agent needs bounded native surface evidence'
    before=copy.deepcopy(p.state);files={f['path']:(hashlib.sha256((p.root/f['path']).read_bytes()).hexdigest(),(p.root/f['path']).stat().st_mtime_ns) for f in built['files']}
    args={'source':'cad/product.cad.json','body_id':0,'face_index':outer['index'],'limit':3}
    result=codex_bridge.execute_tool(p,'inspect_mechanical_surfaces',args,'chat')
    assert result['asset_id']==built['asset_id'] and result['member_id']=='ring' and result['next_offset']==3
    assert len(result['samples'])==3 and result['origin_mm']==pytest.approx(data['origin'])
    assert all(abs(sample['normal'][1])<1e-8 for sample in result['samples'])
    assert all(sample['principal']==pytest.approx([-.25,0],abs=1e-9) for sample in result['samples'])
    with pytest.raises(ValueError,match='changed|SHA|snapshot'):
        codex_bridge.execute_tool(p,'inspect_mechanical_surfaces',{**args,'expected_scene_sha256':'0'*64},'chat')
    assert p.state==before
    for name,value in files.items():
        path=p.root/name;assert (hashlib.sha256(path.read_bytes()).hexdigest(),path.stat().st_mtime_ns)==value
