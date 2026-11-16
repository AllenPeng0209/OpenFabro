# Interactive differential-pair routing

Flux's official layout tutorial starts two traces for a declared differential pair and uses Ctrl/Cmd
to switch pair/single routing. Implement this documented workflow through the existing saved-spec,
native geometry, continuous routing and Undo model. Preserve physical pad IDs and unrelated copper.

Resolve pair identity from existing terminal Bus Group/Pair declarations and manual differential
impedance groups. Return source-bound hints with layout geometry; do not infer polarity from names or
silently select an ambiguous pad/partner. Routing remains geometric: nominal IPC dimensions and an
impedance target do not establish signal-integrity or manufacturing acceptance.

Use one centre guide and two offset paths. Compute coherent mitered corners, pad fanout and paired
through-via transitions; preserve older widths/sections and stable generated copper identities as
the guide grows. Preview and commit must use the same path calculation. Enforce explicit positive
width/gap and pair separation, expose constraints clearly, and retain authoritative native DRC.
No push/shove or general obstacle-routing claim is made by adding simultaneous pair geometry.

The default pair mode and temporary single override must stay scoped to the actual route, project,
account/load and generation. Cancel, late geometry, mixed editing and modifiers cannot mutate a
replacement route. Commit each pair vertex/via as one complete source transaction and undo both legs.

Test metadata ambiguity, independent module buses, endpoint polarity, physical-pad duplication,
corners, gap/width changes, vias/layers, cancellation and Undo. Validate actual native two-net pad
membership and DRC on a real fixture; preserve all older designs and native outputs.

Accepted scoped checkpoint: test-results/diff-pair-acceptance.json. Final847Python/210Node/
527browser across78suites pass. Main v8 has24tracks/2throughvias onF.Cu/B.Cu with actual native
DRC0/0/0 and4filtered ERC library warnings. Old44projects/1639files retain bytes/mtimes. Both AI
reports remain immutable; the guide-limit eligibility fix was independently reproduced/tested after
followup. Preserved native19/geometry4 caches; only source-bound response hints were added.
Broader routing/obstacle/physical-input/performance boundaries remain in docs/FLUX_PARITY.md.
