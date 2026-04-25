"""Revisit-gap helpers for later constructive phases."""

from __future__ import annotations

from datetime import datetime


def revisit_gaps_hours(
    horizon_start: datetime,
    horizon_end: datetime,
    observation_midpoints: list[datetime],
) -> list[float]:
    unique_midpoints = sorted(set(observation_midpoints))
    times = [horizon_start, *unique_midpoints, horizon_end]
    return [
        (right - left).total_seconds() / 3600.0
        for left, right in zip(times, times[1:])
    ]


def max_revisit_gap_hours(
    horizon_start: datetime,
    horizon_end: datetime,
    observation_midpoints: list[datetime],
) -> float:
    gaps = revisit_gaps_hours(horizon_start, horizon_end, observation_midpoints)
    return max(gaps) if gaps else 0.0

