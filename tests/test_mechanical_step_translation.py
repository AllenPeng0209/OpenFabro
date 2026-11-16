import json
import os
from pathlib import Path
import subprocess

import pytest
from wholeboard import enclosure
from test_mechanical_parts import engine, program


def test_exported_step_translation_cannot_pass_roundtrip_verification(tmp_path):
    command = enclosure.find_freecad()
    if not command:
        pytest.skip('FreeCAD is not installed')
    job = {'directory': str(tmp_path), 'source': program(), 'program': engine().resolve(program())}
    (tmp_path/'job.json').write_text(json.dumps(job))
    script = tmp_path/'probe.py'
    script.write_text('''import json,sys,os
from pathlib import Path
import FreeCAD as App
os.environ.pop('OPENFABRO_MECHANICAL_JOB',None)
sys.path.insert(0,sys.argv[-1])
import freecad_model as model
directory=Path.cwd();job=json.loads((directory/'job.json').read_text());read=model.Part.read
def moved(path):
 shape=read(path);shape.translate(App.Vector(1,0,0));return shape
model.Part.read=moved
try:
 model.main(job);answer={'accepted':True}
except ValueError as error:answer={'accepted':False,'error':str(error)}
(directory/'probe-result.json').write_text(json.dumps(answer))
'''.replace('sys.path.insert(0,sys.argv[-1])', 'sys.path.insert(0,'+repr(str(Path(__file__).parents[1]/'wholeboard'))+')'))
    env = {key:value for key,value in os.environ.items() if key != 'OPENFABRO_MECHANICAL_JOB'}
    result = subprocess.run(command+[str(script)], cwd=tmp_path, env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout+result.stderr
    proof = json.loads((tmp_path/'probe-result.json').read_text())
    assert not proof['accepted'], 'A translated STEP passed because only extents and volume were checked'
    assert 'STEP' in proof['error'] or 'geometry' in proof['error']
