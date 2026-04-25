#!/usr/bin/env bash
set -euo pipefail

: "${MPLCONFIGDIR:=/tmp/astroreason-matplotlib}"
export MPLCONFIGDIR
mkdir -p "${MPLCONFIGDIR}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${SOLVER_VENV_DIR:-${SCRIPT_DIR}/.venv}"
PYTHON_BIN="${PYTHON:-python3}"
ENV_FILE="${SCRIPT_DIR}/.solver-env"
VENV_DIR="$("${PYTHON_BIN}" -c 'import pathlib, sys; print(pathlib.Path(sys.argv[1]).expanduser().resolve())' "${VENV_DIR}")"

if [[ ! -x "${VENV_DIR}/bin/python" ]]; then
    mkdir -p "$(dirname "${VENV_DIR}")"
    "${PYTHON_BIN}" -m venv "${VENV_DIR}"
fi

if [[ -f "${VENV_DIR}/pyvenv.cfg" ]] && grep -qi '^include-system-site-packages *= *true' "${VENV_DIR}/pyvenv.cfg"; then
    echo "solver environment at ${VENV_DIR} uses system site packages" >&2
    echo "remove it or set SOLVER_VENV_DIR to a clean isolated environment, then rerun setup.sh" >&2
    exit 2
fi

"${VENV_DIR}/bin/python" -m pip install -q -r "${SCRIPT_DIR}/requirements.txt"

install_backend() {
    local package_spec="$1"
    local label="$2"

    if "${VENV_DIR}/bin/python" -m pip install -q "${package_spec}"; then
        echo "  ${label}: install ok"
    else
        echo "  ${label}: install unavailable; exact OR-Tools mode will fail until it is installed" >&2
    fi
}

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

print("time_window_pruned_stereo_milp setup ok")
print("  Environment: solver-local .venv")
if ortools_ok:
    print("  OR-Tools: available")
else:
    print("  OR-Tools: not installed")
PY

{
    printf 'SOLVER_VENV_DIR=%s\n' "${VENV_DIR}"
    printf 'SOLVER_PYTHON=%s\n' "${VENV_DIR}/bin/python"
} > "${ENV_FILE}"

echo "  Environment handoff: ${ENV_FILE}"
