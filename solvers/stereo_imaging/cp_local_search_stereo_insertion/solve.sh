#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CASE_DIR="${1:?usage: ./solve.sh <case_dir> [config_dir] [solution_dir]}"
CONFIG_DIR="${2:-}"
SOLUTION_DIR="${3:-solution}"

: "${MPLCONFIGDIR:=/tmp/astroreason-matplotlib}"
export MPLCONFIGDIR
mkdir -p "${MPLCONFIGDIR}"

PYTHONPATH="${SCRIPT_DIR}/src${PYTHONPATH:+:${PYTHONPATH}}" python "${SCRIPT_DIR}/src/solve.py" \
  --case-dir "${CASE_DIR}" \
  --config-dir "${CONFIG_DIR}" \
  --solution-dir "${SOLUTION_DIR}"
