"""Compare solver modes: no-added baseline, deterministic SRR, seeded randomized SRR."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT))

from benchmarks.relay_constellation.verifier import verify_solution
from solvers.relay_constellation.umcf_srr_contact_plan.src.solve import solve


CASES = [
    "benchmarks/relay_constellation/dataset/cases/test/case_0001",
    "benchmarks/relay_constellation/dataset/cases/test/case_0002",
    "benchmarks/relay_constellation/dataset/cases/test/case_0003",
    "benchmarks/relay_constellation/dataset/cases/test/case_0004",
    "benchmarks/relay_constellation/dataset/cases/test/case_0005",
]


def _run_mode(case_dir: Path, solution_dir: Path, mode: str) -> dict:
    config_dir = solution_dir / "config"
    config_dir.mkdir(parents=True, exist_ok=True)

    if mode == "no_added":
        config = {"candidate_selection": {"policy": "no-added"}}
    elif mode == "deterministic":
        config = {"candidate_selection": {"policy": "greedy_marginal"}, "srr": {"deterministic": True, "multi_run_count": 1}}
    elif mode == "randomized":
        config = {"candidate_selection": {"policy": "greedy_marginal"}, "srr": {"deterministic": False, "multi_run_count": 8, "seed": 42}}
    else:
        raise ValueError(mode)

    (config_dir / "config.yaml").write_text(json.dumps(config), encoding="utf-8")

    result = solve(case_dir, solution_dir, config_dir)
    verifier_result = verify_solution(case_dir, solution_dir / "solution.json")

    # Read solver status for internal oracle metrics
    status_path = solution_dir / "status.json"
    status = json.loads(status_path.read_text(encoding="utf-8")) if status_path.exists() else {}

    return {
        "mode": mode,
        "case_id": result["summary"]["case_id"],
        "timing_s": result["timing_s"],
        "solver_status": status,
        "verifier": {
            "valid": verifier_result.valid,
            "service_fraction": verifier_result.metrics.get("service_fraction", 0.0),
            "worst_demand_service_fraction": verifier_result.metrics.get("worst_demand_service_fraction", 0.0),
            "mean_latency_ms": verifier_result.metrics.get("mean_latency_ms"),
            "latency_p95_ms": verifier_result.metrics.get("latency_p95_ms"),
            "num_added_satellites": verifier_result.metrics.get("num_added_satellites", 0),
            "num_demanded_windows": verifier_result.metrics.get("num_demanded_windows", 0),
        },
    }


def main() -> int:
    output_dir = Path("results/umcf_srr_mode_comparison")
    output_dir.mkdir(parents=True, exist_ok=True)

    all_results = []
    for case_rel in CASES:
        case_dir = REPO_ROOT / case_rel
        case_id = case_dir.name
        print(f"\n=== {case_id} ===")
        for mode in ["no_added", "deterministic", "randomized"]:
            solution_dir = output_dir / case_id / mode
            if solution_dir.exists():
                import shutil
                shutil.rmtree(solution_dir)
            solution_dir.mkdir(parents=True)
            print(f"  Running {mode} ...", end="", flush=True)
            try:
                row = _run_mode(case_dir, solution_dir, mode)
                all_results.append(row)
                v = row["verifier"]
                print(
                    f" valid={v['valid']}, "
                    f"service={v['service_fraction']:.3f}, "
                    f"worst={v['worst_demand_service_fraction']:.3f}, "
                    f"added={v['num_added_satellites']}"
                )
            except Exception as exc:
                print(f" ERROR: {exc}")
                all_results.append({
                    "mode": mode,
                    "case_id": case_id,
                    "error": str(exc),
                })

    summary_path = output_dir / "comparison_summary.json"
    summary_path.write_text(json.dumps(all_results, indent=2) + "\n", encoding="utf-8")
    print(f"\nWrote {len(all_results)} rows to {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
