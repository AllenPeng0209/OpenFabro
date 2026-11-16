# Native edge curvature combs

Flux's published 3D Analysis controls include curvature comb length and line density:
https://docs.flux.ai/reference/3d-view (checked 2026-11-15).

Evaluate curvature and tangent/normal vectors on placed FreeCAD BRep edges. Store bounded uniform
native-parameter samples in the sealed scene, with singular samples as explicit gaps. This keeps
curvature independent of viewport tessellation. Translation/rotation use the actual placed edge;
sample points use scene-local millimeters, with the scene origin supplied separately. Curvature
is in inverse millimeters. Mesh-derived facets cannot establish smooth source curvature.

The web renderer scales native normals by curvature and an adjustable display gain. Density
subsamples the stored derivatives. Combs follow visible bodies, isolation and cross-section
clipping. Controls are personal/project-scoped view state and never publish a model revision.
Retained legacy models remain unchanged and truthfully report missing samples.

The read-only Agent inspector paginates one hash-pinned edge's derivatives. General topology
inspection includes curvature summaries without derivative arrays. No inflection/jump absence,
surface continuity, zebra/surface curvature or stress result is inferred from finite edge sampling.

Accepted in scope. In-app Codex created a circular part, an ellipse extrusion and a three-member
assembly with one rotated instance, then inspected all nine edges / 396 derivative samples. The
actual Analysis UI passed gain/density changes, section clipping, reload and compact layout checks
without changing source, models or history. Independent STEP reconstruction and analytic circle /
ellipse formulas match every sample's position, tangent, normal and curvature.

Receipt `test-results/comb-acceptance.json`; frozen59 contains 2879 files across six groups.
Original58 specs/versions and2825 SHA/ns-mtimes remain exact. Python1108 (one existing socket-thread
warning), Node290 and browser637 /98suites passed. Installed wheel matches118Python/101webfiles/
98live static, reusing existing dependencies and FreeCAD. Two exact AI reports, three exact copies
of the final real canvas and four desktop/mobile report renders are retained.

Finite edge samples, GPU-only comb rendering and absent legacy samples are explicit limits.
Surface continuity, Zebra, surface curvature and exact inflection/jump analysis remain open.
Full Flux remains active, self-hosted software first; watch deferred.
