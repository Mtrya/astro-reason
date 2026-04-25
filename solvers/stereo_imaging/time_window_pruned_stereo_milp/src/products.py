"""Benchmark-native stereo pair and tri-stereo product enumeration and scoring."""

from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Any

import numpy as np

from geometry import (
    angle_between_deg,
    boresight_ground_intercept_ecef_m,
    make_earth_satellite,
    overlap_fraction_grid,
    pixel_scale_m,
    satellite_state_ecef_m,
    strip_polyline_en,
    target_ecef_m,
    tri_overlap_fraction_grid,
)
from models import (
    CandidateObservation,
    Mission,
    ProductSummary,
    Satellite,
    StereoPair,
    Target,
    TriStereoSet,
)

_SCENE_GEOM_BANDS_DEG: dict[str, tuple[float, float]] = {
    "urban_structured": (8.0, 18.0),
    "vegetated": (8.0, 14.0),
    "rugged": (10.0, 20.0),
    "open": (15.0, 25.0),
}

_NUMERICAL_EPS = 1e-9


@dataclass
class _CandidateGeometry:
    sat_pos_m: np.ndarray
    boresight_ground_m: np.ndarray
    slant_range_m: float
    pixel_scale_m: float
    strip_polyline_en: list[tuple[float, float]] | None = None
    strip_half_width_m: float | None = None


def _candidate_midpoint(cand: CandidateObservation):
    return cand.start + (cand.end - cand.start) / 2


def _product_time_separation_s(candidates: tuple[CandidateObservation, ...] | list[CandidateObservation]) -> float:
    if len(candidates) < 2:
        return 0.0
    midpoints = [_candidate_midpoint(cand) for cand in candidates]
    return (max(midpoints) - min(midpoints)).total_seconds()


def _stereo_pair_mode(
    mission: Mission,
    cand_i: CandidateObservation,
    cand_j: CandidateObservation,
) -> str | None:
    if cand_i.target_id != cand_j.target_id:
        return None
    if cand_i.access_interval_id == "none" or cand_j.access_interval_id == "none":
        return None
    separation_s = _product_time_separation_s((cand_i, cand_j))
    if separation_s - 1e-6 > mission.max_stereo_pair_separation_s:
        return None
    if cand_i.sat_id == cand_j.sat_id:
        if cand_i.access_interval_id != cand_j.access_interval_id:
            return None
        return "same_satellite_same_pass"
    if not mission.allow_cross_satellite_stereo:
        return None
    return "cross_satellite"


def _pair_geom_quality(gamma_deg: float, scene: str) -> float:
    lo, hi = _SCENE_GEOM_BANDS_DEG.get(scene, (8.0, 18.0))
    if lo <= gamma_deg <= hi:
        return 1.0
    dist = min(abs(gamma_deg - lo), abs(gamma_deg - hi))
    return max(0.0, 1.0 - dist / 10.0)


def _tri_bonus_R(pair_ok: list[bool], has_anchor: bool) -> float:
    r = 0.0
    if sum(pair_ok) >= 2:
        r += 0.6
    if has_anchor:
        r += 0.4
    return min(1.0, r)


def _precompute_candidate_geometry(
    cand: CandidateObservation,
    sf: Any,
    sat: Satellite,
    target: Target,
) -> _CandidateGeometry | None:
    te = target_ecef_m(target)
    mid = cand.start + (cand.end - cand.start) / 2
    sp, sv = satellite_state_ecef_m(sf, mid)
    gp = boresight_ground_intercept_ecef_m(sp, sv, cand.off_nadir_along_deg, cand.off_nadir_across_deg)
    if gp is None:
        gp = te
    slant = float(np.linalg.norm(gp - sp))
    ps = pixel_scale_m(sat, slant, cand.combined_off_nadir_deg)
    return _CandidateGeometry(
        sat_pos_m=sp,
        boresight_ground_m=gp,
        slant_range_m=slant,
        pixel_scale_m=ps,
    )


def _ensure_strip_geometry(
    cand: CandidateObservation,
    geo: _CandidateGeometry,
    sf: Any,
    sat: Satellite,
    target_ecef: np.ndarray,
    strip_step_s: float,
    profile: dict[str, Any] | None = None,
) -> _CandidateGeometry:
    if geo.strip_polyline_en is not None and geo.strip_half_width_m is not None:
        return geo
    start = time.perf_counter()
    geo.strip_polyline_en = strip_polyline_en(
        sf,
        target_ecef,
        cand.start,
        cand.end,
        strip_step_s,
        cand.off_nadir_along_deg,
        cand.off_nadir_across_deg,
    )
    geo.strip_half_width_m = geo.slant_range_m * np.tan(np.radians(sat.half_cross_track_fov_deg))
    if profile is not None:
        profile["strip_geometry_s"] = profile.get("strip_geometry_s", 0.0) + (time.perf_counter() - start)
    return geo


def evaluate_pair(
    cand_i: CandidateObservation,
    cand_j: CandidateObservation,
    geo_i: _CandidateGeometry,
    geo_j: _CandidateGeometry,
    target: Target,
    mission: Mission,
    config: dict[str, Any],
    pair_mode: str,
    *,
    sf_i: Any,
    sf_j: Any,
    sat_i: Satellite,
    sat_j: Satellite,
    target_ecef: np.ndarray,
    strip_step_s: float,
    profile: dict[str, Any] | None = None,
) -> StereoPair:
    ui = (geo_i.sat_pos_m - target_ecef) / np.linalg.norm(geo_i.sat_pos_m - target_ecef)
    uj = (geo_j.sat_pos_m - target_ecef) / np.linalg.norm(geo_j.sat_pos_m - target_ecef)
    gamma = angle_between_deg(ui, uj)

    ps_ratio = max(geo_i.pixel_scale_m, geo_j.pixel_scale_m) / min(geo_i.pixel_scale_m, geo_j.pixel_scale_m)

    vt = mission.validity_thresholds
    overlap = 0.0
    geometry_ok = (
        vt.min_convergence_deg - 1e-6 <= gamma <= vt.max_convergence_deg + 1e-6
        and ps_ratio <= vt.max_pixel_scale_ratio + 1e-6
    )
    if geometry_ok:
        geo_i = _ensure_strip_geometry(cand_i, geo_i, sf_i, sat_i, target_ecef, strip_step_s, profile=profile)
        geo_j = _ensure_strip_geometry(cand_j, geo_j, sf_j, sat_j, target_ecef, strip_step_s, profile=profile)
        if profile is not None:
            profile["pair_overlap_evals"] = profile.get("pair_overlap_evals", 0) + 1
        n_angles = int(config.get("overlap_grid_angles", 8))
        n_radii = int(config.get("overlap_grid_radii", 3))
        overlap = overlap_fraction_grid(
            target.aoi_radius_m,
            geo_i.strip_polyline_en or [],
            float(geo_i.strip_half_width_m or 0.0),
            geo_j.strip_polyline_en or [],
            float(geo_j.strip_half_width_m or 0.0),
            n_angles,
            n_radii,
        )

    valid = geometry_ok and overlap + 1e-6 >= vt.min_overlap_fraction

    q_geom = _pair_geom_quality(gamma, target.scene_type)
    q_overlap = min(1.0, overlap / 0.95)
    q_res = max(0.0, 1.0 - (ps_ratio - 1.0) / 0.5)
    w = mission.quality_model.pair_weights
    q_pair = w["geometry"] * q_geom + w["overlap"] * q_overlap + w["resolution"] * q_res
    time_separation_s = _product_time_separation_s((cand_i, cand_j))

    return StereoPair(
        target_id=target.id,
        candidate_i=cand_i,
        candidate_j=cand_j,
        convergence_deg=gamma,
        overlap_fraction=overlap,
        pixel_scale_ratio=ps_ratio,
        valid=valid,
        q_geom=q_geom,
        q_overlap=q_overlap,
        q_res=q_res,
        q_pair=q_pair,
        time_separation_s=time_separation_s,
        satellite_ids=(cand_i.sat_id, cand_j.sat_id),
        access_interval_ids=(cand_i.access_interval_id, cand_j.access_interval_id),
        pair_mode=pair_mode,
    )


def evaluate_tri(
    cands: tuple[CandidateObservation, CandidateObservation, CandidateObservation],
    geos: tuple[_CandidateGeometry, _CandidateGeometry, _CandidateGeometry],
    pair_results: dict[tuple[int, int], StereoPair],
    indices: tuple[int, int, int],
    target: Target,
    mission: Mission,
    config: dict[str, Any],
    *,
    sfs: tuple[Any, Any, Any],
    sats: tuple[Satellite, Satellite, Satellite],
    target_ecef: np.ndarray,
    strip_step_s: float,
    profile: dict[str, Any] | None = None,
) -> TriStereoSet:
    i, j, k = indices
    pair_keys = [(i, j), (i, k), (j, k)]
    pair_flags = []
    pair_qs = []
    for a, b in pair_keys:
        key = (a, b) if a < b else (b, a)
        pr = pair_results.get(key)
        if pr is not None and pr.valid:
            pair_flags.append(True)
            pair_qs.append(pr.q_pair)
        else:
            pair_flags.append(False)
            pair_qs.append(0.0)

    vt = mission.validity_thresholds
    has_anchor = any(
        cands[m].combined_off_nadir_deg <= vt.near_nadir_anchor_max_off_nadir_deg + 1e-6
        for m in range(3)
    )

    common_overlap = 0.0
    if sum(pair_flags) >= 2 and has_anchor:
        for idx, geo in enumerate(geos):
            _ensure_strip_geometry(
                cands[idx],
                geo,
                sfs[idx],
                sats[idx],
                target_ecef,
                strip_step_s,
                profile=profile,
            )
        if profile is not None:
            profile["tri_overlap_evals"] = profile.get("tri_overlap_evals", 0) + 1
        n_angles = int(config.get("overlap_grid_angles", 8))
        n_radii = int(config.get("overlap_grid_radii", 3))
        common_overlap = tri_overlap_fraction_grid(
            target.aoi_radius_m,
            [geos[idx].strip_polyline_en or [] for idx in range(3)],
            [float(geos[idx].strip_half_width_m or 0.0) for idx in range(3)],
            n_angles,
            n_radii,
        )

    valid = common_overlap + 1e-6 >= vt.min_overlap_fraction and sum(pair_flags) >= 2 and has_anchor

    beta = mission.quality_model.tri_stereo_bonus_by_scene.get(target.scene_type, 0.0)
    r = _tri_bonus_R(pair_flags, has_anchor)
    valid_qs = [q for ok, q in zip(pair_flags, pair_qs) if ok]
    q_tri = min(1.0, (max(valid_qs) if valid_qs else 0.0) + beta * r)

    return TriStereoSet(
        target_id=target.id,
        candidates=cands,
        common_overlap_fraction=common_overlap,
        pair_valid_flags=pair_flags,
        pair_qs=pair_qs,
        has_anchor=has_anchor,
        valid=valid,
        q_tri=q_tri,
        satellite_ids=tuple(c.sat_id for c in cands),
        access_interval_ids=tuple(c.access_interval_id for c in cands),
    )


def enumerate_products(
    candidates: list[CandidateObservation],
    satellites: dict[str, Satellite],
    targets: dict[str, Target],
    mission: Mission,
    config: dict[str, Any],
) -> tuple[list[StereoPair], list[TriStereoSet], ProductSummary]:
    total_start = time.perf_counter()
    strip_step_s = float(config.get("strip_sample_step_s", 8.0))

    groups: dict[str, list[CandidateObservation]] = {}
    for cand in candidates:
        groups.setdefault(cand.target_id, []).append(cand)

    pairs: list[StereoPair] = []
    tris: list[TriStereoSet] = []
    summary = ProductSummary()
    summary.approximation_flags = {
        "overlap_method": "polar_grid_area_uniform",
        "overlap_grid_angles": int(config.get("overlap_grid_angles", 8)),
        "overlap_grid_radii": int(config.get("overlap_grid_radii", 3)),
        "strip_sample_step_s": strip_step_s,
        "pixel_scale_secant_correction": True,
        "pair_policy": "benchmark_same_pass_or_cross_satellite_with_midpoint_bound",
        "note": "Overlap is grid-approximated; pixel scale includes off-nadir secant correction.",
    }
    summary.profiling = {
        "total_s": 0.0,
        "midpoint_geometry_s": 0.0,
        "strip_geometry_s": 0.0,
        "pair_policy_checks": 0,
        "pair_overlap_evals": 0,
        "tri_overlap_evals": 0,
        "pairs_emitted": 0,
        "tris_emitted": 0,
    }
    sat_sfs = {sid: make_earth_satellite(sat) for sid, sat in satellites.items()}

    for target_id, group in groups.items():
        if len(group) < 2:
            continue
        target = targets[target_id]
        target_ecef = target_ecef_m(target)
        group_sorted = sorted(
            group,
            key=lambda c: (
                c.start,
                c.end,
                c.sat_id,
                c.access_interval_id,
                c.off_nadir_along_deg,
                c.off_nadir_across_deg,
            ),
        )
        target_midpoint_start = time.perf_counter()
        geos = [
            _precompute_candidate_geometry(c, sat_sfs[c.sat_id], satellites[c.sat_id], target)
            if c.sat_id in satellites and c.sat_id in sat_sfs
            else None
            for c in group_sorted
        ]
        summary.profiling["midpoint_geometry_s"] += time.perf_counter() - target_midpoint_start
        # skip any candidate whose geometry failed (None)
        valid_indices = [idx for idx, g in enumerate(geos) if g is not None]
        if len(valid_indices) < 2:
            continue

        pair_results: dict[tuple[int, int], StereoPair] = {}
        midpoints = [_candidate_midpoint(cand) for cand in group_sorted]
        for a_idx in range(len(valid_indices)):
            for b_idx in range(a_idx + 1, len(valid_indices)):
                i = valid_indices[a_idx]
                j = valid_indices[b_idx]
                if (midpoints[j] - midpoints[i]).total_seconds() - 1e-6 > mission.max_stereo_pair_separation_s:
                    break
                summary.profiling["pair_policy_checks"] += 1
                pair_mode = _stereo_pair_mode(mission, group_sorted[i], group_sorted[j])
                if pair_mode is None:
                    continue
                pair = evaluate_pair(
                    group_sorted[i],
                    group_sorted[j],
                    geos[i],
                    geos[j],
                    target,
                    mission,
                    config,
                    pair_mode,
                    sf_i=sat_sfs[group_sorted[i].sat_id],
                    sf_j=sat_sfs[group_sorted[j].sat_id],
                    sat_i=satellites[group_sorted[i].sat_id],
                    sat_j=satellites[group_sorted[j].sat_id],
                    target_ecef=target_ecef,
                    strip_step_s=strip_step_s,
                    profile=summary.profiling,
                )
                pairs.append(pair)
                summary.record_pair(pair)
                pair_results[(i, j)] = pair

        if len(valid_indices) >= 3:
            for a_idx in range(len(valid_indices)):
                for b_idx in range(a_idx + 1, len(valid_indices)):
                    for c_idx in range(b_idx + 1, len(valid_indices)):
                        i = valid_indices[a_idx]
                        j = valid_indices[b_idx]
                        k = valid_indices[c_idx]
                        if (midpoints[k] - midpoints[i]).total_seconds() - 1e-6 > mission.max_stereo_pair_separation_s:
                            break
                        edge_keys = ((i, j), (i, k), (j, k))
                        if any(edge not in pair_results for edge in edge_keys):
                            continue
                        tri = evaluate_tri(
                            (group_sorted[i], group_sorted[j], group_sorted[k]),
                            (geos[i], geos[j], geos[k]),
                            pair_results,
                            (i, j, k),
                            target,
                            mission,
                            config,
                            sfs=(
                                sat_sfs[group_sorted[i].sat_id],
                                sat_sfs[group_sorted[j].sat_id],
                                sat_sfs[group_sorted[k].sat_id],
                            ),
                            sats=(
                                satellites[group_sorted[i].sat_id],
                                satellites[group_sorted[j].sat_id],
                                satellites[group_sorted[k].sat_id],
                            ),
                            target_ecef=target_ecef,
                            strip_step_s=strip_step_s,
                            profile=summary.profiling,
                        )
                        tris.append(tri)
                        summary.record_tri(tri)

    summary.profiling["pairs_emitted"] = len(pairs)
    summary.profiling["tris_emitted"] = len(tris)
    summary.profiling["total_s"] = time.perf_counter() - total_start
    return pairs, tris, summary
