# Contextual 3D View reference

Observed read-only in the public On Air R2 demo on2026-11-14 at1440×1000. Screenshot:
`test-results/flux-cad-view-current.png`, directly inspected. This later capture contains a partial
loaded PCB model and grid; the earlier flux-3d-view-reference.png had a blank scene.

The existing View dock hosts Camera, Layers, Analysis and Display accordions. Camera has28px rows
with117×22px selectors. Defaults are realistic material and perspective projection. Actual selector
options observed: blueprint/xray/solid/realistic and perspective/orthographic. Layers has45px top and
bottom3D model rows. Display has28px Grid, Collaborative cursors and Keyboard shortcut bar toggles.
Sections are32px headings in a274px panel. Color/type follow the existing dark Roboto workspace.

Curvature comb, Section and Surface continuity are present. The public guest state did not establish
their writable behavior. This software phase connects real mesh clipping, camera/material/grid and
side visibility; curvature/surface and native3D cursor rendering remain open parity work.

The implementation retains existing measurement and enclosure controls. Unknown STEP bodies stay
visible when hiding either side; classification uses exact saved references, never a guessed height.
Browser view settings must not save a circuit version or rewrite native CAD exports.
