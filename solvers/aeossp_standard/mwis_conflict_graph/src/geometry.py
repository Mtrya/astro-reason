"""Solver-local AEOSSP geometry and first-action slew helpers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import math

import brahe
import numpy as np

from .case_io import Mission, NUMERICAL_EPS, Satellite, Task


_BRAHE_READY = False


class PropagationContext:
    def __init__(self, satellites: dict[str, Satellite], step_s: float):
        ensure_brahe_ready()
        self.propagators = {
            satellite_id: brahe.SGPPropagator.from_tle(
                satellite.tle_line1,
                satellite.tle_line2,
                step_s,
            )
            for satellite_id, satellite in satellites.items()
        }
        self._eci_cache: dict[tuple[str, datetime], np.ndarray] = {}
        self._ecef_cache: dict[tuple[str, datetime], np.ndarray] = {}
        self._target_ecef_cache: dict[str, np.ndarray] = {}
        self._target_eci_cache: dict[tuple[str, datetime], np.ndarray] = {}
        self._target_vector_cache: dict[tuple[str, str, datetime], np.ndarray] = {}
        self._cache_stats = {
            "state_eci_hits": 0,
            "state_eci_misses": 0,
            "state_ecef_hits": 0,
            "state_ecef_misses": 0,
            "target_ecef_hits": 0,
            "target_ecef_misses": 0,
            "target_eci_hits": 0,
            "target_eci_misses": 0,
            "target_vector_eci_hits": 0,
            "target_vector_eci_misses": 0,
        }

    def state_eci(self, satellite_id: str, instant: datetime) -> np.ndarray:
        key = (satellite_id, instant.astimezone(UTC))
        state = self._eci_cache.get(key)
        if state is not None:
            self._cache_stats["state_eci_hits"] += 1
            return state
        self._cache_stats["state_eci_misses"] += 1
        state = np.asarray(
            self.propagators[satellite_id].state_eci(datetime_to_epoch(key[1])),
            dtype=float,
        ).reshape(6)
        self._eci_cache[key] = state
        return state

    def state_ecef(self, satellite_id: str, instant: datetime) -> np.ndarray:
        key = (satellite_id, instant.astimezone(UTC))
        state = self._ecef_cache.get(key)
        if state is not None:
            self._cache_stats["state_ecef_hits"] += 1
            return state
        self._cache_stats["state_ecef_misses"] += 1
        state = np.asarray(
            self.propagators[satellite_id].state_ecef(datetime_to_epoch(key[1])),
            dtype=float,
        ).reshape(6)
        self._ecef_cache[key] = state
        return state

    def target_ecef_array(self, task: Task) -> np.ndarray:
        target = self._target_ecef_cache.get(task.task_id)
        if target is not None:
            self._cache_stats["target_ecef_hits"] += 1
            return target
        self._cache_stats["target_ecef_misses"] += 1
        target = np.asarray(task.target_ecef_m, dtype=float)
        self._target_ecef_cache[task.task_id] = target
        return target

    def target_eci(self, task: Task, instant: datetime) -> np.ndarray:
        key = (task.task_id, instant.astimezone(UTC))
        target = self._target_eci_cache.get(key)
        if target is not None:
            self._cache_stats["target_eci_hits"] += 1
            return target
        self._cache_stats["target_eci_misses"] += 1
        target = np.asarray(
            brahe.position_ecef_to_eci(
                datetime_to_epoch(key[1]),
                self.target_ecef_array(task),
            ),
            dtype=float,
        ).reshape(3)
        self._target_eci_cache[key] = target
        return target

    def target_vector_eci(
        self,
        task: Task,
        satellite_id: str,
        instant: datetime,
    ) -> np.ndarray:
        key = (satellite_id, task.task_id, instant.astimezone(UTC))
        vector = self._target_vector_cache.get(key)
        if vector is not None:
            self._cache_stats["target_vector_eci_hits"] += 1
            return vector
        self._cache_stats["target_vector_eci_misses"] += 1
        vector = self.target_eci(task, key[2]) - self.state_eci(satellite_id, key[2])[:3]
        self._target_vector_cache[key] = vector
        return vector

    def cache_summary(self) -> dict[str, int]:
        return {
            **self._cache_stats,
            "state_eci_entries": len(self._eci_cache),
            "state_ecef_entries": len(self._ecef_cache),
            "target_ecef_entries": len(self._target_ecef_cache),
            "target_eci_entries": len(self._target_eci_cache),
            "target_vector_eci_entries": len(self._target_vector_cache),
        }


def ensure_brahe_ready() -> None:
    global _BRAHE_READY
    if _BRAHE_READY:
        return
    brahe.set_global_eop_provider_from_static_provider(
        brahe.StaticEOPProvider.from_zero()
    )
    _BRAHE_READY = True


def datetime_to_epoch(value: datetime) -> brahe.Epoch:
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


def action_sample_times(
    mission: Mission,
    start_time: datetime,
    end_time: datetime,
) -> list[datetime]:
    if end_time <= start_time:
        return [start_time]
    points = [start_time]
    step_s = mission.geometry_sample_step_s
    start_offset_s = int(round((start_time - mission.horizon_start).total_seconds()))
    end_offset_s = int(round((end_time - mission.horizon_start).total_seconds()))
    next_grid_offset_s = ((start_offset_s // step_s) + 1) * step_s
    while next_grid_offset_s < end_offset_s:
        points.append(mission.horizon_start + timedelta(seconds=next_grid_offset_s))
        next_grid_offset_s += step_s
    if points[-1] != end_time:
        points.append(end_time)
    return points


def angle_between_deg(vector_a: np.ndarray, vector_b: np.ndarray) -> float:
    norm_a = float(np.linalg.norm(vector_a))
    norm_b = float(np.linalg.norm(vector_b))
    if norm_a <= NUMERICAL_EPS or norm_b <= NUMERICAL_EPS:
        return 0.0
    cosine = float(np.dot(vector_a, vector_b) / (norm_a * norm_b))
    cosine = max(-1.0, min(1.0, cosine))
    return math.degrees(math.acos(cosine))


def slew_time_s(
    delta_angle_deg: float,
    max_velocity_deg_per_s: float,
    max_acceleration_deg_per_s2: float,
) -> float:
    delta_angle_deg = max(0.0, delta_angle_deg)
    if delta_angle_deg <= NUMERICAL_EPS:
        return 0.0
    if max_velocity_deg_per_s <= 0.0 or max_acceleration_deg_per_s2 <= 0.0:
        return math.inf
    ramp_time = max_velocity_deg_per_s / max_acceleration_deg_per_s2
    triangular_threshold = (
        max_velocity_deg_per_s * max_velocity_deg_per_s / max_acceleration_deg_per_s2
    )
    if delta_angle_deg <= triangular_threshold:
        return 2.0 * math.sqrt(delta_angle_deg / max_acceleration_deg_per_s2)
    cruise_angle = delta_angle_deg - triangular_threshold
    return (2.0 * ramp_time) + (cruise_angle / max_velocity_deg_per_s)


def required_slew_settle_s(
    delta_angle_deg: float,
    satellite: Satellite,
) -> float:
    return slew_time_s(
        delta_angle_deg,
        satellite.attitude_model.max_slew_velocity_deg_per_s,
        satellite.attitude_model.max_slew_acceleration_deg_per_s2,
    ) + satellite.attitude_model.settling_time_s


def initial_slew_feasible_from_vectors(
    *,
    nadir_vector_eci: np.ndarray,
    target_vector_eci: np.ndarray,
    available_gap_s: float,
    satellite: Satellite,
) -> bool:
    slew_angle_deg = angle_between_deg(nadir_vector_eci, target_vector_eci)
    return available_gap_s + NUMERICAL_EPS >= required_slew_settle_s(
        slew_angle_deg,
        satellite,
    )


def target_vector_eci(
    task: Task,
    propagation: PropagationContext,
    satellite_id: str,
    instant: datetime,
) -> np.ndarray:
    return propagation.target_vector_eci(task, satellite_id, instant)


def off_nadir_deg(
    satellite_position_ecef_m: np.ndarray,
    target_ecef_m: np.ndarray,
) -> float:
    return angle_between_deg(
        -satellite_position_ecef_m,
        target_ecef_m - satellite_position_ecef_m,
    )


def target_visible(
    satellite_position_ecef_m: np.ndarray,
    target_ecef_m: np.ndarray,
) -> bool:
    target_norm = float(np.linalg.norm(target_ecef_m))
    if target_norm <= NUMERICAL_EPS:
        return False
    target_normal = target_ecef_m / target_norm
    return float(np.dot(satellite_position_ecef_m - target_ecef_m, target_normal)) > 0.0


def observation_geometry_valid(
    *,
    mission: Mission,
    satellite: Satellite,
    task: Task,
    propagation: PropagationContext,
    start_time: datetime,
    end_time: datetime,
) -> bool:
    target_ecef_m = propagation.target_ecef_array(task)
    for sample_time in action_sample_times(mission, start_time, end_time):
        sat_pos_ecef = propagation.state_ecef(satellite.satellite_id, sample_time)[:3]
        if not target_visible(sat_pos_ecef, target_ecef_m):
            return False
        if (
            off_nadir_deg(sat_pos_ecef, target_ecef_m)
            > satellite.attitude_model.max_off_nadir_deg + 1.0e-6
        ):
            return False
    return True


def initial_slew_feasible(
    *,
    mission: Mission,
    satellite: Satellite,
    task: Task,
    propagation: PropagationContext,
    start_time: datetime,
) -> bool:
    sat_state_eci = propagation.state_eci(satellite.satellite_id, start_time)
    return initial_slew_feasible_from_vectors(
        nadir_vector_eci=-sat_state_eci[:3],
        target_vector_eci=target_vector_eci(
            task,
            propagation,
            satellite.satellite_id,
            start_time,
        ),
        available_gap_s=(start_time - mission.horizon_start).total_seconds(),
        satellite=satellite,
    )
