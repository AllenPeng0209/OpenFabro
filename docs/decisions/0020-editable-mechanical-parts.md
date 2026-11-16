# Editable mechanical parts and immutable native assets

Flux's current official editable-CAD and new-parts documentation explicitly covers parameterized
solid operations, rebuilding from editable source, retaining the original model, and STEP export.
This is a direct full-Flux gap: the existing workbench only produces a board/enclosure and cannot
author a general bracket or mount. The unobserved multi-track push/shove selector is not used as
a substitute for that documented capability. Complete Flux remains the goal, software first and
self-hosted; the watch stays deferred.

Use editable JSON CAD programs with named scalar parameters and bounded arithmetic expressions.
Run only a trusted FreeCAD adapter, with exact extrude/revolve/sweep/loft/shell/fillet/chamfer/hole/
linear-pattern/circular-pattern and Boolean/transform operations. Do not silently approximate a
failed feature. Preserve the source, feature report, exact STEP/STL/FCStd and derived browser mesh.
Rebuilds publish a new source-hash-bound asset and keep all previous files. Native valid-solid,
volume/bounds and operation findings are engineering evidence, not physical-fit acceptance.

Expose the same workflow to in-app Agent and manual Files/3D controls: editable source, parameter
changes, guarded rebuild, previous versions and exports. Build publication must reject changed
source, canceled jobs and invalid or partial outputs. Mechanical-only work must not generate or
modify electrical native files, specification fields or design versions.

Phase50 scoped acceptance is test-results/mechanical-acceptance.json. Current main69061/71863,
assetsda9442091631, has all50runtimes idle, own electrical savedv1 unchanged and no electronic native
generation. Actual Agent/manual modeling retained4/6/8/8mm model assets with independent STEP
feature measurements. All original49projects and2075files preserve bytes/nsmtimes. Frozen50 includes
the active CAD source and all generated mechanical assets, totaling2139files with accepted nsmtimes.

1007Python/oneexisting warning,266Node,572browser/85suites pass. Five reports were fully read and
exact-proposal matched; a missing20k source interval in the broad review was explicitly recovered
with a smaller complete bundle. The final async build ownership and post-commit AI Undo notification
fixes were host-tested after the last AI supplement, not separately approved by it. Current wheel
matches46assets/HTML/107Python using existing runtime dependencies.

This is editable JSON plus native rebuild, not a native expression-linked FCStd feature graph.
Manual global CAD Ctrl-Z/model-pointer restoration, arbitrary imports, assemblies/constraints,
splines and physical fit remain open. Complete Flux remains the goal, softwarefirst/selfhosted,
watchdeferred. Unrelated production/branding/driving_into_world work remains unchanged.
