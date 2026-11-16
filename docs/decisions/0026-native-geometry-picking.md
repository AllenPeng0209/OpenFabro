# Native geometry selection for assembly mates

Keep a sealed map from display triangles to native faces and from visible edge polylines to
native edges. Each assembly instance carries its original source-local selector separately
from its solved world placement and the rebased preview coordinates. Plane, cylinder and circle
data come from FreeCAD; display meshes do not invent analytic surfaces or radii.

A selected reference includes body identity, physical instance path, element index, geometry
kind, direction, normalized location and boundary counts. Compatible dimension edits preserve
the relationship. A changed or ambiguous reference fails before publication and needs reselection.
This is guarded geometric correspondence, not a general persistent topology naming solver.
Repeated definitions cannot silently substitute another physical instance.

The web mate picker temporarily isolates the selected part and highlights native faces/edges.
GPU and software selection honor visible geometry; GPU selection also honors cross sections.
Draft Undo/Redo applies to the chosen references. Existing CAD history restores saved models.
Source changes and abandoned asynchronous reads cancel obsolete selections. A new picked mate
uses both source SHA and preview model ID; changed dependencies reject its dispatch.

Block image capture during opening or active picking so an isolated temporary view cannot be
presented as a normal complete assembly capture. A bounded, hash-pinned Agent inspector supplies
the same exact source selectors without dumping triangle/color payloads. Historical scenes
without the map remain readable and are never regenerated merely for inspection.

Scoped acceptance: `test-results/topology-acceptance.json`. 1086 Python, 283 Node and621 browser
checks /93suites pass, with one existing socket-thread warning. Actual GUI face/edge picks, in-app
Agent dimension update, source preservation, exact history restoration, mobile and real-image
review are verified. Four independently reconstructed STEP states each match12faces/24edges/
72triangle-vertex memberships. Original55/2582 SHA+ns-mtimes preserved; frozen56 totals2687files.
Installed wheel/source/live match115Python modules/96webfiles/93static responses, native smoke
passes with existing dependencies; no clean-OS claim. Aligned mates constrain direction only.

Full Flux parity, general sketch constraints, full topology naming,
closed-loop mechanisms and physical validation remain separate ongoing work. Self-hosted web
IDE first; watch work remains deferred.
