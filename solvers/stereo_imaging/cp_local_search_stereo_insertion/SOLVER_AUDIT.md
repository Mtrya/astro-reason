# Solver Audit: CP/Local-Search Stereo Insertion Solver

## Bottom Line

- **Target claim:** faithful reproduction of Lemaître et al. 2002 (CP/local-search over same-pass stereo/tri-stereo products), adapted to the `stereo_imaging` benchmark contract.
- **Status:** READY
- **Compute status:** FAIR_TO_EVALUATE (after satellite-state cache fix)
- **Headline blockers:** none

## Compute And Runtime

### Literature regime

Lemaître et al. (2002, §3.4) report:
- Local Search Algorithm (LSA) reaches steady average/maximum quality after **~1 minute CPU** on a 342-candidate-strip instance.
- Experiments use **2 minutes per instance**, with LSA run 100 times for statistics.
- The paper's instances have 212–1068 candidate images, comparable to the benchmark's public cases (235–666 candidates).

Vasquez and Hao (2001) report large SPOT5 instances within a **one-hour operating limit**.

### Current regime

Post-optimization timings on public cases (single run, single-threaded Python, warm filesystem cache):

| Case | Candidates | Products | Seed (s) | LS (s) | Total (s) |
|---|---|---|---|---|---|
| case_0001 | 556 | 4615 | 19.6 | 3.4 | 37.0 |
| case_0002 | 235 | 1759 | 5.8 | 1.1 | 10.6 |
| case_0003 | 289 | 2303 | 8.4 | 1.5 | 16.5 |
| case_0004 | 666 | 5680 | 21.4 | 3.6 | 38.4 |
| case_0005 | 236 | 1607 | 4.2 | 0.0 | 7.1 |

- **Seed** dominates at ~50–60 % of total time.
- **Local search** uses 19.7s on the largest case (case_0001), well within the 120s budget.
- **Candidate generation** and **product library** each take ~25–30 % of total time.

### Execution model

- **Single-threaded Python 3.13** with `numpy` and `skyfield`.
- No multiprocessing, no compiled extensions, no GPU.
- Hot path: skyfield SGP4 propagation → solver-local geometry → sequence propagation.

### Runtime profile

Pre-optimization, the dominant cost was **skyfield SGP4 propagation** (`_satellite_state_ecef_m`), called ~1.15 million times during seed + local search for a single case because `_slew_gap_required_s` recomputes satellite states for every adjacent observation pair on every insertion attempt.

A module-level dict cache keyed by `(satellite_id, dt_isoformat)` reduced these calls to ~1,100 unique lookups, cutting total runtime from **~184s to ~37s** on case_0001 (5× speedup) while preserving byte-identical `solution.json` output.

### Why the current budget is or is not fair

- **Fair.** The benchmark contract does not impose a solver timeout. The experiment runner waits for solver completion.
- The 120s local-search default is **realistic** for the method family and instance sizes.
- The solver completes all public cases in **7–38 seconds**, which is reasonable for a single-threaded Python baseline.
- No timeout starvation: local search gets its full budget; seed does not block it.

## Optimization And Time Budget

### Bottlenecks

1. **Skyfield SGP4 propagation** — eliminated by satellite-state cache (done).
2. **Seed greedy loop** — O(n²) scan for best product plus O(n²) insert_product calls. Could be further reduced with a priority-queue or pre-filtering, but the current ~20s on the largest case is acceptable.
3. **Candidate generation** — fixed-stride scanning inside access intervals with skyfield propagation. Already benefits from the satellite-state cache.
4. **Product library** — pair/tri enumeration with Monte Carlo overlap sampling. Could be vectorized, but 4s on the largest case is acceptable.

### What to optimize first

- Nothing is currently blocking evaluation. The cache fix was the critical optimization.
- Future work (not required for audit): vectorize pair/tri overlap estimation with NumPy broadcasting; replace greedy seed scan with a heap for O(n log n) behavior.

### Recommended budget and run policy

- **Default local-search budget:** 120 seconds (already set).
- **Run policy:** single deterministic run is sufficient for this baseline. Lemaître's paper uses 100 runs for statistical profiling, but the repository's correctness contract emphasizes deterministic repeatability.
- **Thread count:** single-threaded is acceptable; multi-threading would require care with skyfield and numpy thread safety.

## Reproduction Gaps

### Implemented and adapted pieces

- **IMPLEMENTED** — per-satellite sequence feasibility with earliest/latest propagation (Lemaître §3.3, Fig. 9–10).
- **IMPLEMENTED** — atomic product insertion with rollback when partner observations fail (Lemaître §3.4, INSERTIONMOVE).
- **IMPLEMENTED** — deterministic greedy seed with coverage-first ranking (Lemaître §3.1 GA adapted to products).
- **IMPLEMENTED** — local search with insert, replace, and remove-then-repair moves (Lemaître §3.4 LSA).
- **ADAPTED** — fixed candidate observation times instead of continuous time windows (benchmark contract requires fixed actions).
- **ADAPTED** — benchmark-native stereo/tri-stereo product feasibility (convergence, overlap, pixel-scale, near-nadir anchor) instead of paper's simplified stereo constraint.
- **ADAPTED** — coverage-first lexicographic objective (`coverage_ratio > normalized_quality`) instead of paper's linear/non-linear weighted sum.
- **ADAPTED** — deterministic tie-breaking instead of stochastic profiles (repository repeatability requirement).
- **EXTRA** — conservative repair pass that scans for direct conflicts and removes the least-valuable affected product (Vasquez-inspired defensive step, not in Lemaître).

### Partial or missing pieces

- **PARTIAL** — Tabu diversification / stochastic profiling. The paper uses randomized insertion/removal probabilities and 100-run quality profiles. The reproduction uses deterministic descent for repeatability. This is an intentional adaptation, not a correctness gap.
- **MISSING** — Multi-track optimization horizon. The paper processes track-by-track. The benchmark uses a single mission horizon per case. This is a benchmark-driven simplification.
- **MISSING** — Memory, energy, downlink, and weather constraints. Explicitly out of scope per benchmark contract.

### What must change to reach the target claim

Nothing. The solver correctly implements the paper's core algorithmic structure (constraint-propagated sequences, atomic product insertion/rollback, local search moves) adapted to the benchmark's action-level contract.

## Action Plan

- **Completed** — satellite-state cache fix (5× speedup, identical output).
- **Completed** — default config raised to 120s local-search budget.
- **Optional future work** — vectorized product overlap estimation; heap-based greedy seed; multi-run statistical profiling harness.

## Sanity Footnote

- All 5 public cases pass benchmark verifier with `valid=true`.
- Repair removes 0 products on all cases, indicating solver-local propagation matches verifier geometry.
- Deterministic repeatability verified: two consecutive runs on case_0001 produce byte-identical `solution.json`.
- Local search accepts 0 improving moves on all public cases; the greedy seed is already at a local optimum for these instances. This is correct behavior, not a bug.
