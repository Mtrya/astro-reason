"""Deterministic strip candidate generation over public action-grid values."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from case_io import RegionalCoverageCase, Satellite
from time_grid import iso_at_offset, iter_start_offsets, require_grid_multiple


@dataclass(frozen=True, slots=True)
class CandidateConfig:
    time_stride_s: int = 600
    roll_step_deg: float = 4.0
    max_candidates_total: int | None = 512
    cap_strategy: str = "balanced_stride"
    duration_values_s: tuple[int, ...] | None = None
    roll_values_deg: tuple[float, ...] | None = None
    debug_candidate_limit: int = 50

    def as_status_dict(self) -> dict[str, Any]:
        return {
            "time_stride_s": self.time_stride_s,
            "roll_step_deg": self.roll_step_deg,
            "max_candidates_total": self.max_candidates_total,
            "cap_strategy": self.cap_strategy,
            "duration_values_s": list(self.duration_values_s) if self.duration_values_s else None,
            "roll_values_deg": list(self.roll_values_deg) if self.roll_values_deg else None,
            "debug_candidate_limit": self.debug_candidate_limit,
        }


DEFAULT_CANDIDATE_CONFIG = CandidateConfig()


@dataclass(frozen=True, slots=True)
class StripCandidate:
    candidate_id: str
    satellite_id: str
    start_offset_s: int
    start_time: str
    duration_s: int
    roll_deg: float
    theta_inner_deg: float
    theta_outer_deg: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "satellite_id": self.satellite_id,
            "start_offset_s": self.start_offset_s,
            "start_time": self.start_time,
            "duration_s": self.duration_s,
            "roll_deg": self.roll_deg,
            "theta_inner_deg": self.theta_inner_deg,
            "theta_outer_deg": self.theta_outer_deg,
        }


@dataclass(frozen=True, slots=True)
class CandidateSummary:
    candidate_count: int
    full_candidate_count: int
    removed_by_cap_count: int
    truncated_by_cap: bool
    active_caps: dict[str, Any]
    per_satellite: dict[str, int]
    per_roll: dict[str, int]
    per_duration: dict[str, int]
    per_time_bucket: dict[str, int]
    first_candidate_ids: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "candidate_count": self.candidate_count,
            "full_candidate_count": self.full_candidate_count,
            "removed_by_cap_count": self.removed_by_cap_count,
            "truncated_by_cap": self.truncated_by_cap,
            "active_caps": self.active_caps,
            "per_satellite": self.per_satellite,
            "per_roll": self.per_roll,
            "per_duration": self.per_duration,
            "per_time_bucket": self.per_time_bucket,
            "first_candidate_ids": list(self.first_candidate_ids),
        }


def load_candidate_config(config_dir: Path | None) -> CandidateConfig:
    if config_dir is None or not config_dir:
        return CandidateConfig()
    path = config_dir / "config.yaml"
    if not path.is_file():
        return CandidateConfig()
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"{path} must contain a mapping")
    section = raw.get("candidate_generation", raw)
    if not isinstance(section, dict):
        raise ValueError(f"{path}: candidate_generation must be a mapping")
    max_candidates_raw = section.get(
        "max_candidates_total", DEFAULT_CANDIDATE_CONFIG.max_candidates_total
    )
    cap_strategy = str(
        section.get("cap_strategy", DEFAULT_CANDIDATE_CONFIG.cap_strategy)
    )
    if cap_strategy not in {"balanced_stride", "first_n"}:
        raise ValueError(
            f"{path}: candidate_generation.cap_strategy must be balanced_stride or first_n"
        )
    return CandidateConfig(
        time_stride_s=int(section.get("time_stride_s", DEFAULT_CANDIDATE_CONFIG.time_stride_s)),
        roll_step_deg=float(section.get("roll_step_deg", DEFAULT_CANDIDATE_CONFIG.roll_step_deg)),
        max_candidates_total=(
            int(max_candidates_raw)
            if max_candidates_raw is not None
            else None
        ),
        cap_strategy=cap_strategy,
        duration_values_s=(
            tuple(int(v) for v in section["duration_values_s"])
            if section.get("duration_values_s") is not None
            else None
        ),
        roll_values_deg=(
            tuple(float(v) for v in section["roll_values_deg"])
            if section.get("roll_values_deg") is not None
            else None
        ),
        debug_candidate_limit=int(
            section.get("debug_candidate_limit", DEFAULT_CANDIDATE_CONFIG.debug_candidate_limit)
        ),
    )


def _valid_edge_angles(satellite: Satellite, roll_deg: float) -> tuple[float, float] | None:
    half_fov = 0.5 * satellite.sensor.cross_track_fov_deg
    theta_inner = abs(roll_deg) - half_fov
    theta_outer = abs(roll_deg) + half_fov
    if theta_inner < satellite.sensor.min_edge_off_nadir_deg - 1.0e-9:
        return None
    if theta_outer > satellite.sensor.max_edge_off_nadir_deg + 1.0e-9:
        return None
    return (theta_inner, theta_outer)


def _duration_values(case: RegionalCoverageCase, satellite: Satellite, config: CandidateConfig) -> tuple[int, ...]:
    step = case.manifest.time_step_s
    if config.duration_values_s is not None:
        raw_values = config.duration_values_s
    else:
        min_dur = int(round(satellite.sensor.min_strip_duration_s))
        max_dur = int(round(satellite.sensor.max_strip_duration_s))
        midpoint = ((min_dur + max_dur) // (2 * step)) * step
        raw_values = (min_dur, midpoint, max_dur)
    values: list[int] = []
    for raw in raw_values:
        try:
            duration = require_grid_multiple(raw, step, field="duration_s")
        except ValueError:
            continue
        if duration < satellite.sensor.min_strip_duration_s - 1.0e-9:
            continue
        if duration > satellite.sensor.max_strip_duration_s + 1.0e-9:
            continue
        values.append(duration)
    return tuple(sorted(set(values)))


def _roll_values(satellite: Satellite, config: CandidateConfig) -> tuple[float, ...]:
    if config.roll_values_deg is not None:
        raw_values = config.roll_values_deg
    else:
        half_fov = 0.5 * satellite.sensor.cross_track_fov_deg
        low = satellite.sensor.min_edge_off_nadir_deg + half_fov
        high = satellite.sensor.max_edge_off_nadir_deg - half_fov
        if low > high + 1.0e-9:
            return ()
        positive: list[float] = []
        value = low
        while value <= high + 1.0e-9:
            positive.append(round(value, 6))
            value += config.roll_step_deg
        if positive[-1] < high - 1.0e-9:
            positive.append(round(high, 6))
        raw_values = tuple(-v for v in reversed(positive)) + tuple(positive)
    valid = []
    for roll in raw_values:
        if abs(roll) <= 1.0e-12:
            continue
        if _valid_edge_angles(satellite, roll) is not None:
            valid.append(round(float(roll), 6))
    return tuple(sorted(set(valid)))


def _candidate_id(satellite_id: str, duration_s: int, roll_deg: float, start_offset_s: int) -> str:
    return f"{satellite_id}|dur={duration_s:04d}|roll={roll_deg:+08.3f}|start={start_offset_s:07d}"


def _time_bucket_label(start_offset_s: int) -> str:
    bucket_start = (start_offset_s // 3600) * 3600
    return f"{bucket_start:07d}-{bucket_start + 3599:07d}"


def _apply_candidate_cap(
    candidates: list[StripCandidate], config: CandidateConfig
) -> tuple[list[StripCandidate], bool]:
    cap = config.max_candidates_total
    if cap is None or cap >= len(candidates):
        return candidates, False
    if cap <= 0:
        return [], bool(candidates)
    if config.cap_strategy == "first_n":
        return candidates[:cap], True
    if config.cap_strategy != "balanced_stride":
        raise ValueError(f"unsupported candidate cap strategy {config.cap_strategy!r}")

    total = len(candidates)
    indices = [(index * total) // cap for index in range(cap)]
    return [candidates[index] for index in indices], True


def generate_candidates(
    case: RegionalCoverageCase, config: CandidateConfig
) -> tuple[list[StripCandidate], CandidateSummary]:
    full_candidates: list[StripCandidate] = []
    for satellite_id in sorted(case.satellites):
        satellite = case.satellites[satellite_id]
        durations = _duration_values(case, satellite, config)
        rolls = _roll_values(satellite, config)
        starts = tuple(iter_start_offsets(case.manifest, stride_s=config.time_stride_s))
        for duration_s in durations:
            for roll_deg in rolls:
                edge_angles = _valid_edge_angles(satellite, roll_deg)
                if edge_angles is None:
                    continue
                for start_offset_s in starts:
                    if start_offset_s + duration_s > case.manifest.horizon_seconds:
                        continue
                    full_candidates.append(
                        StripCandidate(
                            candidate_id=_candidate_id(
                                satellite_id, duration_s, roll_deg, start_offset_s
                            ),
                            satellite_id=satellite_id,
                            start_offset_s=start_offset_s,
                            start_time=iso_at_offset(case.manifest, start_offset_s),
                            duration_s=duration_s,
                            roll_deg=roll_deg,
                            theta_inner_deg=edge_angles[0],
                            theta_outer_deg=edge_angles[1],
                        )
                    )
    candidates, truncated = _apply_candidate_cap(full_candidates, config)
    per_satellite = Counter(candidate.satellite_id for candidate in candidates)
    per_roll = Counter(f"{candidate.roll_deg:.6f}" for candidate in candidates)
    per_duration = Counter(str(candidate.duration_s) for candidate in candidates)
    per_time_bucket = Counter(_time_bucket_label(candidate.start_offset_s) for candidate in candidates)
    summary = CandidateSummary(
        candidate_count=len(candidates),
        full_candidate_count=len(full_candidates),
        removed_by_cap_count=max(0, len(full_candidates) - len(candidates)),
        truncated_by_cap=truncated,
        active_caps={
            "max_candidates_total": config.max_candidates_total,
            "cap_strategy": config.cap_strategy,
            "time_stride_s": config.time_stride_s,
            "default_duration_policy": (
                "min_mid_max" if config.duration_values_s is None else "configured"
            ),
            "default_roll_policy": (
                "edge-valid symmetric roll grid"
                if config.roll_values_deg is None
                else "configured"
            ),
        },
        per_satellite=dict(sorted(per_satellite.items())),
        per_roll=dict(sorted(per_roll.items(), key=lambda kv: float(kv[0]))),
        per_duration=dict(sorted(per_duration.items(), key=lambda kv: int(kv[0]))),
        per_time_bucket=dict(sorted(per_time_bucket.items())),
        first_candidate_ids=tuple(c.candidate_id for c in candidates[:10]),
    )
    return candidates, summary
