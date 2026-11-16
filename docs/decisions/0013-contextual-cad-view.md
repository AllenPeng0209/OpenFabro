# Contextual 3D View

Reuse the same View dock for Schematic, PCB and3D. Alias the legacy camera entry to that pane.
Follow the observed274px panel,32px section headers,28px camera/display rows and45px model rows.
Use the actual Flux material/projection choices and realistic/perspective defaults. Keep assembly
controls and model-coordinate measurement alongside the existing FreeCAD workflow.

Persist normalized browser preferences per account/project. Bound in-memory preferences, notices
and camera poses. Capture pose ownership with the viewer, not whichever account is currently active.
Detached controls require the same mount sequence and owner. Native replacements preserve pose,
clear geometry-qualified measurement feedback and update controls even when their pane is closed.

Classify component bodies by exact saved reference or the supported concept-pad suffix. Hide only
matched top/bottom models. Keep unassigned STEP bodies visible with an explanation. Board mode hides
enclosure geometry; switching back restores personal assembly visibility. Both renderers honor these
filters. GPU grid, materials, projection, clipping and measurement have actual scene effects; the
software fallback explicitly disables unsupported controls.

Derive GPU pan from the active projection at its target plane. Software pan is in screen-plane model
units. Tag cached pan with its renderer; switching renderer resets pan instead of treating these
coordinate systems as interchangeable. Wheel and pose restoration update the visible zoom value.
Guard pointer release as well as down/move/wheel when interaction permission changes.

Measurement uses assembled CAD coordinates. Enabling it closes explosion; the slider stays locked
until measurement ends. Replacement and relevant visibility/clipping changes discard old feedback.
Clipping planes have no generated cap geometry. Neither distance nor model bounds are physical tests.

Markup already captures a separate bitmap plus ink. Same-sized background viewer replacement can
remain behind that unchanged bitmap; it does not itself prove changed annotation pixels. The3D
main UI verifies exact frozen bitmap equality across wheel input and contextual controls disabled
during Markup. No new image was submitted to AI in this phase; source review and host UI evidence
remain distinct.

Curvature/surface analysis, native3D collaborative cursors, navigation-cube and complete writable Flux
pixels remain further work. This decision does not establish full Flux or manufacturing acceptance.

Scoped acceptance:182 Node and494 browser checks/69 suites, including243D checks. Current wheel
matches38assets/HTML and all101unchangedPython members. Main actual STEP rendering and desktop/mobile
interaction evidence are in cad-view-acceptance.json. Own typedv1 and all older42 projects preserve
their frozen source and files; personal QA preferences restored. The two exact source reviews are
historical pinned snapshots; their final findings received host RED/GREEN fixes and the final full
wave afterward. They are not assertions that AI inspected those later lines.
