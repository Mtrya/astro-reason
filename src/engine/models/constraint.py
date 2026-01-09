"""Constraint data structures for access calculations."""

from dataclasses import dataclass


@dataclass(frozen=True)
class RangeConstraint:
    """Range constraint matching Astrox IContraintConstraintRange.

    Distances are expressed in kilometers, as in the Astrox schema.
    """

    minimum_km: float | None = None
    maximum_km: float | None = None
    enable_maximum: bool = True


@dataclass(frozen=True)
class ElevationAngleConstraint:
    """Elevation-angle constraint matching IContraintConstraintElevationAngle."""

    minimum_deg: float | None = None
    maximum_deg: float | None = None
    enable_maximum: bool = True
