"""Conservative solver-local opportunity grouping for fixed candidates."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .candidates import Candidate


@dataclass(frozen=True, slots=True)
class OpportunityConfig:
    enabled: bool = False
    max_time_gap_s: int = 1200
    roll_bucket_deg: float = 1.0e-3
    min_coverage_jaccard: float = 0.5
    debug_limit: int = 250

    @classmethod
    def from_mapping(cls, payload: dict[str, Any] | None) -> "OpportunityConfig":
        payload = payload or {}
        return cls(
            enabled=bool(payload.get("opportunity_grouping_enabled", False)),
            max_time_gap_s=_non_negative_int(
                payload.get("opportunity_max_time_gap_s", 1200),
                "opportunity_max_time_gap_s",
            ),
            roll_bucket_deg=_positive_float(
                payload.get("opportunity_roll_bucket_deg", 1.0e-3),
                "opportunity_roll_bucket_deg",
            ),
            min_coverage_jaccard=_bounded_unit_float(
                payload.get("opportunity_min_coverage_jaccard", 0.5),
                "opportunity_min_coverage_jaccard",
            ),
            debug_limit=_non_negative_int(
                payload.get("opportunity_debug_limit", 250),
                "opportunity_debug_limit",
            ),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "max_time_gap_s": self.max_time_gap_s,
            "roll_bucket_deg": self.roll_bucket_deg,
            "min_coverage_jaccard": self.min_coverage_jaccard,
            "debug_limit": self.debug_limit,
        }


@dataclass(frozen=True, slots=True)
class Opportunity:
    opportunity_id: str
    satellite_id: str
    candidate_ids: tuple[str, ...]
    representative_candidate_id: str
    start_min_offset_s: int
    start_max_offset_s: int
    end_min_offset_s: int
    end_max_offset_s: int
    roll_bucket: int
    roll_min_deg: float
    roll_max_deg: float
    coverage_sample_count_min: int
    coverage_sample_count_max: int
    coverage_union_count: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "opportunity_id": self.opportunity_id,
            "satellite_id": self.satellite_id,
            "candidate_ids": list(self.candidate_ids),
            "representative_candidate_id": self.representative_candidate_id,
            "start_min_offset_s": self.start_min_offset_s,
            "start_max_offset_s": self.start_max_offset_s,
            "end_min_offset_s": self.end_min_offset_s,
            "end_max_offset_s": self.end_max_offset_s,
            "roll_bucket": self.roll_bucket,
            "roll_min_deg": self.roll_min_deg,
            "roll_max_deg": self.roll_max_deg,
            "coverage_sample_count_min": self.coverage_sample_count_min,
            "coverage_sample_count_max": self.coverage_sample_count_max,
            "coverage_union_count": self.coverage_union_count,
        }


@dataclass(slots=True)
class OpportunitySummary:
    enabled: bool = False
    candidate_count: int = 0
    mapped_candidate_count: int = 0
    opportunity_count: int = 0
    singleton_opportunity_count: int = 0
    grouped_opportunity_count: int = 0
    grouped_candidate_count: int = 0
    max_candidates_per_opportunity: int = 0
    discarded_candidate_count: int = 0
    split_reasons: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "candidate_count": self.candidate_count,
            "mapped_candidate_count": self.mapped_candidate_count,
            "opportunity_count": self.opportunity_count,
            "singleton_opportunity_count": self.singleton_opportunity_count,
            "grouped_opportunity_count": self.grouped_opportunity_count,
            "grouped_candidate_count": self.grouped_candidate_count,
            "max_candidates_per_opportunity": self.max_candidates_per_opportunity,
            "discarded_candidate_count": self.discarded_candidate_count,
            "split_reasons": dict(sorted(self.split_reasons.items())),
        }


@dataclass(frozen=True, slots=True)
class OpportunityIndex:
    enabled: bool
    opportunities: tuple[Opportunity, ...]
    candidate_by_id: dict[str, Candidate]
    opportunity_by_id: dict[str, Opportunity]
    opportunity_by_candidate_id: dict[str, Opportunity]
    summary: OpportunitySummary

    def opportunity_id_for_candidate(self, candidate_id: str) -> str | None:
        opportunity = self.opportunity_by_candidate_id.get(candidate_id)
        return None if opportunity is None else opportunity.opportunity_id

    def choose_member(self, source_candidate: Candidate, intended_start_offset_s: int) -> tuple[Candidate, dict[str, Any]]:
        opportunity = self.opportunity_by_candidate_id.get(source_candidate.candidate_id)
        if not self.enabled or opportunity is None:
            return source_candidate, _source_mapping(source_candidate, source_candidate, None, intended_start_offset_s)
        members = [self.candidate_by_id[cid] for cid in opportunity.candidate_ids]
        chosen = min(
            members,
            key=lambda candidate: (
                abs(candidate.start_offset_s - intended_start_offset_s),
                -candidate.base_coverage_weight_m2,
                candidate.start_offset_s,
                candidate.candidate_id,
            ),
        )
        return chosen, _source_mapping(source_candidate, chosen, opportunity.opportunity_id, intended_start_offset_s)

    def choice_groups_for_candidates(self, candidates: list[Candidate]) -> dict[str, list[str]]:
        if not self.enabled:
            return {}
        groups: dict[str, list[str]] = {}
        for candidate in candidates:
            opportunity_id = self.opportunity_id_for_candidate(candidate.candidate_id)
            if opportunity_id is None:
                continue
            groups.setdefault(opportunity_id, []).append(candidate.candidate_id)
        return {
            opportunity_id: sorted(candidate_ids)
            for opportunity_id, candidate_ids in groups.items()
            if len(candidate_ids) > 1
        }

    def debug_payload(self, *, limit: int) -> dict[str, Any]:
        shown = self.opportunities[:limit]
        return {
            "summary": self.summary.as_dict(),
            "opportunities": [opportunity.as_dict() for opportunity in shown],
            "truncated": len(self.opportunities) > limit,
        }


def build_opportunity_index(
    candidates: list[Candidate],
    config: OpportunityConfig,
) -> OpportunityIndex:
    candidate_by_id = {candidate.candidate_id: candidate for candidate in candidates}
    if not config.enabled:
        summary = OpportunitySummary(
            enabled=False,
            candidate_count=len(candidates),
            mapped_candidate_count=len(candidates),
            opportunity_count=len(candidates),
            singleton_opportunity_count=len(candidates),
            max_candidates_per_opportunity=1 if candidates else 0,
        )
        opportunities = tuple(
            _make_opportunity(
                f"opp_{index:05d}_{_safe_id(candidate.satellite_id)}",
                [candidate],
                config=config,
            )
            for index, candidate in enumerate(sorted(candidates, key=_candidate_key), start=1)
        )
        return _make_index(False, opportunities, candidate_by_id, summary)

    summary = OpportunitySummary(enabled=True, candidate_count=len(candidates))
    opportunities: list[Opportunity] = []
    current: list[Candidate] = []
    current_key: tuple[str, int, int] | None = None
    previous: Candidate | None = None

    for candidate in sorted(candidates, key=_candidate_group_key(config)):
        key = _group_key(candidate, config)
        split_reason = _split_reason(current, current_key, previous, candidate, key, config)
        if split_reason is not None:
            summary.split_reasons[split_reason] = summary.split_reasons.get(split_reason, 0) + 1
            opportunities.append(
                _make_opportunity(
                    f"opp_{len(opportunities) + 1:05d}_{_safe_id(current[0].satellite_id)}",
                    current,
                    config=config,
                )
            )
            current = []
        current.append(candidate)
        current_key = key
        previous = candidate

    if current:
        opportunities.append(
            _make_opportunity(
                f"opp_{len(opportunities) + 1:05d}_{_safe_id(current[0].satellite_id)}",
                current,
                config=config,
            )
        )

    summary.opportunity_count = len(opportunities)
    summary.mapped_candidate_count = sum(len(opportunity.candidate_ids) for opportunity in opportunities)
    summary.singleton_opportunity_count = sum(1 for opportunity in opportunities if len(opportunity.candidate_ids) == 1)
    summary.grouped_opportunity_count = summary.opportunity_count - summary.singleton_opportunity_count
    summary.grouped_candidate_count = sum(
        len(opportunity.candidate_ids)
        for opportunity in opportunities
        if len(opportunity.candidate_ids) > 1
    )
    summary.max_candidates_per_opportunity = max((len(opportunity.candidate_ids) for opportunity in opportunities), default=0)
    summary.discarded_candidate_count = max(0, len(candidates) - summary.mapped_candidate_count)
    return _make_index(True, tuple(opportunities), candidate_by_id, summary)


def _make_index(
    enabled: bool,
    opportunities: tuple[Opportunity, ...],
    candidate_by_id: dict[str, Candidate],
    summary: OpportunitySummary,
) -> OpportunityIndex:
    by_id = {opportunity.opportunity_id: opportunity for opportunity in opportunities}
    by_candidate_id = {
        candidate_id: opportunity
        for opportunity in opportunities
        for candidate_id in opportunity.candidate_ids
    }
    return OpportunityIndex(
        enabled=enabled,
        opportunities=opportunities,
        candidate_by_id=candidate_by_id,
        opportunity_by_id=by_id,
        opportunity_by_candidate_id=by_candidate_id,
        summary=summary,
    )


def _make_opportunity(opportunity_id: str, candidates: list[Candidate], *, config: OpportunityConfig) -> Opportunity:
    ordered = sorted(candidates, key=_candidate_key)
    coverage_counts = [len(candidate.coverage_sample_ids) for candidate in ordered]
    coverage_union: set[str] = set()
    for candidate in ordered:
        coverage_union.update(candidate.coverage_sample_ids)
    representative = max(
        ordered,
        key=lambda candidate: (
            candidate.base_coverage_weight_m2,
            -abs(candidate.start_offset_s - ordered[0].start_offset_s),
            -candidate.start_offset_s,
            candidate.candidate_id,
        ),
    )
    return Opportunity(
        opportunity_id=opportunity_id,
        satellite_id=ordered[0].satellite_id,
        candidate_ids=tuple(candidate.candidate_id for candidate in ordered),
        representative_candidate_id=representative.candidate_id,
        start_min_offset_s=min(candidate.start_offset_s for candidate in ordered),
        start_max_offset_s=max(candidate.start_offset_s for candidate in ordered),
        end_min_offset_s=min(candidate.end_offset_s for candidate in ordered),
        end_max_offset_s=max(candidate.end_offset_s for candidate in ordered),
        roll_bucket=_roll_bucket(ordered[0].roll_deg, config),
        roll_min_deg=min(candidate.roll_deg for candidate in ordered),
        roll_max_deg=max(candidate.roll_deg for candidate in ordered),
        coverage_sample_count_min=min(coverage_counts),
        coverage_sample_count_max=max(coverage_counts),
        coverage_union_count=len(coverage_union),
    )


def _split_reason(
    current: list[Candidate],
    current_key: tuple[str, int, int] | None,
    previous: Candidate | None,
    candidate: Candidate,
    key: tuple[str, int, int],
    config: OpportunityConfig,
) -> str | None:
    if not current or current_key is None or previous is None:
        return None
    if key[0] != current_key[0]:
        return "satellite"
    if key[1] != current_key[1]:
        return "roll_bucket"
    if key[2] != current_key[2]:
        return "duration"
    if candidate.start_offset_s - previous.start_offset_s > config.max_time_gap_s:
        return "time_gap"
    if not candidate.coverage_sample_ids or not previous.coverage_sample_ids:
        return "empty_coverage"
    if _jaccard(previous.coverage_sample_ids, candidate.coverage_sample_ids) < config.min_coverage_jaccard:
        return "coverage_jaccard"
    return None


def _source_mapping(
    source: Candidate,
    emitted: Candidate,
    opportunity_id: str | None,
    intended_start_offset_s: int,
) -> dict[str, Any]:
    return {
        "source_candidate_id": source.candidate_id,
        "emitted_candidate_id": emitted.candidate_id,
        "opportunity_id": opportunity_id,
        "intended_start_offset_s": intended_start_offset_s,
        "emitted_start_offset_s": emitted.start_offset_s,
        "emitted_duration_s": emitted.duration_s,
        "emitted_roll_deg": emitted.roll_deg,
        "snapped_to_member": source.candidate_id != emitted.candidate_id
        or source.start_offset_s != emitted.start_offset_s,
    }


def _candidate_group_key(config: OpportunityConfig):
    def key(candidate: Candidate) -> tuple[str, int, int, int, str]:
        return (
            candidate.satellite_id,
            _roll_bucket(candidate.roll_deg, config),
            candidate.duration_s,
            candidate.start_offset_s,
            candidate.candidate_id,
        )

    return key


def _group_key(candidate: Candidate, config: OpportunityConfig) -> tuple[str, int, int]:
    return (
        candidate.satellite_id,
        _roll_bucket(candidate.roll_deg, config),
        candidate.duration_s,
    )


def _candidate_key(candidate: Candidate) -> tuple[str, int, float, str]:
    return (candidate.satellite_id, candidate.start_offset_s, candidate.roll_deg, candidate.candidate_id)


def _roll_bucket(roll_deg: float, config: OpportunityConfig) -> int:
    return int(round(float(roll_deg) / config.roll_bucket_deg))


def _jaccard(left: frozenset[str], right: frozenset[str]) -> float:
    union = left | right
    if not union:
        return 1.0
    return len(left & right) / len(union)


def _safe_id(value: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in value)


def _non_negative_int(value: Any, field: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise ValueError(f"{field} must be non-negative")
    return parsed


def _positive_float(value: Any, field: str) -> float:
    parsed = float(value)
    if parsed <= 0.0:
        raise ValueError(f"{field} must be positive")
    return parsed


def _bounded_unit_float(value: Any, field: str) -> float:
    parsed = float(value)
    if parsed < 0.0 or parsed > 1.0:
        raise ValueError(f"{field} must be in [0, 1]")
    return parsed
