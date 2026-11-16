# Flux editable mechanical reference

Inspected official public documentation on2026-11-15:

- https://docs.flux.ai/reference/editable-cad-code
- https://docs.flux.ai/flux/reference/design-new-parts
- https://docs.flux.ai/reference/import-and-edit-cad-files

The documented workflow selects a part, edits its CAD code or named dimensions, rebuilds, verifies
against the source and saves a new model asset while retaining the original. STEP output is supported.
New-parts documentation explicitly names extrude, revolve, sweep, loft, shell, fillet, chamfer, holes
and linear/circular patterns. Exact-solid and operation claims here are documentation evidence;
no writable Flux modeling trial or source-code access was performed.

Broader documented imports include STEP/IGES/BREP and mesh/DXF/SVG assets. These remain separate
requirements, not satisfied merely by implementing the editable-program path. Existing FreeCAD
enclosure generation alone is not general mechanical-model authoring or complete Flux parity.
