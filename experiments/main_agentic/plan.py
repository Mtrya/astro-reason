#!/usr/bin/env python3
"""Plan concrete runs for the main agentic experiment family."""

from __future__ import annotations

import argparse
from pathlib import Path


FAMILY_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG = FAMILY_DIR / "configs" / "matrix.yaml"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plan the main agentic benchmark x harness matrix (scaffold only)"
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help="Matrix config to expand into concrete runs.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the planned matrix without executing anything.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    raise SystemExit(
        "\n".join(
            [
                "main_agentic planner scaffold is in place but planning is not implemented yet.",
                f"Config: {args.config.resolve()}",
            ]
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
