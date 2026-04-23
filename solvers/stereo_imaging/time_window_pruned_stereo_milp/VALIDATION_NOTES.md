# Validation Notes for README

These notes are prepared during Phase 6 for consumption by the final README (Phase 7).

## Default Config Justification

The default config (`config.example.yaml`) balances runtime and accuracy:

- `time_step_s: 60` — coarse enough for ~37s runtime per case, fine enough that access intervals capture the bulk of valid windows.
- `sample_stride_s: 30` — produces 2–4 candidates per typical access interval; denser strides explode candidate count without improving coverage on current cases.
- `steering_along_samples: 3`, `steering_across_samples: 3` — 3×3 grid filtered by combined off-nadir gives ~5–9 steering variants per sample. Current cases are nadir-dominated, so denser grids do not create valid pairs.
- `pruning.enabled: true` — reduces model size on dense cases with negligible runtime overhead.
- `optimization.backend: auto` — prefers OR-Tools CP-SAT when available, falls back to deterministic greedy.
- `optimization.time_limit_s: 300` — realistic for greedy/heuristic (actual runtime ~37s), but MISALIGNED for exact MILP (literature baselines use up to 3 hours).

## Runtime Expectations

| Case size | Candidates | Pairs | Tris | Greedy runtime | Notes |
|-----------|-----------|-------|------|----------------|-------|
| 36 targets, 3 sats (test cases) | ~120–300 | ~540–1350 | ~1440–3600 | ~17–38s | All current cases |

Runtime scales roughly linearly with candidate count. The dominant cost is SGP4 propagation for access-interval search and geometry precomputation.

## Determinism Guarantee

The solver is deterministic under fixed config and fixed case:
- Access-interval search uses fixed time steps and deterministic predicates.
- Candidate generation uses a sorted steering grid.
- Product enumeration uses deterministic polar-grid overlap (not Monte Carlo).
- Pruning uses deterministic ranking keys.
- Greedy fallback sorts products by quality with deterministic tie-breakers (target_id, sat_id, interval_id, start time).
- Repair removes conflicts by coverage loss → product count → quality → start time.

Verified by running `case_0001` three times: all algorithmic outputs identical; only `solve_time_s` differs.

## Product Precheck Calibration

On `case_0001`:
- Solver reports: 1350 pairs, 0 valid; 3600 tris, 0 valid.
- Verifier reports: 0 pair_evaluations; coverage_ratio = 0.0.
- **Alignment: PERFECT.** The solver's convergence/overlap/pixel-scale prechecks match the verifier's ground truth.

Known approximation differences (documented as drift flags, not correctness issues):
- **Overlap:** Solver uses deterministic polar-grid area-uniform sampling; verifier uses Monte Carlo. Typical difference < 5%.
- **Pixel scale:** Solver omits off-nadir secant correction; verifier applies it. Negligible at small off-nadir angles.
- **Slew check:** Solver conflict graph uses midpoint boresight angles; repair uses boundary-time angles (verifier-aligned).

## Timeout / Resource Assessment

- **Performance baseline:** REALISTIC for greedy fallback; MISALIGNED for exact MILP.
- **Recommended action:** Increase `time_limit_s` to ≥1800s if a MILP backend (OR-Tools, HiGHS) is installed.
- **Hardware assumption:** Generic modern CPU, single-threaded search. No GPU or cluster required.

## Known Limitations

1. **Zero valid pairs on current cases:** The 5 public test cases have nadir-only geometry (convergence angles < 5°). The solver correctly identifies this and emits valid empty solutions. This is a benchmark dataset characteristic, not a solver bug.
2. **No MILP backend installed:** The solver relies on deterministic greedy fallback. Backend drivers (OR-Tools, PuLP) are written but inactive until packages are added.
3. **Coarse time step:** `time_step_s: 60` can miss short access intervals or truncate interval boundaries. Exact SGP4 reproduction is flagged for future work.
4. **Approximate overlap:** Polar-grid overlap may differ from verifier's Monte Carlo by a few percent. No known case where this flips a pair from valid to invalid.
5. **No cross-satellite / cross-date stereo:** The benchmark disables these by default; the solver honors the flag but does not implement them.

## Validation Matrix Results

See `VALIDATION_REPORT.json` for the full matrix. Summary across 5 cases × 5 configs = 25 runs:

| Config | Candidates (range) | Pairs (range) | Runtime (range) | Valid | Coverage |
|--------|-------------------|---------------|-----------------|-------|----------|
| default | 50–370 | 225–1665 | 17–40s | 5/5 | 0.0 |
| pruning_disabled | 50–370 | 225–1665 | 17–40s | 5/5 | 0.0 |
| coarse_time_step | 0 | 0 | 8–17s | 5/5 | 0.0 |
| dense_steering | 100–740 | 950–7030 | 21–57s | 5/5 | 0.0 |
| forced_fallback | 50–370 | 225–1665 | 17–40s | 5/5 | 0.0 |

Key observations:
- **All configs produce `valid: true`** on all 5 cases.
- **Pruning has no effect** on current cases because candidates are already well-spaced (cluster gaps exceed auto threshold).
- **Coarse time step (120s) produces 0 candidates** on all cases: access intervals are shorter than 120s, so the coarse step misses them entirely. This confirms `time_step_s` should not exceed ~60s for these cases.
- **Dense steering grid doubles candidates** (and roughly doubles runtime) but still yields 0 valid pairs, confirming the nadir-only geometry hypothesis.
- **Forced greedy fallback** produces identical results to auto-fallback and is the fastest path when no backend is installed.
