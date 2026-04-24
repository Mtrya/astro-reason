#!/usr/bin/env bash
set -euo pipefail

: "${MPLCONFIGDIR:=/tmp/astroreason-matplotlib}"
export MPLCONFIGDIR
mkdir -p "${MPLCONFIGDIR}"

python - <<'PY'
import brahe
import numpy
import yaml

print("umcf_srr_contact_plan setup ok")
PY
