from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
EXPERIMENT_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG = EXPERIMENT_DIR / "config.yaml"


@dataclass(frozen=True)
class Job:
    solver: dict[str, Any]
    case: dict[str, Any]

    @property
    def benchmark_id(self) -> str:
        return str(self.solver["benchmark"])

    @property
    def solver_id(self) -> str:
        return str(self.solver["id"])

    @property
    def case_id(self) -> str:
        return str(self.case["id"])


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file_obj:
        data = yaml.safe_load(file_obj)
    if not isinstance(data, dict):
        raise ValueError(f"expected mapping in {path}")
    return data


def _load_profile(kind: str, name: str) -> dict[str, Any]:
    return _load_yaml(EXPERIMENT_DIR / kind / f"{name}.yaml")


def _slug(value: str) -> str:
    return value.replace("/", "__").replace(" ", "_")


def _result_dir(results_root: Path, job: Job) -> Path:
    return results_root / job.benchmark_id / job.solver_id / _slug(job.case_id)


def _select_jobs(
    matrix: dict[str, Any],
    *,
    benchmark_filter: str | None,
    solver_filter: str | None,
    case_filter: str | None,
) -> list[Job]:
    solvers = [_load_profile("solvers", name) for name in matrix["solvers"]]

    jobs: list[Job] = []
    for solver in solvers:
        if benchmark_filter and solver["benchmark"] != benchmark_filter:
            continue
        if solver_filter and solver["id"] != solver_filter:
            continue

        cases = solver.get("cases")
        if cases is None and not solver.get("runnable", False):
            metrics_path = solver.get("metrics_path")
            if metrics_path:
                cases = [
                    {"id": row["case_id"], "case_dir": None}
                    for row in _metrics_by_case(REPO_ROOT / metrics_path).values()
                ]
        for case in cases or []:
            if case_filter and case["id"] != case_filter:
                continue
            jobs.append(Job(solver=solver, case=case))
    return jobs


def _run_command(
    command: list[str],
    *,
    cwd: Path,
    stdout_path: Path,
    stderr_path: Path,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
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
    return {
        "command": command,
        "cwd": str(cwd),
        "returncode": completed.returncode,
        "duration_seconds": time.monotonic() - start,
        "stdout": str(stdout_path),
        "stderr": str(stderr_path),
    }


def _script_command(solver_path: Path, script_path: Path) -> str:
    return f"./{script_path.relative_to(solver_path).as_posix()}"


def _read_solver_env_file(solver_path: Path) -> dict[str, str]:
    env_path = solver_path / ".solver-env"
    if not env_path.exists():
        return {}

    values: dict[str, str] = {}
    for line_number, raw_line in enumerate(env_path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(f"malformed solver env line {line_number} in {env_path}")
        key, value = line.split("=", 1)
        if not re.fullmatch(r"SOLVER_[A-Z0-9_]*", key):
            raise ValueError(f"unsupported solver env key {key!r} in {env_path}")
        values[key] = value
    return values


def _run_setup(
    solver: dict[str, Any],
    *,
    results_root: Path,
    setup_cache: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    solver_id = str(solver["id"])
    if solver_id in setup_cache:
        return setup_cache[solver_id]

    solver_path = REPO_ROOT / solver["solver_path"]
    setup_script = solver_path / solver.get("setup_script", "setup.sh")
    log_dir = results_root / "_setup" / solver_id
    result = _run_command(
        [_script_command(solver_path, setup_script)],
        cwd=solver_path,
        stdout_path=log_dir / "setup.stdout.log",
        stderr_path=log_dir / "setup.stderr.log",
    )
    if result["returncode"] == 0:
        solver_env = _read_solver_env_file(solver_path)
        if solver_env:
            result["solver_env_file"] = str(solver_path / ".solver-env")
            result["solver_env"] = solver_env
    setup_cache[solver_id] = result
    return result


def _format_command(command: list[str], values: dict[str, str]) -> list[str]:
    return [part.format(**values) for part in command]


def _parse_spot5_verifier(stdout: str, returncode: int) -> dict[str, Any]:
    match = re.search(r"(VALID|INVALID): profit=(\d+), weight=(\d+)", stdout)
    if match is None:
        return {
            "status": "error",
            "valid": None,
            "returncode": returncode,
            "parse_error": "SPOT5 verifier output did not match compact schema",
        }
    valid = match.group(1) == "VALID"
    return {
        "status": "valid" if valid else "invalid",
        "valid": valid,
        "returncode": returncode,
        "computed_profit": int(match.group(2)),
        "computed_weight": int(match.group(3)),
    }


def _parse_json_verifier(stdout: str, returncode: int) -> dict[str, Any]:
    stripped = stdout.strip()
    if not stripped:
        return {
            "status": "error",
            "valid": None,
            "returncode": returncode,
            "parse_error": "JSON verifier produced no stdout",
        }
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError as exc:
        return {
            "status": "error",
            "valid": None,
            "returncode": returncode,
            "parse_error": f"JSON verifier stdout could not be parsed: {exc}",
        }
    if not isinstance(payload, dict):
        return {
            "status": "error",
            "valid": None,
            "returncode": returncode,
            "parse_error": "JSON verifier stdout must be an object",
        }
    valid = payload.get("valid")
    if valid is None:
        valid = payload.get("is_valid")
    if not isinstance(valid, bool):
        return {
            "status": "error",
            "valid": None,
            "returncode": returncode,
            "parse_error": "JSON verifier report must contain boolean key 'valid' or 'is_valid'",
            "report": payload,
        }
    return {
        "status": "valid" if valid else "invalid",
        "valid": valid,
        "returncode": returncode,
        "metrics": payload.get("metrics", {}),
        "errors": payload.get("errors", []),
        "violations": payload.get("violations", []),
        "warnings": payload.get("warnings", []),
        "diagnostics": payload.get("diagnostics", {}),
        "report": payload,
    }


def _verify_solution(job: Job, solution_path: Path, *, log_dir: Path) -> dict[str, Any]:
    case_dir = REPO_ROOT / job.case["case_dir"]
    verifier_config = job.solver.get("verifier")
    if not verifier_config:
        return {"status": "not_run", "reason": "solver profile has no verifier command"}

    command = _format_command(
        verifier_config["command"],
        {
            "case_dir": str(case_dir),
            "solution_path": str(solution_path),
        },
    )
    run = _run_command(
        command,
        cwd=REPO_ROOT,
        stdout_path=log_dir / "verifier.stdout.log",
        stderr_path=log_dir / "verifier.stderr.log",
    )
    stdout = (log_dir / "verifier.stdout.log").read_text(encoding="utf-8")
    if job.benchmark_id == "spot5":
        parsed = _parse_spot5_verifier(stdout, run["returncode"])
    elif job.benchmark_id in ("aeossp_standard", "stereo_imaging", "revisit_constellation"):
        parsed = _parse_json_verifier(stdout, run["returncode"])
    else:
        parsed = {
            "status": "error",
            "valid": None,
            "returncode": run["returncode"],
            "parse_error": f"no parser configured for benchmark {job.benchmark_id!r}",
        }
    parsed["execution"] = run
    if run["returncode"] not in {0, 1}:
        parsed["status"] = "error"
        parsed["valid"] = None
    return parsed


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _read_solver_status(path: Path) -> dict[str, Any]:
    try:
        status = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {"status": "malformed_status", "error": str(exc)}
    if not isinstance(status, dict):
        return {"status": "malformed_status", "error": "status.json must contain an object"}
    return status


def _run_runnable_job(
    job: Job,
    *,
    results_root: Path,
    setup_cache: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    result_dir = _result_dir(results_root, job)
    config_dir = result_dir / "config"
    solution_dir = result_dir / "solution"
    log_dir = result_dir / "logs"
    if result_dir.exists():
        shutil.rmtree(result_dir)
    config_dir.mkdir(parents=True, exist_ok=True)
    solution_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    solver_config = job.solver.get("config", {})
    if not isinstance(solver_config, dict):
        raise ValueError(f"solver profile {job.solver_id!r} config must be a mapping")
    (config_dir / "config.yaml").write_text(
        yaml.safe_dump(solver_config, sort_keys=True),
        encoding="utf-8",
    )

    setup = _run_setup(job.solver, results_root=results_root, setup_cache=setup_cache)
    payload: dict[str, Any] = {
        "benchmark": job.benchmark_id,
        "solver": job.solver_id,
        "case_id": job.case_id,
        "case_dir": job.case.get("case_dir"),
        "evidence_type": job.solver["evidence_type"],
        "runnable": True,
        "setup": setup,
        "solver_config": solver_config,
        "solution_dir": str(solution_dir),
    }
    if setup["returncode"] != 0:
        payload["status"] = "setup_error"
        _write_json(result_dir / "run.json", payload)
        return payload

    solver_path = REPO_ROOT / job.solver["solver_path"]
    solve_script = solver_path / job.solver.get("solve_script", "solve.sh")
    solve_env = os.environ.copy()
    solve_env.update(setup.get("solver_env", {}))
    solve = _run_command(
        [
            _script_command(solver_path, solve_script),
            str((REPO_ROOT / job.case["case_dir"]).resolve()),
            str(config_dir.resolve()),
            str(solution_dir.resolve()),
        ],
        cwd=solver_path,
        stdout_path=log_dir / "solve.stdout.log",
        stderr_path=log_dir / "solve.stderr.log",
        env=solve_env,
    )
    payload["solve"] = solve
    status_path = solution_dir / "status.json"
    if status_path.exists():
        payload["solver_status"] = _read_solver_status(status_path)

    if solve["returncode"] != 0:
        payload["status"] = "solver_error"
        solver_status = payload.get("solver_status")
        if isinstance(solver_status, dict) and solver_status.get("status") == "unsupported_case":
            payload["status"] = "unsupported_case"
        _write_json(result_dir / "run.json", payload)
        return payload

    solution_path = solution_dir / job.solver["solution_filename"]
    payload["solution_path"] = str(solution_path)
    if not solution_path.exists():
        payload["status"] = "missing_solution"
        _write_json(result_dir / "run.json", payload)
        return payload

    verifier = _verify_solution(job, solution_path, log_dir=log_dir)
    payload["verifier"] = verifier
    payload["status"] = "verified" if verifier.get("valid") is True else "verification_failed"
    _write_json(result_dir / "run.json", payload)
    return payload


def _metrics_by_case(metrics_path: Path) -> dict[str, dict[str, Any]]:
    metrics = _load_yaml(metrics_path)
    return {str(row["case_id"]): row for row in metrics.get("cases", [])}


def _run_literature_job(job: Job, *, results_root: Path) -> dict[str, Any]:
    result_dir = _result_dir(results_root, job)
    metrics_path = REPO_ROOT / job.solver["metrics_path"]
    metrics = _load_yaml(metrics_path)
    case_metrics = _metrics_by_case(metrics_path).get(job.case_id)
    payload = {
        "benchmark": job.benchmark_id,
        "solver": job.solver_id,
        "case_id": job.case_id,
        "case_dir": job.case.get("case_dir"),
        "evidence_type": job.solver["evidence_type"],
        "runnable": False,
        "status": "reported",
        "metrics_path": str(metrics_path),
        "provenance": metrics.get("provenance", {}),
        "reported_metrics": case_metrics,
    }
    if case_metrics is None:
        payload["status"] = "missing_reported_metrics"
    _write_json(result_dir / "run.json", payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Run main solver experiment jobs")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--benchmark")
    parser.add_argument("--solver")
    parser.add_argument("--case")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    matrix = _load_yaml(Path(args.config))
    results_root = REPO_ROOT / matrix.get("results_root", "results/main_solver")
    jobs = _select_jobs(
        matrix,
        benchmark_filter=args.benchmark,
        solver_filter=args.solver,
        case_filter=args.case,
    )

    if args.dry_run:
        for job in jobs:
            print(f"{job.benchmark_id} {job.solver_id} {job.case_id}")
        print(f"{len(jobs)} job(s)")
        return 0

    setup_cache: dict[str, dict[str, Any]] = {}
    failures = 0
    for job in jobs:
        if job.solver.get("runnable", False):
            payload = _run_runnable_job(job, results_root=results_root, setup_cache=setup_cache)
        else:
            payload = _run_literature_job(job, results_root=results_root)
        print(f"{payload['status']}: {job.benchmark_id} {job.solver_id} {job.case_id}")
        if payload["status"] not in {"verified", "reported"}:
            failures += 1
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
