#!/bin/bash
# Build the sandbox_template with required packages and code.
#
# Usage: ./build_sandbox.sh
#
# Run this script whenever you update engine/scenario source code to sync
# changes to the sandbox workspace.
#
# This prepares the sandbox environment:
# - Installs MCP dependencies to lib/ (for MCP server)
# - Copies engine/ and scenario/ source to workspace/ (for agent to use)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
LIB_DIR="$SCRIPT_DIR/sandbox_template/lib"
WORKSPACE_DIR="$SCRIPT_DIR/sandbox_template/workspace"

# Use pixi if available, otherwise fallback to system python
if [ -d "$PROJECT_ROOT/.pixi" ]; then
    PYTHON="pixi run python"
    PIP="pixi run pip"
    echo "Using pixi environment..."
else
    PYTHON=${PYTHON:-python3}
    PIP="$PYTHON -m pip"
    echo "Using system Python..."
fi

echo "Building sandbox environment..."
echo "Using Python: $PYTHON ($($PYTHON --version))"
echo "Project root: $PROJECT_ROOT"

# Clean lib directory
echo ""
echo "Installing MCP dependencies to lib/..."
rm -rf "$LIB_DIR"
mkdir -p "$LIB_DIR"

# Install MCP and dependencies
# We use --target to install into the template's lib/ directory
$PIP install --target="$LIB_DIR" --quiet "mcp>=1.25.0" pydantic pyyaml requests

# Clean and copy engine to workspace
echo "Copying engine/ source to workspace/toolkit/engine..."
rm -rf "$WORKSPACE_DIR/toolkit"
mkdir -p "$WORKSPACE_DIR/toolkit"
cp -r "$PROJECT_ROOT/toolkit/engine" "$WORKSPACE_DIR/toolkit/engine"

# Clean and copy scenario to workspace
echo "Copying scenario/ source to workspace/toolkit/scenario..."
cp -r "$PROJECT_ROOT/toolkit/scenario" "$WORKSPACE_DIR/toolkit/scenario"
touch "$WORKSPACE_DIR/toolkit/__init__.py"

# Create symlinks for flat access (to support both 'import engine' and 'from engines.astrox import ...')
echo "Creating symlinks for flat access..."
rm -rf "$WORKSPACE_DIR/engine" "$WORKSPACE_DIR/scenario"
ln -sf toolkit/engine "$WORKSPACE_DIR/engine"
ln -sf toolkit/scenario "$WORKSPACE_DIR/scenario"

# Verify
echo ""
echo "MCP library installed to lib/:"
ls -1 "$LIB_DIR" | head -10

echo ""
echo "Source code in workspace/:"
echo "  toolkit/engine/:"
ls -1 "$WORKSPACE_DIR/toolkit/engine" | head -5
echo "  toolkit/scenario/:"
ls -1 "$WORKSPACE_DIR/toolkit/scenario" | head -5

echo ""
echo "Testing imports..."
cd "$WORKSPACE_DIR"
$PYTHON -c "from engines.astrox.models import Satellite, Target; print('✓ engines.astrox import OK')"
$PYTHON -c "from toolkits.mission_planner.scenario.scenario import Scenario; print('✓ toolkits.mission_planner.scenario import OK')"
$PYTHON -c "from engine.models import Satellite, Target; print('✓ flat engine import OK')"
$PYTHON -c "from scenario.scenario import Scenario; print('✓ flat scenario import OK')"
PYTHONPATH="../lib" $PYTHON -c "from mcp.server.fastmcp import FastMCP; print('✓ MCP import OK (with PYTHONPATH)')"

echo ""
echo "Sandbox built successfully!"
echo ""
echo "=== Testing Instructions ==="
echo ""
echo "1. LOCAL TESTING (cd to workspace and run claude):"
echo "   cd $WORKSPACE_DIR"
echo "   export CASE_PATH=\"$PROJECT_ROOT/tests/fixtures/case_0001\""
echo "   export HOME=\"\$(dirname \$(pwd))\""
echo "   claude"
echo ""
echo "2. INTERACTIVE TESTING (using run_benchmark.py):"
echo "   First, ensure test fixtures exist:"
echo "   python src/benchmark/generate_benchmark_cases.py \\"
echo "     --output-root src/benchmark/data/benchmark_cases \\"
echo "     --num-cases 1 \\"
echo "     --benchmarks revisit-optimization"
echo ""
echo "   Then run interactively:"
echo "   python src/benchmark/run_benchmark.py \\"
echo "     --benchmark revisit-optimization \\"
echo "     --case case_0001 \\"
echo "     --interactive"
echo ""
echo "3. AUTOMATED TESTING IN /tmp:"
echo "   python src/benchmark/run_benchmark.py \\"
echo "     --benchmark revisit-optimization \\"
echo "     --case case_0001 \\"
echo "     --model claude-sonnet-4 \\"
echo "     --output-dir /tmp/astrox_test"
echo ""
