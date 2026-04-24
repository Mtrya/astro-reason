"""Generate routing grid samples aligned to routing_step_s."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Iterable


def build_time_grid(
    horizon_start: datetime,
    horizon_end: datetime,
    routing_step_s: int,
) -> tuple[datetime, ...]:
    """Return grid-aligned sample instants from horizon_start inclusive to horizon_end inclusive."""
    if routing_step_s <= 0:
        raise ValueError("routing_step_s must be > 0")
    step = timedelta(seconds=routing_step_s)
    samples: list[datetime] = []
    current = horizon_start
    while current <= horizon_end:
        samples.append(current)
        current += step
    return tuple(samples)


def sample_index(
    horizon_start: datetime,
    instant: datetime,
    routing_step_s: int,
) -> int:
    """Return the grid index for an instant; raises ValueError if off-grid."""
    if routing_step_s <= 0:
        raise ValueError("routing_step_s must be > 0")
    delta = instant - horizon_start
    total_seconds = delta.total_seconds()
    step = routing_step_s
    idx_float = total_seconds / step
    idx_rounded = int(round(idx_float))
    if abs(idx_float - idx_rounded) > 1e-9:
        raise ValueError(f"instant {instant} is not aligned to routing_step_s grid")
    return idx_rounded
