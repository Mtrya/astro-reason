"""Benchmark-compatible roll transition helpers."""

from __future__ import annotations

import math
from dataclasses import dataclass

from .case_io import Satellite


@dataclass(frozen=True, slots=True)
class TransitionResult:
    feasible: bool
    required_gap_s: float
    available_gap_s: float
    roll_delta_deg: float


def slew_time_s(roll_delta_deg: float, satellite: Satellite) -> float:
    d = abs(float(roll_delta_deg))
    omega = satellite.agility.max_roll_rate_deg_per_s
    alpha = satellite.agility.max_roll_acceleration_deg_per_s2
    if d <= 0.0:
        return 0.0
    d_tri = omega * omega / alpha
    if d <= d_tri:
        return 2.0 * math.sqrt(d / alpha)
    return d / omega + omega / alpha


def required_transition_gap_s(previous_roll_deg: float, current_roll_deg: float, satellite: Satellite) -> float:
    return slew_time_s(current_roll_deg - previous_roll_deg, satellite) + satellite.agility.settling_time_s


def transition_result(previous, current, *, satellite: Satellite) -> TransitionResult:
    if previous.satellite_id != current.satellite_id:
        return TransitionResult(True, 0.0, float("inf"), 0.0)
    available_gap_s = float(current.start_offset_s - previous.end_offset_s)
    roll_delta_deg = abs(float(current.roll_deg) - float(previous.roll_deg))
    required_gap_s = required_transition_gap_s(previous.roll_deg, current.roll_deg, satellite)
    return TransitionResult(
        feasible=available_gap_s + 1e-6 >= required_gap_s,
        required_gap_s=required_gap_s,
        available_gap_s=available_gap_s,
        roll_delta_deg=roll_delta_deg,
    )

