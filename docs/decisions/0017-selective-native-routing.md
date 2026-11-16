# Selective native routing and reviewed repair

Flux documents routing named nets, preserving existing copper/placement/rules, and approving
concrete existing-copper changes. Implement this workflow with the installed TraceMaker native
router, exact net selection and real KiCad proof. This is not evidence of Flux's unobserved manual
push/shove controls or a claim that a background repair pass is real-time cursor shoving.

Preserve all existing copper by default. Capture native protection flags on tracks/arcs/vias and
round-trip them in source/native files. Old source items default protected, preserving prior behavior;
explicitly unprotected copper may participate only in a requested repair scope. Keep placement,
pad identity, board, rules, zone definitions and all protected or out-of-scope copper unchanged.
Review concrete added/removed/modified IDs and nets. Apply the exact prepared proposal, not a new
stochastic routing run. Existing-copper edits require explicit acceptance; additions to requested
nets may satisfy an authorized Agent request directly when all native proof passes.

Use bounded native jobs, exact (not wildcard-expanded) names, cancellation, source/PCB/plot-input
guards, private immutable proposal receipts, and normal source history/Undo. Measure selected open
connections separately from the whole board; unrelated unrouted nets cannot be called complete.
Check actual pin membership, preserved native geometry, lost connections, rebuilt-source parity,
and raw DRC deltas. Preserve explicit unknowns rather than inventing routability or SI guarantees.

Protection changes require native producer20/geometry5; preserve all older files and sidecars.
TraceMaker restarts its generated UUID counter for each process. Namespace input copper identities
only in the private routing copy, restore each original identity/protection flag, and give new
copper fresh identities before review. Ambiguous duplication of a private existing identity is
rejected. Actual consecutive SIGNAL then coupled USB routing reproduced the collision; the
regression checks preserved original geometry/IDs and real KiCad connectivity across both runs.
New local review controls follow existing editor tokens, not a claim of unseen Flux dialog pixels.
Both direct adapter and project routing reject conductive custom/trapezoid/other unsupported pad shapes before a native job
starts. The legacy visual airwire approximation remains display-only for those shapes. Native DRC
and manual routing remain available; unsupported geometry cannot establish routing completeness.
The adapter rejects existing or symlink output/summary/log/project/rule sidecars before any writes,
including dangling links. This preflight does not claim resistance to arbitrary concurrent local
filesystem writers.
Full interactive shove, arbitrary pair naming/topology, physical SI and clean deployment remain
separate work until actually implemented and verified. Software remains ahead of the deferred watch.

Scoped acceptance: `test-results/routing-acceptance.json`, project20261115-034256-0086v9.
938Python/211Node/12current routing-browser checks passed. Combined browser coverage551/82 includes
two independent reruns after raw full-run timeouts, not a clean one-shot full result. Real Agent,
manual pair routing, protection and whole-source Undo/Redo passed; actual v9 DRC0/0/0, rawERC0errors/
4filteredwarnings, manufacturingfalse. Three actual AI reports and correct image staging retained.
Final shared/direct pad-model preflight lines were host-tested after the last AI review.
