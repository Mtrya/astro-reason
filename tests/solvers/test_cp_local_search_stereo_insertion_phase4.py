"""Focused Phase 4 tests for local search product moves."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SOLVER_DIR = REPO_ROOT / "solvers" / "stereo_imaging" / "cp_local_search_stereo_insertion"

# Pleiades-1A TLE from verifier tests
_PLEIADES_TLE_LINE1 = (
    "1 38012U 11076F   26096.23539690  .00000494  00000+0  11617-3 0  9994"
)
_PLEIADES_TLE_LINE2 = (
    "2 38012  98.2002 172.2949 0001342  74.1943  10.7084 14.58565955761501"
)


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


@pytest.fixture
def solver_imports():
    sys.path.insert(0, str(SOLVER_DIR / "src"))
    try:
        from case_io import SatelliteDef, StereoCase
        from candidates import Candidate
        from geometry import _TS
        from products import StereoProduct, ProductType, ProductLibrary, ProductSummary
        from sequence import (
            SequenceState,
            create_empty_state,
            insert_product,
            remove_product,
        )
        from local_search import (
            LocalSearchConfig,
            LocalSearchState,
            run_local_search,
            _try_insert,
            _try_replace,
            _try_swap,
        )
        from skyfield.api import EarthSatellite

        yield {
            "SatelliteDef": SatelliteDef,
            "StereoCase": StereoCase,
            "Candidate": Candidate,
            "_TS": _TS,
            "StereoProduct": StereoProduct,
            "ProductType": ProductType,
            "ProductLibrary": ProductLibrary,
            "ProductSummary": ProductSummary,
            "SequenceState": SequenceState,
            "create_empty_state": create_empty_state,
            "insert_product": insert_product,
            "remove_product": remove_product,
            "EarthSatellite": EarthSatellite,
            "LocalSearchConfig": LocalSearchConfig,
            "LocalSearchState": LocalSearchState,
            "run_local_search": run_local_search,
            "_try_insert": _try_insert,
            "_try_replace": _try_replace,
            "_try_swap": _try_swap,
        }
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
# Unit tests for move evaluators
# ---------------------------------------------------------------------------


def test_try_insert_increases_coverage(solver_imports) -> None:
    """Inserting a product for an uncovered target increases objective."""
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
    """Replacing a low-quality product with a higher-quality one improves objective."""
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

    # Seed with low-quality product
    seed_state = create_empty_state(_FakeCase())
    solver_imports["insert_product"](low, seed_state, _FakeCase())
    state = LocalSearchState.from_seed(seed_state, [low])

    accepted, new_state, reason = _try_replace(state, low, high, _FakeCase())
    assert accepted
    assert new_state is not None
    assert new_state.total_best_quality == pytest.approx(0.9)


def test_try_replace_rollback_on_failure(solver_imports) -> None:
    """If replacement insert fails, the state is unchanged."""
    sat_def = _make_sat_def()
    ProductType = solver_imports["ProductType"]
    LocalSearchState = solver_imports["LocalSearchState"]
    _try_replace = solver_imports["_try_replace"]
    create_empty_state = solver_imports["create_empty_state"]

    class _FakeCase:
        satellites = {"sat_test": sat_def}
        targets = {"t1": None}

    # Two products for same target that overlap in time (can't both be in sequence)
    c1a = _make_candidate(start="2026-04-22T22:00:00Z", end="2026-04-22T22:00:06Z", candidate_id="c1a")
    c1b = _make_candidate(start="2026-04-22T22:01:00Z", end="2026-04-22T22:01:06Z", candidate_id="c1b")
    low = solver_imports["StereoProduct"](
        product_id="p_low", product_type=ProductType.PAIR, target_id="t1",
        satellite_id="sat_test", access_interval_id="test::0",
        observations=(c1a, c1b), quality=0.3, coverage_value=0.3,
        feasible=True, reject_reasons=tuple(),
    )

    # High product overlaps with low (shares c1a and adds overlapping c2)
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
    """When no moves improve, search stops after one pass."""
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
    # No improving moves possible (only one product, already scheduled)
    assert result.passes_completed == 1
    assert result.moves_accepted == 0


def test_seed_vs_improved_objective(solver_imports) -> None:
    """Local search result is at least as good as the seed."""
    sat_def = _make_sat_def()
    ProductType = solver_imports["ProductType"]
    LocalSearchConfig = solver_imports["LocalSearchConfig"]
    run_local_search = solver_imports["run_local_search"]
    create_empty_state = solver_imports["create_empty_state"]

    class _FakeCase:
        satellites = {"sat_test": sat_def}
        targets = {"t1": None, "t2": None}

    # Seed covers t1 with low quality
    p1 = _make_product(solver_imports, "p1", ProductType.PAIR, "t1", quality=0.3)
    seed_state = create_empty_state(_FakeCase())
    solver_imports["insert_product"](p1, seed_state, _FakeCase())

    # Better product for t1 exists, plus product for uncovered t2
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
    """Same inputs produce identical best objective and final state."""
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
    """Removing a low-quality blocking product allows inserting a better one."""
    sat_def = _make_sat_def()
    ProductType = solver_imports["ProductType"]
    LocalSearchState = solver_imports["LocalSearchState"]
    _try_swap = solver_imports["_try_swap"]
    create_empty_state = solver_imports["create_empty_state"]

    class _FakeCase:
        satellites = {"sat_test": sat_def}
        targets = {"t1": None, "t2": None}

    # Product for t1 at 22:00-22:01
    c1a = _make_candidate(target_id="t1", start="2026-04-22T22:00:00Z", end="2026-04-22T22:00:06Z", candidate_id="c1a")
    c1b = _make_candidate(target_id="t1", start="2026-04-22T22:01:00Z", end="2026-04-22T22:01:06Z", candidate_id="c1b")
    p1 = solver_imports["StereoProduct"](
        product_id="p1", product_type=ProductType.PAIR, target_id="t1",
        satellite_id="sat_test", access_interval_id="test::0",
        observations=(c1a, c1b), quality=0.3, coverage_value=0.3,
        feasible=True, reject_reasons=tuple(),
    )

    # Product for t2 at 22:00-22:01 (overlaps with p1)
    c2a = _make_candidate(target_id="t2", start="2026-04-22T22:00:00Z", end="2026-04-22T22:00:06Z", candidate_id="c2a")
    c2b = _make_candidate(target_id="t2", start="2026-04-22T22:01:00Z", end="2026-04-22T22:01:06Z", candidate_id="c2b")
    p2 = solver_imports["StereoProduct"](
        product_id="p2", product_type=ProductType.PAIR, target_id="t2",
        satellite_id="sat_test", access_interval_id="test::0",
        observations=(c2a, c2b), quality=0.8, coverage_value=0.8,
        feasible=True, reject_reasons=tuple(),
    )

    # Build seed with p1 (blocks p2 due to overlap)
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
    # Should have removed p1 and inserted p2
    assert "t2" in new_state.target_to_product_id
    assert new_state.total_best_quality == pytest.approx(0.8)
