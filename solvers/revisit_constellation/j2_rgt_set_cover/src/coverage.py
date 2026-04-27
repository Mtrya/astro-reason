"""RAAN-phased candidate expansion and repeat-cycle coverage envelopes."""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
import math
import os

import brahe
import numpy as np

from .case_io import RevisitCase, Target
from .rgt import RgtTemplate, brouwer_j2_state_eci, ensure_brahe_ready
from .time_utils import datetime_to_epoch


NUMERICAL_EPS = 1.0e-9


@dataclass(frozen=True, slots=True)
class CoverageConfig:
    raan_count: int = 24
    raan_start_deg: float = 0.0
    sample_step_sec: float = 300.0
    keep_samples_per_window: int = 4
    worker_count: int = 1

    @classmethod
    def from_mapping(cls, payload: dict[str, Any]) -> "CoverageConfig":
        defaults = cls()
        raw = payload.get("coverage", payload)
        if not isinstance(raw, dict):
            raise ValueError("coverage config must be a mapping/object")
        return cls(
            raan_count=int(raw.get("raan_count", defaults.raan_count)),
            raan_start_deg=float(raw.get("raan_start_deg", defaults.raan_start_deg)),
            sample_step_sec=float(raw.get("sample_step_sec", defaults.sample_step_sec)),
            keep_samples_per_window=int(
                raw.get("keep_samples_per_window", defaults.keep_samples_per_window)
            ),
            worker_count=int(raw.get("worker_count", defaults.worker_count)),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "raan_count": self.raan_count,
            "raan_start_deg": self.raan_start_deg,
            "sample_step_sec": self.sample_step_sec,
            "keep_samples_per_window": self.keep_samples_per_window,
            "worker_count": self.worker_count,
        }


@dataclass(frozen=True, slots=True)
class RaanCandidate:
    candidate_id: str
    template_id: str
    repeat_days: int
    revolutions: int
    inclination_deg: float
    semi_major_axis_m: float
    altitude_m: float
    eccentricity: float
    argument_of_perigee_deg: float
    mean_anomaly_deg: float
    repeat_period_sec: float
    raan_deg: float
    template_closure_error_m: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "template_id": self.template_id,
            "repeat_days": self.repeat_days,
            "revolutions": self.revolutions,
            "inclination_deg": self.inclination_deg,
            "semi_major_axis_m": self.semi_major_axis_m,
            "altitude_m": self.altitude_m,
            "eccentricity": self.eccentricity,
            "argument_of_perigee_deg": self.argument_of_perigee_deg,
            "mean_anomaly_deg": self.mean_anomaly_deg,
            "repeat_period_sec": self.repeat_period_sec,
            "raan_deg": self.raan_deg,
            "template_closure_error_m": self.template_closure_error_m,
        }


@dataclass(frozen=True, slots=True)
class VisibilitySample:
    offset_sec: float
    elevation_deg: float
    slant_range_m: float
    off_nadir_deg: float
    visible: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "offset_sec": self.offset_sec,
            "elevation_deg": self.elevation_deg,
            "slant_range_m": self.slant_range_m,
            "off_nadir_deg": self.off_nadir_deg,
            "visible": self.visible,
        }


@dataclass(frozen=True, slots=True)
class VisibilityWindow:
    window_id: str
    candidate_id: str
    template_id: str
    target_id: str
    start_offset_sec: float
    end_offset_sec: float
    midpoint_offset_sec: float
    duration_sec: float
    max_elevation_deg: float
    min_slant_range_m: float
    min_off_nadir_deg: float
    sample_count: int
    samples: tuple[VisibilitySample, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "window_id": self.window_id,
            "candidate_id": self.candidate_id,
            "template_id": self.template_id,
            "target_id": self.target_id,
            "start_offset_sec": self.start_offset_sec,
            "end_offset_sec": self.end_offset_sec,
            "midpoint_offset_sec": self.midpoint_offset_sec,
            "duration_sec": self.duration_sec,
            "max_elevation_deg": self.max_elevation_deg,
            "min_slant_range_m": self.min_slant_range_m,
            "min_off_nadir_deg": self.min_off_nadir_deg,
            "sample_count": self.sample_count,
            "samples": [sample.as_dict() for sample in self.samples],
        }


@dataclass(frozen=True, slots=True)
class CoverageSummary:
    candidates: list[RaanCandidate]
    windows: list[VisibilityWindow]
    target_to_candidates: dict[str, list[str]]
    candidate_to_targets: dict[str, list[str]]
    uncovered_target_ids: list[str]
    config: CoverageConfig
    sample_offset_count: int

    def as_debug_dict(self) -> dict[str, Any]:
        target_coverage = [
            {
                "target_id": target_id,
                "covering_candidate_count": len(candidate_ids),
                "candidate_ids": candidate_ids,
            }
            for target_id, candidate_ids in sorted(self.target_to_candidates.items())
        ]
        return {
            "config": self.config.as_dict(),
            "candidate_count": len(self.candidates),
            "visibility_window_count": len(self.windows),
            "sample_offset_count": self.sample_offset_count,
            "candidates": [candidate.as_dict() for candidate in self.candidates],
            "target_to_candidates": self.target_to_candidates,
            "candidate_to_targets": self.candidate_to_targets,
            "uncovered_target_ids": self.uncovered_target_ids,
            "target_coverage": target_coverage,
            "difficult_targets": sorted(
                target_coverage,
                key=lambda item: (
                    item["covering_candidate_count"],
                    item["target_id"],
                ),
            )[:10],
            "candidate_coverage": [
                {
                    "candidate_id": candidate.candidate_id,
                    "template_id": candidate.template_id,
                    "raan_deg": candidate.raan_deg,
                    "covered_target_count": len(
                        self.candidate_to_targets.get(candidate.candidate_id, [])
                    ),
                    "covered_target_ids": self.candidate_to_targets.get(
                        candidate.candidate_id, []
                    ),
                    "template_closure_error_m": candidate.template_closure_error_m,
                }
                for candidate in self.candidates
            ],
            "windows": [window.as_dict() for window in self.windows],
        }

    def as_status_dict(self) -> dict[str, Any]:
        return {
            "candidate_count": len(self.candidates),
            "visibility_window_count": len(self.windows),
            "covered_target_count": len(self.target_to_candidates),
            "uncovered_target_count": len(self.uncovered_target_ids),
            "uncovered_target_ids": self.uncovered_target_ids,
            "sample_offset_count": self.sample_offset_count,
            "config": self.config.as_dict(),
        }


def angle_between_deg(vector_a: np.ndarray, vector_b: np.ndarray) -> float:
    norm_a = float(np.linalg.norm(vector_a))
    norm_b = float(np.linalg.norm(vector_b))
    if norm_a <= NUMERICAL_EPS or norm_b <= NUMERICAL_EPS:
        return 0.0
    cosine = float(np.dot(vector_a, vector_b) / (norm_a * norm_b))
    cosine = max(-1.0, min(1.0, cosine))
    return math.degrees(math.acos(cosine))


def _raan_token(raan_deg: float) -> str:
    return f"{raan_deg:07.3f}".replace("-", "m").replace(".", "p")


def expand_raan_candidates(
    templates: list[RgtTemplate],
    config: CoverageConfig,
) -> list[RaanCandidate]:
    if config.raan_count <= 0:
        raise ValueError("coverage.raan_count must be > 0")
    accepted = sorted(
        [template for template in templates if template.accepted],
        key=lambda item: item.template_id,
    )
    candidates: list[RaanCandidate] = []
    for template in accepted:
        closure_error = math.inf
        if template.closure is not None:
            closure_error = template.closure.surface_error_m
        for index in range(config.raan_count):
            raan_deg = (
                config.raan_start_deg + 360.0 * index / config.raan_count
            ) % 360.0
            candidate_id = f"{template.template_id}_raan{_raan_token(raan_deg)}"
            candidates.append(
                RaanCandidate(
                    candidate_id=candidate_id,
                    template_id=template.template_id,
                    repeat_days=template.repeat_days,
                    revolutions=template.revolutions,
                    inclination_deg=template.inclination_deg,
                    semi_major_axis_m=template.semi_major_axis_m,
                    altitude_m=template.altitude_m,
                    eccentricity=template.eccentricity,
                    argument_of_perigee_deg=template.argument_of_perigee_deg,
                    mean_anomaly_deg=template.mean_anomaly_deg,
                    repeat_period_sec=template.repeat_period_sec,
                    raan_deg=raan_deg,
                    template_closure_error_m=closure_error,
                )
            )
    return sorted(candidates, key=lambda item: item.candidate_id)


def candidate_state_eci(
    candidate: RaanCandidate,
    *,
    offset_sec: float,
) -> tuple[float, float, float, float, float, float]:
    return brouwer_j2_state_eci(
        candidate.semi_major_axis_m,
        candidate.inclination_deg,
        eccentricity=candidate.eccentricity,
        raan_deg=candidate.raan_deg,
        argument_of_perigee_deg=candidate.argument_of_perigee_deg,
        mean_anomaly_deg=candidate.mean_anomaly_deg,
        duration_sec=offset_sec,
    )


def geometry_sample_from_state(
    *,
    case: RevisitCase,
    target: Target,
    state_eci_m_mps: tuple[float, float, float, float, float, float],
    instant: datetime,
    offset_sec: float,
) -> VisibilitySample:
    ensure_brahe_ready()
    epoch = datetime_to_epoch(instant)
    state_eci = np.asarray(state_eci_m_mps, dtype=float)
    state_ecef = np.asarray(brahe.state_eci_to_ecef(epoch, state_eci), dtype=float)
    target_ecef = np.asarray(target.ecef_position_m, dtype=float)
    relative_enz = np.asarray(
        brahe.relative_position_ecef_to_enz(
            target_ecef,
            state_ecef[:3],
            brahe.EllipsoidalConversionType.GEODETIC,
        ),
        dtype=float,
    )
    aer = np.asarray(
        brahe.position_enz_to_azel(relative_enz, brahe.AngleFormat.DEGREES),
        dtype=float,
    )
    elevation_deg = float(aer[1])
    slant_range_m = float(aer[2])
    target_eci = np.asarray(brahe.position_ecef_to_eci(epoch, target_ecef), dtype=float)
    off_nadir_deg = angle_between_deg(-state_eci[:3], target_eci - state_eci[:3])
    max_allowed_range_m = min(
        target.max_slant_range_m,
        case.satellite_model.sensor.max_range_m,
    )
    visible = (
        elevation_deg + NUMERICAL_EPS >= target.min_elevation_deg
        and slant_range_m <= max_allowed_range_m + NUMERICAL_EPS
        and off_nadir_deg
        <= case.satellite_model.sensor.max_off_nadir_angle_deg + NUMERICAL_EPS
    )
    return VisibilitySample(
        offset_sec=offset_sec,
        elevation_deg=elevation_deg,
        slant_range_m=slant_range_m,
        off_nadir_deg=off_nadir_deg,
        visible=visible,
    )


def _thin_samples(
    samples: list[VisibilitySample],
    keep: int,
) -> tuple[VisibilitySample, ...]:
    if keep <= 0 or len(samples) <= keep:
        return tuple(samples)
    if keep == 1:
        return (samples[len(samples) // 2],)
    indexes = {
        round(index * (len(samples) - 1) / (keep - 1))
        for index in range(keep)
    }
    return tuple(samples[index] for index in sorted(indexes))


def group_visible_samples(
    *,
    candidate_id: str,
    template_id: str,
    target_id: str,
    repeat_period_sec: float,
    sample_step_sec: float,
    min_duration_sec: float,
    samples: list[VisibilitySample],
    keep_samples_per_window: int,
) -> list[VisibilityWindow]:
    windows: list[VisibilityWindow] = []
    current: list[VisibilitySample] = []

    def flush() -> None:
        if not current:
            return
        start_offset = current[0].offset_sec
        end_offset = min(repeat_period_sec, current[-1].offset_sec + sample_step_sec)
        duration_sec = end_offset - start_offset
        if duration_sec + NUMERICAL_EPS < min_duration_sec:
            return
        window_index = len(windows)
        windows.append(
            VisibilityWindow(
                window_id=f"{candidate_id}__{target_id}__win{window_index:04d}",
                candidate_id=candidate_id,
                template_id=template_id,
                target_id=target_id,
                start_offset_sec=start_offset,
                end_offset_sec=end_offset,
                midpoint_offset_sec=start_offset + duration_sec / 2.0,
                duration_sec=duration_sec,
                max_elevation_deg=max(sample.elevation_deg for sample in current),
                min_slant_range_m=min(sample.slant_range_m for sample in current),
                min_off_nadir_deg=min(sample.off_nadir_deg for sample in current),
                sample_count=len(current),
                samples=_thin_samples(current, keep_samples_per_window),
            )
        )

    for sample in samples:
        if sample.visible:
            current.append(sample)
            continue
        flush()
        current = []
    flush()
    return windows


def repeat_cycle_offsets(repeat_period_sec: float, sample_step_sec: float) -> list[float]:
    if sample_step_sec <= 0.0:
        raise ValueError("coverage.sample_step_sec must be > 0")
    count = int(math.floor(repeat_period_sec / sample_step_sec))
    offsets = [index * sample_step_sec for index in range(count + 1)]
    if not offsets or abs(offsets[-1] - repeat_period_sec) > NUMERICAL_EPS:
        offsets.append(repeat_period_sec)
    return [float(offset) for offset in offsets]


def _candidate_visibility_windows(
    args: tuple[RevisitCase, RaanCandidate, tuple[Target, ...], CoverageConfig]
) -> list[VisibilityWindow]:
    case, candidate, targets, config = args
    ensure_brahe_ready()
    offsets = repeat_cycle_offsets(candidate.repeat_period_sec, config.sample_step_sec)
    windows: list[VisibilityWindow] = []
    states = [
        candidate_state_eci(candidate, offset_sec=offset)
        for offset in offsets
    ]
    instants = [
        case.horizon_start + timedelta(seconds=offset)
        for offset in offsets
    ]
    for target in targets:
        samples = [
            geometry_sample_from_state(
                case=case,
                target=target,
                state_eci_m_mps=state,
                instant=instant,
                offset_sec=offset,
            )
            for state, instant, offset in zip(states, instants, offsets, strict=True)
        ]
        windows.extend(
            group_visible_samples(
                candidate_id=candidate.candidate_id,
                template_id=candidate.template_id,
                target_id=target.target_id,
                repeat_period_sec=candidate.repeat_period_sec,
                sample_step_sec=config.sample_step_sec,
                min_duration_sec=target.min_duration_sec,
                samples=samples,
                keep_samples_per_window=config.keep_samples_per_window,
            )
        )
    return windows


def _resolved_worker_count(config: CoverageConfig, candidate_count: int) -> int:
    if candidate_count <= 0:
        return 0
    configured = config.worker_count
    if configured <= 1:
        return 1
    return max(1, min(configured, candidate_count, os.cpu_count() or 1))


def build_coverage_summary(
    case: RevisitCase,
    templates: list[RgtTemplate],
    config: CoverageConfig,
) -> CoverageSummary:
    candidates = expand_raan_candidates(templates, config)
    targets = tuple(sorted(case.targets.values(), key=lambda item: item.target_id))
    worker_args = [(case, candidate, targets, config) for candidate in candidates]
    worker_count = _resolved_worker_count(config, len(candidates))
    windows: list[VisibilityWindow] = []
    if worker_count > 1 and worker_args:
        with ProcessPoolExecutor(max_workers=worker_count) as executor:
            for candidate_windows in executor.map(
                _candidate_visibility_windows,
                worker_args,
            ):
                windows.extend(candidate_windows)
    else:
        for item in worker_args:
            windows.extend(_candidate_visibility_windows(item))
    windows = sorted(
        windows,
        key=lambda item: (
            item.candidate_id,
            item.target_id,
            item.start_offset_sec,
            item.window_id,
        ),
    )
    candidate_to_targets = {
        candidate.candidate_id: sorted(
            {
                window.target_id
                for window in windows
                if window.candidate_id == candidate.candidate_id
            }
        )
        for candidate in candidates
    }
    target_to_candidates = {
        target.target_id: sorted(
            {
                window.candidate_id
                for window in windows
                if window.target_id == target.target_id
            }
        )
        for target in targets
    }
    target_to_candidates = {
        target_id: candidate_ids
        for target_id, candidate_ids in target_to_candidates.items()
        if candidate_ids
    }
    uncovered = [
        target.target_id
        for target in targets
        if target.target_id not in target_to_candidates
    ]
    max_period = max(
        (candidate.repeat_period_sec for candidate in candidates),
        default=0.0,
    )
    sample_offset_count = (
        0
        if max_period <= 0.0
        else len(repeat_cycle_offsets(max_period, config.sample_step_sec))
    )
    return CoverageSummary(
        candidates=candidates,
        windows=windows,
        target_to_candidates=target_to_candidates,
        candidate_to_targets=candidate_to_targets,
        uncovered_target_ids=uncovered,
        config=CoverageConfig(
            raan_count=config.raan_count,
            raan_start_deg=config.raan_start_deg,
            sample_step_sec=config.sample_step_sec,
            keep_samples_per_window=config.keep_samples_per_window,
            worker_count=worker_count,
        ),
        sample_offset_count=sample_offset_count,
    )
