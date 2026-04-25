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

"${VENV_DIR}/bin/python" - <<'PY'
import brahe
import numpy
import pulp
import yaml

solver = pulp.PULP_CBC_CMD(msg=False)
cbc_ok = bool(solver.available())

print("rogers_mmrt_mart_binary_scheduler setup ok")
print("  Environment: solver-local .venv")
if cbc_ok:
    print("  PuLP/CBC: available")
else:
    print("  PuLP/CBC: not available; exact backend modes will fail until CBC is available")
PY

{
  printf 'SOLVER_VENV_DIR=%s\n' "${VENV_DIR}"
  printf 'SOLVER_PYTHON=%s\n' "${VENV_DIR}/bin/python"
} > "${ENV_FILE}"

echo "  Environment handoff: ${ENV_FILE}"
