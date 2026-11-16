These fixtures were generated locally with FreeCAD 1.1.4, not downloaded from a vendor.
The generating probe and its measured results are in test-results/cad-import-fixture-probe.py
and test-results/cad-import-fixtures/probe.json.

colored_assembly.step contains three labeled bodies exported using the headless Import
API, including RGB face colors: Blue bracket (20×14×4, min 7/9/2), Red spacer A
(radius 3, height 6, center 35/9/2) and Red spacer B (center 35/24/2). All coordinates
are millimeters. The total volume is 1120 + 108*pi and the bounds are min 7/6/2,
size 31/21/6. There is no assembly mating/constraint history.

bracket.brep and bracket.iges contain the same uncolored bracket solid. surface.brep
and surface.iges contain a 12×10 planar face with no closed solid. These catch imports
that incorrectly treat valid surfaces as solid geometry.

face_colors.step assigns red to the first face and blue to the other five faces.
first_face_color.step assigns blue to only the first face; FreeCAD exports the other
faces as its default gray. A one-element export color list is NOT a whole-body color.

nested.step exercises an actual STEP shared-shape instance (App::Link after import).
Its two 20×10×4 instances have STEP minima 10/20/3 and 30/20/3. The source FreeCAD
assembly's ancestor transform was not serialized by that fixture export; this file
does not test a nested STEP ancestor placement. FreeCAD's reader returns one uniform
gray color for its definition and no separate color record for the repeated instance.
