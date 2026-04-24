"""Phase 7 tests: reproduction fidelity, mode comparison, and debug artifacts."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CASE_0001 = REPO_ROOT / "benchmarks" / "relay_constellation" / "dataset" / "cases" / "test" / "case_0001"
SOLVER_MODULE = "solvers.relay_constellation.mclp_teg_contact_plan.src.solve"
VERIFIER_MODULE = "benchmarks.relay_constellation.verifier.run"


def _run_solver(case_dir: Path, config: dict) -> tuple[Path, dict]:
    """Run solver with config, return (solution_dir, status). Caller must clean up."""
    import tempfile

    tmp_path = Path(tempfile.mkdtemp())
    config_dir = tmp_path / "config"
    solution_dir = tmp_path / "solution"
    config_dir.mkdir()
    solution_dir.mkdir()
    (config_dir / "config.json").write_text(
        json.dumps(config, indent=2) + "\n", encoding="utf-8"
    )

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            SOLVER_MODULE,
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
    assert result.returncode == 0, f"solver failed: {result.stderr}"
    status = json.loads((solution_dir / "status.json").read_text(encoding="utf-8"))
    return solution_dir, status


def _run_verifier(case_dir: Path, solution_path: Path) -> dict:
    result = subprocess.run(
        [sys.executable, "-m", VERIFIER_MODULE, str(case_dir), str(solution_path)],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        env={**dict(__import__("os").environ), "PYTHONPATH": str(REPO_ROOT)},
    )
    stdout = result.stdout.strip()
    try:
        return json.loads(stdout) if stdout else {}
    except json.JSONDecodeError:
        return {"raw_stdout": stdout}


# ---- Fast unit tests (no solver invocation) ----

def test_default_grid_generates_24_candidates() -> None:
    """Directly test generate_candidates with default orbit_grid params."""
    from solvers.relay_constellation.mclp_teg_contact_plan.src.case_io import load_case
    from solvers.relay_constellation.mclp_teg_contact_plan.src.orbit_library import generate_candidates

    case = load_case(CASE_0001)
    cands = generate_candidates(
        case.manifest.constraints,
        altitude_step_m=None,
        inclination_step_deg=None,
        num_raan_planes=3,
        num_phase_slots=2,
    )
    assert len(cands) == 24


def test_custom_grid_generates_expected_count() -> None:
    """Directly test generate_candidates with custom orbit_grid params."""
    from solvers.relay_constellation.mclp_teg_contact_plan.src.case_io import load_case
    from solvers.relay_constellation.mclp_teg_contact_plan.src.orbit_library import generate_candidates

    case = load_case(CASE_0001)
    cands = generate_candidates(
        case.manifest.constraints,
        altitude_step_m=None,
        inclination_step_deg=None,
        num_raan_planes=5,
        num_phase_slots=3,
    )
    assert len(cands) == 60


def test_reproduction_summary_structure() -> None:
    """Directly test write_reproduction_summary output."""
    import tempfile
    from solvers.relay_constellation.mclp_teg_contact_plan.src.solution_io import write_reproduction_summary

    with tempfile.TemporaryDirectory() as tmp:
        solution_dir = Path(tmp) / "solution"
        solution_dir.mkdir()
        write_reproduction_summary(
            solution_dir,
            mclp_mode="greedy",
            scheduler_mode="greedy",
            parallel_mode="auto",
            worker_count=8,
            time_budget_s=300,
        )
        repro_path = solution_dir / "debug" / "reproduction_summary.json"
        assert repro_path.exists()
        payload = json.loads(repro_path.read_text(encoding="utf-8"))
        assert "paper_components" in payload
        assert "benchmark_adaptations" in payload
        assert "compute_envelope" in payload
        assert "mode_used" in payload
        assert payload["paper_components"]["mclp_candidate_selection"].startswith("Rogers")
        assert payload["paper_components"]["teg_contact_scheduler"].startswith("Gerard")


# ---- E2E tests (solver + verifier via subprocess) ----

@pytest.mark.timeout(600)
def test_no_added_baseline_produces_valid_solution() -> None:
    solution_dir, status = _run_solver(
        CASE_0001, {"mclp_mode": "none", "scheduler_mode": "greedy"}
    )
    try:
        verifier = _run_verifier(CASE_0001, solution_dir / "solution.json")
        assert verifier.get("valid") is True
        assert status["mclp_policy"] == "none"
        assert status["mclp_selected_count"] == 0
    finally:
        shutil.rmtree(solution_dir.parent)


@pytest.mark.timeout(600)
def test_greedy_mclp_beats_no_added_on_service_fraction() -> None:
    solution_no, _ = _run_solver(CASE_0001, {"mclp_mode": "none", "scheduler_mode": "greedy"})
    solution_greedy, _ = _run_solver(
        CASE_0001, {"mclp_mode": "greedy", "scheduler_mode": "greedy"}
    )
    try:
        verifier_no = _run_verifier(CASE_0001, solution_no / "solution.json")
        verifier_greedy = _run_verifier(CASE_0001, solution_greedy / "solution.json")

        sf_no = verifier_no.get("metrics", {}).get("service_fraction", 0.0)
        sf_greedy = verifier_greedy.get("metrics", {}).get("service_fraction", 0.0)
        # Greedy MCLP should improve or match no-added; allow tiny tolerance
        assert sf_greedy >= sf_no - 1e-9, f"greedy sf={sf_greedy} < no-added sf={sf_no}"
    finally:
        shutil.rmtree(solution_no.parent)
        shutil.rmtree(solution_greedy.parent)


@pytest.mark.timeout(600)
def test_milp_scheduler_skipped_when_too_large() -> None:
    """Public cases have ~5761 samples; MILP scheduler should skip due to variable bounds."""
    solution_dir, status = _run_solver(
        CASE_0001,
        {
            "mclp_mode": "none",
            "scheduler_mode": "auto",
            "milp_config": {
                "max_total_variables": 500,
                "max_samples": 50,
                "milp_time_limit_per_sample": 5.0,
            },
        },
    )
    try:
        verifier = _run_verifier(CASE_0001, solution_dir / "solution.json")
        assert verifier.get("valid") is True
        # MILP should be skipped because bounds are too small for public cases
        assert status.get("scheduler_milp_attempted") is False or status.get("scheduler_milp_fallback_reason") is not None
    finally:
        shutil.rmtree(solution_dir.parent)
