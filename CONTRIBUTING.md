# Contributing to OpenFabro

Thank you for helping build an open engineering workspace for complete hardware devices.
Contributions may include code, reproducible bug reports, engineering test cases, documentation,
and improvements to the design workflow.

## Before you begin

Read the [README](README.md), [development guide](docs/development.md), and relevant
[architecture decisions](docs/decisions/index.md). For substantial changes, open an issue to
describe the problem and proposed behavior before investing in an implementation.

Keep changes focused. Preserve existing design files and compatibility unless the change calls
for a migration. Do not commit credentials, local projects, generated builds, or private supplier
and customer information.

## Development environment

```sh
git clone https://github.com/AllenPeng0209/OpenFabro.git
cd OpenFabro
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev,docs]"
npm ci
npm run vendor
```

On Windows, use `py -m venv .venv` and run Python commands with
`.\.venv\Scripts\python.exe`. The Python package includes the committed browser assets;
Node.js 22 or newer is needed for frontend dependencies and browser tests.

Start the workspace with `./run-workbench.sh` on macOS/Linux, or `python -m openfabro` on any
supported platform. Run `python -m openfabro.doctor` to inspect native tool availability.
Native integration coverage requires the relevant engineering tools and KiCad libraries.

## Validation

```sh
python -m pytest tests -q
npm test
python -m mkdocs build --strict
python scripts/verify-package.py
```

Run checks relevant to your change. For user-visible interactions, include browser validation:

```sh
npx playwright install chromium
npm run test:browser -- --suite=production
```

The `--suite` argument selects browser test filenames containing the supplied text. Omitting it
runs the standard browser suite. Mechanical suites are available with `--mechanical` and require
their native tools. The runner creates isolated test workspaces and removes its temporary data;
artifacts are written to the ignored `test-results/` directory. It does not place factory orders.

Report exact commands, outcomes, and skipped coverage. Unit tests do not establish native export,
simulation, manufacturing, or physical acceptance.

## Code and documentation

- Keep the `openfabro` public entry points and `wholeboard` compatibility namespace working.
- Follow the surrounding Python and JavaScript style; avoid unrelated formatting changes.
- Preserve version checks, file provenance, input validation, and immutable production archives.
- Add meaningful regression coverage for behavior changes. Documentation-only changes generally
  need a documentation build and link review.
- Put user documentation in `docs/`. Generated reference pages are maintained through
  `docs/gen.py`; do not edit generated site output.
- Record significant engineering decisions in `docs/decisions/` and user-visible changes in
  `CHANGELOG.md`.
- Retain upstream attribution and bundled dependency licenses.

## Pull requests

Create a branch and open a focused pull request against `main`. Explain the problem, resulting
behavior, validation, and remaining limits. Include screenshots for interface changes and an
anonymized minimal fixture for engineering regressions when possible.

By submitting a contribution, you agree that it may be distributed under the repository's
[GPL-3.0-or-later license](LICENSE). Third-party material must retain its compatible license and
attribution. Be respectful, discuss technical disagreements with evidence, and protect private
information.
