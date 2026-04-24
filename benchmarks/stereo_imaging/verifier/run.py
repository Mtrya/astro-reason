"""CLI entry point for the stereo_imaging v4 verifier."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .engine import verify_solution


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify a stereo_imaging v4 solution against one canonical case directory.",
    )
    parser.add_argument(
        "case_dir",
        help="Path to dataset/cases/<case_id> (contains mission.yaml, satellites.yaml, targets.yaml)",
    )
    parser.add_argument(
        "solution_path",
        help="Path to solution JSON (per-case object with an 'actions' array)",
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        help="Print only valid flag and core metrics (default prints full JSON report)",
    )
    args = parser.parse_args(argv)

    report = verify_solution(args.case_dir, args.solution_path)
    if args.compact:
        print(
            json.dumps(
                {
                    "valid": report.valid,
                    "metrics": report.metrics,
                    "violations": report.violations,
                },
                indent=2,
            )
        )
    else:
        print(json.dumps(report.to_dict(), indent=2))
    return 0 if report.valid else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
