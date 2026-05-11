---
name: python-optimization-for-search
description: Use when writing or speeding up Python search-heavy solvers, candidate generators, product enumerators, or local-search loops under a fixed runtime budget; covers profiling, caching, batching, NumPy vectorization, multiprocessing, deterministic search control, and checkpointing without domain-specific scheduling strategy or OR-Tools modeling.
---

# Python Optimization For Search

When a Python solver is slow because it repeatedly builds candidates, evaluates pairwise/product feasibility, scans large pools, or runs improvement loops, keep correctness first: every optimization must preserve a simple, inspectable data flow and deterministic output.

Use `examples/search_loop_patterns.py` only when you need a runnable pattern for batching, deterministic search, and atomic checkpoint writes.

The fastest candidate is the one you never create. Before multiprocessing, vectorization, or CP-SAT-style selection, check whether the candidate library is too large. Prune early by dominance, margin, natural buckets, and per-job alternatives; then optimize the smaller data flow.

## Symptom To Fix

| Symptom | First fix |
|---|---|
| Candidate generation is slow | Batch by natural independent blocks and cache parsed/static inputs. |
| Candidate count explodes | Add cheap filters, per-key caps, dominance checks, and staged widening before using expensive scoring. |
| Pair/product filtering is slow | Precompute indexes by target/resource/time bucket and vectorize dense numeric masks. |
| Search rescans everything | Store candidate ids and conflict neighborhoods; update only affected neighbors. |
| Multiprocessing is slower | Increase task size, send smaller inputs, or return to deterministic serial code. |
| Improvements are hard to debug | Sort by stable keys, log accept/reject counters, and recompute the objective from scratch after moves. |
| Risk of no final output | Write the best complete solution early and replace it atomically on improvement. |

## Workflow

1. Make the naive version valid on a tiny instance before optimizing.
2. Add stage counters and timings for candidate generation, indexing, scoring/filtering, search moves, repair, and output writing.
3. Profile the whole run with `cProfile`, then micro-time only the few functions you might rewrite.
4. Cache pure expensive computations keyed by small stable values.
5. Prune the candidate library with cheap filters and per-key caps before expensive all-pairs/product enumeration.
6. Batch work by independent blocks such as satellite, target group, resource, day, or shard; build reusable intermediate libraries once.
7. Vectorize dense numeric transforms when records fit cleanly into arrays.
8. Parallelize only coarse independent batches after the serial version is deterministic and measured.
9. Run bounded deterministic improvement loops and checkpoint the best valid or most-likely-valid output early and often.

## Candidate Budgets

Use explicit budgets while developing:

- Print counts after each stage: raw candidates, locally feasible candidates, products, conflicts, selected products, and rejected products by reason.
- Build a tiny first library that can produce a valid incumbent.
- Keep only the best `k` alternatives per target/job/request/resource bucket for the first pass.
- Remove dominated candidates that are worse on value, feasibility margin, and conflict pressure.
- Widen the caps only after the saved incumbent is valid and the profiler shows candidate scarcity, not search overhead.
- Avoid dense all-pairs matrices when a keyed join or time-bucket scan can produce the same high-quality products.

Large candidate sets are not automatically more intelligent. They often bury useful options under model-construction time and repair work.

## Profiling

- Use `python -m cProfile -o profile.pstats script.py ...` for whole-run evidence, then inspect cumulative and internal time with `pstats`.
- Use `timeit` only for small, isolated alternatives after the profiler identifies a hot path.
- Keep counters beside timings: number of candidates, number of products, number of rejected pairs, number of moves attempted, number of moves accepted, and number of checkpoint writes.
- Separate construction time from search time. A slow product library needs a different fix than a slow local-search loop.

## Caching

- Cache only pure functions: same inputs must mean same output, with no hidden mutable state.
- Prefer `functools.lru_cache(maxsize=...)` or `functools.cache` for scalar or tuple-key computations.
- Use manual dictionaries for array, table, or object results so memory ownership is explicit.
- Cache expensive state series, geometry transforms, parsed input records, feasible candidate lists, and product metadata. Do not cache cheap arithmetic unless profiling proves it matters.
- Put cache keys in canonical units and rounded forms when floating-point noise would create accidental misses.

## Batching And Indexing

- Build the candidate/product library once, then reuse it across seed construction, local search, repair, and multi-run variants.
- Batch by natural independence boundaries so each batch has compact inputs and compact outputs.
- Index pools by the question the search loop asks most often: by target, resource, time bucket, candidate id, product id, or conflict neighborhood.
- Replace repeated full-pool rescans with sorted queues, precomputed masks, adjacency lists, or per-key lists.
- Store immutable candidate ids in search state. Keep bulky numeric fields in arrays or tables addressed by id.
- Keep top candidates per index key while building the library. Do not wait until the search loop to discover that every key has hundreds of weak near-duplicates.

## Vectorization

- Use NumPy arrays and ufuncs for elementwise numeric scoring, threshold filters, distance/time transforms, and dense pair/block comparisons.
- Use broadcasting intentionally: check shapes with asserts before relying on a vectorized expression.
- Convert vectorized boolean masks back to compact candidate ids before entering branch-heavy scheduling logic.
- Use `out=` or staged arrays when a hot expression creates large temporaries.
- Avoid vectorization for variable-length records, complex rollback logic, small one-off loops where array construction dominates, object dtype arrays, and dense all-pairs matrices that exceed memory.
- Always keep a tiny expected-output assertion near a vectorized rewrite; if the mask is wrong, fast code just fails faster.

## Multiprocessing

- Use `concurrent.futures.ProcessPoolExecutor` for coarse CPU-bound independent batches after serial profiling shows useful work per task.
- Put worker functions at module top level and guard execution with `if __name__ == "__main__":`.
- Send compact picklable inputs to workers and return compact outputs. Avoid passing large object graphs or mutable global state.
- Keep task order deterministic: sort inputs before submission and sort/merge results by stable keys after completion.
- Do not use process pools for tiny tasks, debug-first phases, large shared arrays that would be copied into each worker, or nested calls from inside a worker.

## Deterministic Search Loops

- Define one explicit score tuple, for example `(coverage_gain, quality_gain, -cost, stable_id)`.
- Sort candidates and moves by stable keys; if randomized perturbation is useful, seed it and record the seed.
- Bound loops by wall time, passes, moves, and no-improvement count.
- Evaluate each tentative move through a cheap local delta check before committing.
- Make moves atomic: save the old state, apply the change, validate affected constraints, then commit or roll back.
- Reuse the same candidate/product library across deterministic multi-run perturbations.

## Checkpointing

- Write a complete solution whenever the best score improves and after each major phase.
- Write atomically through a temporary file plus rename so interrupted runs leave a readable previous checkpoint.
- Include a small local scratch status sidecar with score, counters, timing, seed, selected count, and last completed phase; do not treat it as part of the final submission unless the task explicitly asks for it.
- Prefer an early valid lower-quality output over waiting until the end to write the only solution.

## Keep It Safe

- Optimize only after you have a correctness check.
- Keep the old simple path or a small expected-output test near risky rewrites.
- Prefer changes that make the data flow easier to inspect: fewer repeated scans, clearer indexes, and explicit checkpoints.
- Preserve a simple greedy or insertion path as the fallback whenever an exact or heavy optimizer fails to return a complete solution.
