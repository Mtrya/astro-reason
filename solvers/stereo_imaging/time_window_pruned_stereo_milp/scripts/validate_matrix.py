"""Solver-local validation matrix for the stereo MILP solver.

Runs the solver across multiple configs and caller-provided cases, then records
solver-local status metrics. Official benchmark verification is owned by
experiments/main_solver.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[4]
SOLVER_DIR = REPO_ROOT / "solvers" / "stereo_imaging" / "time_window_pruned_stereo_milp"

CONFIG_MATRIX: list[dict[str, Any]] = [
    {
        "id": "default",
        "description": "Default thorough config: pruning on, OR-Tools exact backend",
        "payload": {},
    },
    {
        "id": "pruning_disabled",
        "description": "Pruning disabled",
        "payload": {"pruning": {"enabled": False}},
    },
    {
        "id": "coarse_time_step",
        "description": "Coarse time step (120s/60s)",
        "payload": {"time_step_s": 120, "sample_stride_s": 60},
    },
    {
        "id": "dense_steering",
        "description": "Dense steering grid (5x5)",
        "payload": {"steering_along_samples": 5, "steering_across_samples": 5},
    },
    {
        "id": "explicit_greedy",
        "description": "Explicit greedy heuristic, no pruning",
        "payload": {"pruning": {"enabled": False}, "optimization": {"backend": "greedy"}},
    },
]

@dataclass
class RunResult:
    case: str
    config_id: str
    solved: bool
    coverage_ratio: float
    normalized_quality: float
    selected_observations: int
    total_pairs: int
    valid_pairs: int
    total_tris: int
    valid_tris: int
    pre_candidates: int
    post_candidates: int
    backend_used: str
    total_runtime_s: float
    solver_status: str
    error: str | None = None


@dataclass
class ValidationReport:
    generated_at: str
    solver_dir: str
    cases: list[str]
    configs: list[str]
    results: list[RunResult] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "solver_dir": self.solver_dir,
            "cases": self.cases,
            "configs": self.configs,
            "results": [asdict(r) for r in self.results],
        }


def _run_solver(case_dir: Path, config_payload: dict[str, Any], solution_dir: Path) -> dict[str, Any]:
    config_path = solution_dir / "config.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with config_path.open("w", encoding="utf-8") as fh:
        import yaml
        yaml.dump(config_payload, fh)

    start = time.perf_counter()
    proc = subprocess.run(
        ["./solve.sh", str(case_dir), str(config_path.parent), str(solution_dir)],
        cwd=SOLVER_DIR,
        capture_output=True,
        text=True,
    )
    elapsed = time.perf_counter() - start

    if proc.returncode != 0:
        return {"error": f"solve.sh failed: {proc.stderr}", "elapsed": elapsed}

    status_path = solution_dir / "status.json"
    if not status_path.exists():
        return {"error": "status.json missing", "elapsed": elapsed}

    status = json.loads(status_path.read_text(encoding="utf-8"))
    status["elapsed"] = elapsed
    return status


def main() -> int:
    from datetime import datetime, timezone

    parser = argparse.ArgumentParser(description="Run solver-local config/case matrix and record status metrics.")
    parser.add_argument(
        "--case-dir",
        action="append",
        required=True,
        help="Case directory to solve. Repeat for multiple cases.",
    )
    parser.add_argument(
        "--config",
        action="append",
        choices=[cfg["id"] for cfg in CONFIG_MATRIX],
        help="Config id to run. Repeat to select multiple configs. Defaults to all configs.",
    )
    parser.add_argument("--output", default=str(SOLVER_DIR / "VALIDATION_REPORT.json"))
    args = parser.parse_args()

    selected_configs = [cfg for cfg in CONFIG_MATRIX if not args.config or cfg["id"] in set(args.config)]
    case_dirs = [Path(value).resolve() for value in args.case_dir]

    report = ValidationReport(
        generated_at=datetime.now(timezone.utc).isoformat(),
        solver_dir=str(SOLVER_DIR),
        cases=[str(path) for path in case_dirs],
        configs=[c["id"] for c in selected_configs],
    )

    for case_dir in case_dirs:
        if not case_dir.is_dir():
            raise FileNotFoundError(f"case directory not found: {case_dir}")
        case = case_dir.name

        for cfg in selected_configs:
            config_id = cfg["id"]
            print(f"Running {case} / {config_id} ...", end=" ", flush=True)
            solution_dir = Path("/tmp") / "stereo_validation" / case / config_id
            if solution_dir.exists():
                import shutil
                shutil.rmtree(solution_dir)
            solution_dir.mkdir(parents=True, exist_ok=True)

            status = _run_solver(case_dir, cfg["payload"], solution_dir)
            if "error" in status and "solve_summary" not in status:
                print(f"SOLVER_ERROR: {status['error']}")
                report.results.append(
                    RunResult(
                        case=case,
                        config_id=config_id,
                        solved=False,
                        coverage_ratio=0.0,
                        normalized_quality=0.0,
                        selected_observations=0,
                        total_pairs=0,
                        valid_pairs=0,
                        total_tris=0,
                        valid_tris=0,
                        pre_candidates=0,
                        post_candidates=0,
                        backend_used="unknown",
                        total_runtime_s=status.get("elapsed", 0.0),
                        solver_status="error",
                        error=status["error"],
                    )
                )
                continue

            solve_summary = status.get("solve_summary", {})
            product_counts = status.get("product_counts", {})
            pruning_summary = status.get("pruning_summary", {})

            result = RunResult(
                case=case,
                config_id=config_id,
                solved=status.get("status") == "solved",
                coverage_ratio=solve_summary.get("coverage_ratio", 0.0),
                normalized_quality=solve_summary.get("normalized_quality", 0.0),
                selected_observations=solve_summary.get("selected_observations", 0),
                total_pairs=product_counts.get("total_pairs", 0),
                valid_pairs=product_counts.get("valid_pairs", 0),
                total_tris=product_counts.get("total_tris", 0),
                valid_tris=product_counts.get("valid_tris", 0),
                pre_candidates=pruning_summary.get("pre_candidates", 0),
                post_candidates=pruning_summary.get("post_candidates", 0),
                backend_used=solve_summary.get("backend_used", "unknown"),
                total_runtime_s=status.get("elapsed", 0.0),
                solver_status=status.get("status", "unknown"),
            )
            report.results.append(result)
            print(
                f"solved={result.solved} "
                f"candidates={result.pre_candidates}/{result.post_candidates} "
                f"pairs={result.valid_pairs}/{result.total_pairs} "
                f"tris={result.valid_tris}/{result.total_tris} "
                f"obs={result.selected_observations} "
                f"time={result.total_runtime_s:.1f}s"
            )

    report_path = Path(args.output).resolve()
    with report_path.open("w", encoding="utf-8") as fh:
        json.dump(report.as_dict(), fh, indent=2)
    print(f"\nWrote validation report to {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
