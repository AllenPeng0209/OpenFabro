# Interactive obstacle routing and copper shove

Preserve the complete Flux/self-hosted IDE goal; this phase advances the live PCB route controller.
The previous accepted phase47 is real progress, not full parity. Its1914 frozen files and47 saved
project sources/versions remain the baseline. The deferred watch remains out of scope.

The current controller directly places geometric elbows. Implement a bounded, synchronous physical
clearance planner used by both cursor preview and click persistence. Walk around foreign copper,
physical holes, board edges/cutouts and native track keepouts. Respect actual layer spans, widths,
rotated standard pads, conservative curved obstacles, protection and separate track/via permissions.
Unprotected pours may refill after placement; protected or unknown fills remain obstacles.

Shove mode may reroute explicitly unprotected foreign straight copper while retaining original
identities, width, layers, endpoints and every discovered same-net junction/contact. Pads, vias,
protected copper and complex contacts remain fixed. A bounded search may walk around instead;
failure leaves the cursor/source unchanged. Ghost displaced copper and report affected nets before
the user's click. Save both the route and displaced copper atomically and undo them together.

Pair routing must keep its shared centreline/spacing and validate actual two-lane fanouts against
foreign geometry. Layer transitions must check the full via span and hole spacing. Hidden geometry
remains an obstacle. Existing route owner/version/generation and optimistic native-refresh behavior
remain required. Native ERC/DRC and pin membership, not the browser model alone, prove acceptance.

Keepout permissions require geometry schema6 sidecars; preserve older geometry/native files and
native producer20. Cache refresh must not overwrite original snapshots. No Rust/C++ rewrite.

Flux's observed docs describe pad touch points, waypoint clicks and F/W/V controls. No official
manual-shove menu has been observed, so new local behavior controls are not a pixel-parity claim.
See docs/reference/flux-interactive-routing.md. General search/topology/performance, arbitrary custom
geometry, full Flux pixels/features and measured SI/manufacturing remain requirements to verify,
not guarantees inferred from this implementation plan.

Scoped acceptance: `test-results/walkaround-acceptance.json`; main20261115-061257-21cav5.
962Python/258Node/560browser/84suites passed. Current geometry7 additionally retains native Cu textbox
refusal markers; native20 and originalschema6cache files stay unchanged. ThreeactualAIreports and
saved-history/native/XML/image evidence distinguish unsavedv1ghost fromsavedv5. DRC0/0/0/rawERC0errors
with7filteredwarnings/manufacturingfalse. Latepair-centre cursor/neutralactionlabel were host-tested
after the last AI review. Savedlongdetour and~.016mmextra segment remain concrete route-quality debt.
