from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from experiments.main_solver.run import DEFAULT_CONFIG, _load_yaml, _parse_json_verifier, _select_jobs


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


def test_main_solver_selects_regional_coverage_cp_local_search_smoke_case() -> None:
    matrix = _load_yaml(DEFAULT_CONFIG)

    jobs = _select_jobs(
        matrix,
        benchmark_filter="regional_coverage",
        solver_filter="regional_coverage_cp_local_search",
        case_filter="test/case_0001",
    )

    assert len(jobs) == 1
    job = jobs[0]
    assert job.benchmark_id == "regional_coverage"
    assert job.solver_id == "regional_coverage_cp_local_search"
    assert job.case["case_dir"] == "benchmarks/regional_coverage/dataset/cases/test/case_0001"
    assert job.solver["evidence_type"] == "reproduced_solver"
    assert job.solver["verifier"]["command"][:4] == [
        "uv",
        "run",
        "python",
        "benchmarks/regional_coverage/verifier.py",
    ]


def test_parse_json_verifier_records_regional_coverage_metrics() -> None:
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
