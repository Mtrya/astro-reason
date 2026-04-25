"""Benchmark solver runtime modes across caller-provided cases."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_SOLVER_DIR = REPO_ROOT / "solvers" / "stereo_imaging" / "time_window_pruned_stereo_milp"

RUNTIME_PAYLOADS: dict[str, dict[str, Any]] = {
    "fast": {
        "runtime": {"mode": "fast"},
        "time_step_s": 60,
        "sample_stride_s": 60,
        "max_candidates_per_interval": 8,
        "use_target_centered_steering": True,
        "steering_along_samples": 1,
        "steering_across_samples": 1,
        "steering_grid_spread_deg": 2.0,
        "parallel_candidate_generation": True,
        "strip_sample_step_s": 10.0,
        "overlap_grid_angles": 4,
        "overlap_grid_radii": 1,
        "pruning": {
            "enabled": True,
            "cluster_gap_s": "auto",
            "max_candidates_per_cluster": "auto",
            "min_candidates_per_cluster": 2,
            "max_total_candidates": 5000,
            "preserve_anchors": True,
            "preserve_products": True,
        },
        "optimization": {
            "backend": "greedy",
            "time_limit_s": 300,
        },
        "debug": False,
    },
    "thorough": {
        "runtime": {"mode": "thorough"},
        "time_step_s": 30,
        "sample_stride_s": 30,
        "max_candidates_per_interval": 20,
        "use_target_centered_steering": True,
        "steering_along_samples": 1,
        "steering_across_samples": 1,
        "steering_grid_spread_deg": 2.0,
        "parallel_candidate_generation": True,
        "strip_sample_step_s": 8.0,
        "overlap_grid_angles": 8,
        "overlap_grid_radii": 3,
        "pruning": {
            "enabled": True,
            "cluster_gap_s": "auto",
            "max_candidates_per_cluster": "auto",
            "min_candidates_per_cluster": 2,
            "max_total_candidates": 10000,
            "preserve_anchors": True,
            "preserve_products": True,
        },
        "optimization": {
            "backend": "ortools",
            "time_limit_s": 1800,
        },
        "debug": False,
    },
}


def _run_case(solver_dir: Path, case_dir: Path, mode: str) -> dict[str, Any]:
    temp_root = Path(tempfile.mkdtemp(prefix=f"stereo_runtime_{mode}_{case_dir.name}_"))
    config_dir = temp_root / "config"
    solution_dir = temp_root / "solution"
    config_dir.mkdir(parents=True, exist_ok=True)
    solution_dir.mkdir(parents=True, exist_ok=True)
    with (config_dir / "config.yaml").open("w", encoding="utf-8") as fh:
        yaml.safe_dump(RUNTIME_PAYLOADS[mode], fh, sort_keys=False)

    start = time.perf_counter()
    proc = subprocess.run(
        ["./solve.sh", str(case_dir), str(config_dir), str(solution_dir)],
        cwd=solver_dir,
        capture_output=True,
        text=True,
    )
    elapsed = time.perf_counter() - start

    status_path = solution_dir / "status.json"
    status = json.loads(status_path.read_text(encoding="utf-8")) if status_path.exists() else None
    result = {
        "case": case_dir.name,
        "mode": mode,
        "returncode": proc.returncode,
        "elapsed_s": elapsed,
        "stdout": proc.stdout.strip(),
        "stderr_tail": proc.stderr[-1000:],
        "status": status,
    }
    shutil.rmtree(temp_root, ignore_errors=True)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark fast/thorough runtime modes on explicit stereo case directories.")
    parser.add_argument("--solver-dir", default=str(DEFAULT_SOLVER_DIR))
    parser.add_argument("--output", default="")
    parser.add_argument(
        "--case-dir",
        action="append",
        required=True,
        help="Case directory to run. Repeat for multiple cases.",
    )
    parser.add_argument("--modes", nargs="*", default=["fast", "thorough"])
    args = parser.parse_args()

    solver_dir = Path(args.solver_dir).resolve()
    case_dirs = [Path(value).resolve() for value in args.case_dir]
    results = []
    for case_dir in case_dirs:
        if not case_dir.is_dir():
            raise FileNotFoundError(f"case directory not found: {case_dir}")
        for mode in args.modes:
            if mode not in RUNTIME_PAYLOADS:
                raise ValueError(f"unsupported mode: {mode}")
            print(f"running {case_dir} / {mode} with solver={solver_dir}")
            results.append(_run_case(solver_dir, case_dir, mode))

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "solver_dir": str(solver_dir),
        "case_dirs": [str(path) for path in case_dirs],
        "modes": args.modes,
        "results": results,
    }
    if args.output:
        output_path = Path(args.output).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    else:
        print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
