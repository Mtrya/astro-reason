#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${SOLVER_VENV_DIR:-${SCRIPT_DIR}/.venv}"
PYTHON_BIN="${VENV_DIR}/bin/python"

export UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/astroreason-uv-cache}"
export UV_LINK_MODE="${UV_LINK_MODE:-copy}"
mkdir -p "${UV_CACHE_DIR}"

if command -v uv >/dev/null 2>&1; then
  uv venv "${VENV_DIR}" --python 3.13 --clear
  uv pip install --python "${PYTHON_BIN}" "${SCRIPT_DIR}"
else
  python3.13 -m venv "${VENV_DIR}"
  "${PYTHON_BIN}" -m pip install "${SCRIPT_DIR}"
fi

cat > "${SCRIPT_DIR}/.solver-env" <<ENV
SOLVER_VENV_DIR=${VENV_DIR}
SOLVER_PYTHON=${PYTHON_BIN}
ENV

PYTHONPATH="${SCRIPT_DIR}" "${PYTHON_BIN}" - <<'PY'
import brahe
import numpy
import pulp
import yaml

print("mclp_teg_contact_plan setup ok")
print(f"pulp={pulp.__version__}")
PY
