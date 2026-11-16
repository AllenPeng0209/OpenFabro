# Custom pad copper and truthful mechanical holes

The old library editor rejected custom copper, and browser geometry exposed only the tiny native
custom-pad anchor. Treating that anchor or the enclosing rectangle as copper fills SVG notches and
voids, misplaces routing targets and misreports contact. Mechanical holes also need visible edges
on a black substrate, without fabricating copper.

Keep bounded SVG paths/documents, DXF or explicit polygons in the editable pad source. Declare
units and curve tolerance. Preserve curve extrema, fill winding and internal holes; constrained
triangulation emits native filled primitives. Select a small native anchor strictly inside copper,
independent of the bounds center. Browser polygons, contours and routing anchors come from actual
native geometry. Connectivity, routing obstacles and endpoint trimming use the filled region.

Native hidden metadata retains the original vector source when it matches current primitives to
native precision. An external native edit takes precedence over stale metadata; editable native
polygons and an explicit note replace that stale association. A portable Project.library.json keeps
source, declarations and native hashes alongside native libraries. Curve flattening and native
micrometer rounding remain explicit; they are not fabrication or physical tolerances.

Custom source stays private until a native plot, pin parity and baseline/candidate DRC are reviewed.
Apply rechecks design/native/render-input digests through the shared source write/Undo slot. Pending
responses belong to the account, project load, view, footprint and pad identity. Setting revisions,
peer saves and ownership changes invalidate obsolete approval. Chat may inspect declared geometry;
only an authorized Agent can edit it. Native findings stay visible and require explicit acceptance.

Draw nonconductive holes at their actual rotated/offset opening, with a neutral screen-pixel boundary.
Picking and selection follow that opening. Newly authored mechanical holes explicitly omit copper.
A native NPTH can carry washer/surface copper: retain it, respect layer visibility/focus and never
infer a plated barrel. Automatic continuity across such native surfaces remains explicitly unknown.
The project-hole policy rebuilds old caches into new directories; geometry9 creates separate sidecars.

Accepted engineering scope:1239Python (one existing socket-thread warning),309Node and709browser
checks across113suites. Actual in-app Agent preview/apply saved the L and CONNECT annulus; main
GUI Undo/Redo/Undo restored whole semanticv3 atv7. Complete-copy Gerber/Excellon/SVG/netlist/DRC
and seven no-drill native-SVG pixel samples verify material, voids and two mechanical openings.
Receipt:`test-results/pad-shapes-acceptance.json`; frozen66 protects3309files.

The current installed wheel matches123Python/108web/105statics and passes actual nativecustom
smoke using existing dependencies. Two exact AI reports and actual Layout image inputs separate
model reads/pixels from host executions. Four desktop/mobile report renders fit without edits.
Disconnected regions, unoutlined strokes/text, richer pad stacks, Library tiny-hole contrast and
the remaining complete Flux scope stay open. A generic NPTH surface note is overbroad on false
rows; authoritative booleans/layers/actual exports take precedence until that wording is refined.
