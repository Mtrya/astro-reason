"""Generate candidate orbit libraries within case constraints."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import brahe
import numpy as np

from .case_io import Constraints

EARTH_RADIUS_M = float(brahe.R_EARTH)
NUMERICAL_EPS = 1e-9


@dataclass(frozen=True)
class CandidateSatellite:
    satellite_id: str
    state_eci_m_mps: tuple[float, float, float, float, float, float]
    # Keplerian metadata for debugging
    altitude_m: float
    inclination_deg: float
    raan_deg: float
    mean_anomaly_deg: float
    eccentricity: float


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def generate_candidates(
    constraints: Constraints,
    *,
    altitude_step_m: float | None = None,
    inclination_step_deg: float | None = None,
    num_raan_planes: int = 2,
    num_phase_slots: int = 2,
    fixed_eccentricity: float | None = None,
) -> tuple[CandidateSatellite, ...]:
    """Generate a deterministic grid of candidate orbits within constraints.

    Parameters
    ----------
    constraints:
        Case orbit constraints.
    altitude_step_m:
        Step between candidate altitude shells (default 200 km).
    inclination_step_deg:
        Step between candidate inclination bands (default 15 deg).
    num_raan_planes:
        Number of RAAN planes to generate (default 4).
    num_phase_slots:
        Number of mean-anomaly slots per plane (default 4).
    fixed_eccentricity:
        If provided, use this eccentricity for all candidates; otherwise use
        0.0 (circular orbits) to guarantee apogee/perigee respect altitude bounds.
    """
    # Small buffer to avoid floating-point drift pushing apogee/perigee outside bounds
    ALTITUDE_BUFFER_M = 50.0

    raw_min_alt = constraints.min_altitude_m
    raw_max_alt = constraints.max_altitude_m
    min_inc = constraints.min_inclination_deg if constraints.min_inclination_deg is not None else 0.0
    max_inc = constraints.max_inclination_deg if constraints.max_inclination_deg is not None else 180.0
    max_ecc = constraints.max_eccentricity

    # Altitude grid: default to two shells (min and max) if step not given
    if altitude_step_m is None:
        altitude_step_m = raw_max_alt - raw_min_alt
    if altitude_step_m <= 0:
        altitude_step_m = max(raw_max_alt - raw_min_alt, 1.0)
    altitudes: list[float] = []
    current_alt = raw_min_alt
    while current_alt <= raw_max_alt + NUMERICAL_EPS:
        # Clamp to safe interior range to avoid verifier rejecting for fp drift
        safe_alt = min(current_alt, raw_max_alt)
        buffer = min(ALTITUDE_BUFFER_M, (raw_max_alt - raw_min_alt) / 2.0)
        safe_alt = max(safe_alt, raw_min_alt + buffer)
        safe_alt = min(safe_alt, raw_max_alt - buffer)
        altitudes.append(safe_alt)
        current_alt += altitude_step_m
    if len(altitudes) == 0:
        altitudes = [(raw_min_alt + raw_max_alt) / 2.0]
    # Inclination grid: default to two bands (min and max) if step not given
    if inclination_step_deg is None:
        inclination_step_deg = max_inc - min_inc
    if inclination_step_deg <= 0:
        inclination_step_deg = max(max_inc - min_inc, 1.0)
    inclinations: list[float] = []
    current_inc = min_inc
    while current_inc <= max_inc + NUMERICAL_EPS:
        inclinations.append(min(current_inc, max_inc))
        current_inc += inclination_step_deg
    if len(inclinations) == 0:
        inclinations = [(min_inc + max_inc) / 2.0]

    # Eccentricity: default to 0 (circular) so altitude bounds are respected
    if fixed_eccentricity is not None:
        ecc = fixed_eccentricity
    else:
        ecc = 0.0
    if max_ecc is not None:
        ecc = min(ecc, max_ecc)

    candidates: list[CandidateSatellite] = []
    cand_counter = 0

    for altitude_m in altitudes:
        semi_major_axis_m = EARTH_RADIUS_M + altitude_m
        for inclination_deg in inclinations:
            for raan_idx in range(num_raan_planes):
                raan_deg = (raan_idx * 360.0 / num_raan_planes) % 360.0
                for phase_idx in range(num_phase_slots):
                    mean_anomaly_deg = (phase_idx * 360.0 / num_phase_slots) % 360.0
                    koe = np.array(
                        [
                            semi_major_axis_m,
                            ecc,
                            inclination_deg,
                            raan_deg,
                            0.0,  # argument of perigee
                            mean_anomaly_deg,
                        ],
                        dtype=float,
                    )
                    state_eci = brahe.state_koe_to_eci(koe, brahe.AngleFormat.DEGREES)
                    cand_counter += 1
                    candidate = CandidateSatellite(
                        satellite_id=f"cand_alt{int(altitude_m)}_inc{int(inclination_deg)}_raan{raan_idx}_phase{phase_idx}",
                        state_eci_m_mps=tuple(float(v) for v in state_eci.tolist()),
                        altitude_m=altitude_m,
                        inclination_deg=inclination_deg,
                        raan_deg=raan_deg,
                        mean_anomaly_deg=mean_anomaly_deg,
                        eccentricity=ecc,
                    )
                    candidates.append(candidate)

    # Deduplicate by satellite_id (should be deterministic anyway)
    seen_ids: set[str] = set()
    unique_candidates: list[CandidateSatellite] = []
    for c in candidates:
        if c.satellite_id not in seen_ids:
            seen_ids.add(c.satellite_id)
            unique_candidates.append(c)

    return tuple(unique_candidates)
