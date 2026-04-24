"""Mode comparison sweep for the MCLP+TEG relay solver.

Runs all public cases through multiple solver modes and captures verifier metrics.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
SOLVER_DIR = REPO_ROOT / "solvers" / "relay_constellation" / "mclp_teg_contact_plan"
CASES_ROOT = REPO_ROOT / "benchmarks" / "relay_constellation" / "dataset" / "cases" / "test"
VERIFIER_MODULE = "benchmarks.relay_constellation.verifier.run"


MODES = [
    ("no_added_greedy", {"mclp_mode": "none", "scheduler_mode": "greedy"}),
    ("mclp_greedy_greedy", {"mclp_mode": "greedy", "scheduler_mode": "greedy"}),
    ("mclp_milp_greedy", {"mclp_mode": "milp", "scheduler_mode": "greedy"}),
    ("mclp_greedy_auto", {"mclp_mode": "greedy", "scheduler_mode": "auto"}),
]


def _find_cases() -> list[Path]:
    cases = sorted(p for p in CASES_ROOT.iterdir() if p.is_dir())
    return cases


def _run_solver(case_dir: Path, config: dict) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        config_dir = tmp_path / "config"
        solution_dir = tmp_path / "solution"
        config_dir.mkdir()
        solution_dir.mkdir()
        (config_dir / "config.json").write_text(
            json.dumps(config, indent=2) + "\n", encoding="utf-8"
        )

        t0 = __import__("time").monotonic()
        solve_result = subprocess.run(
            [
                sys.executable,
                "-m",
                "solvers.relay_constellation.mclp_teg_contact_plan.src.solve",
                "--case-dir",
                str(case_dir),
                "--config-dir",
                str(config_dir),
                "--solution-dir",
                str(solution_dir),
            ],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
            env={**dict(__import__("os").environ), "PYTHONPATH": str(REPO_ROOT)},
        )
        solve_time = __import__("time").monotonic() - t0

        status_path = solution_dir / "status.json"
        status = json.loads(status_path.read_text(encoding="utf-8")) if status_path.exists() else {}

        solution_path = solution_dir / "solution.json"
        if solve_result.returncode != 0 or not solution_path.exists():
            return {
                "case_id": case_dir.name,
                "mode": config.get("mclp_mode", "?") + "+" + config.get("scheduler_mode", "?"),
                "solver_error": True,
                "solver_stderr": solve_result.stderr,
                "solve_time_s": round(solve_time, 2),
                "status": status,
            }

        # Run verifier
        t0 = __import__("time").monotonic()
        verifier_result = subprocess.run(
            [
                sys.executable,
                "-m",
                VERIFIER_MODULE,
                str(case_dir),
                str(solution_path),
            ],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
            env={**dict(__import__("os").environ), "PYTHONPATH": str(REPO_ROOT)},
        )
        verifier_time = __import__("time").monotonic() - t0

        verifier_stdout = verifier_result.stdout.strip()
        try:
            verifier_json = json.loads(verifier_stdout) if verifier_stdout else {}
        except json.JSONDecodeError:
            verifier_json = {"raw_stdout": verifier_stdout}

        metrics = verifier_json.get("metrics", {})
        return {
            "case_id": case_dir.name,
            "mode": config.get("mclp_mode", "?") + "+" + config.get("scheduler_mode", "?"),
            "solver_error": False,
            "valid": verifier_json.get("valid"),
            "service_fraction": metrics.get("service_fraction"),
            "worst_demand_service_fraction": metrics.get("worst_demand_service_fraction"),
            "mean_latency_ms": metrics.get("mean_latency_ms"),
            "latency_p95_ms": metrics.get("latency_p95_ms"),
            "num_added_satellites": metrics.get("num_added_satellites"),
            "num_actions": len(json.loads(solution_path.read_text(encoding="utf-8")).get("actions", [])),
            "solve_time_s": round(solve_time, 2),
            "verifier_time_s": round(verifier_time, 2),
            "status": status,
        }


def main() -> int:
    cases = _find_cases()
    if not cases:
        print("No cases found in", CASES_ROOT)
        return 1

    results: list[dict] = []
    for case_dir in cases:
        for mode_name, mode_config in MODES:
            print(f"Running {case_dir.name} with {mode_name} ...", file=sys.stderr)
            result = _run_solver(case_dir, mode_config)
            result["mode_name"] = mode_name
            results.append(result)
            valid_str = "VALID" if result.get("valid") else "INVALID"
            sf = result.get("service_fraction")
            print(
                f"  {valid_str} sf={sf} added={result.get('num_added_satellites')} actions={result.get('num_actions')}"
                f" solve={result['solve_time_s']}s verify={result.get('verifier_time_s', 0)}s",
                file=sys.stderr,
            )

    # Write JSON
    out_dir = SOLVER_DIR / "results"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / "mode_comparison.json"
    out_path.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {out_path}", file=sys.stderr)

    # Print markdown table
    print("\n## Mode Comparison Summary\n")
    print("| case | mode | valid | service_fraction | worst_demand_sf | added | actions | solve_s | verify_s |")
    print("|------|------|-------|------------------|-----------------|-------|---------|---------|----------|")
    for r in results:
        print(
            f"| {r['case_id']} | {r['mode_name']} | {r.get('valid', '?')} | "
            f"{r.get('service_fraction', '-')} | {r.get('worst_demand_service_fraction', '-')} | "
            f"{r.get('num_added_satellites', '-')} | {r.get('num_actions', '-')} | "
            f"{r['solve_time_s']} | {r['verifier_time_s']} |"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
