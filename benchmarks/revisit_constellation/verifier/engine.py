"""Core verification logic for the revisit_constellation benchmark."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
import math

import brahe
import numpy as np

from .models import (
    ACTION_SAMPLE_STEP_SEC,
    NUMERICAL_EPS,
    RESOURCE_STEP_SEC,
    Action,
    AttitudeModel,
    Instance,
    ManeuverWindow,
    ObservationRecord,
    Solution,
    Target,
    GroundStation,
    VerificationResult,
)
from .io import load_case, load_solution


BRAHE_EOP_INITIALIZED = False


def _ensure_brahe_ready() -> None:
    global BRAHE_EOP_INITIALIZED
    if BRAHE_EOP_INITIALIZED:
        return

    # Use a static zero-valued EOP provider so the verifier stays deterministic
    # and offline-friendly during early benchmark development.
    brahe.set_global_eop_provider_from_static_provider(
        brahe.StaticEOPProvider.from_zero()
    )
    BRAHE_EOP_INITIALIZED = True


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


def _isoformat_z(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _angle_between_deg(vector_a: np.ndarray, vector_b: np.ndarray) -> float:
    norm_a = np.linalg.norm(vector_a)
    norm_b = np.linalg.norm(vector_b)
    if norm_a < NUMERICAL_EPS or norm_b < NUMERICAL_EPS:
        return 0.0
    cosine = float(np.dot(vector_a, vector_b) / (norm_a * norm_b))
    cosine = max(-1.0, min(1.0, cosine))
    return math.degrees(math.acos(cosine))


def _observation_midpoint(action: Action) -> datetime:
    return action.start + ((action.end - action.start) / 2)


def _initial_altitude_m(state_eci_m_mps: np.ndarray) -> float:
    return float(np.linalg.norm(state_eci_m_mps[:3]) - brahe.R_EARTH)


def _sample_times(start: datetime, end: datetime, step_sec: float) -> list[datetime]:
    if end <= start:
        return [start]
    points = [start]
    current = start
    delta = timedelta(seconds=step_sec)
    while current + delta < end:
        current = current + delta
        points.append(current)
    if points[-1] != end:
        points.append(end)
    return points


def _interval_contains(instant: datetime, start: datetime, end: datetime) -> bool:
    return start <= instant < end


def _is_sunlit(position_eci_m: np.ndarray, epoch: brahe.Epoch) -> bool:
    sun_position = np.asarray(brahe.sun_position(epoch), dtype=float)
    sun_hat = sun_position / np.linalg.norm(sun_position)
    projection = float(np.dot(position_eci_m, sun_hat))
    perpendicular = np.linalg.norm(position_eci_m - (projection * sun_hat))
    return not (projection < 0.0 and perpendicular < brahe.R_EARTH)


def _slew_time_sec(angle_deg: float, attitude_model: AttitudeModel) -> float:
    angle_deg = max(0.0, angle_deg)
    if angle_deg <= NUMERICAL_EPS:
        return 0.0

    max_velocity = attitude_model.max_slew_velocity_deg_per_sec
    max_accel = attitude_model.max_slew_acceleration_deg_per_sec2
    if max_velocity <= 0.0 or max_accel <= 0.0:
        return math.inf

    ramp_time = max_velocity / max_accel
    triangular_threshold = (max_velocity * max_velocity) / max_accel
    if angle_deg <= triangular_threshold:
        return 2.0 * math.sqrt(angle_deg / max_accel)
    cruise_angle = angle_deg - triangular_threshold
    return (2.0 * ramp_time) + (cruise_angle / max_velocity)


def _build_propagators(
    instance: Instance, solution: Solution
) -> dict[str, brahe.NumericalOrbitPropagator]:
    epoch = _datetime_to_epoch(instance.horizon_start)
    end_epoch = _datetime_to_epoch(instance.horizon_end)
    force_config = brahe.ForceModelConfig(
        gravity=brahe.GravityConfiguration.spherical_harmonic(2, 0)
    )

    propagators: dict[str, brahe.NumericalOrbitPropagator] = {}
    for satellite in solution.satellites.values():
        propagator = brahe.NumericalOrbitPropagator.from_eci(
            epoch, satellite.state_eci_m_mps, force_config=force_config
        )
        propagator.propagate_to(end_epoch)
        propagators[satellite.satellite_id] = propagator
    return propagators


def _validate_satellites(
    instance: Instance, solution: Solution, errors: list[str]
) -> None:
    if len(solution.satellites) > instance.max_num_satellites:
        errors.append(
            f"Solution defines {len(solution.satellites)} satellites but the case allows at most "
            f"{instance.max_num_satellites}"
        )

    for satellite in solution.satellites.values():
        altitude_m = _initial_altitude_m(satellite.state_eci_m_mps)
        if altitude_m < instance.satellite_model.min_altitude_m - NUMERICAL_EPS:
            errors.append(
                f"Satellite {satellite.satellite_id} starts below min altitude: "
                f"{altitude_m:.3f} m < {instance.satellite_model.min_altitude_m:.3f} m"
            )
        if altitude_m > instance.satellite_model.max_altitude_m + NUMERICAL_EPS:
            errors.append(
                f"Satellite {satellite.satellite_id} starts above max altitude: "
                f"{altitude_m:.3f} m > {instance.satellite_model.max_altitude_m:.3f} m"
            )


def _validate_action_structure(
    instance: Instance, solution: Solution, errors: list[str]
) -> dict[str, list[Action]]:
    actions_by_satellite: dict[str, list[Action]] = defaultdict(list)

    for index, action in enumerate(solution.actions):
        label = f"action[{index}]"
        if action.satellite_id not in solution.satellites:
            errors.append(f"{label} references unknown satellite_id {action.satellite_id!r}")
            continue
        if action.end <= action.start:
            errors.append(f"{label} must satisfy end > start")
        if action.start < instance.horizon_start or action.end > instance.horizon_end:
            errors.append(
                f"{label} lies outside the mission horizon: "
                f"{_isoformat_z(action.start)} to {_isoformat_z(action.end)}"
            )
        if action.action_type == "observation":
            if not action.target_id:
                errors.append(f"{label} observation is missing target_id")
            elif action.target_id not in instance.targets:
                errors.append(f"{label} references unknown target_id {action.target_id!r}")
            if action.station_id is not None:
                errors.append(f"{label} observation must not include station_id")
        elif action.action_type == "downlink":
            if not action.station_id:
                errors.append(f"{label} downlink is missing station_id")
            elif action.station_id not in instance.ground_stations:
                errors.append(f"{label} references unknown station_id {action.station_id!r}")
            if action.target_id is not None:
                errors.append(f"{label} downlink must not include target_id")
        else:
            errors.append(
                f"{label} has unsupported action_type {action.action_type!r}; "
                "expected 'observation' or 'downlink'"
            )
        actions_by_satellite[action.satellite_id].append(action)

    for satellite_id, actions in actions_by_satellite.items():
        actions.sort(key=lambda item: (item.start, item.end, item.action_type))
        for previous, current in zip(actions, actions[1:]):
            if previous.end <= current.start:
                continue
            if previous.action_type == "downlink" and current.action_type == "downlink":
                continue
            errors.append(
                f"Satellite {satellite_id} has overlapping non-downlink-compatible actions: "
                f"{previous.action_type} {_isoformat_z(previous.start)}-{_isoformat_z(previous.end)} "
                f"overlaps {current.action_type} {_isoformat_z(current.start)}-{_isoformat_z(current.end)}"
            )

    return actions_by_satellite


def _observation_geometry_ok(
    instance: Instance,
    target: Target,
    state_eci_m_mps: np.ndarray,
    state_ecef_m_mps: np.ndarray,
    epoch: brahe.Epoch,
) -> tuple[bool, str | None]:
    sensor = instance.satellite_model.sensor
    relative_enz = np.asarray(
        brahe.relative_position_ecef_to_enz(
            target.ecef_position_m,
            state_ecef_m_mps[:3],
            brahe.EllipsoidalConversionType.GEODETIC,
        ),
        dtype=float,
    )
    azimuth_elevation_range = np.asarray(
        brahe.position_enz_to_azel(relative_enz, brahe.AngleFormat.DEGREES),
        dtype=float,
    )
    elevation_deg = float(azimuth_elevation_range[1])
    slant_range_m = float(azimuth_elevation_range[2])

    if elevation_deg < target.min_elevation_deg - NUMERICAL_EPS:
        return (
            False,
            f"elevation {elevation_deg:.3f} deg below target minimum {target.min_elevation_deg:.3f} deg",
        )
    if slant_range_m > target.max_slant_range_m + NUMERICAL_EPS:
        return (
            False,
            f"slant range {slant_range_m:.3f} m exceeds target limit {target.max_slant_range_m:.3f} m",
        )
    if slant_range_m > sensor.max_range_m + NUMERICAL_EPS:
        return (
            False,
            f"slant range {slant_range_m:.3f} m exceeds sensor max range {sensor.max_range_m:.3f} m",
        )

    target_eci_m = np.asarray(
        brahe.position_ecef_to_eci(epoch, target.ecef_position_m),
        dtype=float,
    )
    line_of_sight = target_eci_m - state_eci_m_mps[:3]
    nadir = -state_eci_m_mps[:3]
    off_nadir_deg = _angle_between_deg(nadir, line_of_sight)
    if off_nadir_deg > sensor.field_of_view_half_angle_deg + NUMERICAL_EPS:
        return (
            False,
            f"off-nadir angle {off_nadir_deg:.3f} deg exceeds sensor half FOV "
            f"{sensor.field_of_view_half_angle_deg:.3f} deg",
        )

    return True, None


def _downlink_geometry_ok(
    station: GroundStation, state_ecef_m_mps: np.ndarray
) -> tuple[bool, str | None]:
    relative_enz = np.asarray(
        brahe.relative_position_ecef_to_enz(
            station.ecef_position_m,
            state_ecef_m_mps[:3],
            brahe.EllipsoidalConversionType.GEODETIC,
        ),
        dtype=float,
    )
    azimuth_elevation_range = np.asarray(
        brahe.position_enz_to_azel(relative_enz, brahe.AngleFormat.DEGREES),
        dtype=float,
    )
    elevation_deg = float(azimuth_elevation_range[1])
    if elevation_deg < station.min_elevation_deg - NUMERICAL_EPS:
        return (
            False,
            f"elevation {elevation_deg:.3f} deg below station minimum {station.min_elevation_deg:.3f} deg",
        )
    return True, None


def _validate_action_geometry(
    instance: Instance,
    actions_by_satellite: dict[str, list[Action]],
    propagators: dict[str, brahe.NumericalOrbitPropagator],
    errors: list[str],
) -> list[ObservationRecord]:
    successful_observations: list[ObservationRecord] = []

    for satellite_id, actions in actions_by_satellite.items():
        propagator = propagators[satellite_id]
        for action in actions:
            sample_times = _sample_times(action.start, action.end, ACTION_SAMPLE_STEP_SEC)
            if action.action_type == "observation":
                target = instance.targets[action.target_id or ""]
                if action.duration_sec < target.min_duration_sec - NUMERICAL_EPS:
                    errors.append(
                        f"Observation for target {target.target_id} on {satellite_id} lasts "
                        f"{action.duration_sec:.3f} sec but requires at least "
                        f"{target.min_duration_sec:.3f} sec"
                    )
                    continue
                valid = True
                for sample in sample_times:
                    epoch = _datetime_to_epoch(sample)
                    state_eci = np.asarray(propagator.state_eci(epoch), dtype=float)
                    state_ecef = np.asarray(propagator.state_ecef(epoch), dtype=float)
                    ok, reason = _observation_geometry_ok(
                        instance, target, state_eci, state_ecef, epoch
                    )
                    if not ok:
                        errors.append(
                            f"Observation for target {target.target_id} on {satellite_id} is infeasible at "
                            f"{_isoformat_z(sample)}: {reason}"
                        )
                        valid = False
                        break
                if valid:
                    successful_observations.append(
                        ObservationRecord(
                            satellite_id=satellite_id,
                            target_id=target.target_id,
                            start=action.start,
                            end=action.end,
                            midpoint=_observation_midpoint(action),
                        )
                    )
            else:
                station = instance.ground_stations[action.station_id or ""]
                if action.duration_sec < station.min_duration_sec - NUMERICAL_EPS:
                    errors.append(
                        f"Downlink to station {station.station_id} on {satellite_id} lasts "
                        f"{action.duration_sec:.3f} sec but requires at least "
                        f"{station.min_duration_sec:.3f} sec"
                    )
                    continue
                for sample in sample_times:
                    epoch = _datetime_to_epoch(sample)
                    state_ecef = np.asarray(propagator.state_ecef(epoch), dtype=float)
                    ok, reason = _downlink_geometry_ok(station, state_ecef)
                    if not ok:
                        errors.append(
                            f"Downlink to station {station.station_id} on {satellite_id} is infeasible at "
                            f"{_isoformat_z(sample)}: {reason}"
                        )
                        break

    return successful_observations


def _target_vector_eci(
    target: Target, propagator: brahe.NumericalOrbitPropagator, instant: datetime
) -> np.ndarray:
    epoch = _datetime_to_epoch(instant)
    satellite_state_eci = np.asarray(propagator.state_eci(epoch), dtype=float)
    target_eci = np.asarray(
        brahe.position_ecef_to_eci(epoch, target.ecef_position_m),
        dtype=float,
    )
    return target_eci - satellite_state_eci[:3]


def _build_maneuver_windows(
    instance: Instance,
    actions_by_satellite: dict[str, list[Action]],
    propagators: dict[str, brahe.NumericalOrbitPropagator],
    errors: list[str],
) -> dict[str, list[ManeuverWindow]]:
    maneuver_windows: dict[str, list[ManeuverWindow]] = defaultdict(list)
    attitude_model = instance.satellite_model.attitude_model

    for satellite_id, actions in actions_by_satellite.items():
        observation_actions = [
            action for action in actions if action.action_type == "observation"
        ]
        observation_actions.sort(key=lambda action: action.start)
        propagator = propagators[satellite_id]

        for previous, current in zip(observation_actions, observation_actions[1:]):
            previous_target = instance.targets[previous.target_id or ""]
            current_target = instance.targets[current.target_id or ""]

            previous_vector = _target_vector_eci(
                previous_target, propagator, _observation_midpoint(previous)
            )
            current_vector = _target_vector_eci(
                current_target, propagator, _observation_midpoint(current)
            )
            slew_angle_deg = _angle_between_deg(previous_vector, current_vector)
            required_gap_sec = _slew_time_sec(
                slew_angle_deg, attitude_model
            ) + attitude_model.settling_time_sec
            actual_gap_sec = (current.start - previous.end).total_seconds()

            if actual_gap_sec + NUMERICAL_EPS < required_gap_sec:
                errors.append(
                    f"Satellite {satellite_id} needs {required_gap_sec:.3f} sec between observations "
                    f"but only has {actual_gap_sec:.3f} sec between {_isoformat_z(previous.end)} and "
                    f"{_isoformat_z(current.start)}"
                )
                continue

            window_start = current.start - timedelta(seconds=required_gap_sec)
            window = ManeuverWindow(
                satellite_id=satellite_id,
                start=window_start,
                end=current.start,
            )

            for action in actions:
                if action is previous or action is current:
                    continue
                if action.start < window.end and action.end > window.start:
                    errors.append(
                        f"Satellite {satellite_id} has action overlap with required maneuver/settling "
                        f"window before observation at {_isoformat_z(current.start)}"
                    )
                    break
            maneuver_windows[satellite_id].append(window)

    return maneuver_windows


def _validate_downlink_concurrency(
    instance: Instance,
    actions_by_satellite: dict[str, list[Action]],
    errors: list[str],
) -> None:
    terminal_count = instance.satellite_model.terminal_count
    for satellite_id, actions in actions_by_satellite.items():
        downlinks = [action for action in actions if action.action_type == "downlink"]
        if not downlinks:
            continue

        time_points = sorted(
            {
                instant
                for action in downlinks
                for instant in (action.start, action.end)
            }
        )
        for start, end in zip(time_points, time_points[1:]):
            if end <= start:
                continue
            midpoint = start + ((end - start) / 2)
            concurrent_count = sum(
                1
                for action in downlinks
                if _interval_contains(midpoint, action.start, action.end)
            )
            if concurrent_count > terminal_count:
                errors.append(
                    f"Satellite {satellite_id} uses {concurrent_count} simultaneous downlinks but only "
                    f"{terminal_count} terminals are available"
                )
                break


def _simulate_resources(
    instance: Instance,
    actions_by_satellite: dict[str, list[Action]],
    maneuver_windows: dict[str, list[ManeuverWindow]],
    propagators: dict[str, brahe.NumericalOrbitPropagator],
    errors: list[str],
) -> None:
    resource = instance.satellite_model.resource_model
    sensor = instance.satellite_model.sensor
    terminal = instance.satellite_model.terminal_profile
    attitude = instance.satellite_model.attitude_model

    for satellite_id, propagator in propagators.items():
        actions = actions_by_satellite.get(satellite_id, [])
        maneuvers = maneuver_windows.get(satellite_id, [])
        time_points = {
            instance.horizon_start,
            instance.horizon_end,
        }

        current = instance.horizon_start
        step_delta = timedelta(seconds=RESOURCE_STEP_SEC)
        while current < instance.horizon_end:
            time_points.add(current)
            current = min(current + step_delta, instance.horizon_end)
        time_points.add(instance.horizon_end)

        for action in actions:
            time_points.add(action.start)
            time_points.add(action.end)
        for maneuver in maneuvers:
            time_points.add(maneuver.start)
            time_points.add(maneuver.end)

        battery_wh = resource.initial_battery_wh
        storage_mb = resource.initial_storage_mb

        sorted_points = sorted(time_points)
        for start, end in zip(sorted_points, sorted_points[1:]):
            duration_sec = (end - start).total_seconds()
            if duration_sec <= 0.0:
                continue

            midpoint = start + ((end - start) / 2)
            epoch = _datetime_to_epoch(midpoint)
            state_eci = np.asarray(propagator.state_eci(epoch), dtype=float)

            active_observation = next(
                (
                    action
                    for action in actions
                    if action.action_type == "observation"
                    and _interval_contains(midpoint, action.start, action.end)
                ),
                None,
            )
            active_downlinks = [
                action
                for action in actions
                if action.action_type == "downlink"
                and _interval_contains(midpoint, action.start, action.end)
            ]
            active_maneuver = any(
                _interval_contains(midpoint, maneuver.start, maneuver.end)
                for maneuver in maneuvers
            )

            discharge_w = resource.idle_discharge_rate_w
            storage_rate_mb_per_s = 0.0

            if active_observation is not None:
                discharge_w += sensor.obs_discharge_rate_w
                storage_rate_mb_per_s += sensor.obs_store_rate_mb_per_s
            if active_downlinks:
                discharge_w += len(active_downlinks) * terminal.downlink_discharge_rate_w
                storage_rate_mb_per_s -= (
                    len(active_downlinks) * terminal.downlink_release_rate_mb_per_s
                )
            if active_maneuver:
                discharge_w += attitude.maneuver_discharge_rate_w

            charge_w = (
                resource.sunlight_charge_rate_w if _is_sunlit(state_eci[:3], epoch) else 0.0
            )

            battery_wh += ((charge_w - discharge_w) * duration_sec) / 3600.0
            storage_mb += storage_rate_mb_per_s * duration_sec

            if battery_wh < -NUMERICAL_EPS:
                errors.append(
                    f"Satellite {satellite_id} depletes battery below zero around {_isoformat_z(midpoint)}"
                )
                break
            if storage_mb < -NUMERICAL_EPS:
                errors.append(
                    f"Satellite {satellite_id} depletes storage below zero around {_isoformat_z(midpoint)}"
                )
                break
            if storage_mb > resource.storage_capacity_mb + NUMERICAL_EPS:
                errors.append(
                    f"Satellite {satellite_id} exceeds storage capacity around {_isoformat_z(midpoint)}"
                )
                break

            battery_wh = min(resource.battery_capacity_wh, battery_wh)
            storage_mb = max(0.0, storage_mb)


def _compute_metrics(
    instance: Instance, successful_observations: list[ObservationRecord], satellite_count: int
) -> dict[str, Any]:
    observations_by_target: dict[str, list[datetime]] = defaultdict(list)
    for observation in successful_observations:
        observations_by_target[observation.target_id].append(observation.midpoint)

    target_gap_summary: dict[str, dict[str, float]] = {}
    target_mean_gaps: list[float] = []
    target_max_gaps: list[float] = []

    for target_id, target in instance.targets.items():
        midpoints = sorted(observations_by_target.get(target_id, []))
        times = [instance.horizon_start, *midpoints, instance.horizon_end]
        gaps_hours = [
            (right - left).total_seconds() / 3600.0
            for left, right in zip(times, times[1:])
        ]
        mean_gap = sum(gaps_hours) / len(gaps_hours)
        max_gap = max(gaps_hours)
        target_gap_summary[target_id] = {
            "mean_revisit_gap_hours": mean_gap,
            "max_revisit_gap_hours": max_gap,
            "observation_count": len(midpoints),
            "expected_revisit_period_hours": target.expected_revisit_period_hours,
        }
        target_mean_gaps.append(mean_gap)
        target_max_gaps.append(max_gap)

    threshold_satisfied = all(
        target_gap_summary[target_id]["max_revisit_gap_hours"]
        <= instance.targets[target_id].expected_revisit_period_hours + NUMERICAL_EPS
        for target_id in instance.targets
    )

    return {
        "mean_revisit_gap_hours": (
            sum(target_mean_gaps) / len(target_mean_gaps) if target_mean_gaps else 0.0
        ),
        "max_revisit_gap_hours": max(target_max_gaps) if target_max_gaps else 0.0,
        "satellite_count": satellite_count,
        "threshold_satisfied": threshold_satisfied,
        "target_gap_summary": target_gap_summary,
    }


def verify(instance: Instance, solution: Solution) -> VerificationResult:
    _ensure_brahe_ready()

    errors: list[str] = []
    warnings: list[str] = []

    _validate_satellites(instance, solution, errors)
    actions_by_satellite = _validate_action_structure(instance, solution, errors)
    if errors:
        return VerificationResult(is_valid=False, errors=errors, warnings=warnings)

    propagators = _build_propagators(instance, solution)
    successful_observations = _validate_action_geometry(
        instance, actions_by_satellite, propagators, errors
    )
    maneuver_windows = _build_maneuver_windows(
        instance, actions_by_satellite, propagators, errors
    )
    _validate_downlink_concurrency(instance, actions_by_satellite, errors)
    if errors:
        return VerificationResult(is_valid=False, errors=errors, warnings=warnings)

    _simulate_resources(
        instance, actions_by_satellite, maneuver_windows, propagators, errors
    )
    if errors:
        return VerificationResult(is_valid=False, errors=errors, warnings=warnings)

    metrics = _compute_metrics(instance, successful_observations, len(solution.satellites))
    return VerificationResult(
        is_valid=True,
        metrics=metrics,
        errors=errors,
        warnings=warnings,
    )


def verify_solution(case_dir: str | Path, solution_path: str | Path) -> VerificationResult:
    instance = load_case(case_dir)
    solution = load_solution(solution_path)
    return verify(instance, solution)
