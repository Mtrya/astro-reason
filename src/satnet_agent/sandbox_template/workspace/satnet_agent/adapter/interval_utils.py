"""Interval arithmetic utilities for SatNet scheduling"""

from typing import List, Tuple

Interval = Tuple[int, int]


def subtract_interval(base: Interval, to_remove: Interval) -> List[Interval]:
    """
    Subtract one interval from another.
    
    Returns list of remaining intervals (0, 1, or 2 pieces).
    """
    base_start, base_end = base
    rem_start, rem_end = to_remove

    if rem_end <= base_start or rem_start >= base_end:
        return [base]

    if rem_start <= base_start and rem_end >= base_end:
        return []

    if rem_start <= base_start:
        return [(rem_end, base_end)]

    if rem_end >= base_end:
        return [(base_start, rem_start)]

    return [(base_start, rem_start), (rem_end, base_end)]


def subtract_intervals(base: Interval, to_remove: List[Interval]) -> List[Interval]:
    """Subtract multiple intervals from a base interval."""
    result = [base]
    for interval in to_remove:
        new_result = []
        for r in result:
            new_result.extend(subtract_interval(r, interval))
        result = new_result
    return result


def intersect_interval(a: Interval, b: Interval) -> Interval | None:
    """Find intersection of two intervals. Returns None if no overlap."""
    start = max(a[0], b[0])
    end = min(a[1], b[1])
    if start < end:
        return (start, end)
    return None


def is_overlap(a: Interval, b: Interval) -> bool:
    """Check if two intervals overlap."""
    return a[0] < b[1] and b[0] < a[1]


def merge_intervals(intervals: List[Interval]) -> List[Interval]:
    """Merge overlapping/adjacent intervals."""
    if not intervals:
        return []
    
    sorted_intervals = sorted(intervals, key=lambda x: x[0])
    merged = [sorted_intervals[0]]
    
    for current in sorted_intervals[1:]:
        last = merged[-1]
        if current[0] <= last[1]:
            merged[-1] = (last[0], max(last[1], current[1]))
        else:
            merged.append(current)
    
    return merged


def filter_by_duration(
    intervals: List[Interval], 
    min_duration: int
) -> List[Interval]:
    """Filter intervals shorter than min_duration."""
    return [i for i in intervals if i[1] - i[0] >= min_duration]


def find_available_slots(
    view_period: Interval,
    blocked: List[Interval],
    min_duration: int,
    setup: int,
    teardown: int,
) -> List[Interval]:
    """
    Find available scheduling slots within a view period.
    
    Args:
        view_period: Raw (trx_on, trx_off) from data
        blocked: List of already-blocked intervals (maintenance + scheduled tracks)
        min_duration: Minimum acceptable track duration
        setup: Required setup time before track
        teardown: Required teardown time after track
    
    Returns:
        List of available (trx_on, trx_off) intervals for scheduling
    """
    total_min = min_duration + setup + teardown
    
    available = subtract_intervals(view_period, blocked)
    
    return filter_by_duration(available, total_min)
