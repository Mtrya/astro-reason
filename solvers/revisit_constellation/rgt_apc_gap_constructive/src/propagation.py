"""Standalone Brahe propagation helpers."""

from __future__ import annotations

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

