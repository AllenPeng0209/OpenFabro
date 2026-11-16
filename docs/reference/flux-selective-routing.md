# Selective routing reference

Official page read on2026-11-15: https://docs.flux.ai/reference/route-with-flux

The documented workflow routes named nets/connections or a PCB selection, retains existing
copper/placement/rules when requested, and presents concrete old/new changes for approval.
It also supports route edits, rerouting and deleting unprotected copper, with open-connection
and DRC results. Protected state and routing-only scope remain intact.

The local TraceMaker0.12.1 help/source exposes exact-or-pattern net filters, preservation locks and
bounded repair windows. Its repair lifts unprotected branches near an open connection and keeps
the result only when connectivity improves without losing previously joined pads. This is a native
background route/repair engine; no manual live-shove equivalence is established by that evidence.
