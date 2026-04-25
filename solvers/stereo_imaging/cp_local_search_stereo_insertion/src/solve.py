"""Solver entrypoint: parse case, enumerate candidates and products, emit solution.

Multi-run harness:
- When local_search_config.num_runs > 1, the full pipeline (seed + local search +
  repair) is executed num_runs times with deterministic perturbation derived from
  random_seed + run_index.  The best solution is kept.
- Aggregate statistics (best, mean coverage/quality) are written to status.json.
"""

from __future__ import annotations

import argparse
import random
import sys
import time
import traceback
from pathlib import Path
from typing import Any

from candidates import CandidateConfig, generate_candidates
from case_io import load_case, load_solver_config
from local_search import LocalSearchConfig, run_local_search
from products import ProductConfig, build_product_library
from repair import RepairConfig, repair_state
from seed import SeedConfig, build_greedy_seed
from sequence import create_empty_state, insert_product, remove_product
from solution_io import (
    write_debug_artifacts,
    write_json,
    write_solution_from_state,
)


def _build_status(
    *,
    case_dir: Path,
    config_dir: Path | None,
    solution_path: Path,
    case_id: str,
    satellite_count: int,
    candidate_config: CandidateConfig,
    candidate_summary,
    product_config: ProductConfig,
    product_library,
    sequence_sanity: dict,
    timing_seconds: dict[str, float],
    seed_result,
    local_search_result=None,
    local_search_config=None,
    repair_result=None,
    repair_config=None,
    multi_run_stats: dict[str, Any] | None = None,
) -> dict:
    status = {
        "status": "multi_run",
        "case_dir": str(case_dir),
        "config_dir": str(config_dir) if config_dir is not None else None,
        "solution": str(solution_path),
        "case_id": case_id,
        "satellite_count": satellite_count,
        "candidate_config": candidate_config.as_status_dict(),
        "product_config": product_config.as_status_dict(),
        "seed_config": seed_result.config.as_status_dict() if seed_result else None,
        "local_search_config": local_search_config.as_status_dict() if local_search_config is not None else None,
        "repair_config": repair_config.as_status_dict() if repair_config is not None else None,
        "candidate_summary": candidate_summary.as_dict(),
        "product_summary": product_library.summary.as_dict(),
        "sequence_sanity": sequence_sanity,
        "seed_summary": seed_result.as_dict() if seed_result else None,
        "local_search_summary": local_search_result.as_dict() if local_search_result else None,
        "repair_summary": repair_result.as_dict() if repair_result else None,
        "timing_seconds": timing_seconds,
        "reproduction_summary": {
            "candidate_count": candidate_summary.candidate_count,
            "product_count": product_library.summary.total_products,
            "feasible_product_count": product_library.summary.feasible_products,
            "pair_product_count": product_library.summary.pair_products,
            "tri_product_count": product_library.summary.tri_products,
            "zero_product_target_count": len(product_library.summary.zero_product_target_ids),
            "seed_accepted": seed_result.accepted_count if seed_result else 0,
            "seed_covered_targets": seed_result.covered_target_count if seed_result else 0,
            "local_search_passes": local_search_result.passes_completed if local_search_result else 0,
            "local_search_accepted": local_search_result.moves_accepted if local_search_result else 0,
            "repair_removed": len(repair_result.removed_products) if repair_result else 0,
            "repair_lost_targets": len(repair_result.lost_targets) if repair_result else 0,
            "final_coverage": repair_result.final_coverage if repair_result else 0,
            "final_quality": repair_result.final_quality if repair_result else 0.0,
            "runtime_seconds": timing_seconds["total"],
        },
    }
    if multi_run_stats is not None:
        status["multi_run_stats"] = multi_run_stats
    return status


def _run_sequence_sanity(product_library, case) -> dict:
    """Quick sanity check: insert a few feasible products, verify consistency, remove them."""
    state = create_empty_state(case)
    sample_products = product_library.products[:5]
    if not sample_products:
        return {"checked": False, "reason": "no feasible products"}

    inserted = 0
    removed = 0
    for product in sample_products:
        result = insert_product(product, state, case)
        if result.success:
            inserted += 1
            remove_product(product, state, case)
            removed += 1

    all_empty = all(len(seq.observations) == 0 for seq in state.sequences.values())
    return {
        "checked": True,
        "attempted": len(sample_products),
        "inserted": inserted,
        "removed": removed,
        "all_empty_after_remove": all_empty,
    }


def _run_pipeline(
    case,
    product_library,
    seed_config: SeedConfig,
    local_search_config: LocalSearchConfig,
    repair_config: RepairConfig,
    rng: random.Random | None = None,
) -> tuple:
    """Run one full pass: seed -> local search -> repair.

    Returns (seed_result, local_search_result, repair_result, repaired_state).
    """
    seed_result = build_greedy_seed(product_library, case, seed_config, rng=rng)

    local_search_result = None
    if not seed_config.seed_only:
        local_search_result = run_local_search(
            seed_result.state,
            seed_result.accepted_products,
            product_library,
            case,
            local_search_config,
            rng=rng,
        )
        best_state = local_search_result.best_state.sequence_state
        scheduled_products = local_search_result.best_state.scheduled_products
    else:
        best_state = seed_result.state
        scheduled_products = {p.product_id: p for p in seed_result.accepted_products}

    repair_result, repaired_state, _ = repair_state(
        best_state, scheduled_products, case, repair_config
    )
    return seed_result, local_search_result, repair_result, repaired_state


def _pipeline_objective(repair_result) -> tuple[int, float]:
    """Lexicographic objective from repair result."""
    return (repair_result.final_coverage, repair_result.final_quality)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="CP/local-search stereo insertion solver."
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
        candidate_config = CandidateConfig.from_mapping(config_payload)
        product_config = ProductConfig.from_mapping(config_payload)
        seed_config = SeedConfig.from_mapping(config_payload)
        local_search_config = LocalSearchConfig.from_mapping(config_payload)
        repair_config = RepairConfig.from_mapping(config_payload)

        case = load_case(case_dir)
        case_id = case.case_dir.name

        candidate_start = time.perf_counter()
        candidates, candidate_summary = generate_candidates(case, candidate_config)
        candidate_end = time.perf_counter()

        product_start = time.perf_counter()
        product_library = build_product_library(candidates, case, product_config)
        product_end = time.perf_counter()

        sanity_start = time.perf_counter()
        sequence_sanity = _run_sequence_sanity(product_library, case)
        sanity_end = time.perf_counter()

        num_runs = local_search_config.num_runs
        random_seed = local_search_config.random_seed

        # Single run (default) or multi-run harness
        if num_runs <= 1:
            seed_start = time.perf_counter()
            seed_result, local_search_result, repair_result, repaired_state = _run_pipeline(
                case, product_library, seed_config, local_search_config, repair_config
            )
            seed_end = time.perf_counter()
            timing_local_search = 0.0
            if local_search_result is not None:
                timing_local_search = local_search_result.time_seconds
            multi_run_stats = None
        else:
            # Multi-run harness
            run_results: list[tuple] = []
            coverages: list[int] = []
            qualities: list[float] = []
            pipeline_start = time.perf_counter()

            for run_index in range(num_runs):
                run_seed = random_seed + run_index
                rng = random.Random(run_seed)
                seed_result, local_search_result, repair_result, repaired_state = _run_pipeline(
                    case, product_library, seed_config, local_search_config, repair_config, rng=rng
                )
                run_results.append((seed_result, local_search_result, repair_result, repaired_state))
                coverages.append(repair_result.final_coverage)
                qualities.append(repair_result.final_quality)

            # Pick best run by lexicographic (coverage, quality)
            best_idx = max(range(num_runs), key=lambda i: (coverages[i], qualities[i]))
            seed_result, local_search_result, repair_result, repaired_state = run_results[best_idx]

            pipeline_end = time.perf_counter()
            seed_end = pipeline_end
            seed_start = pipeline_start
            timing_local_search = 0.0
            if local_search_result is not None:
                timing_local_search = local_search_result.time_seconds

            multi_run_stats = {
                "num_runs": num_runs,
                "random_seed": random_seed,
                "best_run": best_idx,
                "best_coverage": coverages[best_idx],
                "best_quality": qualities[best_idx],
                "mean_coverage": sum(coverages) / num_runs,
                "mean_quality": sum(qualities) / num_runs,
                "min_coverage": min(coverages),
                "min_quality": min(qualities),
                "all_coverages": coverages,
                "all_qualities": qualities,
            }

        repair_start = time.perf_counter()
        # repair already done in _run_pipeline
        repair_end = time.perf_counter()
        timing_repair = repair_end - repair_start

        solution_path = write_solution_from_state(solution_dir, repaired_state)

        total_end = time.perf_counter()

        timing_seconds = {
            "candidate_generation": candidate_end - candidate_start,
            "product_library": product_end - product_start,
            "sequence_sanity": sanity_end - sanity_start,
            "seed": seed_end - seed_start,
            "local_search": timing_local_search,
            "repair": timing_repair,
            "total": total_end - total_start,
        }

        status = _build_status(
            case_dir=case_dir,
            config_dir=config_dir,
            solution_path=solution_path,
            case_id=case_id,
            satellite_count=len(case.satellites),
            candidate_config=candidate_config,
            candidate_summary=candidate_summary,
            product_config=product_config,
            product_library=product_library,
            sequence_sanity=sequence_sanity,
            timing_seconds=timing_seconds,
            seed_result=seed_result,
            local_search_result=local_search_result,
            local_search_config=local_search_config,
            repair_result=repair_result,
            repair_config=repair_config,
            multi_run_stats=multi_run_stats,
        )
        write_json(solution_dir / "status.json", status)

        if candidate_config.debug or seed_config.seed_only or local_search_result is not None:
            write_debug_artifacts(
                solution_dir,
                case_id=case_id,
                candidates=candidates,
                candidate_summary=candidate_summary,
                product_library=product_library,
                timing_seconds=timing_seconds,
                sequence_state=repaired_state,
                seed_result=seed_result,
                local_search_result=local_search_result,
                repair_result=repair_result,
            )
    except Exception as exc:
        traceback_text = traceback.format_exc()
        solution_dir.mkdir(parents=True, exist_ok=True)
        write_json(
            solution_dir / "status.json",
            {
                "status": "error",
                "case_dir": str(case_dir),
                "config_dir": str(config_dir) if config_dir is not None else None,
                "error": str(exc),
                "traceback": traceback_text,
            },
        )
        print(traceback_text, file=sys.stderr, end="")
        return 2

    if local_search_result is not None:
        print(
            f"case: {case_id} "
            f"candidates={candidate_summary.candidate_count} "
            f"products={product_library.summary.total_products} "
            f"feasible={product_library.summary.feasible_products} "
            f"pairs={product_library.summary.pair_products} "
            f"tris={product_library.summary.tri_products} "
            f"zero_product_targets={len(product_library.summary.zero_product_target_ids)} "
            f"seed_accepted={seed_result.accepted_count} "
            f"seed_covered={seed_result.covered_target_count} "
            f"ls_passes={local_search_result.passes_completed} "
            f"ls_accepted={local_search_result.moves_accepted} "
            f"ls_best={local_search_result.best_objective} "
            f"repair_removed={len(repair_result.removed_products)} "
            f"repair_lost={len(repair_result.lost_targets)} "
            f"final_coverage={repair_result.final_coverage} "
            f"-> {solution_path}"
        )
    else:
        print(
            f"case: {case_id} "
            f"candidates={candidate_summary.candidate_count} "
            f"products={product_library.summary.total_products} "
            f"feasible={product_library.summary.feasible_products} "
            f"pairs={product_library.summary.pair_products} "
            f"tris={product_library.summary.tri_products} "
            f"zero_product_targets={len(product_library.summary.zero_product_target_ids)} "
            f"seed_accepted={seed_result.accepted_count} "
            f"seed_covered={seed_result.covered_target_count} "
            f"seed_only=true "
            f"repair_removed={len(repair_result.removed_products)} "
            f"repair_lost={len(repair_result.lost_targets)} "
            f"final_coverage={repair_result.final_coverage} "
            f"-> {solution_path}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
