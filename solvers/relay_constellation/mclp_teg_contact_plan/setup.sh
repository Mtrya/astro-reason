#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${SCRIPT_DIR}/.venv"

# Verify base project dependencies are available
python3 - <<'PY'
import brahe, numpy, yaml
print("base deps ok")
PY

# Create solver-local venv if missing
if [[ ! -d "${VENV_DIR}" ]]; then
    if command -v uv &>/dev/null; then
        uv venv "${VENV_DIR}"
    else
        python3 -m venv "${VENV_DIR}"
    fi
fi

# Install solver-local dependencies if pyproject.toml exists
if [[ -f "${SCRIPT_DIR}/pyproject.toml" ]]; then
    if command -v uv &>/dev/null; then
        uv pip install --python "${VENV_DIR}/bin/python" "${SCRIPT_DIR}"
    else
        "${VENV_DIR}/bin/pip" install "${SCRIPT_DIR}"
    fi
fi

# Verify solver-local deps
"${VENV_DIR}/bin/python" - <<'PY'
import pulp
print("pulp ok")
PY

printf "mclp_teg_contact_plan setup ok\n"
