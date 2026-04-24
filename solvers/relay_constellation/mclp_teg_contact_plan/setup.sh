#!/usr/bin/env bash
set -euo pipefail

python3 - <<'PY'
import brahe
import numpy
import yaml

print("mclp_teg_contact_plan setup ok")
PY
