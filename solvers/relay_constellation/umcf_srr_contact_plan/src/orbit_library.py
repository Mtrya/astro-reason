"""Deterministic candidate added-satellite generation within case orbit constraints."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable

import numpy as np

from .case_io import Manifest, Satellite


def _orbit_summary(state_eci: np.ndarray) -> dict[str, float]:
    """Compute orbit summary from Cartesian state (same logic as verifier)."""
    import brahe

    position_m = np.asarray(state_eci[:3], dtype=float)
    velocity_m_s = np.asarray(state_eci[3:], dtype=float)
    radius_m = float(np.linalg.norm(position_m))
    speed_m_s = float(np.linalg.norm(velocity_m_s))
    if radius_m <= 1e-9:
        raise ValueError("Zero-magnitude position")

    mu_m3_s2 = float(brahe.GM_EARTH)
    specific_energy = (0.5 * speed_m_s * speed_m_s) - (mu_m3_s2 / radius_m)
    if specific_energy >= 0.0:
        raise ValueError("Not in a bound orbit")

    semi_major_axis_m = -mu_m3_s2 / (2.0 * specific_energy)
    radial_velocity = float(np.dot(position_m, velocity_m_s))
    eccentricity_vector = (
        ((speed_m_s * speed_m_s) - (mu_m3_s2 / radius_m)) * position_m
        - (radial_velocity * velocity_m_s)
    ) / mu_m3_s2
    eccentricity = float(np.linalg.norm(eccentricity_vector))
    if eccentricity >= 1.0:
        raise ValueError("Not in a closed orbit")

    angular_momentum = np.cross(position_m, velocity_m_s)
    angular_momentum_norm = float(np.linalg.norm(angular_momentum))
    if angular_momentum_norm <= 1e-9:
        raise ValueError("Degenerate angular momentum")
    inclination_deg = math.degrees(
        math.acos(max(-1.0, min(1.0, float(angular_momentum[2]) / angular_momentum_norm)))
    )
    perigee_altitude_m = (semi_major_axis_m * (1.0 - eccentricity)) - float(brahe.R_EARTH)
    apogee_altitude_m = (semi_major_axis_m * (1.0 + eccentricity)) - float(brahe.R_EARTH)
    return {
        "semi_major_axis_m": semi_major_axis_m,
        "eccentricity": eccentricity,
        "inclination_deg": inclination_deg,
        "perigee_altitude_m": perigee_altitude_m,
        "apogee_altitude_m": apogee_altitude_m,
    }


def _state_from_elements(
    semi_major_axis_m: float,
    eccentricity: float,
    inclination_deg: float,
    raan_deg: float,
    arg_perigee_deg: float,
    mean_anomaly_deg: float,
) -> np.ndarray:
    """Convert osculating Keplerian elements to Cartesian state in GCRF/ECI."""
    import brahe

    oe = np.array([
        semi_major_axis_m,
        eccentricity,
        inclination_deg,
        raan_deg,
        arg_perigee_deg,
        mean_anomaly_deg,
    ], dtype=float)
    return np.asarray(brahe.state_koe_to_eci(oe, brahe.AngleFormat.DEGREES), dtype=float)


@dataclass(frozen=True)
class CandidateConfig:
    """Configuration for candidate generation."""

    max_candidates: int = 16
    altitude_steps: int = 4
    inclination_steps: int = 4
    raan_steps: int = 4
    true_anomaly_steps: int = 2
    eccentricity: float = 0.0


def generate_candidates(
    manifest: Manifest,
    config: CandidateConfig | None = None,
) -> dict[str, Satellite]:
    """Generate a deterministic library of candidate satellites within case constraints.

    Returns a dict mapping satellite_id -> Satellite for candidates that pass
    all case orbit constraints.
    """
    if config is None:
        config = CandidateConfig()

    import brahe

    min_alt = manifest.min_altitude_m
    max_alt = manifest.max_altitude_m
    min_inc = manifest.min_inclination_deg if manifest.min_inclination_deg is not None else 0.0
    max_inc = manifest.max_inclination_deg if manifest.max_inclination_deg is not None else 180.0
    max_ecc = manifest.max_eccentricity if manifest.max_eccentricity is not None else 0.99

    # Altitudes -> semi-major axes
    altitudes = np.linspace(min_alt, max_alt, config.altitude_steps)
    semi_major_axes = altitudes + float(brahe.R_EARTH)

    # Inclinations
    if config.inclination_steps <= 1:
        inclinations = np.array([(min_inc + max_inc) / 2.0])
    else:
        inclinations = np.linspace(min_inc, max_inc, config.inclination_steps)

    # RAANs evenly spaced 0-360
    raans = np.linspace(0.0, 360.0, config.raan_steps, endpoint=False)

    # True anomalies (as mean anomaly for circular or near-circular)
    if config.true_anomaly_steps <= 1:
        anomalies = np.array([0.0])
    else:
        anomalies = np.linspace(0.0, 360.0, config.true_anomaly_steps, endpoint=False)

    candidates: dict[str, Satellite] = {}
    counter = 0

    for sma in semi_major_axes:
        for inc in inclinations:
            for raan in raans:
                for anomaly in anomalies:
                    if counter >= config.max_candidates:
                        break
                    try:
                        state = _state_from_elements(
                            semi_major_axis_m=float(sma),
                            eccentricity=config.eccentricity,
                            inclination_deg=float(inc),
                            raan_deg=float(raan),
                            arg_perigee_deg=0.0,
                            mean_anomaly_deg=float(anomaly),
                        )
                        summary = _orbit_summary(state)
                    except ValueError:
                        continue

                    # Enforce constraints
                    if summary["perigee_altitude_m"] < min_alt - 1e-9:
                        continue
                    if summary["apogee_altitude_m"] > max_alt + 1e-9:
                        continue
                    if summary["eccentricity"] > max_ecc + 1e-9:
                        continue
                    if summary["inclination_deg"] < min_inc - 1e-9:
                        continue
                    if summary["inclination_deg"] > max_inc + 1e-9:
                        continue

                    sat_id = f"added_{counter:03d}"
                    candidates[sat_id] = Satellite(
                        satellite_id=sat_id,
                        state_eci_m_mps=state,
                    )
                    counter += 1
                if counter >= config.max_candidates:
                    break
            if counter >= config.max_candidates:
                break
        if counter >= config.max_candidates:
            break

    return candidates
