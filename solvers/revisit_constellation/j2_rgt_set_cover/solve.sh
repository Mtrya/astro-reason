#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -z "${SOLVER_PYTHON:-}" && -f "${SCRIPT_DIR}/.solver-env" ]]; then
  # shellcheck disable=SC1091
  source "${SCRIPT_DIR}/.solver-env"
fi
SOLVER_PYTHON="${SOLVER_PYTHON:-${SCRIPT_DIR}/.venv/bin/python}"
if [[ ! -x "${SOLVER_PYTHON}" ]]; then
  echo "j2_rgt_set_cover requires solver-local setup; run ./setup.sh first" >&2
  exit 2
fi

PYTHONPATH="${SCRIPT_DIR}${PYTHONPATH:+:${PYTHONPATH}}" "${SOLVER_PYTHON}" -m src.solve "$@"
