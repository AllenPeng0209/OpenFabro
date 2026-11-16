"""Run inside FreeCADCmd to tessellate a native KiCad STEP assembly.

Input/output paths are supplied by the trusted server via WB_BOARD_SCENE_JOB.
No model-generated Python is executed.
"""
import json
import math
import os
import traceback

import FreeCAD as App
import Import


def main(job):
    doc = App.newDocument("OpenFabroNative3D")
    try:
        Import.insert(job["step"], doc.Name)
        assemblies = [o for o in doc.Objects if o.TypeId == "App::Part" and hasattr(o, "Shape") and not o.Shape.isNull()]
        root = max(assemblies, key=lambda o: len(o.Shape.Solids)) if assemblies else None
        objects = list(root.Group) if root else list(doc.Objects)
        meshes = []
        unused = list(job.get("components", []))
        for obj in objects:
            if obj.TypeId not in ("App::Part", "Part::Feature", "PartDesign::Feature"):
                continue
            shape = getattr(obj, "Shape", None)
            if shape is None or shape.isNull() or not shape.Faces:
                continue
            bb = shape.BoundBox
            if not all(math.isfinite(n) and abs(n) < 100000 for n in (bb.XMin, bb.YMin, bb.ZMin, bb.XMax, bb.YMax, bb.ZMax)):
                continue
            label = obj.Label
            copper = any(word in label.lower() for word in ("_pad", "_track", "_via", "_zone"))
            substrate = "_pcb" in label.lower()
            color = "#b8a17a" if copper else "#1d6246" if substrate else "#494b47"
            group = "board" if copper or substrate else "parts"
            name = label
            if group == "parts" and unused:
                candidates = [c for c in unused if c.get("model_name") and label.startswith(c["model_name"])] or unused
                cx, cy = (bb.XMin + bb.XMax) / 2, -(bb.YMin + bb.YMax) / 2
                component = min(candidates, key=lambda c: (cx-c["x"])**2 + (cy-c["y"])**2)
                if math.hypot(cx-component["x"], cy-component["y"]) < 8:
                    name = component["ref"]
                    unused.remove(component)
                    if name.startswith("J"):
                        color = "#aeb6ba"
                    elif name.startswith("C"):
                        color = "#b49563"
                    elif name.startswith("D"):
                        color = "#cc5350"
                    else:
                        color = "#313633"
            vertices, triangles = shape.tessellate(0.09)
            if not triangles:
                continue
            # KiCad STEP Y points up; the editor uses the PCB's top-left Y-down coordinates.
            values = [round(n, 5) for p in vertices for n in (p.x, -p.y, p.z)]
            indices = [n for a, b, c in triangles for n in (a, c, b)]
            meshes.append({"name": name, "group": group, "color": color, "v": values, "t": indices})
        if not meshes:
            raise ValueError("The exported STEP assembly contains no displayable faces.")
        mins = [min(min(m["v"][i::3]) for m in meshes) for i in range(3)]
        maxs = [max(max(m["v"][i::3]) for m in meshes) for i in range(3)]
        for mesh in meshes:
            mesh["v"] = [round(n - mins[i % 3], 5) for i, n in enumerate(mesh["v"])]
        scene = {"size": [round(maxs[i]-mins[i], 5) for i in range(3)], "origin": mins,
                 "meshes": meshes, "source": "native-kicad-step", "unmatched_components": [c["ref"] for c in unused]}
        with open(job["output"], "w", encoding="utf-8") as output:
            json.dump(scene, output, separators=(",", ":"))
        return {"ok": True, "meshes": len(meshes), "triangles": sum(len(m["t"])//3 for m in meshes),
                "size": scene["size"], "unmatched_components": scene["unmatched_components"]}
    finally:
        App.closeDocument(doc.Name)


with open(os.environ["WB_BOARD_SCENE_JOB"], encoding="utf-8") as handle:
    job = json.load(handle)
try:
    result = main(job)
except Exception as error:
    result = {"ok": False, "error": str(error), "trace": traceback.format_exc()}
with open(job["report"], "w", encoding="utf-8") as output:
    json.dump(result, output)
