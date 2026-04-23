"""Focused Phase 2 tests for sequence propagation, insertion, and rollback."""

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
) -> "SatelliteDef":
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
) -> "Candidate":
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
        from products import StereoProduct, ProductType
        from skyfield.api import EarthSatellite

        yield {
            "SatelliteDef": SatelliteDef,
            "StereoCase": StereoCase,
            "Candidate": Candidate,
            "_TS": _TS,
            "SatelliteSequence": SatelliteSequence,
            "SequenceState": SequenceState,
            "compute_earliest": compute_earliest,
            "compute_latest": compute_latest,
            "create_empty_state": create_empty_state,
            "insert_observation": insert_observation,
            "insert_product": insert_product,
            "is_consistent": is_consistent,
            "possible_insertion_positions": possible_insertion_positions,
            "propagate": propagate,
            "remove_observation": remove_observation,
            "remove_product": remove_product,
            "_slew_gap_required_s": _slew_gap_required_s,
            "StereoProduct": StereoProduct,
            "ProductType": ProductType,
            "EarthSatellite": EarthSatellite,
        }
    finally:
        sys.path.pop(0)


# ---------------------------------------------------------------------------
# Basic insertion positions
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

    # First observation at 22:00:00 – 22:00:06
    first = _make_candidate(start="2026-04-22T22:00:00Z", end="2026-04-22T22:00:06Z", candidate_id="c0")
    solver_imports["insert_observation"](first, seq, 0, sat_def, sf)
    ok, _ = solver_imports["is_consistent"](seq)
    assert ok

    # Second observation well before first: 21:59:00 – 21:59:06
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


# ---------------------------------------------------------------------------
# Rejection tests
# ---------------------------------------------------------------------------


def test_overlap_rejection(solver_imports) -> None:
    sat_def = _make_sat_def()
    sf = solver_imports["EarthSatellite"](sat_def.tle_line1, sat_def.tle_line2, name="sat_test", ts=solver_imports["_TS"])
    seq = solver_imports["SatelliteSequence"](satellite_id="sat_test")

    c0 = _make_candidate(start="2026-04-22T22:00:00Z", end="2026-04-22T22:00:06Z", candidate_id="c0")
    solver_imports["insert_observation"](c0, seq, 0, sat_def, sf)

    # Overlapping candidate
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

    # Very close in time but with large steering change → insufficient slew gap
    # Using a large across-track angle to force a big slew
    c1 = _make_candidate(
        start="2026-04-22T22:00:07Z",
        end="2026-04-22T22:00:13Z",
        candidate_id="c1",
        across=25.0,
    )
    positions = solver_imports["possible_insertion_positions"](c1, seq, sat_def, sf)
    # With 1 second gap and a 25-degree slew, the required gap should exceed 1 second
    assert len(positions) == 0 or (len(positions) == 1 and positions[0] == 1 and False)
    # Actually let's just check that insertion at the end fails
    result = solver_imports["insert_observation"](c1, seq, len(seq.observations), sat_def, sf)
    assert not result.success


# ---------------------------------------------------------------------------
# Rollback tests
# ---------------------------------------------------------------------------


def test_rollback_after_failed_partner(solver_imports) -> None:
    sat_def = _make_sat_def()
    sf = solver_imports["EarthSatellite"](sat_def.tle_line1, sat_def.tle_line2, name="sat_test", ts=solver_imports["_TS"])
    seq = solver_imports["SatelliteSequence"](satellite_id="sat_test")

    c0 = _make_candidate(start="2026-04-22T22:00:00Z", end="2026-04-22T22:00:06Z", candidate_id="c0")
    solver_imports["insert_observation"](c0, seq, 0, sat_def, sf)

    # Product: first observation fits, second overlaps
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

    # Build a minimal case stub
    class _FakeCase:
        satellites = {"sat_test": sat_def}

    state = solver_imports["SequenceState"](
        sequences={"sat_test": seq},
        sf_sats={"sat_test": sf},
    )

    result = solver_imports["insert_product"](product, state, _FakeCase())
    assert not result.success
    # Original observation should still be there
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


# ---------------------------------------------------------------------------
# Consistency and determinism
# ---------------------------------------------------------------------------


def test_propagation_consistency_after_insert_remove(solver_imports) -> None:
    sat_def = _make_sat_def()
    sf = solver_imports["EarthSatellite"](sat_def.tle_line1, sat_def.tle_line2, name="sat_test", ts=solver_imports["_TS"])
    seq = solver_imports["SatelliteSequence"](satellite_id="sat_test")

    c0 = _make_candidate(start="2026-04-22T22:00:00Z", end="2026-04-22T22:00:06Z", candidate_id="c0")
    c1 = _make_candidate(start="2026-04-22T22:01:00Z", end="2026-04-22T22:01:06Z", candidate_id="c1")

    # Insert both
    solver_imports["insert_observation"](c0, seq, 0, sat_def, sf)
    solver_imports["insert_observation"](c1, seq, 1, sat_def, sf)
    ok, _ = solver_imports["is_consistent"](seq)
    assert ok
    e_after_insert = dict(seq.earliest)
    l_after_insert = dict(seq.latest)

    # Remove both
    solver_imports["remove_observation"]("c0", seq, sat_def, sf)
    solver_imports["remove_observation"]("c1", seq, sat_def, sf)
    assert len(seq.observations) == 0
    assert seq.earliest == {}
    assert seq.latest == {}

    # Re-insert both
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

    # Reset and re-insert c0
    seq2 = solver_imports["SatelliteSequence"](satellite_id="sat_test")
    solver_imports["insert_observation"](c0, seq2, 0, sat_def, sf)
    positions_2 = solver_imports["possible_insertion_positions"](c1, seq2, sat_def, sf)

    assert positions_1 == positions_2
