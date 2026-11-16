import copy

from wholeboard import selective_routing


def scene():
    return {'layers':['F.Cu'],'pads':[{'id':p,'net':n,'x':x,'y':y,'w':1,'h':1,'shape':'circle','kind':'smd','layers':['F.Cu']} for p,n,x,y in [('r1','R',0,0),('r2','R',5,0),('k1','K',10,0),('k2','K',15,0)]],'tracks':[{'id':'r-join','net':'R','a':[0,0],'b':[5,0],'w':.25,'layer':'F.Cu','locked':True},{'id':'k-join','net':'K','a':[10,0],'b':[15,0],'w':.25,'layer':'F.Cu','locked':True},{'id':'branch','net':'R','a':[0,0],'b':[0,2],'w':.25,'layer':'F.Cu','locked':False}],'arcs':[],'vias':[],'zones':[]}


def test_modified_existing_id_cannot_change_to_another_net():
    before=scene();after=copy.deepcopy(before);after['tracks'][-1].update(net='K',a=[10,0],b=[10,2]);result=selective_routing.validate_copper_candidate(before,after,['S'],['R'])
    assert any(v['type']=='net reassignment' for v in result['findings'])


def test_modified_previously_attached_copper_cannot_become_isolated():
    before=scene();after=copy.deepcopy(before);after['tracks'][-1].update(a=[0,5],b=[0,7]);result=selective_routing.validate_copper_candidate(before,after,['S'],['R'])
    assert any(v['type']=='floating copper' for v in result['findings'])


def test_unchanged_copper_cannot_be_stranded_by_removing_its_connector():
    before=scene();before['tracks'][-1]['b']=[0,2];before['tracks'].append({'id':'tail','net':'R','a':[0,2],'b':[2,2],'w':.25,'layer':'F.Cu','locked':True});after=copy.deepcopy(before);after['tracks']=[t for t in after['tracks'] if t['id']!='branch'];result=selective_routing.validate_copper_candidate(before,after,['S'],['R'])
    assert any(v['type']=='floating copper' and 'tail' in v.get('ids',[]) for v in result['findings'])
