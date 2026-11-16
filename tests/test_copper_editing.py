"""Native copper edits must preserve identities and complete zone definitions."""
import json
import subprocess
from pathlib import Path
import pytest

from wholeboard import sexpr
from wholeboard import revisions
from wholeboard.kicad import board,cli,geometry
from wholeboard.sexpr import find,find_all,Sym

ID='11111111-1111-4111-8111-111111111111'


def test_revision_comparison_reports_copper_changes_instead_of_no_design_changes():
    a={'board':{},'components':[],'nets':[],'fixed_copper':[{'net':'SIG','tracks':[{'w':.25}]}]}
    b=json.loads(json.dumps(a));b['fixed_copper'][0]['tracks'][0]['w']=.24
    comparison=revisions.compare(a,b)
    assert comparison.get('field_change_count')==1
    assert 'copper' in revisions.brief(comparison).lower()


def test_full_revision_diff_respects_json_types_and_exposes_output_truncation():
    result=revisions.field_comparison({'flag':True,'stable':3},{'flag':1,'stable':3})
    assert result['field_change_count']==1
    assert result['unchanged_sections']==['stable']
    limited=revisions.field_comparison({'a':1,'b':2},{'a':3,'b':4},limit=1)
    assert limited['field_change_count']==2 and len(limited['field_changes'])==1
    assert limited['field_changes_truncated'] is True


def test_native_copper_identity_and_zone_sources_survive_regeneration(tmp_path):
    spec=json.loads((Path(__file__).parents[1]/'wholeboard/web/workbench-example.json').read_text())
    spec['fixed_copper']=[{'net':'CC1','tracks':[{'id':ID,'a':[12,12],'b':[14,12],'w':.35,'layer':'F.Cu'}]}]
    original=board.build(spec,tmp_path/'original');path=Path(original['pcb'])
    tree=sexpr.parse(path.read_text());tree.append(board.zone('GND','F.Cu',30,22,.5,.25,priority=3))
    path.write_text(sexpr.dumps(tree))
    geo=geometry.read(path)
    assert geo['tracks'][0].get('id')==ID,'Native copper identity is not preserved'
    assert len(geo.get('zone_sources',[]))==1,'The editable PCB loses its native pour definitions'
    spec['fixed_zones']=geo['zone_sources']
    rebuilt=board.build(spec,tmp_path/'rebuilt');new_path=Path(rebuilt['pcb'])
    new_geo=geometry.read(new_path)
    assert new_geo['tracks'][0]['id']==ID
    new_zone=next(find_all(sexpr.parse(new_path.read_text()),'zone'))
    assert str(find(new_zone,'net')[1])=='GND'
    assert str(find(new_zone,'priority')[1])=='3'
    assert [float(v) for v in next(find_all(find(find(new_zone,'polygon'),'pts'),'xy'))[1:]]==[100.5,100.5]
    if cli.find_kicad_cli():
        cli.drc(new_path,refill=True,save=True)
        assert geometry.read(new_path)['zones'],'Actual KiCad must refill the preserved native pour'


def test_editing_a_real_routed_board_keeps_native_connectivity(tmp_path):
    if not cli.find_kicad_cli():pytest.skip('KiCad CLI is required for routed-board editing acceptance')
    spec=json.loads((Path(__file__).parent/'fixtures/routed-usb-c-spec.json').read_text())
    group=next(c for c in spec['fixed_copper'] if c['net']=='CC1');target=group['tracks'][0]
    script='''import fs from 'node:fs';import {editCopper} from './wholeboard/web/workbench-copper.mjs';const input=JSON.parse(fs.readFileSync(0,'utf8'));process.stdout.write(JSON.stringify(editCopper(input.spec,input.geometry,input.selection,{w:.24})));'''
    baseline=board.build(spec,tmp_path/'baseline');geo=geometry.read(Path(baseline['pcb']))
    changed=subprocess.run(['node','--input-type=module','-e',script],cwd=Path(__file__).parents[1],input=json.dumps({'spec':spec,'geometry':geo,'selection':{'kind':'tracks','id':target['id']}}),text=True,capture_output=True,check=True)
    edited=json.loads(changed.stdout)
    output=board.build(edited,tmp_path/'edited');path=Path(output['pcb']);report=cli.drc(path,refill=True,save=True)
    assert report['unconnected']==0,report
    assert report['errors']==0,report
    native=geometry.read(path)
    assert len(native['tracks'])==28
    assert len(native['zone_sources'])==2
    assert len(native['vias'])==1
    assert native['ratsnest']==[]
    assert next(t for t in native['tracks'] if t['id']==target['id'])['w']==.24
