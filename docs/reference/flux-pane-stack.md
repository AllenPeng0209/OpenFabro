# Flux tool-pane stacking reference

Observed in the isolated public On Air R2 demo PCB view at1440×1000, without account changes.
Evidence: test-results/flux-pane-stack-reference.json and flux-pane-resize-reference.json;
test-results/flux-next-layout-reference.png was directly inspected.

Objects and View can remain open together. The dock occupies x732,y73,width276,height927; each
pane's inner width is274. Objects precedes View regardless of which was opened last. Two default
panes each occupy462px with a1px horizontal divider; one pane expands to925px inside the border.
Headers are29px, background rgb(66,66,66); pane bodies rgb(46,46,46). Bodies scroll independently.
Tool icons toggle only their own pane. A header close button also closes only that pane.

The separator is keyboard-focusable, role separator, aria-orientation horizontal, default
aria-valuenow50, cursor row-resize. A pointer drag100px moves the separator fromy536 toy635.5;
dragging back restoresy536. No design or external account was changed. Exact keyboard increment,
small-screen Flux behavior, panel order outside this observed pair and long-term persistence have
not yet been established from this reference.

A subsequent actual keyboard test moved the separator fromy536 toy552 with ArrowDown, then back
with ArrowUp. Its rounded aria-valuenow changed50→52→50, establishing a16px movement at this size.

Implementation should preserve mounted pane bodies and in-flight action guards while another pane
opens/closes. Opening View must not erase an Objects query/selection; refreshing native geometry
must update both. Pane layout is personal UI state, separate from CAD, routing and saved versions.
