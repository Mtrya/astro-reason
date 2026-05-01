"""Numerical certification gate for analytical RGT coverage claims."""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from typing import Any
import math
import os

from .case_io import RevisitCase, Target
from .coverage import (
    CoarseVisibilityHint,
    CoverageSummary,
    RaanCandidate,
    VisibilityWindow,
)


NUMERICAL_EPS = 1.0e-9


@dataclass(frozen=True, slots=True)
class CertificationConfig:
    max_claims_per_target: int = 64
    min_passing_claims_per_target: int = 8
    worker_count: int = 8
    max_selection_retries: int = 8
    opportunity_sample_step_sec: float = 60.0
    validation_sample_step_sec: float = 10.0
    refinement_propagation: str = "numerical_j2"
    elevation_safety_margin_deg: float = 0.0
    range_safety_margin_m: float = 15_000.0
    off_nadir_safety_margin_deg: float = 0.5

    @classmethod
    def from_mapping(cls, payload: dict[str, Any]) -> "CertificationConfig":
        defaults = cls()
        scheduling = payload.get("scheduling", {})
        if scheduling is None:
            scheduling = {}
        if not isinstance(scheduling, dict):
            raise ValueError("scheduling config must be a mapping/object")
        raw = payload.get("certification", {})
        if raw is None:
            raw = {}
        if not isinstance(raw, dict):
            raise ValueError("certification config must be a mapping/object")
        return cls(
            max_claims_per_target=int(
                raw.get(
                    "max_claims_per_target",
                    defaults.max_claims_per_target,
                )
            ),
            min_passing_claims_per_target=int(
                raw.get(
                    "min_passing_claims_per_target",
                    defaults.min_passing_claims_per_target,
                )
            ),
            worker_count=int(raw.get("worker_count", defaults.worker_count)),
            max_selection_retries=int(
                raw.get(
                    "max_selection_retries",
                    defaults.max_selection_retries,
                )
            ),
            opportunity_sample_step_sec=float(
                raw.get(
                    "opportunity_sample_step_sec",
                    scheduling.get(
                        "opportunity_sample_step_sec",
                        defaults.opportunity_sample_step_sec,
                    ),
                )
            ),
            validation_sample_step_sec=float(
                raw.get(
                    "validation_sample_step_sec",
                    scheduling.get(
                        "validation_sample_step_sec",
                        defaults.validation_sample_step_sec,
                    ),
                )
            ),
            refinement_propagation=str(
                raw.get(
                    "refinement_propagation",
                    scheduling.get(
                        "refinement_propagation",
                        defaults.refinement_propagation,
                    ),
                )
            ),
            elevation_safety_margin_deg=float(
                raw.get(
                    "elevation_safety_margin_deg",
                    scheduling.get(
                        "elevation_safety_margin_deg",
                        defaults.elevation_safety_margin_deg,
                    ),
                )
            ),
            range_safety_margin_m=float(
                raw.get(
                    "range_safety_margin_m",
                    scheduling.get(
                        "range_safety_margin_m",
                        defaults.range_safety_margin_m,
                    ),
                )
            ),
            off_nadir_safety_margin_deg=float(
                raw.get(
                    "off_nadir_safety_margin_deg",
                    scheduling.get(
                        "off_nadir_safety_margin_deg",
                        defaults.off_nadir_safety_margin_deg,
                    ),
                )
            ),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "max_claims_per_target": self.max_claims_per_target,
            "min_passing_claims_per_target": self.min_passing_claims_per_target,
            "worker_count": self.worker_count,
            "max_selection_retries": self.max_selection_retries,
            "opportunity_sample_step_sec": self.opportunity_sample_step_sec,
            "validation_sample_step_sec": self.validation_sample_step_sec,
            "refinement_propagation": self.refinement_propagation,
            "elevation_safety_margin_deg": self.elevation_safety_margin_deg,
            "range_safety_margin_m": self.range_safety_margin_m,
            "off_nadir_safety_margin_deg": self.off_nadir_safety_margin_deg,
        }


@dataclass(frozen=True, slots=True)
class AnalyticalCoverageClaim:
    claim_id: str
    rank: int
    candidate: RaanCandidate
    target_id: str
    required_satellites: int
    analytical_window_ids: tuple[str, ...]
    analytical_hint_ids: tuple[str, ...]
    analytical_max_gap_hours: float
    analytical_capped_gap_hours: float
    geometry_margin: float
    repeat_period_hours: float
    closure_error_m: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "rank": self.rank,
            "candidate_id": self.candidate.candidate_id,
            "template_id": self.candidate.template_id,
            "target_id": self.target_id,
            "required_satellites": self.required_satellites,
            "analytical_window_ids": list(self.analytical_window_ids),
            "analytical_hint_ids": list(self.analytical_hint_ids),
            "analytical_max_gap_hours": self.analytical_max_gap_hours,
            "analytical_capped_gap_hours": self.analytical_capped_gap_hours,
            "geometry_margin": self.geometry_margin,
            "repeat_period_hours": self.repeat_period_hours,
            "closure_error_m": self.closure_error_m,
        }


@dataclass(frozen=True, slots=True)
class CertifiedCoverage:
    certification_id: str
    claim: AnalyticalCoverageClaim
    refined_opportunity_count: int
    refined_midpoint_offsets_sec: tuple[float, ...]
    max_gap_hours: float
    capped_max_gap_hours: float
    meets_revisit: bool
    rejection_reason: str | None
    rejection_reasons: dict[str, int]

    @property
    def candidate(self) -> RaanCandidate:
        return self.claim.candidate

    @property
    def candidate_id(self) -> str:
        return self.claim.candidate.candidate_id

    @property
    def target_id(self) -> str:
        return self.claim.target_id

    @property
    def required_satellites(self) -> int:
        return self.claim.required_satellites

    def as_dict(self) -> dict[str, Any]:
        return {
            "certification_id": self.certification_id,
            "claim_id": self.claim.claim_id,
            "rank": self.claim.rank,
            "candidate_id": self.candidate_id,
            "target_id": self.target_id,
            "required_satellites": self.required_satellites,
            "refined_opportunity_count": self.refined_opportunity_count,
            "refined_midpoint_offsets_sec": list(self.refined_midpoint_offsets_sec),
            "max_gap_hours": self.max_gap_hours,
            "capped_max_gap_hours": self.capped_max_gap_hours,
            "meets_revisit": self.meets_revisit,
            "rejection_reason": self.rejection_reason,
            "rejection_reasons": self.rejection_reasons,
            "candidate": self.candidate.as_dict(),
        }


@dataclass(frozen=True, slots=True)
class CertificationSummary:
    claims: list[AnalyticalCoverageClaim]
    certified_records: list[CertifiedCoverage]
    target_summaries: dict[str, dict[str, Any]]
    rejected_reasons: dict[str, int]
    frontier_limited_target_ids: list[str]
    config: CertificationConfig

    @property
    def passing_records(self) -> list[CertifiedCoverage]:
        return [record for record in self.certified_records if record.meets_revisit]

    def as_debug_dict(self) -> dict[str, Any]:
        return {
            "config": self.config.as_dict(),
            "claim_count": len(self.claims),
            "checked_count": len(self.certified_records),
            "passed_count": len(self.passing_records),
            "failed_count": len(self.certified_records) - len(self.passing_records),
            "frontier_limited_target_ids": self.frontier_limited_target_ids,
            "rejected_reasons": self.rejected_reasons,
            "target_summaries": self.target_summaries,
            "claims": [claim.as_dict() for claim in self.claims],
            "certified_records": [
                record.as_dict() for record in self.certified_records
            ],
        }

    def as_status_dict(self) -> dict[str, Any]:
        certified_targets = sorted({record.target_id for record in self.passing_records})
        return {
            "claim_count": len(self.claims),
            "checked_count": len(self.certified_records),
            "passed_count": len(self.passing_records),
            "failed_count": len(self.certified_records) - len(self.passing_records),
            "certified_target_count": len(certified_targets),
            "certified_target_ids": certified_targets,
            "frontier_limited_target_count": len(self.frontier_limited_target_ids),
            "frontier_limited_target_ids": self.frontier_limited_target_ids,
            "rejected_reasons": self.rejected_reasons,
            "config": self.config.as_dict(),
        }


def satellites_required_for_target(candidate: RaanCandidate, target: Target) -> int:
    if target.expected_revisit_period_hours <= 0.0:
        raise ValueError(f"{target.target_id}.expected_revisit_period_hours must be > 0")
    repeat_period_hours = candidate.repeat_period_sec / 3600.0
    return max(1, int(math.ceil(repeat_period_hours / target.expected_revisit_period_hours)))


def _coverage_margin(
    *,
    case: RevisitCase,
    target_id: str,
    windows: list[VisibilityWindow],
    hints: list[CoarseVisibilityHint],
) -> float:
    target = case.targets[target_id]
    range_limit = min(target.max_slant_range_m, case.satellite_model.sensor.max_range_m)
    margins: list[float] = []
    for window in windows:
        margins.append(
            min(
                window.max_elevation_deg - target.min_elevation_deg,
                range_limit - window.min_slant_range_m,
                case.satellite_model.sensor.max_off_nadir_angle_deg
                - window.min_off_nadir_deg,
            )
        )
    margins.extend(hint.min_margin for hint in hints)
    return max(margins, default=-math.inf)


def _offset_max_gap_sec(horizon_sec: float, offsets_sec: list[float]) -> float:
    times = [0.0, *sorted(set(offsets_sec)), horizon_sec]
    return max(right - left for left, right in zip(times, times[1:]))


def _analytical_gap_hours(
    *,
    case: RevisitCase,
    candidate: RaanCandidate,
    required_satellites: int,
    windows: list[VisibilityWindow],
    hints: list[CoarseVisibilityHint],
) -> float:
    horizon_sec = (case.horizon_end - case.horizon_start).total_seconds()
    seed_offsets = [window.midpoint_offset_sec for window in windows]
    if not seed_offsets:
        seed_offsets = [hint.offset_sec for hint in hints]
    offsets: set[float] = set()
    repeat_sec = candidate.repeat_period_sec
    for seed_offset in seed_offsets:
        for phase_index in range(required_satellites):
            phase_offset = repeat_sec * phase_index / required_satellites
            shifted = seed_offset - phase_offset
            while shifted < -NUMERICAL_EPS:
                shifted += repeat_sec
            while shifted <= horizon_sec + NUMERICAL_EPS:
                offsets.add(round(min(max(0.0, shifted), horizon_sec), 6))
                shifted += repeat_sec
    if not offsets:
        return horizon_sec / 3600.0
    return _offset_max_gap_sec(horizon_sec, sorted(offsets)) / 3600.0


def build_analytical_claims(
    case: RevisitCase,
    coverage: CoverageSummary,
) -> list[AnalyticalCoverageClaim]:
    candidates = {candidate.candidate_id: candidate for candidate in coverage.candidates}
    windows_by_pair: dict[tuple[str, str], list[VisibilityWindow]] = {}
    hints_by_pair: dict[tuple[str, str], list[CoarseVisibilityHint]] = {}
    for window in coverage.windows:
        windows_by_pair.setdefault((window.candidate_id, window.target_id), []).append(window)
    for hint in coverage.hints:
        hints_by_pair.setdefault((hint.candidate_id, hint.target_id), []).append(hint)

    claims_by_target: dict[str, list[AnalyticalCoverageClaim]] = {}
    pair_keys = sorted(set(windows_by_pair) | set(hints_by_pair))
    for candidate_id, target_id in pair_keys:
        if candidate_id not in candidates or target_id not in case.targets:
            continue
        candidate = candidates[candidate_id]
        target = case.targets[target_id]
        windows = sorted(
            windows_by_pair.get((candidate_id, target_id), []),
            key=lambda item: (item.midpoint_offset_sec, item.window_id),
        )
        hints = sorted(
            hints_by_pair.get((candidate_id, target_id), []),
            key=lambda item: (item.offset_sec, -item.min_margin, item.hint_id),
        )
        required_satellites = satellites_required_for_target(candidate, target)
        max_gap_hours = _analytical_gap_hours(
            case=case,
            candidate=candidate,
            required_satellites=required_satellites,
            windows=windows,
            hints=hints,
        )
        claim = AnalyticalCoverageClaim(
            claim_id=f"{candidate_id}__{target_id}",
            rank=0,
            candidate=candidate,
            target_id=target_id,
            required_satellites=required_satellites,
            analytical_window_ids=tuple(window.window_id for window in windows),
            analytical_hint_ids=tuple(hint.hint_id for hint in hints),
            analytical_max_gap_hours=max_gap_hours,
            analytical_capped_gap_hours=max(
                max_gap_hours,
                target.expected_revisit_period_hours,
            ),
            geometry_margin=_coverage_margin(
                case=case,
                target_id=target_id,
                windows=windows,
                hints=hints,
            ),
            repeat_period_hours=candidate.repeat_period_sec / 3600.0,
            closure_error_m=candidate.template_closure_error_m,
        )
        claims_by_target.setdefault(target_id, []).append(claim)

    ranked: list[AnalyticalCoverageClaim] = []
    for target_id, target_claims in sorted(claims_by_target.items()):
        ordered = sorted(
            target_claims,
            key=lambda item: (
                item.required_satellites,
                item.analytical_capped_gap_hours,
                item.analytical_max_gap_hours,
                -item.geometry_margin,
                item.repeat_period_hours,
                item.closure_error_m,
                item.candidate.candidate_id,
            ),
        )
        for rank, claim in enumerate(ordered):
            ranked.append(
                AnalyticalCoverageClaim(
                    claim_id=claim.claim_id,
                    rank=rank,
                    candidate=claim.candidate,
                    target_id=claim.target_id,
                    required_satellites=claim.required_satellites,
                    analytical_window_ids=claim.analytical_window_ids,
                    analytical_hint_ids=claim.analytical_hint_ids,
                    analytical_max_gap_hours=claim.analytical_max_gap_hours,
                    analytical_capped_gap_hours=claim.analytical_capped_gap_hours,
                    geometry_margin=claim.geometry_margin,
                    repeat_period_hours=claim.repeat_period_hours,
                    closure_error_m=claim.closure_error_m,
                )
            )
    return ranked


def _resolved_worker_count(configured: int, work_item_count: int) -> int:
    if work_item_count <= 0:
        return 0
    if configured <= 1:
        return 1
    return max(1, min(configured, work_item_count, os.cpu_count() or 1))


def _scheduling_config(config: CertificationConfig) -> Any:
    from .solution import SchedulingConfig

    return SchedulingConfig(
        opportunity_sample_step_sec=config.opportunity_sample_step_sec,
        validation_sample_step_sec=config.validation_sample_step_sec,
        refinement_propagation=config.refinement_propagation,
        elevation_safety_margin_deg=config.elevation_safety_margin_deg,
        range_safety_margin_m=config.range_safety_margin_m,
        off_nadir_safety_margin_deg=config.off_nadir_safety_margin_deg,
        opportunity_worker_count=1,
        repair_worker_count=1,
    )


def _certify_claim_worker(
    args: tuple[RevisitCase, CoverageSummary, AnalyticalCoverageClaim, CertificationConfig],
) -> CertifiedCoverage:
    case, coverage, claim, config = args
    from .solution import _coarse_hints_by_key, _refined_candidate_target_quality

    hints = _coarse_hints_by_key(case=case, coverage=coverage).get(
        (claim.candidate.candidate_id, claim.target_id),
        [],
    )
    quality = _refined_candidate_target_quality(
        case=case,
        coverage=coverage,
        candidate_id=claim.candidate.candidate_id,
        target_id=claim.target_id,
        hints=hints,
        config=_scheduling_config(config),
    )
    target = case.targets[claim.target_id]
    meets = (
        quality.opportunity_count > 0
        and quality.max_gap_hours
        <= target.expected_revisit_period_hours + NUMERICAL_EPS
    )
    rejection_reason = None
    if not meets:
        if quality.opportunity_count <= 0:
            rejection_reason = "no_refined_opportunities"
        else:
            rejection_reason = "revisit_gap_exceeded"
    return CertifiedCoverage(
        certification_id=f"cert__{claim.claim_id}",
        claim=claim,
        refined_opportunity_count=quality.refined_opportunity_count,
        refined_midpoint_offsets_sec=quality.refined_midpoint_offsets_sec,
        max_gap_hours=quality.max_gap_hours,
        capped_max_gap_hours=quality.capped_max_gap_hours,
        meets_revisit=meets,
        rejection_reason=rejection_reason,
        rejection_reasons=quality.rejection_reasons or {},
    )


def certify_coverage_claims(
    case: RevisitCase,
    coverage: CoverageSummary,
    config: CertificationConfig,
) -> CertificationSummary:
    if config.max_claims_per_target <= 0:
        raise ValueError("certification.max_claims_per_target must be > 0")
    if config.min_passing_claims_per_target <= 0:
        raise ValueError("certification.min_passing_claims_per_target must be > 0")

    claims = build_analytical_claims(case, coverage)
    frontier_limited: list[str] = []
    claims_by_target: dict[str, list[AnalyticalCoverageClaim]] = {}
    for target_id in sorted(case.targets):
        target_claims = [claim for claim in claims if claim.target_id == target_id]
        limited = target_claims[: config.max_claims_per_target]
        if len(target_claims) > len(limited):
            frontier_limited.append(target_id)
        claims_by_target[target_id] = limited

    total_limited_claims = sum(len(items) for items in claims_by_target.values())
    worker_count = _resolved_worker_count(config.worker_count, total_limited_claims)
    worker_config = CertificationConfig(
        max_claims_per_target=config.max_claims_per_target,
        min_passing_claims_per_target=config.min_passing_claims_per_target,
        worker_count=worker_count,
        max_selection_retries=config.max_selection_retries,
        opportunity_sample_step_sec=config.opportunity_sample_step_sec,
        validation_sample_step_sec=config.validation_sample_step_sec,
        refinement_propagation=config.refinement_propagation,
        elevation_safety_margin_deg=config.elevation_safety_margin_deg,
        range_safety_margin_m=config.range_safety_margin_m,
        off_nadir_safety_margin_deg=config.off_nadir_safety_margin_deg,
    )
    retained: list[CertifiedCoverage] = []
    executor = (
        ProcessPoolExecutor(max_workers=worker_count)
        if worker_count > 1
        else None
    )
    try:
        for target_id in sorted(case.targets):
            target_claims = claims_by_target.get(target_id, [])
            pass_count = 0
            batch_size = max(1, worker_count)
            for start in range(0, len(target_claims), batch_size):
                batch_claims = target_claims[start : start + batch_size]
                work_items = [
                    (case, coverage, claim, worker_config)
                    for claim in batch_claims
                ]
                if executor is not None:
                    batch_records = list(
                        executor.map(_certify_claim_worker, work_items)
                    )
                else:
                    batch_records = [
                        _certify_claim_worker(item) for item in work_items
                    ]
                for record in sorted(batch_records, key=lambda item: item.claim.rank):
                    retained.append(record)
                    if record.meets_revisit:
                        pass_count += 1
                if pass_count >= config.min_passing_claims_per_target:
                    break
    finally:
        if executor is not None:
            executor.shutdown()

    retained_by_target: dict[str, list[CertifiedCoverage]] = {}
    for record in retained:
        retained_by_target.setdefault(record.target_id, []).append(record)
    retained = []
    for target_id in sorted(case.targets):
        pass_count = 0
        for record in sorted(
            retained_by_target.get(target_id, []),
            key=lambda item: item.claim.rank,
        ):
            retained.append(record)
            if record.meets_revisit:
                pass_count += 1
            if pass_count >= config.min_passing_claims_per_target:
                break

    rejected_reasons: dict[str, int] = {}
    target_summaries: dict[str, dict[str, Any]] = {}
    retained_by_target: dict[str, list[CertifiedCoverage]] = {}
    for record in retained:
        retained_by_target.setdefault(record.target_id, []).append(record)
        if record.rejection_reason is not None:
            rejected_reasons[record.rejection_reason] = (
                rejected_reasons.get(record.rejection_reason, 0) + 1
            )
    for target_id in sorted(case.targets):
        records = retained_by_target.get(target_id, [])
        passed = [record for record in records if record.meets_revisit]
        failed = [record for record in records if not record.meets_revisit]
        target_summaries[target_id] = {
            "target_id": target_id,
            "claim_count": len([claim for claim in claims if claim.target_id == target_id]),
            "checked_count": len(records),
            "passed_count": len(passed),
            "failed_count": len(failed),
            "frontier_limited": target_id in frontier_limited,
            "best_certification_id": (
                None
                if not passed
                else min(
                    passed,
                    key=lambda item: (
                        item.required_satellites,
                        item.capped_max_gap_hours,
                        item.max_gap_hours,
                        item.candidate_id,
                    ),
                ).certification_id
            ),
        }

    return CertificationSummary(
        claims=claims,
        certified_records=sorted(
            retained,
            key=lambda item: (item.target_id, item.claim.rank, item.candidate_id),
        ),
        target_summaries=target_summaries,
        rejected_reasons=rejected_reasons,
        frontier_limited_target_ids=frontier_limited,
        config=worker_config,
    )
