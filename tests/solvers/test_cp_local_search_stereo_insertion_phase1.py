"""Focused Phase 1 tests for the CP/local-search stereo insertion solver."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SOLVER_DIR = REPO_ROOT / "solvers" / "stereo_imaging" / "cp_local_search_stereo_insertion"
CASE_DIR = REPO_ROOT / "benchmarks" / "stereo_imaging" / "dataset" / "cases" / "test" / "case_0001"


@pytest.fixture
def solver_dir() -> Path:
    return SOLVER_DIR


@pytest.fixture
def case_0001_dir() -> Path:
    return CASE_DIR


# ---------------------------------------------------------------------------
# case_io tests
# ---------------------------------------------------------------------------

def test_load_case_smoke(case_0001_dir: Path) -> None:
    sys.path.insert(0, str(SOLVER_DIR / "src"))
    try:
        from case_io import load_case

        case = load_case(case_0001_dir)
        assert case.case_dir == case_0001_dir.resolve()
        assert len(case.satellites) > 0
        assert len(case.targets) > 0
        assert case.mission.horizon_start < case.mission.horizon_end
    finally:
        sys.path.pop(0)


# ---------------------------------------------------------------------------
# End-to-end solver tests
# ---------------------------------------------------------------------------


def _run_solver(case_dir: Path, solution_dir: Path, config_dir: Path | None = None) -> subprocess.CompletedProcess:
    cmd = [str(SOLVER_DIR / "solve.sh"), str(case_dir)]
    cmd.append(str(config_dir) if config_dir is not None else "")
    cmd.append(str(solution_dir))
    return subprocess.run(cmd, capture_output=True, text=True, cwd=str(REPO_ROOT))


def test_setup_script_runs(solver_dir: Path) -> None:
    result = subprocess.run([str(solver_dir / "setup.sh")], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "ok" in result.stdout.lower()


def test_solver_produces_valid_solution(case_0001_dir: Path, tmp_path: Path) -> None:
    solution_dir = tmp_path / "solution"
    result = _run_solver(case_0001_dir, solution_dir)
    assert result.returncode == 0, result.stderr

    solution_path = solution_dir / "solution.json"
    assert solution_path.exists()
    solution = json.loads(solution_path.read_text())
    assert "actions" in solution
    # Phase 7a: solver now produces non-empty solutions with tri-stereo products
    assert len(solution["actions"]) > 0

    # Verify with benchmark verifier
    verify_result = subprocess.run(
        [
            sys.executable, "-m", "benchmarks.stereo_imaging.verifier.run",
            str(case_0001_dir),
            str(solution_path),
            "--compact",
        ],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert verify_result.returncode == 0, verify_result.stderr + verify_result.stdout
    report = json.loads(verify_result.stdout)
    assert report["valid"] is True
    assert report["metrics"]["valid"] is True


def test_debug_artifacts_exist(case_0001_dir: Path, tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "config.yaml").write_text("debug: true\n")
    solution_dir = tmp_path / "solution"

    result = _run_solver(case_0001_dir, solution_dir, config_dir)
    assert result.returncode == 0, result.stderr

    debug_dir = solution_dir / "debug"
    assert (debug_dir / "candidates.json").exists()
    assert (debug_dir / "candidate_summary.json").exists()
    assert (debug_dir / "products.json").exists()
    assert (debug_dir / "product_summary.json").exists()

    candidates = json.loads((debug_dir / "candidates.json").read_text())
    assert isinstance(candidates, list)
    if len(candidates) > 0:
        assert "access_interval_id" in candidates[0]
        assert "effective_pixel_scale_m" in candidates[0]

    products = json.loads((debug_dir / "products.json").read_text())
    assert isinstance(products, list)

    product_summary = json.loads((debug_dir / "product_summary.json").read_text())
    assert "total_products" in product_summary["summary"]


def test_candidate_generation_determinism(case_0001_dir: Path, tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "config.yaml").write_text("debug: true\n")

    solution_dir_a = tmp_path / "solution_a"
    solution_dir_b = tmp_path / "solution_b"

    result_a = _run_solver(case_0001_dir, solution_dir_a, config_dir)
    result_b = _run_solver(case_0001_dir, solution_dir_b, config_dir)

    assert result_a.returncode == 0, result_a.stderr
    assert result_b.returncode == 0, result_b.stderr

    candidates_a = json.loads((solution_dir_a / "debug" / "candidates.json").read_text())
    candidates_b = json.loads((solution_dir_b / "debug" / "candidates.json").read_text())
    assert candidates_a == candidates_b

    products_a = json.loads((solution_dir_a / "debug" / "products.json").read_text())
    products_b = json.loads((solution_dir_b / "debug" / "products.json").read_text())
    assert products_a == products_b


def test_product_library_sorting_and_bounds(case_0001_dir: Path, tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "config.yaml").write_text(
        "debug: true\nmax_tri_products_per_target_access: 5\n"
    )
    solution_dir = tmp_path / "solution"

    result = _run_solver(case_0001_dir, solution_dir, config_dir)
    assert result.returncode == 0, result.stderr

    products = json.loads((solution_dir / "debug" / "products.json").read_text())
    summary = json.loads((solution_dir / "debug" / "product_summary.json").read_text())["summary"]

    # Products should be deterministically sorted
    # Verify monotonic sorting by coverage_value descending, then quality descending
    for i in range(len(products) - 1):
        p_curr = products[i]
        p_next = products[i + 1]
        key_curr = (-p_curr["coverage_value"], -p_curr["quality"], p_curr["target_id"])
        key_next = (-p_next["coverage_value"], -p_next["quality"], p_next["target_id"])
        assert key_curr <= key_next, f"Product sort violated at index {i}"

    # Bound check: count tri products per target/access
    tri_counts: dict[tuple[str, str], int] = {}
    for p in products:
        if p["product_type"] == "tri":
            key = (p["target_id"], p["access_interval_id"])
            tri_counts[key] = tri_counts.get(key, 0) + 1
    for key, count in tri_counts.items():
        assert count <= 5, f"Tri-stereo bound exceeded for {key}: {count}"
