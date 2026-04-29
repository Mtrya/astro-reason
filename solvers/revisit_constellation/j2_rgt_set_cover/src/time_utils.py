"""Time helpers for the standalone revisit solver."""

from __future__ import annotations

from datetime import UTC, datetime

import brahe


def parse_iso_z(value: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("timestamp must be an ISO-8601 UTC string ending in Z")
    parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    return parsed.astimezone(UTC)


def datetime_to_epoch(value: datetime) -> brahe.Epoch:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware UTC")
    if value.utcoffset().total_seconds() != 0:
        raise ValueError("datetime must be UTC")
    value = value.astimezone(UTC)
    seconds = float(value.second) + value.microsecond / 1_000_000.0
    return brahe.Epoch.from_datetime(
        value.year,
        value.month,
        value.day,
        value.hour,
        value.minute,
        seconds,
        0.0,
        brahe.TimeSystem.UTC,
    )
