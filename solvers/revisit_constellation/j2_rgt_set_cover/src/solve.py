"""CLI for the J2 RGT set-cover solver."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any
import json
import sys
import time

from .case_io import load_case, load_solver_config
from .certification import CertificationConfig, certify_coverage_claims
from .coverage import CoverageConfig, build_coverage_summary
from .rgt import RgtSearchConfig, search_rgt_templates
from .selection import select_candidates
from .solution import (
    SchedulingConfig,
    build_solution,
)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _profile_status(config: dict[str, Any]) -> dict[str, Any]:
    profiles = config.get("profiles")
    profile_keys = sorted(profiles) if isinstance(profiles, dict) else []
    compute_envelope = config.get("compute_envelope")
    return {
        "active_profile": str(config.get("active_profile", "custom")),
        "compute_envelope": (
            compute_envelope if isinstance(compute_envelope, dict) else {}
        ),
        "available_profiles": profile_keys,
    }


def _unresolved_selected_target_ids(
    *,
    case: Any,
    selection: Any,
    solution_result: Any,
) -> list[str]:
    action_summary = solution_result.opportunity_refinement_summary.get(
        "action_selection_summary",
        {},
    )
    failed = set(action_summary.get("failed_assigned_target_ids", []))
    for target_id in selection.target_assignments:
        gap = solution_result.target_gap_summary.get(target_id)
        if gap is None:
            failed.add(target_id)
            continue
        if (
            gap["max_revisit_gap_hours"]
            > case.targets[target_id].expected_revisit_period_hours + 1.0e-9
        ):
            failed.add(target_id)
    return sorted(failed)


def _solution_quality_key(
    *,
    case: Any,
    selection: Any,
    solution_result: Any,
) -> tuple[Any, ...]:
    unresolved = set(
        _unresolved_selected_target_ids(
            case=case,
            selection=selection,
            solution_result=solution_result,
        )
    )
    satisfied_count = len(set(selection.target_assignments).difference(unresolved))
    worst_gap = max(
        (
            item["max_revisit_gap_hours"]
            for item in solution_result.target_gap_summary.values()
        ),
        default=float("inf"),
    )
    return (
        not solution_result.validation.is_valid,
        -satisfied_count,
        selection.total_required_satellites,
        worst_gap,
        len(solution_result.actions),
    )


def _selection_variant_ids(selection: Any) -> set[tuple[str, int]]:
    return {
        (item.candidate.candidate_id, item.required_satellites)
        for item in selection.selected_candidates
    }


def solve(case_dir: str, config_dir: str | None, solution_dir: str | None) -> int:
    start_time = time.perf_counter()
    output_dir = Path(solution_dir or ".").resolve()
    debug_dir = output_dir / "debug"
    timing_seconds: dict[str, float] = {}
    try:
        stage_start = time.perf_counter()
        case = load_case(case_dir)
        config = load_solver_config(config_dir)
        timing_seconds["case_and_config_load"] = time.perf_counter() - stage_start
        stage_start = time.perf_counter()
        search_config = RgtSearchConfig.from_mapping(config)
        result = search_rgt_templates(case, search_config)
        timing_seconds["closure_search"] = time.perf_counter() - stage_start
        stage_start = time.perf_counter()
        coverage_config = CoverageConfig.from_mapping(config)
        coverage = build_coverage_summary(
            case,
            result.accepted_templates,
            coverage_config,
        )
        timing_seconds["coverage"] = time.perf_counter() - stage_start
        stage_start = time.perf_counter()
        certification_config = CertificationConfig.from_mapping(config)
        certification = certify_coverage_claims(
            case,
            coverage,
            certification_config,
        )
        timing_seconds["certification"] = time.perf_counter() - stage_start
        stage_start = time.perf_counter()
        initial_selection = select_candidates(case, certification)
        timing_seconds["initial_selection"] = time.perf_counter() - stage_start
        stage_start = time.perf_counter()
        scheduling_config = SchedulingConfig.from_mapping(config)
        blacklisted_certification_ids: set[str] = set()
        blacklisted_variants: set[tuple[str, int]] = set()
        selection = initial_selection
        best_selection = selection
        best_solution_result = None
        retry_history: list[dict[str, Any]] = []
        max_attempts = max(1, certification_config.max_selection_retries + 1)
        for attempt_index in range(max_attempts):
            attempt_start = time.perf_counter()
            solution_result = build_solution(
                case=case,
                coverage=coverage,
                selection=selection,
                config=scheduling_config,
            )
            unresolved = _unresolved_selected_target_ids(
                case=case,
                selection=selection,
                solution_result=solution_result,
            )
            attempt_record = {
                "attempt_index": attempt_index,
                "selected_candidate_count": len(selection.selected_candidates),
                "assigned_target_count": len(selection.target_assignments),
                "satellite_count": len(solution_result.satellites),
                "action_count": len(solution_result.actions),
                "local_validation_valid": solution_result.validation.is_valid,
                "unresolved_selected_target_ids": unresolved,
                "blacklisted_certification_ids": sorted(
                    blacklisted_certification_ids
                ),
                "blacklisted_variants": [
                    {
                        "candidate_id": candidate_id,
                        "required_satellites": required_satellites,
                    }
                    for candidate_id, required_satellites in sorted(
                        blacklisted_variants
                    )
                ],
                "elapsed_seconds": time.perf_counter() - attempt_start,
            }
            retry_history.append(attempt_record)
            if best_solution_result is None or _solution_quality_key(
                case=case,
                selection=selection,
                solution_result=solution_result,
            ) < _solution_quality_key(
                case=case,
                selection=best_selection,
                solution_result=best_solution_result,
            ):
                best_selection = selection
                best_solution_result = solution_result
            if solution_result.validation.is_valid and not unresolved:
                break
            new_record_blacklists = {
                assignment.certification_id
                for target_id, assignment in selection.target_assignments.items()
                if target_id in unresolved and assignment.certification_id is not None
            }
            if new_record_blacklists:
                blacklisted_certification_ids.update(new_record_blacklists)
            else:
                blacklisted_variants.update(_selection_variant_ids(selection))
            if attempt_index + 1 >= max_attempts:
                break
            next_selection = select_candidates(
                case,
                certification,
                blacklisted_certification_ids=blacklisted_certification_ids,
                blacklisted_variants=blacklisted_variants,
            )
            if next_selection.as_debug_dict() == selection.as_debug_dict():
                break
            selection = next_selection
        if best_solution_result is None:
            best_solution_result = build_solution(
                case=case,
                coverage=coverage,
                selection=selection,
                config=scheduling_config,
            )
        selection = best_selection
        solution_result = replace(
            best_solution_result,
            retry_history=retry_history,
        )
        timing_seconds["certified_selection_and_solution_build"] = (
            time.perf_counter() - stage_start
        )
        timing_seconds["total_before_writes"] = time.perf_counter() - start_time

        solution = solution_result.solution_json()
        stage_start = time.perf_counter()
        write_json(output_dir / "solution.json", solution)
        write_json(debug_dir / "closure_search.json", result.as_debug_dict())
        write_json(
            debug_dir / "coverage_summary.json",
            {
                **coverage.as_debug_dict(),
                "coverage_truth": "analytical_claims_only",
                "analytical_claims": [
                    claim.as_dict() for claim in certification.claims
                ],
            },
        )
        write_json(
            debug_dir / "certification_summary.json",
            certification.as_debug_dict(),
        )
        write_json(debug_dir / "selection_summary.json", selection.as_debug_dict())
        write_json(
            debug_dir / "initial_selection_summary.json",
            initial_selection.as_debug_dict(),
        )
        write_json(debug_dir / "solution_summary.json", solution_result.as_debug_dict())
        timing_seconds["debug_writes"] = time.perf_counter() - stage_start
        timing_seconds["total"] = time.perf_counter() - start_time
        profile_status = _profile_status(config)
        compute_profile = {
            **profile_status,
            "coverage_worker_count": coverage.config.worker_count,
            "certification_worker_count": certification.config.worker_count,
            "opportunity_worker_count": scheduling_config.opportunity_worker_count,
            "final_solution_timing_seconds": solution_result.timing_seconds,
        }
        status = {
            "status": "completed",
            "solver": "j2_rgt_set_cover",
            "method_status": "certified_pipeline",
            "case_dir": str(case.case_dir),
            "timing_seconds": timing_seconds,
            "compute_profile": compute_profile,
            "closure_search": {
                "accepted_count": len(result.accepted_templates),
                "rejected_count": len(result.rejected_templates),
                "considered_seed_count": result.considered_seed_count,
                "closure_tolerance_m": search_config.closure_tolerance_m,
                "best_surface_error_m": (
                    None
                    if not result.accepted_templates
                    or result.accepted_templates[0].closure is None
                    else result.accepted_templates[0].closure.surface_error_m
                ),
            },
            "coverage": coverage.as_status_dict(),
            "certification": certification.as_status_dict(),
            "selection": selection.as_status_dict(),
            "solution": solution_result.as_status_dict(),
        }
        write_json(output_dir / "status.json", status)
        print(
            "j2_rgt_set_cover templates/candidates/solution: "
            f"{len(result.accepted_templates)} accepted, "
            f"{len(result.rejected_templates)} rejected, "
            f"{len(coverage.candidates)} candidates, "
            f"{len(coverage.windows)} windows, "
            f"{len(certification.passing_records)} certified, "
            f"{len(selection.selected_candidates)} selected, "
            f"{len(solution_result.satellites)} satellites, "
            f"{len(solution_result.actions)} actions, "
            f"selection_retries={len(retry_history) - 1}, "
            f"workers={coverage.config.worker_count}/"
            f"{certification.config.worker_count}/"
            f"{scheduling_config.opportunity_worker_count}/"
            f"profile={profile_status['active_profile']}, "
            f"local_valid={solution_result.validation.is_valid}"
        )
        return 0
    except (ValueError, FileNotFoundError, PermissionError, OSError, json.JSONDecodeError) as exc:
        write_json(
            output_dir / "status.json",
            {
                "status": "error",
                "solver": "j2_rgt_set_cover",
                "error": f"{type(exc).__name__}: {exc}",
                "timing_seconds": {"total": time.perf_counter() - start_time},
            },
        )
        print(f"error: {exc}", file=sys.stderr)
        return 1


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print("usage: solve.py <case_dir> [config_dir] [solution_dir]", file=sys.stderr)
        return 2
    case_dir = args[0]
    config_dir = args[1] if len(args) > 1 else None
    solution_dir = args[2] if len(args) > 2 else None
    return solve(case_dir, config_dir, solution_dir)


if __name__ == "__main__":
    raise SystemExit(main())
