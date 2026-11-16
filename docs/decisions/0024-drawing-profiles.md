# Native drawing profiles and editable extrusion

Import mechanical DXF/SVG separately from the existing PCB board-outline parser. Keep
immutable source/canonical/report/scene files. Respect DXF document units/layers/block
instances, SVG physical lengths/viewBox/transforms/fill rules, and explicit outline mode.
Sample curves only for nesting; preserve native lines/conics/Bezier/NURBS for faces,
cutouts and thickness extrusion. Reference curves and unoutlined annotations are not material.
Report ignored entities and block unsafe XML/external references, cycles and unbounded paths.

Expose source options, eligible profile selection, native reference-line preview and Thickness
in the asset dialog. extrude_drawing_asset creates import/extrude_shape plus an editable
thickness parameter. Successful source/model changes enter existing CAD history independently
of electrical version. Retain all prior geometry and reconstruct history without remeshing.

Add OBJ RGB-vertex and3MF core display-material exports as optional sealed model files;
older six-file manifests stay readable. STEP remains exact native exchange, mesh outputs have
tessellation error,3MF display colors do not assign printer materials. All geometry/name/
face-color STEP checks remain enforced. Isolate export faces to avoid translated partner-cap
style misassignment in FreeCAD; retain original main-document topology.

Scoped acceptance: test-results/drawing-import-acceptance.json. 1066Python/one existing warning,
278Node,605browser/90suites and102native-core checks pass. Actual GUI Agent extrusion, manual
3→4→5mm/Undo/Redo/reload, independent native holes/corners and six mesh-file decodes passed.
Two fullread/exact AI reports and three exact actual-image copies document evidence review,
not source approval or independent host-action replay. Old53 saved specs/versions and2316
accepted SHA/nsmtimes preserved; frozen54 totals2384files. Main80245/41463/assetsdb08a9a512dc,
all54idle, original profile/config. Installed wheel112Python/48assets matches live source and
does actual STEP/GLB/DXF native builds with existing dependencies/FreeCAD; no clean-host claim.

Full Flux remains active. Proprietary import, general SVG clipping/raster/text/repair, richer
feature/sketch/assembly constraints, full pixels/collaboration/durability and clean-host setup
remain open. Watch work remains deferred.
