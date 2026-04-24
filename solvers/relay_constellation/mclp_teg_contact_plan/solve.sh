#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CASE_DIR="${1:?usage: ./solve.sh <case_dir> [config_dir] [solution_dir]}"
CONFIG_DIR="${2:-}"
SOLUTION_DIR="${3:-solution}"

REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"

# Prefer system/project Python for base deps (brahe, numpy, yaml).
# Append solver-local venv site-packages so optional local deps (e.g. pulp) are importable.
PYTHON="python3"
VENV_SITE_PACKAGES="${SCRIPT_DIR}/.venv/lib/python3.13/site-packages"
if [[ -d "${VENV_SITE_PACKAGES}" ]]; then
    PYTHONPATH="${REPO_ROOT}:${VENV_SITE_PACKAGES}${PYTHONPATH:+:${PYTHONPATH}}"
else
    PYTHONPATH="${REPO_ROOT}${PYTHONPATH:+:${PYTHONPATH}}"
fi

PYTHONPATH="${PYTHONPATH}" \
  "${PYTHON}" -m solvers.relay_constellation.mclp_teg_contact_plan.src.solve \
    --case-dir "${CASE_DIR}" \
    --config-dir "${CONFIG_DIR}" \
    --solution-dir "${SOLUTION_DIR}"
