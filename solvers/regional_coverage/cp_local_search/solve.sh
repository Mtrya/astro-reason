#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CASE_DIR="${1:?usage: ./solve.sh <case_dir> [config_dir] [solution_dir]}"
CONFIG_DIR="${2:-}"
SOLUTION_DIR="${3:-solution}"

if [[ -z "${SOLVER_PYTHON:-}" && -f "${SCRIPT_DIR}/.solver-env" ]]; then
  # shellcheck disable=SC1091
  source "${SCRIPT_DIR}/.solver-env"
fi
SOLVER_PYTHON="${SOLVER_PYTHON:-${SCRIPT_DIR}/.venv/bin/python}"
if [[ ! -x "${SOLVER_PYTHON}" ]]; then
  echo "regional_coverage cp_local_search requires solver-local setup; run ./setup.sh first" >&2
  exit 2
fi

export MPLCONFIGDIR="${MPLCONFIGDIR:-/tmp/astroreason-matplotlib}"
mkdir -p "${MPLCONFIGDIR}"

cd "${SCRIPT_DIR}"
"${SOLVER_PYTHON}" -m src.solve \
  --case-dir "${CASE_DIR}" \
  --config-dir "${CONFIG_DIR}" \
  --solution-dir "${SOLUTION_DIR}"
