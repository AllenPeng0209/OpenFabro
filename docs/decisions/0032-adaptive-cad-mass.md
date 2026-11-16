# Adaptive span-aware CAD mass properties

A C1 spline extrusion exposed inconsistent default FreeCAD area/volume values: the exact planar
profile has area69 and height2, but the default estimate gave137.78276 rather than138 mm³. The
three-member assembly estimate was425.36833 instead of426. The underlying STEP boundary was
correct; splitting the same native curve into equal-geometry knot spans restored the analytic value.

Use the public OpenCascade adaptive Gauss-Kronrod volume integrator with spline spans enabled,
and adaptive surface integration, through CadQuery's OCP bindings. Run it in a cancellable host
Python worker on the exact exported STEP before publication. Bind results to the STEP hash,
library version and estimated relative errors. Match body/face properties by bounded geometry;
reject ambiguous body matching and keep unmatched face measurements explicitly estimated.

New model reports retain default estimates separately, publish adaptive total/body/member values,
and update matched native face areas in their private scene. Intermediate native feature estimates
and face-area identity signatures keep their distinct basis. Historical assets are never rewritten.
The UI identifies legacy kernel estimates. No material density or physical mass is inferred.

Regression checks cover the C1 cap area69, solid volume138, placed assembly volume276, additive
properties, STEP identity and preserved prior files. Supported Python3.10 can use OCP7.8; current
Python3.14 uses OCP8. The lightweight no-VTK package is an explicit runtime dependency.

Accepted in scope with `test-results/events-acceptance.json`. Real in-app rebuilds retain the old
three assets and publish new144/138/426mm³ results, endcaps69mm² and additive body/face properties.
Independent STEP integration agrees with the analytic targets. The original FreeCAD default
estimate still differs and is retained explicitly, rather than treated as the precise mass gate.
All27 original model files keep their SHA and nanosecond mtimes. Full software checks and installed
package smoke pass, with reused dependencies; no clean-OS installation claim.

Correct integration is separate from geometry/manufacturing validation and full Flux parity.
