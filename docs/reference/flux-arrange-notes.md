# Flux arrange and viewport follow-up

Checked official documentation on 2026-11-12. These are documented interactions, not a claim that
the signed-in writable interface was observed. Existing public-editor history access led to signup.

The public On Air schematic was also inspected directly in an isolated guest session. Selecting
R7/R8 in Objects exposes the context menu, including disabled Align and spacing entries; the editing
submenu remains unavailable without editing access. At1440×1000 in its Traditional Chinese UI, the
observed menu is243px wide, with32px rows,14px Roboto text,8px vertical list padding, a borderless
#424242 paper,4px corners and the standard three-layer MUI shadow. These measured tokens inform
the local context menu. Capture: `flux-align-menu-20261112.png`. This does not establish the geometry
semantics of enabled alignment commands or complete writable pixel parity.

The [official shortcut reference](https://docs.flux.ai/Introduction/pcb-editor-shortcuts) documents
six directional/center alignment commands, independent minor-step nudges, spacing, and schematic
viewport slots6–9. Saving a viewport uses Shift with the slot number; recalling it uses the number.
Component insertion has a separate1–5 slot range. These must not conflict with text editing, active
routing, markup, modal dialogs or PCB layer shortcuts.

The [schematic/PCB tutorial](https://docs.flux.ai/Introduction/getting-started-in-flux--schematic)
also exposes alignment through a selected-parts context menu. This makes a visible editing workflow
to implement after the AI-file checkpoint: select several real symbols, align/space them, review
boundary-wire consequences, save, Undo/Redo, and verify native pin/net geometry. PCB behavior needs
its own lock, placement and preserved-copper rules; schematic editor units must remain distinct
from physical millimeters. Bounds versus anchor semantics still need direct verification.

For later primitive work, [custom-shape documentation](https://docs.flux.ai/reference/custom-pad-shapes)
describes SVG/DXF assets and shape rules for pads, lines, zones and outlines. Imported assets and
editable library graphics already exist locally; arbitrary placed drawing/text objects and their
native exports remain separate work. Do not infer that imported symbol graphics are already free
canvas objects or that an SVG preview proves native manufacturing geometry.
