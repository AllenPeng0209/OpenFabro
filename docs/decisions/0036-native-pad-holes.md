# Editable drilled pads and native copper centers

Native pad `(at ...)` positions locate drilled anchors. KiCad's `(drill (offset ...))` moves the
copper shape relative to that anchor, despite ambiguous file-format wording. Earlier browser
geometry interpreted it as a hole offset, placing both copper and drill incorrectly.

Use copper-center coordinates for editable library pads and browser geometry. `drill_offset`
means the hole center relative to copper, in the unrotated pad frame. `drill_shape` and two-axis
`drill_size` preserve round and slotted holes; scalar `drill` remains their minimum dimension.
The native writer transforms the hole anchor and negates the native shape offset. Import and
geometry parsing perform the inverse. Library preview follows KiCad's rotation direction.

Reject invalid, ambiguous or non-finite dimensions and holes outside the actual rounded outline.
SMD conversion removes obsolete drill state; Undo restores the whole saved asset. Preserve exact
declared project holes instead of silently widening to a process default. Native DRC can report
that process incompatibility. The upstream installed-footprint widening policy stays separate.

Geometry schema8 writes separate cache sidecars, preserving original files. A conditional project
hole policy regenerates old silently-widened project PCB caches into new folders. Neither upgrade
changes saved design versions or replaces historical native files.

Real KiCad10.0.8 Gerber copper flashes and Excellon slot endpoints provide independent physical
position checks on both sides at0/90/37degrees. Its IPC exporter returned unrotated shape offsets
for the rotated probes, while Gerber and native shape placement agreed; IPC pad coordinates are
therefore not the authority for this check. Material/stackup IPC evidence remains separate.

Accepted engineering scope:1214Python (one existing socket-thread warning),305Node and693browser
checks across109suites. The full functional batch precedes the final prompt-only clarification;
two affected context tests, installed native smoke and actual in-app correction cover that addition.
Three exact Agent reports retain invalid-ID/reference and ignored-placement failures, canonical
placement correction and final v8 review. Main GUI Undo/Redo/Undo restores whole semanticv4;
private-copy Gerber/Excellon/netlist/DRC verify three holes/two PTH and2nets/2pins. The intentional
0.2mm process violation remains visible. Receipt:`test-results/pad-holes-acceptance.json`.

The last report is9507characters, seven over an internal9500target; this formatting deviation is
retained byte-exact and is not claimed as passed. No false measured-length statement is present.
SVG/custom copper pads, trapezoids, castellations crossing the outline, arbitrary pad stacks,
dark-substrate NPTH visibility and full Flux pad-rule/pixel parity remain open.
