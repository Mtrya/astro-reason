#!/usr/bin/env bash
set -euo pipefail

python - <<'PY'
import yaml

print("celf_submodular setup ok")
PY
