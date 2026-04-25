from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from experiments.main_solver.aggregate import _rows
from experiments.main_solver.run import (
    DEFAULT_CONFIG,
    _result_dir,
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


def test_parse_json_verifier_rejects_missing_valid() -> None:
    parsed = _parse_json_verifier("{}", 1)

    assert parsed["status"] == "error"
    assert parsed["valid"] is None


def test_parse_json_verifier_rejects_extra_stdout() -> None:
    parsed = _parse_json_verifier('note\n{"valid": true}', 0)

    assert parsed["status"] == "error"
    assert parsed["valid"] is None
    assert "could not be parsed" in parsed["parse_error"]


def test_regional_coverage_celf_profile_is_selected_from_default_matrix() -> None:
    matrix = _load_yaml(DEFAULT_CONFIG)

    jobs = _select_jobs(
        matrix,
        benchmark_filter="regional_coverage",
        solver_filter="regional_coverage_celf_submodular",
        case_filter="test/case_0001",
    )

    assert len(jobs) == 1
    job = jobs[0]
    assert job.solver["evidence_type"] == "reproduced_solver"
    assert job.solver["solver_path"] == "solvers/regional_coverage/celf_submodular"
    assert job.solver["solution_filename"] == "solution.json"
    assert job.solver_config["candidate_generation"]["max_candidates_total"] == 512
    assert job.case["case_dir"] == "benchmarks/regional_coverage/dataset/cases/test/case_0001"
    assert "benchmarks/regional_coverage/verifier.py" in job.solver["verifier"]["command"]


def test_regional_coverage_celf_evaluation_policy_selects_all_cases() -> None:
    matrix = _load_yaml(DEFAULT_CONFIG)

    jobs = _select_jobs(
        matrix,
        benchmark_filter="regional_coverage",
        solver_filter="regional_coverage_celf_submodular",
        case_filter=None,
        policy_filter="evaluation",
    )

    assert [job.case_id for job in jobs] == [
        "test/case_0001",
        "test/case_0002",
        "test/case_0003",
        "test/case_0004",
        "test/case_0005",
    ]
    assert {job.policy_id for job in jobs} == {"evaluation"}
    assert all(
        job.solver_config["candidate_generation"]["max_candidates_total"] == 2048
        for job in jobs
    )
    assert all(job.solver_config["coverage_mapping"]["method"] == "indexed" for job in jobs)


def test_policy_result_directory_preserves_policy_artifacts(tmp_path: Path) -> None:
    matrix = _load_yaml(DEFAULT_CONFIG)
    job = _select_jobs(
        matrix,
        benchmark_filter="regional_coverage",
        solver_filter="regional_coverage_celf_submodular",
        case_filter="test/case_0001",
        policy_filter="evaluation",
    )[0]

    result_dir = _result_dir(tmp_path, job)

    assert result_dir == (
        tmp_path
        / "regional_coverage"
        / "regional_coverage_celf_submodular"
        / "test__case_0001__evaluation"
    )


def test_aggregate_rows_include_regional_coverage_metrics(tmp_path: Path) -> None:
    run_dir = (
        tmp_path
        / "regional_coverage"
        / "regional_coverage_celf_submodular"
        / "test__case_0001"
    )
    run_dir.mkdir(parents=True)
    (run_dir / "run.json").write_text(
        json.dumps(
            {
                "benchmark": "regional_coverage",
                "solver": "regional_coverage_celf_submodular",
                "case_id": "test/case_0001",
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
