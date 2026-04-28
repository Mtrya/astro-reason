#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CASE_DIR="${1:?usage: ./solve.sh <case_dir> [config_dir] [solution_dir]}"
CONFIG_DIR="${2:-}"
SOLUTION_DIR="${3:-solution}"

: "${MPLCONFIGDIR:=/tmp/astroreason-matplotlib}"
export MPLCONFIGDIR
mkdir -p "${MPLCONFIGDIR}"

PYTHON_BIN="${PYTHON:-python3}"
VENV_DIR="${SOLVER_VENV_DIR:-${SCRIPT_DIR}/.venv}"

PYTHONPATH="${SCRIPT_DIR}${PYTHONPATH:+:${PYTHONPATH}}"
if [[ -x "${VENV_DIR}/bin/python" ]]; then
    VENV_SITE_PACKAGES=$("${VENV_DIR}/bin/python" -c "import sys, os; print(os.path.join(os.path.dirname(os.path.dirname(sys.executable)), 'lib', f'python{sys.version_info.major}.{sys.version_info.minor}', 'site-packages'))" 2>/dev/null || true)
    if [[ -n "${VENV_SITE_PACKAGES}" && -d "${VENV_SITE_PACKAGES}" ]]; then
        PYTHONPATH="${PYTHONPATH}:${VENV_SITE_PACKAGES}"
    fi
fi

PYTHONPATH="${PYTHONPATH}" "${PYTHON_BIN}" -m src.solve \
  --case-dir "${CASE_DIR}" \
  --config-dir "${CONFIG_DIR}" \
  --solution-dir "${SOLUTION_DIR}"
