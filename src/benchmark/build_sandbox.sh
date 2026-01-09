#!/bin/bash
# Build the sandbox_template with required packages and code.
#
# Usage: ./build_sandbox.sh
#
# Run this script whenever you update engine/planner source code to sync
# changes to the sandbox workspace.
#
# This prepares the sandbox environment:
# - Installs MCP dependencies to lib/ (for MCP server)
# - Copies engine/ and planner/ source to workspace/ (for agent to use)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
LIB_DIR="$SCRIPT_DIR/sandbox_template/lib"
WORKSPACE_DIR="$SCRIPT_DIR/sandbox_template/workspace"

# Use system Python (whichever version claude will use)
PYTHON=${PYTHON:-python3}

echo "Building sandbox environment..."
echo "Using Python: $PYTHON ($($PYTHON --version))"
echo "Project root: $PROJECT_ROOT"

# Clean lib directory
echo ""
echo "Installing MCP dependencies to lib/..."
rm -rf "$LIB_DIR"
mkdir -p "$LIB_DIR"

# Install MCP and dependencies
uv pip install --python "$PYTHON" --target="$LIB_DIR" --quiet "mcp>=1.19.0" pydantic pyyaml requests

# Clean and copy engine to workspace
echo "Copying engine/ source to workspace/..."
rm -rf "$WORKSPACE_DIR/engine"
cp -r "$PROJECT_ROOT/src/engine" "$WORKSPACE_DIR/engine"

# Clean and copy planner to workspace
echo "Copying planner/ source to workspace/..."
rm -rf "$WORKSPACE_DIR/planner"
cp -r "$PROJECT_ROOT/src/planner" "$WORKSPACE_DIR/planner"

# Verify
echo ""
echo "MCP library installed to lib/:"
ls -1 "$LIB_DIR" | head -10

echo ""
echo "Source code in workspace/:"
echo "  engine/:"
ls -1 "$WORKSPACE_DIR/engine" | head -5
echo "  planner/:"
ls -1 "$WORKSPACE_DIR/planner" | head -5

echo ""
echo "Testing imports..."
cd "$WORKSPACE_DIR"
"$PYTHON" -c "from engine.models import Satellite, Target; print('✓ engine import OK')"
"$PYTHON" -c "from planner.scenario import Scenario; print('✓ planner import OK')"
PYTHONPATH="../lib" "$PYTHON" -c "from mcp.server.fastmcp import FastMCP; print('✓ MCP import OK (with PYTHONPATH)')"

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
