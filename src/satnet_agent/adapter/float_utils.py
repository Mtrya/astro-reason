"""Floating point comparison utilities with epsilon tolerance"""

# Default epsilon for floating point comparisons
# This handles rounding errors from division/multiplication operations
EPSILON = 1e-9


def float_eq(a: float, b: float, epsilon: float = EPSILON) -> bool:
    """Check if two floats are approximately equal."""
    return abs(a - b) < epsilon


def float_le(a: float, b: float, epsilon: float = EPSILON) -> bool:
    """Check if a <= b with epsilon tolerance."""
    return a < b + epsilon


def float_ge(a: float, b: float, epsilon: float = EPSILON) -> bool:
    """Check if a >= b with epsilon tolerance."""
    return a > b - epsilon


def float_lt(a: float, b: float, epsilon: float = EPSILON) -> bool:
    """Check if a < b with epsilon tolerance (strict inequality)."""
    return a < b - epsilon


def float_gt(a: float, b: float, epsilon: float = EPSILON) -> bool:
    """Check if a > b with epsilon tolerance (strict inequality)."""
    return a > b + epsilon
