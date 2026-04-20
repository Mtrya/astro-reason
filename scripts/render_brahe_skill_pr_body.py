#!/usr/bin/env python3
"""Render the Brahe skill sync PR body by substituting {{DIFF_SUMMARY}}."""
import os
import sys
from pathlib import Path


def main() -> int:
    template = Path(".github/PULL_REQUEST_TEMPLATE/brahe_skill_sync.md")
    if not template.exists():
        print(f"Template not found: {template}", file=sys.stderr)
        return 1

    body = template.read_text(encoding="utf-8")
    body = body.replace("{{DIFF_SUMMARY}}", os.environ.get("DIFF_SUMMARY", ""))

    output = Path("/tmp/pr-body.md")
    output.write_text(body, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
