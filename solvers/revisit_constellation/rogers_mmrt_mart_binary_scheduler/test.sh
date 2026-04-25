#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/.solver-env"

: "${MPLCONFIGDIR:=/tmp/astroreason-matplotlib}"
export MPLCONFIGDIR
mkdir -p "${MPLCONFIGDIR}"

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

if [[ -z "${SOLVER_PYTHON:-}" && -z "${SOLVER_VENV_DIR:-}" ]]; then
  if [[ ! -x "${PYTHON_BIN}" ]] || ! "${PYTHON_BIN}" - <<'PY'
import brahe
import numpy
import pulp
import yaml
PY
  then
    "${SCRIPT_DIR}/setup.sh"
    PYTHON_BIN="${SCRIPT_DIR}/.venv/bin/python"
  fi
fi

if [[ ! -x "${PYTHON_BIN}" ]]; then
  echo "solver-local Python not found or not executable: ${PYTHON_BIN}" >&2
  echo "run ${SCRIPT_DIR}/setup.sh first, or set SOLVER_PYTHON/SOLVER_VENV_DIR to a prepared solver environment" >&2
  exit 2
fi

if ! "${PYTHON_BIN}" - <<'PY'
import pytest
PY
then
  "${PYTHON_BIN}" -m pip install -q -r "${SCRIPT_DIR}/requirements-test.txt"
fi

cd "${SCRIPT_DIR}"
PYTHONPATH="${SCRIPT_DIR}${PYTHONPATH:+:${PYTHONPATH}}" "${PYTHON_BIN}" -m pytest tests "$@"
