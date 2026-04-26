from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from experiments.main_solver.aggregate import _revisit_metric
from experiments.main_solver.run import (
    DEFAULT_CONFIG,
    _load_yaml,
    _parse_json_verifier,
    _select_jobs,
)


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


def test_parse_json_verifier_records_revisit_report() -> None:
    payload = {
        "is_valid": True,
        "metrics": {"capped_max_revisit_gap_hours": 1.25},
        "errors": [],
        "warnings": ["diagnostic note"],
    }

    parsed = _parse_json_verifier(json.dumps(payload), 0)

    assert parsed["status"] == "valid"
    assert parsed["valid"] is True
    assert parsed["metrics"] == {"capped_max_revisit_gap_hours": 1.25}
    assert parsed["violations"] == []
    assert parsed["diagnostics"] == {"warnings": ["diagnostic note"]}


def test_parse_json_verifier_merges_warnings_and_falls_back_from_null_violations() -> None:
    payload = {
        "valid": False,
        "metrics": {},
        "violations": None,
        "errors": ["bad schedule"],
        "warnings": ["top-level"],
        "diagnostics": {"warnings": ["diagnostic"], "note": "kept"},
    }

    parsed = _parse_json_verifier(json.dumps(payload), 0)

    assert parsed["status"] == "invalid"
    assert parsed["violations"] == ["bad schedule"]
    assert parsed["diagnostics"] == {
        "warnings": ["diagnostic", "top-level"],
        "note": "kept",
    }


def test_revisit_aggregation_prefers_verifier_primary_metric() -> None:
    payload = {
        "verifier": {
            "metrics": {
                "capped_max_revisit_gap_hours": 9.5,
                "target_gap_summary": {
                    "target-a": {
                        "max_revisit_gap_hours": 20.0,
                        "expected_revisit_period_hours": 8.0,
                    }
                },
            }
        }
    }

    assert _revisit_metric(payload, "capped_max_revisit_gap_hours") == 9.5


def test_revisit_aggregation_handles_empty_target_rows() -> None:
    payload = {"verifier": {"metrics": {"target_gap_summary": {"bad": None}}}}

    assert _revisit_metric(payload, "max_revisit_gap_hours") == 0.0


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
