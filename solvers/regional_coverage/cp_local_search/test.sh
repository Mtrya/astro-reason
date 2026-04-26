#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
if [[ -z "${SOLVER_PYTHON:-}" && -f ".solver-env" ]]; then
  # shellcheck disable=SC1091
  source ".solver-env"
fi
SOLVER_PYTHON="${SOLVER_PYTHON:-$(pwd)/.venv/bin/python}"
if [[ ! -x "${SOLVER_PYTHON}" ]]; then
  echo "regional_coverage cp_local_search tests require solver-local setup; run ./setup.sh first" >&2
  exit 2
fi
"${SOLVER_PYTHON}" -m pytest tests
