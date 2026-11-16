#3D navigation cube

Use the observed dark156–160px circular navigator at the upper-right of the3D canvas. Its projected
cube rotates with the actual camera. Faces, edges and corners select their world directions; outer
controls orbit, roll, restore the home view and turn horizontally by180degrees. This half-turn
retains the vertical hemisphere, matching the observed public control rather than changing top to
bottom. Six standard faces and twenty-six
nonzero axis-combination targets share one camera basis for GPU and software rendering. Home uses
the observed top/left/back isometric direction. Fitting changes framing while retaining orientation.

Use Roboto with matte#292929/#303030 rings,#777777 faces,#191919 labels and#008b73 hover. Keep the
existing editor typography and controls. The widget is a camera control, so it never edits source,
generates CAD or saves a design version. Camera settings stay with their existing account/project.

The camera button below the ring opens the observed radial material/projection controls. Those
controls update the same settings as View. Desktop cube remains visible; narrow layouts expose
Show/Hide view cube. Do not obscure the widget with the separate native-build action. Keep all
camera controls paused during Markup and reject detached controls after viewer/owner replacement.

Verify exact pole directions without camera singularities, roll, both renderers, fit, model loads,
ownership, keyboard/focus, viewport hit targets and unchanged saved/native files. Inspect real UI
screenshots against the public reference. This is one part of full Flux parity, not completion.

Trusted Space input needs release ownership independent of the current focus target. Capture the
press only for a valid, non-repeated navigation keydown; mark its release event before clearing it.
A WeakMap retains that event's mount/owner identity while the main keyup handler decides whether to
clear temporary canvas pan. Cleanup removes capture listeners on detach. This also avoids stale
press state and microtask timing between trusted-event listeners. Real browser cases cover release
inside/outside navigation, repeated keydown, the next press and an intentionally armed Pan tool.

Scoped acceptance:190 Node and517 browser checks/76 suites,41installed frontend assets/HTML matched,
all101Python members unchanged from the previous accepted archive. Main real STEP rendering and
desktop/mobile/Markup/focus evidence are in navigation-acceptance.json. Both actual AI reports were
fully read and matched to exact proposals. AI also received and described a host full-IDE image,
not a Markup crop or blind image test. The last Space release fix was tested after the followup;
do not claim the model inspected those later lines. The separate host acceptance document records
that resolution without rewriting historical reviews. Full Flux and physical-device acceptance remain open.
