# Shorter interactive detours and validated path compaction

The accepted phase48 main fixture has83.2542mm of N copper and a0.01598mm extra elbow despite native
DRC passing. A hand-specified octilinear witness preserves the same pads, branch and protected copper
with38.3740mm and passes actual KiCad DRC/pin export. Full Flux remains the goal; this fixes concrete
route quality rather than redefining completion as clean DRC.

Refine the blocker-driven visibility graph after a first valid path: consider encountered obstacles
adjacent to the current blocking envelope, instead of accepting an outer-board detour prematurely.
Try clearance-checked octilinear shortcuts within each independently anchored path interval. Never
move endpoints, protected objects or junction anchors; actual generated geometry remains native-checked.
Keep a valid incumbent if optional quality work runs out of budget. Do not claim global optimality.

The initial regression measured35.2180mm andminimum0.8311mm. Exact anchor retention subsequently
produced the actual saved main v5 with14tracks total, N35.217960243mm andminimum0.187383297mm.
These are different intermediate versions. The current endpoint and clearance regressions pass;
optional refinement retains a validated path when its budget is exhausted. Compaction removes only
exactly collinear vertices, preserves explicit anchors and validates the resulting geometry. Search
and guide endpoints retain the original finite coordinates, including distinct short destinations.

Actual mouse click, whole-source Undo/Redo and completion reached v1→2→3→4→5. KiCad geometry retains
both protected native IDs and original pads/footprints/outline; source board/rules/components/nets/library
remain unchanged. Both in-app reports are fully read and exact-proposal matched; final actualv5 DRC
is0errors/0warnings/0unconnected, rawERC0errors/7filteredwarnings/manufacturingfalse. The final review
identified R1: the absolute determinant threshold could miss short crossing segments. Its public
reproduction failed before correction and passed after using an actual zero determinant for parallel
straight segments. Node265, targeted native23 and the current live browser reproduction pass after
this late host fix; the AI report predates those final lines. Python964/oneexisting warning passes.
Final standard full browser557/83 passes; optional mechanical4/1 passes separately, totaling561/84
coverage. Raw full report remains557/83. Currentwheel/source/live45assets/HTML/105Python match;
main49215/exec25492 assets9c6e534d78c6, all49idle/saved5/prefs{}restored/console0errors. Phase49
scoped acceptance is test-results/route-quality-acceptance.json; fullFlux remains active.
Preserve accepted48 sources/versions and1999frozen files; no watch, account, order, credential, comment,
commit/deployment or unrelated production/branding/driving_into_world work.
