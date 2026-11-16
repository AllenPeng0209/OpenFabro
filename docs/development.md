# Development

## Set up

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev,docs]"
npm ci
npm run vendor
python -m pytest tests -q
npm test
```

Node.js 22 or newer is required for frontend development. Windows contributors can run
Python commands with `.\.venv\Scripts\python.exe`. The Python distribution includes
the browser assets, so Node.js is not required to run an installed package.

Use `./run-workbench.sh` on macOS/Linux for a checkout-local workspace, or
`python -m openfabro` for the standard launcher. The public `openfabro` package delegates
to the `wholeboard` implementation namespace for compatibility.

## Browser and package verification

```sh
npx playwright install chromium
npm run test:browser -- --suite=production
python scripts/verify-package.py
```

The browser runner starts isolated workspaces and writes artifacts to `test-results/`.
Choose another filename substring with `--suite=...`, omit it for the standard suite,
or add `--mechanical` for the mechanical integration suites. Native checks require the
relevant KiCad, FreeCAD, ngspice, or routing dependencies. Package verification builds
a wheel, installs it outside the checkout, and exercises its isolated server and assets.

`pytest` is scoped to `tests/`; separate experiments and generated directories are
outside the application suite. Skipped native-tool coverage must be reported explicitly.

## The documentation

```
.venv/bin/mkdocs serve          # http://127.0.0.1:8000, reloads as you edit
.venv/bin/mkdocs build --strict # what CI runs
```

- Pages are Markdown in `docs/`, organised by [Diátaxis](https://diataxis.fr/): a tutorial teaches, a how-to guide
  does one job, reference describes, explanation gives the why. Put a new page in the section it belongs to and add
  it to `nav` in `mkdocs.yml`.
- Pages built from the code (blocks, profiles, mains, MCP tools, limits, settings, the spec, the Python API) are
  written by `docs/gen.py`. Change the code, not the page ([decision 1](decisions/0001-docs-generated-from-code.md)).
- When you take a figure from a standard or a price from a supplier, add it to [Standards and sources](standards.md)
  with the date.
- When you make a choice someone would otherwise undo, write a [decision record](decisions/index.md).
- Add a line to `CHANGELOG.md` under *Unreleased* for anything a user would notice.

`.github/workflows/ci.yml` checks Python, JavaScript, bundled browser assets, and the
installed package. `.github/workflows/docs.yml` builds the documentation and uploads
the site as a workflow artifact. Public documentation hosting is configured separately.

The Linux Python jobs install KiCad 10 and its footprint/symbol libraries from the
[official Ubuntu PPA](https://www.kicad.org/download/details/ubuntu/), and check tool
discovery before running the suite. FreeCAD-dependent tests report skips when FreeCAD
is unavailable; full mechanical validation requires a workstation with that tool installed.

## Code map

| Where | What |
|---|---|
| `openfabro/` | Public launch commands and compatibility wrappers |
| `wholeboard/workbench.py`, `workbench_native.py` | Interactive design APIs and native geometry |
| `wholeboard/mechanical.py`, `freecad_*.py`, `sketch_program.py` | Mechanical models, assemblies, native CAD and sketches |
| `wholeboard/production/` | Estimates, immutable packages, supplier inquiries and progress records |
| `wholeboard/codex_bridge.py` | Local Codex provider, engineering tools and guarded proposals |
| `wholeboard/ai/` | Providers, the designer agent, the expert model |
| `wholeboard/pipeline.py` | The build steps |
| `wholeboard/design.py` | Design validation and normalisation |
| `wholeboard/blocks.py` | Building blocks |
| `wholeboard/sim.py`, `ngspice.py`, `ngspice_shared.py`, `simlab.py` | Simulation and the Sim Lab |
| `wholeboard/power.py` | Power budget |
| `wholeboard/checks.py` | Trace heating, voltage drop, decoupling |
| `wholeboard/impedance.py` | Controlled impedance and interface profiles |
| `wholeboard/mains.py` | Mains spacing, slots and rules |
| `wholeboard/boxheat.py` | Heat in the enclosure |
| `wholeboard/enclosure.py`, `freecad_enclosure.py`, `case.py`, `dxf.py` | Enclosures, stock cases, DXF outlines |
| `wholeboard/kicad/` | Libraries, board and schematic writers, `kicad-cli`, geometry, rules file, hand edits, KiKit |
| `wholeboard/router.py` | TraceMaker |
| `wholeboard/jlc/` | Parts, quote, stock check, savings, panels, other fabs, Mouser and DigiKey |
| `wholeboard/bringup.py`, `ibom.py`, `firmware.py`, `fwbuild.py`, `report.py` | Bring-up guide, assembly page, firmware, PDF report |
| `wholeboard/revisions.py` | History and comparison |
| `wholeboard/mcp.py` | The MCP server |
| `wholeboard/bench.py`, `bench/` | The benchmark |
| `wholeboard/server.py`, `wholeboard/web/` | API and interface |
| `wholeboard/doctor.py` | Tool checks and installers |

Module-level detail is in the [Python API](api/index.md).

See the repository's [contribution guide](https://github.com/AllenPeng0209/OpenFabro/blob/main/CONTRIBUTING.md)
for pull requests, documentation conventions, and validation expectations.
