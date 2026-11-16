# Editable material intent and realistic appearance

Store material assignments in editable CAD source, independently from geometry and view presets.
Catalog entries cover metals, plastics, woods, glass, composites, ceramic and stone. A preset gives
approximate appearance; grade/specification is user-declared. No density, strength, certification
or manufacturing readiness is inferred.

Whole-part and solid-feature assignments define bulk intent. A scoped material operation can
assign native bodies or finish selected faces; face finishes preserve the bulk declaration.
Native STEP colors remain independently verified. Material/style metadata follows source models
through pinned assembly manifests and native face correspondence. Ambiguous correspondence
rejects publication rather than silently switching appearance to another face.

Realistic rendering uses physical material parameters, generated studio reflections and local
procedural surface maps. X-ray and Blueprint temporarily override the view, preserving source
material choices. The source and native report retain intent; STEP/OBJ/3MF preserve verified colors
and display materials, not full optical properties or a manufacturing material assignment.

Features exposes material scope, preset, color, grade and appearance controls. Material-only edits
do not invalidate unchanged sketch solutions. Native material inspection is read-only and exposes
actual body/surface assignments rather than inferring them from screenshots.

Accepted for this scope. The in-app Codex created a plywood/brass/glass assembly, then the actual
Features UI applied carbon-fiber and colored-glass component overrides without rewriting child
models. Both save/Undo/Redo/reload cycles and the mobile editor passed. All three assembly states
preserve four solids, 40×24×14 mm geometry, volume 4161.061929829748 mm³ and six static fit pairs.
Independent native STEP face colors and saved FCStd material metadata match each state.

Receipt: `test-results/material-acceptance.json`; frozen58 contains 2825 files across six groups.
All 2735 previously accepted files retain SHA and nanosecond mtimes. Two exact AI reports and
five exact CLI copies of the actual final canvas are retained. Python 1105 (one existing socket
thread warning), Node 288 and browser 632 checks / 96 suites passed. The installed wheel matches
118 Python modules, 100 web files and 97 live static files; existing dependencies/FreeCAD were reused.

Procedural maps currently use world-space projection; arbitrary rotated-part UV attachment and
physical optical fidelity are not established. Full Flux parity, physical validation, richer
texture/UV handling, analysis and manufacturing integration remain ongoing. Software first;
watch deferred.
