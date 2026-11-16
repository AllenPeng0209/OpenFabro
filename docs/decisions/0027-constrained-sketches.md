# Native constrained sketches and linked extrusion

Add a bounded declarative sketch operation with named line/circle/arc/ellipse/B-spline geometry,
construction flags and native geometric/dimensional constraints. Source coordinates are initial
guesses. The FreeCAD Sketcher solver determines the actual geometry and reports DoF, conflicts,
redundancy and reference dimensions. Reject inconsistent sketches; optionally require zero DoF.
Report conflicting constraints by source ID, preserving every earlier source/model on failure.

Store actual Sketcher objects in FCStd. Named driving dimensions use a native design-parameter
object; sketch-based extrude_shape creates a linked Part::Extrusion with parameter expressions.
Native parameter edits propagate through the exported document. Arbitrary blocked seed curves
still need source rebuilding; this does not promise every source feature is externally associative.

The Features dialog exposes the ordered feature list, solved sketch preview, geometry forms,
constraints and linked parameters. Solve preview uses a private temporary document and publishes
no source, model or CAD history. Explicit saving rebuilds the solid atomically. Per-sketch draft
versions prevent accepting an old preview after another edit. Historical sources are read through
sealed artifact URLs with SHA verification; protected text paths stay protected. Async ownership
checks prevent abandoned source reads from blocking or replacing a new editor.

New part can create a constrained sketch. Generic primitive fields are also editable; spline
poles/knots remain accessible in CAD code. This is native constraint and feature editing, not
complete interactive sketch authoring or a general solid feature constraint solver.

Scoped acceptance: `test-results/sketch-acceptance.json`. 1096 Python, 286 Node and627 browser
checks /94suites pass, one pre-existing socket-thread warning. Actual in-app Agent creation,
GUI dimension/primitive edits with private solve, conflict rejection, two Undo/Redo cycles,
reload/mobile and real-image review are verified. Three independent STEP/FCStd checks cover
hole/material geometry and native parameter propagation. Original56/2687 SHA+ns-mtimes retained;
frozen57 totals2735files. Wheel/source/live117Python/98webfiles/95statics match; installed native
sketch smoke reuses existing dependencies. General interactive authoring remains incomplete.

Full Flux parity, broader feature history, closed-loop mechanisms,
physical validation and clean-OS setup remain separate work. Self-hosted software first; watch deferred.
