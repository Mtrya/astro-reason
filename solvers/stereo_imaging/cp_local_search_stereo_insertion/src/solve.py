"""Solver entrypoint: parse case, enumerate candidates and products, emit empty solution."""

from __future__ import annotations

import argparse
import sys
import time
import traceback
from pathlib import Path

from candidates import CandidateConfig, generate_candidates
from case_io import load_case, load_solver_config
from products import ProductConfig, build_product_library
from solution_io import write_debug_artifacts, write_json, write_solution


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
    timing_seconds: dict[str, float],
) -> dict:
    return {
        "status": "phase_1_candidates_and_product_library",
        "phase": 1,
        "case_dir": str(case_dir),
        "config_dir": str(config_dir) if config_dir is not None else None,
        "solution": str(solution_path),
        "case_id": case_id,
        "satellite_count": len(product_library.summary.per_target_product_counts),
        "candidate_config": candidate_config.as_status_dict(),
        "product_config": product_config.as_status_dict(),
        "candidate_summary": candidate_summary.as_dict(),
        "product_summary": product_library.summary.as_dict(),
        "timing_seconds": timing_seconds,
        "reproduction_summary": {
            "candidate_count": candidate_summary.candidate_count,
            "product_count": product_library.summary.total_products,
            "feasible_product_count": product_library.summary.feasible_products,
            "pair_product_count": product_library.summary.pair_products,
            "tri_product_count": product_library.summary.tri_products,
            "zero_product_target_count": len(product_library.summary.zero_product_target_ids),
            "runtime_seconds": timing_seconds["total"],
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate stereo_imaging candidates and product library (Phase 1)."
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

        case = load_case(case_dir)
        case_id = case.case_dir.name

        candidate_start = time.perf_counter()
        candidates, candidate_summary = generate_candidates(case, candidate_config)
        candidate_end = time.perf_counter()

        product_start = time.perf_counter()
        product_library = build_product_library(candidates, case, product_config)
        product_end = time.perf_counter()

        solution_path = write_solution(solution_dir)
        total_end = time.perf_counter()

        timing_seconds = {
            "candidate_generation": candidate_end - candidate_start,
            "product_library": product_end - product_start,
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
            timing_seconds=timing_seconds,
        )
        write_json(solution_dir / "status.json", status)

        if candidate_config.debug:
            write_debug_artifacts(
                solution_dir,
                case_id=case_id,
                candidates=candidates,
                candidate_summary=candidate_summary,
                product_library=product_library,
                timing_seconds=timing_seconds,
            )
    except Exception as exc:
        traceback_text = traceback.format_exc()
        solution_dir.mkdir(parents=True, exist_ok=True)
        write_json(
            solution_dir / "status.json",
            {
                "status": "error",
                "phase": 1,
                "case_dir": str(case_dir),
                "config_dir": str(config_dir) if config_dir is not None else None,
                "error": str(exc),
                "traceback": traceback_text,
            },
        )
        print(traceback_text, file=sys.stderr, end="")
        return 2

    print(
        f"phase_1_candidates_and_product_library: {case_id} "
        f"candidates={candidate_summary.candidate_count} "
        f"products={product_library.summary.total_products} "
        f"feasible={product_library.summary.feasible_products} "
        f"pairs={product_library.summary.pair_products} "
        f"tris={product_library.summary.tri_products} "
        f"zero_product_targets={len(product_library.summary.zero_product_target_ids)} "
        f"-> {solution_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
