#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${SCRIPT_DIR}/.venv"
PYTHON_BIN="${VENV_DIR}/bin/python"

export UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/astroreason-uv-cache}"
export UV_LINK_MODE="${UV_LINK_MODE:-copy}"
mkdir -p "${UV_CACHE_DIR}"

uv venv "${VENV_DIR}" --python 3.13 --clear
uv pip install --python "${PYTHON_BIN}" -r "${SCRIPT_DIR}/requirements.txt"

cat > "${SCRIPT_DIR}/.solver-env" <<EOF
SOLVER_VENV_DIR=${VENV_DIR}
SOLVER_PYTHON=${PYTHON_BIN}
EOF

"${PYTHON_BIN}" - <<'PY'
import brahe
import numpy
import ortools
import shapely
import yaml

print("regional_coverage cp_local_search setup ok")
print(f"ortools={ortools.__version__}")
PY
