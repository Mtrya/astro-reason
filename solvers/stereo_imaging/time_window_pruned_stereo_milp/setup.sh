#!/usr/bin/env bash
set -euo pipefail

: "${MPLCONFIGDIR:=/tmp/astroreason-matplotlib}"
export MPLCONFIGDIR
mkdir -p "${MPLCONFIGDIR}"

python - <<'PY'
import brahe
import numpy
import yaml
import skyfield

print("time_window_pruned_stereo_milp setup ok")
PY
