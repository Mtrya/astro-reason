"""Standalone Brahe propagation helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import brahe
import numpy as np

from .orbit_library import OrbitCandidate


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
