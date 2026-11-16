# Flux component hotkey reference

Checked the [official shortcut documentation](https://docs.flux.ai/Introduction/pcb-editor-shortcuts)
on2026-11-12. In Schematic, Shift with a number1–5 assigns a component; the number inserts it.
Viewport assignment/recall uses6–9. PCB layer-number sequences are a different context. These
documented actions supersede the local prototype's former schematic1–4 view navigation.

The local implementation adds a native-symbol preview and an explicit click before a design save,
with Escape/Space cancellation, one complete Undo, project-library dependencies, account-local
browser persistence and guarded late responses. The five-slot context submenu reuses the measured
local context-menu tokens. This reference does not establish the pixels or every behavior of Flux's
enabled writable hotkey menu; those controls were not inspected with editing access.

Regression evidence includes actual delayed native requests versus component dragging, an isolated
Space-drag case whose pointer is verified to hit the canvas, and account identity at the pending
request boundary. Storage isolation testing is distinct from an actual main-account login switch.
The final acceptance receipt, once complete, is recorded in `test-results/component-hotkeys-acceptance.json`.
