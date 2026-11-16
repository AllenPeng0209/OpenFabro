# Files and folders

## Projects

`~/OpenFabroProjects/<date>-<name>/` (the folder is set by `projects_dir` in [Settings](settings.md)):

| Path | |
|---|---|
| `revN/` | One folder per build |
| `revN/*.kicad_pro`, `.kicad_sch`, `.kicad_pcb`, `.kicad_dru` | The KiCad project. Open it in KiCad; [your edits are kept](../how-to/kicad-edits.md) |
| `revN/fab/` | Gerber zip, BOM and CPL for JLCPCB; panel files when made |
| `revN/sim/` | The SPICE netlist and plots |
| `revN/firmware/` | The PlatformIO project |
| `revN/quote.json` | The quote |
| `revN/summary.json` | The *History* entry |
| `exports/` | The zipped KiCad project, firmware and bring-up guide |

## OpenFabro's own files

| Path | |
|---|---|
| `~/.openfabro/config.json` | Settings and API keys (readable by your user only on Linux and macOS) |
| `~/.openfabro/blocks/` | [Your own building blocks](../how-to/add-block.md) |
| `~/.openfabro/models3d/` | Downloaded 3D part models |
| `~/.openfabro/tools/` | Tools the installer fetched (FreeCAD AppImage) |
| `~/.openfabro/kikit-py/` | KiKit, for KiCad's Python |
| `~/.openfabro/mcp/` | The MCP server's working copies |
| `~/.openfabro/` | Also library copies and the parts cache |

Set `OPENFABRO_HOME` to choose a settings directory. The older `WHOLEBOARD_HOME` remains supported.

Existing `~/.wholeboard/config.json` and `~/WholeBoardProjects` are reused when the new
defaults have not been configured. An existing `projects_dir` setting is retained; no project
files or credentials are moved by the rename.

## In the repository

| Path | |
|---|---|
| `wholeboard/jlc/pricing.json` | JLCPCB's board, assembly and shipping prices (estimates; edit when they change) |
| `wholeboard/jlc/capabilities.json` | JLCPCB's manufacturing limits for the rules file |
| `bench/prompts.json`, `bench/results/`, `bench/RESULTS.md` | The benchmark |
