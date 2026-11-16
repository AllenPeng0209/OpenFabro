import json,subprocess
from pathlib import Path
import pytest
from wholeboard import sexpr
from wholeboard.kicad import board,cli,geometry
from test_interactive_routing_native import fixture

@pytest.mark.parametrize('footprint',[False,True])
def test_native_copper_textbox_survives_parser_and_blocks_unsupported_autorouting(tmp_path,footprint):
    spec=fixture();pcb=Path(board.build(spec,tmp_path)['pcb']);tree=sexpr.parse(pcb.read_text());identifier='eeeeeeee-eeee-4eee-8eee-000000000001';kind='fp_text_box' if footprint else 'gr_text_box';coords='(start 14 -1) (end 16 1)' if footprint else '(start 119 109) (end 121 111)';node=sexpr.parse(f'({kind} "Cu" {coords} (layer "F.Cu") (uuid "{identifier}") (effects (font (size 1 1) (thickness 0.15)) (justify left top)) (stroke (width 0.15) (type default)))')
    (next(sexpr.find_all(tree,'footprint')) if footprint else tree).append(node);pcb.write_text(sexpr.dumps(tree));plotted=cli.run(['pcb','export','svg','--layers','F.Cu','-o',str(tmp_path/'svg'),str(pcb)],cwd=tmp_path);assert plotted.returncode==0,plotted.stderr
    g=geometry.read(pcb);drawing=next((d for d in g['drawings'] if d['id']==identifier),None);assert drawing is not None,'The native physical text box was silently dropped'
    script="import {planInteractiveRoute} from './wholeboard/web/workbench-route-obstacles.mjs';let raw='';for await(const c of process.stdin)raw+=c;const {spec,g}=JSON.parse(raw);try{planInteractiveRoute(spec,g,{net:'SIG',layer:'F.Cu',width:.25,from:[5,10],to:[30,10],mode:'walkaround'});process.stdout.write('accepted');}catch(e){process.stdout.write(e.message);}";result=subprocess.run(['node','--input-type=module','-e',script],cwd=Path(__file__).parents[1],input=json.dumps({'spec':spec,'g':g}),capture_output=True,text=True,timeout=15);assert result.returncode==0,result.stderr;assert 'Unsupported' in result.stdout and 'graphic' in result.stdout
