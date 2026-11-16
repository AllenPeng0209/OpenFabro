import math
from test_interactive_routing_native import fixture,native,run_browser_model,prove

def routed(tmp_path):
    spec=fixture();_,geo=native(spec,tmp_path/'before');return spec,geo,run_browser_model(spec,geo,[{'kind':'point','at':[20,10]},{'kind':'pad','pin':'TP2.1'}],mode='shove')

def test_completed_shove_uses_a_local_clear_detour_instead_of_the_far_board_edge(tmp_path):
    spec,before,result=routed(tmp_path);tracks=next(g['tracks'] for g in result['spec']['fixed_copper'] if g['net']=='N')
    # A native-checked octilinear witness fits inside x<=30.8 and is under39mm.
    assert sum(math.dist(t['a'],t['b']) for t in tracks)<45,'A simple shove still takes the long outer-board detour'
    after=prove(result['spec'],tmp_path/'after');assert after['pads']==before['pads'] and result['spec']['nets']==spec['nets']

def test_route_compaction_removes_avoidable_micro_segments_without_moving_junctions(tmp_path):
    spec,before,result=routed(tmp_path);group=next(g for g in result['spec']['fixed_copper'] if g['net']=='N')
    assert min(math.dist(t['a'],t['b']) for t in group['tracks'])>=.05,'The generated route retains a tiny avoidable elbow'
    after=prove(result['spec'],tmp_path/'after')
    for item in before['tracks']:
        if item['locked']:assert next(t for t in after['tracks'] if t['id']==item['id'])==item
