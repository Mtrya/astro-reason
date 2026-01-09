#!/bin/bash
# Clean up test artifacts from sandbox_template.
#
# Usage: ./cleanup_sandbox.sh
#
# This removes all generated files while preserving the template structure.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SANDBOX_ROOT="$SCRIPT_DIR/sandbox_template"

echo "Cleaning sandbox_template..."
echo ""

# Function to clean a sandbox directory (sandbox/ or sandbox_template/)
clean_sandbox_dir() {
    local sandbox_dir="$1"

    if [ ! -d "$sandbox_dir" ]; then
        echo "Skipping: $sandbox_dir (not found)"
        return
    fi
    
    echo "Cleaning: $sandbox_dir"
    
    # 1. Clean ~/.cache (where ~ is $HOME which is sandbox/ or sandbox_template/)
    if [ -d "$sandbox_dir/.cache" ]; then
        echo "  Removing .cache/"
        rm -rf "$sandbox_dir/.cache"
    fi
    
    # 2. Clean specific ~/.claude subdirectories
    local claude_subdirs="debug file-history plan plugins projects session-env shell-snapshots statsig telemetry todos"
    for subdir in $claude_subdirs; do
        local path="$sandbox_dir/.claude/$subdir"
        if [ -d "$path" ]; then
            echo "  Removing .claude/$subdir/"
            rm -rf "$path"
        fi
    done
    
    # 3. Clean ~/.config
    if [ -d "$sandbox_dir/.config" ]; then
        echo "  Removing .config/"
        rm -rf "$sandbox_dir/.config"
    fi
    
    # 4. Clean ~/state (but keep structure for template)
    if [ -d "$sandbox_dir/state" ]; then
        echo "  Cleaning state/"
        find "$sandbox_dir/state" -type f ! -name '.gitkeep' -delete
    fi
    
    # 5. Clean workspace (keep only specific files/dirs)
    if [ -d "$sandbox_dir/workspace" ]; then
        echo "  Cleaning workspace/"
        
        # Iterate over files; handle empty directory case
        shopt -s nullglob
        for file in "$sandbox_dir/workspace"/*; do
            local basename=$(basename "$file")
            
            # Skip protected files
            if [[ "$basename" == ".gitkeep" ]] || \
               [[ "$basename" == ".claude" ]] || \
               [[ "$basename" == "satnet_agent" ]] || \
               [[ "$basename" == ".mcp.json" ]] || \
               [[ "$basename" == "mcp_server.py" ]]; then
                continue
            fi
            
            # Delete everything else
            echo "    Removing workspace/$basename"
            rm -rf "$file"
        done
        shopt -u nullglob
    fi
    
    # 6. Clean .claude.json and .claude.json.backup
    for file in "$sandbox_dir/.claude.json" "$sandbox_dir/.claude.json.backup"; do
        if [ -f "$file" ]; then
            echo "  Removing $(basename "$file")"
            rm -f "$file"
        fi
    done
    
    echo ""
}

# Clean sandbox_template
clean_sandbox_dir "$SANDBOX_ROOT"

echo "============================================================="
echo "Cleanup complete!"
echo ""
echo "Template preserved:"
echo "  workspace/.gitkeep"
echo "  workspace/.mcp.json"
echo "  workspace/.claude/"
echo "  workspace/satnet_agent/"
echo "  workspace/mcp_server.py"
echo "  state/.gitkeep"
echo "============================================================="
