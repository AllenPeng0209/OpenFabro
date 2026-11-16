Generated from literal vertex coordinates and outward-facing triangle indices by
test-results/mesh-import-fixtures.py; no production importer/exporter derives the expectations.
The bracket is 20×14×4 mm (volume1120 mm³). STL has repeated facet vertices.
OBJ includes a companion MTL; the textured OBJ uses a generated 2×2 RGBA checker PNG.
The textured OBJ's face UV indices were subsequently corrected so each cube face
covers the full checker and shared 3D corners have genuine, distinct UV seams.
open.obj has two triangles and no solid. GLB, embedded GLTF and external-buffer GLTF
encode meters and Y-up. A translated parent places instanceA at min7/9/2 mm; instanceB
has a 0.5 X scale and 90° rotation around native Z, yielding min23/9/2, size14/10/4,
volume560. Linear PBR baseColorFactor0.1/0.3/0.8 displays as sRGB #5995e7.
