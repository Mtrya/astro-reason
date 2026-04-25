#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CASE_DIR="${1:?usage: ./solve.sh <case_dir> [config_dir] [solution_dir]}"
CONFIG_DIR="${2:-}"
SOLUTION_DIR="${3:-solution}"
ENV_FILE="${SCRIPT_DIR}/.solver-env"

if [[ -z "${SOLVER_PYTHON:-}" && -z "${SOLVER_VENV_DIR:-}" && -f "${ENV_FILE}" ]]; then
  while IFS= read -r line || [[ -n "${line}" ]]; do
    [[ -z "${line}" || "${line}" == \#* ]] && continue
    key="${line%%=*}"
    value="${line#*=}"
    case "${key}" in
      SOLVER_PYTHON)
        SOLVER_PYTHON="${value}"
        ;;
      SOLVER_VENV_DIR)
        SOLVER_VENV_DIR="${value}"
        ;;
    esac
  done < "${ENV_FILE}"
fi

if [[ -n "${SOLVER_PYTHON:-}" ]]; then
  PYTHON_BIN="${SOLVER_PYTHON}"
elif [[ -n "${SOLVER_VENV_DIR:-}" ]]; then
  PYTHON_BIN="${SOLVER_VENV_DIR}/bin/python"
else
  PYTHON_BIN="${SCRIPT_DIR}/.venv/bin/python"
fi

if [[ ! -x "${PYTHON_BIN}" ]]; then
  echo "solver-local Python not found or not executable: ${PYTHON_BIN}" >&2
  echo "run ${SCRIPT_DIR}/setup.sh first, or set SOLVER_PYTHON/SOLVER_VENV_DIR to a prepared solver environment" >&2
  exit 2
fi

: "${MPLCONFIGDIR:=/tmp/astroreason-matplotlib}"
export MPLCONFIGDIR
mkdir -p "${MPLCONFIGDIR}"

PYTHONPATH="${SCRIPT_DIR}/src${PYTHONPATH:+:${PYTHONPATH}}" "${PYTHON_BIN}" "${SCRIPT_DIR}/src/solve.py" \
  --case-dir "${CASE_DIR}" \
  --config-dir "${CONFIG_DIR}" \
  --solution-dir "${SOLUTION_DIR}"
