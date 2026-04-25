"""Solver entrypoint for RGT/APC gap-aware construction."""

from __future__ import annotations

import argparse
import sys
import time
import traceback
from pathlib import Path

from .baseline import build_baseline_evidence
from .case_io import load_case, load_solver_config
from .orbit_library import OrbitLibraryConfig, generate_orbit_library
from .scheduling import SchedulingConfig, schedule_observations
from .selection import SelectionConfig, select_satellites_greedy
from .solution_io import write_json, write_solution
from .visibility import VisibilityConfig, build_visibility_library


def _paper_adaptation_notes() -> dict:
    return {
        "issue": "https://github.com/Mtrya/astro-reason/issues/87",
        "method_lineage": [
            {
                "source": "Lee et al. 2020 APC/RGT",
                "paper_concept": "Seed-satellite access profile, constellation pattern vector, and coverage timeline under repeating ground-track/common-ground-track structure.",
                "benchmark_adaptation": "Generate bounded circular RGT/APC candidate phase slots and score their sampled target visibility timelines by benchmark revisit-gap metrics instead of solving Lee's BILP coverage-satisfaction model.",
            },
            {
                "source": "Mercado-Martinez et al. 2025 constructive AEOSSP",
                "paper_concept": "Rank targets by freshness/AoI, assignment flexibility, and opportunity cost; refine with insertion/removal local search.",
                "benchmark_adaptation": "Use boundary-inclusive midpoint revisit gaps as freshness, remaining feasible observation options as flexibility, conflict profit as opportunity cost, and deterministic high-gap insertion/removal repair under solver-local hard-validity checks.",
            },
        ],
        "benchmark_contract_mapping": {
            "coverage_timeline": "Target observation midpoint timelines scored with capped max, raw max, mean revisit gap, and threshold violation count.",
            "access_profile": "Solver-local visibility windows sampled from candidate satellite states to benchmark targets.",
            "observation_profit": "Quality-weighted freshness proxy using off-nadir/range/elevation and current target gap.",
            "temporal_constraints": "Same-satellite overlap and bang-coast-bang slew/settle feasibility approximated locally before official experiment verification.",
            "energy_constraints": "Conservative solver-local battery risk screen; official resource truth remains the benchmark verifier.",
            "local_search": "Deterministic repair removes invalid or risky scheduled observations and inserts feasible observations for high-gap targets.",
        },
        "comparison_modes": {
            "no_op": "Selected constellation only, no observation actions.",
            "fifo": "Earliest feasible visibility opportunity first.",
            "constructive": "Freshness/flexibility/opportunity-cost schedule before repair.",
            "repaired": "Final solver output after deterministic repair.",
        },
        "official_verification_boundary": "The solver records local metrics only. Official validity and metrics are produced by experiments/main_solver through the benchmark verifier executable.",
    }


def _build_status(
    *,
    case_dir: Path,
    config_dir: Path | None,
    solution_path: Path,
    case,
    orbit_config: OrbitLibraryConfig,
    visibility_config: VisibilityConfig,
    selection_config: SelectionConfig,
    scheduling_config: SchedulingConfig,
    orbit_library,
    visibility_library,
    selection_result,
    scheduling_result,
    timing_seconds: dict[str, float],
    baseline_evidence: dict,
) -> dict:
    return {
        "status": "phase_6_reproduction_fidelity_validated",
        "phase": 6,
        "case_dir": str(case_dir),
        "config_dir": str(config_dir) if config_dir is not None else None,
        "solution": str(solution_path),
        "case_id": case.case_id,
        "target_count": len(case.targets),
        "max_num_satellites": case.max_num_satellites,
        "horizon_duration_sec": case.horizon_duration_sec,
        "satellite_output_count": len(selection_result.selected_candidate_ids),
        "action_output_count": len(scheduling_result.actions),
        "orbit_library_config": orbit_config.as_status_dict(),
        "visibility_config": visibility_config.as_status_dict(),
        "selection_config": selection_config.as_status_dict(),
        "scheduling_config": scheduling_config.as_status_dict(),
        "orbit_library": orbit_library.as_status_dict(),
        "visibility": visibility_library.as_status_dict(),
        "selection": selection_result.as_status_dict(),
        "scheduling": scheduling_result.as_status_dict(),
        "baseline_evidence": baseline_evidence,
        "reproduction_fidelity": {
            "mode_comparison": scheduling_result.mode_comparison,
            "debug_summary": scheduling_result.debug_summary,
            "paper_adaptation_notes": _paper_adaptation_notes(),
        },
        "timing_seconds": timing_seconds,
        "reproduction_notes": {
            "method_reference": "Lee et al. 2020 APC / RGT pattern plus Mercado-Martinez et al. 2025 freshness constructive scheduling",
            "components_reproduced_this_phase": {
                "public_case_parsing": True,
                "bounded_rgt_apc_candidate_states": True,
                "access_profile_visibility_sampling": True,
                "opportunity_window_grouping": True,
                "benchmark_style_gap_scoring": True,
                "greedy_gap_aware_satellite_selection": True,
                "freshness_flexibility_opportunity_cost_scheduling": True,
                "solver_local_validation_and_repair": True,
                "fifo_no_op_constructive_repaired_comparison": True,
                "paper_vs_benchmark_adaptation_notes": True,
            },
            "components_deferred": {
                "full_verifier_equivalent_energy_repair": "future tuning against official verifier traces",
            },
            "action_output_reason": "The emitted solution uses the repaired mode; no-op, FIFO, and unrepaired constructive modes are recorded as solver-local debug comparisons.",
            "paper_adaptation_summary": _paper_adaptation_notes(),
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build RGT/APC-style candidates and a gap-aware revisit schedule."
    )
    parser.add_argument("--case-dir", required=True)
    parser.add_argument("--config-dir", default="")
    parser.add_argument("--solution-dir", required=True)
    args = parser.parse_args(argv)

    case_dir = Path(args.case_dir).resolve()
    config_dir = Path(args.config_dir).resolve() if args.config_dir else None
    solution_dir = Path(args.solution_dir).resolve()

    try:
        total_start = time.perf_counter()
        config_payload = load_solver_config(config_dir)
        case = load_case(case_dir)

        orbit_config = OrbitLibraryConfig.from_mapping(config_payload, case)
        visibility_config = VisibilityConfig.from_mapping(config_payload)
        selection_config = SelectionConfig.from_mapping(config_payload)
        scheduling_config = SchedulingConfig.from_mapping(config_payload)

        orbit_start = time.perf_counter()
        orbit_library = generate_orbit_library(case, orbit_config)
        orbit_end = time.perf_counter()

        visibility_start = time.perf_counter()
        visibility_library = build_visibility_library(
            case,
            orbit_library.candidates,
            visibility_config,
        )
        visibility_end = time.perf_counter()

        selection_start = time.perf_counter()
        selection_result = select_satellites_greedy(
            case=case,
            candidates=orbit_library.candidates,
            windows=visibility_library.windows,
            config=selection_config,
        )
        selection_end = time.perf_counter()

        scheduling_start = time.perf_counter()
        scheduling_result = schedule_observations(
            case=case,
            selected_candidate_ids=selection_result.selected_candidate_ids,
            selected_candidates=selection_result.selected_candidates,
            windows=visibility_library.windows,
            config=scheduling_config,
        )
        scheduling_end = time.perf_counter()

        solution_path = write_solution(
            solution_dir,
            satellites=[
                candidate.as_solution_satellite()
                for candidate in selection_result.selected_candidates
            ],
            actions=scheduling_result.actions,
        )
        total_end = time.perf_counter()
        timing_seconds = {
            "orbit_library": orbit_end - orbit_start,
            "visibility": visibility_end - visibility_start,
            "selection": selection_end - selection_start,
            "scheduling": scheduling_end - scheduling_start,
            "total": total_end - total_start,
        }
        baseline_evidence = build_baseline_evidence(
            case=case,
            orbit_library=orbit_library,
            visibility_library=visibility_library,
            selection_result=selection_result,
            scheduling_result=scheduling_result,
            timing_seconds=timing_seconds,
        )
        status = _build_status(
            case_dir=case_dir,
            config_dir=config_dir,
            solution_path=solution_path,
            case=case,
            orbit_config=orbit_config,
            visibility_config=visibility_config,
            selection_config=selection_config,
            scheduling_config=scheduling_config,
            orbit_library=orbit_library,
            visibility_library=visibility_library,
            selection_result=selection_result,
            scheduling_result=scheduling_result,
            timing_seconds=timing_seconds,
            baseline_evidence=baseline_evidence,
        )
        write_json(solution_dir / "status.json", status)
        write_json(
            solution_dir / "debug" / "orbit_candidates.json",
            [candidate.as_dict() for candidate in orbit_library.candidates],
        )
        write_json(
            solution_dir / "debug" / "visibility_windows.json",
            [window.as_dict() for window in visibility_library.windows],
        )
        write_json(
            solution_dir / "debug" / "selection_rounds.json",
            [round_info.as_dict() for round_info in selection_result.rounds],
        )
        write_json(
            solution_dir / "debug" / "scheduling_decisions.json",
            [decision.as_dict() for decision in scheduling_result.decisions],
        )
        write_json(
            solution_dir / "debug" / "scheduling_rejections.json",
            scheduling_result.rejected_options,
        )
        write_json(
            solution_dir / "debug" / "local_validation.json",
            scheduling_result.validation_report.as_dict(),
        )
        write_json(
            solution_dir / "debug" / "repair_steps.json",
            [step.as_dict() for step in scheduling_result.repair_steps],
        )
        write_json(
            solution_dir / "debug" / "scheduling_summary.json",
            scheduling_result.debug_summary,
        )
        write_json(
            solution_dir / "debug" / "baseline_summary.json",
            baseline_evidence,
        )
        write_json(
            solution_dir / "debug" / "mode_comparison.json",
            scheduling_result.mode_comparison,
        )
        write_json(
            solution_dir / "debug" / "adaptation_notes.json",
            _paper_adaptation_notes(),
        )
    except Exception as exc:
        traceback_text = traceback.format_exc()
        solution_dir.mkdir(parents=True, exist_ok=True)
        write_json(
            solution_dir / "status.json",
            {
                "status": "failed",
                "error": str(exc),
                "traceback": traceback_text,
            },
        )
        print(traceback_text, file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
