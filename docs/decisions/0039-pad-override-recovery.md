# Recover invalid physical pad overrides without editing JSON

Status: proposed; PAD-02 in the current gap checklist. This is not an implemented feature.

Changing a shared footprint can invalidate the digest/ordinal keys of saved physical-pad overrides.
The current native builder rejects these keys instead of binding them to a different pad. This is
correct for duplicate pad numbers, but the regular pad dialog cannot select a native UUID that the
new footprint no longer generates. Recovery currently requires explicit source editing.

Add a read-only override inventory reachable from the component Inspector and Layout generation
error. It must remain usable when current native generation fails. List component/ref, source
footprint, key, physical pad number and original snapshot dimensions, and classify each entry as
matching, orphaned or unavailable. Do not write/generate files merely to inspect the inventory.
Never rebind by the electrical pad number.

A recovery dialog stages explicit key removals, with a batch selection for multiple components.
Show only selected source changes. Clearing an override restores the current shared footprint;
it does not edit the library, connectivity or unrelated source metadata. When other orphan keys
would still block a native candidate, report those keys and let the user select them explicitly.
Do not silently clear other components' overrides.

Review builds the candidate schematic/PCB privately and checks native pin groups, SVG and DRC.
Current native geometry may be unavailable precisely because the source is invalid. If the only
available native snapshot belongs to an older source, label it as an older comparison baseline;
do not adopt its copper or placements into the current source. If no baseline exists, report
unavailable baseline rather than fabricating zero findings. Apply requires explicit acknowledgement
of this comparison limitation in addition to retained native findings. Candidate generation must
succeed before applying a native-reviewed reset; unrelated invalid footprint/library problems
remain explicit prerequisites to repair.

Acceptance always compares the current source version/identity. Bind the available native snapshot
hash/render inputs as well when it exists. A stale or absent baseline needs its own explicit token
contract; the ordinary route-review token must not falsely imply native/source equivalence.
Use the shared source save and Undo slot. Old native/history files remain immutable. Project/view/
account/role changes, peer source changes, pending Cancel and input revisions invalidate approval.

Agent tools should share the same inventory/review/apply backend. Chat may inspect without native
side effects. Agent reset previews remain private; baseline limitations and remaining native findings
require explicit requested acceptance. Active engine/Agent conflicts must reject competing writes.

Required behavior tests before implementation:

- Duplicate-numbered pads: invalidate one source key; list/reset the exact key only.
- An orphan blocks native generation, yet the inventory and recovery dialog remain usable.
- A reset preserves exact unrelated source, current fixed copper, other overrides and shared assets.
- Multiple remaining orphans are explained and never silently deleted.
- Older/unavailable baselines are represented honestly, never adopted as current placements/copper.
- Native pin parity/DRC and source/native CAS precede Apply; private preview and Cancel save nothing.
- Source/history/native bytes and nanosecond mtimes survive reset, Undo, Redo and reload.
- Viewer access, stale keys, stale version, changed native inputs, pending Cancel/project switch and
  a peer save cannot apply an obsolete proposal.

This task follows the physical pad instance checkpoint. It does not close full Flux functionality,
pixel parity, self-hosting durability or the deferred product/watch work.
