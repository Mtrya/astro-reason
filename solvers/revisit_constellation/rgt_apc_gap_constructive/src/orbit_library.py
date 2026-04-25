"""RGT/APC-style candidate satellite state generation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import math

import brahe
import numpy as np

from .case_io import RevisitCase


SIDEREAL_DAY_SEC = 86164.0905
RGT_ECCENTRICITY = 0.0
RGT_ARGUMENT_OF_PERIGEE_DEG = 0.0


@dataclass(frozen=True, slots=True)
class OrbitLibraryConfig:
    max_candidates: int | None = None
    search_mode: str = "target_diversified"
    max_rgt_days: int = 3
    min_revolutions_per_day: int = 10
    max_revolutions_per_day: int = 18
    phase_slot_count: int | None = None
    fallback_altitude_count: int = 3

    @classmethod
    def from_mapping(cls, payload: dict[str, Any], case: RevisitCase) -> "OrbitLibraryConfig":
        orbit_raw = payload.get("orbit_library", payload)
        if not isinstance(orbit_raw, dict):
            raise ValueError("orbit_library config must be a mapping/object")
        max_candidates = orbit_raw.get("max_candidates")
        if max_candidates is None:
            max_candidates = max(0, case.max_num_satellites * 2)
        phase_slot_count = orbit_raw.get("phase_slot_count")
        search_mode = str(orbit_raw.get("search_mode", "target_diversified"))
        if search_mode not in {"target_diversified", "legacy_base_first"}:
            raise ValueError(
                "orbit_library.search_mode must be 'target_diversified' or "
                "'legacy_base_first'"
            )
        return cls(
            max_candidates=int(max_candidates),
            search_mode=search_mode,
            max_rgt_days=int(orbit_raw.get("max_rgt_days", 3)),
            min_revolutions_per_day=int(orbit_raw.get("min_revolutions_per_day", 10)),
            max_revolutions_per_day=int(orbit_raw.get("max_revolutions_per_day", 18)),
            phase_slot_count=(None if phase_slot_count is None else int(phase_slot_count)),
            fallback_altitude_count=int(orbit_raw.get("fallback_altitude_count", 3)),
        )

    def as_status_dict(self) -> dict[str, Any]:
        return {
            "max_candidates": self.max_candidates,
            "search_mode": self.search_mode,
            "max_rgt_days": self.max_rgt_days,
            "min_revolutions_per_day": self.min_revolutions_per_day,
            "max_revolutions_per_day": self.max_revolutions_per_day,
            "phase_slot_count": self.phase_slot_count,
            "fallback_altitude_count": self.fallback_altitude_count,
        }


@dataclass(frozen=True, slots=True)
class OrbitCandidate:
    candidate_id: str
    source: str
    semi_major_axis_m: float
    eccentricity: float
    inclination_deg: float
    raan_deg: float
    argument_of_perigee_deg: float
    mean_anomaly_deg: float
    altitude_m: float
    period_ratio_np: int | None
    period_ratio_nd: int | None
    phase_slot_index: int
    phase_slot_count: int
    state_eci_m_mps: tuple[float, float, float, float, float, float]

    def as_solution_satellite(self) -> dict[str, float | str]:
        state = self.state_eci_m_mps
        return {
            "satellite_id": self.candidate_id,
            "x_m": state[0],
            "y_m": state[1],
            "z_m": state[2],
            "vx_m_s": state[3],
            "vy_m_s": state[4],
            "vz_m_s": state[5],
        }

    def as_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "source": self.source,
            "semi_major_axis_m": self.semi_major_axis_m,
            "eccentricity": self.eccentricity,
            "inclination_deg": self.inclination_deg,
            "raan_deg": self.raan_deg,
            "argument_of_perigee_deg": self.argument_of_perigee_deg,
            "mean_anomaly_deg": self.mean_anomaly_deg,
            "altitude_m": self.altitude_m,
            "period_ratio_np": self.period_ratio_np,
            "period_ratio_nd": self.period_ratio_nd,
            "phase_slot_index": self.phase_slot_index,
            "phase_slot_count": self.phase_slot_count,
            "state_eci_m_mps": list(self.state_eci_m_mps),
        }


@dataclass(frozen=True, slots=True)
class OrbitLibrary:
    candidates: list[OrbitCandidate]
    considered_base_orbits: int
    rgt_base_orbits: int
    fallback_base_orbits: int
    caps: dict[str, Any]

    def as_status_dict(self) -> dict[str, Any]:
        return {
            "candidate_count": len(self.candidates),
            "considered_base_orbits": self.considered_base_orbits,
            "rgt_base_orbits": self.rgt_base_orbits,
            "fallback_base_orbits": self.fallback_base_orbits,
            "caps": self.caps,
        }


def _angle_normalize_deg(value: float) -> float:
    return value % 360.0


def _candidate_state(
    semi_major_axis_m: float,
    eccentricity: float,
    inclination_deg: float,
    raan_deg: float,
    argument_of_perigee_deg: float,
    mean_anomaly_deg: float,
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


def _target_inclinations(case: RevisitCase) -> list[float]:
    if not case.targets:
        return [53.0, 63.4, 97.8]
    abs_latitudes = sorted(abs(target.latitude_deg) for target in case.targets.values())

    def quantile(fraction: float) -> float:
        index = min(
            len(abs_latitudes) - 1,
            max(0, round((len(abs_latitudes) - 1) * fraction)),
        )
        return abs_latitudes[index]

    demand_values = [
        min(98.0, max(25.0, quantile(0.50) + 10.0)),
        min(98.0, max(25.0, quantile(0.75) + 10.0)),
        min(98.0, max(25.0, abs_latitudes[-1] + 10.0)),
    ]
    values = [*demand_values, 53.0, 63.4, 97.8]
    result: list[float] = []
    for value in values:
        rounded = round(value, 1)
        if rounded not in result:
            result.append(rounded)
    return result


def _rgt_base_orbits(case: RevisitCase, config: OrbitLibraryConfig) -> list[dict[str, float | int | str]]:
    min_a = brahe.R_EARTH + case.satellite_model.min_altitude_m
    max_a = brahe.R_EARTH + case.satellite_model.max_altitude_m
    midpoint_a = 0.5 * (min_a + max_a)
    inclinations = _target_inclinations(case)
    bases: list[dict[str, float | int | str]] = []
    for nd in range(1, max(1, config.max_rgt_days) + 1):
        for np_rev in range(config.min_revolutions_per_day * nd, config.max_revolutions_per_day * nd + 1):
            period_sec = SIDEREAL_DAY_SEC * nd / np_rev
            semi_major_axis_m = float(brahe.semimajor_axis_from_orbital_period(period_sec))
            if min_a <= semi_major_axis_m <= max_a:
                altitude_m = semi_major_axis_m - brahe.R_EARTH
                for inclination_rank, inclination_deg in enumerate(inclinations):
                    bases.append(
                        {
                            "source": "rgt_apc",
                            "semi_major_axis_m": semi_major_axis_m,
                            "altitude_m": altitude_m,
                            "np": np_rev,
                            "nd": nd,
                            "inclination_deg": inclination_deg,
                            "inclination_rank": inclination_rank,
                            "sort_distance": abs(semi_major_axis_m - midpoint_a),
                        }
                    )
    bases.sort(
        key=lambda item: (
            float(item["sort_distance"]),
            int(item["nd"]),
            int(item["np"]),
            float(item["inclination_deg"]),
        )
    )
    return bases


def _fallback_base_orbits(case: RevisitCase, config: OrbitLibraryConfig) -> list[dict[str, float | int | str | None]]:
    min_alt = case.satellite_model.min_altitude_m
    max_alt = case.satellite_model.max_altitude_m
    count = max(1, config.fallback_altitude_count)
    if count == 1:
        altitudes = [0.5 * (min_alt + max_alt)]
    else:
        altitudes = [
            min_alt + ((max_alt - min_alt) * index / (count - 1))
            for index in range(count)
        ]
    inclinations = _target_inclinations(case)
    bases: list[dict[str, float | int | str | None]] = []
    for altitude_m in altitudes:
        semi_major_axis_m = brahe.R_EARTH + altitude_m
        for inclination_rank, inclination_deg in enumerate(inclinations):
            bases.append(
                {
                    "source": "circular_fallback",
                    "semi_major_axis_m": semi_major_axis_m,
                    "altitude_m": altitude_m,
                    "np": None,
                    "nd": None,
                    "inclination_deg": inclination_deg,
                    "inclination_rank": inclination_rank,
                    "sort_distance": abs(altitude_m - (0.5 * (min_alt + max_alt))),
                }
            )
    bases.sort(
        key=lambda item: (
            float(item["sort_distance"]),
            float(item["inclination_deg"]),
        )
    )
    return bases


def _phase_slot_count(case: RevisitCase, config: OrbitLibraryConfig) -> int:
    if config.phase_slot_count is not None:
        return max(1, config.phase_slot_count)
    requested = config.max_candidates or case.max_num_satellites
    return max(1, min(max(case.max_num_satellites, requested, 1), 24))


def _balanced_phase_slot_order(slot_count: int) -> list[int]:
    if slot_count <= 0:
        return []
    order = [0]
    seen = {0}
    denominator = 2
    while len(order) < slot_count and denominator <= slot_count * 2:
        for numerator in range(1, denominator, 2):
            slot_index = int(round((slot_count * numerator) / denominator)) % slot_count
            if slot_index not in seen:
                seen.add(slot_index)
                order.append(slot_index)
                if len(order) >= slot_count:
                    break
        denominator *= 2
    for slot_index in range(slot_count):
        if slot_index not in seen:
            order.append(slot_index)
    return order


def _candidate_id(
    *,
    source: str,
    np_rev: int | None,
    nd: int | None,
    altitude_m: float,
    inclination_deg: float,
    slot_index: int,
) -> str:
    if np_rev is not None and nd is not None:
        prefix = f"rgt_np{np_rev:02d}_nd{nd:02d}"
    else:
        prefix = f"circ_alt{int(round(altitude_m / 1000.0)):04d}km"
    inc = f"i{int(round(inclination_deg * 10.0)):04d}"
    return f"{prefix}_{inc}_slot{slot_index:02d}_{source}"


def _make_candidate(
    *,
    base: dict[str, Any],
    slot_index: int,
    slot_count: int,
) -> OrbitCandidate:
    mean_anomaly_deg = 360.0 * slot_index / slot_count
    np_rev = base.get("np")
    nd = base.get("nd")
    if np_rev is not None and nd is not None:
        raan_deg = _angle_normalize_deg(-(float(nd) / float(np_rev)) * mean_anomaly_deg)
    else:
        raan_deg = _angle_normalize_deg(360.0 * slot_index / slot_count)
    state = _candidate_state(
        float(base["semi_major_axis_m"]),
        RGT_ECCENTRICITY,
        float(base["inclination_deg"]),
        raan_deg,
        RGT_ARGUMENT_OF_PERIGEE_DEG,
        mean_anomaly_deg,
    )
    return OrbitCandidate(
        candidate_id=_candidate_id(
            source=str(base["source"]),
            np_rev=(None if np_rev is None else int(np_rev)),
            nd=(None if nd is None else int(nd)),
            altitude_m=float(base["altitude_m"]),
            inclination_deg=float(base["inclination_deg"]),
            slot_index=slot_index,
        ),
        source=str(base["source"]),
        semi_major_axis_m=float(base["semi_major_axis_m"]),
        eccentricity=RGT_ECCENTRICITY,
        inclination_deg=float(base["inclination_deg"]),
        raan_deg=raan_deg,
        argument_of_perigee_deg=RGT_ARGUMENT_OF_PERIGEE_DEG,
        mean_anomaly_deg=mean_anomaly_deg,
        altitude_m=float(base["altitude_m"]),
        period_ratio_np=(None if np_rev is None else int(np_rev)),
        period_ratio_nd=(None if nd is None else int(nd)),
        phase_slot_index=slot_index,
        phase_slot_count=slot_count,
        state_eci_m_mps=state,
    )


def _base_group_key(base: dict[str, Any]) -> tuple[str, int | None, int | None, int]:
    return (
        str(base["source"]),
        None if base.get("np") is None else int(base["np"]),
        None if base.get("nd") is None else int(base["nd"]),
        int(round(float(base["altitude_m"]))),
    )


def _base_groups(
    bases: list[dict[str, Any]],
) -> list[list[dict[str, Any]]]:
    grouped: dict[tuple[str, int | None, int | None, int], list[dict[str, Any]]] = {}
    for base in bases:
        grouped.setdefault(_base_group_key(base), []).append(base)
    groups = list(grouped.values())
    for group in groups:
        group.sort(
            key=lambda item: (
                int(item.get("inclination_rank", 9999)),
                float(item["inclination_deg"]),
            )
        )
    groups.sort(
        key=lambda group: (
            float(group[0]["sort_distance"]),
            str(group[0]["source"]),
            999999 if group[0].get("nd") is None else int(group[0]["nd"]),
            999999 if group[0].get("np") is None else int(group[0]["np"]),
            float(group[0]["altitude_m"]),
        )
    )
    return groups


def _candidate_source_counts(candidates: list[OrbitCandidate]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for candidate in candidates:
        counts[candidate.source] = counts.get(candidate.source, 0) + 1
    return dict(sorted(counts.items()))


def _candidate_inclination_counts(candidates: list[OrbitCandidate]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for candidate in candidates:
        key = f"{candidate.inclination_deg:.1f}"
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: float(item[0])))


def _legacy_candidate_pairs(
    bases: list[dict[str, Any]],
    slot_count: int,
) -> list[tuple[dict[str, Any], int]]:
    return [
        (base, slot_index)
        for base in bases
        for slot_index in range(slot_count)
    ]


def _target_diversified_candidate_pairs(
    bases: list[dict[str, Any]],
    slot_count: int,
) -> list[tuple[dict[str, Any], int]]:
    phase_order = _balanced_phase_slot_order(slot_count)
    pairs: list[tuple[dict[str, Any], int]] = []
    for group in _base_groups(bases):
        for slot_index in phase_order:
            for base in group:
                pairs.append((base, slot_index))
    return pairs


def generate_orbit_library(
    case: RevisitCase,
    config: OrbitLibraryConfig,
) -> OrbitLibrary:
    max_candidates = max(0, config.max_candidates or 0)
    slot_count = _phase_slot_count(case, config)
    rgt_bases = _rgt_base_orbits(case, config)
    fallback_bases = [] if rgt_bases else _fallback_base_orbits(case, config)
    bases = [*rgt_bases, *fallback_bases]
    candidates: list[OrbitCandidate] = []
    seen_ids: set[str] = set()
    if config.search_mode == "target_diversified":
        candidate_pairs = _target_diversified_candidate_pairs(bases, slot_count)
    else:
        candidate_pairs = _legacy_candidate_pairs(bases, slot_count)
    for base, slot_index in candidate_pairs:
        if len(candidates) >= max_candidates:
            break
        candidate = _make_candidate(base=base, slot_index=slot_index, slot_count=slot_count)
        if candidate.candidate_id in seen_ids:
            continue
        seen_ids.add(candidate.candidate_id)
        candidates.append(candidate)
    return OrbitLibrary(
        candidates=candidates,
        considered_base_orbits=len(bases),
        rgt_base_orbits=len(rgt_bases),
        fallback_base_orbits=len(fallback_bases),
        caps={
            **config.as_status_dict(),
            "candidate_count_capped": len(candidates) >= max_candidates,
            "candidate_cap": max_candidates,
            "candidate_cap_is_independent_of_case_satellite_cap": True,
            "base_group_count": len(_base_groups(bases)),
            "candidate_source_counts": _candidate_source_counts(candidates),
            "candidate_inclination_counts": _candidate_inclination_counts(candidates),
            "phase_slot_order_prefix": _balanced_phase_slot_order(slot_count)[: min(12, slot_count)],
            "phase_slots_used": slot_count,
            "max_num_satellites": case.max_num_satellites,
        },
    )


def initial_orbit_bounds(candidate: OrbitCandidate) -> tuple[float, float]:
    perigee_altitude_m = (
        candidate.semi_major_axis_m * (1.0 - candidate.eccentricity)
    ) - brahe.R_EARTH
    apogee_altitude_m = (
        candidate.semi_major_axis_m * (1.0 + candidate.eccentricity)
    ) - brahe.R_EARTH
    return perigee_altitude_m, apogee_altitude_m
