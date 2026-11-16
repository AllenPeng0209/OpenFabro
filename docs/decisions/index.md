# Decisions

Architecture decision records: one short page per choice that is not obvious from the code, with what was
considered and why. They are numbered in the order they were made and are not edited afterwards; a later decision
that changes one says so and links back.

| # | Decision | Status |
|---|---|---|
| [1](0001-docs-generated-from-code.md) | Reference pages are generated from the code | Accepted |
| [2](0002-functional-spacing-between-declared-mains-nets.md) | Functional mains spacing only between declared mains nets | Accepted |
| [3](0003-surface-rule-for-creepage.md) | A surface clearance rule stands in for creepage | Accepted |
| [4](0004-rules-beside-every-board.md) | The project and rules files go beside every board TraceMaker sees | Accepted |
| [5](0005-kikit-settings.md) | KiKit settings: mill radius, V-cut layer, copy numbering | Accepted |
| [6](0006-price-tables-not-scraping.md) | Board prices from editable tables, not scraping | Accepted |
| [7](0007-worker-and-expert.md) | A worker model and an expert model | Accepted |
| [22](0022-native-cad-import.md) | Immutable CAD originals and editable native import recipes | Accepted in scope |
| [23](0023-mesh-assets.md) | Mesh originals, physical coordinates and faceted edits | Accepted in scope |
| [24](0024-drawing-profiles.md) | Native DXF/SVG profiles, cutouts and thickness extrusion | Accepted in scope |
| [25](0025-linked-assemblies.md) | Linked product components, rigid mates and native fit | Accepted in scope |
| [26](0026-native-geometry-picking.md) | Source-local face/edge selection and guarded mates | Accepted in scope |
| [27](0027-constrained-sketches.md) | Native sketch constraints, draft solve and linked extrusion | Accepted in scope |
| [28](0028-part-materials.md) | Declared bulk/surface materials and realistic appearance | Accepted in scope |
| [29](0029-native-curvature-combs.md) | Native placed edge curvature and view combs | Accepted in scope |
| [30](0030-native-surface-analysis.md) | Native surface derivatives, Zebra and curvature display | Accepted in scope |
| [31](0031-native-curve-events.md) | Native curve roots, one-sided jumps and display filters | Accepted in scope |
| [32](0032-adaptive-cad-mass.md) | Adaptive STEP mass integration and explicit legacy estimates | Accepted in scope |

| [33](0033-file-draft-recovery.md) | Owner-scoped local drafts and explicit three-way recovery | Accepted in scope |

| [34](0034-interface-presets.md) | Native named-pin Part Type setup with explicit conflict review | Accepted in scope |

| [35](0035-physical-stackup.md) | Declared physical layers, copper-safe review and native construction | Accepted in scope |
| [36](0036-native-pad-holes.md) | Copper-center coordinates, editable slots/offsets and exact project holes | Accepted engineering scope |
| [37](0037-custom-pad-copper.md) | Vector copper regions, native anchors, truthful holes and guarded editing | Accepted engineering scope |

| [38](0038-layout-pad-instances.md) | Reviewed physical pad instances and native selective annuli | Full acceptance pending |

| [38](0038-layout-pad-instances.md) | Physical pad instance properties, native review and preserved routes | Accepted engineering scope |

| [39](0039-pad-override-recovery.md) | Explicit recovery of source-keyed orphan pad overrides | Proposed; isolated inventory prototype |

## Adding one

Copy the layout of an existing record into `docs/decisions/NNNN-short-title.md`, add it to this table and to
`nav` in `mkdocs.yml`. Keep it to a screen: context, decision, consequences.
