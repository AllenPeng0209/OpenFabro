# Flux manual-routing reference

Inspected official documentation on2026-11-15:
- https://docs.flux.ai/tutorials/routing-tutorial
- https://docs.flux.ai/flux/Introduction/getting-started-in-flux--pcb-layout-and-routing
- https://docs.flux.ai/reference/route-with-flux
- KiCad native zones: https://dev-docs.kicad.org/en/file-formats/sexpr-pcb/

Flux describes starting a trace at a pad hover dot, clicking waypoints, F to change the elbow,
W for width and V/right-click layer changes. AI routing can target named/selected connections.
This is documentation evidence, not a successful writable Flux trial or source-code access.
No official manual push/shove behavior selector was found in these references. An added local
Walkaround/Shove selector must not be called a1:1 reproduction of an unobserved Flux control.

Native zone keepout rules distinguish tracks, vias, pads, copper pour and footprint permissions.
The current schema5 geometry omitted those permissions; importing them requires a new parser
sidecar version while retaining original geometry files and native PCB/SCH snapshots.
