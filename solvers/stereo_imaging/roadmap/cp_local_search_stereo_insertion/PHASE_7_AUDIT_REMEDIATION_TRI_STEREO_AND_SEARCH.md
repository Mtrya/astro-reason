# Phase 7: Audit Remediation — Tri-Stereo Scheduling And Search Improvements

## Goal

Address the blockers flagged in the Phase 6 solver audit so the solver can credibly claim to be a faithful reproduction of the Lemaître local-search method family, not merely a deterministic greedy baseline.

Audit headline blockers to fix:
1. **Zero tri-stereo products scheduled** on all public cases despite thousands of feasible candidates.
2. **Local search accepts 0 improving moves** because the move neighborhood lacks dedicated removal moves.
3. **Single deterministic run** contradicts the paper's stochastic profiling regime.
4. **Greedy seed is an implementation invention** (pool-based coverage-first) rather than the paper's sequential track-builder.

The solver contract allows per-solver environment management. "venv does not have this" is not an excuse.

## Inputs To Read

- `SOLVER_AUDIT.md` (Phase 6 audit report)
- `solvers/stereo_imaging/literature/lemaitre-2002-cp-local-search.md` (§3.1 GA, §3.4 LSA)
- `solvers/stereo_imaging/literature/vasquez-2001-logic-knapsack-tabu.md` (removal ideas, tabu tenure)
- Current `src/seed.py`, `src/local_search.py`, `src/sequence.py`
- Benchmark verifier diagnostics on tri-stereo evaluation

## In Scope

### 7.1 Fix tri-stereo scheduling

The root cause is that the seed ranking does not prioritize tri-stereo products strongly enough to overcome the difficulty of inserting three observations into a sequence. A tri-stereo product must satisfy:
- Same satellite, target, access interval
- Near-nadir anchor (one observation with low off-nadir)
- Convergence angle within scene-specific band
- Monte-Carlo overlap fraction ≥ threshold

**Implementation:**
- Add a dedicated **tri-stereo-first seed phase**: before the coverage-first greedy loop, attempt to insert the highest-quality feasible tri-stereo product for every target that has one. This is a one-pass greedy insertion with atomic rollback.
- After the tri-stereo phase, fall back to the existing pair-stereo coverage-first greedy seed for uncovered targets.
- Add config knob `tri_stereo_seed_phase: bool = true`.
- If a target already has a tri-stereo product scheduled, skip pair products for that target (they would be redundant).

**Validation:** verifier `diagnostics.tri_evaluations` should be > 0 on at least one public case after this change. Coverage ratio should not decrease; normalized quality should increase due to tri-stereo bonus.

### 7.2 Add removal moves to local search

The current move set is insert, replace, and swap (remove-then-repair). The paper's LSA has both insertion and removal as first-class moves. Without removal, the search cannot free up sequence capacity to insert better products.

**Implementation:**
- Add a `remove` move type to `src/local_search.py`:
  1. Select the lowest-quality scheduled product (deterministic tie-break by product_id).
  2. Remove it from the sequence.
  3. Try to insert better products for uncovered or covered targets into the freed capacity.
  4. Accept only if objective strictly improves.
- Reorder the move priority per pass:
  1. INSERT uncovered targets (coverage increase).
  2. REPLACE covered targets with higher quality (quality increase).
  3. REMOVE low-quality blocking products + INSERT better alternatives.
  4. SWAP (remove-then-repair) as fallback.
- The remove move uses the same clone-based trial evaluation and atomic rollback as existing moves.

**Validation:** local search should accept > 0 moves on at least one public case. Seed-only metrics should be strictly worse than full-pipeline metrics on at least one case.

### 7.3 Add multi-run evaluation harness

The paper evaluates LSA with 100 runs of 2 minutes each. The repository requires determinism, but a reproducible multi-run harness with fixed random seeds satisfies both constraints.

**Implementation:**
- Add `num_runs: int = 1` and `random_seed: int = 42` to config.
- When `num_runs > 1`, run the full pipeline (seed + local search) `num_runs` times. In each run:
  - Perturb the greedy seed tie-breaking with a deterministic pseudo-random offset derived from `random_seed + run_index`.
  - Use the same perturbation for local-search move ordering (e.g., shuffle the order in which targets are tried for insert/replace/remove).
- Keep the best solution across all runs (by lexicographic `(coverage, quality)`).
- Write `status.json` with aggregate statistics: `best_run`, `best_coverage`, `best_quality`, `mean_coverage`, `mean_quality`, `num_runs`.
- The perturbation must be small enough to preserve reproducibility: only shuffle move ordering, never change geometric feasibility.

**Validation:** `num_runs=3` on case_0004 should produce a best result ≥ the single-run result. Running twice with the same `random_seed` must produce identical aggregate statistics.

### 7.4 Parallelize candidate generation

Candidate generation is embarrassingly parallel: each (satellite, target) pair can be processed independently. On large cases it takes ~10–35 seconds single-threaded.

**Implementation:**
- Use `concurrent.futures.ProcessPoolExecutor` (or `ThreadPoolExecutor` if skyfield is thread-safe) to parallelize `generate_candidates` across target-satellite pairs.
- The number of workers should default to `min(4, os.cpu_count())` to avoid overwhelming the system.
- Add config knob `max_workers: int | null = null` (null means auto).
- Preserve deterministic output by sorting results by target_id and satellite_id after parallel collection.

**Validation:** parallel run must produce byte-identical `solution.json` to single-threaded run. Timing should show candidate_generation reduced by roughly the worker count.

### 7.5 Calibrate seed ranking

The current pool-based greedy seed is not the paper's GA. While replacing it entirely is out of scope for this phase, we can calibrate it to better approximate coverage-first behavior.

**Implementation:**
- Add `pair_weight: float = 1.0` and `tri_weight: float = 1.5` config knobs.
- Replace the ad-hoc `coverage_bonus + scarcity + tri_bonus + quality` ranking with a clearer weighted sum:
  - Primary: `coverage_value` (1.0 for uncovered, 0.0 for covered)
  - Secondary: `product_weighted_quality = quality * (tri_weight if tri else pair_weight)`
  - Tertiary: `scarcity`
  - Tie-break: `product_id`
- This makes the ranking transparent and tunable without hidden composite bonuses.

**Validation:** metrics on all 5 cases should not regress. The ranking must still be deterministic.

## Out Of Scope

- Replacing the greedy seed with the paper's sequential track-builder (would be Phase 8 or a new solver).
- Adding full tabu search with dynamic tenure (Vasquez-style). The lightweight tabu filter in local search is sufficient for now.
- GPU or compiled extensions.
- Hidden non-reproducible tuning.

## Implementation Notes

- Solver contract allows per-solver environment. If `concurrent.futures` or `multiprocessing` needs additional packages, add them to `setup.sh` or document them.
- All changes must preserve the no-import rule: no `benchmarks.*`, `experiments.*`, or other solver imports.
- Debug artifacts should include `tri_stereo_seed_accepted.json` and `multi_run_summary.json` when applicable.
- The tri-stereo seed phase must use the same atomic insertion/rollback as pair products.

## Validation

- Run focused solver tests (phases 2–5) and confirm no regressions.
- Run full pipeline on all 5 public cases with new config defaults.
- Verify `tri_evaluations > 0` on at least one case.
- Verify `local_search_accepted > 0` on at least one case.
- Run `num_runs=3` on case_0004 and verify best ≥ single-run.
- Run parallel candidate generation and verify byte-identical output.
- Re-run official main-solver smoke on all 5 cases.
- Update `SOLVER_AUDIT.md` with remediation evidence and revise status if blockers are resolved.

## Exit Criteria

- Tri-stereo products are scheduled on at least one public case (verifier `tri_evaluations > 0`).
- Local search accepts > 0 improving moves on at least one public case.
- Multi-run harness produces reproducible aggregate statistics.
- Parallel candidate generation produces identical output faster.
- All public cases remain `valid=true`.
- Audit report is updated to reflect remediation.
- Coverage ratio does not regress on any case; aim for improvement on case_0004 (currently 0.795) and case_0001 (currently 0.638).
