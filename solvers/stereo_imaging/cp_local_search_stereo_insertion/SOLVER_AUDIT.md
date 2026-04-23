# Solver Audit: CP/Local-Search Stereo Insertion Solver

## Bottom Line

- **Target claim:** faithful reproduction of Lemaître et al. 2002 (CP/local-search over same-pass stereo/tri-stereo products), adapted to the `stereo_imaging` benchmark contract.
- **Status:** NOT_YET
- **Compute status:** OPTIMIZATION_BLOCKED
- **Headline blockers:**
  1. The claimed local-search method is not actually running in a regime where it can improve results; the greedy seed is locally optimal on every tested case, and the move neighborhood is too weak to escape.
  2. ~~Zero tri-stereo products are scheduled across all 5 public cases despite thousands of feasible tri-stereo candidates being generated.~~ **RESOLVED in Phase 7a.** Tri-stereo products are now scheduled on 4 of 5 public cases via weighted lexicographic ranking and a tri-stereo upgrade pass.
  3. The deterministic single-run policy contradicts the paper's stochastic profiling regime (100 runs of 2 minutes each). The solver is evaluated as if it were a deterministic greedy baseline, not a local-search method.
  4. The greedy seed algorithm is not the Lemaître GA; it is a pool-based coverage-first heuristic that was added by the implementation team and has no paper provenance.

## Compute And Runtime

### Literature regime

Lemaître et al. (2002, §3.4) report:
- Local Search Algorithm (LSA) reaches steady average/maximum quality after **~1 minute CPU** on a 342-candidate-strip instance.
- Experiments use **2 minutes per instance**, with LSA run **100 times** for statistical profiling.
- The paper's instances have 212–1068 candidate images, comparable to the benchmark's public cases (235–666 candidates).

Vasquez and Hao (2001) report large SPOT5 instances within a **one-hour operating limit**.

The paper explicitly warns: "An irritating drawback of local search methods is their non-determinism: each execution results in a different solution. To get an idea of the performance of a local search algorithm, it is a common practice to compute a quality profile... over 100 different resolutions."

### Current regime

Post-Phase-7a timings on public cases (single run, single-threaded Python, warm filesystem cache):

- case_0001: ~37 s total (seed ~20 s, local search ~3 s)
- case_0002: ~11 s total (seed ~6 s, local search ~1 s)
- case_0003: ~17 s total (seed ~8 s, local search ~2 s)
- case_0004: ~38 s total (seed ~21 s, local search ~4 s)
- case_0005: ~7 s total (seed ~4 s, local search ~0 s)

Local search accepts **0 improving moves on 4 of 5 cases**; case_0004 accepts 1 move. The seed is already at a local optimum for the move neighborhood on most cases.

### Execution model

- **Single-threaded Python 3.13** with `numpy` and `skyfield`.
- No multiprocessing, no compiled extensions, no GPU.
- Hot path: skyfield SGP4 propagation (now cached) → solver-local geometry → sequence propagation.

### Runtime profile

A satellite-state cache eliminated the dominant skyfield bottleneck, cutting total runtime from ~184 s to ~37 s on case_0001. The cache was a necessary hygiene fix, not an algorithmic improvement.

The remaining time is split roughly:
- ~55 % greedy seed (coverage-first ranking + atomic insertion attempts)
- ~25 % candidate generation and product library
- ~10 % local search (but it finds 0–1 improving moves)
- ~10 % overhead

### Why the current budget is or is not fair

The current regime is **not fair to the claimed method** for three reasons:

1. **The local-search method never executes meaningfully.** The paper's LSA is a stochastic, restart-heavy search that improves over minutes. Our implementation is a deterministic descent that stops after one pass because the seed is already locally optimal. More time would not help because the move neighborhood is too weak.

2. **The run policy contradicts the paper.** The paper expects 100 runs for profiling. We evaluate a single deterministic run. This is like evaluating a Monte Carlo tree search with one playout and calling it fair.

3. **The execution model is a blocker.** Single-threaded Python is acceptable for a greedy baseline but not for a local-search method that should be exploring a large neighborhood. The paper's implementation was compiled C-like code on 2002 hardware. Our Python implementation is at least one order of magnitude slower per move evaluation.

The benchmark envelope itself is fair (no hard timeout), but the solver is shaped around "finish quickly in one deterministic run" rather than "execute the claimed local-search method."

## Optimization And Time Budget

### Bottlenecks

1. **Greedy seed dominates runtime** (~55 % of total). The seed is a pool-based O(n²) scan, not the paper's sequential track-builder. It is an implementation invention, not a literature element, yet it consumes most of the budget.

2. **Local search is starved of algorithmic machinery.** The paper uses randomized insertion/removal probabilities, adaptive p_a, and 100 restarts. We have deterministic insert/replace/swap with no restarts. The neighborhood is too small to escape the seed's local optimum.

3. ~~**Tri-stereo scheduling is completely absent.**~~ **RESOLVED.** Phase 7a introduced weighted lexicographic ranking and a tri-stereo upgrade pass. Tri-stereo products are now scheduled on cases 1–4 (13, 6, 6, and 10 tri products respectively). Coverage does not regress on any case.

### What to optimize first

Before increasing runtime or thread count, fix the remaining algorithmic gaps:

1. **Add removal moves to local search.** The paper's LSA removes low-value images to make room for better ones. Our local search only removes during swap moves, which are too conservative.

2. **Add stochastic restarts.** Run the seed + local search multiple times with different tie-breaking or randomization, and keep the best result. This is the paper's evaluation regime.

3. **Parallelize candidate generation and product library.** These are embarrassingly parallel (independent per target/satellite) and could use `multiprocessing` or `concurrent.futures`.

### Recommended budget and run policy

- **Minimum to be fair:** 10 independent runs of 2 minutes each (matching the paper's profiling regime), keeping the best result. Total budget: ~20 minutes per case.
- **Better:** 100 runs of 2 minutes each, as in the paper. Total budget: ~3.5 hours per case.
- **Execution model:** keep single-threaded Python for correctness, but parallelize the multi-run evaluation across cores.

## Reproduction Gaps

### Implemented and adapted pieces

- **IMPLEMENTED** — per-satellite sequence feasibility with earliest/latest propagation (Lemaître §3.3, Fig. 9–10).
- **IMPLEMENTED** — atomic product insertion with rollback when partner observations fail (Lemaître §3.4, INSERTIONMOVE).
- **IMPLEMENTED** — tri-stereo scheduling via weighted lexicographic ranking and upgrade pass (Phase 7a, benchmark extension).
- **ADAPTED** — fixed candidate observation times instead of continuous time windows (benchmark contract requirement).
- **ADAPTED** — benchmark-native stereo/tri-stereo product feasibility (convergence, overlap, pixel-scale, near-nadir anchor) instead of paper's simplified stereo constraint.
- **ADAPTED** — coverage-first lexicographic objective instead of paper's linear/non-linear weighted sum.
- **EXTRA** — conservative repair pass (Vasquez-inspired defensive step, not in Lemaître).

### Partial or missing pieces

- **PARTIAL** — Greedy seed. The paper's GA (§3.1) is a sequential track-builder with look-ahead and iterative refinement. Our seed is a pool-based coverage-first heuristic invented for this implementation. It happens to work well on small cases but has no paper provenance.

- **PARTIAL** — Local search moves. The paper has insertion + removal with randomized probabilities and adaptive p_a. We have deterministic insert/replace/swap. The missing removal move is critical because it allows the search to escape local optima by freeing up sequence capacity.

- **MISSING** — Stochastic profiling / multi-run evaluation. The paper explicitly requires 100 runs for quality profiling. We evaluate a single deterministic run. This is the single biggest gap between the claimed method and the implementation.

- **MISSING** — Tabu tenure and diversification. Vasquez and Hao's tabu search provides binary/ternary constraint handling and diversification mechanisms that would help escape local optima. We have a lightweight deterministic tabu-like filter in local search but no real tabu mechanism.

- **ADAPTED / MISSING** — Deterministic tie-breaking. The repository requires determinism, which contradicts the paper's stochastic method. This is a necessary adaptation, but it means the solver cannot claim to reproduce the paper's quality profiles.

### What must change to reach the target claim

1. **Add removal moves to local search.** Without removal, the search cannot free up capacity to insert better products. This is a correctness-affecting gap.

2. **Implement multi-run evaluation.** A single deterministic run is not a valid evaluation of a stochastic local-search method. At minimum, run 10 independent seeds with different randomization and report best/average/worst.

3. **Clarify the target claim.** If the solver is intended as a deterministic greedy baseline, that is a valid and useful contribution. But it should not be claimed as a reproduction of Lemaître's local-search method unless the stochastic search components are implemented and evaluated properly.

## Action Plan

- **optimization and parallelization work**
  - Parallelize candidate generation and product library across targets (embarrassingly parallel).
  - Profile the seed loop to identify remaining hot spots after the satellite-state cache.

- **runtime-budget or run-policy changes**
  - Add a `num_runs` config parameter. Run the solver `num_runs` times with different random seeds or tie-breaking and keep the best result.
  - Increase the default local-search budget to 300 seconds per run, but only after removal moves are implemented.
  - Report aggregate statistics (best, mean, std) when `num_runs > 1`.

- **remaining algorithmic completion work**
  - Implement removal moves in local search (remove low-quality products to make room for better ones).
  - Add optional stochastic tie-breaking (with fixed random seeds for reproducibility) to approximate the paper's search behavior.

## Sanity Footnote

- All 5 public cases pass the benchmark verifier with `valid=true` and zero violations.
- Repair removes 0 products on all cases, confirming that solver-local propagation matches verifier geometry at the action level.
- The solver is a valid benchmark baseline, but it is currently a deterministic greedy baseline with a weak local-search veneer, not a faithful reproduction of Lemaître's stochastic local-search method.
