"""Candidate observation generation for the standalone MWIS solver."""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import timedelta
from typing import Any

from .case_io import AeosspCase, Satellite, Task, iso_z
from .geometry import PropagationContext, initial_slew_feasible, observation_geometry_valid


@dataclass(frozen=True, slots=True)
class CandidateConfig:
    candidate_stride_multiplier: int = 1
    max_candidates: int | None = None
    max_candidates_per_task: int | None = None
    candidate_workers: int = 1
    debug: bool = False

    @classmethod
    def from_mapping(cls, payload: dict[str, Any] | None) -> "CandidateConfig":
        payload = payload or {}
        return cls(
            candidate_stride_multiplier=max(1, int(payload.get("candidate_stride_multiplier", 1))),
            max_candidates=_optional_positive_int(payload.get("max_candidates")),
            max_candidates_per_task=_optional_positive_int(
                payload.get("max_candidates_per_task")
            ),
            candidate_workers=_positive_int(payload.get("candidate_workers", 1)),
            debug=bool(payload.get("debug", False)),
        )

    def as_status_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class Candidate:
    candidate_id: str
    satellite_id: str
    task_id: str
    start_offset_s: int
    end_offset_s: int
    start_time: str
    end_time: str
    task_weight: float
    duration_s: int

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class CandidateSummary:
    candidate_count: int = 0
    per_satellite_candidate_counts: dict[str, int] = field(default_factory=dict)
    per_task_candidate_counts: dict[str, int] = field(default_factory=dict)
    skipped_sensor_mismatch: int = 0
    skipped_geometry: int = 0
    skipped_initial_slew: int = 0
    skipped_cap: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "candidate_count": self.candidate_count,
            "per_satellite_candidate_counts": dict(sorted(self.per_satellite_candidate_counts.items())),
            "per_task_candidate_counts": dict(sorted(self.per_task_candidate_counts.items())),
            "skipped_sensor_mismatch": self.skipped_sensor_mismatch,
            "skipped_geometry": self.skipped_geometry,
            "skipped_initial_slew": self.skipped_initial_slew,
            "skipped_cap": self.skipped_cap,
        }

    def as_debug_dict(self, case: AeosspCase) -> dict[str, Any]:
        zero_candidate_task_ids = sorted(
            task.task_id
            for task in case.tasks.values()
            if self.per_task_candidate_counts.get(task.task_id, 0) == 0
        )
        zero_candidate_task_counts_by_sensor: dict[str, int] = {}
        for task_id in zero_candidate_task_ids:
            sensor_type = case.tasks[task_id].required_sensor_type
            zero_candidate_task_counts_by_sensor[sensor_type] = (
                zero_candidate_task_counts_by_sensor.get(sensor_type, 0) + 1
            )
        return {
            **self.as_dict(),
            "task_count": len(case.tasks),
            "satellite_count": len(case.satellites),
            "zero_candidate_task_count": len(zero_candidate_task_ids),
            "zero_candidate_task_counts_by_sensor": dict(
                sorted(zero_candidate_task_counts_by_sensor.items())
            ),
            "zero_candidate_task_ids": zero_candidate_task_ids,
        }


@dataclass(frozen=True, slots=True)
class _CandidateEvent:
    satellite_id: str
    task_id: str
    start_offset_s: int
    candidate: Candidate | None = None
    skipped_geometry: bool = False
    skipped_initial_slew: bool = False


@dataclass(frozen=True, slots=True)
class _SatelliteCandidateEvents:
    satellite_id: str
    events: list[_CandidateEvent]
    skipped_sensor_mismatch: int


def _optional_positive_int(value: Any) -> int | None:
    if value is None:
        return None
    parsed = int(value)
    if parsed <= 0:
        raise ValueError("candidate cap values must be positive integers")
    return parsed


def _positive_int(value: Any) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise ValueError("candidate worker count must be a positive integer")
    return parsed


def start_offsets_for_task(
    case: AeosspCase,
    task: Task,
    *,
    stride_multiplier: int = 1,
) -> list[int]:
    step_s = case.mission.action_time_step_s * max(1, stride_multiplier)
    first_offset = int(round((task.release_time - case.mission.horizon_start).total_seconds()))
    last_offset = int(
        round((task.due_time - case.mission.horizon_start).total_seconds())
    ) - task.required_duration_s
    if last_offset < first_offset:
        return []
    return list(range(first_offset, last_offset + 1, step_s))


def _sensor_matches(satellite: Satellite, task: Task) -> bool:
    return satellite.sensor_type == task.required_sensor_type


def _candidate_from_start(
    *,
    case: AeosspCase,
    satellite: Satellite,
    task: Task,
    start_offset_s: int,
) -> Candidate:
    start_time = case.mission.horizon_start + timedelta(seconds=start_offset_s)
    end_offset_s = start_offset_s + task.required_duration_s
    end_time = case.mission.horizon_start + timedelta(seconds=end_offset_s)
    return Candidate(
        candidate_id=f"{satellite.satellite_id}|{task.task_id}|{start_offset_s}",
        satellite_id=satellite.satellite_id,
        task_id=task.task_id,
        start_offset_s=start_offset_s,
        end_offset_s=end_offset_s,
        start_time=iso_z(start_time),
        end_time=iso_z(end_time),
        task_weight=task.weight,
        duration_s=task.required_duration_s,
    )


def _empty_summary(case: AeosspCase) -> CandidateSummary:
    return CandidateSummary(
        per_satellite_candidate_counts={
            satellite.satellite_id: 0
            for satellite in sorted(
                case.satellites.values(),
                key=lambda item: item.satellite_id,
            )
        },
        per_task_candidate_counts={
            task.task_id: 0
            for task in sorted(case.tasks.values(), key=lambda item: item.task_id)
        },
    )


def _satellite_candidate_events(
    case: AeosspCase,
    config: CandidateConfig,
    satellite_id: str,
) -> _SatelliteCandidateEvents:
    satellite = case.satellites[satellite_id]
    step_s = float(min(case.mission.action_time_step_s, case.mission.geometry_sample_step_s))
    propagation = PropagationContext({satellite.satellite_id: satellite}, step_s=step_s)
    events: list[_CandidateEvent] = []
    skipped_sensor_mismatch = 0
    for task in sorted(case.tasks.values(), key=lambda item: item.task_id):
        offsets = start_offsets_for_task(
            case,
            task,
            stride_multiplier=config.candidate_stride_multiplier,
        )
        if not _sensor_matches(satellite, task):
            skipped_sensor_mismatch += len(offsets)
            continue
        for start_offset_s in offsets:
            start_time = case.mission.horizon_start + timedelta(seconds=start_offset_s)
            end_time = start_time + timedelta(seconds=task.required_duration_s)
            if not observation_geometry_valid(
                mission=case.mission,
                satellite=satellite,
                task=task,
                propagation=propagation,
                start_time=start_time,
                end_time=end_time,
            ):
                events.append(
                    _CandidateEvent(
                        satellite_id=satellite.satellite_id,
                        task_id=task.task_id,
                        start_offset_s=start_offset_s,
                        skipped_geometry=True,
                    )
                )
                continue
            if not initial_slew_feasible(
                mission=case.mission,
                satellite=satellite,
                task=task,
                propagation=propagation,
                start_time=start_time,
            ):
                events.append(
                    _CandidateEvent(
                        satellite_id=satellite.satellite_id,
                        task_id=task.task_id,
                        start_offset_s=start_offset_s,
                        skipped_initial_slew=True,
                    )
                )
                continue
            events.append(
                _CandidateEvent(
                    satellite_id=satellite.satellite_id,
                    task_id=task.task_id,
                    start_offset_s=start_offset_s,
                    candidate=_candidate_from_start(
                        case=case,
                        satellite=satellite,
                        task=task,
                        start_offset_s=start_offset_s,
                    ),
                )
            )
    return _SatelliteCandidateEvents(
        satellite_id=satellite.satellite_id,
        events=events,
        skipped_sensor_mismatch=skipped_sensor_mismatch,
    )


def _replay_candidate_events(
    case: AeosspCase,
    config: CandidateConfig,
    satellite_results: list[_SatelliteCandidateEvents],
) -> tuple[list[Candidate], CandidateSummary]:
    summary = _empty_summary(case)
    candidates: list[Candidate] = []
    results_by_satellite = {
        result.satellite_id: result for result in satellite_results
    }
    for satellite_id in sorted(case.satellites):
        result = results_by_satellite[satellite_id]
        summary.skipped_sensor_mismatch += result.skipped_sensor_mismatch
        events = sorted(
            result.events,
            key=lambda item: (item.satellite_id, item.task_id, item.start_offset_s),
        )
        for event in events:
            if (
                config.max_candidates is not None
                and len(candidates) >= config.max_candidates
            ):
                summary.skipped_cap += 1
                continue
            if (
                config.max_candidates_per_task is not None
                and summary.per_task_candidate_counts[event.task_id]
                >= config.max_candidates_per_task
            ):
                summary.skipped_cap += 1
                continue
            if event.skipped_geometry:
                summary.skipped_geometry += 1
                continue
            if event.skipped_initial_slew:
                summary.skipped_initial_slew += 1
                continue
            if event.candidate is None:
                raise RuntimeError("candidate event did not include an outcome")
            candidates.append(event.candidate)
            summary.candidate_count += 1
            summary.per_satellite_candidate_counts[event.satellite_id] += 1
            summary.per_task_candidate_counts[event.task_id] += 1
    return candidates, summary


def _generate_candidates_serial(
    case: AeosspCase,
    config: CandidateConfig,
) -> tuple[list[Candidate], CandidateSummary]:
    summary = _empty_summary(case)
    candidates: list[Candidate] = []
    step_s = float(min(case.mission.action_time_step_s, case.mission.geometry_sample_step_s))
    propagation = PropagationContext(case.satellites, step_s=step_s)

    for satellite in sorted(case.satellites.values(), key=lambda item: item.satellite_id):
        for task in sorted(case.tasks.values(), key=lambda item: item.task_id):
            if not _sensor_matches(satellite, task):
                summary.skipped_sensor_mismatch += len(
                    start_offsets_for_task(
                        case,
                        task,
                        stride_multiplier=config.candidate_stride_multiplier,
                    )
                )
                continue
            for start_offset_s in start_offsets_for_task(
                case,
                task,
                stride_multiplier=config.candidate_stride_multiplier,
            ):
                if (
                    config.max_candidates is not None
                    and len(candidates) >= config.max_candidates
                ):
                    summary.skipped_cap += 1
                    continue
                if (
                    config.max_candidates_per_task is not None
                    and summary.per_task_candidate_counts[task.task_id]
                    >= config.max_candidates_per_task
                ):
                    summary.skipped_cap += 1
                    continue
                start_time = case.mission.horizon_start + timedelta(seconds=start_offset_s)
                end_time = start_time + timedelta(seconds=task.required_duration_s)
                if not observation_geometry_valid(
                    mission=case.mission,
                    satellite=satellite,
                    task=task,
                    propagation=propagation,
                    start_time=start_time,
                    end_time=end_time,
                ):
                    summary.skipped_geometry += 1
                    continue
                if not initial_slew_feasible(
                    mission=case.mission,
                    satellite=satellite,
                    task=task,
                    propagation=propagation,
                    start_time=start_time,
                ):
                    summary.skipped_initial_slew += 1
                    continue
                candidate = _candidate_from_start(
                    case=case,
                    satellite=satellite,
                    task=task,
                    start_offset_s=start_offset_s,
                )
                candidates.append(candidate)
                summary.candidate_count += 1
                summary.per_satellite_candidate_counts[satellite.satellite_id] += 1
                summary.per_task_candidate_counts[task.task_id] += 1
    return candidates, summary


def _generate_candidates_parallel(
    case: AeosspCase,
    config: CandidateConfig,
) -> tuple[list[Candidate], CandidateSummary]:
    satellite_ids = sorted(case.satellites)
    max_workers = min(config.candidate_workers, len(satellite_ids))
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        satellite_results = list(
            executor.map(
                _satellite_candidate_events,
                [case] * len(satellite_ids),
                [config] * len(satellite_ids),
                satellite_ids,
            )
        )
    return _replay_candidate_events(case, config, satellite_results)


def generate_candidates(
    case: AeosspCase,
    config: CandidateConfig | None = None,
) -> tuple[list[Candidate], CandidateSummary]:
    config = config or CandidateConfig()
    if config.candidate_workers <= 1 or len(case.satellites) <= 1:
        return _generate_candidates_serial(case, config)
    return _generate_candidates_parallel(case, config)
