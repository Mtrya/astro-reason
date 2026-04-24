"""Feasibility audit for generated stereo_imaging cases."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import numpy as np
from skyfield.api import EarthSatellite

from benchmarks.stereo_imaging.verifier.engine import (
    _access_holds_over_window,
    _access_interval_sampling_step_s,
    _access_predicate,
    _action_midpoint,
    _angle_between_deg,
    _boresight_azimuth_deg,
    _boresight_unit_vector,
    _combined_off_nadir_deg,
    _datetime_to_epoch,
    _evaluate_stereo_pair,
    _iso_z,
    _min_slew_time_s,
    _satellite_local_axes,
    _satellite_state_ecef_m,
    _solar_elevation_azimuth_deg,
    _stereo_pair_mode,
    _target_ecef_m,
    _TS,
)
from benchmarks.stereo_imaging.verifier.models import (
    DerivedObservation,
    Mission,
    ObservationAction,
    SatelliteDef,
    TargetDef,
)


DEFAULT_FEASIBILITY_GUARD_CONFIG: dict[str, float | int] = {
    "access_sample_step_s": 60.0,
    "max_candidate_observations_per_access": 8,
    "overlap_samples": 80,
}


@dataclass(frozen=True)
class CandidateObservation:
    action: ObservationAction
    derived: DerivedObservation


@dataclass(frozen=True)
class FeasibilityAuditResult:
    feasible: bool
    diagnostics: dict[str, Any]


def _parse_iso_utc(value: str) -> datetime:
    s = value.strip()
    if s.endswith("Z") or s.endswith("z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        raise ValueError(f"timestamp must include timezone: {value!r}")
    return dt.astimezone(UTC)


def _mission_from_doc(doc: dict[str, Any]) -> Mission:
    m = doc["mission"] if "mission" in doc else doc
    vt = m["validity_thresholds"]
    qm = m["quality_model"]
    return Mission(
        horizon_start=_parse_iso_utc(str(m["horizon_start"])),
        horizon_end=_parse_iso_utc(str(m["horizon_end"])),
        allow_cross_satellite_stereo=bool(m.get("allow_cross_satellite_stereo", False)),
        max_stereo_pair_separation_s=float(m["max_stereo_pair_separation_s"]),
        min_overlap_fraction=float(vt["min_overlap_fraction"]),
        min_convergence_deg=float(vt["min_convergence_deg"]),
        max_convergence_deg=float(vt["max_convergence_deg"]),
        max_pixel_scale_ratio=float(vt["max_pixel_scale_ratio"]),
        min_solar_elevation_deg=float(vt["min_solar_elevation_deg"]),
        near_nadir_anchor_max_off_nadir_deg=float(
            vt["near_nadir_anchor_max_off_nadir_deg"]
        ),
        pair_weights=dict(qm["pair_weights"]),
        tri_stereo_bonus_by_scene=dict(qm["tri_stereo_bonus_by_scene"]),
    )


def _satellites_from_rows(rows: list[dict[str, Any]]) -> dict[str, SatelliteDef]:
    satellites: dict[str, SatelliteDef] = {}
    for row in rows:
        sat = SatelliteDef(
            sat_id=str(row["id"]),
            norad_catalog_id=int(row["norad_catalog_id"]),
            tle_line1=str(row["tle_line1"]),
            tle_line2=str(row["tle_line2"]),
            pixel_ifov_deg=float(row["pixel_ifov_deg"]),
            cross_track_pixels=int(row["cross_track_pixels"]),
            max_off_nadir_deg=float(row["max_off_nadir_deg"]),
            max_slew_velocity_deg_per_s=float(row["max_slew_velocity_deg_per_s"]),
            max_slew_acceleration_deg_per_s2=float(row["max_slew_acceleration_deg_per_s2"]),
            settling_time_s=float(row["settling_time_s"]),
            min_obs_duration_s=float(row["min_obs_duration_s"]),
            max_obs_duration_s=float(row["max_obs_duration_s"]),
        )
        satellites[sat.sat_id] = sat
    return satellites


def _targets_from_rows(rows: list[dict[str, Any]]) -> dict[str, TargetDef]:
    targets: dict[str, TargetDef] = {}
    for row in rows:
        target = TargetDef(
            target_id=str(row["id"]),
            latitude_deg=float(row["latitude_deg"]),
            longitude_deg=float(row["longitude_deg"]),
            aoi_radius_m=float(row["aoi_radius_m"]),
            elevation_ref_m=float(row["elevation_ref_m"]),
            scene_type=str(row["scene_type"]),
        )
        targets[target.target_id] = target
    return targets


def _iter_samples(start: datetime, end: datetime, *, step_s: float):
    step = timedelta(seconds=step_s)
    current = start
    while current <= end:
        yield current
        current += step


def _limited_samples(samples: list[datetime], limit: int) -> list[datetime]:
    if len(samples) <= limit:
        return samples
    if limit <= 1:
        return [samples[len(samples) // 2]]
    selected: list[datetime] = []
    last_idx = len(samples) - 1
    for idx in range(limit):
        sample_idx = round(idx * last_idx / (limit - 1))
        selected.append(samples[sample_idx])
    return selected


def _pointing_offsets_deg(
    sat_pos_m: np.ndarray,
    sat_vel_mps: np.ndarray,
    target_pos_m: np.ndarray,
) -> tuple[float, float] | None:
    los = target_pos_m - sat_pos_m
    norm = float(np.linalg.norm(los))
    if norm <= 0.0:
        return None
    los_hat = los / norm
    along_hat, across_hat, nadir_hat = _satellite_local_axes(sat_pos_m, sat_vel_mps)
    nadir_component = float(np.dot(los_hat, nadir_hat))
    if nadir_component <= 1.0e-9:
        return None
    along = math_atan_deg(float(np.dot(los_hat, along_hat)) / nadir_component)
    across = math_atan_deg(float(np.dot(los_hat, across_hat)) / nadir_component)
    return along, across


def math_atan_deg(value: float) -> float:
    import math

    return math.degrees(math.atan(value))


def _candidate_window(
    mission: Mission,
    sat_def: SatelliteDef,
    midpoint: datetime,
) -> tuple[datetime, datetime] | None:
    duration = timedelta(seconds=sat_def.min_obs_duration_s)
    start = midpoint - duration / 2
    end = start + duration
    if start < mission.horizon_start:
        start = mission.horizon_start
        end = start + duration
    if end > mission.horizon_end:
        end = mission.horizon_end
        start = end - duration
    if start < mission.horizon_start or end > mission.horizon_end or end <= start:
        return None
    return start, end


def _candidate_observation(
    *,
    sat_id: str,
    target_id: str,
    access_interval_id: str,
    action_index: int,
    mission: Mission,
    sat_def: SatelliteDef,
    sf_sat: EarthSatellite,
    target: TargetDef,
    target_pos: np.ndarray,
    midpoint: datetime,
) -> CandidateObservation | None:
    window = _candidate_window(mission, sat_def, midpoint)
    if window is None:
        return None
    start, end = window
    fine_step_s = _access_interval_sampling_step_s(sat_def)
    if not _access_holds_over_window(
        sf_sat,
        target,
        target_pos,
        sat_def,
        mission,
        start,
        end,
        step_s=fine_step_s,
    ):
        return None

    sat_pos, sat_vel = _satellite_state_ecef_m(sf_sat, _action_midpoint(
        ObservationAction(sat_id, target_id, start, end, 0.0, 0.0)
    ))
    offsets = _pointing_offsets_deg(sat_pos, sat_vel, target_pos)
    if offsets is None:
        return None
    off_along, off_across = offsets
    if _combined_off_nadir_deg(off_along, off_across) > sat_def.max_off_nadir_deg + 1.0e-6:
        return None

    action = ObservationAction(sat_id, target_id, start, end, off_along, off_across)
    mid = _action_midpoint(action)
    sat_pos, sat_vel = _satellite_state_ecef_m(sf_sat, mid)
    slant = float(np.linalg.norm(target_pos - sat_pos))
    epoch = _datetime_to_epoch(mid)
    solar_el, solar_az = _solar_elevation_azimuth_deg(epoch, target_pos)
    derived = DerivedObservation(
        satellite_id=sat_id,
        target_id=target_id,
        action_index=action_index,
        start_time=_iso_z(start),
        end_time=_iso_z(end),
        midpoint_time=_iso_z(mid),
        sat_position_ecef_m=sat_pos.tolist(),
        sat_velocity_ecef_mps=sat_vel.tolist(),
        boresight_off_nadir_deg=float(_combined_off_nadir_deg(off_along, off_across)),
        boresight_azimuth_deg=float(_boresight_azimuth_deg(target_pos, target_pos)),
        solar_elevation_deg=float(solar_el),
        solar_azimuth_deg=float(solar_az),
        effective_pixel_scale_m=slant * math.radians(sat_def.pixel_ifov_deg),
        access_interval_id=access_interval_id,
        slant_range_m=slant,
    )
    return CandidateObservation(action=action, derived=derived)


def _append_access_candidates(
    *,
    samples: list[datetime],
    candidates: list[CandidateObservation],
    sat_id: str,
    target_id: str,
    access_index: int,
    mission: Mission,
    sat_def: SatelliteDef,
    sf_sat: EarthSatellite,
    target: TargetDef,
    target_pos: np.ndarray,
    max_candidates: int,
) -> None:
    if not samples:
        return
    access_interval_id = f"{sat_id}::{target_id}::{access_index}"
    for midpoint in _limited_samples(samples, max_candidates):
        candidate = _candidate_observation(
            sat_id=sat_id,
            target_id=target_id,
            access_interval_id=access_interval_id,
            action_index=len(candidates),
            mission=mission,
            sat_def=sat_def,
            sf_sat=sf_sat,
            target=target,
            target_pos=target_pos,
            midpoint=midpoint,
        )
        if candidate is not None:
            candidates.append(candidate)


def _find_candidate_observations(
    mission: Mission,
    satellites: dict[str, SatelliteDef],
    targets: dict[str, TargetDef],
    sf_sats: dict[str, EarthSatellite],
    target_ecef: dict[str, np.ndarray],
    *,
    access_sample_step_s: float,
    max_candidates_per_access: int,
) -> list[CandidateObservation]:
    candidates: list[CandidateObservation] = []
    for sat_id, sat_def in satellites.items():
        sf_sat = sf_sats[sat_id]
        for target_id, target in targets.items():
            target_pos = target_ecef[target_id]
            current_samples: list[datetime] = []
            access_index = 0
            for instant in _iter_samples(
                mission.horizon_start,
                mission.horizon_end,
                step_s=access_sample_step_s,
            ):
                if _access_predicate(sf_sat, target, target_pos, sat_def, mission, instant):
                    current_samples.append(instant)
                    continue
                _append_access_candidates(
                    samples=current_samples,
                    candidates=candidates,
                    sat_id=sat_id,
                    target_id=target_id,
                    access_index=access_index,
                    mission=mission,
                    sat_def=sat_def,
                    sf_sat=sf_sat,
                    target=target,
                    target_pos=target_pos,
                    max_candidates=max_candidates_per_access,
                )
                if current_samples:
                    access_index += 1
                current_samples = []
            _append_access_candidates(
                samples=current_samples,
                candidates=candidates,
                sat_id=sat_id,
                target_id=target_id,
                access_index=access_index,
                mission=mission,
                sat_def=sat_def,
                sf_sat=sf_sat,
                target=target,
                target_pos=target_pos,
                max_candidates=max_candidates_per_access,
            )
    return candidates


def _find_candidate_observations_for_target(
    mission: Mission,
    satellites: dict[str, SatelliteDef],
    target: TargetDef,
    sf_sats: dict[str, EarthSatellite],
    target_pos: np.ndarray,
    *,
    access_sample_step_s: float,
    max_candidates_per_access: int,
) -> list[CandidateObservation]:
    candidates: list[CandidateObservation] = []
    for sat_id, sat_def in satellites.items():
        sf_sat = sf_sats[sat_id]
        current_samples: list[datetime] = []
        access_index = 0
        for instant in _iter_samples(
            mission.horizon_start,
            mission.horizon_end,
            step_s=access_sample_step_s,
        ):
            if _access_predicate(sf_sat, target, target_pos, sat_def, mission, instant):
                current_samples.append(instant)
                continue
            _append_access_candidates(
                samples=current_samples,
                candidates=candidates,
                sat_id=sat_id,
                target_id=target.target_id,
                access_index=access_index,
                mission=mission,
                sat_def=sat_def,
                sf_sat=sf_sat,
                target=target,
                target_pos=target_pos,
                max_candidates=max_candidates_per_access,
            )
            if current_samples:
                access_index += 1
            current_samples = []
        _append_access_candidates(
            samples=current_samples,
            candidates=candidates,
            sat_id=sat_id,
            target_id=target.target_id,
            access_index=access_index,
            mission=mission,
            sat_def=sat_def,
            sf_sat=sf_sat,
            target=target,
            target_pos=target_pos,
            max_candidates=max_candidates_per_access,
        )
    return candidates


def _same_satellite_actions_feasible(
    first: ObservationAction,
    second: ObservationAction,
    sat_def: SatelliteDef,
    sf_sat: EarthSatellite,
) -> bool:
    a0, a1 = (first, second) if first.start <= second.start else (second, first)
    if a1.start < a0.end:
        return False
    pos0, vel0 = _satellite_state_ecef_m(sf_sat, a0.end)
    pos1, vel1 = _satellite_state_ecef_m(sf_sat, a1.start)
    b0 = _boresight_unit_vector(pos0, vel0, a0.off_nadir_along_deg, a0.off_nadir_across_deg)
    b1 = _boresight_unit_vector(pos1, vel1, a1.off_nadir_along_deg, a1.off_nadir_across_deg)
    delta_deg = _angle_between_deg(b0, b1)
    gap_s = (a1.start - a0.end).total_seconds()
    needed_s = sat_def.settling_time_s + _min_slew_time_s(delta_deg, sat_def)
    return gap_s + 1.0e-6 >= needed_s


def _candidate_pair_diagnostics(candidates: list[CandidateObservation]) -> dict[str, Any]:
    targets_by_sat: dict[str, set[str]] = {}
    for candidate in candidates:
        targets_by_sat.setdefault(candidate.derived.target_id, set()).add(
            candidate.derived.satellite_id
        )
    return {
        "satellites_with_access": sorted({c.derived.satellite_id for c in candidates}),
        "targets_with_candidate_access_by_satellite": {
            target_id: sorted(sat_ids) for target_id, sat_ids in sorted(targets_by_sat.items())
        },
        "candidate_observation_count": len(candidates),
    }


def _evaluate_candidate_pairs(
    *,
    case_id: str,
    mission: Mission,
    satellites: dict[str, SatelliteDef],
    targets: dict[str, TargetDef],
    sf_sats: dict[str, EarthSatellite],
    target_ecef: dict[str, np.ndarray],
    candidates: list[CandidateObservation],
    overlap_samples: int,
) -> FeasibilityAuditResult:
    diagnostics = _candidate_pair_diagnostics(candidates)
    actions = [candidate.action for candidate in candidates]
    derived = [candidate.derived for candidate in candidates]
    by_target: dict[str, list[int]] = {}
    for idx, item in enumerate(derived):
        by_target.setdefault(item.target_id, []).append(idx)

    reject_reasons: Counter[str] = Counter()
    same_satellite_pair_count = 0
    cross_satellite_pair_count = 0
    first_rejection_reason: str | None = None

    for target_id, indices in by_target.items():
        if len(indices) < 2:
            reject_reasons["not_enough_observations_for_target"] += 1
            first_rejection_reason = first_rejection_reason or "not_enough_observations_for_target"
            continue
        for left_pos, left_idx in enumerate(indices):
            for right_idx in indices[left_pos + 1 :]:
                first_action = actions[left_idx]
                second_action = actions[right_idx]
                first_derived = derived[left_idx]
                second_derived = derived[right_idx]
                stereo_mode = _stereo_pair_mode(
                    mission,
                    first_action,
                    second_action,
                    first_derived,
                    second_derived,
                )
                if stereo_mode is None:
                    reject_reasons["policy_or_temporal_bound"] += 1
                    first_rejection_reason = first_rejection_reason or "policy_or_temporal_bound"
                    continue
                if stereo_mode == "same_satellite_same_pass":
                    same_satellite_pair_count += 1
                    if not _same_satellite_actions_feasible(
                        first_action,
                        second_action,
                        satellites[first_derived.satellite_id],
                        sf_sats[first_derived.satellite_id],
                    ):
                        reject_reasons["same_satellite_slew_or_overlap"] += 1
                        first_rejection_reason = (
                            first_rejection_reason or "same_satellite_slew_or_overlap"
                        )
                        continue
                else:
                    cross_satellite_pair_count += 1
                pair = _evaluate_stereo_pair(
                    case_id=case_id,
                    mission=mission,
                    satellites=satellites,
                    targets=targets,
                    sf_sats=sf_sats,
                    target_ecef=target_ecef,
                    actions=actions,
                    first_index=left_idx,
                    second_index=right_idx,
                    first_derived=first_derived,
                    second_derived=second_derived,
                    stereo_mode=stereo_mode,
                    n_samples=overlap_samples,
                    role="generator_feasibility",
                )
                if pair["valid_pair"]:
                    diagnostics.update(
                        {
                            "candidate_same_satellite_pair_count": same_satellite_pair_count,
                            "candidate_cross_satellite_pair_count": cross_satellite_pair_count,
                            "accepted_pair": pair,
                            "rejection_reasons": dict(reject_reasons),
                            "first_rejection_reason": first_rejection_reason,
                            "most_common_rejection_reason": (
                                reject_reasons.most_common(1)[0][0] if reject_reasons else None
                            ),
                        }
                    )
                    return FeasibilityAuditResult(feasible=True, diagnostics=diagnostics)
                reject_reasons["geometry_thresholds"] += 1
                first_rejection_reason = first_rejection_reason or "geometry_thresholds"

    diagnostics.update(
        {
            "candidate_same_satellite_pair_count": same_satellite_pair_count,
            "candidate_cross_satellite_pair_count": cross_satellite_pair_count,
            "rejection_reasons": dict(reject_reasons),
            "first_rejection_reason": first_rejection_reason or "no_candidate_access",
            "most_common_rejection_reason": (
                reject_reasons.most_common(1)[0][0] if reject_reasons else "no_candidate_access"
            ),
        }
    )
    return FeasibilityAuditResult(feasible=False, diagnostics=diagnostics)


def _audit_case_feasibility_streaming(
    *,
    case_id: str,
    mission: Mission,
    satellites: dict[str, SatelliteDef],
    targets: dict[str, TargetDef],
    sf_sats: dict[str, EarthSatellite],
    target_ecef: dict[str, np.ndarray],
    access_sample_step_s: float,
    max_candidates_per_access: int,
    overlap_samples: int,
) -> FeasibilityAuditResult:
    scanned_candidates: list[CandidateObservation] = []
    scanned_targets = 0
    last_report: FeasibilityAuditResult | None = None
    for target_id, target in targets.items():
        scanned_targets += 1
        candidates = _find_candidate_observations_for_target(
            mission,
            satellites,
            target,
            sf_sats,
            target_ecef[target_id],
            access_sample_step_s=access_sample_step_s,
            max_candidates_per_access=max_candidates_per_access,
        )
        scanned_candidates.extend(candidates)
        if len(candidates) < 2:
            continue
        target_report = _evaluate_candidate_pairs(
            case_id=case_id,
            mission=mission,
            satellites=satellites,
            targets=targets,
            sf_sats=sf_sats,
            target_ecef=target_ecef,
            candidates=candidates,
            overlap_samples=overlap_samples,
        )
        last_report = target_report
        if target_report.feasible:
            diagnostics = dict(target_report.diagnostics)
            diagnostics["targets_scanned_before_accept"] = scanned_targets
            diagnostics["candidate_observation_count_before_accept"] = len(scanned_candidates)
            return FeasibilityAuditResult(feasible=True, diagnostics=diagnostics)

    if scanned_candidates:
        return _evaluate_candidate_pairs(
            case_id=case_id,
            mission=mission,
            satellites=satellites,
            targets=targets,
            sf_sats=sf_sats,
            target_ecef=target_ecef,
            candidates=scanned_candidates,
            overlap_samples=overlap_samples,
        )
    if last_report is not None:
        return last_report
    return _evaluate_candidate_pairs(
        case_id=case_id,
        mission=mission,
        satellites=satellites,
        targets=targets,
        sf_sats=sf_sats,
        target_ecef=target_ecef,
        candidates=[],
        overlap_samples=overlap_samples,
    )


def audit_case_feasibility(
    *,
    case_id: str,
    mission_doc: dict[str, Any],
    satellite_rows: list[dict[str, Any]],
    target_rows: list[dict[str, Any]],
    guard_config: dict[str, Any] | None = None,
) -> FeasibilityAuditResult:
    config = {**DEFAULT_FEASIBILITY_GUARD_CONFIG, **(guard_config or {})}
    mission = _mission_from_doc(mission_doc)
    satellites = _satellites_from_rows(satellite_rows)
    targets = _targets_from_rows(target_rows)
    sf_sats = {
        sat_id: EarthSatellite(sat.tle_line1, sat.tle_line2, name=sat_id, ts=_TS)
        for sat_id, sat in satellites.items()
    }
    target_ecef = {target_id: _target_ecef_m(target) for target_id, target in targets.items()}
    if bool(config.get("stop_after_first_feasible", True)):
        return _audit_case_feasibility_streaming(
            case_id=case_id,
            mission=mission,
            satellites=satellites,
            targets=targets,
            sf_sats=sf_sats,
            target_ecef=target_ecef,
            access_sample_step_s=float(config["access_sample_step_s"]),
            max_candidates_per_access=int(config["max_candidate_observations_per_access"]),
            overlap_samples=int(config["overlap_samples"]),
        )
    candidates = _find_candidate_observations(
        mission,
        satellites,
        targets,
        sf_sats,
        target_ecef,
        access_sample_step_s=float(config["access_sample_step_s"]),
        max_candidates_per_access=int(config["max_candidate_observations_per_access"]),
    )
    return _evaluate_candidate_pairs(
        case_id=case_id,
        mission=mission,
        satellites=satellites,
        targets=targets,
        sf_sats=sf_sats,
        target_ecef=target_ecef,
        candidates=candidates,
        overlap_samples=int(config["overlap_samples"]),
    )


def format_feasibility_diagnostics(diagnostics: dict[str, Any]) -> str:
    return (
        f"satellites_with_access={diagnostics.get('satellites_with_access', [])}; "
        f"targets_with_candidate_access={len(diagnostics.get('targets_with_candidate_access_by_satellite', {}))}; "
        f"candidate_observations={diagnostics.get('candidate_observation_count', 0)}; "
        f"same_satellite_pairs={diagnostics.get('candidate_same_satellite_pair_count', 0)}; "
        f"cross_satellite_pairs={diagnostics.get('candidate_cross_satellite_pair_count', 0)}; "
        f"most_common_rejection={diagnostics.get('most_common_rejection_reason')}"
    )


__all__ = [
    "CandidateObservation",
    "DEFAULT_FEASIBILITY_GUARD_CONFIG",
    "FeasibilityAuditResult",
    "audit_case_feasibility",
    "format_feasibility_diagnostics",
]
