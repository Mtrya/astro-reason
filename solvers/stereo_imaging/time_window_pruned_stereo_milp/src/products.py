"""Benchmark-native stereo pair and tri-stereo product enumeration and scoring."""

from __future__ import annotations

from dataclasses import dataclass
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


@dataclass(frozen=True)
class _CandidateGeometry:
    sat_pos_m: np.ndarray
    boresight_ground_m: np.ndarray
    slant_range_m: float
    pixel_scale_m: float
    strip_polyline_en: list[tuple[float, float]]
    strip_half_width_m: float


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
    sat: Satellite,
    target: Target,
    strip_step_s: float,
) -> _CandidateGeometry | None:
    sf = make_earth_satellite(sat)
    te = target_ecef_m(target)
    mid = cand.start + (cand.end - cand.start) / 2
    sp, sv = satellite_state_ecef_m(sf, mid)
    gp = boresight_ground_intercept_ecef_m(sp, sv, cand.off_nadir_along_deg, cand.off_nadir_across_deg)
    if gp is None:
        gp = te
    slant = float(np.linalg.norm(gp - sp))
    ps = pixel_scale_m(sat, slant, cand.combined_off_nadir_deg)
    poly = strip_polyline_en(sf, te, cand.start, cand.end, strip_step_s, cand.off_nadir_along_deg, cand.off_nadir_across_deg)
    half_w = slant * np.tan(np.radians(sat.half_cross_track_fov_deg))
    return _CandidateGeometry(
        sat_pos_m=sp,
        boresight_ground_m=gp,
        slant_range_m=slant,
        pixel_scale_m=ps,
        strip_polyline_en=poly,
        strip_half_width_m=float(half_w),
    )


def evaluate_pair(
    cand_i: CandidateObservation,
    cand_j: CandidateObservation,
    geo_i: _CandidateGeometry,
    geo_j: _CandidateGeometry,
    sat: Satellite,
    target: Target,
    mission: Mission,
    config: dict[str, Any],
) -> StereoPair:
    te = target_ecef_m(target)
    ui = (geo_i.sat_pos_m - te) / np.linalg.norm(geo_i.sat_pos_m - te)
    uj = (geo_j.sat_pos_m - te) / np.linalg.norm(geo_j.sat_pos_m - te)
    gamma = angle_between_deg(ui, uj)

    ps_ratio = max(geo_i.pixel_scale_m, geo_j.pixel_scale_m) / min(geo_i.pixel_scale_m, geo_j.pixel_scale_m)

    n_angles = int(config.get("overlap_grid_angles", 8))
    n_radii = int(config.get("overlap_grid_radii", 3))
    overlap = overlap_fraction_grid(
        target.aoi_radius_m,
        geo_i.strip_polyline_en,
        geo_i.strip_half_width_m,
        geo_j.strip_polyline_en,
        geo_j.strip_half_width_m,
        n_angles,
        n_radii,
    )

    vt = mission.validity_thresholds
    valid = (
        vt.min_convergence_deg - 1e-6 <= gamma <= vt.max_convergence_deg + 1e-6
        and overlap + 1e-6 >= vt.min_overlap_fraction
        and ps_ratio <= vt.max_pixel_scale_ratio + 1e-6
    )

    q_geom = _pair_geom_quality(gamma, target.scene_type)
    q_overlap = min(1.0, overlap / 0.95)
    q_res = max(0.0, 1.0 - (ps_ratio - 1.0) / 0.5)
    w = mission.quality_model.pair_weights
    q_pair = w["geometry"] * q_geom + w["overlap"] * q_overlap + w["resolution"] * q_res

    return StereoPair(
        sat_id=sat.id,
        target_id=target.id,
        access_interval_id=cand_i.access_interval_id,
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
    )


def evaluate_tri(
    cands: tuple[CandidateObservation, CandidateObservation, CandidateObservation],
    geos: tuple[_CandidateGeometry, _CandidateGeometry, _CandidateGeometry],
    pair_results: dict[tuple[int, int], StereoPair],
    indices: tuple[int, int, int],
    sat: Satellite,
    target: Target,
    mission: Mission,
    config: dict[str, Any],
) -> TriStereoSet:
    n_angles = int(config.get("overlap_grid_angles", 8))
    n_radii = int(config.get("overlap_grid_radii", 3))
    common_overlap = tri_overlap_fraction_grid(
        target.aoi_radius_m,
        [geos[k].strip_polyline_en for k in range(3)],
        [geos[k].strip_half_width_m for k in range(3)],
        n_angles,
        n_radii,
    )

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

    valid = (
        common_overlap + 1e-6 >= vt.min_overlap_fraction
        and sum(pair_flags) >= 2
        and has_anchor
    )

    beta = mission.quality_model.tri_stereo_bonus_by_scene.get(target.scene_type, 0.0)
    r = _tri_bonus_R(pair_flags, has_anchor)
    valid_qs = [q for ok, q in zip(pair_flags, pair_qs) if ok]
    q_tri = min(1.0, (max(valid_qs) if valid_qs else 0.0) + beta * r)

    return TriStereoSet(
        sat_id=sat.id,
        target_id=target.id,
        access_interval_id=cands[0].access_interval_id,
        candidates=cands,
        common_overlap_fraction=common_overlap,
        pair_valid_flags=pair_flags,
        pair_qs=pair_qs,
        has_anchor=has_anchor,
        valid=valid,
        q_tri=q_tri,
    )


def enumerate_products(
    candidates: list[CandidateObservation],
    satellites: dict[str, Satellite],
    targets: dict[str, Target],
    mission: Mission,
    config: dict[str, Any],
) -> tuple[list[StereoPair], list[TriStereoSet], ProductSummary]:
    strip_step_s = float(config.get("strip_sample_step_s", 8.0))

    groups: dict[tuple[str, str, str], list[CandidateObservation]] = {}
    for cand in candidates:
        key = (cand.sat_id, cand.target_id, cand.access_interval_id)
        groups.setdefault(key, []).append(cand)

    pairs: list[StereoPair] = []
    tris: list[TriStereoSet] = []
    summary = ProductSummary()
    summary.approximation_flags = {
        "overlap_method": "polar_grid_area_uniform",
        "overlap_grid_angles": int(config.get("overlap_grid_angles", 8)),
        "overlap_grid_radii": int(config.get("overlap_grid_radii", 3)),
        "strip_sample_step_s": strip_step_s,
        "pixel_scale_secant_correction": True,
        "note": "Overlap is grid-approximated; pixel scale includes off-nadir secant correction.",
    }

    for (sat_id, target_id, interval_id), group in groups.items():
        if len(group) < 2:
            continue
        sat = satellites[sat_id]
        target = targets[target_id]
        group_sorted = sorted(group, key=lambda c: c.start)
        geos = [_precompute_candidate_geometry(c, sat, target, strip_step_s) for c in group_sorted]
        # skip any candidate whose geometry failed (None)
        valid_indices = [idx for idx, g in enumerate(geos) if g is not None]
        if len(valid_indices) < 2:
            continue

        pair_results: dict[tuple[int, int], StereoPair] = {}
        for a_idx in range(len(valid_indices)):
            for b_idx in range(a_idx + 1, len(valid_indices)):
                i = valid_indices[a_idx]
                j = valid_indices[b_idx]
                pair = evaluate_pair(
                    group_sorted[i], group_sorted[j], geos[i], geos[j], sat, target, mission, config
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
                        tri = evaluate_tri(
                            (group_sorted[i], group_sorted[j], group_sorted[k]),
                            (geos[i], geos[j], geos[k]),
                            pair_results,
                            (i, j, k),
                            sat,
                            target,
                            mission,
                            config,
                        )
                        tris.append(tri)
                        summary.record_tri(tri)

    return pairs, tris, summary
