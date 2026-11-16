"""A valid shape alone must not certify a STEP export's face colors."""
import json
import os
from pathlib import Path
import subprocess

import pytest
from wholeboard import enclosure, mechanical


def test_step_export_that_drops_face_colors_cannot_pass_metadata_verification(tmp_path):
    command=enclosure.find_freecad()
    if not command:pytest.skip('FreeCAD is not installed')
    asset='a'*64
    program={'schema':1,'name':'Painted part','units':'mm','parameters':{},
             'features':[{'id':'imported','op':'import','asset_id':asset}],'result':'imported'}
    job={'program':mechanical.resolve(program),'source':program,'directory':str(tmp_path),
         'imports':{asset:str(Path(__file__).parent/'fixtures/mechanical-import/face_colors.step')}}
    (tmp_path/'job.json').write_text(json.dumps(job))
    script=tmp_path/'probe.py'
    script.write_text('''import json,sys,os
from pathlib import Path
os.environ.pop('OPENFABRO_MECHANICAL_JOB',None)
sys.path.insert(0,SOURCE_DIRECTORY)
import freecad_model as model
export=model.Import.export
def missing_colors(objects,path,**kwargs):
 return export([(obj,colors[:1]) for obj,colors in objects],path,**kwargs)
model.Import.export=missing_colors
job=json.loads(Path('job.json').read_text())
try:model.main(job);answer={'accepted':True}
except ValueError as error:answer={'accepted':False,'error':str(error)}
Path('probe-result.json').write_text(json.dumps(answer))
'''.replace('SOURCE_DIRECTORY',repr(str(Path(__file__).parents[1]/'wholeboard'))))
    env={k:v for k,v in os.environ.items() if k not in ('OPENFABRO_MECHANICAL_JOB','OPENFABRO_IMPORT_JOB')}
    result=subprocess.run(command+[str(script)],cwd=tmp_path,env=env,capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stdout+result.stderr
    proof=json.loads((tmp_path/'probe-result.json').read_text())
    assert not proof['accepted'],'Native STEP verification accepted losing five blue face colors'
    assert 'STEP' in proof['error'] and 'color' in proof['error']
