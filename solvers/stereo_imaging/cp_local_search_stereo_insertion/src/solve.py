"""Solver entrypoint: parse case, enumerate candidates and products, emit solution."""

from __future__ import annotations

import argparse
import sys
import time
import traceback
from pathlib import Path

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
    write_solution,
    write_solution_from_state,
)


def _build_status(
    *,
    case_dir: Path,
    config_dir: Path | None,
    solution_path: Path,
    case_id: str,
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
) -> dict:
    return {
        "status": "phase_5_repair",
        "phase": 5,
        "case_dir": str(case_dir),
        "config_dir": str(config_dir) if config_dir is not None else None,
        "solution": str(solution_path),
        "case_id": case_id,
        "satellite_count": len(product_library.summary.per_target_product_counts),
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


def _run_sequence_sanity(product_library, case) -> dict:
    """Quick sanity check: insert a few feasible products, verify consistency, remove them."""
    state = create_empty_state(case)
    feasible_products = [p for p in product_library.products if p.feasible][:5]
    if not feasible_products:
        return {"checked": False, "reason": "no feasible products"}

    inserted = 0
    removed = 0
    for product in feasible_products:
        result = insert_product(product, state, case)
        if result.success:
            inserted += 1
            remove_product(product, state, case)
            removed += 1

    all_empty = all(len(seq.observations) == 0 for seq in state.sequences.values())
    return {
        "checked": True,
        "attempted": len(feasible_products),
        "inserted": inserted,
        "removed": removed,
        "all_empty_after_remove": all_empty,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="CP/local-search stereo insertion solver (Phase 5)."
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

        seed_start = time.perf_counter()
        seed_result = build_greedy_seed(product_library, case, seed_config)
        seed_end = time.perf_counter()

        local_search_result = None
        if not seed_config.seed_only:
            ls_start = time.perf_counter()
            local_search_result = run_local_search(
                seed_result.state,
                seed_result.accepted_products,
                product_library,
                case,
                local_search_config,
            )
            ls_end = time.perf_counter()
            timing_local_search = ls_end - ls_start
            best_state = local_search_result.best_state.sequence_state
            scheduled_products = local_search_result.best_state.scheduled_products
        else:
            timing_local_search = 0.0
            best_state = seed_result.state
            scheduled_products = {
                p.product_id: p for p in seed_result.accepted_products
            }

        # Repair
        repair_start = time.perf_counter()
        repair_result, repaired_state, _repaired_products = repair_state(
            best_state, scheduled_products, case, repair_config
        )
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
                "phase": 5,
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
            f"phase_5_repair: {case_id} "
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
            f"phase_5_repair: {case_id} "
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
