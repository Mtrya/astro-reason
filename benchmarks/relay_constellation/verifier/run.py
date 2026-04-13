"""CLI entry point for the relay_constellation verifier."""

from __future__ import annotations

import argparse

from .engine import verify_solution


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify a relay_constellation solution against one case directory."
    )
    parser.add_argument(
        "case_dir",
        help="Path to dataset/cases/<case_id>",
    )
    parser.add_argument(
        "solution_path",
        help="Path to the solver-produced solution JSON file",
    )
    args = parser.parse_args(argv)

    result = verify_solution(args.case_dir, args.solution_path)
    print(result)
    return 0 if result.valid else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
