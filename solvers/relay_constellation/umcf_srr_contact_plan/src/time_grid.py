"""Routing sample grid utilities."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Iterable

from .case_io import Manifest


def sample_index(manifest: Manifest, instant: datetime, *, field: str = "time") -> int:
    """Return the sample index for a datetime on the routing grid."""
    delta = instant.astimezone(UTC) - manifest.horizon_start
    total_seconds = delta.total_seconds()
    if total_seconds < -1e-9:
        raise ValueError(f"{field} lies before horizon_start")
    step = manifest.routing_step_s
    index_float = total_seconds / step
    index_rounded = int(round(index_float))
    if abs(index_float - index_rounded) > 1e-9:
        raise ValueError(f"{field} must lie on the routing_step_s grid")
    if index_rounded > manifest.total_samples:
        raise ValueError(f"{field} lies after horizon_end")
    return index_rounded


def time_for_index(manifest: Manifest, sample_index: int) -> datetime:
    """Return the datetime for a given sample index."""
    return manifest.horizon_start + timedelta(seconds=sample_index * manifest.routing_step_s)


def interval_indices(manifest: Manifest, start_time: datetime, end_time: datetime) -> tuple[int, ...]:
    """Return the inclusive sample indices covered by [start_time, end_time)."""
    start_idx = sample_index(manifest, start_time, field="start_time")
    end_idx = sample_index(manifest, end_time, field="end_time")
    if end_idx <= start_idx:
        raise ValueError("end_time must be after start_time")
    if end_idx > manifest.total_samples:
        raise ValueError("end_time lies outside the planning horizon")
    return tuple(range(start_idx, end_idx))


def demand_indices(manifest: Manifest, demand) -> tuple[int, ...]:
    """Return sample indices for a demand window."""
    from .case_io import Demand

    start_idx = sample_index(manifest, demand.start_time, field=f"demand {demand.demand_id} start_time")
    end_idx = sample_index(manifest, demand.end_time, field=f"demand {demand.demand_id} end_time")
    if end_idx <= start_idx:
        raise ValueError(f"Demand {demand.demand_id} must contain at least one sampled instant")
    return tuple(range(start_idx, end_idx))


def all_sample_times(manifest: Manifest) -> list[datetime]:
    """Return all sample datetimes across the horizon."""
    return [time_for_index(manifest, i) for i in range(manifest.total_samples)]
