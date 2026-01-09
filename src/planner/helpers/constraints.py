"""Constraint parsing utilities.

This module handles conversion of raw constraint dictionaries into typed constraint objects.
"""

from typing import List, Any, Union
from engine.models import RangeConstraint, ElevationAngleConstraint


def parse_constraints(raw: List[Any] | None) -> List[Union[RangeConstraint, ElevationAngleConstraint]] | None:
    """
    Parse raw constraint data into typed constraint objects.
    
    Args:
        raw: List of constraint dictionaries or constraint objects, or None
        
    Returns:
        List of typed constraint objects, or None if input is None
        
    Raises:
        TypeError: If a constraint has an unsupported type
        ValueError: If a constraint has an unknown constraint type string
    """
    if raw is None:
        return None

    parsed = []
    for item in raw:
        if isinstance(item, (RangeConstraint, ElevationAngleConstraint)):
            parsed.append(item)
            continue
        if not isinstance(item, dict):
            raise TypeError(f"Unsupported constraint payload: {type(item)!r}")
        ctype = (item.get("type") or item.get("kind") or "").lower()
        if ctype == "range":
            parsed.append(RangeConstraint(
                minimum_km=item.get("minimum_km"),
                maximum_km=item.get("maximum_km"),
                enable_maximum=item.get("enable_maximum", True),
            ))
        elif ctype in ("elevation_angle", "elevation"):
            parsed.append(ElevationAngleConstraint(
                minimum_deg=item.get("minimum_deg"),
                maximum_deg=item.get("maximum_deg"),
                enable_maximum=item.get("enable_maximum", True),
            ))
        else:
            raise ValueError(f"Unsupported constraint type: {ctype!r}")
    return parsed
