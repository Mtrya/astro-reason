"""Action-grid helpers for the regional coverage solver."""

from __future__ import annotations

from datetime import datetime, timedelta

from .case_io import Mission


def align_duration_to_grid(duration_s: int, step_s: int) -> int:
    if duration_s <= 0:
        raise ValueError("duration_s must be positive")
    return ((duration_s + step_s - 1) // step_s) * step_s


def candidate_duration_s(mission: Mission, min_duration_s: int, max_duration_s: int) -> int:
    duration = align_duration_to_grid(min_duration_s, mission.time_step_s)
    if duration > max_duration_s:
        raise ValueError("minimum strip duration cannot be aligned inside maximum duration")
    return duration


def grid_offsets(mission: Mission, *, stride_s: int, duration_s: int) -> list[int]:
    stride = align_duration_to_grid(stride_s, mission.time_step_s)
    latest_start = mission.horizon_duration_s - duration_s
    if latest_start < 0:
        return []
    return list(range(0, latest_start + 1, stride))


def offset_to_datetime(mission: Mission, offset_s: int) -> datetime:
    return mission.horizon_start + timedelta(seconds=offset_s)

