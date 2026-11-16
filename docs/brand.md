# OpenFabro brand and mascot

**OpenFabro — the open-source AI hardware engineer.**

**Circuits. Enclosures. Complete devices.**

中文定位：**覆盖电路、结构与外壳、固件和整机设计的开源 AI 硬件工程师。**

## Product scope

The product starts with a device and its requirements. Electrical design, enclosure geometry,
mounting, connector access, thermal assumptions, firmware and manufacturing preparation belong
to the same workflow. The current implementation focuses on PCB-based devices and parametric
enclosures; the brand expresses the broader product direction without claiming every type of
hardware has already been validated.

Write the product name as **OpenFabro**, with a capital O and F and no space. Use `openfabro`
for the Python distribution, command and public module entry points. The retained `wholeboard`
implementation namespace and legacy settings are compatibility details.

## Fabro

![Fabro, OpenFabro's abstract AI hardware engineer](assets/openfabro-mascot.png){ width="320" }

Fabro is a cute, abstract little maker: a soft mint form with a warm cream lower shell, simple
dark eyes and a tiny copper-coloured glowing core. The seam where its two forms fit together
suggests assembly and making an idea physical. Its dedicated AI engineering probe combines
two small contact tips, an illuminated scanning collar and a few glowing circuit nodes. This
gives it the identity of a hardware engineer while preserving the cute, abstract silhouette.
It has no specific profession's uniform or literal circuit-board body, so it can represent
electronics, enclosures and the complete device.

- Personality: curious, patient and approachable.
- Shape: soft, compact and readable as a small avatar.
- Colours: mint from the workbench's accent, with cream and warm copper details.
- Signature tool: a compact AI engineering probe for the character's measurement and design work.
- Usage: app identity, welcome screen, assistant avatar, About panel and documentation.
- Asset: transparent PNG; keep its proportions and generous surrounding space.

The mascot was generated with the built-in `image_gen` tool with a transparent background.
The [complete generation prompt](assets/openfabro-mascot.prompt.txt) is retained beside the asset.
The [original concept](assets/openfabro-mascot-v1.png) is preserved as a reference for later variations.

## Engineering foundation

OpenFabro builds on [WholeBoard](https://github.com/DingoOz/WholeBoard) and the existing KiCad,
TraceMaker, ngspice and FreeCAD integrations. The OpenFabro source is published at [AllenPeng0209/OpenFabro](https://github.com/AllenPeng0209/OpenFabro).
Upstream links identify the engineering foundation and do not imply endorsement.
