# OpenFabro workbench

The local OpenFabro workspace for circuits, enclosures and complete devices: an open-source AI
hardware engineer with editable electrical and mechanical views, engineering checks and manufacturing outputs.

## Run

```sh
./run-workbench.sh
```

Open <http://127.0.0.1:8770>. Local project data is in `.local/projects`; provider settings are in
`.local/openfabro/config.json` on a fresh workspace (an existing `.local/wholeboard` workspace is reused). The original interface is available at `/classic`.

Opening or switching projects shows a loading view until that project's saved data arrives. The editor
keeps reference/previous BOM rows hidden, disables project editing and saving, and ignores out-of-order
responses from earlier project choices. Reselecting the current project cancels a pending switch.

## Keyboard shortcuts

Open **Keyboard shortcuts** in the main menu, or press Cmd/Ctrl-/; `?` opens it from the canvas.
The viewer supports search, editor filters and macOS/Windows key labels. Esc closes it and returns
focus to the previous control, including an unchanged chat draft. Cmd/Ctrl-K remains command search.

Alt-N opens project creation, Alt-C reveals Chat, Cmd/Ctrl-F searches the existing components, and
Cmd/Ctrl-Shift-A deselects. In Layout, Alt-L toggles Layers and Alt-3 switches between Layout and 3D.
Use `0` to fit the selected component or the design, Shift-0 to fit the design, and `=` / `-` to zoom.
Canvas editing shortcuts pause in text controls and dialogs. The viewer lists the implemented gestures;
additional bindings in the [Flux reference](https://docs.flux.ai/Introduction/pcb-editor-shortcuts)
remain tracked in the parity register.

## Visual reference

- Public Flux project: <https://www.flux.ai/markwuflux/on-air-r2-demo?editor=schematic>
- PCB editor documentation: <https://docs.flux.ai/reference/reference-pcb-editor>
- Workflow reference: <https://docs.flux.ai/Introduction/getting-started-in-flux--project-setup>
- WholeBoard engineering foundation: <https://github.com/DingoOz/WholeBoard>, revision `1471c54c2f55e3e2c1ae75e5f7ff23bfe77f84fe`

Reference captures are in `docs/reference`. They are comparison material, never the application's canvas.

The reference has a 36 px project header, a 37 px pane header, a resizable chat pane,
a black canvas, a floating project inspector, and compact view tabs. The new UI follows
that editor rather than Flux's marketing site.

Design tokens: canvas `#101010`, background `#212121`, panels `#2e2e2e`, raised controls `#424242`,
text `#eeeeee`, primary `#1dfdc0`. Roboto is used for interface text. Thin 1 px dividers,
4–8 px control radii, and a 32 px button rhythm follow the reference. Chat and Inspector
can collapse to give the actual circuit more room. No dashboard cards are added around the editor.

## Objects tree

Objects shows the native Layout hierarchy: components, footprints, individual physical pads, footprint
and board graphics, nets with traces/arcs/vias, zone definitions with filled islands, and outline edges.
Same-number pads remain separate physical objects. Search reveals matching ancestors; click selects,
Cmd/Ctrl-click toggles, and Shift-click selects the visible range. Arrow keys and Enter navigate the tree.
The eye controls change actual painting, hits and routing candidates without saving the design. Visibility
is stored locally per project/view. Search filters the tree and retains the canvas contents.

The Schematic tree contains nested/empty sheets, components and units, authored wire guides, endpoints
and labels. Selecting a unit opens its sheet; double-clicking a sheet opens it. Label/wire visibility uses
the native drawing, preserving shared visible wire sections. Tree rows are retained during selection so
keyboard focus and double-clicks survive Inspector updates. Generated board features expose read-only
geometry; supported component, wire, label and copper objects use the existing guarded editors. Mixed
selections block unsupported partial edits and drags.

Use a row's actions menu or right-click **Add → Group** to create a folder, or select related objects
and choose **Group selection**. Drag rows onto a group to move them inside, or before/after a sibling
to reorder. Nested groups, names, membership and order are saved in the design and participate in
Undo/Redo. Alt-Up/Down reorders the focused object; **Move to** offers the same organization on mobile.
Rename and Ungroup are available in the Inspector. Ungroup removes the folder and retains its members;
an empty group can be deleted separately. Inspector controls refresh when the native scene is ready.

Grouping preserves original categories: pads stay in their footprint, traces in their net and schematic
objects on their sheet. Selecting component groups selects the real components for supported bulk
operations; unsupported mixed selections are rejected as a whole. A group's eye controls its actual
descendants without creating a design version. Layout and Schematic organization are independent;
cloning retains saved groups while local visibility remains project-scoped. Logical reference/net
renames rebase organization keys. Deleted or otherwise unavailable identities are counted explicitly
and never replaced with invented objects.

The persisted schema is `editor.object_tree.{layout,schematic}`, each containing `groups`, `parents`
and `order`. A group has a stable `user-group:<ID>` identity, name and category/group parent. Member
keys use real object identities. Both manual saves and Agent proposals reject cycles, missing group
parents, duplicate ordering and malformed or oversized metadata. The built-in Codex instructions
describe this schema; group-only requests preserve all unrelated design fields. Groups currently
organize the IDE; KiCad group primitives, inherited rules, group clipboard, broader generated schematic
objects, mechanical assembly trees and general primitive editing remain parity work.

Native producer17 derives stable IDs for the rendered footprint/pad/copper/zone/graphic objects before
placement, side, value or net assignments. Hidden native properties and schematic pin-instance UUIDs
can still regenerate; raw PCB/SCH byte identity is not guaranteed by parsed geometry identity. Parsed
geometry schema4 retains those IDs, adds deterministic legacy identities, separates zone definitions from
filled islands, and supplies net-tagged airwire records. Older PCB/SCH/geometry files remain available.
Returning to an earlier design generates into a new folder when its previous folder already contains
outputs; it preserves the old snapshot's bytes and modification times. The current matching snapshot
continues to be cached. Native producer, geometry schema and saved design version are separate values.

## Engineering boundaries

### Parametric symbol editor

Open **Add tab → Symbol**, **Edit symbol** in a component Inspector, or a pin's **Symbol** button in
the project Pins table. Select a component, then choose Native or Parametric style. The Symbol tab
shows each native sub-symbol and every actual source pin. Select pins by click, Cmd/Ctrl toggle,
Shift range or a rectangle; edit Orientation, Pin Group, Section, Terminal Order, display name and
Sub-symbol suffix in the pin Inspector. Only touched fields apply to a multi-pin selection.

Drag a pin to a side/section/group, drag a group to move all its members, or drag section headers
to reorder. Drop pins outside the symbols to name a new sub-symbol. Double-click names to rename;
empty sub-symbols can be removed after their pins move elsewhere. Unit compaction migrates poses,
symbolic object-tree references and physical-pin wire anchors together. Wheel zoom, middle-button
or Space-drag pan and Fit affect only the viewport; Fit retains an unsubmitted property draft.

Parametric geometry is emitted as a self-contained KiCad symbol and parsed back for the web editor.
Source pin numbers, electrical types, PCB placement and copper stay unchanged. Display aliases are
presentation fields. Existing schematic poses freeze so unrelated parts do not reflow. Native XML
pin groups are checked before persistence; a previously routed drawing cannot silently become
unroutable. Valid exact wire paths remain intact. An invalid exact path requires a concrete route
review with a native preview; Cancel leaves the saved design and style unchanged.

The review badge identifies missing explicit Orientation/Group/Section metadata, separately from
electrical validity. Read-only roles can inspect and select; they cannot submit or name edits. Old
responses and naming dialogs are scoped to project, component and saved version/spec. The built-in
Codex exposes `inspect_symbol_layout` and `edit_symbol_layout`; Chat cannot use the editing tool.
Native pin parity is not ERC/DRC, simulation, manufacturing readiness or a physical test. Exact Flux
Symbol-tab pixels, arbitrary native-import roundtrips and broader presentation edges remain unverified.

The bundled USB-C reference uses upstream's `tests/sample_spec.json`, with editable presentation
coordinates and starter placements. It is a reference design, not a routed or manufactured board.
The schematic uses actual native KiCad symbols and the saved netlist. The PCB editor renders native
KiCad library geometry and supports group placement, layer controls, real manual traces and through vias.
Existing geometry stays visible while new native geometry is generated; editing that stale geometry waits
for the replacement. Airwires resolve existing tracks, vias, arcs and filled copper into connected islands. ERC/DRC, raw reports, and physical validation are distinct checks.

Draft changes use an optimistic version to prevent two browser tabs overwriting one another.
Edits mark generated files/checks as stale. CSV export uses saved values and guards against
spreadsheet formula execution. Project creation and editing do not call an AI provider.

KiCad, its libraries, TraceMaker, ngspice, and FreeCAD are separate dependencies. The workbench
reports missing tools and checks that have not run. Manufacturing builds use the original
OpenFabro pipeline. Model credentials are configured through Settings; no model request is
made just by opening the application.

The local signed-in Codex CLI can serve as the AI provider. Agent mode can propose design/doc edits and
call engineering tools; Chat cannot change the design. New instructions can be queued during a run.
Stop is a separate control. Requirement reviews distinguish supported evidence, failures, and unknowns.
AI file proposals check the file versions captured before inference, preserving saves from external editors.
Read-file tools return character chunks with full-file hashes, offsets and explicit truncation. Native
geometry JSON also has a structured summary of the complete file. Evidence remains available across
tool turns as valid JSON, with explicit omissions when the prompt budget is exceeded.

Automatic Markdown context includes at most twelve documents and the first 12,000 characters of each.
Each entry reports its full-file SHA-256, byte and character lengths, delivered range, truncation and
next offset; the coverage record explicitly lists omitted paths and read failures. Hidden and symlinked
paths are excluded. The read-only `list_documents` tool pages the complete visible Markdown catalog;
`expected_index_sha256` rejects a changed catalog. `read_file` uses character offsets and accepts
`expected_sha256` to reject continuation against a changed file. Both automatic context and file reads
share a 2,000,000-byte cap and require valid UTF-8. A full-file hash or an EOF-reaching chunk does not
mean that the model received the complete body. The prompt asks it to reuse prior ranges, read only
the missing task-relevant sections, and keep unknown or unread ranges explicit.

The Files view renders Markdown headings, tables, code and project-relative links/assets. Preview and
Source are read-only; Edit opens a guarded draft. Preview can render the unsaved draft, and Cmd/Ctrl-S
saves the active file. Edits made while an earlier save is in flight remain unsaved and use the returned
file hash for their next save. Late file/edit responses cannot replace a different project's preview.
Scripts, forms and app control attributes are removed; remote Markdown images are shown as links.

Files opens the Documents and Assets workspace. Project Markdown appears as a folder tree; selecting
an image asset shows its actual raster/SVG preview, with SVG Source available separately. All files
opens source, saved design history and native generation folders. Search matches complete paths;
identical basenames retain independent preview, draft and download context. Downloads use saved
contents while an unsaved draft remains local. The mobile picker retains complete relative paths.
Switching to Files closes the canvas Objects drawer and Inspector so they cannot cover the document
viewer. Files uses its own Documents/Assets browser on desktop and its own picker/pane on mobile.

Under All files, editing `design.json` saves a complete design version. Its accepted spec and Undo
entry are installed together, including when the live own-save event arrives before the HTTP response.
While that request is pending, you can keep typing a newer source draft or browse other files;
graphical design edits and duplicate submission wait until it finishes. Switching projects also waits
for the outstanding design save. A newer peer save received during the request is fetched afterward.
Your source draft keeps its original base version across remote updates, so it cannot silently
overwrite another editor's changes. A rejected save retains the raw draft and leaves the saved design
unchanged. Unsaved file text now has an owner/project-scoped recovery copy in this browser. After
reloading, choose **Review drafts** to compare it with the current saved file. Independent edits merge;
overlaps require **Use draft**, **Use saved** or a custom resolution. **Apply to editor** restores an
unsaved buffer; **Save file** commits it through the existing SHA or design-version guard. The
comparison refreshes if the source or another tab's draft changes during review. Deleted files require
explicit recovery confirmation and are created only on Save. Line endings and the final newline are
preserved. Saving advances the next edit's comparison base, including keystrokes typed during Save.

Recovery copies belong to this browser and origin. A storage-denial/quota message means the active
buffer is only in this tab; explicit Save remains available. Clearing browser data removes local
copies. This currently covers the Files editor, not graphical-design edits, chat input or every CAD
dialog. A recovered CAD source remains unsaved and cannot be built until saved.

The file catalog is paged beyond1,000 entries. Its digest binds visible path/size/mtime metadata,
the saved design and exact native output pointer; changing a catalog between pages returns409.
The browser discards mixed pages and retries a bounded number of times. Hidden and symlink paths
are excluded, and special characters are URL encoded. Knowledge and Export load the same complete
catalog; Export uses its own scoped data instead of replacing the Files browser's inventory.

Current native roles come only from exact saved PCB/SCH/geometry paths and the complete saved-spec
fingerprint. Other folders are stored outputs; no generation version is inferred from a filename.
Prior parsed geometry stays distinct from the active sidecar. A generation from another saved design
is marked Older design. History/native sources stay read-only, including case aliases on macOS;
manual text and Agent writes share filesystem-aware protection. These labels describe file provenance,
not an engineering or manufacturing acceptance.

Share can grant workspace accounts or expiring links Viewer, Commenter, or Editor access. The local device
is the workspace administrator. Creating accounts or share links makes remote access private; revoking
access closes existing project event streams too. Comments, replies, anchors, and resolution are persisted;
online cursors are ephemeral. Other devices need a reachable server address. This is not a hosted service
or a simultaneous-edit merge engine.
Project editing rights do not grant permission to run host firmware build scripts; those require the
workspace administrator. Custom SPICE accepts inline circuit/model data, while simulator command blocks,
host-file includes and command substitutions are rejected before launching ngspice.

Manufacturing shows estimated PCB/assembly/component/shipping costs and saved supplier prices/stock.
Fee estimates use OpenFabro's table; final manufacturer checkout prices must be confirmed separately.
The UI marks estimates stale after design changes. No quotation request places a fabrication order.

OpenFabro's GPL-3.0-or-later licence remains in force. See `LICENSE`.

## Native drill geometry and cache versions

Layout retains circular/oval drill dimensions and normalizes native copper/hole coordinates.
Slotted openings rotate and move with their pad; non-plated holes remove only the actual opening.
Hover a pad to inspect hole dimensions, plating type and offset. Editable and browser x/y denote
the copper center; hole offset is relative to copper in the unrotated pad frame. KiCad's native
drill offset instead moves the copper shape relative to a hole anchor, so its sign is translated.

In **Library editor**, select a footprint pad. Drilled types expose **Hole shape**, separate oval
**Hole X/Y**, or a circular diameter, and **Hole offset X/Y**. Slot size and offset update actual
native geometry without moving the copper center. Invalid/non-finite dimensions and holes outside
the rounded outline are rejected. Switching to SMD removes obsolete drilled fields; Undo restores
the complete source. The compact property panel has its own vertical scroll region.

Project-owned holes keep their exact declared size, including a size below the configured process
minimum. Native DRC reports that mismatch instead of silently widening the project pad. Imported
round/oval holes round-trip through portable footprints. Trapezoids, castellations crossing the
copper outline and richer pad stacks remain separate work.

**Custom SVG / DXF shape…** in footprint pad properties opens an editable vector-source dialog.
Choose SVG path/document, DXF or native polygons, declare units and a curve tolerance, then review.
The private candidate compiles filled regions, verifies native pin groups and runs actual native
plotting and baseline/candidate DRC. Apply retains the reviewed source/native digests and uses the
normal complete source Undo chain. Changed inputs, peer saves and owner/view changes invalidate
obsolete approval. Existing native findings remain visible; applying a reviewed draft does not
approve manufacturing.

Bounds-center coordinates can lie in a notch or an annular void. The compiler chooses a small
native anchor inside real copper; routing handles, contact/obstacles and endpoint trimming use
the actual filled geometry. SVG winding and holes remain. Curves are flattened with the declared
tolerance; native serialization also rounds to micrometers. These are separate numerical effects,
not physical fabrication accuracy. One connected filled region is authored per pad; disconnected
regions need separate pads, and strokes/text must first become filled outlines.

The library and Layout preview actual custom contours. Native footprint metadata retains vector
source while it matches the current native primitives; an external native edit takes precedence
over stale SVG metadata. The import note explains fallback to actual native polygons. An exported
Project.library.json keeps editable declarations and native hashes and can be reimported.

Mechanical holes default to no copper. Native NPTH washers can contain surface copper despite an
unplated barrel; this copper is preserved and follows copper layer visibility/focus. Its automatic
cross-surface continuity is explicitly unknown. A neutral Layout boundary and accurate picking
make the physical opening visible on black without drawing imaginary copper. Library ghost
profile outlines are editing aids. Trapezoids, richer pad stacks and remaining pixel parity stay open.

Parsed geometry uses its own `schema`/`geometry_schema` version, independent of the native producer
schema and the design save version. Use the `geometry_file` or `geometry_url` returned by native
generation for the current data. Upgrading an older cached preview creates a versioned geometry
sidecar from the existing PCB. It preserves the original PCB, SCH, old JSON and saved design.
AI context and layout use the current geometry; old snapshots remain available as historical files.
Schema8 corrects copper-center/relative-hole-offset semantics. A separate project-hole cache policy
rebuilds historical silently-widened project footprints into new native folders. Existing originals
remain unchanged. Physical position checks use real Gerber copper flashes and Excellon hole records;
inspected KiCad10.0.8 IPC positions disagreed for rotated-offset pads and are not used as that check's
authority. This is an interchange limitation, not proof of physical fabrication/plating.

Module update previews list the local changes being kept, including explicit **Keep local** conflict
choices. The saved `local_overrides` and preview count agree. When a local edit and a new release
converge to the same value, the value no longer counts as an override against the new baseline.

## Project libraries

Open **Add a view → Library editor**, or **Part library → Edit project library**. Create symbols,
footprints and reusable parts. Select a pin, pad or drawing primitive to edit its properties; drag an
object to move it on the chosen millimetre grid. Drawing changes share the design's undo, autosave,
version history and cloning. Changing an asset ID updates component and reusable-part references.
Removing a used asset or a connected pin/pad is rejected until its connections are changed.

Native project asset references use case-sensitive **Project:AssetID**, matching their library keys.
Lowercase `project:NAME` identifies a stackup preset, a separate namespace. A component's PCB
position uses its `placement` object (`x_mm`, `y_mm`, `rotation`, `side`, `locked`); unrelated top-level
`position` metadata does not place the component. The Agent prompt supplies this distinction and
requires comparing the generated footprint coordinates/bounds with the requested position.

## Sheets and reusable modules

In Schematic, use **Create sheet** beside the sheet picker. A selected component or selection can move
into the new sheet. Nested sheets, empty sheets, names and parent relationships are saved in the design.
Click a sheet boundary to inspect it, drag to move it, and use its lower right handle to resize it.
Double click or press Enter to open it. Components can return to Main through **Move to sheet**.
Removing a sheet moves its components to the parent and preserves their electrical connections.
These are actual KiCad hierarchical sheets; native generation checks their exported pin groups.

In **Library → Modules**, save the complete current project as a module. Choose the exposed nets and
terminal labels. The snapshot includes schematic presentation, project symbol/footprint dependencies,
PCB placements and actual native tracks, arcs, vias and zone definitions. Insert it with a unique
instance ID, a PCB offset and explicit connections to existing target nets. Unmapped nets stay isolated.
Terminal dots support direct schematic wires; adding an external pin retains internal routed copper.
Each insertion allocates unique component references and copper/zone identities. All instances remain
editable. Export/import `.module.json` packages to reuse modules in another project; no source-project
lookup or public library publishing is required.

The module and target board must currently have the same copper layer count. Choose a free PCB area
and run ERC/DRC after insertion.

Select components in Schematic or Layout and choose **Convert to Component** from the context menu
or Inspector. Prepare the module to view its actual native footprint/copper geometry before confirming.
Changing a setting invalidates the prepared draft; cancelling leaves the design unchanged. Confirmation
wraps the selected components in a child sheet and saves a reusable asset without moving the current PCB.
Undo restores the original selection and library. Existing ancestor terminals remain connected through
the nested hierarchy, including interfaces with no outside physical pins.

Automatic PCB capture bounds include selected courtyards and complete internal-net routes, including
detours. Bounds can also be entered manually. Shared-net copper is clipped to the region, with unselected
footprints excluded. Straight traces, exact circular trace arcs and linear zone contours with holes are
retained as native geometry. Captured zone polygons are refilled for preview. Separate captured polygon
fragments are not separate zone definitions. Curved zone contours are rejected explicitly; they are not
flattened. Only the project symbol/footprint assets needed by the selected components enter the package.

Shared-net stubs at capture boundaries may need new routing after reuse. The conversion preview reports
clipping and any outdated drawing guides that disagree with the canonical netlist; canonical connections
remain authoritative. Broader selection/CAD workflows and curved-zone capture remain gaps.

### Published versions and instance updates

In **Library → Modules**, use **Publish project to workspace** to freeze a source circuit and its
actual native layout. **Publish changes** creates an explicit new module version. Project save
versions and published module versions are separate. The workspace catalog only lists sources the
current account can read; access is checked again when installing or reviewing an update.

Use **Browse workspace** to install a published module in another project. Installed instances stay
pinned. A newer publication shows a bottom notification; **Review**, or **Project menu → Component
updates**, opens version selection and a three-way review. Choose instances independently and resolve
conflicts with **Keep local** or **Use module**. Connected interfaces removed by the source require
an explicit reconnection or disconnection. **Review selected** checks the merged native pin groups
and shows PCB/schematic previews. Only **Update selected** saves the proposal. Cancellation, an
external saved edit, or changed conflict choices prevent applying an obsolete preview. Updates,
reference mappings and frozen baselines participate in normal undo/redo.

Value-only changes preserve existing native copper, pads and placements. Physical changes invalidate
affected-net copper, including shared-net copper; review the summary and reroute it. Source project
assets are isolated under content-addressed dependency IDs so updating one instance does not change
another instance's footprint/symbol. Newer portable packages can carry the same immutable history;
an instance may select an intermediate release without downgrading the installed library head.
**Open source** opens the accessible original project, or makes an editable source from a portable
snapshot when no accessible local source exists.

This is a private self-hosted workspace catalog. Public library distribution, automatic draft
subscriptions, richer visual diffs and guided matching for ambiguous legacy instance mappings remain
parity work. Native pin parity is not a DRC or physical acceptance pass.

## Named net labels and power symbols

Click an unconnected native pin to open **Create a net or connect to an existing net** or
**Connect to the GND net**. Right-click another pin for the same actions. **Draw wire** enters
the normal bend-routing workflow. Label and power/ground symbols are also available in the Part
library and canvas context menu. Select a wire and use **Place net label** to attach one without
changing the existing native wire geometry or losing dependent junctions.

Review the connection before **Apply**. Established net merges require explicit confirmation and
clear copper/pours on affected nets for rerouting. Naming a temporary free-wire net binds it to the
existing project net while retaining that net's copper. New pin connections clear the pin's explicit
no-connect mark. Renaming a label renames its project net, all other labels, module aliases, copper,
simulation references and impedance net references.

Drag labels or edit their position/rotation in Inspect. **From Net Type** uses the project net's
Signal/Power property; Ground and Power symbols use actual KiCad power-library graphics. These are
schematic annotations: their native `#PWR` instances do not become design components, PCB pads,
assembly BOM items or extra exported electrical pins. A private ground in an inserted module keeps
its mapped net when rotated. Deleting the symbol preserves named pin connections and any connected
bare wire endpoint. Copying components carries attached labels with remapped node identities/nets.

Same-name explicit labels remain an electrical connection after a wire gap is cut. The cut preview
identifies the named connection and retains its original net. Cosmetic edits, merge changes and
symbol removal participate in normal undo/redo. Changed merge settings reset confirmation; an external
save or a canceled pending preview cannot apply an older proposal.

The Agent can use `edit_net_label`; Chat cannot mutate labels. Native parity is checked before a
tool edit is saved. Raw ERC remains authoritative: a ground symbol can expose an undriven power
input, even when the existing upstream filter reports a clean retained result.

Current Flux uses net labels/power symbols in place of retired Portal parts; see
[Connect nets without wires](https://docs.flux.ai/reference/reference-positioning-wiring#connect-nets-without-wires).
More complete label/object selection remains parity work.

## Bus groups and interface constraints

Open **Pins**, select actual terminal rows and choose **Edit selected bus properties**, or use a
pin's **Properties** button/context menu. A component Inspector also provides its default **Bus Type**.

The component Inspector also has **Part Type** and **Configure interface**. USB A/B/C, HDMI,
PCIe x1/x2/x4/x8/x16, MIPI CSI/DSI and DDR3/4 open a named-terminal review with editable starting
targets. Review matched/unchanged pins, existing-value conflicts and separate draft findings before
**Apply properties**. Choose **Keep existing values** or **Use interface values** explicitly when
needed, then review again. Part Type and generated metadata undo together. Missing, ambiguous or
shorted pairs cannot be applied; display aliases never determine electrical roles. Power pins remain
unchanged. No tolerance or timing limit is inferred. Nominal defaults are setup assumptions, not
protocol or manufacturer acceptance; selecting only a Bus Type still adds no numeric constraints.

Pin overrides can describe multiple interfaces on one component. **Bus Group** groups terminal
properties; it never joins electrical nets. Separate module instances retain their private net names.
Single-pin module terminals share the containing sheet's bus scope rather than each forming a bus alone.

The form supports Bus Type, Pair Role, Controlled Impedance Pair, polarity metadata, impedance/tolerance,
PN skew, Pin Delay, pair-to-pair skew, maximum path length and bus length mismatch. Only changed fields
are applied to a mixed selection. **Review changes** produces a real native preview and checks KiCad
pin-group parity without saving. **Apply properties** saves one revision with the existing routed copper
and placements; cancel, stale versions and changed form settings cannot apply an older preview.

Open **Buses** to inspect group membership, actual net associations and route analysis. Set an explicit
layer/via propagation model with **Propagation model**. A protocol name alone supplies no numerical
targets. Missing route/model evidence, insufficient pairs or missing impedance tolerance remain unknown.
The current timing calculation supports complete point-to-point straight-track paths. It removes copper
inside endpoint pads, adds specified package delays (unspecified delays default to zero), and models a
through-via barrel using board thickness and the entered ps/mm. Arcs, copper zones, branches and unsupported
via spans do not receive a timing pass. Pair-to-pair matching compares lane-mean delays inside this IDE;
it is not exported as an unrelated native all-net skew rule.
Mixed paired and unpaired signals in one Bus Group are visibly pending; place the unpaired signals in
a separate group for their constraints. Their constraints are not silently treated as checked.

Native export retains pin metadata in the schematic/footprint, package delay in PCB pads, explicit length
and skew constraints in `.kicad_dru`, a `.buses.json` manifest, and KiCad10 tuning profiles in the project.
**PCB text `die_delay` is in ps**; KiCad's in-memory pad value is in attoseconds. Project JSON profile
`delay` is in attoseconds/mm and profile width/gap in nm. For example, a 10ps pad writes `(die_delay 10)`,
while a 7ps/mm layer profile writes `"delay": 7000000`. Pin Delay is bounded by KiCad's pad time range
(2147.483637ps). Native producer schema16 and parsed geometry schema3 supersede the earlier incorrect
pad-unit mapping; older native artifacts remain historical files, and the saved design does not change.

The IDE's endpoint trimming can differ from KiCad's native endpoint handling. The package-delay
acceptance example gives 73.1/93.1ps in the IDE and 85/105ps in native DRC: both detect the same20ps
skew, but the absolute values are not interchangeable. Inspect the actual native report separately.
The file-unit mapping follows KiCad10's [pad parser](https://github.com/KiCad/kicad-source-mirror/blob/10.0.8/pcbnew/pcb_io/kicad_sexpr/pcb_io_kicad_sexpr_parser.cpp)
and [unit formatter](https://github.com/KiCad/kicad-source-mirror/blob/10.0.8/common/eda_units.cpp).

The impedance number is an explicitly labeled outer-layer IPC-2141 estimate from OpenFabro's nominal
stackup, only for supported uniform routes. It is not a field solver, supplier-controlled stackup or
physical measurement. Run the actual native ERC/DRC too; the model result and native report are separate
evidence. Neither makes a project manufacturing-ready.

The prepare API is `POST /api/workbench/projects/{pid}/buses/prepare` with `base_version`, an action
(`pins`, `component` or `timing`) and its patch. Inspect current groups with `GET .../buses`.
The Agent uses the same guarded engine through `edit_bus_properties`; `inspect_buses` reads existing
evidence and Chat cannot edit. Declared differential pairs also drive the interactive two-net routing
tool below. Automatic Part Type/protocol presets, coordinated multi-lane bus routing, interactive length
tuning, and using polarity metadata to rename native nets remain parity work.

## Physical board construction

Open **Rules → Stackup Editor** or choose **Stackup Editor** in the command menu. The ordered
table edits copper, dielectric sheets, masks and technical overlay/paste rows. Material names,
thickness, relative permittivity, loss tangent, copper roles and optional plane-net assignments
are explicit saved inputs. The through-hole drawing follows the actual copper-row positions.
**Via Hole Configs** changes defaults for new vias; existing individual via dimensions are retained.

Without a declared construction, the table shows a generic preview. Opening or cancelling it
does not save that preview. **Done** prepares a private native candidate, verifies pin groups and
passes the physical stack through KiCad IPC-2581 export. It rechecks current source digests before
saving. Used removed copper layers require explicit mapping or removal; collapsed via endpoints
and incompatible SMD side changes block applying. Review destructive migration and validation
findings before **Apply reviewed changes**. Failed reviews keep the editable form.

**Fit dielectrics** explicitly scales dielectric sheets to the chosen finished thickness while
retaining copper and masks. Typing a target alone does not silently rescale anything. Finished
thickness includes copper, dielectric and masks, following KiCad; technical silk/paste rows have
zero modeled thickness. The published JLC3313/7628 examples calculate1.59468/1.61668mm with the
declared flat mask, rather than being silently fitted to nominal1.6mm. Loss tangent and flat-mask
assumptions remain visible and editable; a supplier name does not approve fabrication.

Download/import construction JSON without saving a design, or give a project preset a name before
Done. Project presets are portable within the saved project library and omit project-specific net
bindings. Source history restores construction, via defaults and presets together. Native files
include a portable `.stackup.json` with the complete recipe, assumptions and the current PCB hash.
KiCad refill omits zero-thickness paste material labels from the active native PCB; those labels
remain in the editable recipe and sidecar. IPC numeric property text has its own rounding.

Outer-layer analytical estimates use the declared foil, dielectric height and adjacent declared
plane. Several dielectric sheets use a series-capacitance approximation. Plane assignment does
not prove connected copper coverage or measured impedance. Unknown legacy constructions do not
borrow a four-layer estimate; length-only bus limits remain available. One-sided boards use an
unused zero-thickness native compatibility slot; fabrication refuses to silently omit real copper
on an undeclared side. Area-specific stackups, flex regions/bending and more template families
remain separate work within the complete software scope.

## Terminals

Add **Terminal** from the Part library, or drag it onto the schematic. It is a real single-pin object:
connect it with the wire tool, name it in Inspect, and choose its module pin number, direction, side,
order, group and section. Multiple terminals can share a net and remain distinct interface pins.
Designator changes update external module-wire anchors. Moving a terminal in the schematic does not
move its PCB pad. In selection mode its pin can be dragged; wire mode connects it electrically.

A new terminal includes a bare circular PCB test pad. Inspect controls its diameter and **Exclude from
PCB** option. The pad has no solder paste and is excluded from assembly BOM/placement files. Excluded
terminals remain in the schematic/netlist, so logical pin counts can exceed physical pad counts. The
module pin number labels/orders the interface; the terminal's individual native test pad uses pin1.
Existing virtual sheet ports can be made editable from Inspect without adding PCB copper by default.

New isolated terminal placeholders can bind an existing net while preserving its routes. Joining two
established nets still requires explicit review. Deleting a terminal removes its single pin/testpad;
named net memberships between other pins remain connected. It is not a disconnect-all command.
Use the net editor or explicit pin disconnection to change those other connections.

The Agent can use `edit_terminal` for the same guarded operations. Chat cannot execute that tool.
Edits use version checks, current native copper capture and normal immutable history; cancellation and
new instructions prevent an obsolete tool edit from being applied. Frozen published module snapshots
remain separate from later instance edits. Group/section metadata affects ordering; richer section
graphics and automatic draft subscriptions remain parity work.

**Copy installed asset** creates an editable copy of a real KiCad symbol or footprint. **Import library**
accepts exported project JSON, `.kicad_sym` and `.kicad_mod` files. Unsupported custom/trapezoidal or
slotted pads produce an import error rather than substituting a different pad. External 3D model
files are not included in these copies/imports. Native exports include `Project.kicad_sym`,
`Project.pretty`, both library tables and a portable `library.json` archive.

Assets live in `design.json` under `library.symbols`, `library.footprints` and `library.parts`.
Components use `Project:AssetId`; project assets never mutate or share the installed global library
cache. Declared footprint heights feed enclosure-clearance context and are labeled `project-library`;
they are user declarations, not measured component models.

## PCB layer views

Open **Layout → Layers** to focus or show/hide the real board layers. The grouped list follows the
native copper stackup and includes top/bottom silkscreen, mask and paste. Expand a copper row for
its fills, polygons, pads, traces and vias. An eye with mixed contents retains those individual
settings. Display controls separately manage airwires, reference labels, zone outlines and the grid.

In the PCB canvas, a copper number focuses that layer; **L**, then a layer key focuses it, and **H**,
then that key toggles visibility. Layer keys are **D** mechanical metadata, **L** labels, **A** airwires,
**Z** polygon/zone outlines, **O** silkscreen, **P** paste, **M** mask, or a copper number. Hold Shift
with O/P/M for the bottom side. **H → F** toggles copper fills. Escape cancels a pending prefix;
typing, dragging, changing projects/canvases or letting the prefix expire cannot apply an old command.

Focusing shows a hidden target and dims other visible layers. Unfocusing keeps the target visible,
as observed in Flux. These operations do not select a routing layer or create a via. Hiding the
active trace layer stops drawing; show its traces before starting or switching routing onto it.
Hidden geometry is excluded from canvas picking and routing targets. Settings are personal to the
browser account and project; they survive reload without saving a design version. Storage failure
is explicitly reported as session-only persistence.

Mask/paste apertures use KiCad's actual SVG plotting rather than an estimated expansion of copper
pads. The plot uses absolute PCB millimeters, a frozen PCB/project/rule bundle, and a temporary
view filter for personally hidden native objects. The saved CAD files stay unchanged. Geometry,
input-bundle, visibility and downloaded SVG hashes bind the overlay to the current view. External
references, active SVG content and unsupported vector constructs are rejected. A mismatching or
failed plot shows an error and a retry action. These display plots do not establish fabrication
acceptance or replace native Gerber outputs and physical validation.

Completed layer data waits while a gesture owns the canvas and resumes after the gesture or window
focus returns, provided the same project/source is still active. Markup currently freezes pixels;
its semantic layer-state context remains separate parity work, so colors alone should not be treated
as proof that a visible pad is a mask/paste opening.

## Schematic component hotkeys

Select one component and press **Shift+1–5** to save it to a component hotkey. Press **1–5** to
preview that part using actual native symbol geometry, move the pointer, then click to place it on
the10-unit schematic grid. Escape cancels; Space cancels and continues with normal canvas panning.
Assigning or previewing does not save a design change. One Undo removes the complete insertion.
The component context menu also exposes the five assignment slots, and the shortcut viewer lists
assignment and insertion separately from saved viewport positions6–9.

Hotkeys save a snapshot of one electrical part, including its units, relative positions, rotations,
mirrors and required project symbol/footprint assets. Insertion allocates a new reference on the
current sheet. Original nets, physical placement, locks and module ownership are omitted. Ordinary
pins start unconnected; a terminal receives its own placeholder net. The new PCB footprint starts
at the board center and can be arranged in Layout. A same-name destination library asset with
different geometry is rejected, so rename conflicting assets before inserting.

Slots are local to the current browser account and reusable across projects. Reload preserves them;
clearing browser storage removes them. If storage is unavailable, the notification explicitly says
the assignment lasts for this session. Native previews are canceled on project/sheet/view/source
changes and when another pointer gesture starts while a request waits. Typing, modal dialogs,
drawing, markup, dragging and panning keep their existing ownership. Empty projects retain an
interactive canvas so a saved hotkey can place the first component. Whole hierarchical modules
are separate from these single-part templates.

## Schematic wire junctions and disconnection

Enable **Connect pins (W)**, then click a pin and an existing wire, or start at a wire and finish at a pin.
Two existing wires can also be joined. Different saved nets require explicit merge confirmation.
The connection keeps an attachment to its parent route, and the junction follows that route when symbols
or wire paths change. New junctions and automatically routed detours use KiCad's 1.27 mm connection grid;
explicitly supplied off-grid symbol/bend coordinates can still produce raw ERC warnings.

Different-net wires may cross through their interiors without a junction dot. Endpoints, bends,
collinear overlaps and foreign pins are not treated as independent crossings. Routing prefers short
clear detours and validates compressed final polylines before exporting native geometry. Same-net
branches retain their junctions. At an overlapping hit area, the foreground wire receives the click;
choose a clear point on the intended wire when starting a merge or branch.

Native generation19 reports `schematic_routing` counts for the saved explicit guides and preserves
earlier generation directories. These counts do not imply that every logical net has an explicit
wire. A geometrically unsafe path still shows a warning; exceeding the retained90,000-point search
budget is reported separately, with guidance to simplify or split the schematic sheet.
Native totals include saved guides whose anchors are unavailable together on a page; these are
reported separately instead of disappearing from the count. Hierarchical label stubs participate in
the same foreign-net contact checks before explicit wires are routed. Native bend lists share the
editor's100-waypoint limit.

Exact paths are retained when their endpoints still match the pins. Moving an anchor can make a
saved exact span stale; the existing fallback recomputes it and reports `fixed_path:false`. This is
not an absolute geometry lock. Parametric-symbol edits expose released exact paths in their review.

Select a wire to inspect its endpoints. **Disconnect R3.1**, for example, removes that pin from its saved
electrical net and clears the affected drawing branches/copper. **Remove drawing** removes graphics;
named net labels continue to connect their members. Delete opens these choices instead of silently
claiming that erasing a line broke a labeled connection. Segment-level cuts remain a separate parity task.

Wire route IDs and `from_join`/`to_join` metadata live under `editor.connection_guides`. Each join names
a parent route and a normalized offset. The emitted point also snaps along the parent to the connection
grid, so it can differ slightly from an exact fractional midpoint. Dependencies must exist and be acyclic.
Removing components/net memberships prunes orphaned joins; copying symbols remaps IDs for their copied
wire graph. Native wire/junction geometry is checked separately from the KiCad-exported electrical pin groups.

The connection-grid default follows the [KiCad schematic grid documentation](https://docs.kicad.org/10.0/zh/eeschema/eeschema.html).
Routing clearance and electrical connection-grid pitch are distinct values. Raw ERC reports remain available;
the software does not equate a filtered-clean report with a warning-free native export.

## Selection rotation, mirrors and board sides

Select components with Shift-click, a selection rectangle or the Objects list. The shortcuts follow
the [Flux transform reference](https://docs.flux.ai/Introduction/pcb-editor-shortcuts):

| Action | Shortcut |
|---|---|
| Rotate the selection clockwise / counterclockwise | `]` / `[` |
| Rotate each selected object around its own origin | `Shift+]` / `Shift+[` |
| Mirror horizontally / vertically in Schematic | `F` / `Shift+F` |
| Flip each selected footprint to the other board side | `F` in Layout |
| Frame the selection or design | `0` |

During active wire/PCB routing, `F` still changes the routing elbow. Inspector and context-menu controls
provide the same transforms; `R` remains a clockwise-rotation alias. Individual rotation uses each
object's own origin. A single-object group uses its origin too; larger groups use native component
bounds excluding text (PCB courtyard bounds when available). The schematic group pivot snaps to
10 editor units. Inspector's **Rotation pivot** accepts a shared custom pivot in schematic units or
PCB millimetres; individual mode uses own origins instead of that shared pivot.

Schematic transforms emit real KiCad symbol rotation/mirror properties. Mirroring acts on world axes
after rotation; browser glyphs, pin hit targets and native wires use the same convention. Closed internal
wire geometry, free nodes and attached net/power annotations move with the selected units. Power/ground
graphics retain their native mirror too. Boundary wires reattach to actual pins. Native pin-group parity
and the preserved internal wire paths are checked before saving. Multi-unit keys remain distinct, and
copy/paste, rename, deletion, module capture and module revision updates retain mirror metadata. Automatic pin-net callouts follow the transformed pin direction and choose clearance from nearby native wires and property text; these display offsets do not change the electrical design or PCB.

In Layout, unlocked selected footprints rotate as a group. Copper on nets whose physical pads all belong
to that movable group rotates with it: track/arc points, via geometry, zone source contours and holes
retain their identity and rules; zones are refilled. Locked footprints stay fixed and do not determine the
movable group's pivot. A board-side flip acts on each footprint at its own origin. Copper is retained
where supported pad geometry and copper-layer access remain unchanged, including unchanged through pads.

If a transform needs boundary/side-change copper cleared for rerouting, a **Review selection transform**
dialog lists the actual object IDs, nets, types and layers. Switch **Original / Proposed** to inspect the
native geometry. **Cancel** and Escape preserve the saved design; **Apply transform** saves the complete
change once. The list is explicitly truncated above 1000 affected objects while retaining the full count.
Proposal DRC findings are shown, and saved project checks remain separate. This is not a manufacturing
approval or a field solver for complex pad geometries.

Queued real keypresses apply in order. Undo/redo restores the whole operation, including copper changes.
An external save, a canceled in-flight request or a changed project/selection cannot apply an older
proposal. The prepare API is `POST /api/workbench/projects/{pid}/transforms/prepare`; it does not save.
Agent tool `transform_selection` shares that engine and version guard. It returns a concrete impact
review before removing copper unless the listed clearing was explicitly authorized with `confirm_clear`.
Chat cannot execute this mutating tool. General wire/label/module-boundary multiselection remains
separate parity work.

## Editing existing PCB copper

Click a track, arc or via in Layout to open its properties. Change trace width/layer or via diameter/drill,
edit vertex coordinates, or drag the square handles. Dragging a segment moves the segment and its
attached same-net vertices. Moving a via retains attached copper across its layer span. Pads keep their
placement; native DRC and airwires expose any connection that was intentionally detached from a pad.
**Add midpoint** splits a straight segment; **Delete segment** removes only the chosen object. Changes
use the project's autosave, undo and version history.

Both generated and hand-routed copper can be edited. Native copper UUIDs survive regeneration.
Whole native zone definitions, including polygon boundaries, priorities, pad connections and thermal
settings, stay in the project. KiCad refills these zones after an edit; stale filled shapes are discarded.
Net renames update the preserved zones, and removing the last connection to a net removes its zones.
The saved design uses `fixed_copper` and `fixed_zones`; none of these edits assert manufacturing readiness.

To draw continuously, click a pad's white terminal, or arm **Route trace** and choose a pad, via or
straight trace. Click the board to place corners. **F** changes elbow orientation, **W / Shift+W**
cycles width, and holding **Shift** permits a free-angle leg. **V** places a through via at the pointer
and continues on the next layer. The active route also offers layer/width controls; changing its layer
inserts or reuses a via. Click a same-net pad, via or trace to finish; **Esc** ends drawing while keeping
the already placed copper. **Backspace** or Undo restores the previous vertex/layer state.

Each placed leg uses the normal autosave/history flow. Optimistic geometry keeps the active routing
tool usable while native files regenerate; other edits still wait for the current native layout.
Different-net endpoints are rejected and leave the current route active. While drawing, traces on other
copper layers do not attract the active-layer endpoint. **Walkaround** is the default obstacle
behavior. It plans around foreign copper, holes, native keepouts and board edges. Hidden objects
remain obstacles. Unsupported copper glyphs or pad shapes produce an explicit limitation.

The planner checks shorter detours while preserving the route endpoints and discovered branch
contacts. If optional shortening reaches its work limit, an already validated route can still be used.
This improves unnecessary detours without guaranteeing a globally shortest path.

Choose **Shove unprotected** to preview moving permitted straight copper. The orange ghost shows
displacement and the status names affected nets; hovering does not save. Clicking saves the new
route and displaced copper together, and Backspace/Undo restores both. Protected objects, existing
pad/via positions and discovered branch contacts stay fixed. A failed shove can walk around instead;
a blocked or budget-exhausted action leaves the saved design unchanged. Native DRC remains authoritative.

Layer changes check the via's complete copper span and hole spacing. An existing plated through pad
can provide the transition without another hole. Unknown or advanced native rules and large/custom
geometry remain limits of the interactive model; an accepted preview is not manufacturing proof.

Starting on a declared differential-pair pad routes both nets together. Pair identity comes from
terminal Bus Group/Pair metadata or explicit differential impedance groups; ambiguous partners or
physical pads must be resolved rather than guessed. The status shows the partner, layer, width and
nominal edge-to-edge gap. Pad/via fanouts meet board clearance and may relax that nominal spacing.
The initial nominal width/gap can use the declared impedance target;
they remain approximate geometry settings rather than a measured impedance guarantee.

The two legs share a centre guide with coherent corners and pad fanout. **V** places two separated
through vias, or reuses compatible existing vias while retaining their identities and spans. A pair
finishes on its declared corresponding pad endpoints. Hold **Ctrl / Cmd** to route the primary net
alone; releasing it resumes the pair when both physical endpoints support the active layer. A parked
partner on another layer requires a compatible reconnection. Each pair vertex or via placement is one
saved operation, so Undo/Redo restores both legs together. Preview and commit use the same geometry;
protected unrelated copper is preserved. Pair centreline planning also avoids obstacles and validates
the actual fanouts. Broader recursive shove, arbitrary topology and advanced route editing remain
further work, and native DRC is still required.

For an existing routed signal, ask the Agent to tune a net to a length, match a reference net, or use
an explicit modeled-delay target. For example: “Tune CLK to55mm within0.05mm” or “Match DATA1 to
DATA0 within0.1mm.” Selecting both members of a declared differential pair keeps their meanders
coupled; selecting only the short leg performs an independent length correction. These are geometric
edits, not a signal-integrity measurement.

The Layout Inspector also offers **Tune length…** on a selected copper object or net. Choose an
absolute length, reference net or modeled delay; choose trombone, accordion or sawtooth meanders.
Optional radius, pitch, cell count, amplitude and side settings constrain the search. **Review routing**
builds the actual native PCB, displays the two-net/pin proof and DRC, and remeasures the result.
Review and Cancel do not save the circuit. Changing any setting invalidates its preview. **Apply tuning**
uses one source transaction and one complete Undo/Redo entry; a changed native PCB, project, account,
source version or render input cannot apply an older review.

Normal copper pours retain their rules and boundaries and are refilled around the new trace. Track
keepouts remain obstacles. Tuning currently adds length to a simple connected two-physical-pad path;
incomplete, branched, pad-shorted or unsupported paths report an explicit reason. A bounded search
failure does not prove that no possible route exists. Shortening and broader topology editing remain
further work. Existing native findings remain visible; any additional raw error or unconnected item,
including worsened constraint detail or repeated findings, blocks application.

Lengths follow the trace centreline outside endpoint copper pads, including real circular arcs and
excluding via barrel length. Delay targets require explicit propagation data for routed layers and
supported vias; unspecified package delays are zero by convention. The millimeter tolerance also
determines the corresponding delay range. No interface name invents a propagation constant.

These contextual controls follow the [official Flux PCB shortcut reference](https://docs.flux.ai/Introduction/pcb-editor-shortcuts).
Remaining general shortcut parity is recorded in the parity register; the implemented shortcuts
are searchable in the shortcut viewer.

The routed USB-C acceptance corpus exercises an actual JavaScript copper edit, native KiCad rebuild and
DRC: 28 segments, one via, two pours, no native errors/unconnected items after the edit. This validates
the software flow, not assembled hardware or all routing/clearance cases.

Version comparison covers the complete saved design, including copper, zone definitions and library assets.
It reports changed JSON paths, unchanged sections, snapshot hashes and whether the returned changes or
values were truncated. The local Codex reviewer can use the read-only `design_history` tool to list or compare
saved versions. Its prompt asks for that evidence before claiming an edit preserved the other design data.
For disconnect/undo/restore sequences, it also asks for the relevant adjacent versions; a first-to-last
comparison cannot establish intermediate saved states.
Unavailable snapshots remain unknown; a successful ERC/DRC run alone is not proof that only the requested
field changed.

Design history distinguishes numeric formatting from design changes. The versioned
`safe-json-number-v1` policy treats finite integral floats inside ±(2^53−1), including −0.0,
as equivalent integers. It does not round fractions, coerce booleans/strings, reorder arrays or
merge integer/float representations above that range. `field_changes` and semantic fingerprints
use this policy; `representation_changes` lists numeric-only differences. The activity dialog
shows both counts and the compared versions, and discards late results after a project switch.
Original serialized-spec hashes and exact stored snapshot byte hashes remain separate evidence.
No history files or production audit/idempotency hashes are normalized or rewritten.

Current native KiCad/schematic caches, saved check freshness, native file status and production
native-source lookup use the same versioned design identity. An explicit numeric-only save still
creates a saved version; a numerically equivalent Agent full-design proposal is a no-op. Real edits
invalidate these caches. Existing exact-match native metadata may gain semantic fields without
rewriting outputs. Unknown policies retain exact legacy matching. Catalog paging still binds the
saved version and typed source to prevent mixing pages across a save. Supplier quote/stock
fingerprints and immutable audit/package digests retain their existing strict contracts.

Native cache hits recheck the current design under the project lock immediately before returning.
Native checks capture their source design before ERC/DRC, compute their report identity from that
snapshot, then recheck the current identity and PCB bytes while atomically saving the report.
A concurrent real edit makes an obsolete result return409; expensive engineering work runs outside
the save lock. Deterministic interleaving tests cover both fast-cache and check-publication windows.

The Design checks panel owns each request by project, project-load token, saved version, edit
generation and its actual panel controls. Late generic/native successes and failures are discarded
after switching projects, editing or replacing the panel. Old completion handlers cannot unlock a
newer request. Completed findings and the toolbar count become stale on local edits, Undo, source
replacement, history restore or applied external updates. Current failures show a readable error and
allow retry. Successful results identify their saved version and retain warnings/filtered findings.
DRC details include ordinary errors, unconnected items and warnings; warning counts are not a
substitute for the warning list. UI-only response injection covers that rendering branch separately
from the real native engineering fixtures.

Generic checks capture the spec and `version` together under the project lock. Native check reports
expose `source_version` (start snapshot) and `design_version` (locked successful commit). These can
differ after a semantically equivalent numeric-only save; they are not native producer/parser schemas.
The panel requires its captured saved version to match both stages before showing current findings.
Versioned asset URLs identify the frontend document: after updating the server, fully reload the
browser before acceptance; changing only a project hash retains the old JavaScript document.

## Draw on the canvas and ask AI

Open Schematic, Layout or3D, frame the area of interest, then choose the pen beside the composer.
In a narrow composer, open More → Markup. Draw over the frozen viewport and type what the mark
means. On mobile, Ask AI returns to the composer. Send submits one marked PNG with the message;
an accepted matching send clears it. Escape, view/project changes, source changes and canvas resizing
exit markup. Camera controls and electrical editing gestures over the canvas pause while drawing.
Marks themselves never change the saved design. New text/strokes entered during a send are retained.

Each reference belongs to one project and saved version. PNG bytes, dimensions and SHA are checked;
stale, foreign or modified references are rejected. The generated image and metadata live under
`references/canvas`, protected from text-editor and model file writes. Images are pixel references,
not dimensional measurements, copper or connectivity proof. A later Agent edit can make a legitimately
accepted frame historical; its original version label is retained. Use Chat for inspection only;
mutating tools/proposals are blocked server-side. Agent permits requested engineering changes.

PCB markup also freezes the displayed layer state at capture time: focus, visible native layers,
copper features, global filters, personally hidden native objects, and mask/paste loading status.
Ready apertures retain their SVG and visibility identities, checked against an existing export from
the same PCB/input bundle. Layer context is saved with the image and included in CLI manifests,
history and provider image labels. Sending later uses that frozen record; a subsequent layer switch
or completed export cannot make an earlier loading aperture known. Retry IDs cannot relabel the
same PNG with different layers. Older images remain readable and explicitly lack layer context.
This is client display evidence; overlapping layers can still be ambiguous and it does not replace
connectivity or ERC/DRC. Context is bounded to24KB and256 personally hidden native objects per image.
Legacy context records using `path_count` remain readable without rewriting their bytes or digest;
both that field and `client_path_count` describe a client drawable count, not native object cardinality.
Keep drawing until the stroke is complete before sending. Chat submission prevents native form
navigation synchronously, including Enter. Image flags are terminated before the stdin prompt token.

The local Codex CLI receives actual verified staged PNG files via`--image`; provider adapters use
real image blocks. The latest five marked images remain available to the ephemeral CLI conversation.
Capture resolution respects display DPR up to a2048px long edge. Image input disabled or unsupported
must report failure rather than claim visual inspection. Real model acceptance here uses the signed-in
local Codex; other adapters have automated payload/permission tests, without live cloud-key calls.

Failed transport retries retain their image/request identifiers. Replayed accepted requests do not
start duplicate jobs. Interrupted pending receipts fail closed and require checking the conversation
before an explicit new send; jobs are not automatically resumed after a process crash. Composer drafts
and pending submissions stay with their project. A cancelled reference cannot silently become a
text-only request. The reference workflow follows the [official Flux Markup reference](https://docs.flux.ai/reference/markup-mode);
exact writable-state pixel parity remains unverified.

## 3D display and navigation

Open View in3D, or use the bottom camera toolbar button, to access the same contextual pane. Camera controls
provide Blueprint, X-ray, Solid and Realistic materials with perspective or orthographic projection.
Top/Bottom3D models affect matched component bodies; unassigned STEP bodies stay visible with a note.
Grid and Keyboard shortcut bar are personal settings; hiding shortcuts keeps Frame model available.
These options do not save a circuit version or rewrite CAD exports.

Drag to orbit, including below the board; Shift-drag, middle-drag or the Pan tool translates the view.
Scroll to zoom. Preferences and session camera positions belong to the browser account/project.
If the rendering engine changes, pan resets because GPU world vectors and software screen offsets
have different meanings. The software renderer disables unsupported GPU controls explicitly.

The orientation cube at upper right follows the model camera. Click a face, edge band or corner to
choose one of26standard directions. Ring arrows orbit; the curved arrows roll the view90degrees.
Home restores the top/left/back isometric view and framing. Turn view around makes a horizontal
half-turn, retaining the top or bottom hemisphere. Frame model resets pan/zoom and retains the chosen
direction and roll. Standard face labels refer to the model axes.

The circular camera button below the cube opens material and projection shortcuts linked to View.
On narrow screens, use Show/Hide view cube; camera options also reveals the cube. With a cube face
focused, arrow keys orbit. Home works from any navigation control; Enter/Space activate buttons.
Space release stays with the press that started it, including focus changes. Navigation pauses
during Markup. Camera poses remain session settings per account/project, not saved circuit edits.

Select an axis under Section and move Section position to clip the loaded CAD geometry; the output
shows model millimeters. Measure distance uses two picked points in assembled model coordinates.
Measurement closes and locks explosion until it is turned off. Replacing geometry, changing visible
bodies or changing clipping clears old measurement feedback. Board mode hides enclosure geometry;
Assembly controls retain personal base/lid visibility for the enclosure view. Clipping has no cap
surfaces, and model distances are separate from physical measurements.

## Schematic display

Open View in Schematic to toggle All pin labels, Comments, Multiplayer cursors and Keyboard shortcut
bar. Settings belong to the current browser account and project. They change presentation without
saving a design version or moving the camera. All pin labels reveals known labels suppressed by
native symbol styling; electrically hidden pins remain hidden. It becomes available after the native
schematic loads. Shift+P toggles pin labels; Shift+C toggles comment markers; Cmd/Ctrl+Shift+Backslash
toggles collaborator cursors. Typing, dialogs and active canvas gestures retain their own keys.

Hiding the optional toolbar keeps Frame model available. Comment/cursor visibility does not stop
synchronization. Unsent comment drafts clear when project, account or project-load ownership changes.
Failed comment reads offer Retry comments; comment requests stop waiting after30 seconds. A timed-out
write may already have reached the server, so check the thread before sending again.

## Arrange parts and save views

Editor tool panes can stay open together. Objects remains above View; opening another tool preserves
the existing pane's search and controls. Each header and toolbar button closes only its own pane.
Drag the divider to change proportions, or focus it and use ArrowUp/ArrowDown for16px steps.
Home/End move to the constrained ends. Escape during a drag restores its original proportions;
Escape otherwise closes the dock. Proportions are personal browser settings scoped to account and
project. Project changes close the dock; ordinary editor-view changes retain panes and refresh their
contents. Files, Library editor and Symbol transitions close it. These actions never save CAD edits.
Extremely edited storage ratios are bounded on load rather than preserved as arbitrary numeric data.

Select components or symbol units, then use **Align** in the Inspector or the canvas context menu.
Six edge/center commands use native symbol outlines and pins, excluding text. PCB alignment uses
courtyard graphics, with pad/origin fallbacks. **Align using → Object origins** selects anchor-based
alignment instead. Spacing fixes the two spatial end objects and gives equal gaps between their
bounds; schematic `S` chooses the main axis. PCB `Alt+Shift+H/V` spaces horizontally/vertically.
Bounds follow geometric outlines/pin segments and exclude stroke thickness. Spacing orders objects
by their centers; overlapping or nested bounds can require review.

`Alt+A/D/H` aligns left/right/horizontal center; `Alt+W/S/V` aligns top/bottom/vertical center.
Arrow keys nudge a selection; Shift makes the step ten times smaller. Schematic steps are10/1 editor
units, distinct from physical PCB millimeters. PCB steps follow the current grid. With no selection,
arrows pan the view. Repeated translation keys are combined before native checking, and Undo cancels
queued movement. Inputs, dialogs, drawing/markup gestures and mixed object selections retain their
own controls.

Transforms compile temporary native previews and verify pin/net membership. Rigid wire paths follow
the selection; copper with one shared displacement retains its native object IDs. Different
endpoint/pad displacements may require rerouting.
Locked PCB parts stay fixed. Review shows affected copper, custom wire paths, bounds outside the
board and proposed native DRC findings before applying changes that need confirmation. The AI
`transform_selection` tool also accepts `preview_only:true` and uses the same layout DRC review gate.
These checks are software/CAD checks; a valid netlist or PCB DRC result does not prove every explicit
schematic wire guide routed. Existing unroutable-guide warnings remain visible.

In Schematic, `Shift+6–9` stores the current camera and `6–9` recalls it. Slots belong to this browser,
project and schematic sheet and survive reload when browser storage is available. They do not create
design versions or change design Undo/Redo. If storage is unavailable, the notification explains that
the view is saved only for the current session. These controls require a loaded native schematic.
Sheet changes invalidate pending arrangements, including leaving and returning to the same sheet.
Viewport shortcuts are suspended during an active canvas gesture or drawing/markup operation.
Component insertion slots1–5 use separate templates and storage, as described above.

## Review and undo an AI design edit

After an AI request changes saved design versions, its chat card offers Review changes. The history
window shows the exact saved before/after versions, readable field values and a read-only native
schematic preview. Before/After switches snapshots; the preview never edits the live design. Long
values and bounded comparisons explicitly identify truncation. The evidence section retains raw
and semantic hashes. Opening history first saves any existing local design draft.

An AI request initiated in this browser tab can enter its own design undo chain. Several consecutive
saved steps from the same request are grouped, preserving earlier local undo history. Use Undo design
on its current card, or the normal Undo/Redo shortcuts. Unknown requests, collaborator edits, missing
version/snapshot evidence and mixed project-file changes conservatively invalidate automatic design
undo. Returning to a recently visited project can retain this tab's attributable history; reloading
the document or exceeding the bounded tab cache does not guarantee session undo preservation.

This shortcut is design undo, covering the saved circuit/board/presentation specification. A request
that also changes project text files offers a separate **Review all changes** card. Open it to inspect
each file's additions/removals, the saved design field changes and complete before/after file snapshots.
The review marks long-diff truncation, encoding display replacements and line-ending changes.

For structured text files returned by the local Codex Agent, **Undo all changes** restores the saved
design and listed original file bytes, removing files the request created. **Redo all changes** reapplies
that saved result. Consecutive turns of the same request retain the original baseline. File-only
operations keep the circuit design version; design changes save a new version. Unrelated files stay
at their current contents. Generated CAD/cache/tool outputs are outside this file restore operation.

Restore requires the current saved design/version and every listed file to match the reviewed state.
A newer edit, active run, missing/tampered snapshot or unsaved local draft blocks the operation with
an explanation. Refresh reloads its eligibility; it does not overwrite newer work. In-process write
failure rollback is covered by tests; process crashes, permanent I/O failure and multiple server
processes do not have a transactional durability guarantee. Other provider/legacy output paths do not
yet create these structured file-change sets.

Restoring a saved design through ordinary project history leaves project text files at their current contents.
The feature does not attribute legacy revision-only mutations that never save a workbench version.
Origin IDs distinguish client actions and are not an authentication mechanism; normal project
permissions and version guards still apply.

## Verification

```sh
.venv/bin/python -m pytest -q tests
npm ci
npm test
npx playwright install chromium
npm run test:browser
# Also exercise real FreeCAD/STEP generation (requires FreeCAD):
npm run test:browser -- --mechanical
# Build/install the Python wheel and smoke an isolated server with the current runtime dependencies:
.venv/bin/python scripts/verify-package.py
```

Native browser checks require KiCad and its libraries. The runner uses isolated local servers
on free ports, fresh browser contexts, and a recorded supplier response for BOM rendering. It never calls
AI or modifies the working workspace. Reports/screenshots go under `test-results/browser-checks-*`;
failed isolated workspaces remain under `.local/browser-checks-*`. Run one suite with
`npm run test:browser -- --suite=schematic`, or use `--headed` to see the browser.

The suites use the [Playwright library](https://playwright.dev/docs/library) so the same test functions can
also run through the desktop browser tool. Review `docs/FLUX_PARITY.md` for implemented flows and remaining gaps.

The packaging check copies source into a temporary build directory, builds a wheel with isolated build
dependencies, installs it outside the checkout, and checks its CLI server, empty project list, example API
and versioned assets. It explicitly sets both a temporary config location and project directory, then
stops its own server. It reuses the current virtualenv's runtime dependencies; it does not certify a fresh
dependency installation or bundle KiCad/FreeCAD/ngspice. The receipt and wheel live under
`test-results/selfhost-package-*`.

### Physical pad properties in Layout

Select a physical pad in Objects or with Command/Ctrl-click on the Layout canvas, then choose
**Edit pad properties**. Geometry changes apply to that component instance. Board X/Y and rotation
use the board frame even for rotated bottom components. Width/height, hole/slot/offset, connected
copper layers and local mask/paste/clearance/thermal rules have a private draft. Blank local rules
inherit. **Review pad** checks the actual native candidate and displays baseline/candidate findings;
**Apply** saves through source Undo/Redo. Cancel does not save. A peer save retains the entered
values and invalidates old approval. Reset restores a matching shared-footprint pad.

Selective plated annuli use a native per-layer stack. Skipped layers have only the drilled profile;
intentional native zero-annulus warnings remain for review. Automatic routing completeness for
these stacks/barrel contacts is unavailable. When the shared source pad changes, old override
identities are rejected. Use the design source editor to remove the affected keyed override before
regenerating; a dialog for orphan recovery remains future work. See [the decision](decisions/0038-layout-pad-instances.md).

### Physical pad instance properties

In Layout, select an individual pad through Objects or Control/Command-click, then choose
**Edit pad properties**. Width, height, board coordinates/rotation, pad type/shape, drilled slot
size/offset, copper layers and local mask/paste/clearance/thermal rules affect only that physical
pad. Leave a local rule blank to inherit it. **Review pad** checks a private native candidate with
the existing routes; inspect the findings before **Apply**. Cancel saves nothing. Undo/Redo restores
the entire source edit. A peer save preserves your inputs and requires a new review.

**Reset this pad** restores a matching base footprint. If the shared source pad was changed and its
identity no longer matches, the override is rejected explicitly. Until a dedicated orphan-recovery
panel is available, remove only its keyed `pad_overrides` entry in the design source and regenerate.
For a plated pad with skipped annular layers, native zero-annulus warnings remain visible; automatic
barrel-contact routing proof is unavailable. Use the actual native findings and manual review.

Chat can use `inspect_layout_pad` without generating files; Agent `edit_layout_pad` uses the same
private review, stale-source guards and explicit findings acceptance. See
[the design decision](decisions/0038-layout-pad-instances.md) for the native model and limits.
