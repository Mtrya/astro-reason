"""Focused Phase 5 tests for repair, experiment wiring, and output schema."""

from __future__ import annotations

import json
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
        from repair import (
            RepairConfig,
            RepairResult,
            repair_state,
            _find_first_conflict,
        )
        from local_search import LocalSearchState
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
            "RepairConfig": RepairConfig,
            "RepairResult": RepairResult,
            "repair_state": repair_state,
            "_find_first_conflict": _find_first_conflict,
            "LocalSearchState": LocalSearchState,
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
# Repair tests
# ---------------------------------------------------------------------------


def test_repair_noop_on_clean_sequence(solver_imports) -> None:
    """Repair on a sequence with no conflicts removes nothing."""
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
    """When two products overlap, repair removes the lower-quality one."""
    sat_def = _make_sat_def()
    ProductType = solver_imports["ProductType"]
    create_empty_state = solver_imports["create_empty_state"]
    insert_product = solver_imports["insert_product"]
    repair_state = solver_imports["repair_state"]

    class _FakeCase:
        satellites = {"sat_test": sat_def}
        targets = {"t1": None, "t2": None}

    # p1 for t1 at 22:00-22:01 (low quality)
    c1a = _make_candidate(target_id="t1", start="2026-04-22T22:00:00Z", end="2026-04-22T22:00:06Z", candidate_id="c1a")
    c1b = _make_candidate(target_id="t1", start="2026-04-22T22:01:00Z", end="2026-04-22T22:01:06Z", candidate_id="c1b")
    p1 = solver_imports["StereoProduct"](
        product_id="p1", product_type=ProductType.PAIR, target_id="t1",
        satellite_id="sat_test", access_interval_id="test::0",
        observations=(c1a, c1b), quality=0.3, coverage_value=0.3,
        feasible=True, reject_reasons=tuple(),
    )

    # p2 for t2 at 22:00-22:01 (overlaps with p1, high quality)
    c2a = _make_candidate(target_id="t2", start="2026-04-22T22:00:00Z", end="2026-04-22T22:00:06Z", candidate_id="c2a")
    c2b = _make_candidate(target_id="t2", start="2026-04-22T22:01:00Z", end="2026-04-22T22:01:06Z", candidate_id="c2b")
    p2 = solver_imports["StereoProduct"](
        product_id="p2", product_type=ProductType.PAIR, target_id="t2",
        satellite_id="sat_test", access_interval_id="test::0",
        observations=(c2a, c2b), quality=0.9, coverage_value=0.9,
        feasible=True, reject_reasons=tuple(),
    )

    # Manually build a state with both products inserted (they overlap)
    state = create_empty_state(_FakeCase())
    insert_product(p1, state, _FakeCase())
    # Force-insert p2 by directly adding its observations to the sequence
    # (bypassing insert_product's feasibility check to create a conflict)
    seq = state.sequences["sat_test"]
    seq.observations.extend([c2a, c2b])
    # Sort by start to make them adjacent
    seq.observations.sort(key=lambda o: o.start)

    result, repaired_state, products = repair_state(
        state, {"p1": p1, "p2": p2}, _FakeCase(), solver_imports["RepairConfig"]()
    )
    assert len(result.removed_products) == 1
    # Lower-quality product p1 should be removed
    assert result.removed_products[0].product_id == "p1"
    assert "p2" in products
    assert "p1" not in products
    assert result.final_coverage == 1
    assert result.final_quality == pytest.approx(0.9)


def test_repair_deterministic(solver_imports) -> None:
    """Same input produces identical repair output."""
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
    """When repair is disabled, the original state is returned unchanged."""
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
    # State should be a clone, not the same object
    assert repaired_state is not state
    assert len(repaired_state.sequences["sat_test"].observations) == len(state.sequences["sat_test"].observations)


# ---------------------------------------------------------------------------
# Output schema test
# ---------------------------------------------------------------------------


def test_output_schema(solver_imports, tmp_path: Path) -> None:
    """write_solution_from_state produces a valid benchmark solution schema."""
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
    assert len(data["actions"]) == 2  # PAIR has 2 observations
    for action in data["actions"]:
        assert action["type"] == "observation"
        assert "satellite_id" in action
        assert "target_id" in action
        assert "start_time" in action
        assert "end_time" in action
        assert "off_nadir_along_deg" in action
        assert "off_nadir_across_deg" in action
    # Deterministic ordering
    starts = [a["start_time"] for a in data["actions"]]
    assert starts == sorted(starts)
