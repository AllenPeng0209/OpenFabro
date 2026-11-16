# Linked product assemblies and native fit

Resolve assembly components from verified mechanical model revisions, immutable imported assets,
or the saved PCB/enclosure native geometry. Reading or assembling a source never generates it.
Latest model links require unchanged source and dependency receipts; explicit retained revisions
keep their sealed geometry. Pre/post-build dependency checks protect publication. Missing board
component geometry stays incomplete, including through nested or pinned assemblies.

Add rigid component placements and directed coincident, concentric, aligned and offset mates to
the existing editable CAD program. Select real source-local planes, cylinder axes, edges or
explicit datums. Solve in dependency order and reject cycles or inconsistent residuals. Report
remaining possible motion; this does not implement a closed-loop or motion solver.

Measure every declared member pair with native solid common volume and minimum distance. Keep
thresholds, exceptions, nearest points, coverage and violations in the sealed report. Checking
valid solids does not establish fit. Internal geometry inside one member is outside this check.
No physical tolerance, connector access, manufacturing or full-motion acceptance is implied.

The web editor adds named sources, placements, fixed members, mates and clearance. Its member
tree selects all relevant meshes in GPU and fallback viewers. Keep the selected assembly while
linked sources change, mark it stale, and recompute only on rebuild. Account/project-scoped view
selection survives reload. Existing CAD history handles source/model changes without remeshing
restored states. Full Flux parity and watch design remain separate ongoing work.

An independent original-STEP comparison found that flattening document definitions loses
LinkGroup instance transforms. Resolve leaves through complete root instance paths with
getSubObject; preserve repeated instances and their face colors. The regression compares every
PCB solid's mass, area, center and bounds to an independent Part.read, rather than accepting
equal aggregate volume alone. Old assets/reports remain immutable historical evidence.

Large Agent evidence keeps model/source identities, report hashes/paths and compact fit even
when detailed topology exceeds the context budget. The mechanical inspector exposes retained
revisions and full fit while explicitly omitting per-face colors. Source hashes alone cannot
identify geometry after dependency or implementation changes.

Scoped acceptance: `test-results/assembly-acceptance.json`. 1079 Python, 279 Node and 611 browser
checks / 91 suites pass; one pre-existing socket-thread warning remains. Native tests include real
populated KiCad PCB/enclosure sources, missing geometry, nested freshness, conflicts, concentric
offsets and per-solid world-coordinate conservation. Actual GUI Agent and manual editor flows,
four independent STEP variants, exact image review, installed native assembly smoke and desktop/
mobile reports are verified. Original54/2384 SHA+ns-mtimes preserved; frozen55 totals2582files.
The installed wheel matches source/live modules and assets, with existing native dependencies.
