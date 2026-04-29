"""J2-aware repeat-ground-track orbit construction."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any
import math

import brahe
import numpy as np

from .case_io import RevisitCase
from .time_utils import datetime_to_epoch


SIDEREAL_DAY_SEC = 86164.0905
EARTH_ROTATION_RATE_RAD_S = brahe.OMEGA_EARTH
EARTH_RADIUS_M = brahe.R_EARTH
MU_EARTH_M3_S2 = brahe.GM_EARTH
J2_EARTH = brahe.J2_EARTH
DEFAULT_INCLINATIONS_DEG = (30.0, 45.0, 53.0, 63.4, 75.0, 97.8)


@dataclass(frozen=True, slots=True)
class RgtSearchConfig:
    max_repeat_days: int = 2
    min_revolutions_per_day: int = 12
    max_revolutions_per_day: int = 16
    inclinations_deg: tuple[float, ...] = DEFAULT_INCLINATIONS_DEG
    max_templates: int = 12
    eccentricity: float = 0.0
    closure_tolerance_m: float = 5_000.0
    refinement_iterations: int = 8

    @classmethod
    def from_mapping(cls, payload: dict[str, Any]) -> "RgtSearchConfig":
        defaults = cls()
        raw = payload.get("rgt_search", payload)
        if not isinstance(raw, dict):
            raise ValueError("rgt_search config must be a mapping/object")
        inclinations_raw = raw.get("inclinations_deg", DEFAULT_INCLINATIONS_DEG)
        if not isinstance(inclinations_raw, (list, tuple)):
            raise ValueError("rgt_search.inclinations_deg must be a list")
        inclinations = tuple(float(value) for value in inclinations_raw)
        return cls(
            max_repeat_days=int(raw.get("max_repeat_days", defaults.max_repeat_days)),
            min_revolutions_per_day=int(
                raw.get("min_revolutions_per_day", defaults.min_revolutions_per_day)
            ),
            max_revolutions_per_day=int(
                raw.get("max_revolutions_per_day", defaults.max_revolutions_per_day)
            ),
            inclinations_deg=inclinations,
            max_templates=int(raw.get("max_templates", defaults.max_templates)),
            eccentricity=float(raw.get("eccentricity", defaults.eccentricity)),
            closure_tolerance_m=float(
                raw.get("closure_tolerance_m", defaults.closure_tolerance_m)
            ),
            refinement_iterations=int(
                raw.get("refinement_iterations", defaults.refinement_iterations)
            ),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "max_repeat_days": self.max_repeat_days,
            "min_revolutions_per_day": self.min_revolutions_per_day,
            "max_revolutions_per_day": self.max_revolutions_per_day,
            "inclinations_deg": list(self.inclinations_deg),
            "max_templates": self.max_templates,
            "eccentricity": self.eccentricity,
            "closure_tolerance_m": self.closure_tolerance_m,
            "refinement_iterations": self.refinement_iterations,
        }


@dataclass(frozen=True, slots=True)
class J2Rates:
    keplerian_mean_motion_rad_s: float
    anomalistic_mean_motion_rad_s: float
    nodal_mean_motion_rad_s: float
    raan_rate_rad_s: float


@dataclass(frozen=True, slots=True)
class ClosureScore:
    longitude_delta_deg: float
    latitude_delta_deg: float
    surface_error_m: float
    start_longitude_deg: float
    start_latitude_deg: float
    end_longitude_deg: float
    end_latitude_deg: float

    def as_dict(self) -> dict[str, float]:
        return {
            "longitude_delta_deg": self.longitude_delta_deg,
            "latitude_delta_deg": self.latitude_delta_deg,
            "surface_error_m": self.surface_error_m,
            "start_longitude_deg": self.start_longitude_deg,
            "start_latitude_deg": self.start_latitude_deg,
            "end_longitude_deg": self.end_longitude_deg,
            "end_latitude_deg": self.end_latitude_deg,
        }


@dataclass(frozen=True, slots=True)
class RgtTemplate:
    """Canonical closed RGT shell before RAAN-specific coverage expansion."""

    template_id: str
    repeat_days: int
    revolutions: int
    inclination_deg: float
    semi_major_axis_m: float
    altitude_m: float
    eccentricity: float
    raan_deg: float
    argument_of_perigee_deg: float
    mean_anomaly_deg: float
    repeat_period_sec: float
    state_eci_m_mps: tuple[float, float, float, float, float, float]
    rates: J2Rates
    closure: ClosureScore | None
    accepted: bool
    rejection_reason: str | None
    iterations: int
    correction_iterations: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "template_id": self.template_id,
            "repeat_days": self.repeat_days,
            "revolutions": self.revolutions,
            "inclination_deg": self.inclination_deg,
            "semi_major_axis_m": self.semi_major_axis_m,
            "altitude_m": self.altitude_m,
            "eccentricity": self.eccentricity,
            "raan_deg": self.raan_deg,
            "argument_of_perigee_deg": self.argument_of_perigee_deg,
            "mean_anomaly_deg": self.mean_anomaly_deg,
            "repeat_period_sec": self.repeat_period_sec,
            "state_eci_m_mps": list(self.state_eci_m_mps),
            "rates": {
                "keplerian_mean_motion_rad_s": self.rates.keplerian_mean_motion_rad_s,
                "anomalistic_mean_motion_rad_s": self.rates.anomalistic_mean_motion_rad_s,
                "nodal_mean_motion_rad_s": self.rates.nodal_mean_motion_rad_s,
                "raan_rate_rad_s": self.rates.raan_rate_rad_s,
            },
            "closure": None if self.closure is None else self.closure.as_dict(),
            "accepted": self.accepted,
            "rejection_reason": self.rejection_reason,
            "iterations": self.iterations,
            "correction_iterations": self.correction_iterations,
        }


@dataclass(frozen=True, slots=True)
class AnalyticalRgtConstruction:
    semi_major_axis_m: float
    mean_anomaly_deg: float
    repeat_period_sec: float
    state_eci_m_mps: tuple[float, float, float, float, float, float]
    closure: ClosureScore
    iterations: int


@dataclass(frozen=True, slots=True)
class RgtSearchResult:
    accepted_templates: list[RgtTemplate]
    rejected_templates: list[RgtTemplate]
    considered_seed_count: int
    config: RgtSearchConfig

    def as_debug_dict(self) -> dict[str, Any]:
        return {
            "config": self.config.as_dict(),
            "considered_seed_count": self.considered_seed_count,
            "accepted_count": len(self.accepted_templates),
            "rejected_count": len(self.rejected_templates),
            "accepted_templates": [item.as_dict() for item in self.accepted_templates],
            "rejected_templates": [item.as_dict() for item in self.rejected_templates],
        }


_BRAHE_READY = False


def ensure_brahe_ready() -> None:
    global _BRAHE_READY
    if _BRAHE_READY:
        return
    brahe.set_global_eop_provider_from_static_provider(
        brahe.StaticEOPProvider.from_zero()
    )
    _BRAHE_READY = True


def wrap_degrees(value: float) -> float:
    return (value + 180.0) % 360.0 - 180.0


def wrap_radians(value: float) -> float:
    return (value + math.pi) % (2.0 * math.pi) - math.pi


def j2_rates(
    semi_major_axis_m: float,
    inclination_deg: float,
    eccentricity: float = 0.0,
) -> J2Rates:
    inclination_rad = math.radians(inclination_deg)
    sin_i = math.sin(inclination_rad)
    cos_i = math.cos(inclination_rad)
    ecc2 = eccentricity * eccentricity
    p = semi_major_axis_m * (1.0 - ecc2) / EARTH_RADIUS_M
    factor = 1.5 * J2_EARTH / (p * p)
    n = math.sqrt(MU_EARTH_M3_S2 / semi_major_axis_m**3)
    anomalistic = n - factor * n * math.sqrt(1.0 - ecc2) * (1.5 * sin_i * sin_i - 1.0)
    nodal = anomalistic - factor * anomalistic * (2.5 * sin_i * sin_i - 2.0)
    raan_rate = -1.5 * J2_EARTH * anomalistic * cos_i / (p * p)
    return J2Rates(
        keplerian_mean_motion_rad_s=n,
        anomalistic_mean_motion_rad_s=anomalistic,
        nodal_mean_motion_rad_s=nodal,
        raan_rate_rad_s=raan_rate,
    )


def rgt_residual(
    semi_major_axis_m: float,
    *,
    repeat_days: int,
    revolutions: int,
    inclination_deg: float,
    eccentricity: float = 0.0,
) -> float:
    rates = j2_rates(semi_major_axis_m, inclination_deg, eccentricity)
    required_nodal_rate = (
        revolutions
        / repeat_days
        * (EARTH_ROTATION_RATE_RAD_S - rates.raan_rate_rad_s)
    )
    return rates.nodal_mean_motion_rad_s - required_nodal_rate


def solve_rgt_semimajor_axis(
    *,
    repeat_days: int,
    revolutions: int,
    inclination_deg: float,
    min_altitude_m: float,
    max_altitude_m: float,
    eccentricity: float = 0.0,
    max_iterations: int = 80,
    tolerance_m: float = 1e-3,
) -> tuple[float | None, int, str | None]:
    low = EARTH_RADIUS_M + min_altitude_m
    high = EARTH_RADIUS_M + max_altitude_m
    f_low = rgt_residual(
        low,
        repeat_days=repeat_days,
        revolutions=revolutions,
        inclination_deg=inclination_deg,
        eccentricity=eccentricity,
    )
    f_high = rgt_residual(
        high,
        repeat_days=repeat_days,
        revolutions=revolutions,
        inclination_deg=inclination_deg,
        eccentricity=eccentricity,
    )
    if f_low == 0.0:
        return low, 0, None
    if f_high == 0.0:
        return high, 0, None
    if f_low * f_high > 0.0:
        return None, 0, "no_altitude_bracket"

    iterations = 0
    for iterations in range(1, max_iterations + 1):
        mid = 0.5 * (low + high)
        f_mid = rgt_residual(
            mid,
            repeat_days=repeat_days,
            revolutions=revolutions,
            inclination_deg=inclination_deg,
            eccentricity=eccentricity,
        )
        if abs(high - low) <= tolerance_m or f_mid == 0.0:
            return mid, iterations, None
        if f_low * f_mid <= 0.0:
            high = mid
            f_high = f_mid
        else:
            low = mid
            f_low = f_mid
        _ = f_high
    return 0.5 * (low + high), iterations, None


def circular_state_eci(
    semi_major_axis_m: float,
    inclination_deg: float,
    *,
    eccentricity: float = 0.0,
    raan_deg: float = 0.0,
    argument_of_perigee_deg: float = 0.0,
    mean_anomaly_deg: float = 0.0,
) -> tuple[float, float, float, float, float, float]:
    state = brahe.state_koe_to_eci(
        np.asarray(
            [
                semi_major_axis_m,
                eccentricity,
                inclination_deg,
                raan_deg,
                argument_of_perigee_deg,
                mean_anomaly_deg,
            ],
            dtype=float,
        ),
        brahe.AngleFormat.DEGREES,
    )
    return tuple(float(item) for item in state)


def _mean_to_true_anomaly_rad(mean_anomaly_rad: float, eccentricity: float) -> float:
    if eccentricity < 1e-14:
        return mean_anomaly_rad
    eccentric_anomaly = mean_anomaly_rad
    for _ in range(12):
        residual = (
            eccentric_anomaly
            - eccentricity * math.sin(eccentric_anomaly)
            - mean_anomaly_rad
        )
        slope = 1.0 - eccentricity * math.cos(eccentric_anomaly)
        eccentric_anomaly -= residual / slope
    sine_half = math.sqrt(1.0 + eccentricity) * math.sin(0.5 * eccentric_anomaly)
    cosine_half = math.sqrt(1.0 - eccentricity) * math.cos(0.5 * eccentric_anomaly)
    return 2.0 * math.atan2(sine_half, cosine_half)


def brouwer_j2_mean_to_osculating_elements(
    semi_major_axis_m: float,
    eccentricity: float,
    inclination_deg: float,
    raan_deg: float,
    argument_of_perigee_deg: float,
    mean_anomaly_deg: float,
    duration_sec: float,
) -> tuple[float, float, float, float, float, float]:
    """Propagate mean elements with a J2-only Brouwer-Lyddane reconstruction.

    The implementation follows the Brouwer-Lyddane structure: secular
    mean-element drift, then J2 short-period reconstruction to osculating
    elements. Higher zonals and drag are intentionally zeroed.
    """

    mean_eccentricity = min(max(eccentricity, 0.0), 0.999999)
    eccentricity_squared = mean_eccentricity * mean_eccentricity
    eta_squared = 1.0 - eccentricity_squared
    eta = math.sqrt(eta_squared)
    eta_cubed = eta_squared * eta
    eta_term = eta + 1.0 / (1.0 + eta)
    inclination_rad = math.radians(inclination_deg)
    raan_rad = math.radians(raan_deg)
    argument_rad = math.radians(argument_of_perigee_deg)
    mean_anomaly_rad = math.radians(mean_anomaly_deg)

    cos_i = math.cos(inclination_rad)
    sin_i = math.sin(inclination_rad)
    cos_i2 = cos_i * cos_i
    sin_i2 = 1.0 - cos_i2
    cos_i2x3m1 = 3.0 * cos_i2 - 1.0
    cos_i2x5m1 = 5.0 * cos_i2 - 1.0
    mean_motion = math.sqrt(MU_EARTH_M3_S2 / semi_major_axis_m) / semi_major_axis_m
    q = EARTH_RADIUS_M / semi_major_axis_m
    yp2 = 0.5 * J2_EARTH * q * q / (eta_squared * eta_squared)
    yp22 = yp2 * yp2

    secular_mean_longitude_rate = 1.5 * yp2 * eta * (
        cos_i2x3m1
        + 0.0625
        * yp2
        * (
            -15.0
            + eta * (16.0 + 25.0 * eta)
            + cos_i2
            * (
                30.0
                - eta * (96.0 + 90.0 * eta)
                + cos_i2 * (105.0 + eta * (144.0 + 25.0 * eta))
            )
        )
    )
    secular_argument_rate = (
        1.5 * yp2 * cos_i2x5m1
        + 0.09375
        * yp22
        * (
            -35.0
            + eta * (24.0 + 25.0 * eta)
            + cos_i2
            * (
                90.0
                - eta * (192.0 + 126.0 * eta)
                + cos_i2 * (385.0 + eta * (360.0 + 45.0 * eta))
            )
        )
    )
    secular_raan_rate = (
        -3.0 * yp2
        + 0.375
        * yp22
        * (
            -5.0
            + eta * (12.0 + 9.0 * eta)
            - cos_i2 * (35.0 + eta * (36.0 + 5.0 * eta))
        )
    ) * cos_i

    mean_arg = wrap_radians(argument_rad + secular_argument_rate * mean_motion * duration_sec)
    mean_raan = wrap_radians(raan_rad + secular_raan_rate * mean_motion * duration_sec)
    mean_l = wrap_radians(
        mean_anomaly_rad
        + (1.0 + secular_mean_longitude_rate) * mean_motion * duration_sec
    )

    true_anomaly = _mean_to_true_anomaly_rad(mean_l, mean_eccentricity)
    cos_f = math.cos(true_anomaly)
    sin_f = math.sin(true_anomaly)
    e_cos_f = mean_eccentricity * cos_f
    e_sin_f = mean_eccentricity * sin_f
    p1 = 1.0 + e_cos_f
    p2 = 2.0 + e_cos_f
    p3 = 3.0 + e_cos_f
    p1_cubed = p1 * p1 * p1
    double_arg = 2.0 * mean_arg
    sin_2gf = math.sin(double_arg + true_anomaly)
    cos_2gf = math.cos(double_arg + true_anomaly)
    sin_2g2f = math.sin(double_arg + 2.0 * true_anomaly)
    cos_2g2f = math.cos(double_arg + 2.0 * true_anomaly)
    sin_2g3f = math.sin(double_arg + 3.0 * true_anomaly)
    cos_2g3f = math.cos(double_arg + 3.0 * true_anomaly)
    e_cos_2gf = mean_eccentricity * cos_2gf
    e_sin_2gf = mean_eccentricity * sin_2gf
    e_cos_2g3f = mean_eccentricity * cos_2g3f
    e_sin_2g3f = mean_eccentricity * sin_2g3f
    mean_equation = true_anomaly + e_sin_f - mean_l
    w20 = cos_f * (p3 * e_cos_f + 3.0)
    w21 = 3.0 * (sin_2g2f + e_sin_2gf) + e_sin_2g3f
    w22 = p1 * p2 / eta_squared
    sin_half_i = math.sin(0.5 * inclination_rad)
    cos_half_i = math.cos(0.5 * inclination_rad)

    delta_a = semi_major_axis_m * (yp2 / eta_squared) * (
        (p1_cubed - eta_cubed) * cos_i2x3m1
        + 3.0 * p1_cubed * cos_2g2f * sin_i2
    )
    delta_e = 0.5 * yp2 * (
        (w20 + mean_eccentricity * eta_term) * cos_i2x3m1
        + 3.0 * (w20 + e_cos_2gf) * sin_i2
        - (3.0 * e_cos_2gf + e_cos_2g3f) * eta_squared * sin_i2
    )
    delta_i = 0.5 * yp2 * cos_i * sin_i * (
        3.0 * (cos_2g2f + e_cos_2gf) + e_cos_2g3f
    )
    e_delta_l = -0.25 * yp2 * eta_cubed * (
        2.0 * (w22 + 1.0) * sin_f * sin_i2
        + 3.0
        * sin_i2
        * (-(w22 - 1.0) * sin_2gf + (w22 + 1.0 / 3.0) * sin_2g3f)
    )
    sin_i_delta_h = 0.5 * yp2 * cos_i * sin_i * (w21 - 6.0 * mean_equation)
    delta_z = -(
        mean_eccentricity * e_delta_l * (eta_term - 1.0) / eta_cubed
        + 0.25
        * yp2
        * (
            6.0 * mean_equation * (1.0 + cos_i * (2.0 - 5.0 * cos_i))
            - w21 * (3.0 + cos_i * (2.0 - 5.0 * cos_i))
        )
    )

    eccentricity_x = mean_eccentricity + delta_e
    eccentricity_y = e_delta_l
    raan_y = sin_i_delta_h / (2.0 * max(cos_half_i, 1e-14))
    inclination_half_x = sin_half_i + 0.5 * delta_i * cos_half_i
    inclination_half_y = raan_y
    longitude = mean_l + mean_arg + mean_raan + delta_z

    osculating_a = semi_major_axis_m + delta_a
    osculating_e = math.hypot(eccentricity_x, eccentricity_y)
    osculating_l = math.atan2(
        eccentricity_x * math.sin(mean_l) + eccentricity_y * math.cos(mean_l),
        eccentricity_x * math.cos(mean_l) - eccentricity_y * math.sin(mean_l),
    )
    inclination_argument = max(
        -1.0,
        min(
            1.0,
            1.0 - 2.0 * (inclination_half_x * inclination_half_x + inclination_half_y * inclination_half_y),
        ),
    )
    osculating_i = math.acos(inclination_argument)
    osculating_raan = math.atan2(
        inclination_half_x * math.sin(mean_raan)
        + inclination_half_y * math.cos(mean_raan),
        inclination_half_x * math.cos(mean_raan)
        - inclination_half_y * math.sin(mean_raan),
    )
    osculating_arg = longitude - osculating_l - osculating_raan

    return (
        osculating_a,
        osculating_e,
        math.degrees(osculating_i),
        math.degrees(wrap_radians(osculating_raan)),
        math.degrees(wrap_radians(osculating_arg)),
        math.degrees(wrap_radians(osculating_l)),
    )


def brouwer_j2_state_eci(
    semi_major_axis_m: float,
    inclination_deg: float,
    *,
    eccentricity: float = 0.0,
    raan_deg: float = 0.0,
    argument_of_perigee_deg: float = 0.0,
    mean_anomaly_deg: float = 0.0,
    duration_sec: float = 0.0,
) -> tuple[float, float, float, float, float, float]:
    elements = brouwer_j2_mean_to_osculating_elements(
        semi_major_axis_m,
        eccentricity,
        inclination_deg,
        raan_deg,
        argument_of_perigee_deg,
        mean_anomaly_deg,
        duration_sec,
    )
    state = brahe.state_koe_to_eci(
        np.asarray(elements, dtype=float),
        brahe.AngleFormat.DEGREES,
    )
    return tuple(float(item) for item in state)


def _state_longitude_latitude_deg(
    state_eci_m_mps: tuple[float, float, float, float, float, float],
    epoch: brahe.Epoch,
) -> tuple[float, float]:
    ecef = np.asarray(
        brahe.state_eci_to_ecef(epoch, np.asarray(state_eci_m_mps, dtype=float)),
        dtype=float,
    )[:3]
    geo = brahe.position_ecef_to_geocentric(ecef, brahe.AngleFormat.DEGREES)
    return float(geo[0]), float(geo[1])


def analytical_brouwer_closure_score(
    case: RevisitCase,
    *,
    semi_major_axis_m: float,
    inclination_deg: float,
    eccentricity: float,
    mean_anomaly_deg: float,
    duration_sec: float,
) -> tuple[ClosureScore, tuple[float, float, float, float, float, float]]:
    ensure_brahe_ready()
    start_epoch = datetime_to_epoch(case.horizon_start)
    start_state = brouwer_j2_state_eci(
        semi_major_axis_m,
        inclination_deg,
        eccentricity=eccentricity,
        mean_anomaly_deg=mean_anomaly_deg,
        duration_sec=0.0,
    )
    end_state = brouwer_j2_state_eci(
        semi_major_axis_m,
        inclination_deg,
        eccentricity=eccentricity,
        mean_anomaly_deg=mean_anomaly_deg,
        duration_sec=duration_sec,
    )
    start_lon, start_lat = _state_longitude_latitude_deg(start_state, start_epoch)
    end_lon, end_lat = _state_longitude_latitude_deg(
        end_state,
        start_epoch + duration_sec,
    )
    return (
        closure_score_from_geocentric(start_lon, start_lat, end_lon, end_lat),
        start_state,
    )


def closure_score_from_geocentric(
    start_lon_deg: float,
    start_lat_deg: float,
    end_lon_deg: float,
    end_lat_deg: float,
) -> ClosureScore:
    lon_delta = wrap_degrees(end_lon_deg - start_lon_deg)
    lat_delta = end_lat_deg - start_lat_deg
    lat0 = math.radians(start_lat_deg)
    lat1 = math.radians(end_lat_deg)
    lon0 = math.radians(start_lon_deg)
    lon1 = math.radians(start_lon_deg + lon_delta)
    hav = (
        math.sin((lat1 - lat0) / 2.0) ** 2
        + math.cos(lat0) * math.cos(lat1) * math.sin((lon1 - lon0) / 2.0) ** 2
    )
    surface_error = 2.0 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(hav)))
    return ClosureScore(
        longitude_delta_deg=lon_delta,
        latitude_delta_deg=lat_delta,
        surface_error_m=surface_error,
        start_longitude_deg=start_lon_deg,
        start_latitude_deg=start_lat_deg,
        end_longitude_deg=end_lon_deg,
        end_latitude_deg=end_lat_deg,
    )


def numerical_closure_score_at_duration(
    case: RevisitCase,
    state_eci_m_mps: tuple[float, float, float, float, float, float],
    *,
    duration_sec: float,
) -> ClosureScore:
    ensure_brahe_ready()
    start_epoch = datetime_to_epoch(case.horizon_start)
    end_epoch = datetime_to_epoch(
        case.horizon_start + timedelta(seconds=duration_sec)
    )
    force_config = brahe.ForceModelConfig(
        gravity=brahe.GravityConfiguration.spherical_harmonic(2, 0)
    )
    propagator = brahe.NumericalOrbitPropagator.from_eci(
        start_epoch,
        np.asarray(state_eci_m_mps, dtype=float),
        force_config=force_config,
    )
    propagator.propagate_to(end_epoch)
    start_ecef = np.asarray(propagator.state_ecef(start_epoch), dtype=float)[:3]
    end_ecef = np.asarray(propagator.state_ecef(end_epoch), dtype=float)[:3]
    start_geo = brahe.position_ecef_to_geocentric(
        start_ecef, brahe.AngleFormat.DEGREES
    )
    end_geo = brahe.position_ecef_to_geocentric(end_ecef, brahe.AngleFormat.DEGREES)
    return closure_score_from_geocentric(
        float(start_geo[0]),
        float(start_geo[1]),
        float(end_geo[0]),
        float(end_geo[1]),
    )


def construct_analytical_rgt(
    case: RevisitCase,
    *,
    semi_major_axis_m: float,
    inclination_deg: float,
    repeat_days: int,
    eccentricity: float,
    min_altitude_m: float,
    max_altitude_m: float,
    refinement_iterations: int,
) -> AnalyticalRgtConstruction:
    low_a = EARTH_RADIUS_M + min_altitude_m
    high_a = EARTH_RADIUS_M + max_altitude_m
    repeat_period_sec = SIDEREAL_DAY_SEC * repeat_days
    best_a = float(np.clip(semi_major_axis_m, low_a, high_a))
    best_mean_anomaly = 0.0
    best_analytical_closure, best_state = analytical_brouwer_closure_score(
        case,
        semi_major_axis_m=best_a,
        inclination_deg=inclination_deg,
        eccentricity=eccentricity,
        mean_anomaly_deg=best_mean_anomaly,
        duration_sec=repeat_period_sec,
    )

    rounds = max(1, refinement_iterations)
    altitude_span_m = min(50_000.0, max(best_a - low_a, high_a - best_a))
    phase_span_deg = 180.0
    used_iterations = 0
    for iteration in range(1, rounds + 1):
        used_iterations = iteration
        improved = False
        altitude_offsets = np.linspace(-altitude_span_m, altitude_span_m, 21)
        phase_offsets = np.linspace(-phase_span_deg, phase_span_deg, 25)
        for altitude_offset in altitude_offsets:
            trial_a = float(np.clip(best_a + float(altitude_offset), low_a, high_a))
            for phase_offset in phase_offsets:
                trial_mean_anomaly = (best_mean_anomaly + float(phase_offset)) % 360.0
                trial_closure, trial_state = analytical_brouwer_closure_score(
                    case,
                    semi_major_axis_m=trial_a,
                    inclination_deg=inclination_deg,
                    eccentricity=eccentricity,
                    mean_anomaly_deg=trial_mean_anomaly,
                    duration_sec=repeat_period_sec,
                )
                trial_key = (
                    trial_closure.surface_error_m,
                    abs(trial_a - semi_major_axis_m),
                    trial_mean_anomaly,
                )
                best_key = (
                    best_analytical_closure.surface_error_m,
                    abs(best_a - semi_major_axis_m),
                    best_mean_anomaly,
                )
                if trial_key < best_key:
                    best_a = trial_a
                    best_mean_anomaly = trial_mean_anomaly
                    best_analytical_closure = trial_closure
                    best_state = trial_state
                    improved = True
        if (
            best_analytical_closure.surface_error_m <= 2_500.0
            and altitude_span_m <= 200.0
            and phase_span_deg <= 0.5
        ):
            break
        altitude_span_m *= 0.25 if improved else 0.5
        phase_span_deg *= 0.25 if improved else 0.5

    return AnalyticalRgtConstruction(
        best_a,
        best_mean_anomaly,
        repeat_period_sec,
        best_state,
        best_analytical_closure,
        used_iterations,
    )


def _template_id(repeat_days: int, revolutions: int, inclination_deg: float) -> str:
    incl_token = f"{inclination_deg:06.2f}".replace(".", "p").replace("-", "m")
    return f"j2rgt_nd{repeat_days:02d}_np{revolutions:03d}_i{incl_token}"


def enumerate_seeds(config: RgtSearchConfig) -> list[tuple[int, int, float]]:
    inclinations = sorted({round(value, 6) for value in config.inclinations_deg})
    seeds: list[tuple[int, int, float]] = []
    for repeat_days in range(1, max(1, config.max_repeat_days) + 1):
        for rev_per_day in range(
            config.min_revolutions_per_day,
            config.max_revolutions_per_day + 1,
        ):
            revolutions = rev_per_day * repeat_days
            for inclination in inclinations:
                seeds.append((repeat_days, revolutions, inclination))
    return seeds


def construct_template(
    case: RevisitCase,
    config: RgtSearchConfig,
    *,
    repeat_days: int,
    revolutions: int,
    inclination_deg: float,
) -> RgtTemplate:
    semi_major_axis, iterations, rejection = solve_rgt_semimajor_axis(
        repeat_days=repeat_days,
        revolutions=revolutions,
        inclination_deg=inclination_deg,
        min_altitude_m=case.satellite_model.min_altitude_m,
        max_altitude_m=case.satellite_model.max_altitude_m,
        eccentricity=config.eccentricity,
    )
    if semi_major_axis is None:
        rates = j2_rates(
            EARTH_RADIUS_M + case.satellite_model.min_altitude_m,
            inclination_deg,
            config.eccentricity,
        )
        return RgtTemplate(
            template_id=_template_id(repeat_days, revolutions, inclination_deg),
            repeat_days=repeat_days,
            revolutions=revolutions,
            inclination_deg=inclination_deg,
            semi_major_axis_m=0.0,
            altitude_m=0.0,
            eccentricity=config.eccentricity,
            raan_deg=0.0,
            argument_of_perigee_deg=0.0,
            mean_anomaly_deg=0.0,
            repeat_period_sec=SIDEREAL_DAY_SEC * repeat_days,
            state_eci_m_mps=(0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
            rates=rates,
            closure=None,
            accepted=False,
            rejection_reason=rejection,
            iterations=iterations,
            correction_iterations=0,
        )

    construction = construct_analytical_rgt(
        case,
        semi_major_axis_m=semi_major_axis,
        inclination_deg=inclination_deg,
        repeat_days=repeat_days,
        eccentricity=config.eccentricity,
        min_altitude_m=case.satellite_model.min_altitude_m,
        max_altitude_m=case.satellite_model.max_altitude_m,
        refinement_iterations=config.refinement_iterations,
    )
    accepted = construction.closure.surface_error_m <= config.closure_tolerance_m
    return RgtTemplate(
        template_id=_template_id(repeat_days, revolutions, inclination_deg),
        repeat_days=repeat_days,
        revolutions=revolutions,
        inclination_deg=inclination_deg,
        semi_major_axis_m=construction.semi_major_axis_m,
        altitude_m=construction.semi_major_axis_m - EARTH_RADIUS_M,
        eccentricity=config.eccentricity,
        raan_deg=0.0,
        argument_of_perigee_deg=0.0,
        mean_anomaly_deg=construction.mean_anomaly_deg,
        repeat_period_sec=construction.repeat_period_sec,
        state_eci_m_mps=construction.state_eci_m_mps,
        rates=j2_rates(
            construction.semi_major_axis_m,
            inclination_deg,
            config.eccentricity,
        ),
        closure=construction.closure,
        accepted=accepted,
        rejection_reason=(
            None if accepted else f"closure_error_above_{config.closure_tolerance_m:g}_m"
        ),
        iterations=iterations,
        correction_iterations=construction.iterations,
    )


def search_rgt_templates(case: RevisitCase, config: RgtSearchConfig) -> RgtSearchResult:
    accepted: list[RgtTemplate] = []
    rejected: list[RgtTemplate] = []
    seeds = enumerate_seeds(config)
    for repeat_days, revolutions, inclination_deg in seeds:
        template = construct_template(
            case,
            config,
            repeat_days=repeat_days,
            revolutions=revolutions,
            inclination_deg=inclination_deg,
        )
        if template.accepted:
            accepted.append(template)
        else:
            rejected.append(template)

    accepted.sort(
        key=lambda item: (
            math.inf if item.closure is None else item.closure.surface_error_m,
            item.repeat_days,
            item.revolutions,
            item.inclination_deg,
            item.template_id,
        )
    )
    accepted = accepted[: max(0, config.max_templates)]
    rejected.sort(key=lambda item: item.template_id)
    return RgtSearchResult(
        accepted_templates=accepted,
        rejected_templates=rejected,
        considered_seed_count=len(seeds),
        config=config,
    )
