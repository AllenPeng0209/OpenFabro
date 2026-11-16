# Custom copper reference

Inspected2026-11-16: [Flux custom shapes](https://docs.flux.ai/reference/custom-pad-shapes) supports
vector assets and an SVG-path shape rule. [Pads and holes](https://docs.flux.ai/reference/pads)
distinguishes nonconductive holes, through-hole and connector pads. The implementation keeps an
explicit source-unit selector, native review and source history around those editing functions.
The public On Air Layout was observed in an isolated anonymous browser; permission failures and
read-only state do not establish acceptance of enabled editing. Current capture:
test-results/pad-shapes-flux-layout.png. It is a reference, not an application background.

The [KiCad pad syntax](https://dev-docs.kicad.org/en/file-formats/sexpr-intro/#_footprint_pad)
requires a native custom anchor and primitives. Real native DRC and exported SVG, rather than
only source strings, verify the notch/void material and contact behavior. KiCad's NPTH washer
apertures can still include surface copper; the barrel attribute alone cannot decide material.
Imported native surface copper is retained, while new mechanical holes omit it explicitly.

One filled, connected region is authored per pad, with declared curve sampling and native rounding.
SVG/DXF strokes and text must first be converted to closed filled outlines. Multiple disconnected
regions need separate pads. These bounds are surfaced instead of inserting bridges or silently
dropping visible source geometry. Full pad stacks and broader Flux pixel/function parity remain open.
