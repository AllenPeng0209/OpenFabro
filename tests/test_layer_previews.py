"""Layer viewing exports native aperture paths without changing a saved design or old CAD."""
import copy
import hashlib
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

import pytest
from fastapi.testclient import TestClient

from wholeboard import server,workbench
from wholeboard.kicad import cli
from test_workbench import client
from test_project_library import custom_spec
from test_collaboration import workspace,account,login


def create(client):
 response=client.post('/api/workbench/projects',json={'title':'Native layer preview','spec':custom_spec()});assert response.status_code==201,response.text
 pid=response.json()['id'];native=client.post(f'/api/workbench/projects/{pid}/native').json()
 return pid,server.mgr().get(pid),native


def identities(folder):
 return {p:(hashlib.sha256(p.read_bytes()).hexdigest(),p.stat().st_mtime_ns) for p in folder.rglob('*') if p.is_file()}


@pytest.mark.parametrize('layer',['F.Mask','B.Mask','F.Paste','B.Paste'])
def test_native_aperture_view_uses_absolute_board_coordinates_and_preserves_saved_files(client,layer):
 pid,p,native=create(client);before=copy.deepcopy(p.state['spec']);old=identities(Path(native['pcb']).parent)
 response=client.post(f'/api/workbench/projects/{pid}/layer-preview',json={'layer':layer});assert response.status_code==200,response.text
 view=response.json();assert view['coordinate_space']=='pcb-mm' and view['source_version']==1 and view['layer']==layer
 assert view['pcb_sha256']==hashlib.sha256(Path(native['pcb']).read_bytes()).hexdigest()
 data=client.get(view['url']);assert data.status_code==200;root=ET.fromstring(data.text)
 assert root.tag.endswith('svg') and len(root.attrib['viewBox'].split())==4
 if layer.startswith('F.'):
  paths=root.findall('.//{http://www.w3.org/2000/svg}path');assert paths
  assert any('112.' in node.get('d','') or '113.' in node.get('d','') for node in paths),'SVG coordinates were cropped to a separate layer-local origin'
 assert p.state['spec']==before and p.state['workbench']['version']==1
 assert all((hashlib.sha256(f.read_bytes()).hexdigest(),f.stat().st_mtime_ns)==v for f,v in old.items())


@pytest.mark.parametrize('layer',['F.Cu','../../file',None,{'layer':'F.Mask'}])
def test_layer_preview_rejects_unapproved_layers_without_generating_native_files(client,layer):
 pid=client.post('/api/workbench/projects',json={'title':'Invalid native layer','spec':custom_spec()}).json()['id'];p=server.mgr().get(pid)
 r=client.post(f'/api/workbench/projects/{pid}/layer-preview',json={'layer':layer});assert r.status_code==422,r.text
 assert p.state['workbench']['version']==1 and not (p.root/'native').exists()


def test_native_layer_cache_is_reused_without_running_export_again(client,monkeypatch):
 pid,p,native=create(client);url=f'/api/workbench/projects/{pid}/layer-preview';first=client.post(url,json={'layer':'F.Mask'});assert first.status_code==200,first.text
 files=identities(Path(native['pcb']).parent)
 def forbidden(*args,**kwargs):raise AssertionError('A cached native view reran KiCad')
 monkeypatch.setattr(cli,'run',forbidden);second=client.post(url,json={'layer':'F.Mask'});assert second.status_code==200,second.text
 assert first.json()==second.json();assert all((hashlib.sha256(f.read_bytes()).hexdigest(),f.stat().st_mtime_ns)==v for f,v in files.items())


def test_failed_layer_export_cannot_publish_an_empty_or_stale_success(client,monkeypatch):
 pid,p,native=create(client);monkeypatch.setattr(cli,'run',lambda *a,**k:subprocess.CompletedProcess([],1,'','Layer export fixture failure'))
 r=client.post(f'/api/workbench/projects/{pid}/layer-preview',json={'layer':'F.Paste'});assert r.status_code==422,r.text
 assert p.state['workbench']['version']==1 and Path(native['pcb']).is_file()


def test_design_changed_during_layer_export_is_rejected(client,monkeypatch):
 pid,p,native=create(client);original=cli.run;changed=False
 def change(*args,**kwargs):
  nonlocal changed
  result=original(*args,**kwargs)
  if not changed and args[0][:3]==['pcb','export','svg']:
   changed=True;spec=copy.deepcopy(p.state['spec']);spec['components'][0]['value']='Peer changed value'
   saved=client.put(f'/api/workbench/projects/{pid}/design',json={'base_version':1,'spec':spec});assert saved.status_code==200,saved.text
  return result
 monkeypatch.setattr(cli,'run',change);r=client.post(f'/api/workbench/projects/{pid}/layer-preview',json={'layer':'F.Mask'})
 assert r.status_code==409,r.text;assert p.state['workbench']['version']==2


def test_viewer_can_read_native_layer_preview_but_other_users_cannot(workspace):
 owner,_,made=workspace;remote=TestClient(server.app,client=('192.0.2.99',5000));member=account(owner);login(remote);url=f'/api/workbench/projects/{made["id"]}/layer-preview'
 assert remote.post(url,json={'layer':'F.Mask'}).status_code==403
 owner.put(f'/api/workbench/projects/{made["id"]}/members/{member["id"]}',json={'role':'viewer'})
 response=remote.post(url,json={'layer':'F.Mask'});assert response.status_code==200,response.text
 assert remote.get(response.json()['url']).status_code==200
 assert remote.get(f'/api/projects/{made["id"]}').json()['state']['workbench']['version']==1


def test_layout_geometry_identifies_the_same_pcb_used_by_native_apertures(client):
 pid,p,native=create(client);view=client.get(f'/api/workbench/projects/{pid}/layout-geometry').json();aperture=client.post(f'/api/workbench/projects/{pid}/layer-preview',json={'layer':'F.Mask'}).json()
 assert view.get('pcb_sha256')==aperture['pcb_sha256'] and view.get('source_version')==1
 assert view['source']=='draft'


def test_routed_layout_changed_during_read_cannot_be_bound_to_new_layer_svg(client,monkeypatch):
 from wholeboard.kicad import geometry
 pid,p,native=create(client);p.state['artifacts']={'pcb':native['pcb']};p.state['workbench']['checks_stale']=False;p.save();original=geometry.read
 def changed(path):
  result=original(path);spec=copy.deepcopy(p.state['spec']);spec['components'][0]['value']='Peer update during geometry read'
  r=client.put(f'/api/workbench/projects/{pid}/design',json={'base_version':1,'spec':spec});assert r.status_code==200,r.text
  return result
 monkeypatch.setattr(geometry,'read',changed);r=client.get(f'/api/workbench/projects/{pid}/layout-geometry');assert r.status_code==409,r.text


def test_source_change_immediately_after_native_generation_does_not_relabel_old_geometry(client,monkeypatch):
 from wholeboard import workbench_native
 pid,p,native=create(client);original=workbench_native.generate
 def changed(project):
  result=original(project);spec=copy.deepcopy(p.state['spec']);spec['components'][0]['value']='Peer after native result'
  response=client.put(f'/api/workbench/projects/{pid}/design',json={'base_version':1,'spec':spec});assert response.status_code==200,response.text
  return result
 monkeypatch.setattr(workbench_native,'generate',changed);response=client.get(f'/api/workbench/projects/{pid}/layout-geometry');assert response.status_code==409,response.text


def test_changed_native_bytes_cannot_be_paired_with_an_old_geometry_sidecar(client,monkeypatch):
 from wholeboard import workbench_native
 pid,p,native=create(client);original=workbench_native.generate
 def changed(project):
  result=original(project);path=Path(result['pcb']);path.write_text(path.read_text().replace('(at 15 11)', '(at 18 11)')+'\n')
  return result
 monkeypatch.setattr(workbench_native,'generate',changed);response=client.get(f'/api/workbench/projects/{pid}/layout-geometry');assert response.status_code==409,response.text


def test_layer_cache_includes_native_project_and_rule_inputs(client):
 pid,p,native=create(client);url=f'/api/workbench/projects/{pid}/layer-preview';a=client.post(url,json={'layer':'F.Mask'});assert a.status_code==200,a.text
 rules=Path(native['pcb']).with_suffix('.kicad_dru');rules.write_text(rules.read_text()+'\n# changed native plot rules\n')
 b=client.post(url,json={'layer':'F.Mask'});assert b.status_code==200,b.text
 assert a.json().get('render_inputs_sha256')!=b.json().get('render_inputs_sha256'),'Auxiliary KiCad settings were absent from the native plot cache identity'
 assert a.json()['pcb_sha256']==b.json()['pcb_sha256']


def test_project_settings_changed_while_plotting_reject_the_old_layer(client,monkeypatch):
 pid,p,native=create(client);original=cli.run
 def changed(*args,**kwargs):
  result=original(*args,**kwargs)
  if args[0][:3]==['pcb','export','svg']:
   rules=Path(native['pcb']).with_suffix('.kicad_dru');rules.write_text(rules.read_text()+'\n# peer native settings edit\n')
  return result
 monkeypatch.setattr(cli,'run',changed);response=client.post(f'/api/workbench/projects/{pid}/layer-preview',json={'layer':'F.Mask'});assert response.status_code==409,response.text


@pytest.mark.parametrize('kind',['footprints','pads'])
def test_personal_object_hiding_filters_native_apertures_without_changing_cad(client,kind):
 from wholeboard.kicad import geometry
 pid,p,native=create(client);url=f'/api/workbench/projects/{pid}/layer-preview';geo=geometry.read(Path(native['pcb']));before=identities(Path(native['pcb']).parent)
 full=client.post(url,json={'layer':'F.Mask'});assert full.status_code==200,full.text
 filtered=client.post(url,json={'layer':'F.Mask','hidden':{kind:[geo[kind][0]['id']]}});assert filtered.status_code==200,filtered.text
 def paths(reply):return ET.fromstring(client.get(reply.json()['url']).text).findall('.//{http://www.w3.org/2000/svg}path')
 assert len(paths(filtered))<len(paths(full)),'Hidden native objects remained in the mask plot'
 assert filtered.json()['pcb_sha256']==full.json()['pcb_sha256'] and filtered.json()['render_inputs_sha256']==full.json()['render_inputs_sha256']
 assert filtered.json()['visibility_sha256']!=full.json()['visibility_sha256']
 assert p.state['workbench']['version']==1
 assert all((hashlib.sha256(f.read_bytes()).hexdigest(),f.stat().st_mtime_ns)==v for f,v in before.items())


def test_native_view_filter_rejects_unrecognized_object_ids(client):
 pid,p,native=create(client);response=client.post(f'/api/workbench/projects/{pid}/layer-preview',json={'layer':'F.Mask','hidden':{'pads':['not-a-native-pad']}});assert response.status_code==422,response.text


def test_hiding_a_printed_reference_keeps_its_semantic_identity_for_native_rules(client):
 from wholeboard import workbench_native,sexpr
 from wholeboard.kicad import geometry
 pid,p,native=create(client);path=Path(native['pcb']);geo=geometry.read(path);reference=next(d for d in geo['drawings'] if d.get('role')=='reference')
 filtered=sexpr.parse(workbench_native._filtered_plot(path.read_bytes(),{'drawings':[reference['id']]}).decode())
 footprint=next(sexpr.find_all(filtered,'footprint'));properties={str(prop[1]):str(prop[2]) for prop in sexpr.find_all(footprint,'property')}
 assert properties.get('Reference')=='U1','A visual filter removed the reference used by native rules and text variables'
