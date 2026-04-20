#!/usr/bin/env python3
"""Run the main agentic experiment family."""

from __future__ import annotations

import argparse
from pathlib import Path


FAMILY_DIR = Path(__file__).resolve().parent
DEFAULT_BATCH_CONFIG = FAMILY_DIR / "configs" / "matrix.yaml"
DEFAULT_INTERACTIVE_CONFIG = FAMILY_DIR / "configs" / "interactive.yaml"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the main agentic experiment family (scaffold only)"
    )
    parser.add_argument(
        "--config",
        type=Path,
        help="Override the family config path. Defaults to matrix.yaml or interactive.yaml.",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Use interactive defaults instead of the batch matrix defaults.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    default_config = DEFAULT_INTERACTIVE_CONFIG if args.interactive else DEFAULT_BATCH_CONFIG
    config_path = (args.config or default_config).resolve()
    raise SystemExit(
        "\n".join(
            [
                "main_agentic scaffold is in place but execution is not implemented yet.",
                f"Selected config: {config_path}",
                "Next step: implement matrix planning, batch execution, and aggregation.",
            ]
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
