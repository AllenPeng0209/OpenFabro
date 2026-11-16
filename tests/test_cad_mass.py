"""Mass properties must converge across C1 spans and remain additive after placement."""
import json
import pytest
from wholeboard import mechanical
from test_mechanical_workflow import workspace
from test_curve_events import profile


def test_c1_extrusion_uses_span_aware_mass_instead_of_default_kernel_estimate(workspace):
    _,p,_=workspace
    model=mechanical.rebuild(p,{'path':'cad/mass.cad.json','program':profile(True)})
    assert model['metrics']['volume_mm3']==pytest.approx(138,abs=1e-7),'Default C1 integration produces an incorrect volume'
    proof=model['metrics']['mass_properties'];assert proof['method']=='occt-adaptive-span-integration'
    assert proof['volume_relative_error']<=1e-8 and proof['kernel_default_volume_mm3']!=pytest.approx(138,abs=1e-4)
    assert model['metrics']['bodies'][0]['volume_mm3']==pytest.approx(138,abs=1e-7)
    step=next(f for f in model['files'] if f['name']=='part.step');assert proof['STEP_sha256']==step['sha256']
    scene_file=next(f for f in model['files'] if f['name']=='scene.json');scene=json.loads((p.root/scene_file['path']).read_text());faces=scene['topology']['bodies'][0]['faces']
    caps=[f for f in faces if f['surface']=='Plane' and abs(f['normal'][2])>.99]
    assert len(caps)==2 and all(f['area_mm2']==pytest.approx(69,abs=1e-7) for f in caps),'Default C1 cap areas must not remain authoritative'
    assert sum(f['area_mm2'] for f in faces)==pytest.approx(model['metrics']['area_mm2'],abs=1e-7)


def test_precise_assembly_mass_is_additive_and_old_model_files_stay_immutable(workspace):
    import hashlib
    _,p,_=workspace
    first=mechanical.rebuild(p,{'path':'cad/shape.cad.json','program':profile(True)})
    frozen={f['path']:(hashlib.sha256((p.root/f['path']).read_bytes()).hexdigest(),(p.root/f['path']).stat().st_mtime_ns) for f in first['files']}
    code={'schema':1,'name':'Mass assembly','units':'mm','parameters':{},'features':[
        {'id':'a','op':'component','source':{'kind':'model','path':'cad/shape.cad.json'}},
        {'id':'b','op':'component','source':{'kind':'model','path':'cad/shape.cad.json'},'translation':[20,0,0],'rotation':{'axis':[0,0,1],'angle':90}},
        {'id':'product','op':'assembly','members':['a','b'],'fixed':['a','b']}],'result':'product'}
    model=mechanical.rebuild(p,{'path':'cad/product.cad.json','program':code});metrics=model['metrics']
    assert metrics['volume_mm3']==pytest.approx(276,abs=1e-7)
    assert sum(b['volume_mm3'] for b in metrics['bodies'])==pytest.approx(metrics['volume_mm3'],abs=1e-7)
    for name,expected in frozen.items():
        path=p.root/name;assert (hashlib.sha256(path.read_bytes()).hexdigest(),path.stat().st_mtime_ns)==expected
    assert p.state['workbench']['version']==1
