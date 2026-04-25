from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RESULTS_ROOT = REPO_ROOT / "results" / "main_solver"


def _read_run_json(path: Path) -> dict[str, Any]:
    raw_text = path.read_text(encoding="utf-8")
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        return {
            "status": "malformed_artifact",
            "parse_error": str(exc),
            "raw_text": raw_text,
        }
    if not isinstance(payload, dict):
        return {
            "status": "malformed_artifact",
            "parse_error": "run.json must contain an object",
            "raw_text": raw_text,
        }
    return payload


def _metric(payload: dict[str, Any], key: str) -> Any:
    verifier = payload.get("verifier") or {}
    reported = payload.get("reported_metrics") or {}
    verifier_metrics = verifier.get("metrics") if isinstance(verifier, dict) else None
    if isinstance(verifier_metrics, dict) and key in verifier_metrics:
        return verifier_metrics[key]
    if key in verifier:
        return verifier[key]
    return reported.get(key)


def _solver_status(payload: dict[str, Any]) -> dict[str, Any]:
    status = payload.get("solver_status")
    return status if isinstance(status, dict) else {}


def _nested(payload: dict[str, Any], *keys: str) -> Any:
    current: Any = payload
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _json_compact(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _rows(results_root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for run_path in sorted(results_root.glob("*/*/*/run.json")):
        payload = _read_run_json(run_path)
        solver_status = _solver_status(payload)
        timing = _nested(solver_status, "timing_seconds") or {}
        wall_phases = _nested(timing, "wall_phases") or {}
        cp_repair_timing = _nested(timing, "reported_subphases", "cp_repair") or {}
        candidate_summary = _nested(solver_status, "candidate_summary") or {}
        search_summary = _nested(solver_status, "search_summary") or {}
        cp_summary = _nested(solver_status, "cp_summary") or {}
        local_search_summary = _nested(solver_status, "local_search_summary") or {}
        greedy_summary = _nested(solver_status, "greedy_summary") or {}
        rows.append(
            {
                "benchmark": payload.get("benchmark"),
                "solver": payload.get("solver"),
                "case_id": payload.get("case_id"),
                "status": payload.get("status"),
                "evidence_type": payload.get("evidence_type"),
                "runnable": payload.get("runnable"),
                "valid": _metric(payload, "valid"),
                "computed_profit": _metric(payload, "computed_profit"),
                "computed_weight": _metric(payload, "computed_weight"),
                "total_hours": _metric(payload, "total_hours"),
                "n_tracks": _metric(payload, "n_tracks"),
                "n_satisfied_requests": _metric(payload, "n_satisfied_requests"),
                "WCR": _metric(payload, "WCR"),
                "CR": _metric(payload, "CR"),
                "TAT": _metric(payload, "TAT"),
                "PC": _metric(payload, "PC"),
                "u_rms": _metric(payload, "u_rms"),
                "u_max": _metric(payload, "u_max"),
                "coverage_ratio": _metric(payload, "coverage_ratio"),
                "weighted_coverage_ratio": _metric(payload, "weighted_coverage_ratio"),
                "num_actions": _metric(payload, "num_actions"),
                "min_battery_wh": _metric(payload, "min_battery_wh"),
                "execution_mode": solver_status.get("execution_mode"),
                "solve_duration_seconds": _nested(payload, "solve", "duration_seconds"),
                "verifier_duration_seconds": _nested(payload, "verifier", "execution", "duration_seconds"),
                "solver_timing_total_s": timing.get("total"),
                "timing_case_parsing_s": wall_phases.get("case_parsing"),
                "timing_coverage_index_s": wall_phases.get("coverage_index"),
                "timing_candidate_generation_s": wall_phases.get("candidate_generation"),
                "timing_search_s": wall_phases.get("search"),
                "timing_solution_writing_s": wall_phases.get("solution_writing"),
                "timing_debug_writing_s": wall_phases.get("debug_writing"),
                "timing_local_validation_s": wall_phases.get("local_validation"),
                "timing_cp_repair_total_s": cp_repair_timing.get("total"),
                "candidate_count": candidate_summary.get("candidate_count"),
                "positive_coverage_candidate_count": candidate_summary.get("positive_coverage_candidate_count"),
                "evaluated_candidate_count": candidate_summary.get("evaluated_candidate_count"),
                "propagated_window_count": candidate_summary.get("propagated_window_count"),
                "cached_state_sample_reuse_count": candidate_summary.get("cached_state_sample_reuse_count"),
                "search_configured_run_count": search_summary.get("configured_run_count"),
                "search_completed_run_count": search_summary.get("completed_run_count"),
                "search_best_seed": search_summary.get("best_seed"),
                "search_stop_reason": search_summary.get("stop_reason"),
                "greedy_random_choice_probability": greedy_summary.get("random_choice_probability"),
                "greedy_random_choices": greedy_summary.get("random_choices"),
                "local_search_iterations": local_search_summary.get("iterations"),
                "local_search_attempted_moves": local_search_summary.get("attempted_moves"),
                "local_search_accepted_moves": local_search_summary.get("accepted_moves"),
                "local_search_stop_reason": local_search_summary.get("stop_reason"),
                "cp_backend": cp_summary.get("backend"),
                "cp_sat_version": cp_summary.get("cp_sat_version"),
                "cp_calls": cp_summary.get("calls"),
                "cp_successful_calls": cp_summary.get("successful_calls"),
                "cp_call_success_rate": cp_summary.get("call_success_rate"),
                "cp_improving_solutions": cp_summary.get("improving_solutions"),
                "cp_improving_success_rate": cp_summary.get("improving_success_rate"),
                "cp_model_build_time_s": cp_summary.get("model_build_time_s"),
                "cp_solve_time_s": cp_summary.get("solve_time_s"),
                "cp_branches": cp_summary.get("branches"),
                "cp_conflicts": cp_summary.get("conflicts"),
                "cp_status_counts": _json_compact(cp_summary.get("status_counts")),
                "parse_error": payload.get("parse_error"),
                "raw_text": payload.get("raw_text"),
                "run_json": str(run_path),
            }
        )
    return rows


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "benchmark",
        "solver",
        "case_id",
        "status",
        "evidence_type",
        "runnable",
        "valid",
        "computed_profit",
        "computed_weight",
        "total_hours",
        "n_tracks",
        "n_satisfied_requests",
        "WCR",
        "CR",
        "TAT",
        "PC",
        "u_rms",
        "u_max",
        "coverage_ratio",
        "weighted_coverage_ratio",
        "num_actions",
        "min_battery_wh",
        "execution_mode",
        "solve_duration_seconds",
        "verifier_duration_seconds",
        "solver_timing_total_s",
        "timing_case_parsing_s",
        "timing_coverage_index_s",
        "timing_candidate_generation_s",
        "timing_search_s",
        "timing_solution_writing_s",
        "timing_debug_writing_s",
        "timing_local_validation_s",
        "timing_cp_repair_total_s",
        "candidate_count",
        "positive_coverage_candidate_count",
        "evaluated_candidate_count",
        "propagated_window_count",
        "cached_state_sample_reuse_count",
        "search_configured_run_count",
        "search_completed_run_count",
        "search_best_seed",
        "search_stop_reason",
        "greedy_random_choice_probability",
        "greedy_random_choices",
        "local_search_iterations",
        "local_search_attempted_moves",
        "local_search_accepted_moves",
        "local_search_stop_reason",
        "cp_backend",
        "cp_sat_version",
        "cp_calls",
        "cp_successful_calls",
        "cp_call_success_rate",
        "cp_improving_solutions",
        "cp_improving_success_rate",
        "cp_model_build_time_s",
        "cp_solve_time_s",
        "cp_branches",
        "cp_conflicts",
        "cp_status_counts",
        "parse_error",
        "raw_text",
        "run_json",
    ]
    with path.open("w", encoding="utf-8", newline="") as file_obj:
        writer = csv.DictWriter(file_obj, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="Aggregate main solver results")
    parser.add_argument("--results-root", default=str(DEFAULT_RESULTS_ROOT))
    args = parser.parse_args()

    results_root = Path(args.results_root)
    results_root.mkdir(parents=True, exist_ok=True)
    rows = _rows(results_root)
    summary = {
        "results_root": str(results_root),
        "row_count": len(rows),
        "rows": rows,
    }
    (results_root / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _write_csv(results_root / "summary.csv", rows)
    print(f"wrote {len(rows)} rows to {results_root / 'summary.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
