"""Pair and tri-stereo product library for the stereo_imaging CP/local-search solver."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

import brahe
import numpy as np
from skyfield.api import EarthSatellite

from case_io import StereoCase
from candidates import Candidate
from geometry import (
    _TS,
    _angle_between_deg,
    _iso_z,
    _monte_carlo_overlap_fraction,
    _monte_carlo_tri_overlap,
    _pair_geom_quality,
    _satellite_state_ecef_m,
    _stereo_mc_rng,
    _strip_polyline_en,
    _tri_bonus_R,
    _tri_quality_from_valid_pairs,
)


class ProductType(Enum):
    PAIR = "pair"
    TRI = "tri"


@dataclass(frozen=True, slots=True)
class StereoProduct:
    product_id: str
    product_type: ProductType
    target_id: str
    satellite_id: str
    access_interval_id: str
    observations: tuple[Candidate, ...]
    quality: float
    coverage_value: float
    feasible: bool
    reject_reasons: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "product_id": self.product_id,
            "product_type": self.product_type.value,
            "target_id": self.target_id,
            "satellite_id": self.satellite_id,
            "access_interval_id": self.access_interval_id,
            "observations": [obs.as_dict() for obs in self.observations],
            "quality": self.quality,
            "coverage_value": self.coverage_value,
            "feasible": self.feasible,
            "reject_reasons": list(self.reject_reasons),
        }


@dataclass(slots=True)
class ProductSummary:
    total_products: int = 0
    pair_products: int = 0
    tri_products: int = 0
    feasible_products: int = 0
    infeasible_products: int = 0
    pair_candidates_considered: int = 0
    pair_pruned_prerequisite: int = 0
    pair_rejected_geometry: int = 0
    tri_candidates_evaluated: int = 0
    tri_rejected_geometry: int = 0
    bounded_tri_products: int = 0
    per_target_product_counts: dict[str, int] = field(default_factory=dict)
    per_target_feasible_counts: dict[str, int] = field(default_factory=dict)
    zero_product_target_ids: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "total_products": self.total_products,
            "pair_products": self.pair_products,
            "tri_products": self.tri_products,
            "feasible_products": self.feasible_products,
            "infeasible_products": self.infeasible_products,
            "pair_candidates_considered": self.pair_candidates_considered,
            "pair_pruned_prerequisite": self.pair_pruned_prerequisite,
            "pair_rejected_geometry": self.pair_rejected_geometry,
            "tri_candidates_evaluated": self.tri_candidates_evaluated,
            "tri_rejected_geometry": self.tri_rejected_geometry,
            "bounded_tri_products": self.bounded_tri_products,
            "per_target_product_counts": dict(sorted(self.per_target_product_counts.items())),
            "per_target_feasible_counts": dict(sorted(self.per_target_feasible_counts.items())),
            "zero_product_target_ids": sorted(self.zero_product_target_ids),
        }


@dataclass(frozen=True, slots=True)
class ProductConfig:
    max_tri_products_per_target_access: int = 50
    pair_mc_samples: int = 100
    tri_mc_samples: int = 100
    tri_pair_edge_mc_samples: int = 80

    @classmethod
    def from_mapping(cls, payload: dict[str, Any] | None) -> "ProductConfig":
        payload = payload or {}
        return cls(
            max_tri_products_per_target_access=int(
                payload.get("max_tri_products_per_target_access", 50)
            ),
            pair_mc_samples=int(payload.get("pair_mc_samples", 100)),
            tri_mc_samples=int(payload.get("tri_mc_samples", 100)),
            tri_pair_edge_mc_samples=int(payload.get("tri_pair_edge_mc_samples", 80)),
        )

    def as_status_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ProductLibrary:
    products: list[StereoProduct]
    per_target_products: dict[str, list[StereoProduct]]
    summary: ProductSummary

    def as_dict(self) -> dict[str, Any]:
        return {
            "products": [p.as_dict() for p in self.products],
            "summary": self.summary.as_dict(),
        }


@dataclass(slots=True)
class _CandidateGeoCache:
    """Pre-computed polyline and half-swath-width for a candidate."""

    polyline: list[tuple[float, float]]
    half_width_m: float


def _observation_window_keys(candidates: list[Candidate]) -> tuple[tuple[str, str], ...]:
    return tuple(sorted((_iso_z(c.start), _iso_z(c.end)) for c in candidates))


def _candidate_midpoint(candidate: Candidate):
    return candidate.start + (candidate.end - candidate.start) / 2


def _product_satellite_metadata(observations: tuple[Candidate, ...]) -> tuple[str, str]:
    satellite_ids = {obs.satellite_id for obs in observations}
    access_ids = {obs.access_interval_id for obs in observations}
    if len(satellite_ids) == 1:
        satellite_id = observations[0].satellite_id
        access_interval_id = observations[0].access_interval_id if len(access_ids) == 1 else "multi"
        return satellite_id, access_interval_id
    return "multi", "multi"


def _product_rng_keys(candidates: tuple[Candidate, ...]) -> tuple[str, str]:
    satellite_key = "&".join(sorted(c.satellite_id for c in candidates))
    access_key = "&".join(sorted(f"{c.satellite_id}:{c.access_interval_id}" for c in candidates))
    return satellite_key, access_key


def _pair_prerequisite_reasons(
    ci: Candidate,
    cj: Candidate,
    mission,
) -> list[str]:
    reasons: list[str] = []

    if ci.target_id != cj.target_id:
        reasons.append(f"target mismatch: {ci.target_id} != {cj.target_id}")

    mi = _candidate_midpoint(ci)
    mj = _candidate_midpoint(cj)
    pair_separation_s = abs((mi - mj).total_seconds())
    if pair_separation_s > mission.max_stereo_pair_separation_s + 1e-6:
        reasons.append(
            f"pair_separation {pair_separation_s:.3f}s > max {mission.max_stereo_pair_separation_s}"
        )

    if ci.satellite_id == cj.satellite_id:
        if ci.access_interval_id != cj.access_interval_id:
            reasons.append(
                "same-satellite pair requires matching access_interval_id"
            )
    elif not mission.allow_cross_satellite_stereo:
        reasons.append("cross-satellite stereo is disabled by mission")

    return reasons


def _evaluate_pair(
    ci: Candidate,
    cj: Candidate,
    case: StereoCase,
    sf_sats: dict[str, EarthSatellite],
    target_ecef: dict[str, np.ndarray],
    product_config: ProductConfig,
    geo_cache: dict[int, _CandidateGeoCache] | None = None,
    i: int = -1,
    j: int = -1,
) -> tuple[bool, float, list[str]]:
    """Evaluate a candidate pair. Returns (feasible, quality, reject_reasons)."""
    mission = case.mission
    target = case.targets[ci.target_id]
    sat_def_i = case.satellites[ci.satellite_id]
    sat_def_j = case.satellites[cj.satellite_id]
    sf_i = sf_sats[ci.satellite_id]
    sf_j = sf_sats[cj.satellite_id]
    te = target_ecef[ci.target_id]

    reasons = _pair_prerequisite_reasons(ci, cj, mission)
    if reasons:
        return False, 0.0, reasons

    # Convergence angle at target between view directions at midpoints
    mi = ci.start + (ci.end - ci.start) / 2
    mj = cj.start + (cj.end - cj.start) / 2
    si_pos, _ = _satellite_state_ecef_m(sf_i, mi)
    sj_pos, _ = _satellite_state_ecef_m(sf_j, mj)
    ui = (si_pos - te) / np.linalg.norm(si_pos - te)
    uj = (sj_pos - te) / np.linalg.norm(sj_pos - te)
    gamma = _angle_between_deg(ui, uj)

    if gamma < mission.min_convergence_deg - 1e-6:
        reasons.append(f"convergence {gamma:.3f}deg < min {mission.min_convergence_deg}")
    if gamma > mission.max_convergence_deg + 1e-6:
        reasons.append(f"convergence {gamma:.3f}deg > max {mission.max_convergence_deg}")

    # Overlap fraction via Monte Carlo
    if geo_cache is not None and i >= 0 and j >= 0:
        poly_i = geo_cache[i].polyline
        poly_j = geo_cache[j].polyline
        ri = geo_cache[i].half_width_m
        rj = geo_cache[j].half_width_m
    else:
        ri = ci.slant_range_m * math.tan(math.radians(sat_def_i.half_cross_track_fov_deg))
        rj = cj.slant_range_m * math.tan(math.radians(sat_def_j.half_cross_track_fov_deg))
        poly_i = _strip_polyline_en(
            sf_i, te, ci.start, ci.end, sample_step_s=8.0,
            off_nadir_along_deg=ci.off_nadir_along_deg,
            off_nadir_across_deg=ci.off_nadir_across_deg,
        )
        poly_j = _strip_polyline_en(
            sf_j, te, cj.start, cj.end, sample_step_s=8.0,
            off_nadir_along_deg=cj.off_nadir_along_deg,
            off_nadir_across_deg=cj.off_nadir_across_deg,
        )
    wk_pair = tuple(sorted((
        (_iso_z(ci.start), _iso_z(ci.end)),
        (_iso_z(cj.start), _iso_z(cj.end)),
    )))
    rng_satellite_id, rng_access_interval_id = _product_rng_keys((ci, cj))
    rng_pair = _stereo_mc_rng(
        case.case_dir.name,
        rng_satellite_id,
        ci.target_id,
        rng_access_interval_id,
        window_keys=wk_pair,
        n_samples=product_config.pair_mc_samples,
        role="pair_overlap",
    )
    o_ij = _monte_carlo_overlap_fraction(
        target.aoi_radius_m,
        poly_i, ri,
        poly_j, rj,
        n_samples=product_config.pair_mc_samples,
        rng=rng_pair,
    )

    if o_ij + 1e-6 < mission.min_overlap_fraction:
        reasons.append(f"overlap {o_ij:.3f} < min {mission.min_overlap_fraction}")

    # Pixel scale ratio
    si_m = ci.effective_pixel_scale_m
    sj_m = cj.effective_pixel_scale_m
    rscale = max(si_m, sj_m) / min(si_m, sj_m) if min(si_m, sj_m) > 0 else float("inf")
    if rscale > mission.max_pixel_scale_ratio + 1e-6:
        reasons.append(f"pixel_scale_ratio {rscale:.3f} > max {mission.max_pixel_scale_ratio}")

    feasible = len(reasons) == 0

    # Quality
    q_overlap = min(1.0, o_ij / 0.95)
    q_res = max(0.0, 1.0 - (rscale - 1.0) / 0.5)
    q_geom = _pair_geom_quality(gamma, target.scene_type)
    w = mission.pair_weights
    q_pair = (
        w["geometry"] * q_geom
        + w["overlap"] * q_overlap
        + w["resolution"] * q_res
    )

    return feasible, q_pair, reasons


def _evaluate_triple(
    c0: Candidate,
    c1: Candidate,
    c2: Candidate,
    case: StereoCase,
    sf_sats: dict[str, EarthSatellite],
    target_ecef: dict[str, np.ndarray],
    product_config: ProductConfig,
    geo_cache: dict[int, _CandidateGeoCache] | None = None,
    indices: tuple[int, int, int] | None = None,
    pair_cache: dict[tuple[int, int], tuple[bool, float, list[str]]] | None = None,
) -> tuple[bool, float, list[str]]:
    """Evaluate a candidate triple. Returns (feasible, quality, reject_reasons)."""
    mission = case.mission
    target = case.targets[c0.target_id]
    te = target_ecef[c0.target_id]

    reasons: list[str] = []
    candidates = [c0, c1, c2]

    # Common overlap
    if geo_cache is not None and indices is not None:
        i, j, k = indices
        polys = [geo_cache[i].polyline, geo_cache[j].polyline, geo_cache[k].polyline]
        hw = [geo_cache[i].half_width_m, geo_cache[j].half_width_m, geo_cache[k].half_width_m]
    else:
        polys = []
        hw = []
        for c in candidates:
            sat_def = case.satellites[c.satellite_id]
            sf = sf_sats[c.satellite_id]
            polys.append(_strip_polyline_en(
                sf, te, c.start, c.end, 8.0,
                off_nadir_along_deg=c.off_nadir_along_deg,
                off_nadir_across_deg=c.off_nadir_across_deg,
            ))
            hw.append(c.slant_range_m * math.tan(math.radians(sat_def.half_cross_track_fov_deg)))

    wk_tri = tuple(sorted(((_iso_z(c.start), _iso_z(c.end)) for c in candidates)))
    rng_satellite_id, rng_access_interval_id = _product_rng_keys((c0, c1, c2))
    rng_tri = _stereo_mc_rng(
        case.case_dir.name,
        rng_satellite_id,
        c0.target_id,
        rng_access_interval_id,
        window_keys=wk_tri,
        n_samples=product_config.tri_mc_samples,
        role="tri_overlap",
    )
    o_tri = _monte_carlo_tri_overlap(
        target.aoi_radius_m, polys, hw,
        n_samples=product_config.tri_mc_samples,
        rng=rng_tri,
    )

    if o_tri + 1e-6 < mission.min_overlap_fraction:
        reasons.append(f"tri_overlap {o_tri:.3f} < min {mission.min_overlap_fraction}")

    # Pair validity flags among (0,1),(0,2),(1,2)
    pair_flags: list[bool] = []
    pair_qs: list[float] = []
    pair_reason_count = 0
    pair_index_lookup = ((0, 1), (0, 2), (1, 2))
    for (ix, jx) in pair_index_lookup:
        ci, cj = candidates[ix], candidates[jx]
        prereq_reasons = _pair_prerequisite_reasons(ci, cj, mission)
        if prereq_reasons:
            pair_reason_count += 1
            for reason in prereq_reasons:
                reasons.append(f"pair {ix}-{jx}: {reason}")

        if pair_cache is not None and indices is not None:
            i, j, k = indices
            index_map = {0: i, 1: j, 2: k}
            a = index_map[ix]
            b = index_map[jx]
            key = (min(a, b), max(a, b))
            feasible, q_pair, _ = pair_cache[key]
        else:
            feasible, q_pair, _ = _evaluate_pair(
                ci,
                cj,
                case,
                sf_sats,
                target_ecef,
                product_config,
            )
        pair_flags.append(feasible)
        pair_qs.append(q_pair)

    if pair_reason_count > 0:
        reasons.append(
            f"{pair_reason_count} constituent pair(s) failed stereo-mode or pair-separation prerequisites"
        )

    if sum(1 for x in pair_flags if x) < 2:
        reasons.append(f"only {sum(1 for x in pair_flags if x)} valid pairs among 3 (need >= 2)")

    # Near-nadir anchor
    anchor = any(
        candidates[ix].boresight_off_nadir_deg <= mission.near_nadir_anchor_max_off_nadir_deg + 1e-6
        for ix in (0, 1, 2)
    )
    if not anchor:
        reasons.append(f"no near-nadir anchor (off_nadir <= {mission.near_nadir_anchor_max_off_nadir_deg})")

    feasible = len(reasons) == 0
    beta = mission.tri_stereo_bonus_by_scene[target.scene_type]
    tri_bonus_R = _tri_bonus_R(pair_flags, anchor)
    q_tri = _tri_quality_from_valid_pairs(
        pair_flags,
        pair_qs,
        beta=beta,
        tri_bonus_R=tri_bonus_R,
    )

    return feasible, q_tri, reasons


def build_product_library(
    candidates: list[Candidate],
    case: StereoCase,
    config: ProductConfig | None = None,
) -> ProductLibrary:
    config = config or ProductConfig()
    products: list[StereoProduct] = []
    per_target: dict[str, list[StereoProduct]] = {tid: [] for tid in case.targets}
    summary = ProductSummary()

    # Cache satellites and target ECEF
    sf_sats: dict[str, EarthSatellite] = {}
    for sid, sd in sorted(case.satellites.items()):
        sf_sats[sid] = EarthSatellite(sd.tle_line1, sd.tle_line2, name=sid, ts=_TS)
    target_ecef = {tid: np.asarray(brahe.position_geodetic_to_ecef(
        [t.longitude_deg, t.latitude_deg, t.elevation_ref_m],
        brahe.AngleFormat.DEGREES,
    ), dtype=float).reshape(3) for tid, t in case.targets.items()}

    # Group candidates by target_id so cross-satellite products can be enumerated.
    groups: dict[str, list[Candidate]] = {}
    for c in candidates:
        groups.setdefault(c.target_id, []).append(c)

    # Sort each group by midpoint time for deterministic pair-window pruning.
    for key in sorted(groups):
        groups[key].sort(
            key=lambda c: (
                _candidate_midpoint(c),
                c.start,
                c.end,
                c.satellite_id,
                c.access_interval_id,
                c.candidate_id,
            )
        )

    for target_id, group in sorted(groups.items()):
        n = len(group)
        te = target_ecef[target_id]

        # Pre-compute polylines and swath widths once per candidate in this group
        geo_cache: dict[int, _CandidateGeoCache] = {}
        for idx, c in enumerate(group):
            sat_def = case.satellites[c.satellite_id]
            sf = sf_sats[c.satellite_id]
            poly = _strip_polyline_en(
                sf, te, c.start, c.end, sample_step_s=8.0,
                off_nadir_along_deg=c.off_nadir_along_deg,
                off_nadir_across_deg=c.off_nadir_across_deg,
            )
            hw = c.slant_range_m * math.tan(math.radians(sat_def.half_cross_track_fov_deg))
            geo_cache[idx] = _CandidateGeoCache(polyline=poly, half_width_m=hw)

        midpoints = [_candidate_midpoint(candidate) for candidate in group]

        # Pairs — prune by cheap prerequisites before geometry and cache results
        summary.pair_candidates_considered += n * (n - 1) // 2
        pair_cache: dict[tuple[int, int], tuple[bool, float, list[str]]] = {}
        pair_prereq_neighbors: dict[int, set[int]] = {idx: set() for idx in range(n)}
        prereq_pass_count = 0
        upper = 1
        for i in range(n):
            if upper < i + 1:
                upper = i + 1
            while (
                upper < n
                and (midpoints[upper] - midpoints[i]).total_seconds()
                <= case.mission.max_stereo_pair_separation_s + 1e-6
            ):
                upper += 1
            for j in range(i + 1, upper):
                ci, cj = group[i], group[j]
                prereq_reasons = _pair_prerequisite_reasons(ci, cj, case.mission)
                if prereq_reasons:
                    continue
                prereq_pass_count += 1
                pair_prereq_neighbors[i].add(j)
                pair_prereq_neighbors[j].add(i)
                feasible, q_pair, reasons = _evaluate_pair(
                    ci, cj, case, sf_sats, target_ecef, config,
                    geo_cache=geo_cache, i=i, j=j,
                )
                pair_cache[(i, j)] = (feasible, q_pair, reasons)
                if not feasible:
                    summary.infeasible_products += 1
                    summary.pair_rejected_geometry += 1
                    continue
                product_satellite_id, product_access_interval_id = _product_satellite_metadata((ci, cj))
                product = StereoProduct(
                    product_id=f"pair|{target_id}|{i}|{j}",
                    product_type=ProductType.PAIR,
                    target_id=target_id,
                    satellite_id=product_satellite_id,
                    access_interval_id=product_access_interval_id,
                    observations=(ci, cj),
                    quality=q_pair,
                    coverage_value=q_pair,
                    feasible=True,
                    reject_reasons=tuple(),
                )
                products.append(product)
                per_target[target_id].append(product)
                summary.total_products += 1
                summary.pair_products += 1
                summary.feasible_products += 1
                summary.per_target_feasible_counts[target_id] = (
                    summary.per_target_feasible_counts.get(target_id, 0) + 1
                )
        summary.pair_pruned_prerequisite += (n * (n - 1) // 2) - prereq_pass_count

        # Triples — evaluate only from prerequisite-compatible pair triangles.
        tri_candidates: list[StereoProduct] = []
        for i in range(n):
            for j in sorted(k for k in pair_prereq_neighbors[i] if k > i):
                candidate_ks = sorted(k for k in pair_prereq_neighbors[i].intersection(pair_prereq_neighbors[j]) if k > j)
                for k in candidate_ks:
                    summary.tri_candidates_evaluated += 1
                    c0, c1, c2 = group[i], group[j], group[k]
                    feasible, q_tri, reasons = _evaluate_triple(
                        c0, c1, c2, case, sf_sats, target_ecef, config,
                        geo_cache=geo_cache, indices=(i, j, k),
                        pair_cache=pair_cache,
                    )
                    if not feasible:
                        summary.infeasible_products += 1
                        summary.tri_rejected_geometry += 1
                        continue
                    product_satellite_id, product_access_interval_id = _product_satellite_metadata((c0, c1, c2))
                    product = StereoProduct(
                        product_id=f"tri|{target_id}|{i}|{j}|{k}",
                        product_type=ProductType.TRI,
                        target_id=target_id,
                        satellite_id=product_satellite_id,
                        access_interval_id=product_access_interval_id,
                        observations=(c0, c1, c2),
                        quality=q_tri,
                        coverage_value=q_tri,
                        feasible=True,
                        reject_reasons=tuple(),
                    )
                    tri_candidates.append(product)

        # Bound tri-stereo candidates per target after target-global enumeration.
        tri_candidates.sort(key=lambda p: (-p.coverage_value, -p.quality, p.product_id))
        kept = tri_candidates[: config.max_tri_products_per_target_access]
        summary.bounded_tri_products += len(tri_candidates) - len(kept)

        for product in kept:
            products.append(product)
            per_target[target_id].append(product)
            summary.total_products += 1
            summary.tri_products += 1
            summary.feasible_products += 1
            summary.per_target_feasible_counts[target_id] = (
                summary.per_target_feasible_counts.get(target_id, 0) + 1
            )

    # Sort all products deterministically
    products.sort(key=lambda p: (
        -p.coverage_value,
        -p.quality,
        p.target_id,
        p.satellite_id,
        p.access_interval_id,
        tuple(_iso_z(o.start) for o in p.observations),
    ))

    for target_id in case.targets:
        summary.per_target_product_counts[target_id] = len(per_target[target_id])
        if len(per_target[target_id]) == 0:
            summary.zero_product_target_ids.append(target_id)

    return ProductLibrary(
        products=products,
        per_target_products=per_target,
        summary=summary,
    )
