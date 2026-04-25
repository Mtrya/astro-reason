"""Grid helpers for public regional-coverage action times."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import timedelta

from case_io import Manifest, iso_z


def require_grid_multiple(value_s: int | float, step_s: int, *, field: str) -> int:
    value = float(value_s)
    rounded = int(round(value))
    if abs(value - rounded) > 1.0e-9:
        raise ValueError(f"{field} must be an integer number of seconds")
    if rounded <= 0:
        raise ValueError(f"{field} must be positive")
    if rounded % step_s != 0:
        raise ValueError(f"{field}={rounded} is not a multiple of time_step_s={step_s}")
    return rounded


def iter_start_offsets(manifest: Manifest, *, stride_s: int) -> Iterator[int]:
    stride = require_grid_multiple(stride_s, manifest.time_step_s, field="time_stride_s")
    for offset_s in range(0, manifest.horizon_seconds, stride):
        yield offset_s


def iso_at_offset(manifest: Manifest, offset_s: int) -> str:
    return iso_z(manifest.horizon_start + timedelta(seconds=offset_s))
