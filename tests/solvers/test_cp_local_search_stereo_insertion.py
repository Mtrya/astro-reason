"""Tests for the CP/local-search stereo insertion solver."""

from __future__ import annotations

import json
import math
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SOLVER_DIR = REPO_ROOT / "solvers" / "stereo_imaging" / "cp_local_search_stereo_insertion"
CASE_DIR = REPO_ROOT / "benchmarks" / "stereo_imaging" / "dataset" / "cases" / "test" / "case_0001"

# Pleiades-1A TLE from verifier tests
_PLEIADES_TLE_LINE1 = (
    "1 38012U 11076F   26096.23539690  .00000494  00000+0  11617-3 0  9994"
)
_PLEIADES_TLE_LINE2 = (
    "2 38012  98.2002 172.2949 0001342  74.1943  10.7084 14.58565955761501"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_sat_def(
    *,
    sat_id: str = "sat_test",
    omega: float = 1.95,
    alpha: float = 0.95,
    settling: float = 1.9,
    min_dur: float = 2.0,
    max_dur: float = 60.0,
    max_off_nadir: float = 30.0,
):
    sys.path.insert(0, str(SOLVER_DIR / "src"))
    try:
        from case_io import SatelliteDef

        return SatelliteDef(
            sat_id=sat_id,
            norad_catalog_id=38012,
            tle_line1=_PLEIADES_TLE_LINE1,
            tle_line2=_PLEIADES_TLE_LINE2,
            pixel_ifov_deg=4.0e-5,
            cross_track_pixels=20000,
            max_off_nadir_deg=max_off_nadir,
            max_slew_velocity_deg_per_s=omega,
            max_slew_acceleration_deg_per_s2=alpha,
            settling_time_s=settling,
            min_obs_duration_s=min_dur,
            max_obs_duration_s=max_dur,
        )
    finally:
        sys.path.pop(0)


def _make_candidate(
    satellite_id: str = "sat_test",
    target_id: str = "t1",
    start: str = "2026-04-22T22:00:00Z",
    end: str = "2026-04-22T22:00:06Z",
    along: float = 0.0,
    across: float = 0.0,
    access_interval_id: str = "test::0",
    candidate_id: str | None = None,
):
    sys.path.insert(0, str(SOLVER_DIR / "src"))
    try:
        from candidates import Candidate

        start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
        end_dt = datetime.fromisoformat(end.replace("Z", "+00:00"))
        cid = candidate_id or f"{satellite_id}|{target_id}|{access_interval_id}|{start}"
        return Candidate(
            candidate_id=cid,
            satellite_id=satellite_id,
            target_id=target_id,
            start=start_dt,
            end=end_dt,
            off_nadir_along_deg=along,
            off_nadir_across_deg=across,
            access_interval_id=access_interval_id,
            effective_pixel_scale_m=1.0,
            slant_range_m=700000.0,
            boresight_off_nadir_deg=0.0,
        )
    finally:
        sys.path.pop(0)


def _make_product(
    solver_imports,
    product_id: str,
    product_type,
    target_id: str,
    satellite_id: str = "sat_test",
    access_interval_id: str = "test::0",
    quality: float = 0.5,
    observations: tuple | None = None,
    feasible: bool = True,
):
    StereoProduct = solver_imports["StereoProduct"]
    ProductType = solver_imports["ProductType"]
    if observations is None:
        c1 = _make_candidate(
            satellite_id=satellite_id,
            target_id=target_id,
            start="2026-04-22T22:00:00Z",
            end="2026-04-22T22:00:06Z",
            candidate_id=f"{product_id}_c1",
        )
        c2 = _make_candidate(
            satellite_id=satellite_id,
            target_id=target_id,
            start="2026-04-22T22:01:00Z",
            end="2026-04-22T22:01:06Z",
            candidate_id=f"{product_id}_c2",
        )
        if product_type == ProductType.TRI:
            c3 = _make_candidate(
                satellite_id=satellite_id,
                target_id=target_id,
                start="2026-04-22T22:02:00Z",
                end="2026-04-22T22:02:06Z",
                candidate_id=f"{product_id}_c3",
            )
            observations = (c1, c2, c3)
        else:
            observations = (c1, c2)
    return StereoProduct(
        product_id=product_id,
        product_type=product_type,
        target_id=target_id,
        satellite_id=satellite_id,
        access_interval_id=access_interval_id,
        observations=observations,
        quality=quality,
        coverage_value=quality if feasible else 0.0,
        feasible=feasible,
        reject_reasons=tuple(),
    )


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def solver_imports():
    sys.path.insert(0, str(SOLVER_DIR / "src"))
    try:
        from case_io import Mission, SatelliteDef, StereoCase, TargetDef, load_case
        from candidates import Candidate, CandidateConfig, generate_candidates
        from geometry import _TS
        from local_search import (
            LocalSearchConfig,
            LocalSearchState,
            run_local_search,
            _try_insert,
            _try_replace,
            _try_remove,
            _try_swap,
        )
        from products import ProductLibrary, ProductSummary, StereoProduct, ProductType
        from repair import RepairConfig, RepairResult, repair_state, _find_first_conflict
        from seed import (
            SeedConfig,
            SeedResult,
            build_greedy_seed,
            _product_sort_key,
            _compute_remaining_counts,
        )
        from sequence import (
            SatelliteSequence,
            SequenceState,
            compute_earliest,
            compute_latest,
            create_empty_state,
            insert_observation,
            insert_product,
            is_consistent,
            possible_insertion_positions,
            propagate,
            remove_observation,
            remove_product,
            _slew_gap_required_s,
        )
        from skyfield.api import EarthSatellite

        yield {
            "Candidate": Candidate,
            "CandidateConfig": CandidateConfig,
            "EarthSatellite": EarthSatellite,
            "LocalSearchConfig": LocalSearchConfig,
            "LocalSearchState": LocalSearchState,
            "Mission": Mission,
            "ProductLibrary": ProductLibrary,
            "ProductSummary": ProductSummary,
            "ProductType": ProductType,
            "RepairConfig": RepairConfig,
            "RepairResult": RepairResult,
            "SatelliteDef": SatelliteDef,
            "SatelliteSequence": SatelliteSequence,
            "SeedConfig": SeedConfig,
            "SeedResult": SeedResult,
            "SequenceState": SequenceState,
            "StereoCase": StereoCase,
            "StereoProduct": StereoProduct,
            "TargetDef": TargetDef,
            "_TS": _TS,
            "_compute_remaining_counts": _compute_remaining_counts,
            "_find_first_conflict": _find_first_conflict,
            "_product_sort_key": _product_sort_key,
            "_slew_gap_required_s": _slew_gap_required_s,
            "_try_insert": _try_insert,
            "_try_remove": _try_remove,
            "_try_replace": _try_replace,
            "_try_swap": _try_swap,
            "build_greedy_seed": build_greedy_seed,
            "compute_earliest": compute_earliest,
            "compute_latest": compute_latest,
            "create_empty_state": create_empty_state,
            "generate_candidates": generate_candidates,
            "insert_observation": insert_observation,
            "insert_product": insert_product,
            "is_consistent": is_consistent,
            "load_case": load_case,
            "possible_insertion_positions": possible_insertion_positions,
            "propagate": propagate,
            "remove_observation": remove_observation,
            "remove_product": remove_product,
            "repair_state": repair_state,
            "run_local_search": run_local_search,
        }
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


def test_load_case_smoke(solver_imports) -> None:
    case = solver_imports["load_case"](CASE_DIR)
    assert case.case_dir == CASE_DIR.resolve()
    assert len(case.satellites) > 0
    assert len(case.targets) > 0
    assert case.mission.horizon_start < case.mission.horizon_end


def test_setup_script_runs() -> None:
    result = subprocess.run([str(SOLVER_DIR / "setup.sh")], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "ok" in result.stdout.lower()


def test_solver_produces_valid_solution(tmp_path: Path) -> None:
    solution_dir = tmp_path / "solution"
    result = _run_solver(CASE_DIR, solution_dir)
    assert result.returncode == 0, result.stderr

    solution_path = solution_dir / "solution.json"
    assert solution_path.exists()
    solution = json.loads(solution_path.read_text())
    assert "actions" in solution
    assert len(solution["actions"]) > 0

    verify_result = subprocess.run(
        [
            sys.executable, "-m", "benchmarks.stereo_imaging.verifier.run",
            str(CASE_DIR),
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


def test_debug_artifacts_exist(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "config.yaml").write_text("debug: true\n")
    solution_dir = tmp_path / "solution"

    result = _run_solver(CASE_DIR, solution_dir, config_dir)
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


def test_candidate_generation_determinism(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "config.yaml").write_text("debug: true\n")

    solution_dir_a = tmp_path / "solution_a"
    solution_dir_b = tmp_path / "solution_b"

    result_a = _run_solver(CASE_DIR, solution_dir_a, config_dir)
    result_b = _run_solver(CASE_DIR, solution_dir_b, config_dir)

    assert result_a.returncode == 0, result_a.stderr
    assert result_b.returncode == 0, result_b.stderr

    candidates_a = json.loads((solution_dir_a / "debug" / "candidates.json").read_text())
    candidates_b = json.loads((solution_dir_b / "debug" / "candidates.json").read_text())
    assert candidates_a == candidates_b

    products_a = json.loads((solution_dir_a / "debug" / "products.json").read_text())
    products_b = json.loads((solution_dir_b / "debug" / "products.json").read_text())
    assert products_a == products_b


def test_product_library_sorting_and_bounds(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "config.yaml").write_text(
        "debug: true\nmax_tri_products_per_target_access: 5\n"
    )
    solution_dir = tmp_path / "solution"

    result = _run_solver(CASE_DIR, solution_dir, config_dir)
    assert result.returncode == 0, result.stderr

    products = json.loads((solution_dir / "debug" / "products.json").read_text())
    summary = json.loads((solution_dir / "debug" / "product_summary.json").read_text())["summary"]

    for i in range(len(products) - 1):
        p_curr = products[i]
        p_next = products[i + 1]
        key_curr = (-p_curr["coverage_value"], -p_curr["quality"], p_curr["target_id"])
        key_next = (-p_next["coverage_value"], -p_next["quality"], p_next["target_id"])
        assert key_curr <= key_next, f"Product sort violated at index {i}"

    tri_counts: dict[tuple[str, str], int] = {}
    for p in products:
        if p["product_type"] == "tri":
            key = (p["target_id"], p["access_interval_id"])
            tri_counts[key] = tri_counts.get(key, 0) + 1
    for key, count in tri_counts.items():
        assert count <= 5, f"Tri-stereo bound exceeded for {key}: {count}"


# ---------------------------------------------------------------------------
# Sequence propagation and insertion tests
# ---------------------------------------------------------------------------


def test_empty_sequence_positions(solver_imports) -> None:
    sat_def = _make_sat_def()
    sf = solver_imports["EarthSatellite"](sat_def.tle_line1, sat_def.tle_line2, name="sat_test", ts=solver_imports["_TS"])
    seq = solver_imports["SatelliteSequence"](satellite_id="sat_test")
    cand = _make_candidate(start="2026-04-22T22:00:00Z", end="2026-04-22T22:00:06Z")
    positions = solver_imports["possible_insertion_positions"](cand, seq, sat_def, sf)
    assert positions == [0]


def test_beginning_insertion(solver_imports) -> None:
    sat_def = _make_sat_def()
    sf = solver_imports["EarthSatellite"](sat_def.tle_line1, sat_def.tle_line2, name="sat_test", ts=solver_imports["_TS"])
    seq = solver_imports["SatelliteSequence"](satellite_id="sat_test")

    first = _make_candidate(start="2026-04-22T22:00:00Z", end="2026-04-22T22:00:06Z", candidate_id="c0")
    solver_imports["insert_observation"](first, seq, 0, sat_def, sf)
    ok, _ = solver_imports["is_consistent"](seq)
    assert ok

    second = _make_candidate(start="2026-04-22T21:59:00Z", end="2026-04-22T21:59:06Z", candidate_id="c1")
    positions = solver_imports["possible_insertion_positions"](second, seq, sat_def, sf)
    assert 0 in positions

    result = solver_imports["insert_observation"](second, seq, 0, sat_def, sf)
    assert result.success
    assert seq.observations[0].candidate_id == "c1"
    assert seq.observations[1].candidate_id == "c0"


def test_end_insertion(solver_imports) -> None:
    sat_def = _make_sat_def()
    sf = solver_imports["EarthSatellite"](sat_def.tle_line1, sat_def.tle_line2, name="sat_test", ts=solver_imports["_TS"])
    seq = solver_imports["SatelliteSequence"](satellite_id="sat_test")

    first = _make_candidate(start="2026-04-22T22:00:00Z", end="2026-04-22T22:00:06Z", candidate_id="c0")
    solver_imports["insert_observation"](first, seq, 0, sat_def, sf)

    second = _make_candidate(start="2026-04-22T22:01:00Z", end="2026-04-22T22:01:06Z", candidate_id="c1")
    positions = solver_imports["possible_insertion_positions"](second, seq, sat_def, sf)
    assert len(seq.observations) in positions

    result = solver_imports["insert_observation"](second, seq, len(seq.observations), sat_def, sf)
    assert result.success
    assert seq.observations[-1].candidate_id == "c1"


def test_middle_insertion(solver_imports) -> None:
    sat_def = _make_sat_def()
    sf = solver_imports["EarthSatellite"](sat_def.tle_line1, sat_def.tle_line2, name="sat_test", ts=solver_imports["_TS"])
    seq = solver_imports["SatelliteSequence"](satellite_id="sat_test")

    c0 = _make_candidate(start="2026-04-22T22:00:00Z", end="2026-04-22T22:00:06Z", candidate_id="c0")
    c2 = _make_candidate(start="2026-04-22T22:02:00Z", end="2026-04-22T22:02:06Z", candidate_id="c2")
    solver_imports["insert_observation"](c0, seq, 0, sat_def, sf)
    solver_imports["insert_observation"](c2, seq, 1, sat_def, sf)

    c1 = _make_candidate(start="2026-04-22T22:01:00Z", end="2026-04-22T22:01:06Z", candidate_id="c1")
    positions = solver_imports["possible_insertion_positions"](c1, seq, sat_def, sf)
    assert 1 in positions

    result = solver_imports["insert_observation"](c1, seq, 1, sat_def, sf)
    assert result.success
    assert [o.candidate_id for o in seq.observations] == ["c0", "c1", "c2"]


def test_overlap_rejection(solver_imports) -> None:
    sat_def = _make_sat_def()
    sf = solver_imports["EarthSatellite"](sat_def.tle_line1, sat_def.tle_line2, name="sat_test", ts=solver_imports["_TS"])
    seq = solver_imports["SatelliteSequence"](satellite_id="sat_test")

    c0 = _make_candidate(start="2026-04-22T22:00:00Z", end="2026-04-22T22:00:06Z", candidate_id="c0")
    solver_imports["insert_observation"](c0, seq, 0, sat_def, sf)

    overlap = _make_candidate(start="2026-04-22T22:00:03Z", end="2026-04-22T22:00:09Z", candidate_id="c_overlap")
    positions = solver_imports["possible_insertion_positions"](overlap, seq, sat_def, sf)
    assert positions == []

    result = solver_imports["insert_observation"](overlap, seq, 0, sat_def, sf)
    assert not result.success


def test_slew_too_fast_rejection(solver_imports) -> None:
    sat_def = _make_sat_def()
    sf = solver_imports["EarthSatellite"](sat_def.tle_line1, sat_def.tle_line2, name="sat_test", ts=solver_imports["_TS"])
    seq = solver_imports["SatelliteSequence"](satellite_id="sat_test")

    c0 = _make_candidate(start="2026-04-22T22:00:00Z", end="2026-04-22T22:00:06Z", candidate_id="c0")
    solver_imports["insert_observation"](c0, seq, 0, sat_def, sf)

    c1 = _make_candidate(
        start="2026-04-22T22:00:07Z",
        end="2026-04-22T22:00:13Z",
        candidate_id="c1",
        across=25.0,
    )
    result = solver_imports["insert_observation"](c1, seq, len(seq.observations), sat_def, sf)
    assert not result.success


def test_rollback_after_failed_partner(solver_imports) -> None:
    sat_def = _make_sat_def()
    sf = solver_imports["EarthSatellite"](sat_def.tle_line1, sat_def.tle_line2, name="sat_test", ts=solver_imports["_TS"])
    seq = solver_imports["SatelliteSequence"](satellite_id="sat_test")

    c0 = _make_candidate(start="2026-04-22T22:00:00Z", end="2026-04-22T22:00:06Z", candidate_id="c0")
    solver_imports["insert_observation"](c0, seq, 0, sat_def, sf)

    c1 = _make_candidate(start="2026-04-22T22:01:00Z", end="2026-04-22T22:01:06Z", candidate_id="c1")
    c2 = _make_candidate(start="2026-04-22T22:01:03Z", end="2026-04-22T22:01:09Z", candidate_id="c2")
    product = solver_imports["StereoProduct"](
        product_id="pair|test",
        product_type=solver_imports["ProductType"].PAIR,
        target_id="t1",
        satellite_id="sat_test",
        access_interval_id="test::0",
        observations=(c1, c2),
        quality=0.5,
        coverage_value=0.5,
        feasible=True,
        reject_reasons=tuple(),
    )

    class _FakeCase:
        satellites = {"sat_test": sat_def}

    state = solver_imports["SequenceState"](
        sequences={"sat_test": seq},
        sf_sats={"sat_test": sf},
    )

    result = solver_imports["insert_product"](product, state, _FakeCase())
    assert not result.success
    assert len(seq.observations) == 1
    assert seq.observations[0].candidate_id == "c0"


def test_tri_product_rollback(solver_imports) -> None:
    sat_def = _make_sat_def()
    sf = solver_imports["EarthSatellite"](sat_def.tle_line1, sat_def.tle_line2, name="sat_test", ts=solver_imports["_TS"])
    seq = solver_imports["SatelliteSequence"](satellite_id="sat_test")

    c0 = _make_candidate(start="2026-04-22T22:00:00Z", end="2026-04-22T22:00:06Z", candidate_id="c0")
    solver_imports["insert_observation"](c0, seq, 0, sat_def, sf)

    c1 = _make_candidate(start="2026-04-22T22:01:00Z", end="2026-04-22T22:01:06Z", candidate_id="c1")
    c2 = _make_candidate(start="2026-04-22T22:02:00Z", end="2026-04-22T22:02:06Z", candidate_id="c2")
    c3 = _make_candidate(start="2026-04-22T22:02:03Z", end="2026-04-22T22:02:09Z", candidate_id="c3")
    product = solver_imports["StereoProduct"](
        product_id="tri|test",
        product_type=solver_imports["ProductType"].TRI,
        target_id="t1",
        satellite_id="sat_test",
        access_interval_id="test::0",
        observations=(c1, c2, c3),
        quality=0.5,
        coverage_value=0.5,
        feasible=True,
        reject_reasons=tuple(),
    )

    class _FakeCase:
        satellites = {"sat_test": sat_def}

    state = solver_imports["SequenceState"](
        sequences={"sat_test": seq},
        sf_sats={"sat_test": sf},
    )

    result = solver_imports["insert_product"](product, state, _FakeCase())
    assert not result.success
    assert len(seq.observations) == 1
    assert seq.observations[0].candidate_id == "c0"


def test_propagation_consistency_after_insert_remove(solver_imports) -> None:
    sat_def = _make_sat_def()
    sf = solver_imports["EarthSatellite"](sat_def.tle_line1, sat_def.tle_line2, name="sat_test", ts=solver_imports["_TS"])
    seq = solver_imports["SatelliteSequence"](satellite_id="sat_test")

    c0 = _make_candidate(start="2026-04-22T22:00:00Z", end="2026-04-22T22:00:06Z", candidate_id="c0")
    c1 = _make_candidate(start="2026-04-22T22:01:00Z", end="2026-04-22T22:01:06Z", candidate_id="c1")

    solver_imports["insert_observation"](c0, seq, 0, sat_def, sf)
    solver_imports["insert_observation"](c1, seq, 1, sat_def, sf)
    ok, _ = solver_imports["is_consistent"](seq)
    assert ok
    e_after_insert = dict(seq.earliest)
    l_after_insert = dict(seq.latest)

    solver_imports["remove_observation"]("c0", seq, sat_def, sf)
    solver_imports["remove_observation"]("c1", seq, sat_def, sf)
    assert len(seq.observations) == 0
    assert seq.earliest == {}
    assert seq.latest == {}

    solver_imports["insert_observation"](c0, seq, 0, sat_def, sf)
    solver_imports["insert_observation"](c1, seq, 1, sat_def, sf)
    assert seq.earliest == e_after_insert
    assert seq.latest == l_after_insert


def test_deterministic_position_selection(solver_imports) -> None:
    sat_def = _make_sat_def()
    sf = solver_imports["EarthSatellite"](sat_def.tle_line1, sat_def.tle_line2, name="sat_test", ts=solver_imports["_TS"])
    seq = solver_imports["SatelliteSequence"](satellite_id="sat_test")

    c0 = _make_candidate(start="2026-04-22T22:00:00Z", end="2026-04-22T22:00:06Z", candidate_id="c0")
    solver_imports["insert_observation"](c0, seq, 0, sat_def, sf)

    c1 = _make_candidate(start="2026-04-22T22:01:00Z", end="2026-04-22T22:01:06Z", candidate_id="c1")
    positions_1 = solver_imports["possible_insertion_positions"](c1, seq, sat_def, sf)

    seq2 = solver_imports["SatelliteSequence"](satellite_id="sat_test")
    solver_imports["insert_observation"](c0, seq2, 0, sat_def, sf)
    positions_2 = solver_imports["possible_insertion_positions"](c1, seq2, sat_def, sf)

    assert positions_1 == positions_2


# ---------------------------------------------------------------------------
# Greedy seed ranking tests
# ---------------------------------------------------------------------------


def test_ranking_uncovered_target_first(solver_imports) -> None:
    ProductType = solver_imports["ProductType"]
    SeedConfig = solver_imports["SeedConfig"]
    _product_sort_key = solver_imports["_product_sort_key"]

    config = SeedConfig()
    covered = {"t2"}
    remaining = {"t1": 5, "t2": 5}

    p_uncovered = _make_product(solver_imports, "p1", ProductType.PAIR, "t1", quality=0.3)
    p_covered = _make_product(solver_imports, "p2", ProductType.PAIR, "t2", quality=0.9)

    k1 = _product_sort_key(p_uncovered, covered, remaining, config)
    k2 = _product_sort_key(p_covered, covered, remaining, config)
    assert k1[0] > k2[0]


def test_ranking_scarcity_tiebreak(solver_imports) -> None:
    ProductType = solver_imports["ProductType"]
    SeedConfig = solver_imports["SeedConfig"]
    _product_sort_key = solver_imports["_product_sort_key"]

    config = SeedConfig()
    covered: set[str] = set()
    remaining = {"t1": 2, "t2": 10}

    p_scarce = _make_product(solver_imports, "p1", ProductType.PAIR, "t1", quality=0.5)
    p_abundant = _make_product(solver_imports, "p2", ProductType.PAIR, "t2", quality=0.5)

    k1 = _product_sort_key(p_scarce, covered, remaining, config)
    k2 = _product_sort_key(p_abundant, covered, remaining, config)
    assert k1[2] > k2[2]


def test_ranking_tri_before_pair(solver_imports) -> None:
    ProductType = solver_imports["ProductType"]
    SeedConfig = solver_imports["SeedConfig"]
    _product_sort_key = solver_imports["_product_sort_key"]

    config = SeedConfig()
    covered = {"t1"}
    remaining = {"t1": 5}

    p_tri = _make_product(solver_imports, "p_tri", ProductType.TRI, "t1", quality=0.5)
    p_pair = _make_product(solver_imports, "p_pair", ProductType.PAIR, "t1", quality=0.5)

    k1 = _product_sort_key(p_tri, covered, remaining, config)
    k2 = _product_sort_key(p_pair, covered, remaining, config)
    assert k1[1] > k2[1]


def test_ranking_pair_before_tri_when_configured(solver_imports) -> None:
    ProductType = solver_imports["ProductType"]
    SeedConfig = solver_imports["SeedConfig"]
    _product_sort_key = solver_imports["_product_sort_key"]

    config = SeedConfig(tri_weight=0.5, pair_weight=1.0)
    covered = {"t1"}
    remaining = {"t1": 5}

    p_tri = _make_product(solver_imports, "p_tri", ProductType.TRI, "t1", quality=0.5)
    p_pair = _make_product(solver_imports, "p_pair", ProductType.PAIR, "t1", quality=0.5)

    k1 = _product_sort_key(p_tri, covered, remaining, config)
    k2 = _product_sort_key(p_pair, covered, remaining, config)
    assert k2[1] > k1[1]


def test_ranking_deterministic(solver_imports) -> None:
    ProductType = solver_imports["ProductType"]
    SeedConfig = solver_imports["SeedConfig"]
    _product_sort_key = solver_imports["_product_sort_key"]

    config = SeedConfig()
    covered: set[str] = set()
    remaining = {"t1": 5}

    p = _make_product(solver_imports, "p1", ProductType.PAIR, "t1", quality=0.5)

    k1 = _product_sort_key(p, covered, remaining, config)
    k2 = _product_sort_key(p, covered, remaining, config)
    assert k1 == k2


def test_greedy_seed_accepts_feasible_product(solver_imports) -> None:
    ProductType = solver_imports["ProductType"]
    ProductLibrary = solver_imports["ProductLibrary"]
    ProductSummary = solver_imports["ProductSummary"]
    SeedConfig = solver_imports["SeedConfig"]
    build_greedy_seed = solver_imports["build_greedy_seed"]

    product = _make_product(solver_imports, "p1", ProductType.PAIR, "t1", quality=0.8)
    library = ProductLibrary(
        products=[product],
        per_target_products={"t1": [product]},
        summary=ProductSummary(
            total_products=1,
            pair_products=1,
            feasible_products=1,
            per_target_product_counts={"t1": 1},
        ),
    )

    class _FakeCase:
        satellites = {"sat_test": _make_sat_def()}
        targets = {"t1": None}

    seed = build_greedy_seed(library, _FakeCase(), SeedConfig())
    assert seed.accepted_count == 1
    assert "t1" in seed.covered_targets


def test_greedy_seed_rejects_infeasible_insertion(solver_imports) -> None:
    ProductType = solver_imports["ProductType"]
    ProductLibrary = solver_imports["ProductLibrary"]
    ProductSummary = solver_imports["ProductSummary"]
    SeedConfig = solver_imports["SeedConfig"]
    build_greedy_seed = solver_imports["build_greedy_seed"]

    sat_def = _make_sat_def()

    c1a = _make_candidate(start="2026-04-22T22:00:00Z", end="2026-04-22T22:00:06Z", candidate_id="c1a")
    c1b = _make_candidate(start="2026-04-22T22:01:00Z", end="2026-04-22T22:01:06Z", candidate_id="c1b")
    p1 = solver_imports["StereoProduct"](
        product_id="p1",
        product_type=ProductType.PAIR,
        target_id="t1",
        satellite_id="sat_test",
        access_interval_id="test::0",
        observations=(c1a, c1b),
        quality=0.8,
        coverage_value=0.8,
        feasible=True,
        reject_reasons=tuple(),
    )

    c2a = _make_candidate(start="2026-04-22T22:00:03Z", end="2026-04-22T22:00:09Z", candidate_id="c2a")
    c2b = _make_candidate(start="2026-04-22T22:01:03Z", end="2026-04-22T22:01:09Z", candidate_id="c2b")
    p2 = solver_imports["StereoProduct"](
        product_id="p2",
        product_type=ProductType.PAIR,
        target_id="t1",
        satellite_id="sat_test",
        access_interval_id="test::0",
        observations=(c2a, c2b),
        quality=0.9,
        coverage_value=0.9,
        feasible=True,
        reject_reasons=tuple(),
    )

    library = ProductLibrary(
        products=[p1, p2],
        per_target_products={"t1": [p1, p2]},
        summary=ProductSummary(
            total_products=2,
            pair_products=2,
            feasible_products=2,
            per_target_product_counts={"t1": 2},
        ),
    )

    class _FakeCase:
        satellites = {"sat_test": sat_def}
        targets = {"t1": None}

    seed = build_greedy_seed(library, _FakeCase(), SeedConfig())
    assert seed.accepted_count == 1
    assert seed.accepted_products[0].product_id == "p2"
    assert "p1" not in [p.product_id for p in seed.accepted_products]


def test_seed_repeatability(solver_imports) -> None:
    ProductType = solver_imports["ProductType"]
    ProductLibrary = solver_imports["ProductLibrary"]
    ProductSummary = solver_imports["ProductSummary"]
    SeedConfig = solver_imports["SeedConfig"]
    build_greedy_seed = solver_imports["build_greedy_seed"]

    sat_def = _make_sat_def()

    products = []
    for i in range(3):
        c1 = _make_candidate(
            start=f"2026-04-22T22:0{i}:00Z",
            end=f"2026-04-22T22:0{i}:06Z",
            candidate_id=f"c{i}a",
        )
        c2 = _make_candidate(
            start=f"2026-04-22T22:0{i+3}:00Z",
            end=f"2026-04-22T22:0{i+3}:06Z",
            candidate_id=f"c{i}b",
        )
        p = solver_imports["StereoProduct"](
            product_id=f"p{i}",
            product_type=ProductType.PAIR,
            target_id=f"t{i}",
            satellite_id="sat_test",
            access_interval_id="test::0",
            observations=(c1, c2),
            quality=0.5 + i * 0.1,
            coverage_value=0.5 + i * 0.1,
            feasible=True,
            reject_reasons=tuple(),
        )
        products.append(p)

    library = ProductLibrary(
        products=products,
        per_target_products={f"t{i}": [products[i]] for i in range(3)},
        summary=ProductSummary(
            total_products=3,
            pair_products=3,
            feasible_products=3,
            per_target_product_counts={f"t{i}": 1 for i in range(3)},
        ),
    )

    class _FakeCase:
        satellites = {"sat_test": sat_def}
        targets = {f"t{i}": None for i in range(3)}

    seed1 = build_greedy_seed(library, _FakeCase(), SeedConfig())
    seed2 = build_greedy_seed(library, _FakeCase(), SeedConfig())

    assert seed1.accepted_count == seed2.accepted_count
    assert [p.product_id for p in seed1.accepted_products] == [
        p.product_id for p in seed2.accepted_products
    ]


def test_seed_only_mode_empty_solution_when_no_products(solver_imports) -> None:
    ProductLibrary = solver_imports["ProductLibrary"]
    ProductSummary = solver_imports["ProductSummary"]
    SeedConfig = solver_imports["SeedConfig"]
    build_greedy_seed = solver_imports["build_greedy_seed"]

    library = ProductLibrary(
        products=[],
        per_target_products={},
        summary=ProductSummary(),
    )

    class _FakeCase:
        satellites = {"sat_test": _make_sat_def()}
        targets = {}

    seed = build_greedy_seed(library, _FakeCase(), SeedConfig())
    assert seed.accepted_count == 0
    assert seed.covered_target_count == 0


def test_tri_stereo_pre_phase_accepts_tri_and_skips_pair(solver_imports) -> None:
    ProductType = solver_imports["ProductType"]
    ProductLibrary = solver_imports["ProductLibrary"]
    ProductSummary = solver_imports["ProductSummary"]
    SeedConfig = solver_imports["SeedConfig"]
    build_greedy_seed = solver_imports["build_greedy_seed"]

    sat_def = _make_sat_def()

    c1 = _make_candidate(start="2026-04-22T22:00:00Z", end="2026-04-22T22:00:06Z", candidate_id="c1")
    c2 = _make_candidate(start="2026-04-22T22:02:00Z", end="2026-04-22T22:02:06Z", candidate_id="c2")
    c3 = _make_candidate(start="2026-04-22T22:04:00Z", end="2026-04-22T22:04:06Z", candidate_id="c3")
    p_tri = solver_imports["StereoProduct"](
        product_id="p_tri",
        product_type=ProductType.TRI,
        target_id="t1",
        satellite_id="sat_test",
        access_interval_id="test::0",
        observations=(c1, c2, c3),
        quality=0.7,
        coverage_value=0.7,
        feasible=True,
        reject_reasons=tuple(),
    )

    c4 = _make_candidate(start="2026-04-22T22:06:00Z", end="2026-04-22T22:06:06Z", candidate_id="c4")
    c5 = _make_candidate(start="2026-04-22T22:08:00Z", end="2026-04-22T22:08:06Z", candidate_id="c5")
    p_pair = solver_imports["StereoProduct"](
        product_id="p_pair",
        product_type=ProductType.PAIR,
        target_id="t1",
        satellite_id="sat_test",
        access_interval_id="test::0",
        observations=(c4, c5),
        quality=0.9,
        coverage_value=0.9,
        feasible=True,
        reject_reasons=tuple(),
    )

    library = ProductLibrary(
        products=[p_tri, p_pair],
        per_target_products={"t1": [p_tri, p_pair]},
        summary=ProductSummary(
            total_products=2,
            pair_products=1,
            tri_products=1,
            feasible_products=2,
            per_target_product_counts={"t1": 2},
        ),
    )

    class _FakeCase:
        satellites = {"sat_test": sat_def}
        targets = {"t1": None}

    seed = build_greedy_seed(library, _FakeCase(), SeedConfig())
    assert seed.tri_accepted >= 1
    assert "p_tri" in [p.product_id for p in seed.accepted_products]
    assert "p_pair" not in [p.product_id for p in seed.accepted_products]


def test_tri_stereo_pre_phase_disabled(solver_imports) -> None:
    ProductType = solver_imports["ProductType"]
    ProductLibrary = solver_imports["ProductLibrary"]
    ProductSummary = solver_imports["ProductSummary"]
    SeedConfig = solver_imports["SeedConfig"]
    build_greedy_seed = solver_imports["build_greedy_seed"]

    sat_def = _make_sat_def()

    c1 = _make_candidate(start="2026-04-22T22:00:00Z", end="2026-04-22T22:00:06Z", candidate_id="c1")
    c2 = _make_candidate(start="2026-04-22T22:02:00Z", end="2026-04-22T22:02:06Z", candidate_id="c2")
    c3 = _make_candidate(start="2026-04-22T22:04:00Z", end="2026-04-22T22:04:06Z", candidate_id="c3")
    p_tri = solver_imports["StereoProduct"](
        product_id="p_tri",
        product_type=ProductType.TRI,
        target_id="t1",
        satellite_id="sat_test",
        access_interval_id="test::0",
        observations=(c1, c2, c3),
        quality=0.7,
        coverage_value=0.7,
        feasible=True,
        reject_reasons=tuple(),
    )

    c4 = _make_candidate(start="2026-04-22T22:06:00Z", end="2026-04-22T22:06:06Z", candidate_id="c4")
    c5 = _make_candidate(start="2026-04-22T22:08:00Z", end="2026-04-22T22:08:06Z", candidate_id="c5")
    p_pair = solver_imports["StereoProduct"](
        product_id="p_pair",
        product_type=ProductType.PAIR,
        target_id="t1",
        satellite_id="sat_test",
        access_interval_id="test::0",
        observations=(c4, c5),
        quality=0.9,
        coverage_value=0.9,
        feasible=True,
        reject_reasons=tuple(),
    )

    library = ProductLibrary(
        products=[p_tri, p_pair],
        per_target_products={"t1": [p_tri, p_pair]},
        summary=ProductSummary(
            total_products=2,
            pair_products=1,
            tri_products=1,
            feasible_products=2,
            per_target_product_counts={"t1": 2},
        ),
    )

    class _FakeCase:
        satellites = {"sat_test": sat_def}
        targets = {"t1": None}

    seed = build_greedy_seed(
        library, _FakeCase(), SeedConfig(tri_stereo_seed_phase=False, tri_weight=0.5)
    )
    assert seed.tri_accepted == 0
    assert "p_pair" in [p.product_id for p in seed.accepted_products]


# ---------------------------------------------------------------------------
# Local search move tests
# ---------------------------------------------------------------------------


def test_try_insert_increases_coverage(solver_imports) -> None:
    sat_def = _make_sat_def()
    ProductType = solver_imports["ProductType"]
    LocalSearchState = solver_imports["LocalSearchState"]
    _try_insert = solver_imports["_try_insert"]
    create_empty_state = solver_imports["create_empty_state"]

    class _FakeCase:
        satellites = {"sat_test": sat_def}
        targets = {"t1": None}

    state = LocalSearchState.from_seed(
        create_empty_state(_FakeCase()), []
    )
    product = _make_product(solver_imports, "p1", ProductType.PAIR, "t1", quality=0.8)

    accepted, new_state, reason = _try_insert(state, product, _FakeCase())
    assert accepted
    assert new_state is not None
    assert new_state.coverage_count == 1
    assert new_state.total_best_quality == pytest.approx(0.8)


def test_try_replace_improves_quality(solver_imports) -> None:
    sat_def = _make_sat_def()
    ProductType = solver_imports["ProductType"]
    LocalSearchState = solver_imports["LocalSearchState"]
    _try_replace = solver_imports["_try_replace"]
    create_empty_state = solver_imports["create_empty_state"]

    class _FakeCase:
        satellites = {"sat_test": sat_def}
        targets = {"t1": None}

    low = _make_product(solver_imports, "p_low", ProductType.PAIR, "t1", quality=0.3)
    high = _make_product(solver_imports, "p_high", ProductType.PAIR, "t1", quality=0.9)

    seed_state = create_empty_state(_FakeCase())
    solver_imports["insert_product"](low, seed_state, _FakeCase())
    state = LocalSearchState.from_seed(seed_state, [low])

    accepted, new_state, reason = _try_replace(state, low, high, _FakeCase())
    assert accepted
    assert new_state is not None
    assert new_state.total_best_quality == pytest.approx(0.9)


def test_try_replace_rollback_on_failure(solver_imports) -> None:
    sat_def = _make_sat_def()
    ProductType = solver_imports["ProductType"]
    LocalSearchState = solver_imports["LocalSearchState"]
    _try_replace = solver_imports["_try_replace"]
    create_empty_state = solver_imports["create_empty_state"]

    class _FakeCase:
        satellites = {"sat_test": sat_def}
        targets = {"t1": None}

    c1a = _make_candidate(start="2026-04-22T22:00:00Z", end="2026-04-22T22:00:06Z", candidate_id="c1a")
    c1b = _make_candidate(start="2026-04-22T22:01:00Z", end="2026-04-22T22:01:06Z", candidate_id="c1b")
    low = solver_imports["StereoProduct"](
        product_id="p_low", product_type=ProductType.PAIR, target_id="t1",
        satellite_id="sat_test", access_interval_id="test::0",
        observations=(c1a, c1b), quality=0.3, coverage_value=0.3,
        feasible=True, reject_reasons=tuple(),
    )

    c2 = _make_candidate(start="2026-04-22T22:00:03Z", end="2026-04-22T22:00:09Z", candidate_id="c2")
    high = solver_imports["StereoProduct"](
        product_id="p_high", product_type=ProductType.PAIR, target_id="t1",
        satellite_id="sat_test", access_interval_id="test::0",
        observations=(c1a, c2), quality=0.9, coverage_value=0.9,
        feasible=True, reject_reasons=tuple(),
    )

    seed_state = create_empty_state(_FakeCase())
    solver_imports["insert_product"](low, seed_state, _FakeCase())
    state = LocalSearchState.from_seed(seed_state, [low])

    before_obj = state.objective()
    accepted, new_state, reason = _try_replace(state, low, high, _FakeCase())
    assert not accepted
    assert state.objective() == before_obj


def test_local_optimum_stops_early(solver_imports) -> None:
    sat_def = _make_sat_def()
    ProductType = solver_imports["ProductType"]
    LocalSearchConfig = solver_imports["LocalSearchConfig"]
    run_local_search = solver_imports["run_local_search"]
    create_empty_state = solver_imports["create_empty_state"]

    class _FakeCase:
        satellites = {"sat_test": sat_def}
        targets = {"t1": None}

    product = _make_product(solver_imports, "p1", ProductType.PAIR, "t1", quality=0.8)
    seed_state = create_empty_state(_FakeCase())
    solver_imports["insert_product"](product, seed_state, _FakeCase())

    library = solver_imports["ProductLibrary"](
        products=[product],
        per_target_products={"t1": [product]},
        summary=solver_imports["ProductSummary"](
            total_products=1, pair_products=1, feasible_products=1,
            per_target_product_counts={"t1": 1},
        ),
    )

    config = LocalSearchConfig(max_passes=10, max_moves_per_pass=100)
    result = run_local_search(seed_state, [product], library, _FakeCase(), config)
    assert result.passes_completed == 1
    assert result.moves_accepted == 0


def test_seed_vs_improved_objective(solver_imports) -> None:
    sat_def = _make_sat_def()
    ProductType = solver_imports["ProductType"]
    LocalSearchConfig = solver_imports["LocalSearchConfig"]
    run_local_search = solver_imports["run_local_search"]
    create_empty_state = solver_imports["create_empty_state"]

    class _FakeCase:
        satellites = {"sat_test": sat_def}
        targets = {"t1": None, "t2": None}

    p1 = _make_product(solver_imports, "p1", ProductType.PAIR, "t1", quality=0.3)
    seed_state = create_empty_state(_FakeCase())
    solver_imports["insert_product"](p1, seed_state, _FakeCase())

    p1b = _make_product(solver_imports, "p1b", ProductType.PAIR, "t1", quality=0.9)
    c2a = _make_candidate(target_id="t2", start="2026-04-22T23:00:00Z", end="2026-04-22T23:00:06Z", candidate_id="c2a")
    c2b = _make_candidate(target_id="t2", start="2026-04-22T23:01:00Z", end="2026-04-22T23:01:06Z", candidate_id="c2b")
    p2 = solver_imports["StereoProduct"](
        product_id="p2", product_type=ProductType.PAIR, target_id="t2",
        satellite_id="sat_test", access_interval_id="test::0",
        observations=(c2a, c2b), quality=0.7, coverage_value=0.7,
        feasible=True, reject_reasons=tuple(),
    )

    library = solver_imports["ProductLibrary"](
        products=[p1, p1b, p2],
        per_target_products={"t1": [p1, p1b], "t2": [p2]},
        summary=solver_imports["ProductSummary"](
            total_products=3, pair_products=3, feasible_products=3,
            per_target_product_counts={"t1": 2, "t2": 1},
        ),
    )

    config = LocalSearchConfig(max_passes=5, max_moves_per_pass=100)
    result = run_local_search(seed_state, [p1], library, _FakeCase(), config)

    seed_obj = (1, 0.3)
    assert result.best_objective >= seed_obj


def test_deterministic_replay(solver_imports) -> None:
    sat_def = _make_sat_def()
    ProductType = solver_imports["ProductType"]
    LocalSearchConfig = solver_imports["LocalSearchConfig"]
    run_local_search = solver_imports["run_local_search"]
    create_empty_state = solver_imports["create_empty_state"]

    class _FakeCase:
        satellites = {"sat_test": sat_def}
        targets = {"t1": None, "t2": None}

    p1 = _make_product(solver_imports, "p1", ProductType.PAIR, "t1", quality=0.3)
    p1b = _make_product(solver_imports, "p1b", ProductType.PAIR, "t1", quality=0.9)
    c2a = _make_candidate(target_id="t2", start="2026-04-22T23:00:00Z", end="2026-04-22T23:00:06Z", candidate_id="c2a")
    c2b = _make_candidate(target_id="t2", start="2026-04-22T23:01:00Z", end="2026-04-22T23:01:06Z", candidate_id="c2b")
    p2 = solver_imports["StereoProduct"](
        product_id="p2", product_type=ProductType.PAIR, target_id="t2",
        satellite_id="sat_test", access_interval_id="test::0",
        observations=(c2a, c2b), quality=0.7, coverage_value=0.7,
        feasible=True, reject_reasons=tuple(),
    )

    library = solver_imports["ProductLibrary"](
        products=[p1, p1b, p2],
        per_target_products={"t1": [p1, p1b], "t2": [p2]},
        summary=solver_imports["ProductSummary"](
            total_products=3, pair_products=3, feasible_products=3,
            per_target_product_counts={"t1": 2, "t2": 1},
        ),
    )

    seed_state = create_empty_state(_FakeCase())
    solver_imports["insert_product"](p1, seed_state, _FakeCase())

    config = LocalSearchConfig(max_passes=5, max_moves_per_pass=100)
    r1 = run_local_search(seed_state, [p1], library, _FakeCase(), config)
    r2 = run_local_search(seed_state, [p1], library, _FakeCase(), config)

    assert r1.best_objective == r2.best_objective
    assert r1.moves_accepted == r2.moves_accepted
    assert r1.passes_completed == r2.passes_completed


def test_swap_remove_then_repair(solver_imports) -> None:
    sat_def = _make_sat_def()
    ProductType = solver_imports["ProductType"]
    LocalSearchState = solver_imports["LocalSearchState"]
    _try_swap = solver_imports["_try_swap"]
    create_empty_state = solver_imports["create_empty_state"]

    class _FakeCase:
        satellites = {"sat_test": sat_def}
        targets = {"t1": None, "t2": None}

    c1a = _make_candidate(target_id="t1", start="2026-04-22T22:00:00Z", end="2026-04-22T22:00:06Z", candidate_id="c1a")
    c1b = _make_candidate(target_id="t1", start="2026-04-22T22:01:00Z", end="2026-04-22T22:01:06Z", candidate_id="c1b")
    p1 = solver_imports["StereoProduct"](
        product_id="p1", product_type=ProductType.PAIR, target_id="t1",
        satellite_id="sat_test", access_interval_id="test::0",
        observations=(c1a, c1b), quality=0.3, coverage_value=0.3,
        feasible=True, reject_reasons=tuple(),
    )

    c2a = _make_candidate(target_id="t2", start="2026-04-22T22:00:00Z", end="2026-04-22T22:00:06Z", candidate_id="c2a")
    c2b = _make_candidate(target_id="t2", start="2026-04-22T22:01:00Z", end="2026-04-22T22:01:06Z", candidate_id="c2b")
    p2 = solver_imports["StereoProduct"](
        product_id="p2", product_type=ProductType.PAIR, target_id="t2",
        satellite_id="sat_test", access_interval_id="test::0",
        observations=(c2a, c2b), quality=0.8, coverage_value=0.8,
        feasible=True, reject_reasons=tuple(),
    )

    seed_state = create_empty_state(_FakeCase())
    solver_imports["insert_product"](p1, seed_state, _FakeCase())
    state = LocalSearchState.from_seed(seed_state, [p1])

    feasible_by_target = {
        "t1": [p1],
        "t2": [p2],
    }

    config = solver_imports["LocalSearchConfig"](repair_candidates_limit=5)
    accepted, new_state, reason = _try_swap(state, p1, feasible_by_target, _FakeCase(), config)
    assert accepted
    assert new_state is not None
    assert "t2" in new_state.target_to_product_id
    assert new_state.total_best_quality == pytest.approx(0.8)


def test_try_remove_frees_capacity_and_reinserts(solver_imports) -> None:
    sat_def = _make_sat_def()
    ProductType = solver_imports["ProductType"]
    LocalSearchState = solver_imports["LocalSearchState"]
    _try_remove = solver_imports["_try_remove"]
    create_empty_state = solver_imports["create_empty_state"]

    class _FakeCase:
        satellites = {"sat_test": sat_def}
        targets = {"t1": None, "t2": None}

    c1a = _make_candidate(target_id="t1", start="2026-04-22T22:00:00Z", end="2026-04-22T22:00:06Z", candidate_id="c1a")
    c1b = _make_candidate(target_id="t1", start="2026-04-22T22:01:00Z", end="2026-04-22T22:01:06Z", candidate_id="c1b")
    p1 = solver_imports["StereoProduct"](
        product_id="p1", product_type=ProductType.PAIR, target_id="t1",
        satellite_id="sat_test", access_interval_id="test::0",
        observations=(c1a, c1b), quality=0.3, coverage_value=0.3,
        feasible=True, reject_reasons=tuple(),
    )

    c2a = _make_candidate(target_id="t2", start="2026-04-22T22:00:00Z", end="2026-04-22T22:00:06Z", candidate_id="c2a")
    c2b = _make_candidate(target_id="t2", start="2026-04-22T22:01:00Z", end="2026-04-22T22:01:06Z", candidate_id="c2b")
    p2 = solver_imports["StereoProduct"](
        product_id="p2", product_type=ProductType.PAIR, target_id="t2",
        satellite_id="sat_test", access_interval_id="test::0",
        observations=(c2a, c2b), quality=0.8, coverage_value=0.8,
        feasible=True, reject_reasons=tuple(),
    )

    seed_state = create_empty_state(_FakeCase())
    solver_imports["insert_product"](p1, seed_state, _FakeCase())
    state = LocalSearchState.from_seed(seed_state, [p1])

    feasible_by_target = {
        "t1": [p1],
        "t2": [p2],
    }

    config = solver_imports["LocalSearchConfig"](remove_candidates_limit=50)
    accepted, new_state, reason = _try_remove(state, p1, feasible_by_target, _FakeCase(), config)
    assert accepted
    assert new_state is not None
    assert "t2" in new_state.target_to_product_id
    assert new_state.total_best_quality == pytest.approx(0.8)


def test_remove_move_priority_in_local_search(solver_imports) -> None:
    sat_def = _make_sat_def()
    ProductType = solver_imports["ProductType"]
    LocalSearchConfig = solver_imports["LocalSearchConfig"]
    run_local_search = solver_imports["run_local_search"]
    create_empty_state = solver_imports["create_empty_state"]

    class _FakeCase:
        satellites = {"sat_test": sat_def}
        targets = {"t1": None, "t2": None}

    c1a = _make_candidate(target_id="t1", start="2026-04-22T22:00:00Z", end="2026-04-22T22:00:06Z", candidate_id="c1a")
    c1b = _make_candidate(target_id="t1", start="2026-04-22T22:01:00Z", end="2026-04-22T22:01:06Z", candidate_id="c1b")
    p1 = solver_imports["StereoProduct"](
        product_id="p1", product_type=ProductType.PAIR, target_id="t1",
        satellite_id="sat_test", access_interval_id="test::0",
        observations=(c1a, c1b), quality=0.3, coverage_value=0.3,
        feasible=True, reject_reasons=tuple(),
    )

    c2a = _make_candidate(target_id="t2", start="2026-04-22T22:00:00Z", end="2026-04-22T22:00:06Z", candidate_id="c2a")
    c2b = _make_candidate(target_id="t2", start="2026-04-22T22:01:00Z", end="2026-04-22T22:01:06Z", candidate_id="c2b")
    p2 = solver_imports["StereoProduct"](
        product_id="p2", product_type=ProductType.PAIR, target_id="t2",
        satellite_id="sat_test", access_interval_id="test::0",
        observations=(c2a, c2b), quality=0.8, coverage_value=0.8,
        feasible=True, reject_reasons=tuple(),
    )

    library = solver_imports["ProductLibrary"](
        products=[p1, p2],
        per_target_products={"t1": [p1], "t2": [p2]},
        summary=solver_imports["ProductSummary"](
            total_products=2, pair_products=2, feasible_products=2,
            per_target_product_counts={"t1": 1, "t2": 1},
        ),
    )

    seed_state = create_empty_state(_FakeCase())
    solver_imports["insert_product"](p1, seed_state, _FakeCase())

    config = LocalSearchConfig(max_passes=5, max_moves_per_pass=100, remove_move_enabled=True)
    result = run_local_search(seed_state, [p1], library, _FakeCase(), config)

    assert result.moves_accepted >= 1
    assert result.best_objective == (1, pytest.approx(0.8))


# ---------------------------------------------------------------------------
# Repair tests
# ---------------------------------------------------------------------------


def test_repair_noop_on_clean_sequence(solver_imports) -> None:
    sat_def = _make_sat_def()
    ProductType = solver_imports["ProductType"]
    create_empty_state = solver_imports["create_empty_state"]
    insert_product = solver_imports["insert_product"]
    repair_state = solver_imports["repair_state"]

    class _FakeCase:
        satellites = {"sat_test": sat_def}
        targets = {"t1": None}

    p1 = _make_product(solver_imports, "p1", ProductType.PAIR, "t1", quality=0.8)
    state = create_empty_state(_FakeCase())
    insert_product(p1, state, _FakeCase())

    result, repaired_state, _products = repair_state(
        state, {"p1": p1}, _FakeCase(), solver_imports["RepairConfig"]()
    )
    assert result.removed_products == []
    assert result.lost_targets == []
    assert result.final_coverage == 1
    assert result.final_quality == pytest.approx(0.8)


def test_repair_removes_conflicting_product(solver_imports) -> None:
    sat_def = _make_sat_def()
    ProductType = solver_imports["ProductType"]
    create_empty_state = solver_imports["create_empty_state"]
    insert_product = solver_imports["insert_product"]
    repair_state = solver_imports["repair_state"]

    class _FakeCase:
        satellites = {"sat_test": sat_def}
        targets = {"t1": None, "t2": None}

    c1a = _make_candidate(target_id="t1", start="2026-04-22T22:00:00Z", end="2026-04-22T22:00:06Z", candidate_id="c1a")
    c1b = _make_candidate(target_id="t1", start="2026-04-22T22:01:00Z", end="2026-04-22T22:01:06Z", candidate_id="c1b")
    p1 = solver_imports["StereoProduct"](
        product_id="p1", product_type=ProductType.PAIR, target_id="t1",
        satellite_id="sat_test", access_interval_id="test::0",
        observations=(c1a, c1b), quality=0.3, coverage_value=0.3,
        feasible=True, reject_reasons=tuple(),
    )

    c2a = _make_candidate(target_id="t2", start="2026-04-22T22:00:00Z", end="2026-04-22T22:00:06Z", candidate_id="c2a")
    c2b = _make_candidate(target_id="t2", start="2026-04-22T22:01:00Z", end="2026-04-22T22:01:06Z", candidate_id="c2b")
    p2 = solver_imports["StereoProduct"](
        product_id="p2", product_type=ProductType.PAIR, target_id="t2",
        satellite_id="sat_test", access_interval_id="test::0",
        observations=(c2a, c2b), quality=0.9, coverage_value=0.9,
        feasible=True, reject_reasons=tuple(),
    )

    state = create_empty_state(_FakeCase())
    insert_product(p1, state, _FakeCase())
    seq = state.sequences["sat_test"]
    seq.observations.extend([c2a, c2b])
    seq.observations.sort(key=lambda o: o.start)

    result, repaired_state, products = repair_state(
        state, {"p1": p1, "p2": p2}, _FakeCase(), solver_imports["RepairConfig"]()
    )
    assert len(result.removed_products) == 1
    assert result.removed_products[0].product_id == "p1"
    assert "p2" in products
    assert "p1" not in products
    assert result.final_coverage == 1
    assert result.final_quality == pytest.approx(0.9)


def test_repair_deterministic(solver_imports) -> None:
    sat_def = _make_sat_def()
    ProductType = solver_imports["ProductType"]
    create_empty_state = solver_imports["create_empty_state"]
    insert_product = solver_imports["insert_product"]
    repair_state = solver_imports["repair_state"]

    class _FakeCase:
        satellites = {"sat_test": sat_def}
        targets = {"t1": None}

    p1 = _make_product(solver_imports, "p1", ProductType.PAIR, "t1", quality=0.8)
    state = create_empty_state(_FakeCase())
    insert_product(p1, state, _FakeCase())

    config = solver_imports["RepairConfig"]()
    r1, _, _ = repair_state(state, {"p1": p1}, _FakeCase(), config)
    r2, _, _ = repair_state(state, {"p1": p1}, _FakeCase(), config)
    assert r1.removed_products == r2.removed_products
    assert r1.lost_targets == r2.lost_targets
    assert r1.final_coverage == r2.final_coverage
    assert r1.final_quality == pytest.approx(r2.final_quality)


def test_repair_disabled_returns_original(solver_imports) -> None:
    sat_def = _make_sat_def()
    ProductType = solver_imports["ProductType"]
    create_empty_state = solver_imports["create_empty_state"]
    insert_product = solver_imports["insert_product"]
    repair_state = solver_imports["repair_state"]

    class _FakeCase:
        satellites = {"sat_test": sat_def}
        targets = {"t1": None}

    p1 = _make_product(solver_imports, "p1", ProductType.PAIR, "t1", quality=0.8)
    state = create_empty_state(_FakeCase())
    insert_product(p1, state, _FakeCase())

    config = solver_imports["RepairConfig"](enabled=False)
    result, repaired_state, products = repair_state(state, {"p1": p1}, _FakeCase(), config)
    assert result.removed_products == []
    assert result.final_coverage == 1
    assert repaired_state is not state
    assert len(repaired_state.sequences["sat_test"].observations) == len(state.sequences["sat_test"].observations)


# ---------------------------------------------------------------------------
# Output schema test
# ---------------------------------------------------------------------------


def test_output_schema(solver_imports, tmp_path: Path) -> None:
    sat_def = _make_sat_def()
    ProductType = solver_imports["ProductType"]
    create_empty_state = solver_imports["create_empty_state"]
    insert_product = solver_imports["insert_product"]

    class _FakeCase:
        satellites = {"sat_test": sat_def}
        targets = {"t1": None}

    p1 = _make_product(solver_imports, "p1", ProductType.PAIR, "t1", quality=0.8)
    state = create_empty_state(_FakeCase())
    insert_product(p1, state, _FakeCase())

    sys.path.insert(0, str(SOLVER_DIR / "src"))
    try:
        from solution_io import write_solution_from_state

        solution_path = write_solution_from_state(tmp_path, state)
    finally:
        sys.path.pop(0)

    data = json.loads(solution_path.read_text())
    assert "actions" in data
    assert isinstance(data["actions"], list)
    assert len(data["actions"]) == 2
    for action in data["actions"]:
        assert action["type"] == "observation"
        assert "satellite_id" in action
        assert "target_id" in action
        assert "start_time" in action
        assert "end_time" in action
        assert "off_nadir_along_deg" in action
        assert "off_nadir_across_deg" in action
    starts = [a["start_time"] for a in data["actions"]]
    assert starts == sorted(starts)


# ---------------------------------------------------------------------------
# Config parsing tests
# ---------------------------------------------------------------------------


def test_local_search_config_parses_num_runs_and_seed(solver_imports) -> None:
    LocalSearchConfig = solver_imports["LocalSearchConfig"]
    config = LocalSearchConfig.from_mapping({"num_runs": 10, "random_seed": 123})
    assert config.num_runs == 10
    assert config.random_seed == 123


def test_local_search_config_defaults(solver_imports) -> None:
    LocalSearchConfig = solver_imports["LocalSearchConfig"]
    config = LocalSearchConfig.from_mapping({})
    assert config.num_runs == 1
    assert config.random_seed == 42


def test_candidate_config_parses_parallel_workers(solver_imports) -> None:
    CandidateConfig = solver_imports["CandidateConfig"]
    config = CandidateConfig.from_mapping({"parallel_workers": 4})
    assert config.parallel_workers == 4


def test_candidate_config_parallel_workers_null_default(solver_imports) -> None:
    CandidateConfig = solver_imports["CandidateConfig"]
    config = CandidateConfig.from_mapping({})
    assert config.parallel_workers is None


def test_candidate_config_parallel_workers_zero_disables(solver_imports) -> None:
    CandidateConfig = solver_imports["CandidateConfig"]
    config = CandidateConfig.from_mapping({"parallel_workers": 0})
    assert config.parallel_workers == 0


# ---------------------------------------------------------------------------
# Parallel candidate generation identity
# ---------------------------------------------------------------------------


def _make_minimal_stereo_case(solver_imports) -> "StereoCase":
    SatelliteDef = solver_imports["SatelliteDef"]
    TargetDef = solver_imports["TargetDef"]
    Mission = solver_imports["Mission"]
    StereoCase = solver_imports["StereoCase"]

    tle1 = (
        "1 38012U 11076F   26096.23539690  .00000494  00000+0  11617-3 0  9994"
    )
    tle2 = (
        "2 38012  98.2002 172.2949 0001342  74.1943  10.7084 14.58565955761501"
    )

    sat_a = SatelliteDef(
        sat_id="sat_a", norad_catalog_id=38012, tle_line1=tle1, tle_line2=tle2,
        pixel_ifov_deg=4.0e-5, cross_track_pixels=20000, max_off_nadir_deg=30.0,
        max_slew_velocity_deg_per_s=1.95, max_slew_acceleration_deg_per_s2=0.95,
        settling_time_s=1.9, min_obs_duration_s=2.0, max_obs_duration_s=60.0,
    )
    sat_b = SatelliteDef(
        sat_id="sat_b", norad_catalog_id=38012, tle_line1=tle1, tle_line2=tle2,
        pixel_ifov_deg=4.0e-5, cross_track_pixels=20000, max_off_nadir_deg=30.0,
        max_slew_velocity_deg_per_s=1.95, max_slew_acceleration_deg_per_s2=0.95,
        settling_time_s=1.9, min_obs_duration_s=2.0, max_obs_duration_s=60.0,
    )

    target_1 = TargetDef(
        target_id="t1", latitude_deg=48.8566, longitude_deg=2.3522,
        aoi_radius_m=5000.0, elevation_ref_m=0.0, scene_type="urban_structured",
    )
    target_2 = TargetDef(
        target_id="t2", latitude_deg=40.7128, longitude_deg=-74.0060,
        aoi_radius_m=5000.0, elevation_ref_m=0.0, scene_type="open",
    )

    mission = Mission(
        horizon_start=datetime(2026, 4, 22, 0, 0, 0, tzinfo=UTC),
        horizon_end=datetime(2026, 4, 23, 0, 0, 0, tzinfo=UTC),
        allow_cross_satellite_stereo=True,
        allow_cross_date_stereo=False,
        min_overlap_fraction=0.5,
        min_convergence_deg=5.0,
        max_convergence_deg=35.0,
        max_pixel_scale_ratio=2.0,
        min_solar_elevation_deg=10.0,
        near_nadir_anchor_max_off_nadir_deg=15.0,
        pair_weights={"urban_structured": 0.9, "open": 1.0},
        tri_stereo_bonus_by_scene={"urban_structured": 0.15, "open": 0.1},
    )

    return StereoCase(
        case_dir=Path("/tmp/test_case"),
        mission=mission,
        satellites={"sat_a": sat_a, "sat_b": sat_b},
        targets={"t1": target_1, "t2": target_2},
    )


def test_parallel_candidates_identical_to_serial(solver_imports) -> None:
    CandidateConfig = solver_imports["CandidateConfig"]
    generate_candidates = solver_imports["generate_candidates"]

    case = _make_minimal_stereo_case(solver_imports)
    config_serial = CandidateConfig(parallel_workers=0)
    config_parallel = CandidateConfig(parallel_workers=2)

    candidates_serial, summary_serial = generate_candidates(case, config_serial)
    candidates_parallel, summary_parallel = generate_candidates(case, config_parallel)

    assert summary_parallel.candidate_count == summary_serial.candidate_count
    assert summary_parallel.per_satellite_candidate_counts == summary_serial.per_satellite_candidate_counts
    assert summary_parallel.per_target_candidate_counts == summary_serial.per_target_candidate_counts
    assert summary_parallel.skipped_no_access_intervals == summary_serial.skipped_no_access_intervals
    assert summary_parallel.skipped_off_nadir == summary_serial.skipped_off_nadir
    assert summary_parallel.skipped_solar_elevation == summary_serial.skipped_solar_elevation

    serial_ids = [c.candidate_id for c in candidates_serial]
    parallel_ids = [c.candidate_id for c in candidates_parallel]
    assert parallel_ids == serial_ids


# ---------------------------------------------------------------------------
# Multi-run harness tests
# ---------------------------------------------------------------------------


def test_multi_run_different_results_with_rng(solver_imports) -> None:
    import random
    from seed import SeedConfig, build_greedy_seed
    from products import ProductLibrary, ProductSummary

    case = _make_minimal_stereo_case(solver_imports)
    config = SeedConfig()
    rng1 = random.Random(1)
    rng2 = random.Random(2)

    empty_lib = ProductLibrary(products=[], per_target_products={}, summary=ProductSummary(
        total_products=0, pair_products=0, feasible_products=0, per_target_product_counts={}
    ))

    result1 = build_greedy_seed(empty_lib, case, config, rng=rng1)
    result2 = build_greedy_seed(empty_lib, case, config, rng=rng2)
    assert result1.accepted_count == 0
    assert result2.accepted_count == 0


def test_multi_run_keeps_best_result(solver_imports) -> None:
    from solve import _pipeline_objective
    from repair import RepairResult

    r1 = RepairResult(removed_products=[], lost_targets=set(), final_coverage=10, final_quality=5.0)
    r2 = RepairResult(removed_products=[], lost_targets=set(), final_coverage=12, final_quality=3.0)
    r3 = RepairResult(removed_products=[], lost_targets=set(), final_coverage=10, final_quality=7.0)

    assert _pipeline_objective(r1) == (10, 5.0)
    assert _pipeline_objective(r2) == (12, 3.0)
    assert _pipeline_objective(r3) == (10, 7.0)

    best = max([r1, r2, r3], key=_pipeline_objective)
    assert best.final_coverage == 12

    r4 = RepairResult(removed_products=[], lost_targets=set(), final_coverage=10, final_quality=7.0)
    best2 = max([r1, r3, r4], key=_pipeline_objective)
    assert best2.final_quality == 7.0


def test_status_includes_multi_run_stats_when_enabled(solver_imports) -> None:
    from solve import _build_status
    from candidates import CandidateSummary
    from products import ProductLibrary, ProductSummary
    from seed import SeedResult, SeedConfig
    from local_search import LocalSearchConfig
    from repair import RepairResult, RepairConfig
    import tempfile

    case_dir = Path(tempfile.mkdtemp())
    solution_path = case_dir / "solution.json"

    candidate_config = solver_imports["CandidateConfig"]()
    product_library = ProductLibrary(
        products=[], per_target_products={},
        summary=ProductSummary(total_products=0, pair_products=0, feasible_products=0, per_target_product_counts={})
    )
    seed_result = SeedResult(
        accepted_products=[], rejected_records=[], covered_targets=set(),
        state=None, config=SeedConfig(), iterations=0
    )
    repair_result = RepairResult(
        removed_products=[], lost_targets=set(), final_coverage=5, final_quality=3.0
    )
    multi_run_stats = {
        "num_runs": 3,
        "random_seed": 42,
        "best_run": 1,
        "best_coverage": 5,
        "best_quality": 3.0,
        "mean_coverage": 4.33,
        "mean_quality": 2.5,
        "min_coverage": 3,
        "min_quality": 1.0,
        "all_coverages": [3, 5, 5],
        "all_qualities": [1.0, 3.0, 3.5],
    }

    status = _build_status(
        case_dir=case_dir,
        config_dir=None,
        solution_path=solution_path,
        case_id="test",
        satellite_count=2,
        candidate_config=candidate_config,
        candidate_summary=CandidateSummary(),
        product_config=solver_imports["CandidateConfig"](),
        product_library=product_library,
        sequence_sanity={},
        timing_seconds={"total": 1.0},
        seed_result=seed_result,
        repair_result=repair_result,
        repair_config=RepairConfig(),
        local_search_config=LocalSearchConfig(),
        multi_run_stats=multi_run_stats,
    )

    assert status["multi_run_stats"] == multi_run_stats
    assert status["status"] == "phase_7b_multi_run"
