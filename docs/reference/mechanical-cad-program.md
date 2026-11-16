# Editable mechanical CAD program format

A visible project file such as `cad/bracket.cad.json` is the editable source. It contains schema1,
units`mm`, name, named scalar parameters, ordered features and the result feature ID. Rebuilding uses
the real FreeCAD solid kernel. Previous model assets remain immutable; edit the original CAD source,
not the generated `mechanical/` copy. No generated Python is executed.

```json
{
  "schema": 1,
  "units": "mm",
  "name": "Mounting plate",
  "parameters": {
    "width": {"value": 40, "unit": "mm"},
    "depth": {"value": 24, "unit": "mm"},
    "thickness": {"value": 4, "unit": "mm"},
    "hole_diameter": {"value": 3.2, "unit": "mm"}
  },
  "features": [
    {"id": "plate", "op": "extrude", "profile": {"kind": "rectangle", "width": "width", "height": "depth"}, "vector": [0, 0, "thickness"]},
    {"id": "hole", "op": "hole", "target": "plate", "origin": ["width/2", "depth/2", -1], "diameter": "hole_diameter", "depth": "thickness+2"}
  ],
  "result": "hole"
}
```

All vector values are3D. Dimensions can be numbers or arithmetic strings using parameters with
`+ - * /` and parentheses. Parameter values themselves are finite scalars. Units are mm, deg or number;
CAD coordinates are X/Y/Z with Z up and angles in degrees. No functions, Python, files or attributes
are valid dimension expressions. Feature references must name earlier features.

| Operation | Fields beyond `id` and `op` |
|---|---|
| `box` | `size:[x,y,z]`, optional `origin` |
| `cylinder` | `radius`, `height`, optional `origin`, `axis` |
| `extrude` | `profile`, nonzero `vector` |
| `revolve` | `profile`, optional `origin`, `axis`, `angle` (default360) |
| `loft` | `profiles:[profile,...]`,2–16 ordered sections |
| `sweep` | `profile`, `path:[[x,y,z],...]`; polyline path with miter joins |
| `cut`, `fuse`, `common` | earlier `target` and `tool` IDs |
| `translate` | `target`, nonzero `vector` |
| `rotate` | `target`, `angle`, optional `origin`, `axis` |
| `shell` | `target`, positive `thickness`, `faces:"top"|"bottom"|[zeroBasedIndices]` (defaulttop, inward thickness) |
| `fillet` | `target`, `radius`, `edges:"all"|"vertical"|[zeroBasedIndices]` |
| `chamfer` | `target`, `distance`, same edge selectors |
| `hole` | `target`, `diameter`, `depth`, optional `origin`, `axis` |
| `linear_pattern` | `target`, `count`, nonzero `step:[x,y,z]` |
| `circular_pattern` | `target`, `count`, `step_angle`, optional `origin`, `axis` |

A profile has `kind:"rectangle"` plus `width,height`, `kind:"circle"` plus `radius`, or
`kind:"polygon"` plus2D `points`. Optional3D `origin` defaults to[0,0,0], `normal` defaults to[0,0,1].
Rectangles start at the local origin; circles are centered there. Local XY is rotated from+Z to the
specified normal before translation. Circular patterns increment step_angle per copy, including the
original at0°. Patterns produce multiple solids; use Boolean operations for other relationships.

At most64features,64parameters,64copies per pattern,256polygon points and128sweep points are accepted.
Dimensions must be finite within±10000mm and positive sizes at least0.000001mm; native kernel validity,
feature/mesh bounds and build time may impose tighter limits. Kernel errors and invalid solid results
reject the entire build. A hole must remove material from its target; an outside or missed hole reports
an error. General Boolean subtraction may validly leave its target unchanged. STEP is reimported and compared with the built
solid count, volume and bounds before publication. STEP/STL/FCStd, exact source copy, mesh and native
verification report are retained for every accepted model revision. Full arbitrary CAD imports,
curved/spline sweep paths, general constraint solving and motion mechanisms remain separate.

## Linked assemblies

`component` loads a verified source: `{kind:"model",path:"cad/part.cad.json",asset_id?:revision}`,
`{kind:"asset",asset_id,bodies?:indices}`, `{kind:"board"}` or
`{kind:"enclosure",part:"base"|"lid"}`. Optional `label`, `translation:[x,y,z]` and
`rotation:{axis:[x,y,z],angle,origin:[x,y,z]}` preserve rigid source coordinates. PCB STEP Y is
native CAD Y, distinct from the older browser scene's display conversion. All source bytes are
pinned during the build; current links reject stale nested dependencies. Pinned historical
models retain their saved geometry and coverage limits.

`assembly` has `members:[earlier feature IDs]`, nonempty `fixed:[member IDs]`,
`clearance_mm`, optional `mates` and pair `rules`. Each mate has `id`, `type` (coincident,
concentric, aligned, offset), moving `target`, `reference`, `target_anchor`, `reference_anchor`,
optional signed `offset` and `flip`. Anchors use `kind` plane/axis/edge/datum, `normal`,
`extreme` min/max/nearest and optional point/body/index/radius selectors. Coordinates are local
to the source before placement. Top outward face is normal+Z/extreme max; bottom outward face
is normal-Z/extreme max. Coincident flips normals by default and moves along the reference
normal by offset; concentric aligns and centers axes while retaining axial freedom. Aligned
changes direction; offset changes signed distance. Pair rules name `a`,`b` and can override
`minimum_mm`/`allow_overlap_mm3`.

Directed acyclic mates reject conflicts/cycles; unassigned freedoms remain possible. Native
`metrics.assembly` records solved placements, residuals and every member pair's real common
volume and minimum distance. Incomplete source geometry sets overall fit pass to null, including
nested assemblies. Pair checks exclude internal geometry inside a member. This is static native
fit evidence; physical tolerance, kinematic motion, production and full Flux parity need more work.

## Picked native references

In a current assembly preview, **Mate parts** isolates the selected member while you choose a
face or edge. Native planes support coincident mates; cylinder faces and circular edges supply
axes. Aligned currently changes direction, without making lines collinear. Draft Undo/Redo
changes the chosen references; saved CAD Undo/Redo restores source/model pointers. Leaving the
editor or changing a source cancels obsolete picks. Image capture waits until picking ends.

Native selectors additionally contain `body_instance` and `reference`:
`{schema:1,entity:"face"|"edge",surface,position:[x,y,z],direction:[x,y,z],edges,wires}`.
Copy these values from the verified scene or `inspect_mechanical_topology`; do not fabricate
them. Position is normalized within the source body. The signature and physical instance path
guard compatible parameter edits; changed topology or instances require reselection. This is
not a general persistent-topology naming guarantee. A saved selector point can describe the old
selection snapshot while the solver matches the current native element after a dimension edit.

For a new picked mate, build with `expected_asset_id` as well as `expected_sha256`; stale model
or dependency snapshots reject dispatch. Ordinary rebuilding after a known dimension update
uses the saved source and its SHA. The read-only topology inspector accepts a source, optional
retained asset/member/body filter, face/edge, offset/limit and expected scene SHA for pagination.
It exposes exact native geometry and source-local selectors without triangle payloads. Historical
scenes lacking the pick map stay readable and are never regenerated by inspection.

## Native sketches and feature editing

`sketch` defines `geometry`, `constraints`, optional `plane:{origin,normal}` and
`require_fully_constrained`. Geometry uses named `line` (start/end), `circle` (center/radius),
`arc` (center/radius/start_angle/end_angle), `ellipse` (center/major_radius/minor_radius/angle)
or nonperiodic `bspline` (poles/degree/expanded knots/optional weights). Coordinates are local
2D millimeters, angles degrees. Construction geometry is excluded from material. Limits are
64 entities and256 constraints; native solve and geometry budgets still apply.

Each constraint has `id`,`type`,`refs`, optional `value` and `driving`. Reference entries name an
entity and optional start/end/center point; origin is already a point, while x_axis/y_axis are
external lines. Supported types are coincident, horizontal, vertical, point_on_object, parallel,
perpendicular, tangent, equal, symmetric, distance, distance_x/y, radius, diameter, angle and block.
Driving dimensions accept existing named parameter expressions. Reference dimensions have
driving:false and do not remove freedom. Source geometry seeds need not equal the solved shape.

Follow a closed sketch with `extrude_shape(target:sketchID,vector:[0,0,"depth"])` for a linked
native extrusion. Hole loops remain cutouts. The report includes actual solved geometry, native
Sketcher type, constraint identities, DoF and solver diagnostics. Fully constrained requirements,
conflicts and redundant constraints are enforced before publication.

**Features** opens the source feature list, native sketch preview, geometry/constraint forms and
shared dimensions. **Solve preview** leaves the saved source/model/history unchanged; **Save and
rebuild** publishes a verified revision. New part offers a constrained sketch option. Exported
FCStd preserves native driving parameter, Sketcher and Part::Extrusion dependencies. Blocked seed
geometry and other static source features still require source rebuilding.

## CAD Undo and Redo

The mechanical editor keeps a persistent project CAD history of exact source bytes and the active
native model pointer. Parameter edits, saved CAD source and native rebuilds are separate operations.
Ctrl/Cmd-Z and Ctrl/Cmd-Shift-Z, or the CAD Undo/Redo buttons, restore the corresponding saved state
without rebuilding. A source-only state can intentionally display a stale older model. Undoing part
creation removes its source/current pointer while retaining every generated model export.

The last512changes are undoable across reload; discarded redo branches and older native assets remain
on disk. New edits clear Redo. Conflicting current source/model/history or corrupt target snapshots
block restoration. Save or discard unsaved CAD drafts first. Queued keyboard requests stop on errors
or an editor/project change before submission. Textarea/input Undo while typing remains local.

This is CAD-editor project history. PCB/schematic Undo remains in its editor, and whole mixed Agent
file/design batches use their separate change-review mechanism. Restoring a file through that mechanism
is recorded as another exact CAD source change, including any resulting stale model state. FCStd remains
static native shapes with source metadata; these journal controls do not create a native expression graph
or provide crash/powerloss/multiprocess guarantees.
