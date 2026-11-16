# Next Flux reference: visual markup

Verified2026-11-12 against the [official Markup documentation](https://docs.flux.ai/reference/markup-mode).
This is an open parity gap; no implementation or completion is claimed here.

Flux lets users annotate a fixed schematic, PCB or3D viewport and send its image with a chat request.
Annotations do not edit the design. Sending clears them. Escape, view/thread changes and canvas
resizing also exit; camera movement is suspended during drawing. The composer exposes a stylus action
and a compact-menu entry.

Current foundation: codex_bridge.request_once already attaches native build images via CLI`--image`;
provider adapters accept image tool results. No current composer/viewport markup workflow was found.
Next implementation should connect real viewport capture, strokes, project/version ownership and
image provenance to these existing paths, then prove actual model image receipt and design isolation.
Retain all other gaps in FLUX_PARITY.md; do not replace the full-replica objective with this feature.
