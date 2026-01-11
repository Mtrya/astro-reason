"""Resource management data structures."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ResourceEvent:
    """Represents an event that consumes or releases a resource over time."""

    start: datetime
    end: datetime
    rate_change: float  # Positive for accumulation, negative for depletion
    # e.g. MB/min
