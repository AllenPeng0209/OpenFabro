# Personal Schematic display controls

Replace the Schematic View's Open Layout placeholder with four working display controls, using the
observed28px rows, checkmarks and keyboard shortcuts. Preserve PCB controls and existing CAD exports.

Use bounded, account/project-local boolean preferences. All pin labels is an inspection override for
known labels on visible pins; normal mode retains the symbol's existing styles. Semantically hidden
pins remain hidden and missing names are not invented. Optional SVG label nodes can be shown without
rebuilding the canvas, changing pin anchors or saving the design. Markup must capture their actual
computed display state, including changes made before capture.

Comments and cursors affect visible SVG overlays, including overlays arriving after the preference
changes. They do not delete threads, alter roles, or stop synchronization/broadcast. Keyboard shortcut
bar controls the optional action/zoom toolbar while keeping Frame model available. Its exact editable
Flux hint contents remain a separate parity task. These display options are presented in Schematic;
broader contextual3D View unification and surface analysis are subsequent work.

Test real rendered labels, keyboard/input/gesture guards, future comment/cursor overlays, account and
project isolation, mounted Comments loading beside another pane, reload, narrow viewport and unchanged
saved version/CAD bytes. Do not post comments to the main workspace; comment/presence fixtures belong
only to isolated test servers. Baseline old41 is pane-stack-frozen41.json with byte/mtime snapshot
schematic-display-start41.json. Keep the software-first goal and deferred watch unchanged.

Comment draft/reply/focus state clears at project, account or project-load boundaries, matching the
existing application's project-switch policy. The widget now enforces this boundary itself; reads,
cached results and presence packets carry the same generation identity. This is not persistent draft
recovery. Successful older actions may finish on the server but cannot clear a replacement context.
Replies track submitted revisions and pending ownership; newer editing remains open after completion.
Preference caches and notice bookkeeping are bounded for both reads and writes. Hidden pins emit no
pin-specific body, label, net text, cross, endpoint dot or hit target; source connectivity is retained.

Acceptance:178 Node and470 browser checks/59 suites, current installed wheel34assets matched.
Fresh main audit verifies all42 idle, old41 exact bytes/mtimes, own typedv1 and frozen native/history
files. Personal QA preferences restored; current console0errors. See schematic-display-acceptance.json.
Late source fixes invalidate stale access responses by sequence/load/socket/actor, reconcile retained
project resources after failed opens, and bound comment transports to30s without mutation retries.
This deadline cannot undo an already accepted server write. The two final compact-toolbar checks use
actual element hit targets after layout settles, rather than only comparing bounding rectangles.
