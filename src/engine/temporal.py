"""
Temporal logic engine for conflict detection and interval operations.
"""

from datetime import datetime, timezone
from typing import TypeVar, Tuple, Union

T = TypeVar("T")


def format_for_astrox(dt: datetime) -> str:
    """Format datetime for Astrox API (uses 'Z' suffix for UTC, not '+00:00')."""
    if dt.tzinfo is None:
        raise ValueError("Datetime must be timezone-aware")
    utc_dt = dt.astimezone(timezone.utc)
    return utc_dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(value: Union[str, datetime]) -> datetime:
    """Parse ISO datetime string and enforce timezone awareness."""
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        raw = value.strip()
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        dt = datetime.fromisoformat(raw)
    else:
        raise ValueError(f"Unsupported datetime type: {type(value)}")
    
    if dt.tzinfo is None:
        raise ValueError("Datetime values must include timezone information.")
    return dt


def times_overlap(
    start1: datetime, end1: datetime, start2: datetime, end2: datetime
) -> bool:
    """Check if two time intervals overlap."""
    return start1 < end2 and start2 < end1


def find_overlaps(
    query_start: datetime,
    query_end: datetime,
    candidates: list[Tuple[datetime, datetime, T]],
) -> list[T]:
    """
    Find all candidates that overlap with the query interval.

    Args:
        query_start: Start of query interval.
        query_end: End of query interval.
        candidates: List of (start, end, item) tuples.

    Returns:
        List of items that overlap with the query interval.
    """
    overlaps = []
    for start, end, item in candidates:
        if times_overlap(query_start, query_end, start, end):
            overlaps.append(item)
    return overlaps
