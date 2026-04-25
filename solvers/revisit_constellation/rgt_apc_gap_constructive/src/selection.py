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
    tuple[int, float, float, float, int, int, int, float, str],
    str,
    TimelineMap,
    GapScore,
    GapImprovement,
    dict[str, int | float],
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
    new_target_count: int
    candidate_target_count: int
    new_latitude_band_count: int
    phase_spread_deg: float
    score_before: GapScore
    score_after: GapScore
    improvement: GapImprovement

    def as_dict(self) -> dict[str, Any]:
        return {
            "round_index": self.round_index,
            "candidate_id": self.candidate_id,
            "opportunity_count": self.opportunity_count,
            "new_target_count": self.new_target_count,
            "candidate_target_count": self.candidate_target_count,
            "new_latitude_band_count": self.new_latitude_band_count,
            "phase_spread_deg": self.phase_spread_deg,
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
    target_coverage: list[dict[str, Any]]
    candidate_coverage: list[dict[str, Any]]
    caps: dict[str, Any]

    def as_status_dict(self) -> dict[str, Any]:
        return {
            "selected_candidate_count": len(self.selected_candidate_ids),
            "selected_candidate_ids": self.selected_candidate_ids,
            "initial_score": self.initial_score.as_dict(),
            "final_score": self.final_score.as_dict(),
            "rounds": [round_info.as_dict() for round_info in self.rounds],
            "target_coverage": self.target_coverage,
            "candidate_coverage": self.candidate_coverage,
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


def _latitude_band(latitude_deg: float) -> int:
    return int((latitude_deg + 90.0) // 30.0)


def _target_bands(case: RevisitCase, target_ids: set[str]) -> set[int]:
    return {
        _latitude_band(case.targets[target_id].latitude_deg)
        for target_id in target_ids
        if target_id in case.targets
    }


def _circular_distance_deg(first: float, second: float) -> float:
    distance = abs((first - second) % 360.0)
    return min(distance, 360.0 - distance)


def _phase_spread_deg(
    candidate: OrbitCandidate,
    selected_candidates: list[OrbitCandidate],
) -> float:
    if not selected_candidates:
        return 180.0
    spreads = [
        0.5
        * (
            _circular_distance_deg(candidate.raan_deg, selected.raan_deg)
            + _circular_distance_deg(candidate.mean_anomaly_deg, selected.mean_anomaly_deg)
        )
        for selected in selected_candidates
    ]
    return min(spreads)


def _candidate_diversity_diagnostics(
    *,
    case: RevisitCase,
    candidate: OrbitCandidate,
    candidate_timeline: TimelineMap,
    current_timelines: TimelineMap,
    selected_candidates: list[OrbitCandidate],
) -> dict[str, int | float]:
    candidate_target_ids = {
        target_id for target_id, midpoints in candidate_timeline.items() if midpoints
    }
    covered_target_ids = {
        target_id for target_id, midpoints in current_timelines.items() if midpoints
    }
    new_target_ids = candidate_target_ids - covered_target_ids
    covered_bands = _target_bands(case, covered_target_ids)
    candidate_bands = _target_bands(case, candidate_target_ids)
    return {
        "new_target_count": len(new_target_ids),
        "candidate_target_count": len(candidate_target_ids),
        "new_latitude_band_count": len(candidate_bands - covered_bands),
        "phase_spread_deg": _phase_spread_deg(candidate, selected_candidates),
    }


def _target_coverage_summary(
    *,
    case: RevisitCase,
    candidate_timelines: CandidateTimelineMap,
    selected_ids: set[str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for target_id in sorted(case.targets):
        candidate_ids = sorted(
            candidate_id
            for candidate_id, timeline in candidate_timelines.items()
            if timeline.get(target_id)
        )
        selected_candidate_ids = [
            candidate_id for candidate_id in candidate_ids if candidate_id in selected_ids
        ]
        visibility_window_count = sum(
            len(candidate_timelines[candidate_id].get(target_id, []))
            for candidate_id in candidate_ids
        )
        selected_visibility_window_count = sum(
            len(candidate_timelines[candidate_id].get(target_id, []))
            for candidate_id in selected_candidate_ids
        )
        if selected_candidate_ids:
            status = "selected_covered"
        elif candidate_ids:
            status = "candidate_only"
        else:
            status = "uncovered"
        rows.append(
            {
                "target_id": target_id,
                "candidate_count": len(candidate_ids),
                "selected_candidate_count": len(selected_candidate_ids),
                "visibility_window_count": visibility_window_count,
                "selected_visibility_window_count": selected_visibility_window_count,
                "coverage_status": status,
                "candidate_ids": candidate_ids[:10],
                "selected_candidate_ids": selected_candidate_ids,
            }
        )
    return rows


def _candidate_coverage_summary(
    *,
    candidates: list[OrbitCandidate],
    candidate_timelines: CandidateTimelineMap,
    selected_ids: set[str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for candidate in sorted(candidates, key=lambda item: item.candidate_id):
        timeline = candidate_timelines.get(candidate.candidate_id, {})
        target_ids = sorted(target_id for target_id, midpoints in timeline.items() if midpoints)
        rows.append(
            {
                "candidate_id": candidate.candidate_id,
                "selected": candidate.candidate_id in selected_ids,
                "target_count": len(target_ids),
                "opportunity_count": _opportunity_count(timeline),
                "inclination_deg": candidate.inclination_deg,
                "raan_deg": candidate.raan_deg,
                "mean_anomaly_deg": candidate.mean_anomaly_deg,
                "target_ids": target_ids,
            }
        )
    return rows


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
            candidate = candidate_by_id[candidate_id]
            candidate_timeline = candidate_timelines.get(candidate_id, {})
            merged = merge_timelines(current_timelines, candidate_timeline)
            candidate_score = score_observation_timelines(case, merged)
            improvement = gap_improvement(current_score, candidate_score)
            if config.require_positive_improvement and not improvement.is_positive:
                continue
            diversity = _candidate_diversity_diagnostics(
                case=case,
                candidate=candidate,
                candidate_timeline=candidate_timeline,
                current_timelines=current_timelines,
                selected_candidates=selected_candidates,
            )
            # Lower score is better; diversity terms only break score ties.
            key = (
                *candidate_score.optimization_key,
                -int(diversity["new_target_count"]),
                -int(diversity["candidate_target_count"]),
                -int(diversity["new_latitude_band_count"]),
                -float(diversity["phase_spread_deg"]),
                candidate_id,
            )
            if best is None or key < best[0]:
                best = (
                    key,
                    candidate_id,
                    merged,
                    candidate_score,
                    improvement,
                    diversity,
                )

        if best is None:
            break

        _, candidate_id, current_timelines, next_score, improvement, diversity = best
        selected_ids.append(candidate_id)
        selected_candidates.append(candidate_by_id[candidate_id])
        remaining_ids.remove(candidate_id)
        rounds.append(
            SelectionRound(
                round_index=len(rounds),
                candidate_id=candidate_id,
                opportunity_count=_opportunity_count(candidate_timelines.get(candidate_id, {})),
                new_target_count=int(diversity["new_target_count"]),
                candidate_target_count=int(diversity["candidate_target_count"]),
                new_latitude_band_count=int(diversity["new_latitude_band_count"]),
                phase_spread_deg=float(diversity["phase_spread_deg"]),
                score_before=current_score,
                score_after=next_score,
                improvement=improvement,
            )
        )
        current_score = next_score

    selected_id_set = set(selected_ids)
    target_coverage = _target_coverage_summary(
        case=case,
        candidate_timelines=candidate_timelines,
        selected_ids=selected_id_set,
    )
    candidate_coverage = _candidate_coverage_summary(
        candidates=candidates,
        candidate_timelines=candidate_timelines,
        selected_ids=selected_id_set,
    )
    coverage_status_counts: dict[str, int] = {}
    for row in target_coverage:
        status = str(row["coverage_status"])
        coverage_status_counts[status] = coverage_status_counts.get(status, 0) + 1

    return SelectionResult(
        selected_candidate_ids=selected_ids,
        selected_candidates=selected_candidates,
        candidate_timelines=candidate_timelines,
        final_timelines=current_timelines,
        initial_score=initial_score,
        final_score=current_score,
        rounds=rounds,
        target_coverage=target_coverage,
        candidate_coverage=candidate_coverage,
        caps={
            **config.as_status_dict(),
            "selected_satellite_limit": limit,
            "case_max_num_satellites": case.max_num_satellites,
            "candidate_count": len(candidates),
            "candidate_pool_exceeds_selected_limit": len(candidates) > limit,
            "target_coverage_status_counts": dict(sorted(coverage_status_counts.items())),
            "stopped_by_limit": len(selected_ids) >= limit,
            "stopped_by_no_improvement": len(selected_ids) < limit,
        },
    )
