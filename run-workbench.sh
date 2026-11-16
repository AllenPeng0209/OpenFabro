#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
  .venv/bin/pip install -e '.[dev]' httpx
fi
openfabro_default_dir="$PWD/.local/openfabro"
if [ -d "$PWD/.local/wholeboard" ] && [ ! -d "$openfabro_default_dir" ]; then
  openfabro_default_dir="$PWD/.local/wholeboard"
fi
export OPENFABRO_HOME="${OPENFABRO_HOME:-${WHOLEBOARD_HOME:-$openfabro_default_dir}}"
.venv/bin/python - <<'PY'
from pathlib import Path
from wholeboard import config
if not config.CONFIG_FILE.exists():
    config.update({"projects_dir": str(Path.cwd() / ".local" / "projects")})
PY
exec .venv/bin/python -m openfabro --host 127.0.0.1 "$@"
