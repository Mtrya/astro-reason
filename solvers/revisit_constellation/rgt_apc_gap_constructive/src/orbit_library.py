"""RGT/APC-style candidate satellite state generation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import math

import brahe
import numpy as np

from .case_io import RevisitCase
from .rgt import J2RgtSearchResult, search_j2_rgt_shells


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
    raan_slot_count: int | None = None
    phase_slot_count: int | None = None
    max_shells: int | None = None
    max_closure_error_m: float | None = None
    fallback_altitude_count: int = 3
    j2_closure_tolerance_m: float = 5_000.0
    j2_refinement_iterations: int = 6

    @classmethod
    def from_mapping(cls, payload: dict[str, Any], case: RevisitCase) -> "OrbitLibraryConfig":
        orbit_raw = payload.get("orbit_library", payload)
        if not isinstance(orbit_raw, dict):
            raise ValueError("orbit_library config must be a mapping/object")
        max_candidates = orbit_raw.get("max_candidates")
        if max_candidates is None:
            max_candidates = max(0, case.max_num_satellites * 2)
        raan_slot_count = orbit_raw.get("raan_slot_count")
        phase_slot_count = orbit_raw.get("phase_slot_count")
        max_shells = orbit_raw.get("max_shells")
        max_closure_error_m = orbit_raw.get("max_closure_error_m")
        search_mode = str(orbit_raw.get("search_mode", "target_diversified"))
        if search_mode not in {
            "minmax_architecture",
            "target_diversified",
            "legacy_base_first",
        }:
            raise ValueError(
                "orbit_library.search_mode must be 'minmax_architecture', "
                "'target_diversified', or 'legacy_base_first'"
            )
        return cls(
            max_candidates=int(max_candidates),
            search_mode=search_mode,
            max_rgt_days=int(orbit_raw.get("max_rgt_days", 3)),
            min_revolutions_per_day=int(orbit_raw.get("min_revolutions_per_day", 10)),
            max_revolutions_per_day=int(orbit_raw.get("max_revolutions_per_day", 18)),
            raan_slot_count=(None if raan_slot_count is None else int(raan_slot_count)),
            phase_slot_count=(None if phase_slot_count is None else int(phase_slot_count)),
            max_shells=(None if max_shells is None else int(max_shells)),
            max_closure_error_m=(
                None if max_closure_error_m is None else float(max_closure_error_m)
            ),
            fallback_altitude_count=int(orbit_raw.get("fallback_altitude_count", 3)),
            j2_closure_tolerance_m=float(
                orbit_raw.get(
                    "j2_closure_tolerance_m",
                    max_closure_error_m if max_closure_error_m is not None else 5_000.0,
                )
            ),
            j2_refinement_iterations=int(
                orbit_raw.get("j2_refinement_iterations", 6)
            ),
        )

    def as_status_dict(self) -> dict[str, Any]:
        return {
            "max_candidates": self.max_candidates,
            "search_mode": self.search_mode,
            "max_rgt_days": self.max_rgt_days,
            "min_revolutions_per_day": self.min_revolutions_per_day,
            "max_revolutions_per_day": self.max_revolutions_per_day,
            "raan_slot_count": self.raan_slot_count,
            "phase_slot_count": self.phase_slot_count,
            "max_shells": self.max_shells,
            "max_closure_error_m": self.max_closure_error_m,
            "fallback_altitude_count": self.fallback_altitude_count,
            "j2_closure_tolerance_m": self.j2_closure_tolerance_m,
            "j2_refinement_iterations": self.j2_refinement_iterations,
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
    raan_slot_index: int
    raan_slot_count: int
    phase_slot_index: int
    phase_slot_count: int
    state_eci_m_mps: tuple[float, float, float, float, float, float]
    rgt_shell_id: str | None = None
    rgt_repeat_period_sec: float | None = None
    rgt_analytical_closure_m: float | None = None
    rgt_closure_diagnostics: dict[str, Any] | None = None

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
            "raan_slot_index": self.raan_slot_index,
            "raan_slot_count": self.raan_slot_count,
            "phase_slot_index": self.phase_slot_index,
            "phase_slot_count": self.phase_slot_count,
            "state_eci_m_mps": list(self.state_eci_m_mps),
            "rgt_shell_id": self.rgt_shell_id,
            "rgt_repeat_period_sec": self.rgt_repeat_period_sec,
            "rgt_analytical_closure_m": self.rgt_analytical_closure_m,
            "rgt_closure_diagnostics": self.rgt_closure_diagnostics,
        }


@dataclass(frozen=True, slots=True)
class OrbitLibrary:
    candidates: list[OrbitCandidate]
    considered_base_orbits: int
    rgt_base_orbits: int
    fallback_base_orbits: int
    caps: dict[str, Any]
    rgt_shell_search: J2RgtSearchResult | None = None

    def as_status_dict(self) -> dict[str, Any]:
        rgt_shell_search = (
            None if self.rgt_shell_search is None else self.rgt_shell_search.as_debug_dict()
        )
        return {
            "candidate_count": len(self.candidates),
            "considered_base_orbits": self.considered_base_orbits,
            "rgt_base_orbits": self.rgt_base_orbits,
            "fallback_base_orbits": self.fallback_base_orbits,
            "j2_rgt_shell_search": rgt_shell_search,
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


def _rgt_base_orbits(
    case: RevisitCase,
    config: OrbitLibraryConfig,
    slot_count: int,
    raan_slot_count: int,
) -> tuple[list[dict[str, Any]], J2RgtSearchResult]:
    min_a = brahe.R_EARTH + case.satellite_model.min_altitude_m
    max_a = brahe.R_EARTH + case.satellite_model.max_altitude_m
    midpoint_a = 0.5 * (min_a + max_a)
    inclinations = _target_inclinations(case)
    estimated_shells_needed = max(
        len(inclinations),
        math.ceil(
            max(1, config.max_candidates or 1)
            / max(1, slot_count * raan_slot_count)
        ),
    )
    max_shells = max(1, config.max_shells or estimated_shells_needed)
    closure_tolerance_m = (
        config.max_closure_error_m
        if config.max_closure_error_m is not None
        else config.j2_closure_tolerance_m
    )
    search_result = search_j2_rgt_shells(
        case,
        repeat_days_max=config.max_rgt_days,
        min_revolutions_per_day=config.min_revolutions_per_day,
        max_revolutions_per_day=config.max_revolutions_per_day,
        inclinations_deg=inclinations,
        max_accepted_shells=max_shells,
        eccentricity=RGT_ECCENTRICITY,
        closure_tolerance_m=closure_tolerance_m,
        refinement_iterations=config.j2_refinement_iterations,
    )
    bases: list[dict[str, Any]] = []
    inclination_ranks = {
        round(inclination_deg, 6): rank
        for rank, inclination_deg in enumerate(inclinations)
    }
    for shell in search_result.accepted_shells:
        if min_a <= shell.semi_major_axis_m <= max_a:
            closure = (
                None
                if shell.analytical_closure is None
                else shell.analytical_closure.as_dict()
            )
            bases.append(
                {
                    "source": "rgt_apc",
                    "semi_major_axis_m": shell.semi_major_axis_m,
                    "altitude_m": shell.altitude_m,
                    "np": shell.revolutions,
                    "nd": shell.repeat_days,
                    "inclination_deg": shell.inclination_deg,
                    "inclination_rank": inclination_ranks.get(
                        round(shell.inclination_deg, 6),
                        9999,
                    ),
                    "sort_distance": abs(shell.semi_major_axis_m - midpoint_a),
                    "rgt_shell_id": shell.shell_id,
                    "rgt_repeat_period_sec": shell.repeat_period_sec,
                    "rgt_analytical_closure_m": (
                        None
                        if shell.analytical_closure is None
                        else shell.analytical_closure.surface_error_m
                    ),
                    "rgt_closure_diagnostics": {
                        "accepted": shell.accepted,
                        "rejection_reason": shell.rejection_reason,
                        "root_iterations": shell.root_iterations,
                        "correction_iterations": shell.correction_iterations,
                        "rates": shell.rates.as_dict(),
                        "analytical_closure": closure,
                    },
                    "base_mean_anomaly_deg": shell.mean_anomaly_deg,
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
    return bases, search_result


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


def _raan_slot_count(config: OrbitLibraryConfig, phase_slot_count: int) -> int:
    if config.raan_slot_count is not None:
        return max(1, config.raan_slot_count)
    requested = max(1, config.max_candidates or 1)
    return max(1, min(12, math.ceil(requested / max(1, phase_slot_count))))


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
    raan_slot_index: int,
    slot_index: int,
) -> str:
    if np_rev is not None and nd is not None:
        prefix = f"rgt_np{np_rev:03d}_nd{nd:02d}"
    else:
        prefix = f"circ_alt{int(round(altitude_m / 1000.0)):04d}km"
    inc = f"i{int(round(inclination_deg * 10.0)):04d}"
    return f"{prefix}_{inc}_raan{raan_slot_index:02d}_phase{slot_index:02d}_{source}"


def _make_candidate(
    *,
    base: dict[str, Any],
    raan_slot_index: int,
    raan_slot_count: int,
    slot_index: int,
    slot_count: int,
) -> OrbitCandidate:
    mean_anomaly_deg = (
        float(base.get("base_mean_anomaly_deg", 0.0))
        + 360.0 * slot_index / slot_count
    ) % 360.0
    np_rev = base.get("np")
    nd = base.get("nd")
    raan_deg = _angle_normalize_deg(360.0 * raan_slot_index / raan_slot_count)
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
            raan_slot_index=raan_slot_index,
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
        raan_slot_index=raan_slot_index,
        raan_slot_count=raan_slot_count,
        phase_slot_index=slot_index,
        phase_slot_count=slot_count,
        state_eci_m_mps=state,
        rgt_shell_id=base.get("rgt_shell_id"),
        rgt_repeat_period_sec=base.get("rgt_repeat_period_sec"),
        rgt_analytical_closure_m=base.get("rgt_analytical_closure_m"),
        rgt_closure_diagnostics=base.get("rgt_closure_diagnostics"),
    )


def _base_group_key(base: dict[str, Any]) -> tuple[str, int | None, int | None, int]:
    if base.get("source") == "rgt_apc":
        altitude_key = 0
    else:
        altitude_key = int(round(float(base["altitude_m"])))
    return (
        str(base["source"]),
        None if base.get("np") is None else int(base["np"]),
        None if base.get("nd") is None else int(base["nd"]),
        altitude_key,
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
    raan_slot_count: int,
    slot_count: int,
) -> list[tuple[dict[str, Any], int, int]]:
    return [
        (base, raan_slot_index, slot_index)
        for base in bases
        for raan_slot_index in range(raan_slot_count)
        for slot_index in range(slot_count)
    ]


def _target_diversified_candidate_pairs(
    bases: list[dict[str, Any]],
    raan_slot_count: int,
    slot_count: int,
) -> list[tuple[dict[str, Any], int, int]]:
    phase_order = _balanced_phase_slot_order(slot_count)
    raan_order = _balanced_phase_slot_order(raan_slot_count)
    pairs: list[tuple[dict[str, Any], int, int]] = []
    for group in _base_groups(bases):
        for raan_slot_index in raan_order:
            for slot_index in phase_order:
                for base in group:
                    pairs.append((base, raan_slot_index, slot_index))
    return pairs


def _minmax_architecture_candidate_pairs(
    bases: list[dict[str, Any]],
    raan_slot_count: int,
    slot_count: int,
) -> list[tuple[dict[str, Any], int, int]]:
    """Interleave RGT families and phases before caps bind.

    The earlier target-diversified order keeps a single base RGT family together.
    This order samples one inclination/phase from many repeat families first, so
    a small candidate cap still contains temporal and altitude diversity.
    """
    phase_order = _balanced_phase_slot_order(slot_count)
    raan_order = _balanced_phase_slot_order(raan_slot_count)
    groups = _base_groups(bases)
    max_group_size = max((len(group) for group in groups), default=0)
    pairs: list[tuple[dict[str, Any], int, int]] = []
    if not groups or not phase_order or not raan_order:
        return pairs
    for tier in range(max_group_size * len(raan_order) * len(phase_order)):
        for group_index, group in enumerate(groups):
            base = group[(tier + group_index) % len(group)]
            raan_slot_index = raan_order[
                ((tier // len(phase_order)) + group_index) % len(raan_order)
            ]
            slot_index = phase_order[(tier + group_index) % len(phase_order)]
            pairs.append((base, raan_slot_index, slot_index))
    return pairs


def _candidate_shell_counts(candidates: list[OrbitCandidate]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for candidate in candidates:
        key = candidate.rgt_shell_id or candidate.source
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def _candidate_raan_slot_counts(candidates: list[OrbitCandidate]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for candidate in candidates:
        key = f"{candidate.raan_slot_index:02d}:{candidate.raan_deg:.1f}"
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def _candidate_phase_slot_counts(candidates: list[OrbitCandidate]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for candidate in candidates:
        key = f"{candidate.phase_slot_index:02d}:{candidate.mean_anomaly_deg:.1f}"
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def generate_orbit_library(
    case: RevisitCase,
    config: OrbitLibraryConfig,
) -> OrbitLibrary:
    max_candidates = max(0, config.max_candidates or 0)
    slot_count = _phase_slot_count(case, config)
    raan_slot_count = _raan_slot_count(config, slot_count)
    rgt_bases, rgt_shell_search = _rgt_base_orbits(
        case,
        config,
        slot_count,
        raan_slot_count,
    )
    fallback_bases = [] if rgt_bases else _fallback_base_orbits(case, config)
    bases = [*rgt_bases, *fallback_bases]
    candidates: list[OrbitCandidate] = []
    seen_ids: set[str] = set()
    if config.search_mode == "minmax_architecture":
        candidate_pairs = _minmax_architecture_candidate_pairs(
            bases,
            raan_slot_count,
            slot_count,
        )
    elif config.search_mode == "target_diversified":
        candidate_pairs = _target_diversified_candidate_pairs(
            bases,
            raan_slot_count,
            slot_count,
        )
    else:
        candidate_pairs = _legacy_candidate_pairs(bases, raan_slot_count, slot_count)
    for base, raan_slot_index, slot_index in candidate_pairs:
        if len(candidates) >= max_candidates:
            break
        candidate = _make_candidate(
            base=base,
            raan_slot_index=raan_slot_index,
            raan_slot_count=raan_slot_count,
            slot_index=slot_index,
            slot_count=slot_count,
        )
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
            "candidate_shell_counts": _candidate_shell_counts(candidates),
            "candidate_raan_slot_counts": _candidate_raan_slot_counts(candidates),
            "candidate_phase_slot_counts": _candidate_phase_slot_counts(candidates),
            "raan_slot_order_prefix": _balanced_phase_slot_order(raan_slot_count)[
                : min(12, raan_slot_count)
            ],
            "raan_slots_used": raan_slot_count,
            "phase_slot_order_prefix": _balanced_phase_slot_order(slot_count)[: min(12, slot_count)],
            "phase_slots_used": slot_count,
            "accepted_j2_shell_count": len(rgt_bases),
            "fallback_used": bool(fallback_bases),
            "architecture_search_strategy": config.search_mode,
            "max_num_satellites": case.max_num_satellites,
        },
        rgt_shell_search=rgt_shell_search,
    )


def initial_orbit_bounds(candidate: OrbitCandidate) -> tuple[float, float]:
    perigee_altitude_m = (
        candidate.semi_major_axis_m * (1.0 - candidate.eccentricity)
    ) - brahe.R_EARTH
    apogee_altitude_m = (
        candidate.semi_major_axis_m * (1.0 + candidate.eccentricity)
    ) - brahe.R_EARTH
    return perigee_altitude_m, apogee_altitude_m
