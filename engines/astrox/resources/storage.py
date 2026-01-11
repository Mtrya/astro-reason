"""
Satellite storage simulation.
"""

from ..models import ResourceEvent
from .common import simulate_resource_usage


def simulate_storage(
    usage_events: list[ResourceEvent], capacity: float, initial: float
) -> dict[str, float]:
    """
    Simulate storage usage.

    Args:
        usage_events: List of storage usage events (obs+, downlink-)
        capacity: Max storage capacity in MB
        initial: Initial storage in MB

    Returns:
        Dict with "capacity" (original cap), "peak", "final", and bool flags via simulate_resource_usage logic?
        Actually, simulate_resource_usage returns {"peak", "final"}.
        We'll wrap it to provide context.
    """
    sim_result = simulate_resource_usage(usage_events, initial_level=initial)
    return {
        "capacity": capacity,
        "peak": sim_result["peak"],
        "final": sim_result["final"],
    }
