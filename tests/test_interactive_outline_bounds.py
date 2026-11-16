from pathlib import Path
import pytest
from wholeboard import sexpr
from wholeboard.kicad import board,geometry
from test_selective_routing import fixture

@pytest.mark.parametrize('kind',['circle','arc','polygon'])
def test_native_board_origin_uses_complete_physical_boundary_extrema(tmp_path,kind):
    spec=fixture('selective-routing-repair');spec['board'].update(width_mm=20,height_mm=20);spec['components']=spec['components'][:1];spec['components'][0]['placement']={'x_mm':10,'y_mm':10};spec['nets']=[{'name':'SIG','pins':['TP1.1']}];spec['fixed_copper']=[];spec['fixed_zones']=[];pcb=Path(board.build(spec,tmp_path)['pcb']);tree=sexpr.parse(pcb.read_text());tree[:]=[item for item in tree if not isinstance(item,list) or str((sexpr.find(item,'layer') or ['',''])[1])!='Edge.Cuts']
    raw={'circle':'(gr_circle (center 110 110) (end 120 110) (stroke (width 0.05) (type default)) (fill none) (layer "Edge.Cuts"))','arc':'(gr_arc (start 120 110) (mid 100 110) (end 110 120) (stroke (width 0.05) (type default)) (layer "Edge.Cuts"))','polygon':'(gr_poly (pts (xy 100 100) (xy 120 100) (xy 120 120) (xy 100 120)) (stroke (width 0.05) (type default)) (fill none) (layer "Edge.Cuts"))'}[kind];tree.append(sexpr.parse(raw))
    if kind=='arc':tree.append(sexpr.parse('(gr_line (start 110 120) (end 120 110) (stroke (width 0.05) (type default)) (layer "Edge.Cuts"))'))
    pcb.write_text(sexpr.dumps(tree));g=geometry.read(pcb);assert g.get('bbox')==[100,100,120,120],g.get('bbox');assert g['pads'][0]['x']-g['bbox'][0]==10 and g['pads'][0]['y']-g['bbox'][1]==10
