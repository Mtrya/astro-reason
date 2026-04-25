"""Baseline evidence summaries for profiling and future-phase comparisons."""

from __future__ import annotations

from typing import Any

from .case_io import RevisitCase


BASELINE_VERSION = 1
OFFICIAL_VERIFICATION_BOUNDARY = (
    "Solver output records local metrics only. Official validity and metrics are "
    "produced by experiments/main_solver through the benchmark verifier executable."
)


def _target_counts_from_windows(windows: list[Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for window in windows:
        counts[window.target_id] = counts.get(window.target_id, 0) + 1
    return dict(sorted(counts.items()))


def _candidate_counts_from_windows(windows: list[Any]) -> dict[str, int]:
    target_candidates: dict[str, set[str]] = {}
    for window in windows:
        target_candidates.setdefault(window.target_id, set()).add(window.candidate_id)
    return {
        target_id: len(candidate_ids)
        for target_id, candidate_ids in sorted(target_candidates.items())
    }


def _stage_timing_profile(timing_seconds: dict[str, float]) -> dict[str, Any]:
    total = max(0.0, float(timing_seconds.get("total", 0.0)))
    stage_seconds = {
        key: float(value)
        for key, value in sorted(timing_seconds.items())
        if key != "total"
    }
    denominator = total if total > 0.0 else sum(stage_seconds.values())
    stage_fraction_of_total = {
        key: (value / denominator if denominator > 0.0 else 0.0)
        for key, value in stage_seconds.items()
    }
    dominant_stage_order = [
        key
        for key, _ in sorted(
            stage_seconds.items(),
            key=lambda item: (-item[1], item[0]),
        )
    ]
    return {
        "total_seconds": total,
        "stage_seconds": stage_seconds,
        "stage_fraction_of_total": stage_fraction_of_total,
        "dominant_stage_order": dominant_stage_order,
    }


def _mode_compact(mode_comparison: dict[str, Any]) -> list[dict[str, Any]]:
    compact: list[dict[str, Any]] = []
    for entry in mode_comparison.get("entries", []):
        score = entry.get("score", {})
        compact.append(
            {
                "mode": entry.get("mode"),
                "action_count": entry.get("action_count"),
                "observed_target_count": entry.get("observed_target_count"),
                "high_gap_target_count": entry.get("high_gap_target_count"),
                "local_valid": entry.get("local_valid"),
                "local_issue_count": entry.get("local_issue_count"),
                "capped_max_revisit_gap_hours": score.get(
                    "capped_max_revisit_gap_hours"
                ),
                "max_revisit_gap_hours": score.get("max_revisit_gap_hours"),
                "mean_revisit_gap_hours": score.get("mean_revisit_gap_hours"),
                "threshold_violation_count": score.get("threshold_violation_count"),
                "improvement_vs_no_op": entry.get("improvement_vs_no_op"),
                "improvement_vs_fifo": entry.get("improvement_vs_fifo"),
            }
        )
    return compact


def _target_rejection_counts(rejected_options: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    counts: dict[str, dict[str, int]] = {}
    for item in rejected_options:
        target_id = item.get("target_id")
        reason = item.get("reason")
        if not isinstance(target_id, str) or not isinstance(reason, str):
            continue
        target_counts = counts.setdefault(target_id, {})
        target_counts[reason] = target_counts.get(reason, 0) + 1
    return {
        target_id: dict(sorted(reason_counts.items()))
        for target_id, reason_counts in sorted(counts.items())
    }


def _unobserved_reason(
    *,
    visibility_window_count: int,
    option_count: int,
    rejected_count: int,
    scheduled_count: int,
) -> str | None:
    if scheduled_count > 0:
        return None
    if visibility_window_count <= 0:
        return "no_visibility_window"
    if option_count <= 0 and rejected_count > 0:
        return "all_options_rejected"
    if option_count > 0:
        return "options_available_not_scheduled"
    return "visibility_window_without_schedulable_option"


def build_baseline_evidence(
    *,
    case: RevisitCase,
    orbit_library: Any,
    visibility_library: Any,
    selection_result: Any,
    scheduling_result: Any,
    timing_seconds: dict[str, float],
) -> dict[str, Any]:
    """Build a deterministic, JSON-safe run profile for future comparisons."""
    visibility_count_by_target = _target_counts_from_windows(visibility_library.windows)
    visibility_candidate_count_by_target = _candidate_counts_from_windows(
        visibility_library.windows
    )
    scheduling_summary = scheduling_result.debug_summary
    option_count_by_target = scheduling_summary.get("option_count_by_target", {})
    scheduled_count_by_target = scheduling_summary.get("scheduled_action_count_by_target", {})
    rejected_count_by_target = scheduling_summary.get("rejected_option_count_by_target", {})
    rejection_reasons_by_target = _target_rejection_counts(
        scheduling_result.rejected_options
    )
    final_score = scheduling_result.validation_report.score
    high_gap_ids = set(scheduling_result.validation_report.high_gap_target_ids)

    target_evidence: list[dict[str, Any]] = []
    for target_id in sorted(case.targets):
        target_score = final_score.target_gap_summary[target_id]
        visibility_window_count = int(visibility_count_by_target.get(target_id, 0))
        option_count = int(option_count_by_target.get(target_id, 0))
        rejected_count = int(rejected_count_by_target.get(target_id, 0))
        scheduled_count = int(scheduled_count_by_target.get(target_id, 0))
        target_evidence.append(
            {
                "target_id": target_id,
                "visibility_window_count": visibility_window_count,
                "visibility_candidate_count": int(
                    visibility_candidate_count_by_target.get(target_id, 0)
                ),
                "option_count": option_count,
                "rejected_option_count": rejected_count,
                "rejection_reason_counts": rejection_reasons_by_target.get(target_id, {}),
                "scheduled_action_count": scheduled_count,
                "final_observation_count": target_score.observation_count,
                "expected_revisit_period_hours": (
                    target_score.expected_revisit_period_hours
                ),
                "max_revisit_gap_hours": target_score.max_revisit_gap_hours,
                "mean_revisit_gap_hours": target_score.mean_revisit_gap_hours,
                "high_gap": target_id in high_gap_ids,
                "unobserved_reason": _unobserved_reason(
                    visibility_window_count=visibility_window_count,
                    option_count=option_count,
                    rejected_count=rejected_count,
                    scheduled_count=scheduled_count,
                ),
            }
        )

    counts = {
        "target_count": len(case.targets),
        "candidate_count": len(orbit_library.candidates),
        "selected_satellite_count": len(selection_result.selected_candidate_ids),
        "visibility_sample_count": visibility_library.sample_count,
        "visibility_window_count": len(visibility_library.windows),
        "candidate_target_pair_count": visibility_library.pair_count,
        "option_count": scheduling_summary.get("option_count", 0),
        "rejected_option_count": len(scheduling_result.rejected_options),
        "action_count": len(scheduling_result.actions),
        "decision_count": len(scheduling_result.decisions),
        "repair_step_count": len(scheduling_result.repair_steps),
        "local_issue_count": len(scheduling_result.validation_report.issues),
        "observed_target_count": scheduling_summary.get("observed_target_count", 0),
        "unobserved_target_count": len(
            scheduling_summary.get("unobserved_target_ids", [])
        ),
        "high_gap_target_count": len(
            scheduling_result.validation_report.high_gap_target_ids
        ),
    }

    return {
        "version": BASELINE_VERSION,
        "case_id": case.case_id,
        "official_verification_boundary": OFFICIAL_VERIFICATION_BOUNDARY,
        "counts": counts,
        "timing_profile": _stage_timing_profile(timing_seconds),
        "mode_comparison_compact": _mode_compact(
            scheduling_result.mode_comparison
        ),
        "target_evidence": target_evidence,
        "target_evidence_summary": {
            "observed_target_ids": scheduling_summary.get("observed_target_ids", []),
            "unobserved_target_ids": scheduling_summary.get(
                "unobserved_target_ids", []
            ),
            "high_gap_target_ids": (
                scheduling_result.validation_report.high_gap_target_ids
            ),
            "top_high_gap_targets": scheduling_summary.get(
                "top_high_gap_targets", []
            ),
        },
    }
