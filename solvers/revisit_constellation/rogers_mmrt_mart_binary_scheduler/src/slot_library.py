"""Deterministic finite orbital slot library."""

from __future__ import annotations

from dataclasses import dataclass
import math

import brahe
import numpy as np

from .case_io import RevisitCase, SolverConfig


@dataclass(frozen=True)
class OrbitSlot:
    slot_id: str
    altitude_m: float
    inclination_deg: float
    raan_deg: float
    phase_deg: float
    state_eci_m_mps: tuple[float, float, float, float, float, float]


def _linspace_inclusive(start: float, stop: float, count: int) -> tuple[float, ...]:
    if count == 1:
        return ((start + stop) / 2.0,)
    return tuple(float(item) for item in np.linspace(start, stop, count))


def _rotation_state(
    radius_m: float, inclination_deg: float, raan_deg: float, phase_deg: float
) -> tuple[float, float, float, float, float, float]:
    inclination = math.radians(inclination_deg)
    raan = math.radians(raan_deg)
    phase = math.radians(phase_deg)
    speed_m_s = math.sqrt(brahe.GM_EARTH / radius_m)

    position_pqw = np.array([radius_m * math.cos(phase), radius_m * math.sin(phase), 0.0])
    velocity_pqw = np.array([-speed_m_s * math.sin(phase), speed_m_s * math.cos(phase), 0.0])

    cos_raan = math.cos(raan)
    sin_raan = math.sin(raan)
    cos_inc = math.cos(inclination)
    sin_inc = math.sin(inclination)
    rotation = np.array(
        [
            [cos_raan, -sin_raan * cos_inc, sin_raan * sin_inc],
            [sin_raan, cos_raan * cos_inc, -cos_raan * sin_inc],
            [0.0, sin_inc, cos_inc],
        ]
    )
    state = np.concatenate((rotation @ position_pqw, rotation @ velocity_pqw))
    return tuple(float(item) for item in state)


def build_slot_library(case: RevisitCase, config: SolverConfig) -> tuple[OrbitSlot, ...]:
    model = case.satellite_model
    altitudes = _linspace_inclusive(
        model.min_altitude_m, model.max_altitude_m, config.altitude_count
    )
    raw_slots: list[OrbitSlot] = []
    for altitude_m in altitudes:
        if altitude_m < model.min_altitude_m or altitude_m > model.max_altitude_m:
            continue
        radius_m = brahe.R_EARTH + altitude_m
        for inclination_deg in config.inclination_deg:
            if inclination_deg < 0.0 or inclination_deg > 180.0:
                continue
            for raan_index in range(config.raan_count):
                raan_deg = (360.0 * raan_index) / config.raan_count
                for phase_index in range(config.phase_count):
                    phase_deg = (360.0 * phase_index) / config.phase_count
                    slot_id = (
                        f"slot_a{round(altitude_m):07d}"
                        f"_i{int(round(inclination_deg * 10)):04d}"
                        f"_r{raan_index:02d}_u{phase_index:02d}"
                    )
                    raw_slots.append(
                        OrbitSlot(
                            slot_id=slot_id,
                            altitude_m=float(altitude_m),
                            inclination_deg=float(inclination_deg),
                            raan_deg=float(raan_deg),
                            phase_deg=float(phase_deg),
                            state_eci_m_mps=_rotation_state(
                                radius_m, inclination_deg, raan_deg, phase_deg
                            ),
                        )
                    )
    raw_slots.sort(key=lambda slot: slot.slot_id)
    return tuple(raw_slots[: config.max_slots])


def slots_to_records(slots: tuple[OrbitSlot, ...]) -> list[dict[str, object]]:
    return [
        {
            "slot_id": slot.slot_id,
            "altitude_m": slot.altitude_m,
            "inclination_deg": slot.inclination_deg,
            "raan_deg": slot.raan_deg,
            "phase_deg": slot.phase_deg,
            "state_eci_m_mps": list(slot.state_eci_m_mps),
        }
        for slot in slots
    ]

