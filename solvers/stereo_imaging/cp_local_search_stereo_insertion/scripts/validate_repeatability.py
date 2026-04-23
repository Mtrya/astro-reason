#!/usr/bin/env python3
"""Validate deterministic repeatability of the CP/local-search solver.

Runs the solver twice on the same case with the same config and checks that
solution.json is byte-identical and key status metrics match.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SOLVER_DIR = Path(__file__).resolve().parents[1]


def _run_solver(case_dir: Path, config_dir: Path | None, solution_dir: Path) -> None:
    cmd = [
        str(SOLVER_DIR / "solve.sh"),
        str(case_dir),
        str(config_dir) if config_dir else "",
        str(solution_dir),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        print(f"Solver failed:\n{result.stderr}", file=sys.stderr)
        raise SystemExit(1)


def _load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate solver repeatability")
    parser.add_argument("--case-dir", required=True, help="Path to benchmark case directory")
    parser.add_argument("--config-dir", default=None, help="Optional config directory")
    args = parser.parse_args(argv)

    case_dir = Path(args.case_dir).resolve()
    config_dir = Path(args.config_dir).resolve() if args.config_dir else None

    with tempfile.TemporaryDirectory(prefix="stereo_rep_") as tmp:
        tmp_path = Path(tmp)
        run1 = tmp_path / "run1"
        run2 = tmp_path / "run2"

        print(f"Run 1: {run1}")
        _run_solver(case_dir, config_dir, run1)
        print(f"Run 2: {run2}")
        _run_solver(case_dir, config_dir, run2)

        sol1 = run1 / "solution.json"
        sol2 = run2 / "solution.json"
        if sol1.read_bytes() != sol2.read_bytes():
            print("FAIL: solution.json differs between runs")
            return 1
        print("PASS: solution.json is byte-identical")

        status1 = _load_json(run1 / "status.json")
        status2 = _load_json(run2 / "status.json")

        keys = [
            ("reproduction_summary", "seed_accepted"),
            ("reproduction_summary", "seed_covered_targets"),
            ("reproduction_summary", "local_search_accepted"),
            ("reproduction_summary", "local_search_passes"),
            ("reproduction_summary", "repair_removed"),
            ("reproduction_summary", "final_coverage"),
            ("reproduction_summary", "final_quality"),
        ]

        for section, key in keys:
            v1 = status1.get(section, {}).get(key)
            v2 = status2.get(section, {}).get(key)
            if v1 != v2:
                print(f"FAIL: {section}.{key} differs: {v1} vs {v2}")
                return 1
            print(f"PASS: {section}.{key} = {v1}")

        print("All repeatability checks passed.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
