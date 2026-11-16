"""Create only the isolated projects owned by the browser acceptance runner."""
import argparse
import json
from pathlib import Path

from wholeboard import config
from wholeboard.project import Manager
from wholeboard.workbench import _write_spec

parser = argparse.ArgumentParser()
parser.add_argument("--directory", type=Path, required=True)
parser.add_argument("--fixture", type=Path, required=True)
args = parser.parse_args()
config.update({"projects_dir": str(args.directory / "projects")})
# Reuse only the locally built native executable. The isolated profile must not
# inherit the main server's accounts, credentials, projects or other settings.
native_root = Path(__file__).parents[1] / ".local/wholeboard/tools/tracemaker"
native = sorted(p for p in native_root.glob("src/build/*/src/app/tracemaker") if p.is_file())
if native:
    config.update({"tools": {"tracemaker": str(native[0].resolve())}})
manager = Manager()
p = manager.create("Recorded supplier data — UI test fixture")
spec = json.loads((Path(__file__).parents[1] / "wholeboard/web/workbench-example.json").read_text())
quote = json.loads(args.fixture.read_text())["quote"]
quote.update(source_version=1, quoted_at=1794379239, build_revision=0)
p.state.update(spec=spec, quote=quote, workbench={"version": 1, "checks_stale": True},
               custom_title="Recorded supplier data — UI test fixture", owner_id="device")
_write_spec(p)
docs = p.root / "docs"
docs.mkdir()
(docs / "sandbox.svg").write_text("<svg xmlns='http://www.w3.org/2000/svg' onload='window.executed=true'><rect width='10' height='10'/></svg>")
(docs / "sandbox.html").write_text("<!doctype html><button id='counter' onclick='this.textContent=Number(this.textContent)+1'>0</button><script>window.interactive=true</script>")
p.save()
print(p.id)
