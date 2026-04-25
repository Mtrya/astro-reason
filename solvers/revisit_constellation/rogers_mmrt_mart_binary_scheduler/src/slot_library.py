"""Deterministic finite orbital slot library."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

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
    family: str = "circular_grid"
    semi_major_axis_m: float = 0.0
    resonance: str | None = None
    apc_phase_index: int | None = None
    provenance: dict[str, Any] | None = None


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


def _clip(value: float, lower: float, upper: float) -> float:
    return min(max(value, lower), upper)


def _slot_sort_key(slot: OrbitSlot) -> tuple[int, str]:
    family_rank = {
        "circular_grid": 0,
        "rgt_apc": 0,
        "heterogeneous_rgt_apc": 0,
        "heterogeneous_uniform": 1,
    }.get(slot.family, 9)
    return family_rank, slot.slot_id


def _circular_grid_slots(
    case: RevisitCase,
    config: SolverConfig,
    *,
    family: str = "circular_grid",
    slot_prefix: str = "slot",
    source: str = "bounded circular altitude/inclination/RAAN/phase grid",
) -> tuple[OrbitSlot, ...]:
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
                        f"{slot_prefix}_a{round(altitude_m):07d}"
                        f"_i{int(round(inclination_deg * 10)):04d}"
                        f"_r{raan_index:02d}_u{phase_index:02d}"
                    )
                    semi_major_axis_m = radius_m
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
                            family=family,
                            semi_major_axis_m=float(semi_major_axis_m),
                            provenance={
                                "source": source,
                                "altitude_source": "case_altitude_linspace",
                            },
                        )
                    )
    raw_slots.sort(key=_slot_sort_key)
    return tuple(raw_slots)


def _rgt_apc_slots(case: RevisitCase, config: SolverConfig, *, family: str = "rgt_apc") -> tuple[OrbitSlot, ...]:
    model = case.satellite_model
    reference_altitude_m = config.rgt_reference_semi_major_axis_m - brahe.R_EARTH
    altitude_m = _clip(reference_altitude_m, model.min_altitude_m, model.max_altitude_m)
    inclination_deg = config.rgt_reference_inclination_deg
    if inclination_deg < 0.0 or inclination_deg > 180.0:
        return ()
    radius_m = brahe.R_EARTH + altitude_m
    resonance = f"{config.rgt_resonance_numerator}:{config.rgt_resonance_denominator}"
    adaptation = (
        "reference_altitude_clipped_to_case_bounds"
        if abs(altitude_m - reference_altitude_m) > 1.0e-6
        else "reference_altitude_within_case_bounds"
    )
    raw_slots: list[OrbitSlot] = []
    for raan_index in range(config.raan_count):
        raan_deg = (360.0 * raan_index) / config.raan_count
        for phase_index in range(config.phase_count):
            apc_shift_deg = (360.0 * phase_index) / config.phase_count
            phase_deg = (
                (
                    config.rgt_phase_constant_deg
                    + apc_shift_deg
                    - (config.rgt_resonance_numerator * raan_deg)
                )
                / config.rgt_resonance_denominator
            ) % 360.0
            slot_id = (
                f"slot_rgt_a{round(altitude_m):07d}"
                f"_i{int(round(inclination_deg * 10)):04d}"
                f"_n{config.rgt_resonance_numerator:02d}d{config.rgt_resonance_denominator:02d}"
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
                    family=family,
                    semi_major_axis_m=float(radius_m),
                    resonance=resonance,
                    apc_phase_index=phase_index,
                    provenance={
                        "source": "Rogers common RGT/APC slot relation adapted to benchmark bounds",
                        "apc_relation": "N_P * RAAN + N_D * phase = constant + APC_shift mod 360 deg",
                        "reference_semi_major_axis_m": config.rgt_reference_semi_major_axis_m,
                        "reference_inclination_deg": config.rgt_reference_inclination_deg,
                        "adaptation": adaptation,
                    },
                )
            )
    raw_slots.sort(key=_slot_sort_key)
    return tuple(raw_slots)


def build_slot_library(case: RevisitCase, config: SolverConfig) -> tuple[OrbitSlot, ...]:
    if config.slot_library_mode == "circular_grid":
        slots = _circular_grid_slots(case, config)
    elif config.slot_library_mode == "rgt_apc":
        slots = _rgt_apc_slots(case, config)
    else:
        slots = (
            *_rgt_apc_slots(case, config, family="heterogeneous_rgt_apc"),
            *_circular_grid_slots(
                case,
                config,
                family="heterogeneous_uniform",
                slot_prefix="slot_nonrgt",
                source="Rogers heterogeneous-family extension adapted as uniform non-RGT grid",
            ),
        )
    return tuple(sorted(slots, key=_slot_sort_key)[: config.max_slots])


def slot_library_summary(
    config: SolverConfig, slots: tuple[OrbitSlot, ...]
) -> dict[str, object]:
    family_counts: dict[str, int] = {}
    for slot in slots:
        family_counts[slot.family] = family_counts.get(slot.family, 0) + 1
    return {
        "run_policy": config.run_policy,
        "slot_library_mode": config.slot_library_mode,
        "slot_count": len(slots),
        "family_counts": dict(sorted(family_counts.items())),
        "max_slots": config.max_slots,
        "raan_count": config.raan_count,
        "phase_count": config.phase_count,
        "altitude_count": config.altitude_count,
        "rgt_resonance": f"{config.rgt_resonance_numerator}:{config.rgt_resonance_denominator}",
        "rgt_reference_semi_major_axis_m": config.rgt_reference_semi_major_axis_m,
        "rgt_reference_inclination_deg": config.rgt_reference_inclination_deg,
        "adaptation_note": (
            "RGT/APC modes preserve the Rogers common-slot RAAN/phase relation while "
            "using benchmark-valid circular states within case altitude bounds."
        ),
    }


def slots_to_records(slots: tuple[OrbitSlot, ...]) -> list[dict[str, object]]:
    return [
        {
            "slot_id": slot.slot_id,
            "altitude_m": slot.altitude_m,
            "inclination_deg": slot.inclination_deg,
            "raan_deg": slot.raan_deg,
            "phase_deg": slot.phase_deg,
            "family": slot.family,
            "semi_major_axis_m": slot.semi_major_axis_m,
            "resonance": slot.resonance,
            "apc_phase_index": slot.apc_phase_index,
            "provenance": slot.provenance or {},
            "state_eci_m_mps": list(slot.state_eci_m_mps),
        }
        for slot in slots
    ]
