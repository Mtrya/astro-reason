"""Greedy satellite selection over visibility opportunity timelines."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .case_io import RevisitCase
from .gaps import GapImprovement, GapScore, gap_improvement, score_observation_timelines
from .orbit_library import OrbitCandidate
from .visibility import VisibilityWindow


TimelineMap = dict[str, list[datetime]]
CandidateTimelineMap = dict[str, TimelineMap]
SelectionCandidate = tuple[
    tuple[int, float, float, float, str],
    str,
    TimelineMap,
    GapScore,
    GapImprovement,
]


@dataclass(frozen=True, slots=True)
class SelectionConfig:
    max_selected_satellites: int | None = None
    require_positive_improvement: bool = True

    @classmethod
    def from_mapping(cls, payload: dict[str, Any]) -> "SelectionConfig":
        raw = payload.get("selection", payload)
        if not isinstance(raw, dict):
            raise ValueError("selection config must be a mapping/object")
        max_selected_satellites = raw.get("max_selected_satellites")
        return cls(
            max_selected_satellites=(
                None if max_selected_satellites is None else int(max_selected_satellites)
            ),
            require_positive_improvement=bool(raw.get("require_positive_improvement", True)),
        )

    def selected_satellite_limit(self, case: RevisitCase, candidate_count: int) -> int:
        configured = (
            case.max_num_satellites
            if self.max_selected_satellites is None
            else self.max_selected_satellites
        )
        return max(0, min(case.max_num_satellites, configured, candidate_count))

    def as_status_dict(self) -> dict[str, Any]:
        return {
            "max_selected_satellites": self.max_selected_satellites,
            "require_positive_improvement": self.require_positive_improvement,
        }


@dataclass(frozen=True, slots=True)
class SelectionRound:
    round_index: int
    candidate_id: str
    opportunity_count: int
    score_before: GapScore
    score_after: GapScore
    improvement: GapImprovement

    def as_dict(self) -> dict[str, Any]:
        return {
            "round_index": self.round_index,
            "candidate_id": self.candidate_id,
            "opportunity_count": self.opportunity_count,
            "score_before": self.score_before.as_dict(),
            "score_after": self.score_after.as_dict(),
            "improvement": self.improvement.as_dict(),
        }


@dataclass(frozen=True, slots=True)
class SelectionResult:
    selected_candidate_ids: list[str]
    selected_candidates: list[OrbitCandidate]
    candidate_timelines: CandidateTimelineMap
    final_timelines: TimelineMap
    initial_score: GapScore
    final_score: GapScore
    rounds: list[SelectionRound]
    caps: dict[str, Any]

    def as_status_dict(self) -> dict[str, Any]:
        return {
            "selected_candidate_count": len(self.selected_candidate_ids),
            "selected_candidate_ids": self.selected_candidate_ids,
            "initial_score": self.initial_score.as_dict(),
            "final_score": self.final_score.as_dict(),
            "rounds": [round_info.as_dict() for round_info in self.rounds],
            "caps": self.caps,
        }


def build_candidate_timelines(windows: list[VisibilityWindow]) -> CandidateTimelineMap:
    timelines: CandidateTimelineMap = {}
    for window in windows:
        candidate_targets = timelines.setdefault(window.candidate_id, {})
        candidate_targets.setdefault(window.target_id, []).append(window.midpoint)
    for target_map in timelines.values():
        for target_id, midpoints in list(target_map.items()):
            target_map[target_id] = sorted(set(midpoints))
    return timelines


def merge_timelines(base: TimelineMap, addition: TimelineMap) -> TimelineMap:
    merged: TimelineMap = {
        target_id: list(midpoints)
        for target_id, midpoints in base.items()
    }
    for target_id, midpoints in addition.items():
        merged.setdefault(target_id, []).extend(midpoints)
        merged[target_id] = sorted(set(merged[target_id]))
    return merged


def _opportunity_count(timeline: TimelineMap) -> int:
    return sum(len(midpoints) for midpoints in timeline.values())


def select_satellites_greedy(
    *,
    case: RevisitCase,
    candidates: list[OrbitCandidate],
    windows: list[VisibilityWindow],
    config: SelectionConfig,
) -> SelectionResult:
    candidate_timelines = build_candidate_timelines(windows)
    candidate_by_id = {candidate.candidate_id: candidate for candidate in candidates}
    remaining_ids = sorted(candidate.candidate_id for candidate in candidates)
    limit = config.selected_satellite_limit(case, len(candidates))

    selected_ids: list[str] = []
    selected_candidates: list[OrbitCandidate] = []
    rounds: list[SelectionRound] = []
    current_timelines: TimelineMap = {}
    current_score = score_observation_timelines(case, current_timelines)
    initial_score = current_score

    while len(selected_ids) < limit:
        best: SelectionCandidate | None = None
        for candidate_id in remaining_ids:
            candidate_timeline = candidate_timelines.get(candidate_id, {})
            merged = merge_timelines(current_timelines, candidate_timeline)
            candidate_score = score_observation_timelines(case, merged)
            improvement = gap_improvement(current_score, candidate_score)
            if config.require_positive_improvement and not improvement.is_positive:
                continue
            # Lower score is better; candidate_id gives deterministic ties.
            key = (*candidate_score.optimization_key, candidate_id)
            if best is None or key < best[0]:
                best = (key, candidate_id, merged, candidate_score, improvement)

        if best is None:
            break

        _, candidate_id, current_timelines, next_score, improvement = best
        selected_ids.append(candidate_id)
        selected_candidates.append(candidate_by_id[candidate_id])
        remaining_ids.remove(candidate_id)
        rounds.append(
            SelectionRound(
                round_index=len(rounds),
                candidate_id=candidate_id,
                opportunity_count=_opportunity_count(candidate_timelines.get(candidate_id, {})),
                score_before=current_score,
                score_after=next_score,
                improvement=improvement,
            )
        )
        current_score = next_score

    return SelectionResult(
        selected_candidate_ids=selected_ids,
        selected_candidates=selected_candidates,
        candidate_timelines=candidate_timelines,
        final_timelines=current_timelines,
        initial_score=initial_score,
        final_score=current_score,
        rounds=rounds,
        caps={
            **config.as_status_dict(),
            "selected_satellite_limit": limit,
            "case_max_num_satellites": case.max_num_satellites,
            "candidate_count": len(candidates),
            "stopped_by_limit": len(selected_ids) >= limit,
            "stopped_by_no_improvement": len(selected_ids) < limit,
        },
    )
