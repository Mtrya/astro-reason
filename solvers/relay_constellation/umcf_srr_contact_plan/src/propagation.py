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


def _epoch_to_tuple(ep: object) -> tuple:
    """Convert brahe Epoch to a pickle-friendly datetime tuple.

    Returns (year, month, day, hour, minute, second, fraction, time_system).
    """
    return ep.to_datetime()


def _tuple_to_epoch(t: tuple) -> object:
    """Reconstruct a brahe Epoch from a datetime tuple."""
    import brahe

    return brahe.Epoch.from_datetime(*t, brahe.TimeSystem.UTC)


def _propagate_one_satellite(
    satellite_state: np.ndarray,
    epoch_tuple: tuple,
    last_epoch_tuple: tuple,
    sample_epoch_tuples: list[tuple],
) -> np.ndarray:
    """Propagate a single satellite and return ECEF positions at sample times.

    This function is pickle-friendly for ProcessPoolExecutor.
    Epoch arguments are passed as datetime tuples from ``Epoch.to_datetime()``.
    """
    import brahe

    brahe.set_global_eop_provider_from_static_provider(
        brahe.StaticEOPProvider.from_zero()
    )
    force_config = brahe.ForceModelConfig(
        gravity=brahe.GravityConfiguration.spherical_harmonic(2, 0)
    )
    epoch = _tuple_to_epoch(epoch_tuple)
    last_epoch = _tuple_to_epoch(last_epoch_tuple)
    propagator = brahe.NumericalOrbitPropagator.from_eci(
        epoch,
        satellite_state,
        force_config=force_config,
    )
    propagator.propagate_to(last_epoch)
    rows = np.zeros((len(sample_epoch_tuples), 3), dtype=float)
    for row_index, sample_tuple in enumerate(sample_epoch_tuples):
        sample_epoch = _tuple_to_epoch(sample_tuple)
        state_eci = np.asarray(propagator.state(sample_epoch), dtype=float)
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

    epoch_tuple = _epoch_to_tuple(epoch)
    last_epoch_tuple = _epoch_to_tuple(last_epoch)
    sample_epoch_tuples = [_epoch_to_tuple(ep) for ep in sample_epochs]

    satellite_ids = sorted(satellites.keys())
    states = [satellites[sid].state_eci_m_mps for sid in satellite_ids]

    # Use process pool for parallel propagation if more than one satellite
    if len(satellite_ids) > 1:
        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            futures = [
                executor.submit(
                    _propagate_one_satellite,
                    state,
                    epoch_tuple,
                    last_epoch_tuple,
                    sample_epoch_tuples,
                )
                for state in states
            ]
            results = [f.result() for f in futures]
    else:
        results = [
            _propagate_one_satellite(
                state, epoch_tuple, last_epoch_tuple, sample_epoch_tuples
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
