#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CASE_DIR="${1:?usage: ./solve.sh <case_dir> [config_dir] [solution_dir]}"
CONFIG_DIR="${2:-}"
SOLUTION_DIR="${3:-solution}"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"

: "${MPLCONFIGDIR:=/tmp/astroreason-matplotlib}"
export MPLCONFIGDIR
mkdir -p "${MPLCONFIGDIR}"

PYTHONPATH="${REPO_ROOT}${PYTHONPATH:+:${PYTHONPATH}}" python -m solvers.revisit_constellation.rogers_mmrt_mart_binary_scheduler.src.solve \
  --case-dir "${CASE_DIR}" \
  --config-dir "${CONFIG_DIR}" \
  --solution-dir "${SOLUTION_DIR}"
