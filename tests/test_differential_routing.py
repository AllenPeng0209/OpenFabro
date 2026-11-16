"""Simultaneous browser pair routing must survive actual KiCad connectivity and DRC."""
import copy
import json
import subprocess
from pathlib import Path
from wholeboard import routing_pairs
from wholeboard.kicad import board,geometry,cli
from test_routing_pairs import fixture

def test_pair_corners_and_paired_through_vias_connect_both_nets_without_replacing_other_copper(tmp_path):
    spec=fixture();spec['fixed_copper']=[{'net':name,'tracks':[{'id':f'33333333-3333-4333-8333-{i:012d}','a':[8,8+(i-1)*2.54],'b':[38,8+(i-1)*2.54],'w':.25,'layer':'B.Cu'}]} for i,name in [(3,'D1_P'),(4,'D1_N')]]
    saved=copy.deepcopy(spec);initial=board.build(spec,tmp_path/'before');geo=geometry.read(Path(initial['pcb']));profiles=routing_pairs.hints(spec)
    script="""import fs from 'node:fs';import {beginRoute,extendRoute,changeRouteLayer} from './wholeboard/web/workbench-routing.mjs';import {copperGeometry} from './wholeboard/web/workbench-copper.mjs';let {spec,geometry,profiles}=JSON.parse(fs.readFileSync(0,'utf8'));const pad=(ref,name)=>({kind:'pad',pin:ref+'.'+name,padId:geometry.pads.find(p=>p.ref===ref&&p.name===name).id});let session=beginRoute(spec,geometry,pad('J1','1'),{layer:'F.Cu',profiles});if(!session.pair)throw Error('Pair session missing');for(const at of [[14,9.27],[20,6],[24,9.27]]){const r=extendRoute(spec,geometry,session,{kind:'point',at});spec=r.spec;session=r.session;geometry=copperGeometry(spec,geometry);}let r=changeRouteLayer(spec,geometry,session,[26,9.27],'B.Cu');spec=r.spec;session=r.session;geometry=copperGeometry(spec,geometry);r=extendRoute(spec,geometry,session,pad('J2','1'));if(!r.finished)throw Error('Pair did not finish');process.stdout.write(JSON.stringify(r.spec));"""
    ran=subprocess.run(['node','--input-type=module','-e',script],cwd=Path(__file__).parents[1],input=json.dumps({'spec':spec,'geometry':geo,'profiles':profiles}),capture_output=True,text=True,check=True)
    routed=json.loads(ran.stdout);output=board.build(routed,tmp_path/'after');native=geometry.read(Path(output['pcb']));report=cli.drc(Path(output['pcb']),refill=False,save=False)
    assert report['errors']==0,report
    assert report['unconnected']==0,report
    assert len(native['vias'])==2 and {v['net'] for v in native['vias']}=={'D0_P','D0_N'}
    assert routed['nets']==saved['nets'] and routed['components']==saved['components']
    for name in ['D1_P','D1_N']:
        assert [t for t in native['tracks'] if t['net']==name]==[t for t in geo['tracks'] if t['net']==name]
    for name in ['D0_P','D0_N']:assert {t['layer'] for t in native['tracks'] if t['net']==name}=={'F.Cu','B.Cu'}

def test_existing_pair_vias_are_reused_in_actual_native_output_without_duplicate_holes(tmp_path):
    spec=fixture();spec['fixed_copper']=[{'net':name,'tracks':[{'id':f'33333333-3333-4333-8333-{i:012d}','a':[8,8+(i-1)*2.54],'b':[38,8+(i-1)*2.54],'w':.25,'layer':'B.Cu'}]} for i,name in [(3,'D1_P'),(4,'D1_N')]]
    for index,(net,y) in enumerate([('D0_P',8.8695),('D0_N',9.6705)]):spec['fixed_copper'].append({'net':net,'vias':[{'id':f'44444444-4444-4444-8444-{index:012d}','p':[20,y],'d':.6,'drill':.3,'layers':['F.Cu','B.Cu'],'type':'through'}]})
    initial=board.build(spec,tmp_path/'before');geo=geometry.read(Path(initial['pcb']));profiles=routing_pairs.hints(spec)
    script="""import fs from 'node:fs';import {beginRoute,extendRoute,changeRouteLayer} from './wholeboard/web/workbench-routing.mjs';import {copperGeometry} from './wholeboard/web/workbench-copper.mjs';let {spec,geometry,profiles}=JSON.parse(fs.readFileSync(0,'utf8'));const pad=(ref,name)=>({kind:'pad',pin:ref+'.'+name,padId:geometry.pads.find(p=>p.ref===ref&&p.name===name).id});const session=beginRoute(spec,geometry,pad('J1','1'),{profiles,width:.25,gap:.2});const r=changeRouteLayer(spec,geometry,session,[20,9.27],'B.Cu');const finish=extendRoute(r.spec,copperGeometry(r.spec,geometry),r.session,pad('J2','1'));process.stdout.write(JSON.stringify(finish.spec));"""
    ran=subprocess.run(['node','--input-type=module','-e',script],cwd=Path(__file__).parents[1],input=json.dumps({'spec':spec,'geometry':geo,'profiles':profiles}),capture_output=True,text=True,check=True)
    routed=json.loads(ran.stdout);output=board.build(routed,tmp_path/'after');native=geometry.read(Path(output['pcb']));report=cli.drc(Path(output['pcb']),refill=False,save=False)
    assert report['errors']==0 and report['unconnected']==0,report
    assert native['vias']==geo['vias'] and len(native['vias'])==2
