# Reviewed physical pad instances in Layout

The Layout Inspector could select a native pad but could only display its dimensions. Editing
the shared footprint changed every component using it. A physical pad needs its own reviewed
dimensions, board position/rotation, hole and local manufacturing rules.

Store instance overrides on the component, keyed by a source-pad digest and duplicate ordinal.
The key excludes the reference, net and UUID, while the emitted pad keeps its original deterministic
UUID and electrical number. Duplicate-numbered pads remain distinct. Placement changes and cloned
references preserve the override; a changed source pad fails explicitly instead of rebinding to
another physical pad. Reset removes a matching override. An orphan can currently be recovered by
explicitly removing its keyed `pad_overrides` entry in the design source, then regenerating; the
pad dialog cannot reset a source identity that no longer exists. A richer recovery UI remains work.

Read the actual native pad, undo the component rotation/flip, and store the edited native snapshot
in the footprint's top frame. Board coordinates and global rotation work for rotated bottom-side
components. Preserve unrelated pad properties, named nets, other pads, shared libraries, current
tracks/arcs/vias/zones and their protection flags. Review copies the entire native directory before
running baseline DRC, then privately builds the candidate schematic/PCB, checks pin parity, plots it
and reports native findings. Apply rechecks source, PCB and render-input hashes through the shared
source saving/Undo slot. Cancel, pending responses, changed inputs, peer saves, project/view/owner
changes and read-only access cannot apply an obsolete candidate.

Physical connected layers need more than a `layers` list. The installed KiCad10 still plots the
full PTH annulus on omitted drill-span layers. Use a custom native pad stack with drill-sized
circular/oval profiles on skipped layers: outside the drilled opening there is no annulus. Retain
KiCad's intentional zero-annulus warnings in review; do not weaken design rules. Actual SVG pixels
and Gerber apertures after a real refill verify selected versus skipped layers. The Canvas keeps
the mechanical hole visible when its copper is hidden. Automatic proof for per-layer pad stacks
and plated barrel contact remains explicitly unknown and is rejected; manual/native review remains
available. Arbitrary native stacks are preserved and cannot be flattened by geometry editing.

Stackup changes inventory explicit instance annuli, require mappings for removed layers and rebuild
their skipped-layer profiles. Saved source validation rejects inactive copper layers. A conditional
native instance policy rebuilds previously ignored overrides in a new directory, preserving older
native bytes and nanosecond mtimes. Chat can inspect a native pad without generating anything;
Agent editing shares private review and requires explicit acceptance of remaining native findings.

Accepted engineering scope: current1272Python tests (one existing socket-thread warning),310Node,
58affected native tests and12affected browser checks pass. A previous full721browser/116suite
batch preceded the final Python-only authored-source fixes; affected12 reran after each correction.
The installed native wheel now explicitly checks authored-zone preservation after native refill.

Actual in-app Codex performed two instance edits, identified strict-source isolation failure, and
later reviewed the source correction, current native checks, history and host evidence. Three
byte-exact reports remain saved. The source comparer preserves unchanged placement defaults and
Cu/zone representation; its private baseline mirrors the native refill/save process. Real native
external changes remain adopted. The first failed report/history is not rewritten; HOST manually
removed redundant current source fields atv4 after proving equal native geometry. MainGUI edit5,
Undo6/Redo7/Undo8 restored exactv4; source8 differs from initial1 only by U1's two pad overrides.

Complete-copy SVG/Gerber/Excellon/netlist/DRC prove six tracks,2nets4pins and the offset plated slot.
Actual native mask/copper samples verify the declared0.1mm mask rim at selected points. Current
DRC0/0/0; ERCraw0errors retains2filtered library warnings. Receipt:`test-results/layout-pads-acceptance.json`.
Main package matches124Python/109web/106statics using existing dependencies; clean OS is unverified.

Full Flux software parity stays open. Dedicated orphan recovery, richer stacks and automated barrel
contact proof remain work. Files390 floating Project dock overlap is tracked under UI-02. No watch work.
