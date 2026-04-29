"""Standalone Brahe propagation helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import brahe
import numpy as np

from .case_io import RevisitCase
from .orbit_library import OrbitCandidate
from .rgt import closure_score_from_geocentric


_BRAHE_READY = False


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


@dataclass(frozen=True, slots=True)
class CandidateStateGrid:
    candidate_id: str
    sample_times: tuple[datetime, ...]
    eci_states: np.ndarray
    ecef_states: np.ndarray


class PropagationCache:
    def __init__(self, candidates: list[OrbitCandidate], start: datetime, end: datetime):
        ensure_brahe_ready()
        start_epoch = datetime_to_epoch(start)
        end_epoch = datetime_to_epoch(end)
        force_config = brahe.ForceModelConfig(
            gravity=brahe.GravityConfiguration.spherical_harmonic(2, 0)
        )
        self._propagators: dict[str, brahe.NumericalOrbitPropagator] = {}
        for candidate in candidates:
            propagator = brahe.NumericalOrbitPropagator.from_eci(
                start_epoch,
                np.asarray(candidate.state_eci_m_mps, dtype=float),
                force_config=force_config,
            )
            propagator.propagate_to(end_epoch)
            self._propagators[candidate.candidate_id] = propagator
        self._eci_cache: dict[tuple[str, datetime], np.ndarray] = {}
        self._ecef_cache: dict[tuple[str, datetime], np.ndarray] = {}
        self._state_grid_cache: dict[
            tuple[str, tuple[datetime, ...]], CandidateStateGrid
        ] = {}

    def state_eci(self, candidate_id: str, instant: datetime) -> np.ndarray:
        key = (candidate_id, instant.astimezone(UTC))
        state = self._eci_cache.get(key)
        if state is None:
            state = np.asarray(
                self._propagators[candidate_id].state_eci(datetime_to_epoch(key[1])),
                dtype=float,
            ).reshape(6)
            self._eci_cache[key] = state
        return state

    def state_ecef(self, candidate_id: str, instant: datetime) -> np.ndarray:
        key = (candidate_id, instant.astimezone(UTC))
        state = self._ecef_cache.get(key)
        if state is None:
            state = np.asarray(
                self._propagators[candidate_id].state_ecef(datetime_to_epoch(key[1])),
                dtype=float,
            ).reshape(6)
            self._ecef_cache[key] = state
        return state

    def candidate_state_grid(
        self,
        candidate_id: str,
        sample_times: list[datetime] | tuple[datetime, ...],
    ) -> CandidateStateGrid:
        normalized_times = tuple(instant.astimezone(UTC) for instant in sample_times)
        key = (candidate_id, normalized_times)
        grid = self._state_grid_cache.get(key)
        if grid is not None:
            return grid
        eci_states = np.asarray(
            [self.state_eci(candidate_id, instant) for instant in normalized_times],
            dtype=float,
        ).reshape((len(normalized_times), 6))
        ecef_states = np.asarray(
            [self.state_ecef(candidate_id, instant) for instant in normalized_times],
            dtype=float,
        ).reshape((len(normalized_times), 6))
        grid = CandidateStateGrid(
            candidate_id=candidate_id,
            sample_times=normalized_times,
            eci_states=eci_states,
            ecef_states=ecef_states,
        )
        self._state_grid_cache[key] = grid
        return grid

    def state_grids(
        self,
        sample_times: list[datetime] | tuple[datetime, ...],
    ) -> dict[str, CandidateStateGrid]:
        return {
            candidate_id: self.candidate_state_grid(candidate_id, sample_times)
            for candidate_id in sorted(self._propagators)
        }


def numerical_closure_score(
    case: RevisitCase,
    candidate: OrbitCandidate,
    *,
    duration_sec: float,
) -> dict[str, float]:
    ensure_brahe_ready()
    start_epoch = datetime_to_epoch(case.horizon_start)
    end_epoch = datetime_to_epoch(
        case.horizon_start + timedelta(seconds=duration_sec)
    )
    force_config = brahe.ForceModelConfig(
        gravity=brahe.GravityConfiguration.spherical_harmonic(2, 0)
    )
    propagator = brahe.NumericalOrbitPropagator.from_eci(
        start_epoch,
        np.asarray(candidate.state_eci_m_mps, dtype=float),
        force_config=force_config,
    )
    propagator.propagate_to(end_epoch)
    start_ecef = np.asarray(propagator.state_ecef(start_epoch), dtype=float)[:3]
    end_ecef = np.asarray(propagator.state_ecef(end_epoch), dtype=float)[:3]
    start_geo = brahe.position_ecef_to_geocentric(
        start_ecef, brahe.AngleFormat.DEGREES
    )
    end_geo = brahe.position_ecef_to_geocentric(end_ecef, brahe.AngleFormat.DEGREES)
    return closure_score_from_geocentric(
        float(start_geo[0]),
        float(start_geo[1]),
        float(end_geo[0]),
        float(end_geo[1]),
    ).as_dict()


def build_selected_emitted_closure_audit(
    case: RevisitCase,
    candidates: list[OrbitCandidate],
) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    for candidate in sorted(candidates, key=lambda item: item.candidate_id):
        if candidate.rgt_repeat_period_sec is None:
            skipped.append(
                {
                    "candidate_id": candidate.candidate_id,
                    "reason": "candidate_has_no_rgt_repeat_period",
                }
            )
            continue
        closure = numerical_closure_score(
            case,
            candidate,
            duration_sec=candidate.rgt_repeat_period_sec,
        )
        records.append(
            {
                "candidate_id": candidate.candidate_id,
                "source": candidate.source,
                "rgt_shell_id": candidate.rgt_shell_id,
                "period_ratio_np": candidate.period_ratio_np,
                "period_ratio_nd": candidate.period_ratio_nd,
                "repeat_period_sec": candidate.rgt_repeat_period_sec,
                "semi_major_axis_m": candidate.semi_major_axis_m,
                "altitude_m": candidate.altitude_m,
                "inclination_deg": candidate.inclination_deg,
                "raan_deg": candidate.raan_deg,
                "mean_anomaly_deg": candidate.mean_anomaly_deg,
                "analytical_shell_closure_m": candidate.rgt_analytical_closure_m,
                "numerical_closure": closure,
            }
        )
    numerical_errors = [
        float(record["numerical_closure"]["surface_error_m"])
        for record in records
    ]
    return {
        "model": "brahe_numerical_j2_selected_emitted_audit",
        "audited_candidate_count": len(records),
        "skipped_candidate_count": len(skipped),
        "max_surface_error_m": max(numerical_errors) if numerical_errors else None,
        "mean_surface_error_m": (
            float(sum(numerical_errors) / len(numerical_errors))
            if numerical_errors
            else None
        ),
        "candidates": records,
        "skipped_candidates": skipped,
    }
