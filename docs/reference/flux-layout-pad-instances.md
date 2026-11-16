# Physical pad properties and connected layers

Inspected 2026-11-16: [Flux pads and holes](https://docs.flux.ai/reference/pads) and
[Connected Layers](https://docs.flux.ai/reference/layout-rules-types#connected-layers).
Flux exposes per-object geometry, pad type and local rules. Its connected-layer description keeps
annular rings on selected layers and only the hole on skipped layers. This is a functional reference;
the new native-review dialog does not establish complete Inspector pixel parity.

The [KiCad10 parser](https://gitlab.com/kicad/code/kicad/-/raw/10.0/pcbnew/pcb_io/kicad_sexpr/pcb_io_kicad_sexpr_parser.cpp)
reads pad layers, per-layer custom stack sizes/offsets and local rules.
[PAD::FlashLayer](https://gitlab.com/kicad/code/kicad/-/raw/10.0/pcbnew/pad.cpp) can flash PTH
copper on the drill span. Actual exports on this machine confirmed a 2mm back annulus despite a
front/inner-only layers list. A custom stack with a drill-sized skipped-layer profile removed that
annulus outside the hole, including after native refill. Removing unused layers alone depends on
connectivity and can restore rings; it does not express a fixed per-layer profile.

Native warnings about intentional zero annulus remain visible. These exports do not establish
manufacturability, plating quality, physical acceptance or verified automatic barrel-contact routing.
