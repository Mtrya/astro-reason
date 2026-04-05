"""Stereo imaging v3 verification engine."""

from __future__ import annotations

import math
import random
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import brahe
import numpy as np
from skyfield.api import EarthSatellite, load
from skyfield.framelib import itrs

from .io import load_case, load_solution_actions
from .models import (
    DerivedObservation,
    Mission,
    ObservationAction,
    SatelliteDef,
    TargetDef,
    VerificationReport,
)

# ---------------------------------------------------------------------------
# Numerics / frames
# ---------------------------------------------------------------------------

_NUMERICAL_EPS = 1e-9
_WGS84_A_M = 6378137.0
_WGS84_B_M = 6356752.3142451793

_TS = load.timescale()
brahe.set_global_eop_provider_from_static_provider(brahe.StaticEOPProvider.from_zero())

_SCENE_GEOM_BANDS_DEG: dict[str, tuple[float, float]] = {
    "urban_structured": (8.0, 18.0),
    "vegetated": (8.0, 14.0),
    "rugged": (10.0, 20.0),
    "open": (15.0, 25.0),
}


def _datetime_to_epoch(value: datetime) -> brahe.Epoch:
    value = value.astimezone(UTC)
    second = float(value.second) + (value.microsecond / 1_000_000.0)
    return brahe.Epoch.from_datetime(
        value.year,
        value.month,
        value.day,
        value.hour,
        value.minute,
        second,
        0.0,
        brahe.TimeSystem.UTC,
    )


def _iso_z(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _angle_between_deg(a: np.ndarray, b: np.ndarray) -> float:
    na = np.linalg.norm(a)
    nb = np.linalg.norm(b)
    if na < _NUMERICAL_EPS or nb < _NUMERICAL_EPS:
        return 0.0
    c = float(np.dot(a, b) / (na * nb))
    c = max(-1.0, min(1.0, c))
    return math.degrees(math.acos(c))


def _satellite_state_ecef_m(sat: EarthSatellite, dt: datetime) -> tuple[np.ndarray, np.ndarray]:
    """Return (position_m, velocity_mps) in ITRS/ECEF consistent with brahe geodetic ECEF."""
    t = _TS.from_datetime(dt.astimezone(UTC))
    g = sat.at(t)
    pos, vel = g.frame_xyz_and_velocity(itrs)
    pos_m = np.asarray(pos.km, dtype=float).reshape(3) * 1000.0
    vel_mps = np.asarray(vel.km_per_s, dtype=float).reshape(3) * 1000.0
    return pos_m, vel_mps


def _target_ecef_m(target: TargetDef) -> np.ndarray:
    return np.asarray(
        brahe.position_geodetic_to_ecef(
            [target.longitude_deg, target.latitude_deg, target.elevation_ref_m],
            brahe.AngleFormat.DEGREES,
        ),
        dtype=float,
    ).reshape(3)


def _ray_ellipsoid_intersection_m(
    origin_m: np.ndarray,
    direction_unit: np.ndarray,
) -> float | None:
    """Smallest positive t where origin + t*dir hits WGS84-like ellipsoid."""
    ox, oy, oz = (float(origin_m[i]) for i in range(3))
    dx, dy, dz = (float(direction_unit[i]) for i in range(3))
    a2 = _WGS84_A_M * _WGS84_A_M
    b2 = _WGS84_B_M * _WGS84_B_M
    inv_a2 = 1.0 / a2
    inv_b2 = 1.0 / b2
    aa = (dx * dx + dy * dy) * inv_a2 + dz * dz * inv_b2
    bb = 2.0 * ((ox * dx + oy * dy) * inv_a2 + oz * dz * inv_b2)
    cc = (ox * ox + oy * oy) * inv_a2 + oz * oz * inv_b2 - 1.0
    disc = bb * bb - 4.0 * aa * cc
    if disc < 0.0 or abs(aa) < _NUMERICAL_EPS:
        return None
    sqrt_disc = math.sqrt(disc)
    t1 = (-bb - sqrt_disc) / (2.0 * aa)
    t2 = (-bb + sqrt_disc) / (2.0 * aa)
    candidates = [t for t in (t1, t2) if t > _NUMERICAL_EPS]
    if not candidates:
        return None
    return min(candidates)


def _ground_intercept_ecef_m(
    sat_pos_m: np.ndarray,
    target_pos_m: np.ndarray,
) -> np.ndarray:
    """Ground intercept of the ray from satellite toward target (positive t)."""
    los = target_pos_m - sat_pos_m
    dist = float(np.linalg.norm(los))
    if dist < _NUMERICAL_EPS:
        return target_pos_m.copy()
    d = los / dist
    t_hit = _ray_ellipsoid_intersection_m(sat_pos_m, d)
    if t_hit is None:
        return target_pos_m.copy()
    return sat_pos_m + t_hit * d


def _off_nadir_deg(sat_pos_m: np.ndarray, target_pos_m: np.ndarray) -> float:
    los = target_pos_m - sat_pos_m
    if float(np.linalg.norm(los)) < _NUMERICAL_EPS:
        return 0.0
    los_hat = los / np.linalg.norm(los)
    nadir = -sat_pos_m / np.linalg.norm(sat_pos_m)
    c = float(np.dot(nadir, los_hat))
    c = max(-1.0, min(1.0, c))
    return math.degrees(math.acos(c))


def _solar_elevation_azimuth_deg(
    epoch: brahe.Epoch,
    target_ecef_m: np.ndarray,
) -> tuple[float, float]:
    """Solar elevation and azimuth (deg) at target using brahe sun vector."""
    sun_hat = np.asarray(brahe.sun_position(epoch), dtype=float).reshape(3)
    sun_hat = sun_hat / np.linalg.norm(sun_hat)
    r = np.asarray(brahe.rotation_eci_to_ecef(epoch), dtype=float).reshape(3, 3)
    sun_dir_ecef = (r @ sun_hat).reshape(3)
    au = 1.496e11
    r_t = target_ecef_m.reshape(3)
    up = r_t / np.linalg.norm(r_t)
    v = au * sun_dir_ecef - r_t
    v = v / np.linalg.norm(v)
    el = math.degrees(math.asin(max(-1.0, min(1.0, float(np.dot(up, v))))))
    east = np.cross(up, np.array([0.0, 0.0, 1.0]))
    if float(np.linalg.norm(east)) < _NUMERICAL_EPS:
        east = np.array([0.0, 1.0, 0.0])
    else:
        east = east / np.linalg.norm(east)
    north = np.cross(east, up)
    north = north / np.linalg.norm(north)
    proj = v - float(np.dot(v, up)) * up
    if float(np.linalg.norm(proj)) < _NUMERICAL_EPS:
        az = 0.0
    else:
        proj = proj / np.linalg.norm(proj)
        az = math.degrees(math.atan2(float(np.dot(proj, east)), float(np.dot(proj, north))))
        if az < 0.0:
            az += 360.0
    return el, az


def _enu_horizontal(en_vec: np.ndarray) -> tuple[float, float]:
    return float(en_vec[0]), float(en_vec[1])


def _boresight_azimuth_deg(target_ecef_m: np.ndarray, sat_ecef_m: np.ndarray) -> float:
    los = sat_ecef_m - target_ecef_m
    if float(np.linalg.norm(los)) < _NUMERICAL_EPS:
        return 0.0
    rel = brahe.relative_position_ecef_to_enz(
        target_ecef_m,
        sat_ecef_m,
        brahe.EllipsoidalConversionType.GEOCENTRIC,
    )
    e, n = float(rel[0]), float(rel[1])
    return math.degrees(math.atan2(e, n)) % 360.0


def _ecef_to_enz(target_ecef_m: np.ndarray, point_ecef_m: np.ndarray) -> np.ndarray:
    return np.asarray(
        brahe.relative_position_ecef_to_enz(
            target_ecef_m,
            point_ecef_m,
            brahe.EllipsoidalConversionType.GEOCENTRIC,
        ),
        dtype=float,
    ).reshape(3)


def _point_distance_to_polyline_2d(
    p_en: tuple[float, float],
    poly: list[tuple[float, float]],
) -> float:
    if not poly:
        return float("inf")
    px, py = p_en
    best = float("inf")
    for i in range(len(poly) - 1):
        x1, y1 = poly[i]
        x2, y2 = poly[i + 1]
        vx, vy = x2 - x1, y2 - y1
        seg_len2 = vx * vx + vy * vy
        if seg_len2 < _NUMERICAL_EPS:
            d = math.hypot(px - x1, py - y1)
            best = min(best, d)
            continue
        t = max(0.0, min(1.0, ((px - x1) * vx + (py - y1) * vy) / seg_len2))
        qx = x1 + t * vx
        qy = y1 + t * vy
        best = min(best, math.hypot(px - qx, py - qy))
    return best


def _strip_polyline_en(
    sat: EarthSatellite,
    target_ecef_m: np.ndarray,
    start: datetime,
    end: datetime,
    sample_step_s: float,
) -> list[tuple[float, float]]:
    pts: list[tuple[float, float]] = []
    if end <= start:
        return pts
    t = start
    while t <= end:
        sp, _ = _satellite_state_ecef_m(sat, t)
        gp = _ground_intercept_ecef_m(sp, target_ecef_m)
        enz = _ecef_to_enz(target_ecef_m, gp)
        e, n = _enu_horizontal(enz)
        pts.append((e, n))
        t += timedelta(seconds=sample_step_s)
    return pts


def _monte_carlo_overlap_fraction(
    aoi_radius_m: float,
    poly_a: list[tuple[float, float]],
    half_w_a_m: float,
    poly_b: list[tuple[float, float]],
    half_w_b_m: float,
    *,
    n_samples: int,
    rng: random.Random,
) -> float:
    """Approximate area(intersection of strips with AOI disk) / area(disk).

    Polyline vertices and sample points are in the same local ENU frame (origin at
    target center); target ECEF is not needed here.
    """
    if aoi_radius_m <= _NUMERICAL_EPS:
        return 0.0
    inside_both = 0
    for _ in range(n_samples):
        r = aoi_radius_m * math.sqrt(rng.random())
        theta = rng.random() * 2.0 * math.pi
        e = r * math.cos(theta)
        n = r * math.sin(theta)
        da = _point_distance_to_polyline_2d((e, n), poly_a)
        db = _point_distance_to_polyline_2d((e, n), poly_b)
        if da <= half_w_a_m + _NUMERICAL_EPS and db <= half_w_b_m + _NUMERICAL_EPS:
            inside_both += 1
    return inside_both / n_samples


def _monte_carlo_tri_overlap(
    aoi_radius_m: float,
    polys: list[list[tuple[float, float]]],
    half_ws: list[float],
    *,
    n_samples: int,
    rng: random.Random,
) -> float:
    if aoi_radius_m <= _NUMERICAL_EPS:
        return 0.0
    ok = 0
    for _ in range(n_samples):
        r = aoi_radius_m * math.sqrt(rng.random())
        theta = rng.random() * 2.0 * math.pi
        e = r * math.cos(theta)
        n = r * math.sin(theta)
        if all(
            _point_distance_to_polyline_2d((e, n), polys[i]) <= half_ws[i] + _NUMERICAL_EPS
            for i in range(3)
        ):
            ok += 1
    return ok / n_samples


def _combined_off_nadir_deg(along: float, across: float) -> float:
    return math.hypot(float(along), float(across))


def _access_predicate(
    sat: EarthSatellite,
    target: TargetDef,
    target_ecef_m: np.ndarray,
    sat_def: SatelliteDef,
    mission: Mission,
    dt: datetime,
) -> bool:
    sp, _ = _satellite_state_ecef_m(sat, dt)
    off = _off_nadir_deg(sp, target_ecef_m)
    if off > sat_def.max_off_nadir_deg + 1e-6:
        return False
    epoch = _datetime_to_epoch(dt)
    el, _ = _solar_elevation_azimuth_deg(epoch, target_ecef_m)
    if el < mission.min_solar_elevation_deg - 1e-6:
        return False
    return True


def _build_access_intervals(
    sat: EarthSatellite,
    target: TargetDef,
    target_ecef_m: np.ndarray,
    sat_def: SatelliteDef,
    mission: Mission,
    horizon_start: datetime,
    horizon_end: datetime,
    grid_s: float = 60.0,
) -> list[tuple[datetime, datetime, str]]:
    """Return maximal contiguous intervals where access predicate holds."""
    intervals: list[tuple[datetime, datetime, str]] = []
    if horizon_end <= horizon_start:
        return intervals
    dts: list[datetime] = []
    t = horizon_start
    while t <= horizon_end:
        dts.append(t)
        t += timedelta(seconds=grid_s)
    if dts[-1] < horizon_end:
        dts.append(horizon_end)

    mask = [
        _access_predicate(sat, target, target_ecef_m, sat_def, mission, d)
        for d in dts
    ]

    i = 0
    idx = 0
    while i < len(mask):
        if not mask[i]:
            i += 1
            continue
        j = i
        while j < len(mask) and mask[j]:
            j += 1
        start_dt = dts[i]
        end_dt = dts[j - 1] + timedelta(seconds=grid_s)
        if end_dt >= start_dt:
            aid = f"{sat_def.sat_id}::{target.target_id}::{idx}"
            idx += 1
            intervals.append((start_dt, end_dt, aid))
        i = j
    return intervals


def _interval_contains(mid: datetime, start: datetime, end: datetime) -> bool:
    return start <= mid <= end


def _assign_access_id(
    mid: datetime,
    intervals: list[tuple[datetime, datetime, str]],
) -> str | None:
    for a, b, aid in intervals:
        if _interval_contains(mid, a, b):
            return aid
    return None


def _min_slew_time_s(delta_deg: float, sat_def: SatelliteDef) -> float:
    """Minimum slew time using bang-bang (trapezoidal) profile."""
    d = abs(delta_deg)
    if d < _NUMERICAL_EPS:
        return 0.0
    omega = sat_def.max_slew_velocity_deg_per_s
    alpha = sat_def.max_slew_acceleration_deg_per_s2
    if omega < _NUMERICAL_EPS or alpha < _NUMERICAL_EPS:
        return float("inf")
    d_triangular = omega * omega / alpha
    if d <= d_triangular:
        return 2.0 * math.sqrt(d / alpha)
    else:
        return d / omega + omega / alpha


def _pair_geom_quality(gamma_deg: float, scene: str) -> float:
    lo, hi = _SCENE_GEOM_BANDS_DEG.get(scene, (8.0, 18.0))
    if lo <= gamma_deg <= hi:
        return 1.0
    dist = min(abs(gamma_deg - lo), abs(gamma_deg - hi))
    return max(0.0, 1.0 - dist / 10.0)


def _tri_bonus_R(
    pair_ok: list[bool],
    has_anchor: bool,
) -> float:
    """Bounded redundancy + anchor bonus in [0, 1]."""
    r = 0.0
    if sum(pair_ok) >= 2:
        r += 0.6
    if has_anchor:
        r += 0.4
    return min(1.0, r)


def verify_solution(case_dir: str | Path, solution_path: str | Path) -> VerificationReport:
    case_path = Path(case_dir)
    case_id = case_path.name
    mission, satellites, targets = load_case(case_path)
    actions = load_solution_actions(solution_path, case_id)

    violations: list[str] = []
    rng = random.Random(20260406)

    # EarthSatellite cache
    sf_sats: dict[str, EarthSatellite] = {}
    for sid, sd in satellites.items():
        sf_sats[sid] = EarthSatellite(sd.tle_line1, sd.tle_line2, name=sid, ts=_TS)

    # Access intervals only for satellite–target pairs referenced by the solution
    access_index: dict[tuple[str, str], list[tuple[datetime, datetime, str]]] = {}
    target_ecef: dict[str, np.ndarray] = {tid: _target_ecef_m(t) for tid, t in targets.items()}

    needed_pairs = {(a.satellite_id, a.target_id) for a in actions}
    for sid, tid in needed_pairs:
        if sid not in satellites or tid not in targets:
            continue
        access_index[(sid, tid)] = _build_access_intervals(
            sf_sats[sid],
            targets[tid],
            target_ecef[tid],
            satellites[sid],
            mission,
            mission.horizon_start,
            mission.horizon_end,
            grid_s=90.0,
        )

    derived_list: list[DerivedObservation] = []

    # --- Action-level checks ---
    for k, act in enumerate(actions):
        prefix = f"actions[{k}]"
        if act.end <= act.start:
            violations.append(f"{prefix}: end_time must be after start_time")
        if act.start < mission.horizon_start or act.end > mission.horizon_end:
            violations.append(f"{prefix}: observation outside mission horizon")
        if act.satellite_id not in satellites:
            violations.append(f"{prefix}: unknown satellite_id {act.satellite_id!r}")
            continue
        if act.target_id not in targets:
            violations.append(f"{prefix}: unknown target_id {act.target_id!r}")
            continue
        sd = satellites[act.satellite_id]
        dur = (act.end - act.start).total_seconds()
        if dur + 1e-9 < sd.min_obs_duration_s or dur - 1e-9 > sd.max_obs_duration_s:
            violations.append(
                f"{prefix}: duration {dur:.3f}s not in "
                f"[{sd.min_obs_duration_s}, {sd.max_obs_duration_s}]"
            )
        comb = _combined_off_nadir_deg(act.off_nadir_along_deg, act.off_nadir_across_deg)
        if comb - 1e-6 > sd.max_off_nadir_deg:
            violations.append(
                f"{prefix}: combined off-nadir {comb:.6f}deg exceeds max_off_nadir_deg "
                f"{sd.max_off_nadir_deg}"
            )

    # Per-satellite: overlap and slew
    by_sat: dict[str, list[tuple[int, ObservationAction]]] = {}
    for i, act in enumerate(actions):
        by_sat.setdefault(act.satellite_id, []).append((i, act))
    for sid, lst in by_sat.items():
        lst.sort(key=lambda x: x[1].start)
        for j in range(len(lst) - 1):
            (_, a0), (_, a1) = lst[j], lst[j + 1]
            if a1.start < a0.end:
                violations.append(
                    f"satellite {sid}: overlapping observations "
                    f"[{a0.start.isoformat()}, {a0.end.isoformat()}) and "
                    f"[{a1.start.isoformat()}, {a1.end.isoformat()})"
                )
            sd = satellites[sid]
            te0 = target_ecef[a0.target_id]
            te1 = target_ecef[a1.target_id]
            sf = sf_sats[sid]
            los0 = _satellite_state_ecef_m(sf, a0.end)[0]
            los1 = _satellite_state_ecef_m(sf, a1.start)[0]
            v0 = (te0 - los0) / np.linalg.norm(te0 - los0)
            v1 = (te1 - los1) / np.linalg.norm(te1 - los1)
            delta_deg = _angle_between_deg(v0, v1)
            gap = (a1.start - a0.end).total_seconds()
            need = sd.settling_time_s + _min_slew_time_s(delta_deg, sd)
            if gap + 1e-6 < need:
                violations.append(
                    f"satellite {sid}: insufficient slew/settle between observations "
                    f"(need ~{need:.3f}s, gap {gap:.3f}s, delta {delta_deg:.4f}deg)"
                )

    # Derived observations + access membership
    for k, act in enumerate(actions):
        prefix = f"actions[{k}]"
        sd = satellites[act.satellite_id]
        tg = targets[act.target_id]
        mid = act.start + (act.end - act.start) / 2
        sf = sf_sats[act.satellite_id]
        sp, sv = _satellite_state_ecef_m(sf, mid)
        te = target_ecef[act.target_id]
        epoch = _datetime_to_epoch(mid)
        el, saz = _solar_elevation_azimuth_deg(epoch, te)
        off = _off_nadir_deg(sp, te)
        slant = float(np.linalg.norm(te - sp))
        eff_px = slant * sd.pixel_ifov_deg * (math.pi / 180.0)
        intervals = access_index.get((act.satellite_id, act.target_id), [])
        aid = _assign_access_id(mid, intervals)
        if aid is None:
            violations.append(
                f"{prefix}: observation midpoint not inside a continuous access interval"
            )
        derived_list.append(
            DerivedObservation(
                satellite_id=act.satellite_id,
                target_id=act.target_id,
                start_time=_iso_z(act.start),
                end_time=_iso_z(act.end),
                midpoint_time=_iso_z(mid),
                sat_position_ecef_m=sp.tolist(),
                sat_velocity_ecef_mps=sv.tolist(),
                boresight_off_nadir_deg=float(off),
                boresight_azimuth_deg=float(_boresight_azimuth_deg(te, sp)),
                solar_elevation_deg=float(el),
                solar_azimuth_deg=float(saz),
                effective_pixel_scale_m=float(eff_px),
                access_interval_id=aid or "none",
                slant_range_m=float(slant),
            )
        )

    # Stereo products (same satellite, same target, same access id)
    derived_by_key: dict[tuple[str, str, str], list[tuple[int, DerivedObservation]]] = {}
    for i, d in enumerate(derived_list):
        if d.access_interval_id == "none":
            continue
        key = (d.satellite_id, d.target_id, d.access_interval_id)
        derived_by_key.setdefault(key, []).append((i, d))

    pair_diagnostics: list[dict[str, Any]] = []

    per_target_best: dict[str, float] = {tid: 0.0 for tid in targets}
    covered: set[str] = set()

    for _key, group in derived_by_key.items():
        sat_id, target_id, _aid = _key
        tg = targets[target_id]
        sd = satellites[sat_id]
        sf = sf_sats[sat_id]
        te = target_ecef[target_id]
        obs_indices = [g[0] for g in group]
        ders = [g[1] for g in group]
        n = len(ders)
        # pairwise
        for i in range(n):
            for j in range(i + 1, n):
                di, dj = ders[i], ders[j]
                ai = actions[obs_indices[i]]
                aj = actions[obs_indices[j]]
                # convergence at target between view directions to satellite at midpoints
                si = _satellite_state_ecef_m(sf, ai.start + (ai.end - ai.start) / 2)[0]
                sj = _satellite_state_ecef_m(sf, aj.start + (aj.end - aj.start) / 2)[0]
                ui = (si - te) / np.linalg.norm(si - te)
                uj = (sj - te) / np.linalg.norm(sj - te)
                gamma = _angle_between_deg(ui, uj)
                ri = di.slant_range_m * math.tan(math.radians(sd.half_cross_track_fov_deg))
                rj = dj.slant_range_m * math.tan(math.radians(sd.half_cross_track_fov_deg))
                poly_i = _strip_polyline_en(sf, te, ai.start, ai.end, sample_step_s=8.0)
                poly_j = _strip_polyline_en(sf, te, aj.start, aj.end, sample_step_s=8.0)
                o_ij = _monte_carlo_overlap_fraction(
                    tg.aoi_radius_m,
                    poly_i,
                    ri,
                    poly_j,
                    rj,
                    n_samples=100,
                    rng=rng,
                )
                si_m = di.effective_pixel_scale_m
                sj_m = dj.effective_pixel_scale_m
                rscale = max(si_m, sj_m) / min(si_m, sj_m)
                nadir_alt_i = float(np.linalg.norm(si)) - _WGS84_A_M
                nadir_alt_j = float(np.linalg.norm(sj)) - _WGS84_A_M
                mean_alt = max(1000.0, 0.5 * (nadir_alt_i + nadir_alt_j))
                bh = float(np.linalg.norm(si - sj)) / mean_alt

                ok = (
                    o_ij + 1e-6 >= mission.min_overlap_fraction
                    and mission.min_convergence_deg - 1e-6 <= gamma <= mission.max_convergence_deg + 1e-6
                    and rscale <= mission.max_pixel_scale_ratio + 1e-6
                )
                q_overlap = min(1.0, o_ij / 0.95)
                q_res = max(0.0, 1.0 - (rscale - 1.0) / 0.5)
                q_geom = _pair_geom_quality(gamma, tg.scene_type)
                w = mission.pair_weights
                q_pair = (
                    w["geometry"] * q_geom
                    + w["overlap"] * q_overlap
                    + w["resolution"] * q_res
                )
                pair_diagnostics.append(
                    {
                        "satellite_id": sat_id,
                        "target_id": target_id,
                        "access_interval_id": di.access_interval_id,
                        "gamma_deg": gamma,
                        "overlap_fraction": o_ij,
                        "pixel_scale_ratio": rscale,
                        "b_h_proxy": bh,
                        "valid_pair": ok,
                        "q_pair": q_pair if ok else 0.0,
                    }
                )
                if ok:
                    covered.add(target_id)
                    if q_pair > per_target_best[target_id]:
                        per_target_best[target_id] = q_pair

        # triples
        for i in range(n):
            for j in range(i + 1, n):
                for k in range(j + 1, n):
                    a0, a1, a2 = actions[obs_indices[i]], actions[obs_indices[j]], actions[obs_indices[k]]
                    d0, d1, d2 = ders[i], ders[j], ders[k]
                    polys = [
                        _strip_polyline_en(sf, te, a0.start, a0.end, 8.0),
                        _strip_polyline_en(sf, te, a1.start, a1.end, 8.0),
                        _strip_polyline_en(sf, te, a2.start, a2.end, 8.0),
                    ]
                    hw = [
                        d0.slant_range_m * math.tan(math.radians(sd.half_cross_track_fov_deg)),
                        d1.slant_range_m * math.tan(math.radians(sd.half_cross_track_fov_deg)),
                        d2.slant_range_m * math.tan(math.radians(sd.half_cross_track_fov_deg)),
                    ]
                    o_tri = _monte_carlo_tri_overlap(
                        tg.aoi_radius_m, polys, hw, n_samples=100, rng=rng
                    )
                    # pair validity flags among (0,1),(0,2),(1,2) using same geometry as above - approximate by recomputing
                    pair_flags = []
                    pair_qs = []
                    for (ix, jx) in ((i, j), (i, k), (j, k)):
                        di, dj = ders[ix], ders[jx]
                        ai, aj = actions[obs_indices[ix]], actions[obs_indices[jx]]
                        si = _satellite_state_ecef_m(sf, ai.start + (ai.end - ai.start) / 2)[0]
                        sj = _satellite_state_ecef_m(sf, aj.start + (aj.end - aj.start) / 2)[0]
                        ui = (si - te) / np.linalg.norm(si - te)
                        uj = (sj - te) / np.linalg.norm(sj - te)
                        gam = _angle_between_deg(ui, uj)
                        poly_i = _strip_polyline_en(sf, te, ai.start, ai.end, 8.0)
                        poly_j = _strip_polyline_en(sf, te, aj.start, aj.end, 8.0)
                        o2 = _monte_carlo_overlap_fraction(
                            tg.aoi_radius_m,
                            poly_i,
                            di.slant_range_m * math.tan(math.radians(sd.half_cross_track_fov_deg)),
                            poly_j,
                            dj.slant_range_m * math.tan(math.radians(sd.half_cross_track_fov_deg)),
                            n_samples=80,
                            rng=rng,
                        )
                        si_m = di.effective_pixel_scale_m
                        sj_m = dj.effective_pixel_scale_m
                        rsc = max(si_m, sj_m) / min(si_m, sj_m)
                        okp = (
                            o2 + 1e-6 >= mission.min_overlap_fraction
                            and mission.min_convergence_deg - 1e-6
                            <= gam
                            <= mission.max_convergence_deg + 1e-6
                            and rsc <= mission.max_pixel_scale_ratio + 1e-6
                        )
                        pair_flags.append(okp)
                        qo = min(1.0, o2 / 0.95)
                        qr = max(0.0, 1.0 - (rsc - 1.0) / 0.5)
                        qg = _pair_geom_quality(gam, tg.scene_type)
                        w = mission.pair_weights
                        pair_qs.append(
                            w["geometry"] * qg
                            + w["overlap"] * qo
                            + w["resolution"] * qr
                        )
                    anchor = any(
                        ders[ix].boresight_off_nadir_deg
                        <= mission.near_nadir_anchor_max_off_nadir_deg + 1e-6
                        for ix in (i, j, k)
                    )
                    tri_ok = (
                        o_tri + 1e-6 >= mission.min_overlap_fraction
                        and sum(1 for x in pair_flags if x) >= 2
                        and anchor
                    )
                    beta = mission.tri_stereo_bonus_by_scene[tg.scene_type]
                    r = _tri_bonus_R(pair_flags, anchor)
                    q_tri = min(
                        1.0,
                        max(pair_qs) + beta * r,
                    )
                    if tri_ok:
                        covered.add(target_id)
                        if q_tri > per_target_best[target_id]:
                            per_target_best[target_id] = q_tri

    n_targets = len(targets)
    coverage_ratio = len(covered) / n_targets
    normalized_quality = sum(per_target_best[tid] for tid in targets) / n_targets

    valid = len(violations) == 0

    report = VerificationReport(
        valid=valid,
        metrics={
            "valid": valid,
            "coverage_ratio": float(coverage_ratio),
            "normalized_quality": float(normalized_quality),
        },
        violations=violations,
        derived_observations=[asdict(d) for d in derived_list],
        diagnostics={
            "pair_evaluations": pair_diagnostics,
            "per_target_best_score": {k: float(v) for k, v in per_target_best.items()},
        },
    )
    return report


def verify_solution_dict(case_dir: str | Path, solution_path: str | Path) -> dict[str, Any]:
    return verify_solution(case_dir, solution_path).to_dict()
