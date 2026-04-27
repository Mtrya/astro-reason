"""Run canonical profile experiments for the MCLP+TEG relay solver.

This script is solver-local on purpose: it sweeps solver profiles and keeps
per-profile artifacts without changing the generic `experiments/main_solver`
matrix contract.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[4]
SOLVER_DIR = REPO_ROOT / "solvers" / "relay_constellation" / "mclp_teg_contact_plan"
CASES_ROOT = REPO_ROOT / "benchmarks" / "relay_constellation" / "dataset" / "cases" / "test"
RESULTS_ROOT = SOLVER_DIR / "results" / "canonical"
VERIFIER_MODULE = "benchmarks.relay_constellation.verifier.run"
SOLVER_MODULE = "solvers.relay_constellation.mclp_teg_contact_plan.src.solve"


PROFILE_MATRIX: dict[str, dict[str, Any]] = {
    "no_added": {
        "profile": "smoke",
        "config": {
            "profile": "smoke",
            "mclp_mode": "none",
            "scheduler_mode": "route_aware",
        },
        "description": "Backbone-only baseline using the route-aware scheduler.",
    },
    "smoke_default": {
        "profile": "smoke",
        "config": None,
        "description": "Historical lightweight smoke/default profile.",
    },
    "reproduction": {
        "profile": "reproduction",
        "config": None,
        "description": "Meaningful larger-candidate reproduction profile.",
    },
    "quality": {
        "profile": "quality",
        "config": None,
        "description": "Strongest intended optimization profile.",
    },
}


SUMMARY_FIELDS = [
    "profile_name",
    "case_id",
    "status",
    "valid",
    "service_fraction",
    "worst_demand_service_fraction",
    "mean_latency_ms",
    "latency_p95_ms",
    "num_added_satellites",
    "num_actions",
    "solve_time_s",
    "verifier_time_s",
    "candidate_count",
    "mclp_policy",
    "mclp_milp_eligible",
    "mclp_milp_attempted",
    "mclp_milp_fallback_reason",
    "scheduler_mode",
    "scheduler_num_actions",
    "scheduler_route_aware_demands_considered",
    "scheduler_route_aware_demands_routed",
    "scheduler_route_aware_demands_unrouted",
    "scheduler_route_aware_capacity_rejects",
    "parallel_enabled",
    "worker_count",
    "propagation_mode",
    "link_cache_mode",
    "timing_total_s",
    "timing_propagate_candidates_s",
    "timing_build_link_cache_s",
    "timing_mclp_selection_s",
    "timing_scheduler_s",
    "run_dir",
]


def _case_dirs() -> list[Path]:
    return sorted(path for path in CASES_ROOT.iterdir() if path.is_dir())


def _selected(values: list[str] | None, allowed: list[str]) -> list[str]:
    if not values:
        return allowed
    unknown = sorted(set(values) - set(allowed))
    if unknown:
        raise ValueError(f"unknown selection(s): {', '.join(unknown)}")
    return values


def _run_command(
    command: list[str],
    *,
    cwd: Path,
    stdout_path: Path,
    stderr_path: Path,
    env: dict[str, str],
) -> tuple[dict[str, Any], str, str]:
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    start = time.monotonic()
    with stdout_path.open("w", encoding="utf-8") as stdout_obj:
        with stderr_path.open("w", encoding="utf-8") as stderr_obj:
            completed = subprocess.run(
                command,
                cwd=cwd,
                env=env,
                stdout=stdout_obj,
                stderr=stderr_obj,
                check=False,
            )
    execution = {
        "command": command,
        "cwd": str(cwd),
        "returncode": completed.returncode,
        "duration_seconds": time.monotonic() - start,
        "stdout": str(stdout_path),
        "stderr": str(stderr_path),
    }
    return (
        execution,
        stdout_path.read_text(encoding="utf-8"),
        stderr_path.read_text(encoding="utf-8"),
    )


def _write_config(run_dir: Path, profile_name: str, profile_spec: dict[str, Any]) -> Path | None:
    config = profile_spec.get("config")
    if config is None:
        return None
    config_dir = run_dir / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "canonical_profile_name": profile_name,
        **config,
    }
    (config_dir / "config.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return config_dir


def _parse_verifier(stdout: str, returncode: int) -> dict[str, Any]:
    stripped = stdout.strip()
    if not stripped:
        return {
            "status": "error",
            "valid": None,
            "returncode": returncode,
            "parse_error": "verifier produced no stdout",
        }
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError as exc:
        return {
            "status": "error",
            "valid": None,
            "returncode": returncode,
            "parse_error": str(exc),
            "raw_stdout": stripped,
        }
    return {
        "status": "valid" if payload.get("valid") is True else "invalid",
        "valid": payload.get("valid"),
        "returncode": returncode,
        "metrics": payload.get("metrics", {}),
        "violations": payload.get("violations", []),
        "diagnostics": payload.get("diagnostics", {}),
        "report": payload,
    }


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _row_from_run(
    *,
    profile_name: str,
    case_id: str,
    run_dir: Path,
    solve: dict[str, Any],
    verifier: dict[str, Any],
    solver_status: dict[str, Any],
) -> dict[str, Any]:
    metrics = verifier.get("metrics") or {}
    execution_model = solver_status.get("execution_model") or {}
    timings = solver_status.get("timings_s") or {}
    return {
        "profile_name": profile_name,
        "case_id": case_id,
        "status": verifier.get("status") if solve.get("returncode") == 0 else "solver_error",
        "valid": verifier.get("valid"),
        "service_fraction": metrics.get("service_fraction"),
        "worst_demand_service_fraction": metrics.get("worst_demand_service_fraction"),
        "mean_latency_ms": metrics.get("mean_latency_ms"),
        "latency_p95_ms": metrics.get("latency_p95_ms"),
        "num_added_satellites": metrics.get("num_added_satellites"),
        "num_actions": solver_status.get("scheduler_num_actions"),
        "solve_time_s": round(float(solve.get("duration_seconds", 0.0)), 3),
        "verifier_time_s": round(float((verifier.get("execution") or {}).get("duration_seconds", 0.0)), 3),
        "candidate_count": solver_status.get("num_candidate_satellites"),
        "mclp_policy": solver_status.get("mclp_policy"),
        "mclp_milp_eligible": solver_status.get("mclp_milp_eligible"),
        "mclp_milp_attempted": solver_status.get("mclp_milp_attempted"),
        "mclp_milp_fallback_reason": solver_status.get("mclp_milp_fallback_reason"),
        "scheduler_mode": solver_status.get("scheduler_mode"),
        "scheduler_num_actions": solver_status.get("scheduler_num_actions"),
        "scheduler_route_aware_demands_considered": solver_status.get("scheduler_route_aware_demands_considered"),
        "scheduler_route_aware_demands_routed": solver_status.get("scheduler_route_aware_demands_routed"),
        "scheduler_route_aware_demands_unrouted": solver_status.get("scheduler_route_aware_demands_unrouted"),
        "scheduler_route_aware_capacity_rejects": solver_status.get("scheduler_route_aware_capacity_rejects"),
        "parallel_enabled": execution_model.get("parallel_enabled"),
        "worker_count": execution_model.get("worker_count"),
        "propagation_mode": execution_model.get("propagation_mode"),
        "link_cache_mode": execution_model.get("link_cache_mode"),
        "timing_total_s": timings.get("total"),
        "timing_propagate_candidates_s": timings.get("propagate_candidates"),
        "timing_build_link_cache_s": timings.get("build_link_cache"),
        "timing_mclp_selection_s": timings.get("mclp_selection"),
        "timing_scheduler_s": timings.get("scheduler"),
        "run_dir": str(run_dir),
    }


def _write_summary(results_root: Path, rows: list[dict[str, Any]], runs: list[dict[str, Any]]) -> None:
    existing_rows, existing_runs = _scan_existing_results(results_root)
    if existing_rows:
        rows = existing_rows
        runs = existing_runs

    summary = {
        "results_root": str(results_root),
        "profiles": PROFILE_MATRIX,
        "row_count": len(rows),
        "rows": rows,
        "runs": runs,
    }
    results_root.mkdir(parents=True, exist_ok=True)
    (results_root / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with (results_root / "summary.csv").open("w", encoding="utf-8", newline="") as file_obj:
        writer = csv.DictWriter(file_obj, fieldnames=SUMMARY_FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    lines = ["# Canonical MCLP+TEG Results", ""]
    lines.append("| profile | case | valid | service_fraction | worst_demand_sf | added | actions | solve_s | verifier_s | scheduler | candidates |")
    lines.append("|---|---|---:|---:|---:|---:|---:|---:|---:|---|---:|")
    for row in rows:
        lines.append(
            "| {profile_name} | {case_id} | {valid} | {service_fraction} | {worst_demand_service_fraction} | "
            "{num_added_satellites} | {scheduler_num_actions} | {solve_time_s} | {verifier_time_s} | {scheduler_mode} | {candidate_count} |".format(**row)
        )
    lines.append("")
    lines.append("Artifacts are stored in each row's `run_dir`.")
    (results_root / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _scan_existing_results(results_root: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    runs: list[dict[str, Any]] = []
    if not results_root.exists():
        return rows, runs

    for run_json in sorted(results_root.glob("*/*/run.json")):
        payload = _load_json(run_json)
        row = payload.get("row")
        if not isinstance(row, dict):
            continue
        rows.append(row)
        runs.append({
            "profile_name": payload.get("profile_name"),
            "case_id": payload.get("case_id"),
            "run_json": str(run_json),
            "status": row.get("status"),
            "valid": row.get("valid"),
        })
    return rows, runs


def run_one(
    *,
    results_root: Path,
    profile_name: str,
    profile_spec: dict[str, Any],
    case_dir: Path,
    env: dict[str, str],
    force: bool,
) -> tuple[dict[str, Any], dict[str, Any]]:
    case_id = case_dir.name
    run_dir = results_root / profile_name / case_id
    solution_dir = run_dir / "solution"
    run_json_path = run_dir / "run.json"
    if run_json_path.exists() and not force:
        payload = _load_json(run_json_path)
        return payload.get("row", {}), payload

    if run_dir.exists():
        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    config_dir = _write_config(run_dir, profile_name, profile_spec)

    command = [
        sys.executable,
        "-m",
        SOLVER_MODULE,
        "--case-dir",
        str(case_dir),
        "--solution-dir",
        str(solution_dir),
        "--profile",
        str(profile_spec["profile"]),
    ]
    if config_dir is not None:
        command.extend(["--config-dir", str(config_dir)])

    solve, solve_stdout, solve_stderr = _run_command(
        command,
        cwd=REPO_ROOT,
        stdout_path=run_dir / "logs" / "solver.stdout.log",
        stderr_path=run_dir / "logs" / "solver.stderr.log",
        env=env,
    )

    solver_status = _load_json(solution_dir / "status.json")
    verifier: dict[str, Any]
    if solve["returncode"] == 0 and (solution_dir / "solution.json").exists():
        verify_command = [
            sys.executable,
            "-m",
            VERIFIER_MODULE,
            str(case_dir),
            str(solution_dir / "solution.json"),
        ]
        verifier_exec, verifier_stdout, verifier_stderr = _run_command(
            verify_command,
            cwd=REPO_ROOT,
            stdout_path=run_dir / "logs" / "verifier.stdout.log",
            stderr_path=run_dir / "logs" / "verifier.stderr.log",
            env=env,
        )
        verifier = _parse_verifier(verifier_stdout, verifier_exec["returncode"])
        verifier["execution"] = verifier_exec
        (run_dir / "verifier.json").write_text(
            json.dumps(verifier, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    else:
        verifier = {
            "status": "not_run",
            "valid": None,
            "reason": "solver failed or did not write solution.json",
        }

    row = _row_from_run(
        profile_name=profile_name,
        case_id=case_id,
        run_dir=run_dir,
        solve=solve,
        verifier=verifier,
        solver_status=solver_status,
    )
    payload = {
        "profile_name": profile_name,
        "profile": profile_spec,
        "case_id": case_id,
        "case_dir": str(case_dir),
        "solve": solve,
        "solver_stdout_tail": solve_stdout[-4000:],
        "solver_stderr_tail": solve_stderr[-4000:],
        "solver_status": solver_status,
        "verifier": verifier,
        "row": row,
    }
    run_json_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return row, payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Run canonical MCLP+TEG profile experiments")
    parser.add_argument("--results-root", default=str(RESULTS_ROOT))
    parser.add_argument("--profiles", nargs="*", choices=sorted(PROFILE_MATRIX), default=None)
    parser.add_argument("--cases", nargs="*", default=None, help="Case directory names, e.g. case_0001")
    parser.add_argument("--force", action="store_true", help="Rerun even if run.json exists")
    args = parser.parse_args()

    results_root = Path(args.results_root)
    profiles = _selected(args.profiles, list(PROFILE_MATRIX))
    cases = _selected(args.cases, [path.name for path in _case_dirs()])
    case_by_name = {path.name: path for path in _case_dirs()}

    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT)
    env.setdefault("UV_CACHE_DIR", "/tmp/uv-cache")
    env.setdefault("MPLCONFIGDIR", "/tmp/matplotlib-cache")

    rows: list[dict[str, Any]] = []
    runs: list[dict[str, Any]] = []
    for profile_name in profiles:
        profile_spec = PROFILE_MATRIX[profile_name]
        for case_name in cases:
            print(f"running {profile_name} {case_name}", file=sys.stderr, flush=True)
            row, run_payload = run_one(
                results_root=results_root,
                profile_name=profile_name,
                profile_spec=profile_spec,
                case_dir=case_by_name[case_name],
                env=env,
                force=args.force,
            )
            rows.append(row)
            runs.append({
                "profile_name": profile_name,
                "case_id": case_name,
                "run_json": str(results_root / profile_name / case_name / "run.json"),
                "status": row.get("status"),
                "valid": row.get("valid"),
            })
            print(
                f"  {row.get('status')} valid={row.get('valid')} sf={row.get('service_fraction')} "
                f"solve={row.get('solve_time_s')}s verify={row.get('verifier_time_s')}s",
                file=sys.stderr,
                flush=True,
            )
            _write_summary(results_root, rows, runs)

    _write_summary(results_root, rows, runs)
    print(f"wrote {len(rows)} rows to {results_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
