from __future__ import annotations

import json
from pathlib import Path
import sys

REPO_ROOT_FOR_IMPORT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT_FOR_IMPORT))

from experiments.main_solver.run import DEFAULT_CONFIG, REPO_ROOT, _load_yaml, _select_jobs
from experiments.main_solver.run import _parse_json_verifier


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


def test_parse_json_verifier_rejects_missing_valid() -> None:
    parsed = _parse_json_verifier("{}", 1)

    assert parsed["status"] == "error"
    assert parsed["valid"] is None


def test_parse_json_verifier_rejects_extra_stdout() -> None:
    parsed = _parse_json_verifier('note\n{"valid": true}', 0)

    assert parsed["status"] == "error"
    assert parsed["valid"] is None
    assert "could not be parsed" in parsed["parse_error"]


def test_main_solver_matrix_includes_revisit_constructive_smoke_job() -> None:
    matrix = _load_yaml(DEFAULT_CONFIG)

    jobs = _select_jobs(
        matrix,
        benchmark_filter="revisit_constellation",
        solver_filter="revisit_constellation_rgt_apc_gap_constructive",
        case_filter="test/case_0001",
    )

    assert len(jobs) == 1
    job = jobs[0]
    assert job.solver["evidence_type"] == "reproduced_solver"
    assert job.solver["solver_path"] == "solvers/revisit_constellation/rgt_apc_gap_constructive"
    assert job.solver["solution_filename"] == "solution.json"
    assert job.solver["verifier"]["command"] == [
        "uv",
        "run",
        "python",
        "-m",
        "benchmarks.revisit_constellation.verifier.run",
        "{case_dir}",
        "{solution_path}",
    ]
    assert (REPO_ROOT / job.case["case_dir"]).is_dir()
