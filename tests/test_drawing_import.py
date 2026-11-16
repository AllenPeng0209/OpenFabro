"""Drawing profiles preserve analytic boundaries, cutouts, units and source assets."""
import base64,copy,hashlib,importlib,json,math
from pathlib import Path
import pytest
from wholeboard import mechanical,mechanical_assets,codex_bridge
from test_mechanical_workflow import workspace

FIXTURES=Path(__file__).parent/'fixtures/drawing-import'


def drawing():
    try:return importlib.import_module('wholeboard.drawing_assets')
    except ModuleNotFoundError:pytest.fail('Mechanical DXF/SVG profile import is missing')


def upload(client,p,name,**kwargs):
    response=client.post(f'/api/workbench/projects/{p.id}/mechanical/assets',json={'name':name,'data':base64.b64encode((FIXTURES/name).read_bytes()).decode(),**kwargs})
    assert response.status_code==200,response.text
    return response.json()


def test_dxf_preserves_bulge_arcs_circle_holes_layers_and_reference_geometry():
    value=drawing().convert('rounded_plate.dxf',(FIXTURES/'rounded_plate.dxf').read_bytes())
    assert value['geometry_kind']=='planar-drawing' and value['units']=='mm' and not value['units_assumed']
    assert len(value['profiles'])==1 and len(value['profiles'][0]['holes'])==2
    assert {'ellipse','line'}<={edge['kind'] for edge in value['profiles'][0]['outer']}
    assert value['references'] and {'CUT','HOLES','REFERENCE'}<=set(value['layers'])
    assert any(row['type']=='TEXT' for row in value['diagnostics']['ignored'])


@pytest.mark.parametrize('name,origin',[('rounded_plate.dxf',[0,0,0]),('rounded_plate.svg',[0,-24,0])])
def test_drawing_import_and_extrusion_keep_exact_round_holes_and_original_bytes(workspace,name,origin):
    client,p,_=workspace;before=copy.deepcopy(p.state['spec']);asset=upload(client,p,name)
    assert asset['geometry_kind']=='planar-drawing';profile=next(b for b in asset['bodies'] if b.get('can_extrude'))
    assert profile['area_mm2']==pytest.approx(944-4*math.pi,abs=1e-6)
    assert profile['holes']==2 and profile['size_mm']==pytest.approx([40,24,0],abs=1e-6)
    assert profile['origin_mm']==pytest.approx(origin,abs=1e-6)
    accepted={f['path']:(hashlib.sha256((p.root/f['path']).read_bytes()).hexdigest(),(p.root/f['path']).stat().st_mtime_ns) for f in asset['files']}
    response=client.post(f'/api/workbench/projects/{p.id}/mechanical/assets/extrude',json={'asset_id':asset['asset_id'],'path':'cad/drawing.cad.json','thickness':3,'name':'Drawing bracket'})
    assert response.status_code==200,response.text
    model=response.json();assert model['metrics']['solids']==1 and model['metrics']['volume_mm3']==pytest.approx((944-4*math.pi)*3,abs=1e-5)
    assert model['metrics']['size_mm']==pytest.approx([40,24,3],abs=1e-6)
    code=json.loads((p.root/'cad/drawing.cad.json').read_text());assert code['parameters']['thickness']['value']==3 and code['features'][0]['asset_id']==asset['asset_id']
    assert {'part.obj','part.3mf'}<={f['name'] for f in model['files']}
    assert model['metrics']['step_face_colors_verified'] and model['metrics']['step_roundtrip']['valid']
    assert all((hashlib.sha256((p.root/n).read_bytes()).hexdigest(),(p.root/n).stat().st_mtime_ns)==value for n,value in accepted.items())
    assert p.state['spec']==before and p.state['workbench']['version']==1 and not (p.root/'native').exists()


def test_inch_multiple_profiles_and_transformed_block_copies_keep_their_holes(workspace):
    client,p,_=workspace;inch=upload(client,p,'inch_multi.dxf');profiles=[b for b in inch['bodies'] if b.get('can_extrude')]
    assert len(profiles)==2 and profiles[0]['size_mm']==pytest.approx([50.8,25.4,0])
    assert profiles[1]['origin_mm']==pytest.approx([76.2,0,0])
    assert profiles[0]['area_mm2']==pytest.approx((2-math.pi*.125**2)*25.4**2,abs=1e-5)
    blocks=upload(client,p,'blocks.dxf');profiles=[b for b in blocks['bodies'] if b.get('can_extrude')]
    assert len(profiles)==2
    assert [b['area_mm2'] for b in profiles]==pytest.approx([120-2*math.pi,60-math.pi],abs=1e-5)
    assert profiles[0]['origin_mm']==pytest.approx([1,9,0],abs=1e-6) and profiles[0]['size_mm']==pytest.approx([6,20,0],abs=1e-6)


@pytest.mark.parametrize('name,area',[('nonzero.svg',800),('evenodd.svg',600),('bezier.svg',60),('bezier_spline.dxf',60),('transformed.svg',100-2*math.pi)])
def test_svg_fill_rules_and_exact_bezier_spline_affine_profiles(workspace,name,area):
    client,p,_=workspace;asset=upload(client,p,name);profiles=[b for b in asset['bodies'] if b.get('can_extrude')]
    assert len(profiles)==1 and profiles[0]['area_mm2']==pytest.approx(area,abs=1e-5)
    if name.startswith('bezier'):
        result=mechanical_assets.extrude(p,{'asset_id':asset['asset_id'],'path':'cad/arch.cad.json','thickness':2})
        assert result['metrics']['volume_mm3']==pytest.approx(120,abs=1e-5)


def test_outline_mode_and_layer_selection_are_explicit(workspace):
    client,p,_=workspace
    cut_only=upload(client,p,'rounded_plate.dxf',layers=['CUT']);profile=next(b for b in cut_only['bodies'] if b.get('can_extrude'))
    assert profile['holes']==0 and profile['area_mm2']==pytest.approx(944+4*math.pi,abs=1e-6)
    outline=upload(client,p,'outline.svg',drawing_mode='outline');profile=next(b for b in outline['bodies'] if b.get('can_extrude'))
    assert profile['holes']==1 and profile['area_mm2']==pytest.approx(800-4*math.pi,abs=1e-6)


def test_open_curves_remain_reference_geometry_without_publishing_a_false_solid(workspace):
    client,p,_=workspace;asset=upload(client,p,'open_curves.dxf')
    assert asset['bodies'] and not any(b.get('can_extrude') for b in asset['bodies'])
    assert client.get(asset['scene_url']).json()['lines']
    response=client.post(f'/api/workbench/projects/{p.id}/mechanical/assets/extrude',json={'asset_id':asset['asset_id'],'path':'cad/open.cad.json','thickness':3})
    assert response.status_code==422 and not (p.root/'cad/open.cad.json').exists() and not p.engine_busy


def test_svg_entities_and_external_references_do_not_load_outside_the_upload():
    module=drawing()
    samples=['<!DOCTYPE svg [<!ENTITY outside SYSTEM "file:///etc/passwd">]><svg xmlns="http://www.w3.org/2000/svg"><text>&outside;</text></svg>',
             '<svg xmlns="http://www.w3.org/2000/svg"><use href="https://example.invalid/a.svg#shape"/></svg>']
    for text in samples:
        with pytest.raises(ValueError,match='SVG|external|DOCTYPE|entity|unsafe'):module.convert('bad.svg',text.encode())


def test_agent_extrusion_requires_agent_mode_and_preserves_source_version(workspace):
    client,p,_=workspace;asset=upload(client,p,'rounded_plate.dxf')
    with pytest.raises(ValueError,match='Chat mode'):codex_bridge.execute_tool(p,'extrude_drawing_asset',{'asset_id':asset['asset_id'],'path':'cad/chat.cad.json','thickness':3},'chat')
    result=codex_bridge.execute_tool(p,'extrude_drawing_asset',{'asset_id':asset['asset_id'],'path':'cad/agent.cad.json','thickness':1.5},'agent')
    assert result['metrics']['volume_mm3']==pytest.approx((944-4*math.pi)*1.5,abs=1e-5) and p.state['workbench']['version']==1


def test_obj_and_3mf_geometry_decode_independently_with_units_names_and_closed_topology(workspace):
    import io,zipfile,xml.etree.ElementTree as ET
    import numpy as np
    import trimesh
    client,p,_=workspace;asset=upload(client,p,'rounded_plate.dxf');model=mechanical_assets.extrude(p,{'asset_id':asset['asset_id'],'path':'cad/exports.cad.json','thickness':3})
    files={f['name']:p.root/f['path'] for f in model['files']}
    obj=trimesh.load_scene(files['part.obj'],process=False,maintain_order=False)
    mesh=obj.to_geometry();mesh.merge_vertices();assert mesh.is_watertight and mesh.is_winding_consistent
    assert mesh.bounds[1]-mesh.bounds[0]==pytest.approx([40,24,3],abs=1e-5)
    assert mesh.volume==pytest.approx((944-4*math.pi)*3,rel=1e-4)
    ns={'m':'http://schemas.microsoft.com/3dmanufacturing/core/2015/02'}
    with zipfile.ZipFile(files['part.3mf']) as z:
        root=ET.fromstring(z.read('3D/3dmodel.model'));assert root.get('unit')=='millimeter';objects=root.findall('m:resources/m:object',ns);assert len(objects)==1 and objects[0].get('name')=='CUT'
        vertices=np.array([[float(v.get(k)) for k in ('x','y','z')] for v in objects[0].findall('m:mesh/m:vertices/m:vertex',ns)])
        triangles=np.array([[int(v.get(k)) for k in ('v1','v2','v3')] for v in objects[0].findall('m:mesh/m:triangles/m:triangle',ns)])
        decoded=trimesh.Trimesh(vertices=vertices,faces=triangles,process=False)
        assert decoded.is_watertight and decoded.is_winding_consistent and decoded.volume==pytest.approx((944-4*math.pi)*3,rel=1e-4)
        assert len(root.findall('m:build/m:item',ns))==1 and root.find('m:resources/m:basematerials/m:base',ns).get('displaycolor')=='#1a4dccff'


def test_a_trusted_legacy_six_file_model_remains_readable_without_regeneration(workspace):
    _,p,_=workspace;asset=upload(*workspace[:2],'bezier.svg');model=mechanical_assets.extrude(p,{'asset_id':asset['asset_id'],'path':'cad/legacy.cad.json','thickness':2});folder=p.root/'mechanical'/model['asset_id'];manifest=json.loads((folder/'manifest.json').read_text())
    # Model only the accepted old storage contract; optional new outputs are unclaimed.
    for key in ['part.obj','part.3mf']:manifest['hashes'].pop(key)
    (folder/'manifest.json').write_text(json.dumps(manifest));seal=hashlib.sha256((folder/'manifest.json').read_bytes()).hexdigest();p.state['mechanical_asset_receipts'][model['asset_id']]=seal
    old=mechanical._record(p,folder);assert len(old['files'])==6


def test_multiple_profiles_extrude_with_individual_names_and_preserved_positions(workspace):
    client,p,_=workspace;asset=upload(client,p,'inch_multi.dxf');profiles=[b for b in asset['bodies'] if b.get('can_extrude')]
    model=mechanical_assets.extrude(p,{'asset_id':asset['asset_id'],'path':'cad/multi.cad.json','thickness':2})
    assert model['metrics']['solids']==2
    assert [b['name'] for b in model['metrics']['bodies']]==[b['name'] for b in profiles]
    assert model['metrics']['bodies'][1]['origin_mm']==pytest.approx([76.2,0,0])
    assert model['metrics']['volume_mm3']==pytest.approx(((2-math.pi*.125**2)+1)*25.4**2*2,abs=1e-5)


def test_svg_use_instances_css_and_unoutlined_text_are_reported_and_not_duplicated():
    raw=b'<svg xmlns="http://www.w3.org/2000/svg" width="40mm" height="20mm" viewBox="0 0 40 20"><defs><rect id="template" width="10" height="5"/></defs><g fill="#1a4dcc"><use id="left" href="#template" x="2" y="3"/><use id="right" href="#template" x="20" y="3"/></g><text x="0" y="18">label</text></svg>'
    value=drawing().convert('instances.svg',raw)
    assert len(value['profiles'])==2 and sum(p['topology_area_mm2'] for p in value['profiles'])==pytest.approx(100,abs=1e-6)
    assert any(row['type']=='text' for row in value['diagnostics']['ignored'])


def test_failed_or_canceled_drawing_import_and_extrusion_publish_no_partial_state(workspace,monkeypatch):
    client,p,_=workspace;asset=upload(client,p,'rounded_plate.dxf');before=copy.deepcopy(p.state['spec'])
    for height in [0,-1,True,'3',float('inf')]:
        with pytest.raises(ValueError):mechanical_assets.extrude(p,{'asset_id':asset['asset_id'],'path':'cad/bad.cad.json','thickness':height})
    assert not (p.root/'cad/bad.cad.json').exists()
    original=mechanical_assets.inspect_native
    def canceled(*args,**kwargs):
        result=original(*args,**kwargs);p.cancel.set();return result
    monkeypatch.setattr(mechanical_assets,'inspect_native',canceled)
    with pytest.raises((ValueError,RuntimeError),match='cancel'):mechanical_assets.ingest(p,{'name':'new.svg','data':base64.b64encode((FIXTURES/'bezier.svg').read_bytes()).decode()})
    assert len(mechanical_assets.listing(p)['assets'])==1 and not p.engine_busy and p.state['spec']==before


def test_svg_reference_cycles_and_path_budgets_stop_before_library_expansion(monkeypatch):
    module=drawing()
    def no_decoder(*args,**kwargs):raise AssertionError('Unsafe SVG reached the geometry decoder')
    monkeypatch.setattr(module.svg.SVG,'parse',no_decoder)
    cyclic=b'<svg xmlns="http://www.w3.org/2000/svg"><defs><g id="cycle"><use href="#cycle"/></g></defs><use href="#cycle"/></svg>'
    with pytest.raises(ValueError,match='cyclic|cycle'):module.convert('cycle.svg',cyclic)
    oversized=('<svg xmlns="http://www.w3.org/2000/svg"><path d="M'+'0 0 '*100001+'"/></svg>').encode()
    with pytest.raises(ValueError,match='budget'):module.convert('many.svg',oversized)
