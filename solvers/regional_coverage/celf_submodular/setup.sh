#!/usr/bin/env bash
set -euo pipefail

python - <<'PY'
import brahe
import numpy
import yaml

print("celf_submodular setup ok")
PY
