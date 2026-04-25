# Solver Audit: cp_local_search_stereo_insertion

## Bottom Line
- Target claim: faithful reproduction adapted to the benchmark
- Status: NOT_YET
- Compute status: BOTH
- Headline blockers:
- The benchmark contract adaptation is mostly in place: mission loading uses `max_stereo_pair_separation_s`, products are target-global, cross-satellite pair and tri products are represented, and sequence insertion is product-atomic across satellites.
- The current implementation is not yet ready to claim a fair optimization and compute envelope. Product construction and seed construction still dominate runtime, local search is not receiving a meaningful search regime on measured outputs, and the public README still reports obsolete small-scale validation numbers.
- Current evidence is also incomplete for promotion: the full 5 public cases have not been rerun after the cross-satellite/product-pruning changes, and the latest available timing artifacts are noisy enough that they should be treated as diagnostic rather than final benchmark evidence.

## Compute And Runtime

### Literature regime
Lemaitre et al. frame the AEOS track selection and scheduling problem as a highly combinatorial sequence selection problem with time windows, transition times, strip/stereo coupling constraints, and feasible image sequences. Their local search maintains a current feasible sequence, performs insertion and removal moves, keeps earliest/latest starting-time propagation variables, and uses stochastic repeated tries with an evolving insertion probability. The reported local-search evaluation uses quality profiles over many executions; for one large instance, the profile is summarized over 100 executions, and the comparison table gives LSA 100 runs with a 2 minute runtime limit per run.

The literature therefore expects a genuine sustained search regime, not a single short pass whose runtime is mostly spent constructing candidates and products. It also expects repeated stochastic executions or equivalent multi-run profiling when making method-quality claims.

### Current regime
The current solver executes:
- case loading from public benchmark files,
- candidate generation,
- feasible product-library construction,
- deterministic greedy seed construction with a tri-stereo upgrade pass,
- deterministic product-level local search,
- conservative repair,
- optional multi-run replay when `num_runs > 1`.

The default run policy is still `num_runs: 1`, `max_time_seconds: 120.0`, and `parallel_workers: null`. Candidate generation can use process workers across satellites. Product construction, seed construction, local search, and repair are single-process Python with NumPy/Brahe/Skyfield calls in the hot path.

### Execution model
Candidate generation has meaningful process-level parallelism across satellites. The rest of the dominant path is single-threaded Python orchestration:
- product enumeration loops over target-local candidate pairs and prerequisite-compatible triples,
- overlap and geometry evaluation are called repeatedly inside Python loops,
- seed selection repeatedly recomputes remaining counts and scans/pops from the full product pool,
- local search clones and tries product-level insert/replace/remove/swap moves in a deterministic order.

There is no compiled extension, graph solver, CP solver, tabu engine, or distributed execution in the dominant search phases.

### Runtime profile
Latest inspected diagnostic artifacts:
- `/tmp/cp_phase2_case_0001/status.json`
- `/tmp/cp_phase3_case_0001_direct/status.json`

Pre-pruning diagnostic profile on `test/case_0001`:
- candidate generation: 19.29 s
- product library: 54.62 s
- seed: 195.43 s
- local search: 53.06 s
- total: 269.37 s
- candidates: 7,815
- materialized products: 276,917
- feasible products: 32,570
- final coverage: 142 targets
- final quality: 141.5726

Post-pruning diagnostic profile on `test/case_0001`:
- candidate generation: 82.30 s
- product library: 206.15 s
- seed: 167.12 s
- local search: 1.74 s
- total: 455.85 s
- candidates: 7,815
- materialized products: 32,570
- feasible products: 32,570
- pair candidates considered: 269,817
- pair candidates pruned before geometry: 224,412
- pair products retained: 27,618
- tri candidates evaluated: 194,851
- tri products retained: 4,952
- tri geometry rejections: 168,220
- bounded tri products: 21,679
- final coverage: 142 targets
- final quality: 141.5726

The product-pruning counters are good evidence that the implementation now avoids materializing infeasible products. They are not good evidence that the runtime envelope is solved: measured product-library time worsened in the available artifact, candidate generation varied despite no candidate-generation change, and local search received only about 1.7 seconds in the cleanest Phase 3 artifact.

### Why the current budget is or is not fair
The current budget is not fair enough to support the target claim. The issue is not just that the time limit is too short; the current implementation leaves obvious performance on the table before time should simply be increased.

The strongest evidence:
- Product construction still evaluates 194,851 tri candidates and rejects 168,220 through geometry on `case_0001`.
- Seed construction remains a major bottleneck and still uses repeated global pool scans and repeated remaining-count recomputation.
- The measured local-search stage is small relative to construction time, which means the named planning/search method is often not the dominant computation.
- The literature local search relies on repeated stochastic attempts and quality profiles; default `num_runs: 1` does not match that regime.

More time would help only after product construction and seed construction are improved enough that the additional time actually goes to search.

## Optimization And Time Budget

### Bottlenecks
Product construction:
- Still performs target-global pair and tri enumeration in Python.
- Performs expensive geometry and Monte Carlo overlap checks inside nested loops.
- Uses useful early pair prerequisite pruning, but tri candidate enumeration and geometry rejection remain large.

Seed construction:
- Recomputes remaining product counts for the pool on each loop iteration.
- Uses `max(range(len(pool)), key=...)` over the active pool and `pop(best_idx)`.
- This is effectively quadratic in the number of feasible products and becomes expensive at the 32k product scale.

Local search:
- Move logic is present, but the measured run spent very little time there.
- The current deterministic move ordering is useful for reproducibility, but it does not reproduce the literature stochastic repeated-try regime by default.

Documentation and evidence:
- README validation numbers are stale and describe the old small candidate/product scale.
- Phase 4 public-case validation has not been refreshed after the current cross-satellite and pruning work.

### What to optimize first
- Replace seed selection with a target-indexed or heap/bucket strategy that avoids repeated full-pool rescans and repeated remaining-count recomputation.
- Add stronger tri-candidate pruning before `_evaluate_triple`, for example per-target top-k pair graph bounds, quality upper bounds, or anchor-aware filtering.
- Parallelize product geometry evaluation across targets or target chunks after deterministic ordering is locked down.
- Separate construction budget from local-search budget in status and run policy so reported `max_time_seconds` is not mistaken for total solver time.
- Make multi-run evaluation a documented benchmark profile rather than a hidden optional knob.

### Recommended budget and run policy
For current code, the honest policy is diagnostic, not final:
- Use `num_runs: 1` only for deterministic smoke validation and reproducibility checks.
- Use a multi-minute total runtime envelope for public evidence, because construction alone can consume several minutes on `case_0001`.
- Do not claim a fair local-search envelope until construction has been reduced enough that local search receives sustained time.

After basic optimization:
- Keep a deterministic single-run profile for CI and documentation reproducibility.
- Add a benchmark profile with multiple deterministic seeds, for example `num_runs: 5` to `10`, and report best/mean coverage and quality.
- Consider a per-case budget of at least several minutes for the benchmark profile. The literature comparison used 2 minutes per LSA run and 100 LSA executions for meaningful profiles; the adapted solver does not need to match that literally, but it should not present a single setup-heavy run as the search regime.

## Reproduction Gaps

### Implemented and adapted pieces
- ADAPTED: Benchmark case loading and mission contract, including `allow_cross_satellite_stereo` and `max_stereo_pair_separation_s`.
- ADAPTED: Candidate generation from TLEs, target geometry, solar elevation, off-nadir steering, and fixed benchmark observation windows.
- ADAPTED: Product-coupled stereo handling for benchmark pair and tri-stereo, including target-global cross-satellite products.
- ADAPTED: Atomic product insertion and rollback across per-satellite sequences.
- ADAPTED: Earliest/latest propagation shape is preserved, but benchmark candidates have fixed windows, so `e_i = l_i = start_i`.
- IMPLEMENTED: Deterministic local search with insert, replace, remove, and swap/repair moves over whole products.
- IMPLEMENTED: Conservative repair pass for sequence conflicts.
- IMPLEMENTED: Optional deterministic multi-run harness with `num_runs` and `random_seed`.

### Partial or missing pieces
- PARTIAL: Lemaitre local search stochastic regime. The code has deterministic perturbation for multi-run mode, but the default policy is a single deterministic run and does not implement evolving insertion probability `p_a`, random insertion/removal selection with the paper's probabilities, or quality-profile evaluation.
- PARTIAL: Lemaitre CP approach. The solver has CP-style sequence feasibility and temporal propagation concepts, but it does not implement an OPL/CP complete or bounded complete search model.
- PARTIAL: Literature track-builder/greedy context. The implementation uses a pool-based coverage-first product seed rather than the sequential track-builder described in Lemaitre's greedy algorithm.
- PARTIAL: Compute realism. Dominant product/seed phases are still single-threaded Python and are not optimized enough to call the runtime envelope fair.
- MISSING: Final public validation evidence for all 5 redesigned public cases after current cross-satellite and pruning changes.
- MISSING: Updated public README/runtime-policy table reflecting current metrics.
- EXTRA: Tri-stereo and cross-satellite products are benchmark-driven extensions not present as such in the original single-satellite track model.
- EXTRA: Conservative repair and Vasquez-style remove/repair ideas are useful robustness features, but they are not the core Lemaitre method.

### What must change to reach the target claim
- Complete Phase 4 public validation and update docs with current evidence.
- Optimize seed construction enough that it is no longer the dominant bottleneck.
- Reduce or parallelize product geometry work enough that local search receives a meaningful share of the budget.
- Define a documented fair run policy, likely including deterministic multi-run mode, and show best/mean metrics.
- Keep known algorithmic differences explicit: benchmark-adapted product coupling and deterministic reproducibility are valid adaptations, while missing stochastic quality profiling and exact CP search should remain documented limitations.

## Action Plan
- Optimize seed selection with indexed candidate queues or per-target best-product structures.
- Add stronger tri-pruning before expensive overlap/geometry checks.
- Parallelize product construction by target once deterministic output order is preserved.
- Run all 5 public test cases end-to-end and verify with the benchmark verifier.
- Run two byte-level deterministic single-run checks on one representative case.
- Run a benchmark multi-run profile after construction cost is improved.
- Replace stale README validation table and config comments with current metrics, exact commands, and budget policy.
- Keep `cp_local_search_stereo_insertion-audit.md` or a promoted solver-local audit/report until Phase 4 evidence is updated.

## Sanity Footnote
- The focused solver test suite currently passes after trimming expensive public-case subprocess tests: `55 passed in 2.26s`.
- The local worktree has uncommitted changes to `src/repair.py` and `tests/solvers/test_cp_local_search_stereo_insertion.py`.
- Existing `case_0001` status artifacts show strong final coverage and quality and no repair loss, but they are not sufficient as final public evidence because timings are noisy and public-case validation has not been refreshed after the latest implementation state.
