import copy
import json
from pathlib import Path

import pytest

from wholeboard import design,sexpr
from wholeboard.kicad import board,geometry
from wholeboard.module_capture import native_copper
from test_route_tuning import fixture
from test_workbench import client


def test_native_protection_flags_round_trip_without_forcing_every_item_locked(tmp_path):
    spec,_=fixture();spec['fixed_copper'][0]['tracks'][0]['locked']=False
    spec['fixed_copper'][1]['arcs']=[{'id':'66666666-6666-4666-8666-000000000009','a':[12,20],'m':[13,21],'b':[14,20],'w':.25,'layer':'B.Cu','locked':False}]
    spec['fixed_copper'][1]['vias']=[{'id':'66666666-6666-4666-8666-000000000010','p':[14,20],'d':.6,'drill':.3,'layers':['F.Cu','B.Cu'],'locked':False}]
    spec=design.normalise(spec);before=copy.deepcopy(spec);pcb=Path(board.build(spec,tmp_path/'first')['pcb']);g=geometry.read(pcb)
    assert next(t for t in g['tracks'] if t['net']=='DP').get('locked') is False,'Explicitly unprotected copper is still forced locked'
    assert next(t for t in g['tracks'] if t['net']=='DN').get('locked') is True,'Legacy source copper must retain its protected default'
    assert g['arcs'][0].get('locked') is False and g['vias'][0].get('locked') is False
    restored=copy.deepcopy(spec);restored['fixed_copper'],restored['fixed_zones']=native_copper(g);g2=geometry.read(Path(board.build(restored,tmp_path/'second')['pcb']))
    for kind in ['tracks','arcs','vias']:assert g[kind]==g2[kind]
    assert spec==before


def test_native_bare_locked_flag_is_read_as_protected(tmp_path):
    spec,_=fixture();pcb=Path(board.build(design.normalise(spec),tmp_path)['pcb']);tree=sexpr.parse(pcb.read_text());segment=next(sexpr.find_all(tree,'segment'));flag=sexpr.find(segment,'locked');flag[1:]=[];pcb.write_text(sexpr.dumps(tree))
    assert next(t for t in geometry.read(pcb)['tracks'] if t['id']==str(sexpr.find(segment,'uuid')[1])).get('locked') is True


@pytest.mark.parametrize('value',['false',0,None])
def test_protection_is_a_strict_boolean_in_design_api(client,value):
    spec,_=fixture();pid=client.post('/api/workbench/projects',json={'title':'Protection validation','spec':spec}).json()['id'];spec['fixed_copper'][0]['tracks'][0]['locked']=value
    response=client.put(f'/api/workbench/projects/{pid}/design',json={'base_version':1,'spec':spec});assert response.status_code==422,response.text
    assert client.get('/api/projects/'+pid).json()['state']['workbench']['version']==1


def test_explicit_tuning_preserves_the_original_automation_protection_state():
    from wholeboard import route_tuning
    spec,geo=fixture()
    for t in geo['tracks']:t['locked']=t['net']!='CLK'
    result=route_tuning.prepare(spec,geo,{'nets':['CLK'],'target_mm':55})
    group=next(g for g in result['spec']['fixed_copper'] if g['net']=='CLK')
    assert all(v.get('locked') is False for kind in ['tracks','arcs'] for v in group[kind]),'Tuning silently protected previously unprotected copper'


def test_module_content_treats_missing_protection_as_legacy_true_without_changing_frozen_digests():
    from wholeboard import modules,module_updates
    spec,_=fixture();asset=modules.publish(spec,name='Protection module');explicit=copy.deepcopy(asset)
    for group in explicit['design']['fixed_copper']:
        for kind in ['tracks','arcs','vias']:
            for item in group.get(kind,[]):item['locked']=True
    assert module_updates.content_digest(asset)==module_updates.content_digest(explicit)
    assert module_updates.digest(asset)!=module_updates.digest(explicit),'Immutable release identity must still describe exact stored content'
    explicit['design']['fixed_copper'][0]['tracks'][0]['locked']=False
    assert module_updates.content_digest(asset)!=module_updates.content_digest(explicit)


def test_invalid_module_protection_cannot_enter_a_portable_library():
    from wholeboard import modules
    spec,_=fixture();asset=modules.publish(spec,name='Protection module');asset['design']['fixed_copper'][0]['tracks'][0]['locked']='false'
    with pytest.raises(ValueError,match='protection|boolean'):modules.validate_asset('Protection',asset)


def test_legacy_producer_migration_preserves_every_old_file_and_repairs_explicit_protection(client,monkeypatch):
    from wholeboard import server,workbench_native
    spec,_=fixture();spec['fixed_copper'][0]['tracks'][0]['locked']=False
    pid=client.post('/api/workbench/projects',json={'title':'Native protection migration','spec':spec}).json()['id'];p=server.mgr().get(pid);source=copy.deepcopy(p.state['spec']);serialize=board.fixed_copper
    def legacy_copper(value):
        value=copy.deepcopy(value)
        for group in value.get('fixed_copper',[]):
            for kind in ['tracks','arcs','vias']:
                for item in group.get(kind,[]):item['locked']=True
        return serialize(value)
    with monkeypatch.context() as old:
        old.setattr(workbench_native,'NATIVE_SCHEMA',19);old.setattr(geometry,'SCHEMA',4);old.setattr(board,'fixed_copper',legacy_copper)
        previous=workbench_native.generate(p)
    frozen={f:(f.read_bytes(),f.stat().st_mtime_ns) for kind in ['native','history'] for f in (p.root/kind).rglob('*') if f.is_file()}
    assert next(t for t in geometry.read(Path(previous['pcb']))['tracks'] if t['net']=='DP')['locked'] is True
    current=workbench_native.generate(p)
    assert current['schema']==20 and current['geometry_schema']==geometry.SCHEMA and current['pcb']!=previous['pcb']
    assert next(t for t in geometry.read(Path(current['pcb']))['tracks'] if t['net']=='DP')['locked'] is False
    assert all((f.read_bytes(),f.stat().st_mtime_ns)==value for f,value in frozen.items())
    assert p.state['spec']==source and p.state['workbench']['version']==1
    snapshot={f:(f.read_bytes(),f.stat().st_mtime_ns) for f in Path(current['pcb']).parent.rglob('*') if f.is_file()}
    assert workbench_native.generate(p)['pcb']==current['pcb']
    assert all((f.read_bytes(),f.stat().st_mtime_ns)==value for f,value in snapshot.items())
