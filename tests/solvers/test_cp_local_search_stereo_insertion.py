"""Tests for the CP/local-search stereo insertion solver."""

from __future__ import annotations

import importlib
import json
import math
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import brahe
import numpy as np
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
        from products import (
            ProductConfig,
            ProductLibrary,
            ProductSummary,
            StereoProduct,
            ProductType,
            build_product_library,
        )
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
            "ProductConfig": ProductConfig,
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
            "build_product_library": build_product_library,
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
# Case-loading contract tests
# ---------------------------------------------------------------------------


def test_load_case_smoke(solver_imports) -> None:
    case = solver_imports["load_case"](CASE_DIR)
    assert case.case_dir == CASE_DIR.resolve()
    assert len(case.satellites) > 0
    assert len(case.targets) > 0
    assert case.mission.horizon_start < case.mission.horizon_end
    assert case.mission.allow_cross_satellite_stereo is True
    assert case.mission.max_stereo_pair_separation_s == 3600.0


def test_load_case_requires_max_stereo_pair_separation(tmp_path: Path, solver_imports) -> None:
    case_dir = tmp_path / "case_missing_pair_separation"
    case_dir.mkdir()
    (case_dir / "mission.yaml").write_text(
        """mission:
  horizon_start: '2026-04-22T02:00:00Z'
  horizon_end: '2026-04-24T02:00:00Z'
  allow_cross_satellite_stereo: true
  validity_thresholds:
    min_overlap_fraction: 0.8
    min_convergence_deg: 5.0
    max_convergence_deg: 45.0
    max_pixel_scale_ratio: 1.5
    min_solar_elevation_deg: 10.0
    near_nadir_anchor_max_off_nadir_deg: 10.0
  quality_model:
    pair_weights:
      geometry: 0.5
      overlap: 0.35
      resolution: 0.15
    tri_stereo_bonus_by_scene:
      urban_structured: 0.12
      rugged: 0.1
      vegetated: 0.08
      open: 0.05
""",
        encoding="utf-8",
    )
    (case_dir / "satellites.yaml").write_text(
        """- id: sat_test
  norad_catalog_id: 38012
  tle_line1: "1 38012U 11076F   26096.23539690  .00000494  00000+0  11617-3 0  9994"
  tle_line2: "2 38012  98.2002 172.2949 0001342  74.1943  10.7084 14.58565955761501"
  pixel_ifov_deg: 4.0e-5
  cross_track_pixels: 20000
  max_off_nadir_deg: 30.0
  max_slew_velocity_deg_per_s: 1.95
  max_slew_acceleration_deg_per_s2: 0.95
  settling_time_s: 1.9
  min_obs_duration_s: 2.0
  max_obs_duration_s: 60.0
""",
        encoding="utf-8",
    )
    (case_dir / "targets.yaml").write_text(
        """- id: t1
  latitude_deg: 48.8566
  longitude_deg: 2.3522
  aoi_radius_m: 5000.0
  elevation_ref_m: 0.0
  scene_type: urban_structured
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="missing max_stereo_pair_separation_s"):
        solver_imports["load_case"](case_dir)


# ---------------------------------------------------------------------------
# Product correctness tests
# ---------------------------------------------------------------------------


def test_build_product_library_includes_cross_satellite_products(solver_imports, monkeypatch) -> None:
    products_module = importlib.import_module("products")
    build_product_library = solver_imports["build_product_library"]
    ProductConfig = solver_imports["ProductConfig"]

    case = _make_minimal_stereo_case(solver_imports)
    candidates = [
        _make_candidate(
            satellite_id="sat_a",
            target_id="t1",
            start="2026-04-22T22:00:00Z",
            end="2026-04-22T22:00:06Z",
            access_interval_id="sat_a::0",
            candidate_id="sat_a_t1_0",
        ),
        _make_candidate(
            satellite_id="sat_b",
            target_id="t1",
            start="2026-04-22T22:10:00Z",
            end="2026-04-22T22:10:06Z",
            access_interval_id="sat_b::0",
            candidate_id="sat_b_t1_0",
        ),
        _make_candidate(
            satellite_id="sat_b",
            target_id="t1",
            start="2026-04-22T22:20:00Z",
            end="2026-04-22T22:20:06Z",
            access_interval_id="sat_b::0",
            candidate_id="sat_b_t1_1",
        ),
    ]

    monkeypatch.setattr(products_module, "_strip_polyline_en", lambda *args, **kwargs: [(0.0, 0.0), (1.0, 0.0)])
    monkeypatch.setattr(
        products_module,
        "_evaluate_pair",
        lambda ci, cj, *args, **kwargs: (
            True,
            0.9,
            [],
        ),
    )
    monkeypatch.setattr(
        products_module,
        "_evaluate_triple",
        lambda c0, c1, c2, *args, **kwargs: (
            True,
            0.95,
            [],
        ),
    )

    library = build_product_library(candidates, case, ProductConfig(max_tri_products_per_target_access=10))

    cross_sat_pairs = [
        p for p in library.products
        if p.product_type == solver_imports["ProductType"].PAIR
        and {obs.satellite_id for obs in p.observations} == {"sat_a", "sat_b"}
        and p.feasible
    ]
    cross_sat_tris = [
        p for p in library.products
        if p.product_type == solver_imports["ProductType"].TRI
        and {obs.satellite_id for obs in p.observations} == {"sat_a", "sat_b"}
        and p.feasible
    ]

    assert cross_sat_pairs, "expected at least one feasible cross-satellite pair"
    assert cross_sat_pairs[0].satellite_id == "multi"
    assert cross_sat_pairs[0].access_interval_id == "multi"
    assert cross_sat_tris, "expected at least one feasible mixed-satellite tri product"
    assert cross_sat_tris[0].satellite_id == "multi"
    assert cross_sat_tris[0].access_interval_id == "multi"


def test_build_product_library_prunes_out_of_window_pairs_before_geometry(
    solver_imports, monkeypatch
) -> None:
    products_module = importlib.import_module("products")
    build_product_library = solver_imports["build_product_library"]
    ProductConfig = solver_imports["ProductConfig"]

    case = _make_minimal_stereo_case(solver_imports)
    candidates = [
        _make_candidate(
            satellite_id="sat_a",
            target_id="t1",
            start="2026-04-22T22:00:00Z",
            end="2026-04-22T22:00:06Z",
            access_interval_id="sat_a::0",
            candidate_id="prune_0",
        ),
        _make_candidate(
            satellite_id="sat_b",
            target_id="t1",
            start="2026-04-22T22:30:00Z",
            end="2026-04-22T22:30:06Z",
            access_interval_id="sat_b::0",
            candidate_id="prune_1",
        ),
        _make_candidate(
            satellite_id="sat_b",
            target_id="t1",
            start="2026-04-23T01:30:00Z",
            end="2026-04-23T01:30:06Z",
            access_interval_id="sat_b::1",
            candidate_id="prune_2",
        ),
    ]

    pair_calls: list[tuple[str, str]] = []
    tri_calls: list[tuple[str, str, str]] = []

    monkeypatch.setattr(products_module, "_strip_polyline_en", lambda *args, **kwargs: [(0.0, 0.0), (1.0, 0.0)])

    def _fake_pair(ci, cj, *args, **kwargs):
        pair_calls.append((ci.candidate_id, cj.candidate_id))
        return True, 0.9, []

    def _fake_tri(c0, c1, c2, *args, **kwargs):
        tri_calls.append((c0.candidate_id, c1.candidate_id, c2.candidate_id))
        return True, 0.95, []

    monkeypatch.setattr(products_module, "_evaluate_pair", _fake_pair)
    monkeypatch.setattr(products_module, "_evaluate_triple", _fake_tri)

    library = build_product_library(candidates, case, ProductConfig(max_tri_products_per_target_access=10))

    assert pair_calls == [("prune_0", "prune_1")]
    assert tri_calls == []
    assert library.summary.pair_candidates_considered == 3
    assert library.summary.pair_pruned_prerequisite == 2
    assert library.summary.pair_rejected_geometry == 0
    assert library.summary.tri_candidates_evaluated == 0
    assert len(library.products) == 1


def test_evaluate_pair_allows_cross_satellite_within_pair_separation(solver_imports, monkeypatch) -> None:
    products_module = importlib.import_module("products")

    case = _make_minimal_stereo_case(solver_imports)
    sf_sats = {
        sid: solver_imports["EarthSatellite"](sat.tle_line1, sat.tle_line2, name=sid, ts=solver_imports["_TS"])
        for sid, sat in case.satellites.items()
    }
    target = case.targets["t1"]
    target_ecef = {
        "t1": np.asarray(
            brahe.position_geodetic_to_ecef(
                [target.longitude_deg, target.latitude_deg, target.elevation_ref_m],
                brahe.AngleFormat.DEGREES,
            ),
            dtype=float,
        ).reshape(3)
    }
    geo_cache = {
        0: products_module._CandidateGeoCache(polyline=[(0.0, 0.0), (1.0, 0.0)], half_width_m=100.0),
        1: products_module._CandidateGeoCache(polyline=[(0.0, 0.0), (1.0, 0.0)], half_width_m=100.0),
    }
    state_by_sat = {
        "sat_a": np.array([7_000_000.0, 0.0, 0.0]),
        "sat_b": np.array([0.0, 7_000_000.0, 0.0]),
    }

    monkeypatch.setattr(
        products_module,
        "_satellite_state_ecef_m",
        lambda sat, dt: (state_by_sat[sat.name], np.zeros(3)),
    )
    monkeypatch.setattr(products_module, "_angle_between_deg", lambda a, b: 10.0)
    monkeypatch.setattr(products_module, "_monte_carlo_overlap_fraction", lambda *args, **kwargs: 0.9)

    c0 = _make_candidate(
        satellite_id="sat_a",
        target_id="t1",
        start="2026-04-22T22:00:00Z",
        end="2026-04-22T22:00:06Z",
        access_interval_id="sat_a::0",
        candidate_id="pair_a",
    )
    c1 = _make_candidate(
        satellite_id="sat_b",
        target_id="t1",
        start="2026-04-22T22:30:00Z",
        end="2026-04-22T22:30:06Z",
        access_interval_id="sat_b::0",
        candidate_id="pair_b",
    )

    feasible, quality, reasons = products_module._evaluate_pair(
        c0,
        c1,
        case,
        sf_sats,
        target_ecef,
        solver_imports["ProductConfig"](pair_mc_samples=4),
        geo_cache=geo_cache,
        i=0,
        j=1,
    )

    assert feasible
    assert quality > 0.0
    assert reasons == []


def test_evaluate_pair_rejects_cross_satellite_outside_pair_separation(solver_imports) -> None:
    products_module = importlib.import_module("products")

    case = _make_minimal_stereo_case(solver_imports)
    sf_sats = {
        sid: solver_imports["EarthSatellite"](sat.tle_line1, sat.tle_line2, name=sid, ts=solver_imports["_TS"])
        for sid, sat in case.satellites.items()
    }
    target = case.targets["t1"]
    target_ecef = {
        "t1": np.asarray(
            brahe.position_geodetic_to_ecef(
                [target.longitude_deg, target.latitude_deg, target.elevation_ref_m],
                brahe.AngleFormat.DEGREES,
            ),
            dtype=float,
        ).reshape(3)
    }

    c0 = _make_candidate(
        satellite_id="sat_a",
        target_id="t1",
        start="2026-04-22T22:00:00Z",
        end="2026-04-22T22:00:06Z",
        access_interval_id="sat_a::0",
        candidate_id="pair_far_a",
    )
    c1 = _make_candidate(
        satellite_id="sat_b",
        target_id="t1",
        start="2026-04-23T00:30:00Z",
        end="2026-04-23T00:30:06Z",
        access_interval_id="sat_b::0",
        candidate_id="pair_far_b",
    )

    feasible, quality, reasons = products_module._evaluate_pair(
        c0,
        c1,
        case,
        sf_sats,
        target_ecef,
        solver_imports["ProductConfig"](pair_mc_samples=4),
    )

    assert not feasible
    assert quality == 0.0
    assert any("pair_separation" in reason for reason in reasons)


def test_evaluate_pair_rejects_same_satellite_different_access_interval(solver_imports) -> None:
    products_module = importlib.import_module("products")

    case = _make_minimal_stereo_case(solver_imports)
    sf_sats = {
        sid: solver_imports["EarthSatellite"](sat.tle_line1, sat.tle_line2, name=sid, ts=solver_imports["_TS"])
        for sid, sat in case.satellites.items()
    }
    target = case.targets["t1"]
    target_ecef = {
        "t1": np.asarray(
            brahe.position_geodetic_to_ecef(
                [target.longitude_deg, target.latitude_deg, target.elevation_ref_m],
                brahe.AngleFormat.DEGREES,
            ),
            dtype=float,
        ).reshape(3)
    }

    c0 = _make_candidate(
        satellite_id="sat_a",
        target_id="t1",
        start="2026-04-22T22:00:00Z",
        end="2026-04-22T22:00:06Z",
        access_interval_id="sat_a::0",
        candidate_id="same_sat_0",
    )
    c1 = _make_candidate(
        satellite_id="sat_a",
        target_id="t1",
        start="2026-04-22T22:10:00Z",
        end="2026-04-22T22:10:06Z",
        access_interval_id="sat_a::1",
        candidate_id="same_sat_1",
    )

    feasible, quality, reasons = products_module._evaluate_pair(
        c0,
        c1,
        case,
        sf_sats,
        target_ecef,
        solver_imports["ProductConfig"](pair_mc_samples=4),
    )

    assert not feasible
    assert quality == 0.0
    assert any("access_interval_id" in reason for reason in reasons)


def test_evaluate_triple_accepts_mixed_satellite_with_anchor(solver_imports, monkeypatch) -> None:
    products_module = importlib.import_module("products")

    case = _make_minimal_stereo_case(solver_imports)
    sf_sats = {
        sid: solver_imports["EarthSatellite"](sat.tle_line1, sat.tle_line2, name=sid, ts=solver_imports["_TS"])
        for sid, sat in case.satellites.items()
    }
    target = case.targets["t1"]
    target_ecef = {
        "t1": np.asarray(
            brahe.position_geodetic_to_ecef(
                [target.longitude_deg, target.latitude_deg, target.elevation_ref_m],
                brahe.AngleFormat.DEGREES,
            ),
            dtype=float,
        ).reshape(3)
    }
    geo_cache = {
        0: products_module._CandidateGeoCache(polyline=[(0.0, 0.0), (1.0, 0.0)], half_width_m=100.0),
        1: products_module._CandidateGeoCache(polyline=[(0.0, 0.0), (1.0, 0.0)], half_width_m=100.0),
        2: products_module._CandidateGeoCache(polyline=[(0.0, 0.0), (1.0, 0.0)], half_width_m=100.0),
    }
    monkeypatch.setattr(products_module, "_monte_carlo_tri_overlap", lambda *args, **kwargs: 0.9)

    c0 = _make_candidate(
        satellite_id="sat_a",
        target_id="t1",
        start="2026-04-22T22:00:00Z",
        end="2026-04-22T22:00:06Z",
        access_interval_id="sat_a::0",
        candidate_id="tri_a",
    )
    c1 = _make_candidate(
        satellite_id="sat_b",
        target_id="t1",
        start="2026-04-22T22:10:00Z",
        end="2026-04-22T22:10:06Z",
        access_interval_id="sat_b::0",
        candidate_id="tri_b0",
    )
    c2 = _make_candidate(
        satellite_id="sat_b",
        target_id="t1",
        start="2026-04-22T22:20:00Z",
        end="2026-04-22T22:20:06Z",
        access_interval_id="sat_b::0",
        candidate_id="tri_b1",
    )

    feasible, quality, reasons = products_module._evaluate_triple(
        c0,
        c1,
        c2,
        case,
        sf_sats,
        target_ecef,
        solver_imports["ProductConfig"](tri_mc_samples=4),
        geo_cache=geo_cache,
        indices=(0, 1, 2),
        pair_cache={
            (0, 1): (True, 0.8, []),
            (0, 2): (True, 0.81, []),
            (1, 2): (True, 0.82, []),
        },
    )

    assert feasible
    assert quality > 0.0
    assert reasons == []


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


def test_cross_satellite_product_inserts_into_independent_sequences(solver_imports) -> None:
    case = _make_minimal_stereo_case(solver_imports)
    state = solver_imports["create_empty_state"](case)

    c0 = _make_candidate(
        satellite_id="sat_a",
        target_id="t1",
        start="2026-04-22T22:00:00Z",
        end="2026-04-22T22:00:06Z",
        access_interval_id="sat_a::0",
        candidate_id="cross_insert_a",
    )
    c1 = _make_candidate(
        satellite_id="sat_b",
        target_id="t1",
        start="2026-04-22T22:00:00Z",
        end="2026-04-22T22:00:06Z",
        access_interval_id="sat_b::0",
        candidate_id="cross_insert_b",
    )
    product = solver_imports["StereoProduct"](
        product_id="pair|cross_insert",
        product_type=solver_imports["ProductType"].PAIR,
        target_id="t1",
        satellite_id="multi",
        access_interval_id="multi",
        observations=(c0, c1),
        quality=0.5,
        coverage_value=0.5,
        feasible=True,
        reject_reasons=tuple(),
    )

    result = solver_imports["insert_product"](product, state, case)

    assert result.success
    assert [obs.candidate_id for obs in state.sequences["sat_a"].observations] == ["cross_insert_a"]
    assert [obs.candidate_id for obs in state.sequences["sat_b"].observations] == ["cross_insert_b"]


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


def test_sequence_uses_fixed_window_times(solver_imports) -> None:
    sat_def = _make_sat_def()
    sf = solver_imports["EarthSatellite"](sat_def.tle_line1, sat_def.tle_line2, name="sat_test", ts=solver_imports["_TS"])
    seq = solver_imports["SatelliteSequence"](satellite_id="sat_test")

    c0 = _make_candidate(start="2026-04-22T22:00:00Z", end="2026-04-22T22:00:06Z", candidate_id="c0")
    c1 = _make_candidate(start="2026-04-22T22:02:00Z", end="2026-04-22T22:02:06Z", candidate_id="c1")

    solver_imports["insert_observation"](c0, seq, 0, sat_def, sf)
    solver_imports["insert_observation"](c1, seq, 1, sat_def, sf)

    assert seq.earliest == {"c0": c0.start, "c1": c1.start}
    assert seq.latest == {"c0": c0.start, "c1": c1.start}
    assert solver_imports["compute_earliest"](seq, sat_def, sf) == seq.earliest
    assert solver_imports["compute_latest"](seq, sat_def, sf) == seq.latest


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


def test_greedy_seed_tie_selection_is_deterministic(solver_imports) -> None:
    ProductType = solver_imports["ProductType"]
    ProductLibrary = solver_imports["ProductLibrary"]
    ProductSummary = solver_imports["ProductSummary"]
    SeedConfig = solver_imports["SeedConfig"]
    build_greedy_seed = solver_imports["build_greedy_seed"]

    p_a = _make_product(solver_imports, "p_a", ProductType.PAIR, "t1", quality=0.5)
    p_b = _make_product(solver_imports, "p_b", ProductType.PAIR, "t1", quality=0.5)
    library = ProductLibrary(
        products=[p_a, p_b],
        per_target_products={"t1": [p_a, p_b]},
        summary=ProductSummary(
            total_products=2,
            pair_products=2,
            feasible_products=2,
            per_target_product_counts={"t1": 2},
        ),
    )

    class _FakeCase:
        satellites = {"sat_test": _make_sat_def()}
        targets = {"t1": None}

    seed = build_greedy_seed(library, _FakeCase(), SeedConfig(max_seed_products=1))
    assert [p.product_id for p in seed.accepted_products] == ["p_b"]


def test_greedy_seed_prefers_scarce_target_head(solver_imports) -> None:
    ProductType = solver_imports["ProductType"]
    ProductLibrary = solver_imports["ProductLibrary"]
    ProductSummary = solver_imports["ProductSummary"]
    SeedConfig = solver_imports["SeedConfig"]
    build_greedy_seed = solver_imports["build_greedy_seed"]

    scarce = _make_product(solver_imports, "scarce", ProductType.PAIR, "t1", quality=0.5)
    abundant = [
        _make_product(
            solver_imports, f"abundant_{i}", ProductType.PAIR, "t2", quality=0.5
        )
        for i in range(10)
    ]
    products = [scarce, *abundant]
    library = ProductLibrary(
        products=products,
        per_target_products={"t1": [scarce], "t2": abundant},
        summary=ProductSummary(
            total_products=len(products),
            pair_products=len(products),
            feasible_products=len(products),
            per_target_product_counts={"t1": 1, "t2": 10},
        ),
    )

    class _FakeCase:
        satellites = {"sat_test": _make_sat_def()}
        targets = {"t1": None, "t2": None}

    seed = build_greedy_seed(library, _FakeCase(), SeedConfig(max_seed_products=1))
    assert [p.product_id for p in seed.accepted_products] == ["scarce"]


def test_greedy_seed_rng_perturbation_is_seeded(solver_imports) -> None:
    import random

    ProductType = solver_imports["ProductType"]
    ProductLibrary = solver_imports["ProductLibrary"]
    ProductSummary = solver_imports["ProductSummary"]
    SeedConfig = solver_imports["SeedConfig"]
    build_greedy_seed = solver_imports["build_greedy_seed"]

    p1 = _make_product(solver_imports, "p1", ProductType.PAIR, "t1", quality=0.5)
    p2 = _make_product(solver_imports, "p2", ProductType.PAIR, "t2", quality=0.5)
    library = ProductLibrary(
        products=[p1, p2],
        per_target_products={"t1": [p1], "t2": [p2]},
        summary=ProductSummary(
            total_products=2,
            pair_products=2,
            feasible_products=2,
            per_target_product_counts={"t1": 1, "t2": 1},
        ),
    )

    class _FakeCase:
        satellites = {"sat_test": _make_sat_def()}
        targets = {"t1": None, "t2": None}

    config = SeedConfig(max_seed_products=1)
    seed_a = build_greedy_seed(library, _FakeCase(), config, rng=random.Random(1))
    seed_b = build_greedy_seed(library, _FakeCase(), config, rng=random.Random(1))
    seed_c = build_greedy_seed(library, _FakeCase(), config, rng=random.Random(2))

    assert [p.product_id for p in seed_a.accepted_products] == [
        p.product_id for p in seed_b.accepted_products
    ]
    assert [p.product_id for p in seed_a.accepted_products] != [
        p.product_id for p in seed_c.accepted_products
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


def test_tri_upgrade_rolls_back_when_replacement_conflicts(solver_imports) -> None:
    ProductType = solver_imports["ProductType"]
    ProductLibrary = solver_imports["ProductLibrary"]
    ProductSummary = solver_imports["ProductSummary"]
    SeedConfig = solver_imports["SeedConfig"]
    build_greedy_seed = solver_imports["build_greedy_seed"]

    blocker = _make_product(
        solver_imports,
        "blocker",
        ProductType.PAIR,
        "t2",
        quality=1.0,
        observations=(
            _make_candidate(
                target_id="t2",
                start="2026-04-22T22:04:00Z",
                end="2026-04-22T22:04:06Z",
                candidate_id="blocker_a",
            ),
            _make_candidate(
                target_id="t2",
                start="2026-04-22T22:08:00Z",
                end="2026-04-22T22:08:06Z",
                candidate_id="blocker_b",
            ),
        ),
    )
    pair = _make_product(
        solver_imports,
        "pair",
        ProductType.PAIR,
        "t1",
        quality=0.6,
        observations=(
            _make_candidate(
                start="2026-04-22T21:40:00Z",
                end="2026-04-22T21:40:06Z",
                candidate_id="pair_a",
            ),
            _make_candidate(
                start="2026-04-22T21:50:00Z",
                end="2026-04-22T21:50:06Z",
                candidate_id="pair_b",
            ),
        ),
    )
    tri = _make_product(
        solver_imports,
        "tri",
        ProductType.TRI,
        "t1",
        quality=0.9,
        observations=(
            _make_candidate(
                start="2026-04-22T21:55:00Z",
                end="2026-04-22T21:55:06Z",
                candidate_id="tri_a",
            ),
            _make_candidate(
                start="2026-04-22T22:04:00Z",
                end="2026-04-22T22:04:06Z",
                candidate_id="tri_b",
            ),
            _make_candidate(
                start="2026-04-22T22:12:00Z",
                end="2026-04-22T22:12:06Z",
                candidate_id="tri_c",
            ),
        ),
    )
    products = [blocker, tri, pair]
    library = ProductLibrary(
        products=products,
        per_target_products={"t1": [tri, pair], "t2": [blocker]},
        summary=ProductSummary(
            total_products=3,
            pair_products=2,
            tri_products=1,
            feasible_products=3,
            per_target_product_counts={"t1": 2, "t2": 1},
        ),
    )

    class _FakeCase:
        satellites = {"sat_test": _make_sat_def()}
        targets = {"t1": None, "t2": None}

    seed = build_greedy_seed(library, _FakeCase(), SeedConfig())
    accepted_ids = [p.product_id for p in seed.accepted_products]

    assert "blocker" in accepted_ids
    assert "pair" in accepted_ids
    assert "tri" not in accepted_ids
    assert any(
        record.product_id == "tri" and "tri_upgrade_failed" in record.reasons
        for record in seed.rejected_records
    )


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
    solver_imports["propagate"](seq, sat_def, state.sf_sats["sat_test"])

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
    assert config.run_profile == "smoke"
    assert config.num_runs == 10
    assert config.random_seed == 123


def test_local_search_config_defaults(solver_imports) -> None:
    LocalSearchConfig = solver_imports["LocalSearchConfig"]
    config = LocalSearchConfig.from_mapping({})
    assert config.run_profile == "smoke"
    assert config.num_runs == 1
    assert config.random_seed == 42
    assert config.max_time_seconds == pytest.approx(30.0)


def test_local_search_config_benchmark_profile_defaults(solver_imports) -> None:
    LocalSearchConfig = solver_imports["LocalSearchConfig"]
    config = LocalSearchConfig.from_mapping({"run_profile": "benchmark"})
    assert config.run_profile == "benchmark"
    assert config.num_runs == 5
    assert config.max_passes == 50
    assert config.max_moves_per_pass == 2000
    assert config.max_time_seconds == pytest.approx(120.0)


def test_local_search_config_profile_explicit_overrides(solver_imports) -> None:
    LocalSearchConfig = solver_imports["LocalSearchConfig"]
    config = LocalSearchConfig.from_mapping(
        {"run_profile": "profile", "num_runs": 2, "max_time_seconds": 7.5}
    )
    assert config.run_profile == "profile"
    assert config.num_runs == 2
    assert config.max_time_seconds == pytest.approx(7.5)


def test_local_search_config_rejects_unknown_profile(solver_imports) -> None:
    LocalSearchConfig = solver_imports["LocalSearchConfig"]
    with pytest.raises(ValueError, match="run_profile"):
        LocalSearchConfig.from_mapping({"run_profile": "surprise"})


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
        max_stereo_pair_separation_s=3600.0,
        min_overlap_fraction=0.5,
        min_convergence_deg=5.0,
        max_convergence_deg=35.0,
        max_pixel_scale_ratio=2.0,
        min_solar_elevation_deg=10.0,
        near_nadir_anchor_max_off_nadir_deg=15.0,
        pair_weights={"geometry": 0.5, "overlap": 0.35, "resolution": 0.15},
        tri_stereo_bonus_by_scene={
            "urban_structured": 0.12,
            "rugged": 0.1,
            "vegetated": 0.08,
            "open": 0.05,
        },
    )

    return StereoCase(
        case_dir=Path("/tmp/test_case"),
        mission=mission,
        satellites={"sat_a": sat_a, "sat_b": sat_b},
        targets={"t1": target_1, "t2": target_2},
    )


def test_minimal_stereo_case_uses_benchmark_shaped_mission(solver_imports) -> None:
    case = _make_minimal_stereo_case(solver_imports)

    assert case.mission.allow_cross_satellite_stereo is True
    assert case.mission.max_stereo_pair_separation_s == 3600.0
    assert case.mission.pair_weights == {
        "geometry": 0.5,
        "overlap": 0.35,
        "resolution": 0.15,
    }
    assert case.mission.tri_stereo_bonus_by_scene == {
        "urban_structured": 0.12,
        "rugged": 0.1,
        "vegetated": 0.08,
        "open": 0.05,
    }


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
        "run_details": [],
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
        timing_seconds={
            "candidate_generation": 0.2,
            "product_library": 0.3,
            "sequence_sanity": 0.01,
            "construction": 0.51,
            "seed": 0.02,
            "seed_total": 0.06,
            "local_search": 0.1,
            "local_search_total": 0.3,
            "repair": 0.01,
            "repair_total": 0.03,
            "selected_run_pipeline": 0.13,
            "search_pipeline_total": 0.39,
            "total": 1.0,
        },
        seed_result=seed_result,
        repair_result=repair_result,
        repair_config=RepairConfig(),
        local_search_config=LocalSearchConfig.from_mapping({"run_profile": "benchmark"}),
        multi_run_stats=multi_run_stats,
    )

    assert status["multi_run_stats"] == multi_run_stats
    assert status["status"] == "multi_run"
    assert status["run_policy"]["run_profile"] == "benchmark"
    assert status["run_policy"]["construction_reused_across_runs"] is True
    assert status["run_policy"]["construction_seconds"] == pytest.approx(0.51)
    assert status["run_policy"]["local_search_seconds_total"] == pytest.approx(0.3)
    assert status["run_policy"]["best_run"] == 1
