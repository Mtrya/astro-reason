"""Experiment-level integration tests for the relay MCLP+TEG solver."""

from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

import yaml

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
RUN_PY = REPO_ROOT / "experiments" / "main_solver" / "run.py"
AGGREGATE_PY = REPO_ROOT / "experiments" / "main_solver" / "aggregate.py"
PROFILE_PATH = REPO_ROOT / "experiments" / "main_solver" / "solvers" / "relay_mclp_teg.yaml"


def _load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def test_solver_profile_loads() -> None:
    profile = _load_yaml(PROFILE_PATH)
    assert profile["id"] == "relay_mclp_teg"
    assert profile["benchmark"] == "relay_constellation"
    assert profile["evidence_type"] == "reproduced_solver"
    assert profile["runnable"] is True
    assert profile["solution_filename"] == "solution.json"
    assert "verifier" in profile
    assert len(profile.get("cases", [])) == 5


def test_dry_run_lists_relay_jobs() -> None:
    result = subprocess.run(
        [sys.executable, str(RUN_PY), "--dry-run", "--benchmark", "relay_constellation"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0
    lines = result.stdout.strip().splitlines()
    assert any("relay_constellation" in line for line in lines)
    assert any("relay_mclp_teg" in line for line in lines)
    assert any("case_0001" in line for line in lines)
    assert "5 job(s)" in lines[-1]


def _make_temp_config(tmp_path: Path) -> Path:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        f"results_root: {tmp_path / 'results'}\n\nsolvers:\n  - relay_mclp_teg\n",
        encoding="utf-8",
    )
    return config_path


@pytest.mark.timeout(600)
def test_experiment_smoke_case_0001(tmp_path: Path) -> None:
    config_path = _make_temp_config(tmp_path)
    result = subprocess.run(
        [
            sys.executable,
            str(RUN_PY),
            "--config",
            str(config_path),
            "--benchmark",
            "relay_constellation",
            "--solver",
            "relay_mclp_teg",
            "--case",
            "test/case_0001",
        ],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        env={**dict(subprocess.os.environ), "PYTHONPATH": str(REPO_ROOT)},
    )
    print("STDOUT:", result.stdout)
    print("STDERR:", result.stderr)
    assert result.returncode == 0, f"run.py exited {result.returncode}: {result.stderr}"

    results_root = tmp_path / "results"
    run_json_path = (
        results_root
        / "relay_constellation"
        / "relay_mclp_teg"
        / "test__case_0001"
        / "run.json"
    )
    assert run_json_path.exists()
    payload = json.loads(run_json_path.read_text(encoding="utf-8"))

    assert payload["benchmark"] == "relay_constellation"
    assert payload["solver"] == "relay_mclp_teg"
    assert payload["case_id"] == "test/case_0001"
    assert payload["evidence_type"] == "reproduced_solver"
    assert payload["runnable"] is True
    assert payload["status"] == "verified"

    verifier = payload.get("verifier", {})
    assert verifier.get("valid") is True
    metrics = verifier.get("metrics", {})
    assert "service_fraction" in metrics
    assert metrics["service_fraction"] > 0.0

    solver_status = payload.get("solver_status", {})
    assert isinstance(solver_status, dict)
    assert "execution_model" in solver_status
    assert "timings_s" in solver_status

    # Verify the solution file exists
    solution_dir = Path(payload["solution_dir"])
    assert (solution_dir / "solution.json").exists()
    assert (solution_dir / "status.json").exists()


@pytest.mark.timeout(600)
def test_aggregate_includes_relay_metrics(tmp_path: Path) -> None:
    config_path = _make_temp_config(tmp_path)
    results_root = tmp_path / "results"
    # First run the smoke case
    subprocess.run(
        [
            sys.executable,
            str(RUN_PY),
            "--config",
            str(config_path),
            "--benchmark",
            "relay_constellation",
            "--solver",
            "relay_mclp_teg",
            "--case",
            "test/case_0001",
        ],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        env={**dict(subprocess.os.environ), "PYTHONPATH": str(REPO_ROOT)},
        check=True,
    )

    # Then aggregate
    result = subprocess.run(
        [sys.executable, str(AGGREGATE_PY), "--results-root", str(results_root)],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0, f"aggregate.py exited {result.returncode}: {result.stderr}"

    csv_path = results_root / "summary.csv"
    assert csv_path.exists()

    with csv_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    assert "service_fraction" in reader.fieldnames
    assert "worst_demand_service_fraction" in reader.fieldnames
    assert "mean_latency_ms" in reader.fieldnames
    assert "latency_p95_ms" in reader.fieldnames
    assert "num_added_satellites" in reader.fieldnames

    relay_rows = [r for r in rows if r["benchmark"] == "relay_constellation"]
    assert len(relay_rows) >= 1
    row = relay_rows[0]
    assert row["solver"] == "relay_mclp_teg"
    assert row["status"] == "verified"
    assert row["valid"] == "True"
    assert float(row["service_fraction"]) > 0.0
