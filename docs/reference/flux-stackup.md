# Stackup editor reference

Inspected 2026-11-16. [Flux Stackup Editor](https://docs.flux.ai/reference/stackup-editor) supplies
the editable layer table, template selector, layer ordering and material properties. The reference
capture `flux-stackup-editor-20261116.png` is comparison material, not an application background.
The live public On Air project eventually rendered schematic/layout in an anonymous isolated tab;
its realtime endpoint also reported permission errors. No editable-project acceptance is inferred.

The code-rendered editor follows the table/header/selection colors and via-column layout, with
actual editable values, private source review, native export, import/download, project presets,
default through-via settings and atomic source history. Copper weight is displayed as a nominal
35µm/oz equivalent; it is not a supplier foil-weight certificate.

Physical construction uses the [KiCad PCB file format](https://dev-docs.kicad.org/en/file-formats/sexpr-pcb/)
and the [KiCad10 stackup implementation](https://gitlab.com/kicad/code/kicad/-/raw/10.0/pcbnew/board_stackup_manager/board_stackup.cpp).
KiCad includes enabled mask thickness in its board-stackup total; overlays and paste do not enter
that bare-board total. Real IPC-2581 export is used to test consumption. Its numeric formatting can
round fields, so the original recipe and native PCB remain the precision-bearing inputs.
Actual zone refill drops the zero-thickness solder-paste material label from the native PCB;
the complete declaration remains in the editable recipe/portable sidecar. IPC also normalizes
overlay/mask material labels. Neither export is claimed to echo every technical-layer label.

[JLCPCB's published constructions](https://jlcpcb.com/impedance) provide the7628/3313 layer values.
Both four-layer examples use outer35µm and inner15.2µm copper. The7628 example has210.4µm prepregs
and1.065mm core;3313 has99.4µm prepregs and1.265mm core. Published Dk values are4.4/4.1 for those
prepregs and4.6 for the core. The flat mask model uses the published15.24µm above-trace value and
Dk3.8. Loss tangents use explicit generic assumptions and remain editable.

These recipes sum to1.61668mm and1.59468mm including that declared flat mask, rather than being
silently rescaled to nominal1.6mm. Coating geometry is not actually flat over etched copper; source
and assumptions travel with the recipe. Supplier confirmation, process tolerance and measured SI
remain separate gates. Generic Standard1/2/4/6/8/10/12 presets are declared examples, not fab approvals.

Area stackups, flexible-region drawing, bending constraints, all flex-specific layer types and the
remaining supplier template families stay within the full replication scope and remain open.
