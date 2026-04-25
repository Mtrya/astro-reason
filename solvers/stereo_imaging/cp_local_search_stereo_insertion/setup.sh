#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${MPLCONFIGDIR:-}" ]]; then
  MPLCONFIGDIR="$(mktemp -d)"
fi
export MPLCONFIGDIR
mkdir -p "${MPLCONFIGDIR}"

python - <<'PY'
import brahe
import numpy
import yaml
import skyfield

print("cp_local_search_stereo_insertion setup ok")
PY
