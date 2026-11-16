# Part Type interface setup reference

Inspected on 2026-11-16: [Flux Impedance Control](https://docs.flux.ai/reference/impedance-control)
documents automatic terminal properties for USB A/B/C, HDMI, five PCIe link widths, MIPI CSI/DSI,
DDR3 and DDR4. [Schematic FAQs](https://docs.flux.ai/faq/frequently-asked-questions--faq-)
distinguishes Bus Group identity and Bus Type. The existing manual terminal editor remains useful
for custom and multiplexed interfaces.

This implementation adds the complete documented Part Type list with real native symbol-name
matching, data-lane roles/polarity, separate USB ports, DDR byte masks/strobes and reviewed targets.
Unmatched pins remain visible and unchanged. Missing/ambiguous/shorted pairs block automatic Apply.
Existing values require an explicit Keep or Replace choice; a unique kept pair target extends to
both legs. Connections, physical placement and routed copper are retained by native parity review.
Changing a label's display alias never changes the electrical-name match.

The targets are editable starting assumptions. They do not encode every protocol revision, device
constraint or board stackup. No tolerance or skew is inferred. In particular, VBUS is a power pin;
the public Flux page's statement assigning differential impedance to VBUS is not used here.

Engineering references for the starting targets:

- [TI USB/HDMI layout guide SLLA414A](https://www.ti.com/lit/an/slla414a/slla414a.pdf): USB90Ω and
  HDMI100Ω differential examples.
- [Hailo-15L design guidelines](https://ww1.microchip.com/downloads/aemDocuments/documents/hailo/hailo15l_board_design_guidelines_1.2.pdf): PCIe Gen3 85Ω example. Link width alone does not establish
  generation; other targets and reference-clock requirements must follow the actual device guide.
- [TI SN65DPHY440SS](https://www.ti.com/lit/ds/symlink/sn65dphy440ss.pdf): MIPI D-PHY100Ω example.
  C-PHY trios are outside this differential-pair preset and require manual configuration.
- [TI DDR3 SPRABI1D](https://www.ti.com/lit/an/sprabi1d/sprabi1d.pdf):50Ω single-ended and100Ω
  differential data-strobe example with byte grouping. The DDR4 row starts at the same editable
 50/100 targets; this is a project setup policy, not a claim that DDR4 universally requires them.

Inspection and tests of metadata/native outputs do not establish interface compliance, physical
signal integrity or manufacturing readiness. Full Flux functional and pixel parity remains open.
