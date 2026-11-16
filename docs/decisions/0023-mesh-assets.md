# Mesh originals, physical coordinates and faceted edits

STL, OBJ, GLB and GLTF are product assets, alongside exact CAD originals. Keep the
original bytes and all referenced companion files with trusted hashes and a downloadable
original ZIP bundle. Discover only the referenced buffers/materials/images from selected
files or folders. Decode offline through an in-memory resolver, not filesystem or web URLs.
Relative paths may traverse inside the uploaded folder but cannot escape that namespace.

Normalize glTF meters/Y-up and complete node instance transforms to millimeters/Z-up.
STL/OBJ have explicit source-unit choices. Preserve body names, linear glTF base colors,
OBJ UV seams, base-color textures and vertex colors in the original preview. Split bodies
by connected edges, so shells touching only at a vertex remain separate. Closed/winding
topology, open meshes and native solid verification are different states in API/UI/Agent
evidence. Open or oversized meshes remain useful reference assets.

Use a canonical JSON snapshot for the trusted FreeCAD adapter. Eligible closed meshes
convert to faceted BRep for import recipes and existing modeling operations. Keep originals
and prior models. Report mesh provenance, conversion tolerance and per-face appearance
approximation. STEP export verifies native geometry and corresponding colors; it does not
recover analytic surfaces, a vendor feature tree or texture-map interchange.

Renderer previews use actual UV textures and linear vertex colors. Imported opacity and
material properties survive style changes. Texture callbacks and modal requests belong
to their original viewer/project/dialog. Closing and reopening, switching projects and
asynchronous folder traversal must not adopt old inventories, dispatch into another project,
release another dialog's busy state or close another dialog.

Implementation uses trimesh4.12/NumPy with bounded geometry/accessors and PIL texture
decoding. The native FreeCAD process consumes only the canonical snapshot and requires no
trimesh installation. Preview budgets and native conversion budgets are separate. Required
glTF extensions, animated/skinned assets, richer PBR/smoothing and general high-resolution
solid reconstruction remain open parts of the full Flux objective.

Primary references: [Flux import workflow](https://docs.flux.ai/reference/import-and-edit-cad-files),
[glTF2 specification](https://registry.khronos.org/glTF/specs/2.0/glTF-2.0.html),
[trimesh loader implementation](https://github.com/mikedh/trimesh/blob/main/trimesh/exchange/load.py).

Phase53 scoped acceptance: test-results/mesh-import-acceptance.json. Final1047Python/one
existing warning,277Node,600browser/89suites and83native-core checks pass. Actual GUI
file/folder/texture/inch/open-reference, Agent native create/drill, host parameter/Undo/
Redo/reload and direct three-STEP probes passed. Two fullread/exact reports and three
exact image copies document evidence review, not AI source approval. Last material/
alpha fixes were host-tested after that review and gated-loaded without native regeneration.

Main51797/20995/assets579fbe3be645 retains original profile/config, all53idle. Old52specs/
versions and2239 hashes/nsmtimes exact; frozen53 totals2316files. Installed wheel111Python/
48assets and native CAD+GLB smoke source matched, using existing deps/FreeCAD. Full Flux,
richer materials, clean-host and deferred watch work remain open.
