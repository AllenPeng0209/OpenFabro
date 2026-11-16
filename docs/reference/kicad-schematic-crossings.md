# Schematic crossing evidence

The [KiCad10 schematic manual](https://docs.kicad.org/10.0/en/eeschema/eeschema.html#wire-junctions)
distinguishes a crossing from a connected junction. A perpendicular intersection inside both wires
can remain independent; a connection is explicitly marked. Interactive endpoint placement can create
a junction, so it must not be treated as an independent crossing by this exporter.

The installed KiCad CLI was checked directly: a generated four-port schematic with two crossing
wires and no dot retained two separate nets. Adding a dot at the crossing joined them and caused the
pin/net parity check to fail. This is executable evidence in
`tests/test_schematic_crossings.py`, separate from the documentation statement.

Routing uses symbol obstacles and electrical contact checks. Proper interior crossings have a cost,
so a short clear detour can be preferred. A temporary visibility-grid node or pin-escape portal is
not necessarily a final vertex; compressed final paths are checked again. Collinear overlap, foreign
wire endpoints, bends or a foreign pin at the intersection are refused. Same-net branches and their
junctions retain their existing rules.

The real three-header fixture now completes six explicit guides across720 guide-order permutations.
This is scoped routing evidence, not a proof for arbitrary schematics or physical manufacturing.
The existing90,000-point search-grid budget remains; exceeding it is reported separately from a
geometrically blocked path. Native generation19 writes a new directory, preserving prior files,
and reports explicit-guide routing counts. Zero explicit guides does not mean all logical nets have
been drawn as wires.

The source-review followup reserves hierarchical terminal stubs before routing, rejects conflicting
stubs, counts unavailable/cross-sheet guide anchors, and bounds native waypoints at100. Policy v2
invalidates older policy caches even within generation19, allocating a separate suffixed directory.
Five generator/emitter regressions cover these boundaries. Fixed paths whose endpoints no longer
match their anchors retain the existing autoroute fallback; they are not absolute geometry locks.
Actual checks still expose six filtered library-configuration warnings separately from retained
ERC findings. Final bounded acceptance is recorded in `test-results/wire-routing-acceptance.json`.
