from wholeboard.kicad import connectivity
import pytest


def test_native_islands_identify_connected_pads_and_isolated_copper_separately():
    geo={'layers':['F.Cu','B.Cu'],'pads':[{'id':'p1','ref':'J1','name':'1','net':'N','x':0,'y':0,'w':1,'h':1,'shape':'circle','kind':'thru_hole','layers':['*.Cu']},{'id':'p2','ref':'J2','name':'1','net':'N','x':5,'y':0,'w':1,'h':1,'shape':'circle','kind':'thru_hole','layers':['*.Cu']},{'id':'p3','ref':'J3','name':'1','net':'N','x':10,'y':0,'w':1,'h':1,'shape':'circle','kind':'thru_hole','layers':['*.Cu']}],'tracks':[{'id':'joined','net':'N','a':[0,0],'b':[5,0],'w':.25,'layer':'F.Cu'},{'id':'floating','net':'N','a':[15,3],'b':[16,3],'w':.25,'layer':'F.Cu'}]}
    result=connectivity.electrical_islands(geo)
    assert {'pads':['p1','p2'],'copper':['joined']} in result['N']
    assert {'pads':['p3'],'copper':[]} in result['N']
    assert {'pads':[],'copper':['floating']} in result['N']
    assert len(connectivity.airwires(geo))==2


def test_small_arc_contacts_are_analytic_without_joining_nearby_disconnected_pads():
    import math
    for radius in [1,1000]:
        for offset,joined in [(.0099,True),(.0104,False)]:
            angle=math.radians(2.5);point=[(radius+offset)*math.cos(angle),(radius+offset)*math.sin(angle)]
            geo={'layers':['F.Cu'],'pads':[{'id':'start','net':'N','x':radius,'y':0,'w':.01,'h':.01,'shape':'circle','kind':'smd','layers':['F.Cu']},{'id':'tip','net':'N','x':point[0],'y':point[1],'w':.01,'h':.01,'shape':'circle','kind':'smd','layers':['F.Cu']}],'arcs':[{'id':'curve','net':'N','a':[radius,0],'m':[0,radius],'b':[-radius,0],'w':.01,'layer':'F.Cu'}]}
            islands=connectivity.electrical_islands(geo)['N'];actual=any(set(g['pads'])=={'start','tip'} for g in islands)
            assert actual is joined,(radius,offset,islands)


@pytest.mark.parametrize('shape',['trapezoid','custom'])
def test_routing_membership_rejects_unsupported_pad_copper_instead_of_a_false_rectangle(shape):
    geo={'layers':['F.Cu'],'pads':[{'id':'unsupported','ref':'J1','name':'1','net':'N','x':0,'y':0,'w':2,'h':2,'shape':shape,'kind':'smd','layers':['F.Cu']}],'tracks':[{'id':'outside','net':'N','a':[.8,.8],'b':[.85,.8],'w':.01,'layer':'F.Cu'}]}
    with pytest.raises(ValueError,match='Unsupported.*pad|unknown'):connectivity.electrical_islands(geo)
    assert isinstance(connectivity.airwires(geo),list),'An unknown routing topology must not prevent displaying the imported PCB'
