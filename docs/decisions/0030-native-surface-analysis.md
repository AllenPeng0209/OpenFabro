# Native surface inspection and temporary analysis display

Flux's 3D Analysis documentation exposes Surface Continuity with Zebra Stripes and Curvature:
[Mechanical 3D view](https://docs.flux.ai/reference/3d-view), checked 2026-11-15.

Evaluate normals and principal curvatures on the placed FreeCAD BRep surface at preview vertices.
Use the topological face orientation to sign the principal values: outward convex surfaces are
negative, inner cylindrical holes positive. Keep singular, faceted and budget-limited samples
unavailable rather than zero. Store samples and per-face summaries in immutable model scenes;
retained models remain unchanged. The read-only Agent can inspect bounded, hash-pinned face pages.

Surface inspection temporarily replaces the GPU material. Zebra shows reflected bands based on
native normals, with camera-correct orthographic/perspective behavior. Curvature colors use signed
principal/mean/Gaussian values or maximum magnitude, with a numeric scale. Unknown samples are
gray. Off restores the original material and maps; clipping, visibility and picking remain usable.
Controls are personal/project view state and do not publish source or model revisions.

Finite samples and interpolated display are visual inspection aids, not a proof of G0/G1/G2
continuity, surface accuracy, stress, material properties or manufacturing suitability. Legacy
and software-fallback views cannot synthesize native smooth derivatives from faceted triangles.

Accepted in scope. In-app Codex created an R4/R2 ring, an exact R8/r2 revolved torus and a linked
three-member assembly including a rotated ring. All nine faces have native derivatives. Independent
STEP reconstruction and analytic cylinder/hole/torus formulas match all17892 records. The actual
Analysis UI passed Zebra density/angle/projection, five curvature metrics and unit scales, clipping,
reload and mobile. Off restores the exact original pure-canvas pixels, with DOM overlays excluded.

Receipt `test-results/surface-acceptance.json`, frozen60=2933files. All2879 prior accepted SHA and
nanosecond mtimes remain exact. Python1112 (one existing socket-thread warning), Node292 and
browser644 /100suites passed. Installed wheel matches118Python/102webfiles/99live statics, reusing
existing dependencies and FreeCAD. Two exact AI reports, three exact CLI copies of the real Zebra
canvas and four desktop/mobile report renders are retained.

Mesh provenance is preserved through edits and assemblies; faceted inputs cannot become false
smooth derivative evidence. The torus native bounding box includes about1e-7mm kernel padding;
independent analytic bounds use1e-6mm, separately from point/derivative tolerances. Formal continuity
and remaining Flux functionality stay open. Self-hosted software first; watch deferred.
