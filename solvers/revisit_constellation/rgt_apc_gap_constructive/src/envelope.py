"""Opportunity-envelope diagnostics for revisit-gap failures."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .case_io import RevisitCase
from .gaps import GapScore, revisit_gaps_hours, score_observation_timelines
from .orbit_library import OrbitCandidate
from .scheduling import ScheduledObservation
from .time_grid import iso_z
from .visibility import VisibilityWindow


TimelineMap = dict[str, list[datetime]]


@dataclass(frozen=True, slots=True)
class EnvelopeArtifacts:
    opportunity_envelope: dict[str, Any]
    high_gap_intervals: dict[str, Any]


def _window_timelines(
    windows: list[VisibilityWindow],
    selected_candidate_ids: set[str] | None = None,
    allowed_candidate_ids: set[str] | None = None,
) -> TimelineMap:
    timelines: TimelineMap = {}
    for window in windows:
        if (
            selected_candidate_ids is not None
            and window.candidate_id not in selected_candidate_ids
        ):
            continue
        if (
            allowed_candidate_ids is not None
            and window.candidate_id not in allowed_candidate_ids
        ):
            continue
        timelines.setdefault(window.target_id, []).append(window.midpoint)
    return {
        target_id: sorted(set(midpoints))
        for target_id, midpoints in timelines.items()
    }


def _schedule_timelines(scheduled: list[ScheduledObservation]) -> TimelineMap:
    timelines: TimelineMap = {}
    for observation in scheduled:
        timelines.setdefault(observation.target_id, []).append(observation.midpoint)
    return {
        target_id: sorted(set(midpoints))
        for target_id, midpoints in timelines.items()
    }


def _worst_interval(
    *,
    case: RevisitCase,
    target_id: str,
    midpoints: list[datetime],
) -> tuple[datetime, datetime, float]:
    times = [case.horizon_start, *sorted(set(midpoints)), case.horizon_end]
    best_left = times[0]
    best_right = times[1]
    best_gap = (best_right - best_left).total_seconds() / 3600.0
    for left, right in zip(times, times[1:]):
        gap_hours = (right - left).total_seconds() / 3600.0
        if gap_hours > best_gap:
            best_left = left
            best_right = right
            best_gap = gap_hours
    return best_left, best_right, best_gap


def _envelope_target_rows(
    *,
    case: RevisitCase,
    timelines: TimelineMap,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for target_id, target in case.targets.items():
        midpoints = sorted(set(timelines.get(target_id, [])))
        worst_start, worst_end, worst_gap_hours = _worst_interval(
            case=case,
            target_id=target_id,
            midpoints=midpoints,
        )
        rows.append(
            {
                "target_id": target_id,
                "observation_count": len(midpoints),
                "expected_revisit_period_hours": target.expected_revisit_period_hours,
                "mean_revisit_gap_hours": (
                    sum(
                        revisit_gaps_hours(
                            case.horizon_start,
                            case.horizon_end,
                            midpoints,
                        )
                    )
                    / (len(midpoints) + 1)
                ),
                "max_revisit_gap_hours": worst_gap_hours,
                "capped_max_revisit_gap_hours": max(
                    worst_gap_hours,
                    target.expected_revisit_period_hours,
                ),
                "above_expected_threshold": (
                    worst_gap_hours > target.expected_revisit_period_hours
                ),
                "above_12h_threshold": worst_gap_hours > 12.0,
                "worst_interval_start": iso_z(worst_start),
                "worst_interval_end": iso_z(worst_end),
                "worst_interval_hours": worst_gap_hours,
                "first_observation_midpoint": iso_z(midpoints[0]) if midpoints else None,
                "last_observation_midpoint": iso_z(midpoints[-1]) if midpoints else None,
            }
        )
    return rows


def _envelope_summary(
    *,
    case: RevisitCase,
    name: str,
    description: str,
    timelines: TimelineMap,
) -> dict[str, Any]:
    score = score_observation_timelines(case, timelines)
    target_rows = _envelope_target_rows(case=case, timelines=timelines)
    observation_count = sum(len(set(items)) for items in timelines.values())
    return {
        "name": name,
        "description": description,
        "optimism": (
            "Opportunity envelope scored from available midpoints; ignores "
            "slew, overlap, and battery conflicts unless this is the final "
            "scheduled envelope."
        ),
        "score": score.as_dict(),
        "metrics": {
            "capped_max_revisit_gap_hours": score.capped_max_revisit_gap_hours,
            "worst_target_capped_max_revisit_gap_hours": (
                score.worst_target_capped_max_revisit_gap_hours
            ),
            "max_revisit_gap_hours": score.max_revisit_gap_hours,
            "mean_revisit_gap_hours": score.mean_revisit_gap_hours,
            "threshold_violation_count": score.threshold_violation_count,
            "target_count_above_12h": sum(
                1 for row in target_rows if row["above_12h_threshold"]
            ),
            "target_count_above_expected": sum(
                1 for row in target_rows if row["above_expected_threshold"]
            ),
            "observed_target_count": sum(
                1 for row in target_rows if row["observation_count"] > 0
            ),
            "unobserved_target_count": sum(
                1 for row in target_rows if row["observation_count"] <= 0
            ),
            "observation_count": observation_count,
        },
        "target_metrics": target_rows,
    }


def _target_interval_row(
    *,
    case: RevisitCase,
    target_id: str,
    all_timelines: TimelineMap,
    closure_timelines: TimelineMap,
    selected_timelines: TimelineMap,
    hard_feasible_timelines: TimelineMap,
    final_timelines: TimelineMap,
    all_score: GapScore,
    closure_score: GapScore,
    selected_score: GapScore,
    hard_feasible_score: GapScore,
    final_score: GapScore,
    generated_candidate_ids: set[str],
    closure_candidate_ids: set[str],
    selected_candidate_ids: set[str],
    candidate_cap_limited: bool,
    selection_budget_limited: bool,
) -> dict[str, Any]:
    all_midpoints = sorted(set(all_timelines.get(target_id, [])))
    closure_midpoints = sorted(set(closure_timelines.get(target_id, [])))
    selected_midpoints = sorted(set(selected_timelines.get(target_id, [])))
    hard_feasible_midpoints = sorted(set(hard_feasible_timelines.get(target_id, [])))
    final_midpoints = sorted(set(final_timelines.get(target_id, [])))
    worst_start, worst_end, worst_gap_hours = _worst_interval(
        case=case,
        target_id=target_id,
        midpoints=final_midpoints,
    )
    target = case.targets[target_id]
    all_target = all_score.target_gap_summary[target_id]
    closure_target = closure_score.target_gap_summary[target_id]
    selected_target = selected_score.target_gap_summary[target_id]
    hard_feasible_target = hard_feasible_score.target_gap_summary[target_id]
    final_target = final_score.target_gap_summary[target_id]
    all_can_meet_expected = (
        all_target.max_revisit_gap_hours <= target.expected_revisit_period_hours
    )
    selected_can_meet_expected = (
        selected_target.max_revisit_gap_hours <= target.expected_revisit_period_hours
    )
    closure_can_meet_expected = (
        closure_target.max_revisit_gap_hours <= target.expected_revisit_period_hours
    )
    selected_has_opportunity = bool(selected_midpoints)
    if not all_midpoints:
        blocker = "no_generated_opportunity"
    elif not closure_midpoints:
        blocker = "closure_filtered_away"
    elif not all_can_meet_expected:
        blocker = (
            "candidate_cap_limited"
            if candidate_cap_limited
            else "selected_but_insufficient_temporal_spread"
        )
    elif not closure_can_meet_expected:
        blocker = "closure_filtered_away"
    elif not selected_has_opportunity and selection_budget_limited:
        blocker = "selection_budget_limited"
    elif not selected_can_meet_expected:
        blocker = (
            "selection_budget_limited"
            if selection_budget_limited
            else "selected_but_insufficient_temporal_spread"
        )
    elif final_target.max_revisit_gap_hours > target.expected_revisit_period_hours:
        blocker = "scheduler_conflict"
    else:
        blocker = "within_expected_threshold"

    return {
        "target_id": target_id,
        "blocker": blocker,
        "expected_revisit_period_hours": target.expected_revisit_period_hours,
        "final_max_revisit_gap_hours": final_target.max_revisit_gap_hours,
        "final_capped_max_revisit_gap_hours": (
            final_target.capped_max_revisit_gap_hours
        ),
        "all_candidate_max_revisit_gap_hours": all_target.max_revisit_gap_hours,
        "closure_filtered_max_revisit_gap_hours": closure_target.max_revisit_gap_hours,
        "selected_candidate_max_revisit_gap_hours": (
            selected_target.max_revisit_gap_hours
        ),
        "hard_feasible_selected_max_revisit_gap_hours": (
            hard_feasible_target.max_revisit_gap_hours
        ),
        "worst_interval_start": iso_z(worst_start),
        "worst_interval_end": iso_z(worst_end),
        "worst_interval_hours": worst_gap_hours,
        "first_opportunity_midpoint": iso_z(all_midpoints[0]) if all_midpoints else None,
        "last_opportunity_midpoint": iso_z(all_midpoints[-1]) if all_midpoints else None,
        "first_closure_filtered_midpoint": (
            iso_z(closure_midpoints[0]) if closure_midpoints else None
        ),
        "last_closure_filtered_midpoint": (
            iso_z(closure_midpoints[-1]) if closure_midpoints else None
        ),
        "first_selected_opportunity_midpoint": (
            iso_z(selected_midpoints[0]) if selected_midpoints else None
        ),
        "last_selected_opportunity_midpoint": (
            iso_z(selected_midpoints[-1]) if selected_midpoints else None
        ),
        "all_candidate_opportunity_count": len(all_midpoints),
        "closure_filtered_opportunity_count": len(closure_midpoints),
        "selected_candidate_opportunity_count": len(selected_midpoints),
        "hard_feasible_selected_opportunity_count": len(hard_feasible_midpoints),
        "scheduled_observation_count": len(final_midpoints),
        "generated_candidate_count": len(generated_candidate_ids),
        "closure_candidate_count": len(closure_candidate_ids),
        "selected_candidate_count": len(selected_candidate_ids),
        "candidate_cap_limited": candidate_cap_limited,
        "selection_budget_limited": selection_budget_limited,
        "above_12h_threshold": final_target.max_revisit_gap_hours > 12.0,
        "above_expected_threshold": (
            final_target.max_revisit_gap_hours
            > target.expected_revisit_period_hours
        ),
    }


def build_opportunity_envelope_artifacts(
    *,
    case: RevisitCase,
    windows: list[VisibilityWindow],
    selected_candidate_ids: list[str],
    scheduled_observations: list[ScheduledObservation],
    candidates: list[OrbitCandidate] | None = None,
    closure_error_limit_m: float | None = None,
    candidate_cap_limited: bool = False,
    selection_budget_limited: bool = False,
) -> EnvelopeArtifacts:
    """Build all/selected/final opportunity-envelope diagnostics."""
    selected_ids = set(selected_candidate_ids)
    candidate_by_id = {
        candidate.candidate_id: candidate
        for candidate in (candidates or [])
    }
    generated_candidate_ids = {
        candidate.candidate_id for candidate in (candidates or [])
    } or {window.candidate_id for window in windows}
    if closure_error_limit_m is None:
        closure_candidate_ids = set(generated_candidate_ids)
    else:
        closure_candidate_ids = {
            candidate_id
            for candidate_id in generated_candidate_ids
            if (
                candidate_by_id.get(candidate_id) is None
                or candidate_by_id[candidate_id].rgt_analytical_closure_m is None
                or candidate_by_id[candidate_id].rgt_analytical_closure_m
                <= closure_error_limit_m
            )
        }
    all_timelines = _window_timelines(windows)
    closure_timelines = _window_timelines(
        windows,
        allowed_candidate_ids=closure_candidate_ids,
    )
    selected_timelines = _window_timelines(windows, selected_ids)
    hard_feasible_timelines = _schedule_timelines(scheduled_observations)
    final_timelines = _schedule_timelines(scheduled_observations)
    all_envelope = _envelope_summary(
        case=case,
        name="all_generated_candidates",
        description="All generated candidate visibility windows, ignoring scheduling conflicts.",
        timelines=all_timelines,
    )
    selected_envelope = _envelope_summary(
        case=case,
        name="selected_candidates",
        description="Visibility windows from the selected output satellites, before scheduling.",
        timelines=selected_timelines,
    )
    closure_envelope = _envelope_summary(
        case=case,
        name="all_generated_candidates_after_closure_filter",
        description="All generated visibility windows from candidates within the configured shell-closure limit.",
        timelines=closure_timelines,
    )
    hard_feasible_envelope = _envelope_summary(
        case=case,
        name="selected_candidates_after_hard_local_feasibility_filters",
        description="Midpoints from selected candidates that survived local scheduling feasibility checks.",
        timelines=hard_feasible_timelines,
    )
    final_envelope = _envelope_summary(
        case=case,
        name="final_schedule",
        description="Midpoints from the emitted observation schedule.",
        timelines=final_timelines,
    )
    all_score = score_observation_timelines(case, all_timelines)
    closure_score = score_observation_timelines(case, closure_timelines)
    selected_score = score_observation_timelines(case, selected_timelines)
    hard_feasible_score = score_observation_timelines(case, hard_feasible_timelines)
    final_score = score_observation_timelines(case, final_timelines)
    interval_rows = [
        _target_interval_row(
            case=case,
            target_id=target_id,
            all_timelines=all_timelines,
            closure_timelines=closure_timelines,
            selected_timelines=selected_timelines,
            hard_feasible_timelines=hard_feasible_timelines,
            final_timelines=final_timelines,
            all_score=all_score,
            closure_score=closure_score,
            selected_score=selected_score,
            hard_feasible_score=hard_feasible_score,
            final_score=final_score,
            generated_candidate_ids=generated_candidate_ids,
            closure_candidate_ids=closure_candidate_ids,
            selected_candidate_ids=selected_ids,
            candidate_cap_limited=candidate_cap_limited,
            selection_budget_limited=selection_budget_limited,
        )
        for target_id in case.targets
    ]
    high_gap_rows = [
        row
        for row in interval_rows
        if row["above_expected_threshold"] or row["above_12h_threshold"]
    ]
    blocker_counts: dict[str, int] = {}
    for row in high_gap_rows:
        blocker = str(row["blocker"])
        blocker_counts[blocker] = blocker_counts.get(blocker, 0) + 1

    opportunity_envelope = {
        "version": 1,
        "case_id": case.case_id,
        "selected_candidate_count": len(selected_ids),
        "generated_visibility_window_count": len(windows),
        "scheduled_observation_count": len(scheduled_observations),
        "envelopes": [
            all_envelope,
            closure_envelope,
            selected_envelope,
            hard_feasible_envelope,
            final_envelope,
        ],
        "comparison": {
            "closure_filtered_minus_all_capped_max_hours": (
                closure_score.capped_max_revisit_gap_hours
                - all_score.capped_max_revisit_gap_hours
            ),
            "selected_minus_all_capped_max_hours": (
                selected_score.capped_max_revisit_gap_hours
                - all_score.capped_max_revisit_gap_hours
            ),
            "selected_minus_closure_filtered_capped_max_hours": (
                selected_score.capped_max_revisit_gap_hours
                - closure_score.capped_max_revisit_gap_hours
            ),
            "hard_feasible_minus_selected_capped_max_hours": (
                hard_feasible_score.capped_max_revisit_gap_hours
                - selected_score.capped_max_revisit_gap_hours
            ),
            "final_minus_selected_capped_max_hours": (
                final_score.capped_max_revisit_gap_hours
                - selected_score.capped_max_revisit_gap_hours
            ),
            "final_minus_all_capped_max_hours": (
                final_score.capped_max_revisit_gap_hours
                - all_score.capped_max_revisit_gap_hours
            ),
            "current_profile_candidate_limited": (
                all_score.capped_max_revisit_gap_hours > 12.0
            ),
            "current_profile_selection_limited": (
                closure_score.capped_max_revisit_gap_hours <= 12.0
                and selected_score.capped_max_revisit_gap_hours > 12.0
            ),
            "current_profile_scheduler_limited": (
                selected_score.capped_max_revisit_gap_hours <= 12.0
                and final_score.capped_max_revisit_gap_hours > 12.0
            ),
        },
    }
    high_gap_intervals = {
        "version": 1,
        "case_id": case.case_id,
        "blocker_counts": dict(sorted(blocker_counts.items())),
        "high_gap_target_count": len(high_gap_rows),
        "targets": sorted(
            high_gap_rows,
            key=lambda row: (
                -float(row["final_capped_max_revisit_gap_hours"]),
                str(row["target_id"]),
            ),
        ),
    }
    return EnvelopeArtifacts(
        opportunity_envelope=opportunity_envelope,
        high_gap_intervals=high_gap_intervals,
    )
