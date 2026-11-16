# Stack editor tool panes without replacing their state

The current single drawer replaces its entire HTML whenever another tool opens. Flux keeps Objects
and View simultaneously mounted, vertically ordered, with independent closing, scrolling and a
resizable divider. This is a visible and functional parity gap.

Introduce an isolated dock model/controller for open membership, canonical ordering and constrained
pane fractions. Keep each pane's DOM while another is added/removed; refresh only a requested pane.
Move pane-specific CSS to each section to prevent Objects padding from leaking into layer controls.
Use one unique focused close-button compatibility ID and distinct accessible per-pane close names.
Project changes, Files/Library/Symbol transitions and Escape close all panes. Ordinary editor view changes retain panes and refresh their content; 3D camera controls close when leaving3D. Audit each existing S.panel
check: mounted membership rather than last-focused identity must guard refresh and async results.

Verify Objects+Layers coexistence/query retention, ordered geometry/29px headers/274px bodies,
independent close and scrolling, pointer/keyboard resize and cancellation, project isolation,
source/native refresh, permissions, mobile containment and unchanged saved design. Do not introduce
new engineering operations for these display actions. Existing production work and all40 frozen
projects/files must remain unchanged. Current baseline: test-results/canvas-context-frozen40.json.

The dock is instantiated once as a module-level page-lifetime controller. The static aside host is
never removed during project/view changes; only its children are replaced. No unused destroy API
is added for a remount path the application does not have. Window navigation releases the complete
page. If a future application remounts this controller, it must add explicit teardown then.

Saved pane weights are personal view preferences, normalized on load with a1e-6 relative floor.
This intentionally bounds corrupt or externally edited extreme ratios; exact arbitrary-vector import
fidelity is not a contract. Ordinary pointer/keyboard sizing retains its displayed proportions across
reload. No CAD or routing quantity uses these weights.
