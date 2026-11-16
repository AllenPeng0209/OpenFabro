# Flux layer-view evidence

The [official shortcuts](https://docs.flux.ai/Introduction/pcb-editor-shortcuts) and
[layer-view guide](https://docs.flux.ai/reference/reference-layer-view-control) were checked with
the live public [On Air PCB](https://www.flux.ai/markwuflux/on-air-r2-demo~4a/pcb/2d).
The isolated guest view permits these personal display actions without editing the design.

Observed leaf rows are28px high,14px/20px Roboto, with padding0px8px0px28px. Focus uses a white
16% background, hover8%. The physical layer rows are grouped around Top, inner copper layers,
Bottom and Mechanical. Copper rows expand to Fills, Polygons, Pads, Traces and Vias. Eye states
include mixed contents. Captures and measured DOM states are recorded in `layer-view-reference-*.json`
and `docs/reference/flux-layer-*.png`.

Direct PCB digit2 focused the first inner copper layer; L1 focused top copper and H2 hid the first
inner layer. HF showed all fills. Focus preserved other eyes, showed a hidden silkscreen target,
and dimmed other actual board pixels. Unfocusing kept that silkscreen visible. The latter contradicts
an initial AI plan suggestion to roll back the eye state; implementation follows the observed UI.

Measured common colors: top copper#FF0000, bottom copper#3939FF, inner1#FFCE00, inner2#00BDFF;
top/bottom silk#00FFFF/#FF00FF, mask#1DBC6C/#90F490 and paste#E39CE5/#98CBE8. The local workbench
uses those values for the measured layers; higher-inner-layer colors and enabled editing flows were
not observed. Pane stacking, complete writable pixels and every view interaction remain separate
parity work. External Flux console errors are not local product errors.

Native masks/paste are plotted with installed KiCad in page-size-mode1; a direct experiment confirmed
its paths retain absolute board coordinates. Page-size-mode2 rebases the origin and is unsuitable for
this overlay. Physical CAD bytes and the project/rules bundle are pinned independently from personal
object visibility. Tests exercise native coordinates, immutable snapshots, role access, late results,
actual canvas pixels and an explicitly labeled SVG-response hash mismatch injection.

Followup review found a lost-focus recovery boundary. A controlled blur/focus test first failed
with the native layer left waiting, then passed after a focus-event resume hook. The main workbench
replayed that same event boundary without a design edit. This is not physical OS/device-focus
acceptance. Earlier review documents remain immutable and retain their then-current findings.

An actual marked native canvas reached the signed-in Codex CLI byte-for-byte, and it read an image-only
four-digit nonce. Its color-based opening classification was partly wrong: only the two left R1
openings were plotted F.Mask, while right-side copper pads were also visible. Frozen layer-state
context for the model is therefore required followup work, not accepted semantic image analysis.
