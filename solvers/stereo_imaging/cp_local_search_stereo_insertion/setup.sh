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

print("cp_local_search_stereo_insertion setup ok")
PY
