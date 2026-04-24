"""Focused tests for relay_constellation wiring in main_solver experiment runner."""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

import pytest

from experiments.main_solver.run import (
    _parse_json_verifier,
    _run_command,
    _verify_solution,
    Job,
)


def test_parse_json_verifier_relay_constellation_valid() -> None:
    payload = {
        "valid": True,
        "metrics": {
            "service_fraction": 0.75,
            "worst_demand_service_fraction": 0.5,
            "mean_latency_ms": 120.0,
            "latency_p95_ms": 200.0,
            "num_added_satellites": 2,
        },
        "violations": [],
        "diagnostics": {"note": "ok"},
    }

    parsed = _parse_json_verifier(json.dumps(payload), 0)

    assert parsed["status"] == "valid"
    assert parsed["valid"] is True
    assert parsed["metrics"]["service_fraction"] == 0.75
    assert parsed["diagnostics"]["note"] == "ok"


def test_verify_solution_routes_relay_through_json_parser(tmp_path: Path) -> None:
    # Write a tiny verifier script that prints valid JSON without needing
    # braces in the command string (which would conflict with .format()).
    script = tmp_path / "fake_verifier.py"
    script.write_text(
        'import json\n'
        'print(json.dumps({"valid": True, "metrics": {"service_fraction": 0.8}, "violations": [], "diagnostics": {}}))\n',
        encoding="utf-8",
    )
    solver = {
        "id": "relay_constellation_umcf_srr_contact_plan",
        "benchmark": "relay_constellation",
        "verifier": {
            "command": [
                "python",
                str(script),
            ],
        },
    }
    case = {
        "id": "test/case_0001",
        "case_dir": "benchmarks/relay_constellation/dataset/cases/test/case_0001",
    }
    job = Job(solver=solver, case=case)

    solution_path = tmp_path / "solution.json"
    solution_path.write_text("{}", encoding="utf-8")
    log_dir = tmp_path / "logs"
    log_dir.mkdir()

    result = _verify_solution(job, solution_path, log_dir=log_dir)

    assert result["status"] == "valid"
    assert result["valid"] is True
    assert result["metrics"]["service_fraction"] == 0.8


def test_run_command_timeout_fires() -> None:
    start = time.monotonic()
    result = _run_command(
        ["sleep", "10"],
        cwd=Path("."),
        stdout_path=Path("/dev/null"),
        stderr_path=Path("/dev/null"),
        timeout_seconds=0.5,
    )
    elapsed = time.monotonic() - start

    assert result["timeout"] is True
    assert result["returncode"] == -9
    assert elapsed < 2.0


def test_run_command_no_timeout_completes() -> None:
    result = _run_command(
        ["python", "-c", "print('ok')"],
        cwd=Path("."),
        stdout_path=Path("/dev/null"),
        stderr_path=Path("/dev/null"),
        timeout_seconds=None,
    )

    assert result["timeout"] is False
    assert result["returncode"] == 0
