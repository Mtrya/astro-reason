#!/bin/bash
# Build the sandbox_template with required packages and code.
#
# Usage: ./build_sandbox.sh
#
# Run this script whenever you update satnet_agent source code to sync
# changes to the sandbox workspace.
#
# This prepares the sandbox environment:
# - Installs MCP library to lib/ (for MCP server only)
# - Copies satnet_agent source to workspace/ (for agent to use & edit)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB_DIR="$SCRIPT_DIR/sandbox_template/lib"
WORKSPACE_DIR="$SCRIPT_DIR/sandbox_template/workspace"

# Use system Python (whichever version claude will use)
PYTHON=${PYTHON:-python3}

echo "Building sandbox environment..."
echo "Using Python: $PYTHON ($($PYTHON --version))"

# Clean lib directory
echo ""
echo "Installing MCP library to lib/..."
rm -rf "$LIB_DIR"
mkdir -p "$LIB_DIR"

# Install ONLY MCP and dependencies (not satnet_agent)
uv pip install --python "$PYTHON" --target="$LIB_DIR" --quiet "mcp>=1.19.0"

# Clean and copy satnet_agent to workspace
echo "Installing satnet_agent source to workspace/..."
rm -rf "$WORKSPACE_DIR/satnet_agent"
mkdir -p "$WORKSPACE_DIR/satnet_agent"
mkdir -p "$WORKSPACE_DIR/satnet_agent/adapter"

# Copy all Python files
cp "$SCRIPT_DIR"/__init__.py "$WORKSPACE_DIR/satnet_agent/"
cp "$SCRIPT_DIR"/models.py "$WORKSPACE_DIR/satnet_agent/"
cp "$SCRIPT_DIR"/state.py "$WORKSPACE_DIR/satnet_agent/"
cp "$SCRIPT_DIR"/scenario.py "$WORKSPACE_DIR/satnet_agent/"
cp "$SCRIPT_DIR"/sandbox.py "$WORKSPACE_DIR/satnet_agent/"
cp "$SCRIPT_DIR"/adapter/*.py "$WORKSPACE_DIR/satnet_agent/adapter/"

# Copy mcp_server.py to workspace root (not inside satnet_agent package)
cp "$SCRIPT_DIR"/mcp_server.py "$WORKSPACE_DIR/"

# Verify
echo ""
echo "MCP library installed to lib/:"
ls -1 "$LIB_DIR" | head -10

echo ""
echo "satnet_agent source in workspace/:"
ls -1 "$WORKSPACE_DIR/satnet_agent/"

echo ""
echo "Testing imports..."
cd "$WORKSPACE_DIR"
"$PYTHON" -c "from satnet_agent.scenario import SatNetScenario; print('✓ satnet_agent import OK (no PYTHONPATH needed!)')"
PYTHONPATH="../lib" "$PYTHON" -c "from mcp.server.fastmcp import FastMCP; print('✓ MCP import OK (with PYTHONPATH)')"

echo ""
echo "Sandbox built successfully!"
echo ""
echo "To test locally:"
echo "  source .venv/bin/activate"
echo "  cd $WORKSPACE_DIR"
echo "  HOME=\$(dirname \$(pwd)) claude"
