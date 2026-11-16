"""Published revisions and three-way updates preserve host and instance edits."""
import copy
from pathlib import Path
import pytest
from wholeboard import modules,sexpr
from wholeboard.kicad import board,geometry,schematic,cli
try:
    from wholeboard import module_updates
except ImportError:
    module_updates=None

def source():
    return {'name':'versioned_supply','board':{'width_mm':25,'height_mm':20,'layers':2,'ground_pour':None},
      'components':[{'ref':f'R{i}','value':'1k','symbol':'Device:R','footprint':'Resistor_SMD:R_0603_1608Metric','placement':{'x_mm':5+(i-1)*8,'y_mm':10,'rotation':0}} for i in (1,2)],
      'nets':[{'name':'SIG','class':'signal','pins':['R1.1','R2.1']},{'name':'GND','class':'power','pins':['R1.2','R2.2']}],
      'editor':{'positions':{'R1':[200,200],'R2':[600,200]},'connection_guides':[{'id':'signal','from':'R1.1','to':'R2.1'},{'id':'ground','from':'R1.2','to':'R2.2'}]},
      'fixed_copper':[{'net':name,'tracks':[{'id':str(__import__('uuid').uuid5(__import__('uuid').NAMESPACE_DNS,name+str(i))),'a':a,'b':b,'w':.25,'layer':'F.Cu'} for i,(a,b) in enumerate(points)]} for name,points in [('SIG',[([4.175,10],[4.175,8]),([4.175,8],[12.175,8]),([12.175,8],[12.175,10])]),('GND',[([5.825,10],[5.825,12]),([5.825,12],[13.825,12]),([13.825,12],[13.825,10])])]],'library':{'symbols':{},'footprints':{},'parts':{}}}

def published(spec=None):return modules.publish(spec or source(),name='Supply',ports={'OUT':'SIG','GND':'GND'})

def target(two=False):
    asset=published();base={'name':'module_update_host','board':{'width_mm':70,'height_mm':35,'layers':2,'ground_pour':None},
      'components':[{'ref':'J1','value':'Host','symbol':'Connector_Generic:Conn_01x02','footprint':'Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical','placement':{'x_mm':3,'y_mm':22,'rotation':0}}],
      'nets':[{'name':'BUS','class':'signal','pins':['J1.1']},{'name':'GND','class':'power','pins':['J1.2']}],
      'fixed_copper':[{'net':'GND','tracks':[{'id':'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa','a':[30,24],'b':[35,24],'w':.3,'layer':'B.Cu'}]}],
      'library':{'symbols':{},'footprints':{},'parts':{},'modules':{'Supply':asset}}}
    out=modules.instantiate(base,'Supply','M1',offset=[5,0],connections={'OUT':'BUS','GND':'GND'})
    return modules.instantiate(out,'Supply','M2',offset=[30,0],connections={'OUT':'BUS','GND':'GND'}) if two else out

def revised(project,changed):
    assert module_updates is not None,'Versioned module updates are missing'
    old=project['library']['modules']['Supply'];return module_updates.release(published(changed),previous=old,note='Update circuit')

def test_revisions_freeze_prior_content_and_reject_noop_publications():
    assert module_updates is not None,'Versioned module publishing is missing'
    original=published();before=copy.deepcopy(original);changed=source();changed['components'][1]['value']='2k';v2=module_updates.release(published(changed),previous=original,note='R2 value')
    assert v2['version']==2 and v2['history'][0]['version']==1
    assert v2['history'][0]['asset']['design']['components'][1]['value']=='1k';assert original==before
    with pytest.raises(ValueError,match='[Nn]o.*change'):module_updates.release(published(),previous=original)

def test_frozen_revision_fingerprints_survive_browser_numeric_round_trips():
    original=published();original['design']['components'][0]['placement']['x_mm']=5.0
    changed=source();changed['components'][1]['value']='2k'
    revision=module_updates.release(published(changed),previous=original)
    def browser_numbers(value):
        if isinstance(value,float) and value.is_integer():return int(value)
        if isinstance(value,list):return [browser_numbers(v) for v in value]
        if isinstance(value,dict):return {k:browser_numbers(v) for k,v in value.items()}
        return value
    wire=browser_numbers(revision);module_updates.validate_history(wire)
    assert module_updates.digest(original)==module_updates.digest(browser_numbers(original))
    wire['history'][0]['asset']['design']['components'][0]['value']='TAMPERED'
    with pytest.raises(ValueError,match='fingerprint'):module_updates.validate_history(wire)

def test_new_instances_record_stable_source_maps_and_frozen_baseline():
    out=target();meta=out['editor']['module_instances']['M1']
    assert meta.get('version')==1 and meta.get('source_maps',{}).get('refs')=={'R1':'R1','R2':'R2'}
    assert meta['baseline']['version']==1 and meta['baseline']['maps']['nets']=={'SIG':'BUS','GND':'GND'}

def test_nonconflicting_updates_preserve_local_edits_other_instances_and_every_copper_record(tmp_path):
    before=target(two=True);before['components'][1]['description']='Keep local note';before['editor']['sheets']['M1']['title']='Custom title';changed=source();changed['components'][1]['value']='2k';before['library']['modules']['Supply']=revised(before,changed);saved=copy.deepcopy(before)
    result=module_updates.prepare(before,'M1');out=result['spec'];assert not result['conflicts']
    assert next(c for c in out['components'] if c['ref']=='R2')['value']=='2k';assert next(c for c in out['components'] if c['ref']=='R1')['description']=='Keep local note'
    assert out['editor']['sheets']['M1']['title']=='Custom title';assert out['fixed_copper']==before['fixed_copper']
    assert out['editor']['module_instances']['M1']['version']==2 and out['editor']['module_instances']['M2']['version']==1
    assert [c for c in out['components'] if c.get('module_instance')=='M2']==[c for c in before['components'] if c.get('module_instance')=='M2'];assert before==saved
    native=schematic.build(out,tmp_path);assert schematic.netlist_parity(out,cli.schematic_nets(Path(native['sch'])))['ok']

def test_same_field_conflicts_require_an_explicit_choice_and_remain_local_overrides_later():
    before=target();before['components'][1]['value']='3k';changed=source();changed['components'][0]['value']='2k';before['library']['modules']['Supply']=revised(before,changed)
    pending=module_updates.prepare(before,'M1');assert pending['spec'] is None and len(pending['conflicts'])==1
    key=pending['conflicts'][0]['id'];proposal=module_updates.prepare(before,'M1',resolutions={key:'local'});kept=proposal['spec'];assert next(c for c in kept['components'] if c['ref']=='R1')['value']=='3k'
    assert 'components/R1/value' in kept['editor']['module_instances']['M1']['local_overrides']
    assert proposal.get('local_overrides')==kept['editor']['module_instances']['M1']['local_overrides']
    assert proposal['summary']['kept_local']==len(kept['editor']['module_instances']['M1']['local_overrides'])
    taken=module_updates.prepare(before,'M1',resolutions={key:'module'})['spec'];assert next(c for c in taken['components'] if c['ref']=='R1')['value']=='2k'
    changed['components'][0]['value']='4k';kept['library']['modules']['Supply']=revised(kept,changed);assert module_updates.prepare(kept,'M1')['conflicts']

def test_a_local_value_that_converges_with_the_new_release_is_not_an_override():
    before=target();before['components'][1]['value']='3k';changed=source();changed['components'][0]['value']='3k';before['library']['modules']['Supply']=revised(before,changed)
    result=module_updates.prepare(before,'M1');assert not result['conflicts']
    assert result['spec']['editor']['module_instances']['M1']['local_overrides']==[]
    assert result['spec']['editor']['module_instances']['M1']['modified'] is False
    assert result['summary']['kept_local']==len(result['spec']['editor']['module_instances']['M1']['local_overrides'])

def test_source_added_parts_do_not_reuse_a_local_component_designator():
    before=target();before['components'].append({'ref':'R3','value':'local','symbol':'Device:R','footprint':'Resistor_SMD:R_0603_1608Metric','sheet':'M1','placement':{'x_mm':25,'y_mm':20}})
    changed=source();changed['components'].append({'ref':'R3','value':'new source','symbol':'Device:R','footprint':'Resistor_SMD:R_0603_1608Metric','placement':{'x_mm':20,'y_mm':10}});before['library']['modules']['Supply']=revised(before,changed)
    out=module_updates.prepare(before,'M1')['spec'];assert next(c for c in out['components'] if c['ref']=='R3')['value']=='local'
    assert next(c for c in out['components'] if c['value']=='new source')['ref']=='R4'

def test_port_rename_preserves_external_net_binding_and_wire_anchor():
    before=target();before['editor']['connection_guides'].append({'id':'host_wire','from':'J1.1','to':'sheet:M1.OUT'});candidate=published();candidate['ports']['OUTPUT']=candidate['ports'].pop('OUT')
    assert module_updates is not None
    before['library']['modules']['Supply']=module_updates.release(candidate,previous=before['library']['modules']['Supply']);out=module_updates.prepare(before,'M1')['spec']
    assert next(g for g in out['editor']['connection_guides'] if g['id']=='host_wire')['to']=='sheet:M1.OUTPUT'
    assert out['editor']['sheets']['M1']['ports']['OUTPUT']['net']=='BUS'

def test_removed_connected_port_requires_reconnect_or_disconnect_not_silent_unbinding():
    before=target();before['editor']['connection_guides'].append({'id':'host_wire','from':'J1.1','to':'sheet:M1.OUT'});candidate=published();del candidate['ports']['OUT'];assert module_updates is not None
    before['library']['modules']['Supply']=module_updates.release(candidate,previous=before['library']['modules']['Supply']);pending=module_updates.prepare(before,'M1');assert pending['spec'] is None and pending['port_changes']
    out=module_updates.prepare(before,'M1',port_actions={'OUT':'disconnect'})['spec'];assert not any(g['id']=='host_wire' for g in out['editor']['connection_guides']);assert next(n for n in out['nets'] if n['name']=='BUS')['pins']==['J1.1']

def test_local_electrical_split_survives_a_value_only_module_revision():
    before=target();bus=next(n for n in before['nets'] if n['name']=='BUS');bus['pins'].remove('R2.1');before['nets'].append({'name':'LOCAL','class':'signal','pins':['R2.1']});before['editor']['connection_guides']=[g for g in before['editor']['connection_guides'] if g['from']!='R1.1'];changed=source();changed['components'][1]['value']='2k';before['library']['modules']['Supply']=revised(before,changed)
    out=module_updates.prepare(before,'M1')['spec'];assert next(n for n in out['nets'] if n['name']=='LOCAL')['pins']==['R2.1']

def test_source_insertion_before_existing_parts_keeps_all_prior_designators():
    before=target();changed=source();changed['components'].insert(0,{'ref':'R3','value':'added first','symbol':'Device:R','footprint':'Resistor_SMD:R_0603_1608Metric','placement':{'x_mm':20,'y_mm':15}});before['library']['modules']['Supply']=revised(before,changed)
    out=module_updates.prepare(before,'M1')['spec'];mapping=out['editor']['module_instances']['M1']['source_maps']['refs'];assert mapping['R1']=='R1' and mapping['R2']=='R2' and mapping['R3']=='R3'

def test_lock_changes_do_not_invalidate_electrically_unchanged_routing():
    before=target();changed=source();changed['components'][0]['placement']['locked']=True;before['library']['modules']['Supply']=revised(before,changed)
    out=module_updates.prepare(before,'M1')['spec'];assert out['fixed_copper']==before['fixed_copper']

def test_footprint_revision_is_namespaced_instead_of_modifying_other_instances():
    from wholeboard import project_library
    src=source();footprint=project_library.copy_installed('footprints','Resistor_SMD:R_0603_1608Metric',src);src['library']['footprints']['Shared']=footprint
    for c in src['components']:c['footprint']='Project:Shared'
    asset=published(src);before=target(two=True);before['library']['modules']['Supply']=asset
    # Build actual instances from the custom dependency before revising it.
    clean={**before,'components':[before['components'][0]],'nets':[{'name':'BUS','pins':['J1.1']},{'name':'GND','pins':['J1.2']}],'editor':{},'fixed_copper':before['fixed_copper'][:1]}
    before=modules.instantiate(clean,'Supply','M1',offset=[5,0],connections={'OUT':'BUS','GND':'GND'});before=modules.instantiate(before,'Supply','M2',offset=[30,0],connections={'OUT':'BUS','GND':'GND'})
    changed=copy.deepcopy(src);changed['library']['footprints']['Shared']['pads'][0]['w']+=.1;before['library']['modules']['Supply']=revised(before,changed)
    out=module_updates.prepare(before,'M1')['spec'];assert out['library']['footprints']['Shared']==footprint
    assert all(c['footprint']=='Project:Shared' for c in out['components'] if c.get('module_instance')=='M2')
    assert all(c['footprint']!='Project:Shared' for c in out['components'] if c.get('module_instance')=='M1')

def test_retaining_a_locally_modified_deleted_part_keeps_its_pin_memberships_and_pose():
    before=target();before['components'][2]['value']='3k';changed=source();changed['components'].pop();changed['editor']['positions'].pop('R2');changed['editor']['connection_guides']=[];changed['fixed_copper']=[]
    for n in changed['nets']:n['pins']=[p for p in n['pins'] if not p.startswith('R2.')]
    before['library']['modules']['Supply']=revised(before,changed);pending=module_updates.prepare(before,'M1');key=next(c['id'] for c in pending['conflicts'] if c['id']=='components/R2')
    out=module_updates.prepare(before,'M1',resolutions={key:'local'})['spec'];assert next(c for c in out['components'] if c['ref']=='R2')['value']=='3k';assert out['editor']['positions']['R2']==before['editor']['positions']['R2'];assert 'R2.1' in next(n for n in out['nets'] if n['name']=='BUS')['pins']

def test_native_id_and_number_format_changes_are_not_a_new_module_revision():
    import uuid
    old=published();candidate=copy.deepcopy(old)
    for c in candidate['design']['components']:
        c['placement']['side']='top';c['placement']['x_mm']=float(c['placement']['x_mm'])
    for g in candidate['design']['fixed_copper']:
        for item in g['tracks']:item['id']=str(uuid.uuid4());item['net']=g['net']
    with pytest.raises(ValueError,match='[Nn]o.*change'):module_updates.release(candidate,previous=old)

def test_publishing_freezes_actual_native_placements_without_modifying_the_source():
    src=source();before=copy.deepcopy(src);native={'bbox':[100,100,125,120],'footprints':[{'ref':'R1','x':112,'y':114,'rot':90,'side':'B.Cu'},{'ref':'R2','x':113,'y':110,'rot':0,'side':'F.Cu'}]}
    asset=modules.publish(src,name='Actual layout',native_geometry=native);part=asset['design']['components'][0]
    assert part['placement']=={'x_mm':12,'y_mm':14,'rotation':90,'side':'bottom'};assert src==before

def test_pinning_an_intermediate_revision_does_not_downgrade_the_host_library_head():
    before=target();v2source=source();v2source['components'][0]['value']='2k';v2=revised(before,v2source);v3source=copy.deepcopy(v2source);v3source['components'][1]['value']='4k';v3=module_updates.release(published(v3source),previous=v2);before['library']['modules']['Supply']=v3
    out=module_updates.prepare(before,'M1',asset=v2)['spec'];assert out['library']['modules']['Supply']['version']==3 and out['editor']['module_instances']['M1']['version']==2

def test_deleting_a_part_with_local_wire_dependencies_requires_a_choice():
    before=target();before['editor']['connection_guides'].append({'id':'local_branch','from':'R2.1','to':'R1.1'});changed=source();changed['components'].pop();changed['editor']['positions'].pop('R2');changed['editor']['connection_guides']=[];changed['fixed_copper']=[]
    for n in changed['nets']:n['pins']=[p for p in n['pins'] if not p.startswith('R2.')]
    before['library']['modules']['Supply']=revised(before,changed);pending=module_updates.prepare(before,'M1');assert pending['spec'] is None and any(c['id']=='components/R2' for c in pending['conflicts'])
    kept=module_updates.prepare(before,'M1',resolutions={'components/R2':'local'})['spec'];assert any(g['id']=='local_branch' for g in kept['editor']['connection_guides'])

def test_copper_update_summary_counts_actual_changed_tracks_not_rebuilt_groups():
    before=target();changed=source()
    for item in changed['fixed_copper'][0]['tracks']:
        for key in ('a','b'):
            if item[key][1]==8:item[key][1]=7.5
    before['library']['modules']['Supply']=revised(before,changed);result=module_updates.prepare(before,'M1');assert result['summary']['removed_copper'].get('tracks',0)==0;assert result['summary']['updated_copper']['tracks']==3
