"""Shared utilities for benchmark scenario window computation."""

import random
from typing import List, TypeVar, Optional

T = TypeVar('T')


def shuffle_list(items: List[T], seed: Optional[int] = None) -> List[T]:
    """Shuffle a list with optional seed for reproducibility.

    Args:
        items: List to shuffle
        seed: Random seed (None for no shuffling)

    Returns:
        Shuffled copy of the list (or original if seed is None)
    """
    if seed is None:
        return items

    shuffled = items.copy()
    rng = random.Random(seed)
    rng.shuffle(shuffled)
    return shuffled


def should_stop(current_count: int, limit: Optional[int]) -> bool:
    """Check if window count has reached its limit.

    Args:
        current_count: Current window count
        limit: Maximum allowed windows (None for unlimited)

    Returns:
        True if limit is reached, False otherwise
    """
    return limit is not None and current_count >= limit
