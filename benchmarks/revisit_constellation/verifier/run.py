"""CLI entry point for the revisit_constellation verifier."""

from __future__ import annotations

import argparse
from pathlib import Path

from .engine import verify_solution


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify a revisit_constellation solution against one case directory."
    )
    parser.add_argument(
        "case_dir",
        help="Path to the case directory containing assets.json and mission.json",
    )
    parser.add_argument(
        "solution_path",
        help="Path to the solver-produced solution.json file",
    )
    args = parser.parse_args(argv)

    result = verify_solution(args.case_dir, args.solution_path)
    print(result)
    return 0 if result.is_valid else 1


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
