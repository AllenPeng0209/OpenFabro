"""Produce a browser mesh from native KiCad STEP rather than placeholder part boxes."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
from pathlib import Path

from . import config, enclosure
from .kicad import cli, geometry


def build(p, pcb: Path, folder: Path, log=print, force=False) -> dict:
    cfg = config.load()
    command = enclosure.find_freecad(cfg)
    if not command:
        raise RuntimeError("FreeCAD is required for native STEP preview.")
    source_sha = hashlib.sha256(pcb.read_bytes()).hexdigest()
    existing = p.state.get("workbench_board3d") or {}
    if not force and existing.get("source_sha") == source_sha and (p.root / existing.get("scene_path", "")).is_file():
        return existing
    out = folder / "board3d"
    out.mkdir(parents=True, exist_ok=True)
    step = (out / "board.step").resolve()
    step.unlink(missing_ok=True)
    geo = geometry.read(pcb)
    ox, oy = geo.get("bbox", [100, 100])[:2]
    log("Exporting native KiCad STEP with component models and copper")
    result = cli.run(["pcb", "export", "step", "--force", "--subst-models", "--include-tracks", "--include-pads",
                      "--include-zones", "--user-origin", f"{ox}x{oy}mm", "-o", str(step), str(pcb.resolve())])
    if result.returncode != 0 or not step.is_file() or step.stat().st_size < 100:
        raise RuntimeError("KiCad STEP export failed: " + (result.stderr or result.stdout)[-500:])
    components = []
    for f in geo["footprints"]:
        models = f.get("models") or []
        path = str(models[0].get("path", "")) if models else ""
        components.append({"ref": f["ref"], "x": f["x"]-ox, "y": f["y"]-oy, "model_name": Path(path).stem})
    scene = (out / "scene.json").resolve()
    report = (out / "report.json").resolve()
    report.unlink(missing_ok=True)
    scene.unlink(missing_ok=True)
    job = (out / "job.json").resolve()
    job.write_text(json.dumps({"step": str(step), "output": str(scene), "report": str(report), "components": components}))
    script = Path(__file__).with_name("freecad_board_scene.py").resolve()
    env = {**os.environ, "WB_BOARD_SCENE_JOB": str(job)}
    log("Tessellating the actual STEP assembly with FreeCAD")
    with (out / "freecad.log").open("w") as stdout:
        proc = subprocess.Popen(command + [str(script)], stdout=stdout, stderr=subprocess.STDOUT, text=True, env=env, cwd=out)
        try:
            deadline = time.monotonic() + 180
            while proc.poll() is None:
                if p.cancel.wait(.15):
                    raise RuntimeError("Native 3D generation cancelled.")
                if time.monotonic() > deadline:
                    raise RuntimeError("Native 3D generation exceeded three minutes.")
            proc.wait(timeout=5)
        finally:
            if proc.poll() is None:
                proc.kill()
    if not report.is_file():
        raise RuntimeError("FreeCAD did not produce a native 3D report.")
    data = json.loads(report.read_text())
    if not data.get("ok") or not scene.is_file():
        raise RuntimeError(data.get("error") or "The native STEP assembly could not be previewed.")
    return {"version": (p.state.get("workbench") or {}).get("version", 0), "source_sha": source_sha,
            "step_sha": hashlib.sha256(step.read_bytes()).hexdigest(), "scene_sha": hashlib.sha256(scene.read_bytes()).hexdigest(),
            "scene_path": scene.relative_to(p.root.resolve()).as_posix(), "url": p.file_url(scene),
            "step_url": p.file_url(step), **data}
