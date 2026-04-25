#!/usr/bin/env bash
set -euo pipefail

: "${MPLCONFIGDIR:=/tmp/astroreason-matplotlib}"
export MPLCONFIGDIR
mkdir -p "${MPLCONFIGDIR}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${SOLVER_VENV_DIR:-${SCRIPT_DIR}/.venv}"
PYTHON_BIN="${PYTHON:-python3}"

if [[ ! -x "${VENV_DIR}/bin/python" ]]; then
    "${PYTHON_BIN}" -m venv --system-site-packages "${VENV_DIR}"
fi

"${VENV_DIR}/bin/python" -m pip install -q -r "${SCRIPT_DIR}/requirements.txt"

"${VENV_DIR}/bin/python" - <<'PY'
import brahe
import numpy
import yaml
import skyfield

try:
    import ortools
    ortools_ok = True
except Exception:
    ortools_ok = False

try:
    import pulp
    pulp_ok = True
except Exception:
    pulp_ok = False

print("time_window_pruned_stereo_milp setup ok")
print("  Environment: solver-local .venv")
if ortools_ok:
    print("  OR-Tools: available")
else:
    print("  OR-Tools: not installed")
if pulp_ok:
    print("  PuLP: available")
else:
    print("  PuLP: not installed")
if not (ortools_ok or pulp_ok):
    print("  Exact backend unavailable: default thorough runs will fail until OR-Tools or PuLP is installed")
    print("  Use optimization.backend=greedy only for intentional heuristic runs")
PY
