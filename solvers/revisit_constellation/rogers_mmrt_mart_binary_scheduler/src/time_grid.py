"""Mission time-grid helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from .case_io import iso_z


@dataclass(frozen=True)
class TimeSample:
    index: int
    offset_sec: float
    instant: datetime


def build_time_grid(start: datetime, end: datetime, step_sec: float) -> tuple[TimeSample, ...]:
    if end <= start:
        raise ValueError("time-grid end must be after start")
    if step_sec <= 0.0:
        raise ValueError("time-grid step must be positive")

    samples: list[TimeSample] = []
    current = start
    index = 0
    delta = timedelta(seconds=step_sec)
    while current < end:
        samples.append(TimeSample(index=index, offset_sec=(current - start).total_seconds(), instant=current))
        index += 1
        current = current + delta
    if not samples or samples[-1].instant != end:
        samples.append(TimeSample(index=index, offset_sec=(end - start).total_seconds(), instant=end))
    return tuple(samples)


def time_grid_to_records(samples: tuple[TimeSample, ...]) -> list[dict[str, object]]:
    return [
        {
            "index": sample.index,
            "offset_sec": sample.offset_sec,
            "instant": iso_z(sample.instant),
        }
        for sample in samples
    ]

