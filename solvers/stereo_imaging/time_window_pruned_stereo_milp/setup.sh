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

install_backend() {
    local package_spec="$1"
    local label="$2"

    if "${VENV_DIR}/bin/python" -m pip install -q "${package_spec}"; then
        echo "  ${label}: install ok"
    else
        echo "  ${label}: install unavailable; continuing because the alternate exact backend may suffice" >&2
    fi
}

install_backend "pulp>=2.9" "PuLP"
install_backend "ortools>=9.11" "OR-Tools"

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
    raise SystemExit(
        "Exact backend unavailable: install OR-Tools or PuLP in the solver-local environment. "
        "Use optimization.backend=greedy only for intentional heuristic runs."
    )
PY
