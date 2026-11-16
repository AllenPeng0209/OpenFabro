# Native curve inflections and curvature jumps

Flux's published Curvature Combs controls include Inflections and Curvature Jumps:
[Mechanical 3D View](https://docs.flux.ai/reference/3d-view), checked 2026-11-15.

Read native curve definitions, independently of the65 display samples. Split bounded B-splines
into homogeneous Bézier spans. Numerically isolate planar signed-curvature numerator roots,
verify a sign change with nonzero speed, and retain the parameter bracket/residual. Spatial
inflections are unknown rather than guessed from projection. Positive rational weights are
supported; unsupported degree/span/evaluation budgets are explicit.

Compare exact one-sided derivative formulas at knots and endpoint limits at native wire joins.
Record curvature jumps only when tangents agree. Tangent breaks and stationary singularities
are separate event kinds. Store placed scene-local points in sealed model scenes, and expose
bounded hash-pinned Agent inspection. Existing scenes stay immutable.

Curvature Combs has independent view filters and colored native event markers. They follow
source-body visibility, isolation, sections and the master comb switch; display density/gain do
not redefine event positions. No geometry or source revision is published by these controls.

Accepted in scope. Native tests cover ordinary and rational planar roots, trimmed/excluded roots,
planar spans of spatial definitions, singularities, C1 knots, tangent line/arc wire joins and placed
read-only inspection. Actual GUI filters/gain/density/sections/reload/mobile passed; independent
STEP derivatives and analytic positions match the six roots and two jumps in the three-member QA
assembly. The in-app Agent identified a mass-integration inconsistency, then rebuilt corrected
revisions and reviewed the actual marked canvas. All older models and reports remain unchanged.

Receipt `test-results/events-acceptance.json`; frozen61 contains3025files across six groups.
Python1119 (one existing socket-thread warning), Node294 and browser649 /102suites passed.
Three exact AI reports, three exact final-image CLI copies and six desktop/mobile report renders
are retained. Installed wheel matches120Python/102webfiles/99live statics, reusing dependencies.

Numerical analysis does not prove global continuity, material properties or manufacturing suitability.
Unsupported spatial/degree/span/budget cases remain explicit. Full Flux stays active; watch deferred.
