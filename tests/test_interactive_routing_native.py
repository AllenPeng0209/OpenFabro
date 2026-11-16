import copy,json,subprocess,math
import pytest
from pathlib import Path
from wholeboard import design,routing_pairs
from wholeboard.kicad import board,cli,geometry,schematic

ROOT=Path(__file__).parents[1]
def fixture(name='interactive-routing'):
    return design.normalise(json.loads((ROOT/'tests/fixtures'/f'{name}.json').read_text()))

def run_browser_model(spec,geo,steps,mode='walkaround',pin='TP1.1',start=None):
    script="""import {beginRoute,previewRoute,extendRoute,changeRouteLayer} from './wholeboard/web/workbench-routing.mjs';
import {copperGeometry} from './wholeboard/web/workbench-copper.mjs';
let raw='';for await(const chunk of process.stdin)raw+=chunk;const input=JSON.parse(raw);let s=input.spec,g=input.geometry,session=beginRoute(s,g,input.start||{kind:'pad',pin:input.pin},{obstacleMode:input.mode,profiles:input.profiles}),proof=[];
for(const target of input.steps){const preview=target.kind==='layer'?null:previewRoute(s,g,session,target),result=target.kind==='layer'?changeRouteLayer(s,g,session,target.at,target.layer):extendRoute(s,g,session,target);proof.push({preview,shoves:result.shoves,finished:result.finished});s=result.spec;session=result.session;g=copperGeometry(s,g);}
process.stdout.write(JSON.stringify({spec:s,proof}));
"""
    result=subprocess.run(['node','--input-type=module','-e',script],cwd=ROOT,input=json.dumps({'spec':spec,'geometry':geo,'steps':steps,'mode':mode,'pin':pin,'start':start,'profiles':routing_pairs.hints(spec)}),text=True,capture_output=True,timeout=30)
    assert result.returncode==0,result.stderr
    return json.loads(result.stdout)

def native(spec,folder):
    pcb=Path(board.build(spec,folder)['pcb']);return pcb,geometry.read(pcb)

def prove(spec,folder):
    pcb,geo=native(spec,folder);report=cli.drc(pcb,refill=False,save=False);assert report['errors']==0 and report['unconnected']==0,report
    sch=schematic.build(spec,folder);assert schematic.netlist_parity(spec,cli.schematic_nets(Path(sch['sch'])))['ok'];return geo

def test_actual_browser_walkaround_keeps_protected_copper_and_has_clean_native_connectivity(tmp_path):
    spec=fixture()
    for group in spec['fixed_copper']:
        for track in group['tracks']:track['locked']=True
    _,before=native(spec,tmp_path/'before');result=run_browser_model(spec,before,[{'kind':'pad','pin':'TP2.1'}]);after=prove(result['spec'],tmp_path/'after')
    for net in ['N','KEEP']:assert [t for t in after['tracks'] if t['net']==net]==[t for t in before['tracks'] if t['net']==net]
    for key in ['pads','footprints','outline']:assert after[key]==before[key]
    for key in ['board','rules','components','nets']:assert result['spec'][key]==spec[key]
    assert len(result['proof'][0]['preview']['paths'][0]['points'])>2

def test_actual_browser_shove_preserves_a_native_branch_and_connects_both_halves(tmp_path):
    spec=fixture();_,before=native(spec,tmp_path/'before');result=run_browser_model(spec,before,[{'kind':'point','at':[21,10]},{'kind':'pad','pin':'TP2.1'}],mode='shove');after=prove(result['spec'],tmp_path/'after')
    assert result['proof'][0]['shoves'] and result['proof'][1]['finished']
    immutable={t['id']:t for t in before['tracks'] if t['locked']}
    for t in after['tracks']:
        if t['id'] in immutable:assert t==immutable.pop(t['id'])
    assert not immutable
    assert after['pads']==before['pads'] and after['footprints']==before['footprints']
    assert any(t['id']=='aaaaaaaa-aaaa-4aaa-8aaa-000000000001' and t['locked'] is False for t in after['tracks'])

def test_actual_paired_browser_walkaround_retains_native_spacing_and_foreign_copper(tmp_path):
    spec=fixture('selective-routing');spec['fixed_copper'].append({'net':'SIGNAL','tracks':[{'id':'bbbbbbbb-bbbb-4bbb-8bbb-000000000001','a':[8,8],'b':[50,8],'w':.25,'layer':'In1.Cu','locked':True}]});_,before=native(spec,tmp_path/'before')
    result=run_browser_model(spec,before,[{'kind':'pad','pin':'J2.2'}],pin='J1.2');after=prove(result['spec'],tmp_path/'after')
    for kind in ['tracks','arcs','vias']:assert [t for t in after[kind] if t['net'] in ['KEEP','SIGNAL']]==[t for t in before[kind] if t['net'] in ['KEEP','SIGNAL']]


@pytest.mark.parametrize('obstacle',['via','arc','rotated_pad','hole','keepout','footprint_cutout','copper_graphic'])
def test_actual_native_obstacles_remain_clear_after_browser_routing(tmp_path,obstacle):
    spec=fixture();group=spec['fixed_copper'][0]
    if obstacle=='via':
        group['vias']=[{'id':'cccccccc-cccc-4ccc-8ccc-000000000001','p':[18,10],'d':1,'drill':.4,'layers':['F.Cu','B.Cu']}];group['tracks'].append({'id':'cccccccc-cccc-4ccc-8ccc-000000000002','a':[18,10],'b':[20,10],'w':.25,'layer':'F.Cu'})
    elif obstacle=='arc':
        line=group['tracks'].pop(0);group['arcs']=[{'id':line['id'],'a':[20,5],'m':[27.5,12.5],'b':[20,20],'w':.4,'layer':'F.Cu','locked':True}];group['tracks'][0].update(a=[24,15],b=[20+math.sqrt(7.5**2-2.5**2),15])
    elif obstacle=='keepout':
        zone=copy.deepcopy(fixture('selective-routing-repair')['fixed_zones'][0]);zone['source']=zone['source'].replace('(tracks allowed)','(tracks not_allowed)').replace('(vias not_allowed)','(vias allowed)').replace('(xy 100.2 100.2) (xy 117.8 100.2) (xy 117.8 115.8) (xy 100.2 115.8)','(xy 112 108) (xy 116 108) (xy 116 112) (xy 112 112)');spec['fixed_zones']=[zone]
    else:
        name={'rotated_pad':'Rotated','hole':'Hole','footprint_cutout':'Cutout','copper_graphic':'CopperGraphic'}[obstacle];asset={'name':name,'mount':'smd','height_mm':.035,'courtyard':[-2.1,-2.1,2.1,2.1],'graphics':[],'pads':[]}
        if obstacle=='rotated_pad':asset['pads']=[{'name':'1','kind':'smd','shape':'rect','x':0,'y':0,'w':3,'h':1,'layer':'F.Cu','paste':False}]
        elif obstacle=='hole':asset.update(mount='through_hole');asset['pads']=[{'name':'','kind':'np_thru_hole','shape':'circle','x':0,'y':0,'w':2,'h':2,'drill':2,'layer':'*.Cu'}]
        else:asset['graphics']=[{'kind':'rectangle','start':[-2,-2],'end':[2,2],'layer':'F.Cu' if obstacle=='copper_graphic' else 'Edge.Cuts','fill':'solid' if obstacle=='copper_graphic' else 'none','width':.05}]
        spec['library']['footprints'][name]=asset;component={**copy.deepcopy(spec['components'][0]),'ref':'TP8','footprint':'Project:'+name,'placement':{'x_mm':18 if obstacle=='rotated_pad' else 14,'y_mm':10,'rotation':45 if obstacle=='rotated_pad' else 0}};spec['components'].append(component)
        if obstacle=='rotated_pad':spec['nets'][1]['pins'].append('TP8.1');group['tracks'].append({'id':'cccccccc-cccc-4ccc-8ccc-000000000003','a':[18,10],'b':[20,10],'w':.25,'layer':'F.Cu'})
        if obstacle in ['footprint_cutout','copper_graphic']:
            for ref,x,y in [('TP3',20,18),('TP4',20,25),('TP5',24,20),('TP6',8,27),('TP7',32,27)]:next(c for c in spec['components'] if c['ref']==ref)['placement'].update(x_mm=x,y_mm=y)
            group['tracks'][0].update(a=[20,18],b=[20,25]);group['tracks'][1].update(a=[20,20],b=[24,20]);spec['fixed_copper'][1]['tracks'][0].update(a=[8,27],b=[32,27])
    pcb,before=native(spec,tmp_path/'before');baseline=cli.drc(pcb,refill=False,save=False);assert baseline['errors']==0 and baseline['unconnected']==1,baseline
    result=run_browser_model(spec,before,[{'kind':'pad','pin':'TP2.1'}]);after=prove(result['spec'],tmp_path/'after')
    assert after['pads']==before['pads'] and after['footprints']==before['footprints']


def test_branching_on_protected_native_copper_keeps_its_identity_span_and_connects(tmp_path):
    spec=fixture();spec['components']=spec['components'][:3];spec['components'][2]['placement']={'x_mm':15,'y_mm':15};spec['nets']=[{'name':'SIG','pins':['TP1.1','TP2.1','TP3.1']}];identifier='dddddddd-dddd-4ddd-8ddd-000000000001';spec['fixed_copper']=[{'net':'SIG','tracks':[{'id':identifier,'a':[5,10],'b':[30,10],'w':.25,'layer':'F.Cu','locked':True}]}];_,before=native(spec,tmp_path/'before')
    result=run_browser_model(spec,before,[{'kind':'pad','pin':'TP3.1'}],start={'kind':'tracks','id':identifier,'at':[115,110]});after=prove(result['spec'],tmp_path/'after');assert next(t for t in after['tracks'] if t['id']==identifier)==before['tracks'][0] and len(after['tracks'])==2


def test_approaching_a_through_pad_changes_layer_without_drilling_another_hole(tmp_path):
    spec=fixture();spec['components']=spec['components'][:3];spec['components'][1].update(footprint='Project:Through',placement={'x_mm':15,'y_mm':10});spec['components'][2]['placement']={'x_mm':30,'y_mm':10,'side':'bottom'};spec['nets']=[{'name':'SIG','pins':['TP1.1','TP2.1','TP3.1']}];spec['fixed_copper']=[];asset=copy.deepcopy(spec['library']['footprints']['PadA']);asset.update(name='Through',mount='through_hole',courtyard=[-.9,-.9,.9,.9]);asset['pads'][0].update(kind='thru_hole',shape='circle',w=1.7,h=1.7,drill=1,layer='*.Cu');spec['library']['footprints']['Through']=asset;_,before=native(spec,tmp_path/'before')
    result=run_browser_model(spec,before,[{'kind':'layer','at':[15,10],'layer':'B.Cu'},{'kind':'pad','pin':'TP3.1'}]);after=prove(result['spec'],tmp_path/'after');assert not after['vias'] and after['pads']==before['pads'] and {t['layer'] for t in after['tracks']}=={'F.Cu','B.Cu'}
