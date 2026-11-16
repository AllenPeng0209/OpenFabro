# Native CAD originals and editable import recipes

Import STEP/STP, compressed STEP (gzip or a single bounded ZIP entry), IGES/IGS and
BREP as immutable project assets. Preserve exact original bytes and a separate native
inspection report, named bodies, per-face colors and world-space native bounds. Use
FreeCAD's headless Import API and exact BRep geometry. Open surfaces are distinct from
solids; convert IGES face compounds only when their sewn shell is closed and valid.

Imported assets have independent trusted manifest receipts and SHA-verified payloads.
An editable `.cad.json` references an inspected asset ID and optional body indices,
never an arbitrary server path. Pin native dependency bytes, receipt and adapter before
execution; verify them again before publication and before cache reuse. Keep originals
and all generated model revisions. CAD journal restoration reuses verified model assets.

Expose the import dialog from the project menu and the 3D toolbar. Allow multiple
files/drop, per-file outcomes, native previews, body selection, original downloads and
report copying. Create selected solids as an editable part, or extrude one imported face.
Further holes, transformations and other supported modeling operations use the CAD code
and existing parameter/build workflow. Guard asynchronous UI work by project/editor
ownership, including leaving and returning to an editor before a pending save completes.

Preserve body names/colors when topology permits an unambiguous match. Explicitly mark
unmatched native body identity as unpreserved. Export individual bodies with labels and
face colors through the native STEP exporter; reimport to check geometry, names, colors
and positions. The FCStd document contains the JSON recipe and static Part features; it
does not reconstruct a vendor's parametric feature tree or assembly mating constraints.

Official workflow reference: [Flux import and edit CAD files](https://docs.flux.ai/reference/import-and-edit-cad-files).
The public Flux example is read-only in this session; no writable Flux import trial is
claimed. Proprietary CAD, mesh and 2D imports, general surface editing, constrained
assemblies and full pixel parity remain separate requirements of the complete goal.

Phase52 scoped acceptance is test-results/cad-import-acceptance.json. Native core69,
full Python1033/one existing warning, Node274 and browser591/87suites pass. Actual
Agent import/create/drill and manual parameter/Undo/Redo/reload preserved all original
and earlier model files. Delayed idle UI and missing/per-face appearance were reproduced
and fixed. Two fully read exact reports, three real image copies and a direct STEP BRep
probe support the current three-model state. The final AI review does not approve the
implementation source or independently replay the host's UI steps.

Main99033/23645/assets97069a487ac9 uses the original profile/config, all52idle. Installed
wheel110Python/47assets matches live source and executes real native import/build with
existing dependencies/FreeCAD. Old51 project specs/versions and2190 accepted hashes/
nanosecond mtimes remain unchanged; frozen52 records2239files. Full Flux and clean-host
acceptance remain open. Watch, orders, deployment and unrelated production work remain deferred.
