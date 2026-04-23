# Phase 6: Validation, Tuning, and Solver Audit

## Goal

Tune and validate the solver so the team can defend "this is a valid, correct implementation of the claimed method, reasonably configured for the benchmark" rather than merely "this is a faithful paper reproduction."

An unoptimized or slow implementation is not a failure if the algorithmic logic is correct. The audit should flag correctness-affecting deviations and timeout/resource misalignment, not penalize implementation style or performance gaps that do not affect validity.

## Inputs To Read

- `solvers/stereo_imaging/roadmap/time_window_pruned_stereo_milp/ROADMAP.md`
- Phase 5 implementation and debug artifacts
- Issue #89
- `solvers/stereo_imaging/literature/kim-2020-stereo-milp.md`
- `solvers/stereo_imaging/literature/summary.md`
- `benchmarks/stereo_imaging/README.md`
- Official verification outputs from `experiments/main_solver`

## In Scope

- Run a validation matrix across public cases and selected configs:
  - pruning disabled
  - low/mid/high lambda-style pruning
  - optimized backend when available
  - deterministic fallback mode
- Track:
  - validity
  - `coverage_ratio`
  - `normalized_quality`
  - action count
  - valid pair count
  - valid tri count
  - candidate/product counts
  - pruned candidate/product counts
  - runtime
  - backend status
- Compare against a simple greedy earliest-pair baseline if available or add a tiny internal comparison mode.
- Calibrate product prechecks against verifier diagnostics on representative emitted solutions.
- Record where benchmark adaptation intentionally differs from Kim:
  - no downlink/storage constraints
  - benchmark convergence/overlap/pixel-scale validity instead of pitch-difference-only stereo
  - tri-stereo extension
  - coverage-first objective
- **Assess performance baseline and timeout realism:**
  - What runtime does Kim et al. report for comparable instances?
  - What timeout and thread count does the benchmark envelope provide?
  - Is the timeout realistic for a MILP of this structure, or does it make success practically impossible?
  - Document any timeout/resource misalignment; do not flag a correct-but-slow solver as invalid.

## Out Of Scope

- Rewriting the algorithm into an unrelated metaheuristic.
- Adding non-paper features that cannot be explained as benchmark adaptation.
- Long private sweeps that leave no reproducible config.
- Treating performance-only differences (e.g., slower loop, simpler data structure) as correctness deviations.

## Implementation Notes

- Keep tuning knobs in `config.example.yaml` with documented defaults.
- Tuning should preserve validity first, coverage second, and quality third.
- If the backend produces infeasible or unstable results, prefer a conservative fallback and document the limitation.
- Debug summaries should make candidate pruning and model tradeoffs visible enough for future papers or README claims.
- **Correctness vs. performance:** flag only differences that change algorithmic correctness or violate the benchmark contract. Cosmetic or performance-related differences are notes, not deviations.

## Validation

- Run focused tests.
- Run official smoke and all feasible public cases through `experiments/main_solver`.
- Run forced fallback smoke.
- Compare debug product counts against official `diagnostics.pair_evaluations` on at least one case.
- Check deterministic repeatability by running the same case/config twice.
- **Check timeout/resource alignment:** document whether the benchmark envelope is realistic for the claimed method.

## Exit Criteria

- Default config is chosen and justified.
- Validation notes explain correctness, runtime, and drift from paper assumptions.
- Official smoke is valid.
- At least one reproducible validation artifact supports the README's solver-audit claims.
- Known limitations are concrete and ready for final docs.
- **Performance baseline assessment is documented:** REALISTIC, MISALIGNED, or UNKNOWN.

## Suggested Prompt

Read the stereo MILP roadmap, issue #89, Kim transcript, current implementation, and official main-solver outputs. Tune and validate for solver audit: compare pruning levels and fallback mode, calibrate product prechecks against verifier diagnostics, assess timeout/resource realism against literature baselines, record metrics, and prepare concrete notes for the final README.
