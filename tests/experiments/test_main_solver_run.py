from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from experiments.main_solver.aggregate import _rows
from experiments.main_solver.run import Job, _parse_json_verifier, _result_dir


def test_parse_json_verifier_records_aeossp_report() -> None:
    payload = {
        "valid": True,
        "metrics": {"CR": 0.5},
        "violations": [],
        "diagnostics": {"note": "ok"},
    }

    parsed = _parse_json_verifier(json.dumps(payload), 0)

    assert parsed["status"] == "valid"
    assert parsed["valid"] is True
    assert parsed["metrics"] == {"CR": 0.5}
    assert parsed["diagnostics"] == {"note": "ok"}


def test_parse_json_verifier_rejects_missing_valid() -> None:
    parsed = _parse_json_verifier("{}", 1)

    assert parsed["status"] == "error"
    assert parsed["valid"] is None


def test_parse_json_verifier_rejects_extra_stdout() -> None:
    parsed = _parse_json_verifier('note\n{"valid": true}', 0)

    assert parsed["status"] == "error"
    assert parsed["valid"] is None
    assert "could not be parsed" in parsed["parse_error"]


def test_policy_result_directory_preserves_policy_artifacts(tmp_path: Path) -> None:
    job = Job(
        solver={"benchmark": "example_benchmark", "id": "example_solver"},
        case={"id": "suite/case_001"},
        solver_config={},
        policy_id="large_policy",
        policy={},
    )

    result_dir = _result_dir(tmp_path, job)

    assert result_dir == (
        tmp_path
        / "example_benchmark"
        / "example_solver"
        / "suite__case_001__large_policy"
    )


def test_parse_json_verifier_records_coverage_metrics() -> None:
    payload = {
        "valid": True,
        "metrics": {
            "coverage_ratio": 0.1,
            "weighted_coverage_ratio": 0.2,
            "num_actions": 3,
            "min_battery_wh": 12.5,
        },
        "violations": [],
        "diagnostics": {"actions": []},
    }

    parsed = _parse_json_verifier(json.dumps(payload), 0)

    assert parsed["status"] == "valid"
    assert parsed["valid"] is True
    assert parsed["metrics"]["coverage_ratio"] == 0.1
    assert parsed["metrics"]["weighted_coverage_ratio"] == 0.2


def test_aggregate_rows_include_coverage_metrics(tmp_path: Path) -> None:
    run_dir = (
        tmp_path
        / "example_benchmark"
        / "example_solver"
        / "suite__case_001"
    )
    run_dir.mkdir(parents=True)
    (run_dir / "run.json").write_text(
        json.dumps(
            {
                "benchmark": "example_benchmark",
                "solver": "example_solver",
                "case_id": "suite/case_001",
                "status": "verified",
                "evidence_type": "reproduced_solver",
                "runnable": True,
                "verifier": {
                    "valid": True,
                    "metrics": {
                        "coverage_ratio": 0.25,
                        "weighted_coverage_ratio": 0.2,
                        "num_actions": 3,
                        "min_battery_wh": 12.5,
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    rows = _rows(tmp_path)

    assert rows[0]["coverage_ratio"] == 0.25
    assert rows[0]["weighted_coverage_ratio"] == 0.2
    assert rows[0]["num_actions"] == 3
    assert rows[0]["min_battery_wh"] == 12.5
