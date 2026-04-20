#!/usr/bin/env python3
"""Aggregate run artifacts for the main agentic experiment family."""

from __future__ import annotations

import argparse
from pathlib import Path


FAMILY_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG = FAMILY_DIR / "configs" / "matrix.yaml"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Aggregate main agentic run artifacts into reviewable summaries (scaffold only)"
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help="Matrix config whose results should be aggregated.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    raise SystemExit(
        "\n".join(
            [
                "main_agentic aggregation scaffold is in place but aggregation is not implemented yet.",
                f"Config: {args.config.resolve()}",
            ]
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
