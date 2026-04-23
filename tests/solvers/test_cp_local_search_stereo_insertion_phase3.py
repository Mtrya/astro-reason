"""Focused Phase 3 tests for deterministic greedy seed construction."""

from __future__ import annotations

import math
import sys
from datetime import UTC, datetime, timedelta
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
            SatelliteSequence,
            SequenceState,
            create_empty_state,
            insert_product,
        )
        from seed import (
            SeedConfig,
            SeedResult,
            build_greedy_seed,
            _product_sort_key,
            _compute_remaining_counts,
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
            "SatelliteSequence": SatelliteSequence,
            "SequenceState": SequenceState,
            "create_empty_state": create_empty_state,
            "insert_product": insert_product,
            "EarthSatellite": EarthSatellite,
            "SeedConfig": SeedConfig,
            "SeedResult": SeedResult,
            "build_greedy_seed": build_greedy_seed,
            "_product_sort_key": _product_sort_key,
            "_compute_remaining_counts": _compute_remaining_counts,
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
# Ranking tests
# ---------------------------------------------------------------------------


def test_ranking_uncovered_target_first(solver_imports) -> None:
    ProductType = solver_imports["ProductType"]
    SeedConfig = solver_imports["SeedConfig"]
    _product_sort_key = solver_imports["_product_sort_key"]

    config = SeedConfig()
    covered = {"t2"}
    remaining = {"t1": 5, "t2": 5}

    p_uncovered = _make_product(
        solver_imports, "p1", ProductType.PAIR, "t1", quality=0.3
    )
    p_covered = _make_product(
        solver_imports, "p2", ProductType.PAIR, "t2", quality=0.9
    )

    k1 = _product_sort_key(p_uncovered, covered, remaining, config)
    k2 = _product_sort_key(p_covered, covered, remaining, config)
    # Uncovered target should win (coverage_value 1.0 > 0.0)
    assert k1[0] > k2[0]


def test_ranking_scarcity_tiebreak(solver_imports) -> None:
    ProductType = solver_imports["ProductType"]
    SeedConfig = solver_imports["SeedConfig"]
    _product_sort_key = solver_imports["_product_sort_key"]

    config = SeedConfig()
    covered: set[str] = set()
    remaining = {"t1": 2, "t2": 10}

    p_scarce = _make_product(
        solver_imports, "p1", ProductType.PAIR, "t1", quality=0.5
    )
    p_abundant = _make_product(
        solver_imports, "p2", ProductType.PAIR, "t2", quality=0.5
    )

    k1 = _product_sort_key(p_scarce, covered, remaining, config)
    k2 = _product_sort_key(p_abundant, covered, remaining, config)
    # Same coverage_value and weighted_quality; scarce target wins on scarcity
    assert k1[2] > k2[2]


def test_ranking_tri_before_pair(solver_imports) -> None:
    ProductType = solver_imports["ProductType"]
    SeedConfig = solver_imports["SeedConfig"]
    _product_sort_key = solver_imports["_product_sort_key"]

    config = SeedConfig()  # tri_weight=1.5 > pair_weight=1.0
    covered = {"t1"}
    remaining = {"t1": 5}

    p_tri = _make_product(
        solver_imports, "p_tri", ProductType.TRI, "t1", quality=0.5
    )
    p_pair = _make_product(
        solver_imports, "p_pair", ProductType.PAIR, "t1", quality=0.5
    )

    k1 = _product_sort_key(p_tri, covered, remaining, config)
    k2 = _product_sort_key(p_pair, covered, remaining, config)
    # Tri should win on weighted_quality (0.5*1.5 > 0.5*1.0)
    assert k1[1] > k2[1]


def test_ranking_pair_before_tri_when_configured(solver_imports) -> None:
    ProductType = solver_imports["ProductType"]
    SeedConfig = solver_imports["SeedConfig"]
    _product_sort_key = solver_imports["_product_sort_key"]

    config = SeedConfig(tri_weight=0.5, pair_weight=1.0)
    covered = {"t1"}
    remaining = {"t1": 5}

    p_tri = _make_product(
        solver_imports, "p_tri", ProductType.TRI, "t1", quality=0.5
    )
    p_pair = _make_product(
        solver_imports, "p_pair", ProductType.PAIR, "t1", quality=0.5
    )

    k1 = _product_sort_key(p_tri, covered, remaining, config)
    k2 = _product_sort_key(p_pair, covered, remaining, config)
    # Pair should win on weighted_quality when tri_weight < pair_weight
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


# ---------------------------------------------------------------------------
# Greedy seed behavior tests
# ---------------------------------------------------------------------------


def test_greedy_seed_accepts_feasible_product(solver_imports) -> None:
    ProductType = solver_imports["ProductType"]
    ProductLibrary = solver_imports["ProductLibrary"]
    ProductSummary = solver_imports["ProductSummary"]
    SeedConfig = solver_imports["SeedConfig"]
    build_greedy_seed = solver_imports["build_greedy_seed"]

    product = _make_product(
        solver_imports, "p1", ProductType.PAIR, "t1", quality=0.8
    )
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
    """Two products for the same target on the same satellite; second overlaps first."""
    ProductType = solver_imports["ProductType"]
    ProductLibrary = solver_imports["ProductLibrary"]
    ProductSummary = solver_imports["ProductSummary"]
    SeedConfig = solver_imports["SeedConfig"]
    build_greedy_seed = solver_imports["build_greedy_seed"]

    sat_def = _make_sat_def()

    # First product: 22:00:00 – 22:00:06
    c1a = _make_candidate(
        start="2026-04-22T22:00:00Z",
        end="2026-04-22T22:00:06Z",
        candidate_id="c1a",
    )
    c1b = _make_candidate(
        start="2026-04-22T22:01:00Z",
        end="2026-04-22T22:01:06Z",
        candidate_id="c1b",
    )
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

    # Second product overlaps first: 22:00:03 – 22:00:09
    c2a = _make_candidate(
        start="2026-04-22T22:00:03Z",
        end="2026-04-22T22:00:09Z",
        candidate_id="c2a",
    )
    c2b = _make_candidate(
        start="2026-04-22T22:01:03Z",
        end="2026-04-22T22:01:09Z",
        candidate_id="c2b",
    )
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

    # p2 has higher quality, so it should be tried first and accepted.
    # After p2 is inserted, target t1 is covered.  p1 is skipped (not
    # rejected) because the solver does not attempt insertion for products
    # whose target is already covered.
    seed = build_greedy_seed(library, _FakeCase(), SeedConfig())
    assert seed.accepted_count == 1
    assert seed.accepted_products[0].product_id == "p2"
    # p1 should not be in accepted products
    assert "p1" not in [p.product_id for p in seed.accepted_products]


# ---------------------------------------------------------------------------
# Repeatability and edge-case tests
# ---------------------------------------------------------------------------


def test_seed_repeatability(solver_imports) -> None:
    """Run greedy seed twice with identical inputs and compare results."""
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
    """Tri-stereo pre-phase should accept a feasible tri product and exclude
    pair products for the same target from the pair phase."""
    ProductType = solver_imports["ProductType"]
    ProductLibrary = solver_imports["ProductLibrary"]
    ProductSummary = solver_imports["ProductSummary"]
    SeedConfig = solver_imports["SeedConfig"]
    build_greedy_seed = solver_imports["build_greedy_seed"]

    sat_def = _make_sat_def()

    # Tri-stereo product: three candidates spaced 2 min apart
    c1 = _make_candidate(
        start="2026-04-22T22:00:00Z",
        end="2026-04-22T22:00:06Z",
        candidate_id="c1",
    )
    c2 = _make_candidate(
        start="2026-04-22T22:02:00Z",
        end="2026-04-22T22:02:06Z",
        candidate_id="c2",
    )
    c3 = _make_candidate(
        start="2026-04-22T22:04:00Z",
        end="2026-04-22T22:04:06Z",
        candidate_id="c3",
    )
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

    # Pair product for same target (different candidates, also feasible)
    c4 = _make_candidate(
        start="2026-04-22T22:06:00Z",
        end="2026-04-22T22:06:06Z",
        candidate_id="c4",
    )
    c5 = _make_candidate(
        start="2026-04-22T22:08:00Z",
        end="2026-04-22T22:08:06Z",
        candidate_id="c5",
    )
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

    # With tri_stereo_seed_phase=True (default), tri should be attempted first.
    # If tri inserts successfully, pair is skipped because target is covered.
    seed = build_greedy_seed(library, _FakeCase(), SeedConfig())
    assert seed.tri_accepted >= 1
    assert "p_tri" in [p.product_id for p in seed.accepted_products]
    # Pair should NOT be in accepted because t1 is already covered by tri
    assert "p_pair" not in [p.product_id for p in seed.accepted_products]


def test_tri_stereo_pre_phase_disabled(solver_imports) -> None:
    """When tri_stereo_seed_phase=False, tri products compete in the same pool."""
    ProductType = solver_imports["ProductType"]
    ProductLibrary = solver_imports["ProductLibrary"]
    ProductSummary = solver_imports["ProductSummary"]
    SeedConfig = solver_imports["SeedConfig"]
    build_greedy_seed = solver_imports["build_greedy_seed"]

    sat_def = _make_sat_def()

    c1 = _make_candidate(
        start="2026-04-22T22:00:00Z",
        end="2026-04-22T22:00:06Z",
        candidate_id="c1",
    )
    c2 = _make_candidate(
        start="2026-04-22T22:02:00Z",
        end="2026-04-22T22:02:06Z",
        candidate_id="c2",
    )
    c3 = _make_candidate(
        start="2026-04-22T22:04:00Z",
        end="2026-04-22T22:04:06Z",
        candidate_id="c3",
    )
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

    c4 = _make_candidate(
        start="2026-04-22T22:06:00Z",
        end="2026-04-22T22:06:06Z",
        candidate_id="c4",
    )
    c5 = _make_candidate(
        start="2026-04-22T22:08:00Z",
        end="2026-04-22T22:08:06Z",
        candidate_id="c5",
    )
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
    # With tri_weight < pair_weight, pair has higher weighted_quality
    # (0.9*1.0 > 0.7*0.5) so pair is accepted first; tri is skipped.
    assert seed.tri_accepted == 0
    assert "p_pair" in [p.product_id for p in seed.accepted_products]
