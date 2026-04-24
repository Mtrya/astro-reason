"""Propagate satellite states over the routing grid using Brahe."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

import brahe
import numpy as np

from .case_io import BackboneSatellite
from .orbit_library import CandidateSatellite

_BRAHE_EOP_INITIALIZED = False


def _ensure_brahe_ready() -> None:
    global _BRAHE_EOP_INITIALIZED
    if _BRAHE_EOP_INITIALIZED:
        return
    brahe.set_global_eop_provider_from_static_provider(
        brahe.StaticEOPProvider.from_zero()
    )
    _BRAHE_EOP_INITIALIZED = True


def _datetime_to_epoch(value: datetime) -> brahe.Epoch:
    value = value.astimezone(timezone.utc)
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
    return value.astimezone(datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def propagate_satellite(
    state_eci_m_mps: tuple[float, float, float, float, float, float],
    epoch: datetime,
    sample_times: Iterable[datetime],
) -> dict[int, np.ndarray]:
    """Propagate a satellite and return ECEF positions keyed by sample index.

    sample_times must be sorted ascending for efficiency.
    """
    _ensure_brahe_ready()
    epoch_brahe = _datetime_to_epoch(epoch)
    force_config = brahe.ForceModelConfig(
        gravity=brahe.GravityConfiguration.spherical_harmonic(2, 0)
    )
    propagator = brahe.NumericalOrbitPropagator.from_eci(
        epoch_brahe,
        np.array(state_eci_m_mps, dtype=float),
        force_config=force_config,
    )

    sample_times_list = list(sample_times)
    if not sample_times_list:
        return {}

    last_sample_time = sample_times_list[-1]
    last_epoch = _datetime_to_epoch(last_sample_time)
    propagator.propagate_to(last_epoch)

    positions_ecef: dict[int, np.ndarray] = {}
    for sample_index, sample_time in enumerate(sample_times_list):
        sample_epoch = _datetime_to_epoch(sample_time)
        state_eci = np.asarray(propagator.state(sample_epoch), dtype=float)
        ecef = np.asarray(
            brahe.position_eci_to_ecef(sample_epoch, state_eci[:3]),
            dtype=float,
        )
        positions_ecef[sample_index] = ecef

    return positions_ecef
