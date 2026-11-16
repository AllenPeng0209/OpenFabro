import importlib
import json
import threading
from pathlib import Path

import pytest

from wholeboard import config,design
from wholeboard.kicad import board,cli,geometry


def routing():return importlib.import_module('wholeboard.selective_routing')


def fixture(name='selective-routing'):
    return design.normalise(json.loads((Path(__file__).parent/'fixtures'/f'{name}.json').read_text()))


@pytest.fixture
def native_router(tmp_path,monkeypatch):
    binary=Path(__file__).parents[1]/'.local/wholeboard/tools/tracemaker/src/build/macos-metal/src/app/tracemaker'
    if not binary.is_file():pytest.skip('TraceMaker native binary is required')
    monkeypatch.setattr(config,'APP_DIR',tmp_path/'profile');monkeypatch.setattr(config,'CONFIG_FILE',tmp_path/'profile/config.json');config.update({'projects_dir':str(tmp_path/'projects'),'tools':{'tracemaker':str(binary)}})
    return binary


def test_exact_native_selection_routes_signal_around_existing_copper_only(tmp_path,native_router):
    spec=fixture();source=Path(board.build(spec,tmp_path/'input')['pcb']);before=geometry.read(source);raw=source.read_bytes();result=routing().route_native(source,tmp_path/'output/board.kicad_pcb',nets=['SIGNAL'],seconds=5,work=500000)
    after=geometry.read(Path(result['pcb']));assert source.read_bytes()==raw
    assert any(t['net']=='SIGNAL' for t in after['tracks'])
    for net in ['USB_DP','USB_DN']:assert not any(t['net']==net for kind in ['tracks','arcs','vias'] for t in after[kind]),'A wildcard/whole-board route modified an unrequested net'
    assert [t for t in after['tracks'] if t['net']=='KEEP']==[t for t in before['tracks'] if t['net']=='KEEP']
    assert after['pads']==before['pads'] and after['footprints']==before['footprints']
    report=cli.drc(Path(result['pcb']),refill=False,save=False);assert report['errors']==0 and report['unconnected']==2,report


def test_selector_treats_wildcards_and_commas_in_real_net_names_as_literal(tmp_path,native_router):
    spec=fixture();spec['nets'][0]['name']='SIG*,[A]';spec['nets'][1]['name']='SIG_OTHER';source=Path(board.build(spec,tmp_path/'input')['pcb']);result=routing().route_native(source,tmp_path/'output/board.kicad_pcb',nets=['SIG*,[A]'],seconds=5,work=500000);geo=geometry.read(Path(result['pcb']))
    assert any(t['net']=='SIG*,[A]' for t in geo['tracks']) and not any(t['net']=='SIG_OTHER' for t in geo['tracks'])


def test_requested_repair_moves_only_unprotected_blocker_and_joins_both_nets(tmp_path,native_router):
    spec=fixture('selective-routing-repair');source=Path(board.build(spec,tmp_path/'input')['pcb']);before=geometry.read(source)
    result=routing().route_native(source,tmp_path/'output/board.kicad_pcb',nets=['SIGNAL'],repair_nets=['BLOCKER'],seconds=5,work=500000);geo=geometry.read(Path(result['pcb']));report=cli.drc(Path(result['pcb']),refill=False,save=False)
    assert report['errors']==0 and report['unconnected']==0,report
    assert geo['pads']==before['pads'] and geo['footprints']==before['footprints']
    assert [t for t in geo['tracks'] if t['net']=='BLOCKER']!=[t for t in before['tracks'] if t['net']=='BLOCKER']
    assert not geo['vias'],'The fixture prohibits vias on both layers'


def test_protected_ring_is_not_lifted_even_when_its_net_is_in_repair_scope(tmp_path,native_router):
    spec=fixture('selective-routing-repair')
    for t in spec['fixed_copper'][0]['tracks']:t['locked']=True
    source=Path(board.build(spec,tmp_path/'input')['pcb']);before=geometry.read(source);result=routing().route_native(source,tmp_path/'output/board.kicad_pcb',nets=['SIGNAL'],repair_nets=['BLOCKER'],seconds=3,work=250000);after=geometry.read(Path(result['pcb']))
    assert [t for t in after['tracks'] if t['net']=='BLOCKER']==[t for t in before['tracks'] if t['net']=='BLOCKER']
    assert not any(t['net']=='SIGNAL' for t in after['tracks'])
    assert result['returncode']==3,'An unroutable selected connection must retain its explicit partial result'


def test_canceled_native_job_never_starts_or_publishes_an_output(tmp_path,native_router):
    source=Path(board.build(fixture(),tmp_path/'input')['pcb']);cancel=threading.Event();cancel.set();target=tmp_path/'output/board.kicad_pcb'
    with pytest.raises(InterruptedError):routing().route_native(source,target,nets=['SIGNAL'],cancel=cancel)
    assert not target.exists()


def test_declared_named_pair_uses_actual_native_coupled_routing(tmp_path,native_router):
    spec=fixture();spec['board']['timing']={'track_ps_per_mm':{'F.Cu':7,'In1.Cu':7,'In2.Cu':7,'B.Cu':7},'via_ps_per_mm':0};source=Path(board.build(spec,tmp_path/'input')['pcb'])
    result=routing().route_native(source,tmp_path/'output/board.kicad_pcb',nets=['USB_DP','USB_DN'],seconds=5,work=1000000,diff_pairs=True)
    report=cli.drc(Path(result['pcb']),refill=False,save=False);assert report['errors']==0 and report['unconnected']==1,report
    assert result['summary'].get('pair_work',0)>0,'The native result must report an actual coupled search'
    pair=next(p for p in result['summary'].get('pairs',[]) if {p['net_a'],p['net_b']}=={'USB_DP','USB_DN'})
    assert pair['coupled_share']>.5,'The returned native geometry is not predominantly coupled'


def test_legacy_uuidless_copper_keeps_original_protection_after_private_input_locks(tmp_path,native_router):
    from wholeboard import sexpr
    spec=fixture();spec['fixed_copper'][0]['tracks'][0]['locked']=False;source=Path(board.build(spec,tmp_path/'input')['pcb']);tree=sexpr.parse(source.read_text());segment=next(sexpr.find_all(tree,'segment'));segment.remove(sexpr.find(segment,'uuid'));source.write_text(sexpr.dumps(tree));before=geometry.read(source)
    result=routing().route_native(source,tmp_path/'output/board.kicad_pcb',nets=['SIGNAL'],seconds=3,work=500000);after=geometry.read(Path(result['pcb']))
    expected=next(t for t in before['tracks'] if not t['locked']);actual=next((t for t in after['tracks'] if t['id']==expected['id']),None)
    assert actual is not None and actual['locked'] is False,'Temporary protection changed a legacy native identity or leaked into its result'


def test_adapter_intermediate_filename_cannot_alias_its_source(tmp_path,native_router):
    spec=fixture();spec['fixed_copper'][0]['tracks'][0]['locked']=False;original=Path(board.build(spec,tmp_path/'input')['pcb']);source=original.with_name('routing-input.kicad_pcb');source.write_bytes(original.read_bytes())
    for ext in ['.kicad_pro','.kicad_dru']:source.with_suffix(ext).write_bytes(original.with_suffix(ext).read_bytes())
    raw=source.read_bytes();routing().route_native(source,source.parent/'result.kicad_pcb',nets=['SIGNAL'],seconds=3,work=500000)
    assert source.read_bytes()==raw,'The private routing input overwrote the source board'


@pytest.mark.parametrize('extension',['.kicad_pcb','.route.json','.stuck.json','.route.log','.kicad_pro','.kicad_dru'])
def test_dangling_output_or_sidecar_links_are_rejected_before_any_native_writes(tmp_path,native_router,monkeypatch,extension):
    source=Path(board.build(fixture(),tmp_path/'input')['pcb']);raw=source.read_bytes();target=tmp_path/'output/board.kicad_pcb';target.parent.mkdir();outside=tmp_path/'outside/generated';outside.parent.mkdir();target.with_suffix(extension).symlink_to(outside)
    def forbidden(*args,**kwargs):raise AssertionError('A preexisting output link reached the native process')
    monkeypatch.setattr(routing().router,'_stream',forbidden)
    with pytest.raises(ValueError,match='new private|private output'):routing().route_native(source,target,nets=['SIGNAL'])
    assert not outside.exists() and source.read_bytes()==raw


@pytest.mark.parametrize('shape',['trapezoid','custom'])
def test_direct_adapter_also_rejects_unsupported_conductive_pads_before_creating_output(tmp_path,native_router,monkeypatch,shape):
    from wholeboard import sexpr
    source=Path(board.build(fixture(),tmp_path/'input')['pcb']);tree=sexpr.parse(source.read_text());pad=next(sexpr.find_all(next(sexpr.find_all(tree,'footprint')),'pad'));pad[3]=sexpr.Sym(shape);source.write_text(sexpr.dumps(tree));target=tmp_path/'new-output/board.kicad_pcb'
    def forbidden(*args,**kwargs):raise AssertionError('A direct native call bypassed the unsupported pad preflight')
    monkeypatch.setattr(routing().router,'_stream',forbidden)
    with pytest.raises(ValueError,match='Unsupported.*pad|unknown'):routing().route_native(source,target,nets=['SIGNAL'])
    assert not target.parent.exists()
