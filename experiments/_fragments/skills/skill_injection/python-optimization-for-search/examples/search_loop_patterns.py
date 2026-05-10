#!/usr/bin/env python3
"""Synthetic search-loop optimization patterns for the python-optimization-for-search skill."""

from __future__ import annotations

import argparse
import json
import math
import os
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor
from functools import lru_cache
from pathlib import Path
from typing import Iterable

import numpy as np


def validate_vectorized_filter() -> None:
    target_priority = np.array([10.0, 20.0])
    machine_skill = np.array([1.0, 2.0, 4.0])
    difficulty = np.array([1.0, 4.0])
    score = target_priority[:, None] * np.exp(-difficulty[:, None] / machine_skill[None, :])
    expected = np.array(
        [
            [3.67879441, 6.0653066, 7.78800783],
            [0.36631278, 2.70670566, 7.35758882],
        ]
    )
    assert score.shape == (2, 3)
    assert np.allclose(score, expected, atol=1e-8)
    assert np.argwhere(score >= 7.0).tolist() == [[0, 2], [1, 2]]


def build_candidate_batch(args: tuple[int, int, int, int]) -> dict[str, list[float]]:
    block_id, n_targets, n_machines, seed = args
    rng = np.random.default_rng(seed + block_id)
    target_ids = np.arange(block_id * n_targets, (block_id + 1) * n_targets, dtype=np.int64)
    centers = rng.integers(0, 7200, size=n_targets).astype(np.float64)
    priority = rng.uniform(1.0, 5.0, size=n_targets)
    difficulty = rng.uniform(0.2, 3.0, size=n_targets)
    machine_ids = np.arange(n_machines, dtype=np.int64)
    machine_skill = np.linspace(0.8, 2.5, n_machines)
    machine_offset = np.linspace(-35.0, 35.0, n_machines)
    duration = 20.0 + 4.0 * difficulty[:, None]
    start = centers[:, None] + machine_offset[None, :] - duration / 2.0
    end = start + duration
    score = priority[:, None] * np.exp(-difficulty[:, None] / machine_skill[None, :]) - 0.002 * np.abs(machine_offset[None, :])
    feasible = (start >= 0.0) & (end <= 7200.0) & (score >= 0.8)
    target_index, machine_index = np.nonzero(feasible)
    return {
        "target": target_ids[target_index].astype(int).tolist(),
        "machine": machine_ids[machine_index].astype(int).tolist(),
        "start": start[feasible].round(3).tolist(),
        "end": end[feasible].round(3).tolist(),
        "score": score[feasible].round(6).tolist(),
    }


def merge_batches(batches: Iterable[dict[str, list[float]]]) -> dict[str, np.ndarray]:
    rows: dict[str, list[float]] = {"target": [], "machine": [], "start": [], "end": [], "score": []}
    for batch in batches:
        for key in rows:
            rows[key].extend(batch[key])
    ids = np.arange(len(rows["score"]), dtype=np.int64)
    return {
        "id": ids,
        "target": np.asarray(rows["target"], dtype=np.int64),
        "machine": np.asarray(rows["machine"], dtype=np.int64),
        "start": np.asarray(rows["start"], dtype=np.float64),
        "end": np.asarray(rows["end"], dtype=np.float64),
        "score": np.asarray(rows["score"], dtype=np.float64),
    }


@lru_cache(maxsize=4096)
def transition_gap_s(machine_id: int, left_target_mod: int, right_target_mod: int) -> float:
    return 3.0 + 0.25 * machine_id + abs(left_target_mod - right_target_mod)


def fits(candidate_id: int, selected: set[int], candidates: dict[str, np.ndarray]) -> bool:
    machine = int(candidates["machine"][candidate_id])
    start = float(candidates["start"][candidate_id])
    end = float(candidates["end"][candidate_id])
    target_mod = int(candidates["target"][candidate_id] % 11)
    for other_id in selected:
        if int(candidates["machine"][other_id]) != machine:
            continue
        other_start = float(candidates["start"][other_id])
        other_end = float(candidates["end"][other_id])
        other_mod = int(candidates["target"][other_id] % 11)
        if end <= other_start:
            gap = transition_gap_s(machine, target_mod, other_mod)
            if end + gap <= other_start:
                continue
        elif other_end <= start:
            gap = transition_gap_s(machine, other_mod, target_mod)
            if other_end + gap <= start:
                continue
        return False
    return True


def checkpoint(path: Path, selected: set[int], candidates: dict[str, np.ndarray], phase: str, counters: dict[str, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    chosen = sorted(selected, key=lambda i: (int(candidates["machine"][i]), float(candidates["start"][i]), int(candidates["target"][i]), int(i)))
    payload = {
        "phase": phase,
        "score": round(sum(float(candidates["score"][i]) for i in chosen), 6),
        "selected_count": len(chosen),
        "counters": counters,
        "actions": [
            {
                "candidate_id": int(i),
                "target": int(candidates["target"][i]),
                "machine": int(candidates["machine"][i]),
                "start": float(candidates["start"][i]),
                "end": float(candidates["end"][i]),
                "score": float(candidates["score"][i]),
            }
            for i in chosen
        ],
    }
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp_path, path)


def generate_candidates(blocks: int, targets_per_block: int, machines: int, seed: int, workers: int) -> dict[str, np.ndarray]:
    batch_args = [(block_id, targets_per_block, machines, seed) for block_id in range(blocks)]
    if workers > 1:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            batches = list(pool.map(build_candidate_batch, batch_args))
    else:
        batches = [build_candidate_batch(arg) for arg in batch_args]
    candidates = merge_batches(batches)
    order = np.lexsort((candidates["id"], candidates["start"], -candidates["score"]))
    return {key: value[order] for key, value in candidates.items()}


def greedy_seed(candidates: dict[str, np.ndarray], counters: dict[str, int]) -> set[int]:
    selected: set[int] = set()
    covered_targets: set[int] = set()
    for candidate_id in range(len(candidates["id"])):
        counters["greedy_considered"] += 1
        target = int(candidates["target"][candidate_id])
        if target in covered_targets:
            continue
        if fits(candidate_id, selected, candidates):
            selected.add(candidate_id)
            covered_targets.add(target)
    return selected


def improve(selected: set[int], candidates: dict[str, np.ndarray], counters: dict[str, int], max_passes: int) -> set[int]:
    selected = set(selected)
    best_score = sum(float(candidates["score"][i]) for i in selected)
    candidate_order = sorted(range(len(candidates["id"])), key=lambda i: (-float(candidates["score"][i]), float(candidates["end"][i]), int(candidates["target"][i]), int(i)))
    for _ in range(max_passes):
        improved = False
        for candidate_id in candidate_order:
            counters["moves_considered"] += 1
            if candidate_id in selected:
                continue
            target = int(candidates["target"][candidate_id])
            duplicate_targets = [i for i in selected if int(candidates["target"][i]) == target]
            conflicts = [
                i
                for i in selected
                if i not in duplicate_targets
                and int(candidates["machine"][i]) == int(candidates["machine"][candidate_id])
                and not fits(candidate_id, selected - {i}, candidates)
            ]
            remove = set(duplicate_targets + conflicts[:1])
            trial = (selected - remove) | {candidate_id}
            if not fits(candidate_id, trial - {candidate_id}, candidates):
                continue
            trial_score = sum(float(candidates["score"][i]) for i in trial)
            if trial_score > best_score + 1e-9:
                selected = trial
                best_score = trial_score
                counters["moves_accepted"] += 1
                improved = True
        if not improved:
            break
    return selected


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--blocks", type=int, default=4)
    parser.add_argument("--targets-per-block", type=int, default=28)
    parser.add_argument("--machines", type=int, default=5)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--max-passes", type=int, default=2)
    parser.add_argument("--checkpoint", type=Path, default=Path(tempfile.gettempdir()) / "search_loop_patterns_checkpoint.json")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    validate_vectorized_filter()
    started = time.perf_counter()
    counters = {"greedy_considered": 0, "moves_considered": 0, "moves_accepted": 0}
    candidates = generate_candidates(args.blocks, args.targets_per_block, args.machines, args.seed, args.workers)
    assert len(candidates["id"]) > 0
    selected = greedy_seed(candidates, counters)
    checkpoint(args.checkpoint, selected, candidates, "greedy_seed", counters)
    selected = improve(selected, candidates, counters, args.max_passes)
    checkpoint(args.checkpoint, selected, candidates, "improved", counters)
    elapsed = time.perf_counter() - started
    payload = json.loads(args.checkpoint.read_text(encoding="utf-8"))
    assert payload["phase"] == "improved"
    assert math.isclose(payload["score"], round(sum(float(candidates["score"][i]) for i in selected), 6))
    print(json.dumps({"candidates": int(len(candidates["id"])), "selected": int(len(selected)), "score": payload["score"], "elapsed_s": round(elapsed, 4), "checkpoint": str(args.checkpoint)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
