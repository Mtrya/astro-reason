"""Solver entrypoint: generate candidates, enumerate products, optimize, and emit a valid solution."""

from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from pathlib import Path

from candidates import generate_candidates
from case_io import load_case, load_solver_config
from models import CandidateObservation, PruningSummary, RepairLog, SolveSummary
from products import enumerate_products
from pruning import prune_candidates
from milp_model import solve_milp
from repair import repair_solution


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, default=str)


def _candidate_to_action(cand: CandidateObservation) -> dict:
    return {
        "type": "observation",
        "satellite_id": cand.sat_id,
        "target_id": cand.target_id,
        "start_time": cand.start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "end_time": cand.end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "off_nadir_along_deg": cand.off_nadir_along_deg,
        "off_nadir_across_deg": cand.off_nadir_across_deg,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Time-window-pruned stereo MILP solver: candidate generation, product enumeration, pruning, and optimization."
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
        mission, satellites, targets = load_case(case_dir)

        candidate_start = time.perf_counter()
        candidates, rejections, candidate_summary = generate_candidates(
            mission, satellites, targets, config_payload
        )
        candidate_end = time.perf_counter()

        product_start = time.perf_counter()
        pairs, tris, product_summary = enumerate_products(
            candidates, satellites, targets, mission, config_payload
        )
        product_end = time.perf_counter()

        # Optional time-window cluster pruning
        pruning_start = time.perf_counter()
        pruning_cfg = config_payload.get("pruning", {})
        if pruning_cfg.get("enabled", False):
            candidates, pairs, tris, pruning_summary = prune_candidates(
                candidates, pairs, tris, satellites, targets, mission, config_payload
            )
        else:
            pruning_summary = PruningSummary(
                enabled=False,
                cluster_gap_s=0.0,
                lambda_cap=0,
                pre_candidates=len(candidates),
                post_candidates=len(candidates),
                pre_pairs=len(pairs),
                post_pairs=len(pairs),
                pre_tris=len(tris),
                post_tris=len(tris),
            )
        pruning_end = time.perf_counter()

        # MILP solve or greedy fallback
        solve_start = time.perf_counter()
        selected_indices, solve_summary = solve_milp(
            candidates, pairs, tris, targets, satellites, mission, config_payload
        )
        solve_end = time.perf_counter()

        selected_candidates = [candidates[i] for i in selected_indices]

        # Conservative deterministic repair
        repair_start = time.perf_counter()
        repaired_candidates, repair_log = repair_solution(
            selected_candidates, pairs, tris, satellites, targets, mission, config_payload
        )
        repair_end = time.perf_counter()

        # Recompute solve_summary with post-repair counts
        post_set = set(repaired_candidates)
        post_pairs = sum(
            1 for p in pairs if p.valid and p.candidate_i in post_set and p.candidate_j in post_set
        )
        post_tris = sum(
            1 for t in tris if t.valid and all(c in post_set for c in t.candidates)
        )
        post_coverage = set()
        post_quality = 0.0
        for p in pairs:
            if p.valid and p.candidate_i in post_set and p.candidate_j in post_set:
                post_coverage.add(p.target_id)
                post_quality += p.q_pair
        for t in tris:
            if t.valid and all(c in post_set for c in t.candidates):
                post_coverage.add(t.target_id)
                post_quality += t.q_tri

        solve_summary.selected_observations = len(repaired_candidates)
        solve_summary.selected_pairs = post_pairs
        solve_summary.selected_tris = post_tris
        solve_summary.covered_targets = len(post_coverage)
        solve_summary.objective_coverage = len(post_coverage)
        solve_summary.objective_quality = post_quality

        solution = {"actions": [_candidate_to_action(c) for c in repaired_candidates]}
        solution_path = solution_dir / "solution.json"
        _write_json(solution_path, solution)

        status = {
            "status": "solved",
            "solver_version": "time_window_pruned_stereo_milp",
            "case_dir": str(case_dir),
            "config_dir": str(config_dir) if config_dir is not None else None,
            "solution": str(solution_path),
            "satellite_count": len(satellites),
            "target_count": len(targets),
            "candidate_counts": candidate_summary.as_dict(),
            "product_counts": product_summary.as_dict(),
            "pruning_summary": pruning_summary.as_dict(),
            "solve_summary": solve_summary.as_dict(),
            "repair_summary": repair_log.as_dict(),
            "timing_seconds": {
                "candidate_generation": candidate_end - candidate_start,
                "product_enumeration": product_end - product_start,
                "pruning": pruning_end - pruning_start,
                "solve": solve_end - solve_start,
                "repair": repair_end - repair_start,
                "total": time.perf_counter() - total_start,
            },
            "approximation_flags": {
                "access_intervals": "coarse_time_step_approximate",
                "solar_elevation": "sampled_at_midpoint",
                "los": "checked_at_midpoint",
                "overlap": product_summary.approximation_flags.get("overlap_method", "unknown"),
                "pixel_scale_secant_correction": product_summary.approximation_flags.get("pixel_scale_secant_correction", False),
                "note": "Access intervals are coarse-step approximations; minor SGP4 drift relative to exact propagation is expected.",
            },
        }
        _write_json(solution_dir / "status.json", status)

        if config_payload.get("debug", False):
            debug_dir = solution_dir / "debug"
            _write_json(
                debug_dir / "candidate_summary.json",
                {
                    "case_dir": str(case_dir),
                    "candidate_counts": candidate_summary.as_dict(),
                    "sample_candidates": [_candidate_to_action(c) for c in candidates[:50]],
                    "sample_rejections": [
                        {
                            "sat_id": r.sat_id,
                            "target_id": r.target_id,
                            "interval_id": r.interval_id,
                            "reason": r.reason,
                            "start": r.start.strftime("%Y-%m-%dT%H:%M:%SZ") if r.start else None,
                            "end": r.end.strftime("%Y-%m-%dT%H:%M:%SZ") if r.end else None,
                        }
                        for r in rejections[:50]
                    ],
                },
            )
            _write_json(
                debug_dir / "product_summary.json",
                {
                    "case_dir": str(case_dir),
                    "product_counts": product_summary.as_dict(),
                    "sample_valid_pairs": [
                        {
                            "sat_id": p.sat_id,
                            "target_id": p.target_id,
                            "access_interval_id": p.access_interval_id,
                            "convergence_deg": p.convergence_deg,
                            "overlap_fraction": p.overlap_fraction,
                            "pixel_scale_ratio": p.pixel_scale_ratio,
                            "q_pair": p.q_pair,
                            "valid": p.valid,
                        }
                        for p in pairs[:30]
                    ],
                    "sample_valid_tris": [
                        {
                            "sat_id": t.sat_id,
                            "target_id": t.target_id,
                            "access_interval_id": t.access_interval_id,
                            "common_overlap_fraction": t.common_overlap_fraction,
                            "pair_valid_flags": t.pair_valid_flags,
                            "has_anchor": t.has_anchor,
                            "q_tri": t.q_tri,
                            "valid": t.valid,
                        }
                        for t in tris[:30]
                    ],
                },
            )
            _write_json(
                debug_dir / "pruning_summary.json",
                {
                    "case_dir": str(case_dir),
                    "pruning_summary": pruning_summary.as_dict(),
                },
            )
            _write_json(
                debug_dir / "repair_log.json",
                {
                    "case_dir": str(case_dir),
                    "repair_summary": repair_log.as_dict(),
                },
            )

    except Exception as exc:
        traceback_text = traceback.format_exc()
        solution_dir.mkdir(parents=True, exist_ok=True)
        _write_json(
            solution_dir / "status.json",
            {
                "status": "error",
                "solver_version": "time_window_pruned_stereo_milp",
                "case_dir": str(case_dir),
                "config_dir": str(config_dir) if config_dir is not None else None,
                "error": str(exc),
                "traceback": traceback_text,
            },
        )
        print(traceback_text, file=sys.stderr, end="")
        return 2

    n_removed = len(repair_log.removed_observations)
    print(
        f"solved: case={case_dir.name} "
        f"candidates={candidate_summary.total_accepted} "
        f"pairs={product_summary.total_pairs} valid_pairs={product_summary.valid_pairs} "
        f"tris={product_summary.total_tris} valid_tris={product_summary.valid_tris} "
        f"pruned={pruning_summary.pre_candidates - pruning_summary.post_candidates} "
        f"selected_obs={solve_summary.selected_observations} "
        f"covered_targets={solve_summary.covered_targets} "
        f"backend={solve_summary.backend_used} "
        f"repaired={n_removed} "
        f"-> {solution_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
