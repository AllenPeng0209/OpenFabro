# Pad and hole editing references

Inspected2026-11-16: [Flux pads and holes](https://docs.flux.ai/reference/pads),
[Hole Position/Size rules](https://docs.flux.ai/reference/layout-rules-types#hole-position),
and [custom pad shapes](https://docs.flux.ai/reference/custom-pad-shapes). The reference exposes
pad type, shape, dimensions, hole position and independent hole axes. Custom SVG/DXF copper shapes
and other rule families remain within the full goal; this checkpoint addresses drilled geometry.

The [KiCad pad/drill syntax](https://dev-docs.kicad.org/en/file-formats/sexpr-intro/#_pad_drill_definition)
supports oval drills and offsets. Actual [KiCad10 PAD source](https://gitlab.com/kicad/code/kicad/-/raw/10.0/pcbnew/pad.cpp)
locates holes at the pad anchor and moves the copper through ShapePos and its rotated offset.
The editable model names the relative hole offset explicitly and translates that native convention.

Independent real Gerber/Excellon exports, rather than a synthetic canvas alone, check copper and
drill placement. Rotated native IPC pad coordinates disagreed with Gerber for the inspected
KiCad10.0.8 probes. This is recorded as an interchange limitation, not corrected by changing actual
copper to match the IPC discrepancy. Historical immutable geometry remains readable with a warning
when its old nonzero-offset convention is encountered.
