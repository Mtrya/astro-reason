"""CLI entrypoint for the aeossp_standard verifier."""

from __future__ import annotations

import argparse
import json

from .engine import verify_solution


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify aeossp_standard observation schedules against a canonical case.",
    )
    parser.add_argument("case_dir", help="Path to one canonical case directory")
    parser.add_argument("solution_path", help="Path to a single-case solution JSON file")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = verify_solution(args.case_dir, args.solution_path)
    print(
        json.dumps(
            {
                "valid": result.valid,
                "metrics": result.metrics,
                "violations": result.violations,
                "diagnostics": result.diagnostics,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if result.valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
