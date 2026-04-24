#!/usr/bin/env bash
set -euo pipefail

: "${MPLCONFIGDIR:=/tmp/astroreason-matplotlib}"
export MPLCONFIGDIR
mkdir -p "${MPLCONFIGDIR}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Install solver-local Python dependencies when available
if command -v pip >/dev/null 2>&1; then
    pip install -q -r "${SCRIPT_DIR}/requirements.txt" || true
fi

python - <<'PY'
import brahe
import numpy
import yaml
import skyfield

try:
    import ortools
    ortools_ok = True
except Exception:
    ortools_ok = False

try:
    import pulp
    pulp_ok = True
except Exception:
    pulp_ok = False

print("time_window_pruned_stereo_milp setup ok")
if ortools_ok:
    print("  OR-Tools: available")
else:
    print("  OR-Tools: not installed (greedy fallback will be used)")
if pulp_ok:
    print("  PuLP: available")
else:
    print("  PuLP: not installed")
PY
