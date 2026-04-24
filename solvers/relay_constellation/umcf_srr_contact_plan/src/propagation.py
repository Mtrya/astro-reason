"""Satellite propagation using brahe, matching verifier configuration.

Supports parallel propagation across satellites to avoid single-threaded
Python bottlenecks.
"""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from datetime import UTC, datetime
from typing import Iterable

import numpy as np

from .case_io import Manifest, Satellite
from .time_grid import time_for_index


def _datetime_to_epoch(value: datetime) -> object:
    """Convert datetime to brahe Epoch."""
    import brahe

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


_brahe_eop_initialized = False


def _ensure_brahe_ready() -> None:
    global _brahe_eop_initialized
    if _brahe_eop_initialized:
        return
    import brahe

    brahe.set_global_eop_provider_from_static_provider(
        brahe.StaticEOPProvider.from_zero()
    )
    _brahe_eop_initialized = True


def _epoch_to_seconds(ep: object) -> float:
    """Convert brahe Epoch to unix timestamp (seconds since 1970-01-01 UTC)."""
    return float(ep.unix_timestamp())


def _seconds_to_epoch(seconds: float) -> object:
    """Convert unix timestamp back to brahe Epoch."""
    import brahe

    return brahe.Epoch.from_unix_timestamp(seconds)


def _propagate_one_satellite(
    satellite_state: np.ndarray,
    epoch_seconds: float,
    last_epoch_seconds: float,
    sample_epoch_seconds: list[float],
) -> np.ndarray:
    """Propagate a single satellite and return ECEF positions at sample times.

    This function is pickle-friendly for ProcessPoolExecutor.
    All epoch arguments are passed as float seconds since J2000.
    """
    import brahe

    brahe.set_global_eop_provider_from_static_provider(
        brahe.StaticEOPProvider.from_zero()
    )
    force_config = brahe.ForceModelConfig(
        gravity=brahe.GravityConfiguration.spherical_harmonic(2, 0)
    )
    epoch = _seconds_to_epoch(epoch_seconds)
    last_epoch = _seconds_to_epoch(last_epoch_seconds)
    propagator = brahe.NumericalOrbitPropagator.from_eci(
        epoch,
        satellite_state,
        force_config=force_config,
    )
    propagator.propagate_to(last_epoch)
    traj = propagator.trajectory
    rows = np.zeros((len(sample_epoch_seconds), 3), dtype=float)
    for row_index, sample_seconds in enumerate(sample_epoch_seconds):
        sample_epoch = _seconds_to_epoch(sample_seconds)
        state_eci = np.asarray(traj.interpolate(sample_epoch), dtype=float)
        rows[row_index] = np.asarray(
            brahe.position_eci_to_ecef(sample_epoch, state_eci[:3]),
            dtype=float,
        )
    return rows


def propagate_satellites(
    manifest: Manifest,
    satellites: dict[str, Satellite],
    sample_indices: Iterable[int],
    max_workers: int | None = None,
) -> dict[str, np.ndarray]:
    """Propagate satellites to sample times and return ECEF positions.

    Returns a dict mapping satellite_id -> np.ndarray of shape (n_samples, 3).
    """
    _ensure_brahe_ready()

    samples = sorted(sample_indices)
    if not samples:
        return {}

    epoch = _datetime_to_epoch(manifest.epoch)
    last_sample_index = max(samples)
    last_epoch = _datetime_to_epoch(time_for_index(manifest, last_sample_index))
    sample_epochs = [_datetime_to_epoch(time_for_index(manifest, idx)) for idx in samples]

    epoch_seconds = _epoch_to_seconds(epoch)
    last_epoch_seconds = _epoch_to_seconds(last_epoch)
    sample_epoch_seconds = [_epoch_to_seconds(ep) for ep in sample_epochs]

    satellite_ids = sorted(satellites.keys())
    states = [satellites[sid].state_eci_m_mps for sid in satellite_ids]

    # Use process pool for parallel propagation if more than one satellite
    if len(satellite_ids) > 1:
        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            futures = [
                executor.submit(
                    _propagate_one_satellite,
                    state,
                    epoch_seconds,
                    last_epoch_seconds,
                    sample_epoch_seconds,
                )
                for state in states
            ]
            results = [f.result() for f in futures]
    else:
        results = [
            _propagate_one_satellite(
                state, epoch_seconds, last_epoch_seconds, sample_epoch_seconds
            )
            for state in states
        ]

    return {
        sid: results[i]
        for i, sid in enumerate(satellite_ids)
    }


def propagate_all_to_samples(
    manifest: Manifest,
    satellites: dict[str, Satellite],
    max_workers: int | None = None,
) -> dict[str, np.ndarray]:
    """Propagate satellites to all samples in the horizon."""
    return propagate_satellites(
        manifest,
        satellites,
        range(manifest.total_samples),
        max_workers=max_workers,
    )
