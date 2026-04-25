"""UTC timestamp and horizon grid helpers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta


NUMERICAL_EPS = 1.0e-9


def parse_iso_z(value: str, *, field_name: str = "timestamp") -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be an ISO 8601 timestamp string")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"{field_name} must include timezone information")
    return parsed.astimezone(UTC)


def iso_z(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def horizon_seconds(start: datetime, end: datetime) -> int:
    seconds = (end - start).total_seconds()
    if seconds <= 0.0:
        raise ValueError("horizon end must be after horizon start")
    if abs(seconds - round(seconds)) > NUMERICAL_EPS:
        raise ValueError("mission horizon must be an integer number of seconds")
    return int(round(seconds))


def horizon_sample_times(
    start: datetime,
    end: datetime,
    step_sec: float,
    *,
    include_end: bool = False,
) -> list[datetime]:
    if step_sec <= 0.0:
        raise ValueError("step_sec must be > 0")
    total = horizon_seconds(start, end)
    count = int(total // step_sec)
    times = [start + timedelta(seconds=index * step_sec) for index in range(count + 1)]
    times = [value for value in times if value < end]
    if include_end and (not times or times[-1] != end):
        times.append(end)
    return times


def offset_seconds(start: datetime, instant: datetime) -> float:
    return (instant - start).total_seconds()

