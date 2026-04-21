#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CASE_DIR="${1:?usage: ./solve.sh <case_dir> [config_dir] [solution_dir]}"
CONFIG_DIR="${2:-}"
SOLUTION_DIR="${3:-solution}"

python "${SCRIPT_DIR}/src/lookup.py" \
  --case-dir "${CASE_DIR}" \
  --config-dir "${CONFIG_DIR}" \
  --solution-dir "${SOLUTION_DIR}"
