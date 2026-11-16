import importlib
import math

import pytest


def geometry():
    return importlib.import_module('wholeboard.tuning_geometry')


def test_rounded_trombone_has_exact_added_length_and_real_quarter_circle_arcs():
    result=geometry().pattern(30,10,style='trombone',radius=1,pitch=6,loops=1)
    tracks=[p for p in result['primitives'] if p['kind']=='tracks'];arcs=[p for p in result['primitives'] if p['kind']=='arcs']
    assert len(arcs)==4
    assert math.fsum(math.dist(p['a'],p['b']) for p in tracks)==pytest.approx(40-2*math.pi,abs=1e-6)
    assert result['primitives'][0]['a']==pytest.approx([0,0])
    assert result['primitives'][-1]['b']==pytest.approx([30,0])
    assert result['length_mm']==pytest.approx(40,abs=1e-6)


@pytest.mark.parametrize('style',['trombone','accordion','sawtooth'])
def test_styles_reach_target_with_the_same_endpoints_and_no_mutated_input(style):
    result=geometry().pattern(40,15,style=style,radius=.5,pitch=4,loops=3)
    assert result['length_mm']==pytest.approx(55,abs=1e-5)
    assert result['primitives'][0]['a']==pytest.approx([0,0])
    assert result['primitives'][-1]['b']==pytest.approx([40,0])
    assert any(p['kind']=='arcs' for p in result['primitives'])


def test_offset_pair_keeps_shared_arc_centres_and_equal_lengths():
    a=geometry().pattern(42,9.7,style='trombone',radius=1.5,pitch=6.1,loops=1,offset=-1.27)
    b=geometry().pattern(42,9.7,style='trombone',radius=1.5,pitch=6.1,loops=1,offset=1.27)
    assert a['length_mm']==pytest.approx(51.7,abs=1e-5)
    assert b['length_mm']==pytest.approx(51.7,abs=1e-5)
    assert a['primitives'][0]['a']==pytest.approx([0,-1.27])
    assert b['primitives'][0]['a']==pytest.approx([0,1.27])
    for p,q in zip([p for p in a['primitives'] if p['kind']=='arcs'],[p for p in b['primitives'] if p['kind']=='arcs']):
        c1,r1,_,_,_=geometry().arc_circle(p);c2,r2,_,_,_=geometry().arc_circle(q)
        assert c1==pytest.approx(c2,abs=1e-6)
        assert abs(r1-r2)==pytest.approx(2.54,abs=1e-6)


@pytest.mark.parametrize('patch',[{'extra':-1},{'length':1},{'style':'pretend'},{'loops':10000},{'radius':float('nan')},{'offset':2,'radius':1}])
def test_invalid_or_nonfitting_patterns_fail_before_returning_copper(patch):
    args={'length':30,'extra':10,'style':'trombone','radius':1,'pitch':6,'loops':1};args.update(patch)
    with pytest.raises(ValueError):geometry().pattern(**args)
