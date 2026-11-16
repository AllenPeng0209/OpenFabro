"""Verify the browser routing model through real KiCad multilayer connectivity."""
import json
import subprocess
from pathlib import Path

import pytest

from wholeboard.kicad import board,cli,geometry


def test_continuous_routes_and_layer_changes_create_connected_native_copper(tmp_path):
    if not cli.find_kicad_cli():pytest.skip('Native routing acceptance requires KiCad CLI')
    spec={'name':'continuous_routing','board':{'width_mm':30,'height_mm':22,'layers':2},
        'components':[{'ref':'R1','value':'1k','symbol':'Device:R','footprint':'Resistor_SMD:R_0603_1608Metric','placement':{'x_mm':5,'y_mm':5,'rotation':0}},
            {'ref':'R2','value':'1k','symbol':'Device:R','footprint':'Resistor_SMD:R_0603_1608Metric','placement':{'x_mm':25,'y_mm':17,'rotation':0,'side':'bottom'}}],
        'nets':[{'name':'SIG','pins':['R1.1','R2.1']},{'name':'GND','pins':['R1.2','R2.2']}],
        'rules':{'track_mm':.25,'power_track_mm':.5,'clearance_mm':.2,'via_diameter_mm':.6,'via_drill_mm':.3}}
    initial=board.build(spec,tmp_path/'initial');geo=geometry.read(Path(initial['pcb']))
    script='''import fs from 'node:fs';import {beginRoute,extendRoute,changeRouteLayer} from './wholeboard/web/workbench-routing.mjs';import {copperGeometry} from './wholeboard/web/workbench-copper.mjs';let {spec,geometry}=JSON.parse(fs.readFileSync(0,'utf8'));
    for(const route of [{pin:'1',front:[[3,7]],via:[10,8],back:[[26,12]]},{pin:'2',front:[[7,3]],via:[12,3],back:[[8,3],[8,18],[22,18]]}]){
      let session=beginRoute(spec,geometry,{kind:'pad',pin:'R1.'+route.pin},{layer:'F.Cu'}),result;
      for(const at of route.front){result=extendRoute(spec,geometry,session,{kind:'point',at});spec=result.spec;session=result.session;geometry=copperGeometry(spec,geometry);}
      result=changeRouteLayer(spec,geometry,session,route.via,'B.Cu');spec=result.spec;session=result.session;geometry=copperGeometry(spec,geometry);
      for(const at of route.back){result=extendRoute(spec,geometry,session,{kind:'point',at});spec=result.spec;session=result.session;geometry=copperGeometry(spec,geometry);}
      result=extendRoute(spec,geometry,session,{kind:'pad',pin:'R2.'+route.pin});spec=result.spec;geometry=copperGeometry(spec,geometry);
    }process.stdout.write(JSON.stringify(spec));'''
    ran=subprocess.run(['node','--input-type=module','-e',script],cwd=Path(__file__).parents[1],input=json.dumps({'spec':spec,'geometry':geo}),text=True,capture_output=True,check=True)
    result=json.loads(ran.stdout);output=board.build(result,tmp_path/'routed');path=Path(output['pcb'])
    report=cli.drc(path,refill=True,save=True)
    assert report['errors']==0,report
    assert report['unconnected']==0,report
    native=geometry.read(path)
    assert len(native['vias'])==2
    assert native['ratsnest']==[]
    for net in ('SIG','GND'):
        assert {track['layer'] for track in native['tracks'] if track['net']==net}=={'F.Cu','B.Cu'}
    assert result['nets']==spec['nets']
    assert result['components']==spec['components']
