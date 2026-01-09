"""
Common resource simulation algorithms.
"""

from ..models import ResourceEvent


def _sweep_events(
    events: list[ResourceEvent],
    initial_level: float,
    capacity: float | None,
    saturate: bool = False,
) -> dict[str, float]:
    """Sweep-line integration over possibly overlapping events."""
    if not events:
        return {
            "min": initial_level,
            "max": initial_level,
            "final": initial_level,
            "violated_low": False,
            "violated_high": False,
        }

    # Build boundary points for rate changes
    points: list[tuple] = []
    for e in events:
        points.append((e.start, e.rate_change))
        points.append((e.end, -e.rate_change))

    # Sort by time, stable for same timestamp
    points.sort(key=lambda p: p[0])

    level = initial_level
    current_rate = 0.0
    last_time = points[0][0]
    min_level = level
    max_level = level

    for time, delta_rate in points:
        if time > last_time:
            duration_min = (time - last_time).total_seconds() / 60.0
            level += current_rate * duration_min

            # Saturation logic: if enabled, clamp to capacity (stop charging)
            if saturate and capacity is not None and level > capacity:
                level = capacity

            min_level = min(min_level, level)
            max_level = max(max_level, level)
            last_time = time
        current_rate += delta_rate

    # No more boundaries; update extrema with final level (after last segment)
    min_level = min(min_level, level)
    max_level = max(max_level, level)

    violated_low = min_level < 0.0
    # If saturate is True, we constrained 'level' so max_level <= capacity.
    # Therefore violated_high will naturally be False, which is correct for saturation.
    violated_high = capacity is not None and max_level > capacity

    return {
        "min": min_level,
        "max": max_level,
        "final": level,
        "violated_low": violated_low,
        "violated_high": violated_high,
    }


def simulate_resource_usage(
    events: list[ResourceEvent], initial_level: float = 0.0
) -> dict[str, float]:
    """
    Simulate resource usage assuming events may overlap.

    Returns peak and final usage (non-negative, upper-bound unconstrained).
    """
    res = _sweep_events(events, initial_level, capacity=None, saturate=False)
    # Clamp negative to zero for backward compatibility on returned values
    return {"peak": max(res["max"], 0.0), "final": max(res["final"], 0.0)}


def simulate_resource_profile(
    events: list[ResourceEvent],
    *,
    initial_level: float,
    capacity: float | None = None,
    saturate: bool = False,
) -> dict[str, float | bool]:
    """
    Simulate a resource profile with optional capacity bounds.

    Args:
        events: List of ResourceEvents; may overlap (rates are additive).
        initial_level: Starting amount (e.g., Wh).
        capacity: Optional maximum allowed level; None means unbounded above.
        saturate: If True, level is clamped at capacity (stop accumulating).
                  If False, exceeding capacity sets violated_high=True.

    Returns:
        {
          "min": min_level,
          "max": max_level,
          "final": final_level,
          "violated_low": bool,
          "violated_high": bool,
        }
    """
    return _sweep_events(events, initial_level, capacity, saturate=saturate)


def simulate_resource_curve(
    events: list[ResourceEvent],
    time_points: list,
    initial_level: float,
    capacity: float | None = None,
    saturate: bool = False,
) -> list[float]:
    """
    Simulate resource level at each specified time point.

    Args:
        events: List of ResourceEvents; may overlap (rates are additive).
        time_points: List of datetime objects at which to sample resource level.
        initial_level: Starting amount (e.g., Wh or MB).
        capacity: Optional max level; if saturate=True, level is clamped.
        saturate: If True, level is clamped at capacity.

    Returns:
        List of resource levels, one per time_point.
    """
    if not time_points:
        return []

    points: list[tuple] = []
    for e in events:
        points.append((e.start, e.rate_change))
        points.append((e.end, -e.rate_change))

    points.sort(key=lambda p: p[0])

    result = []
    level = initial_level
    current_rate = 0.0
    last_time = time_points[0]
    point_idx = 0

    all_times = sorted(set([p[0] for p in points] + list(time_points)))

    for t in all_times:
        if t > last_time:
            duration_min = (t - last_time).total_seconds() / 60.0
            level += current_rate * duration_min
            if saturate and capacity is not None and level > capacity:
                level = capacity
            if level < 0 and saturate:
                level = 0.0
            last_time = t

        while point_idx < len(time_points) and time_points[point_idx] <= t:
            result.append(level)
            point_idx += 1

        for pt, delta in points:
            if pt == t:
                current_rate += delta

    while point_idx < len(time_points):
        duration_min = (time_points[point_idx] - last_time).total_seconds() / 60.0
        level += current_rate * duration_min
        if saturate and capacity is not None and level > capacity:
            level = capacity
        if level < 0 and saturate:
            level = 0.0
        result.append(level)
        last_time = time_points[point_idx]
        point_idx += 1

    return result
