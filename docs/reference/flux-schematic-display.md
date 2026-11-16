# Schematic View display reference

Observed read-only in the public On Air R2 demo at1440×1000. Evidence:
test-results/flux-schematic-view-reference.json/png and flux-schematic-display-reference.json;
flux-schematic-pin-labels-on.png was directly inspected. Same stacked Objects/View dock as PCB.

The Schematic View contains a Display accordion and four28px rows,14px Roboto, with whole-row
buttons and aria-pressed state: All pin labels (initiallyfalse), Comments, Collaborative cursors and
Keyboard shortcut bar (initiallytrue). Enabled rows show a right-side checkmark. Pin labels were
toggled false→true→false through the actual UI. No design or external account changes occurred.

Official [shortcut reference](https://docs.flux.ai/Introduction/pcb-editor-shortcuts) lists Shift+P
for Schematic pin labels, Shift+C for comments and Ctrl/Cmd+Shift+Backslash for collaborative cursors.
The public guest's editable shortcut-bar contents and precise label zoom/hover policy are not fully
established; do not claim those are pixel accepted from this inspection.

3D View was also inspected: Camera material/projection, top/bottom3D models, Analysis and Display
sections exist. Its initial captured viewport was blank, so the screenshot does not establish loaded
model geometry or functioning surface analysis. This phase focuses on actual Schematic display controls.
