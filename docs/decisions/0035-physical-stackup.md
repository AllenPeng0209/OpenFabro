# Reviewed physical board stackups

The old Rules view stored a copper count and a total thickness, while native PCB files had no
explicit construction. Impedance estimates silently chose a nominal four-layer construction for
unknown counts. A physical stackup needs one consistent source for materials, dimensions and export.

Store a versioned ordered recipe in `board.stackup`. Stable row IDs are distinct from position-based
KiCad layer names. Copper, dielectrics and mask contribute to finished thickness; silk and paste
remain technical layers without changing KiCad bare-board thickness. Dielectric properties are
declared inputs. A recipe name does not establish manufacturer or signal-integrity acceptance.

The editor keeps changes private until Done. Its native preflight captures actual current copper,
checks layer mappings/removals, preserves UUIDs and placements, verifies electrical pin groups and
passes the construction through real KiCad IPC-2581 export. Removed used layers require an explicit
destination or removal choice. Collapsed via endpoints and incompatible SMD outer-side changes
cannot be applied. Native/source digests are rechecked by both editor and Agent at acceptance.
The save uses the shared source-write slot and one complete Undo entry.

Generated planes remain declarations and are regenerated from them. Manual zones retain their
UUIDs, outlines and settings; migration updates their native source as well as metadata. Existing
user propagation values are retained with a review note. Changing materials does not silently
recalculate those user inputs or prove the continuous reference plane.

Write explicit stackups into native KiCad setup and deliver a portable construction JSON with the
PCB hash. The real parser, rather than only the source S-expression, consumes the candidate. Native
IPC formatting can round numeric fields, while the PCB/recipe preserve declared precision.
KiCad refill drops zero-thickness paste material labels from the native PCB; the full technical
declarations remain in the editable recipe and portable sidecar. That omission is recorded rather
than presented as a complete native material-label round trip.

KiCad requires at least two copper slots. A one-sided construction uses an unused zero-thickness
B.Cu slot, which is hidden only when no actual copper uses it; one-sided Gerbers exclude B.Cu and
refuse to discard real other-side copper. A conditional construction-policy guard regenerates old
ignored/invalid caches into new folders instead of rewriting historical native inputs.

Outer-layer planning uses the declared foil thickness, dielectric height and effective permittivity
to the adjacent declared reference. Several dielectric sheets use a series-capacitance effective
permittivity. This is an approximation, not a field solver; continuity/coverage remains unverified.
Unknown legacy constructions no longer borrow four-layer values, and length-only bus limits stay
available without an impedance reference.

Accepted in this scope:1193Python (one existing socket-thread warning),303Node and687browser
checks across108suites. Main QA `20261116-063109-b0bf` exercises actual Agent inspection/private
preview/apply and GUI material/via/preset changes with whole semantic Undo/Redo/Undo restoration
atv6. Independent complete-copy KiCad exports verify13rows, five Dk/loss layers and6nets/25pins;
all original files remain unchanged. Receipt:`test-results/stackup-acceptance.json`.

The installed wheel matches122Python/107web/104live statics and passes actual native IPC preview
using existing dependencies. Four exact AI reports retain an original14654-character overrun and
a7110-character corrective summary; the original length claim is explicitly rejected. Software
work remains active despite ambiguous wording in the summary's last scope paragraph.

Global construction, rather than area-specific flex regions or mechanical bending, is implemented
in this checkpoint. Full Flux functionality/pixel parity and clean-host installation remain open.
