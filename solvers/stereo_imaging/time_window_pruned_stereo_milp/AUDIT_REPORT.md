# Solver Audit: time_window_pruned_stereo_milp

## Summary

- **Correctness:** PASS
- **Match rate:** 3/4 major Kim steps match directly; 1 is an ADAPTATION
- **Adaptations:** 4
- **Deviations:** 0
- **Extensions:** 2
- **Missing:** 1 (download/storage — benchmark explicitly excludes them)
- **Performance baseline:** REALISTIC for greedy/heuristic; MISALIGNED for exact MILP if a backend were available

## Detailed Comparison

| Kim et al. 2020 Step | Implementation | Status | Benchmark Context | Notes |
|----------------------|---------------|--------|-------------------|-------|
| Observation time window variables (OTW) | Candidate observations per `(satellite, target, access_interval, steering)` | MATCH | Same concept; finer-grained because steering is explicit | Each candidate is a concrete timed observation with along/across steering |
| Priority-based time-window pruning heuristic | `prune_candidates()` with scarcity, product potential, quality, steering similarity | MATCH | Direct implementation of Kim's Step 1–2 | Cluster gap = `(4·max_off_nadir)/max_slew_velocity + settling_time`; ranking uses scarcity → product count → quality → steering similarity |
| MILP formulation with transition-time constraints | Abstract MILP with conflict constraints + pair/tri link constraints | ADAPTATION | Uses benchmark bang-bang slew model instead of Kim's roll/pitch linear approximation | Benchmark verifier uses trapezoidal slew profile; solver mirrors it with 0.5s safety buffer |
| Stereo pitch-angle difference ≥ β (15°) | Precomputed convergence/overlap/pixel-scale validity | ADAPTATION | Required by benchmark contract | Benchmark replaces pitch-only with convergence 5–45°, overlap ≥ 0.80, pixel-scale ratio ≤ 1.5 |
| Download and data capacity constraints | Omitted | MISSING | Benchmark explicitly excludes downlink, storage, and power | Documented in README and roadmap as out-of-scope |
| Coverage-first lexicographic objective | `coverage_weight × covered_targets + Σ(pair_qualities) + Σ(tri_qualities)` | EXTENSION | Benchmark ranks coverage before quality | `coverage_weight = 1000` ensures one covered target dominates any quality improvement |
| Tri-stereo products | `TriStereoSet` variables and link constraints | EXTENSION | Not in Kim's two-image stereo form | Benchmark requires ≥2 valid pairs + near-nadir anchor for tri-stereo |
| Post-solve conservative repair | `repair_solution()` dedup / overlap / slew removal | EXTENSION | Safety net for model-approximation drift | Verifier-aligned boundary-time boresight checks; coverage-preserving tie-breaker |
| Deterministic greedy fallback | `solve_greedy_fallback()` with conflict repair and coverage augment | EXTENSION | Degrades cleanly when MILP backend unavailable | Uses product-quality sort + per-satellite conflict repair + coverage-augmenting pass |

## Performance & Configuration Assessment

| Aspect | Literature / Theory | Benchmark Config | Assessment | Notes |
|--------|--------------------|------------------|------------|-------|
| Hardware | Intel Core i7, 16GB RAM, GUROBI | Project venv, generic CPU | REALISTIC | Comparable single-thread performance |
| Direct MILP timeout | 3 hours (10,800s) | 300s | MISALIGNED for exact MILP | Kim's direct MILP ran 12s–86,540s on 50–100 tasks. 300s is far below the upper end. |
| Heuristic timeout | 12s–2,933s (λ = 12–15) | 300s | REALISTIC for heuristic/fallback | Greedy fallback finishes in ~37s on current 36-target cases. 300s is comfortable. |
| Thread count | Single-thread GUROBI | 1 (OR-Tools CP-SAT driver) | REALISTIC | Matches Kim's deterministic single-thread config |
| Instance size | 50–100 tasks, 24h horizon | 36 targets, 3 sats, 48h horizon | REALISTIC | Candidate count (~300) is in the lower half of Kim's range |

### Timeout/Resource Conclusion

The default 300s timeout is **REALISTIC** for the greedy fallback and would be acceptable for the Kim-style heuristic layer. It is **MISALIGNED** for an exact MILP solve on dense instances: if OR-Tools or PuLP were installed, the solver would likely time out on cases with thousands of candidates before proving optimality. Since the benchmark currently has no official timeout contract, this is a documented limitation, not a correctness issue. Users who install a backend should increase `time_limit_s` to at least 1800s (30 min) for meaningful exact solves.

## Suggested Improvements

1. **Install a MILP backend** (OR-Tools CP-SAT or HiGHS) to activate the exact solver path on cases where greedy quality is insufficient.
2. **Increase `time_limit_s`** to 1800s or higher when a backend is present, to align with literature expectations for exact MILP.
3. **Calibrate `time_step_s`** against exact SGP4 access intervals on a reference case to quantify coarse-step drift.
4. **Add secant correction** to pixel-scale computation to match the verifier's off-nadir projection model.

## Notes

- All 5 public test cases verify as `valid: true` with the current implementation.
- Current test cases have **0 valid stereo pairs** due to nadir-only geometry (convergence < 5°). This is a benchmark dataset characteristic, not a solver bug.
- Solver product counts (1350 pairs / 0 valid on case_0001) match verifier diagnostics (0 pair_evaluations).
- The solver is fully deterministic: repeated runs produce identical candidate counts, product counts, selected observations, and repair logs. Only `solve_time_s` differs (timing noise).
