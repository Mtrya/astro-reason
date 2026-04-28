#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${SCRIPT_DIR}/.venv"
PYTHON_BIN="${PYTHON:-python3}"

: "${MPLCONFIGDIR:=/tmp/astroreason-matplotlib}"
export MPLCONFIGDIR
mkdir -p "${MPLCONFIGDIR}"

export UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/astroreason-uv-cache}"
export UV_LINK_MODE="${UV_LINK_MODE:-copy}"
mkdir -p "${UV_CACHE_DIR}"

"${PYTHON_BIN}" - <<'PY'
import brahe
import numpy
import yaml

print("base deps ok")
PY

if [[ ! -d "${VENV_DIR}" ]]; then
    if command -v uv &>/dev/null; then
        uv venv "${VENV_DIR}"
    else
        "${PYTHON_BIN}" -m venv "${VENV_DIR}"
    fi
fi

VENV_SITE_PACKAGES=$("${VENV_DIR}/bin/python" -c "import sys, os; print(os.path.join(os.path.dirname(os.path.dirname(sys.executable)), 'lib', f'python{sys.version_info.major}.{sys.version_info.minor}', 'site-packages'))")

if ! PYTHONPATH="${VENV_SITE_PACKAGES}${PYTHONPATH:+:${PYTHONPATH}}" "${PYTHON_BIN}" - <<'PY'
import scipy.optimize
PY
then
    if command -v uv &>/dev/null; then
        uv pip install --python "${VENV_DIR}/bin/python" --no-deps -r "${SCRIPT_DIR}/requirements.txt"
    else
        "${VENV_DIR}/bin/python" -m pip install --no-deps -r "${SCRIPT_DIR}/requirements.txt"
    fi
fi

PYTHONPATH="${VENV_SITE_PACKAGES}${PYTHONPATH:+:${PYTHONPATH}}" "${PYTHON_BIN}" - <<'PY'
import scipy.optimize

print("scipy ok")
PY

cat > "${SCRIPT_DIR}/.solver-env" <<EOF
SOLVER_VENV_DIR=${VENV_DIR}
EOF

printf "umcf_srr_contact_plan setup ok\n"
