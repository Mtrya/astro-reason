# Phase 6: Validation, Tuning, and Solver Audit

## Goal

Tune and validate the solver so the team can defend "this is a valid, correct implementation of the claimed method, reasonably configured for the benchmark" rather than merely "this is a faithful paper reproduction."

An unoptimized or slow implementation is not a failure if the algorithmic logic is correct. The audit should flag correctness-affecting deviations and timeout/resource misalignment, not penalize implementation style or performance gaps that do not affect validity.

## Inputs To Read

- `solvers/stereo_imaging/roadmap/cp_local_search_stereo_insertion/ROADMAP.md`
- Phase 5 implementation and debug artifacts
- Issue #90
- `solvers/stereo_imaging/literature/lemaitre-2002-cp-local-search.md`
- `solvers/stereo_imaging/literature/vasquez-2001-logic-knapsack-tabu.md`
- `solvers/stereo_imaging/literature/summary.md`
- Official verification outputs from `experiments/main_solver`

## In Scope

- Run a validation matrix across public cases and selected configs:
  - seed-only
  - deterministic local search
  - seeded stochastic mode if implemented
  - tabu diversification disabled/enabled if implemented
  - pair-first and tri-aware policies
- Track:
  - validity
  - `coverage_ratio`
  - `normalized_quality`
  - action count
  - valid pair count
  - valid tri count
  - candidate/product counts
  - accepted/rejected move counts
  - repair removals
  - runtime
- Compare against earliest-pair greedy and the MILP baseline once available.
- Calibrate solver-local product predicates against verifier diagnostics.
- Record where benchmark adaptation intentionally differs from Lemaitre:
  - point AOI products instead of strips
  - tri-stereo extension
  - benchmark convergence/overlap/pixel-scale quality
  - no memory, energy, weather, or downlink constraints
  - deterministic defaults instead of unbounded stochastic profiling
- **Assess performance baseline and timeout realism:**
  - What runtime does Lemaitre et al. report for comparable instances?
  - What timeout and thread count does the benchmark envelope provide?
  - Is the timeout realistic for CP-style local search with product insertion moves?
  - Document any timeout/resource misalignment; do not flag a correct-but-slow solver as invalid.

## Out Of Scope

- Replacing local search with a full exact solver.
- Hidden non-reproducible tuning.
- Adding benchmark-only hacks that cannot be traced to paper or contract.
- Treating performance-only differences (e.g., slower loop, simpler data structure) as correctness deviations.

## Implementation Notes

- Keep default knobs conservative and reproducible.
- Preserve the paper's product-coupled insertion/rollback behavior in debug evidence.
- Use validation notes to justify any optional Vasquez-inspired tabu or repair behavior as support, not the core method identity.
- **Correctness vs. performance:** flag only differences that change algorithmic correctness or violate the benchmark contract. Cosmetic or performance-related differences are notes, not deviations.
- Repeatability is part of correctness for this repository, even though Lemaitre's original LSA discusses stochastic profiles.

## Validation

- Run focused tests.
- Run official smoke and all feasible public cases through `experiments/main_solver`.
- Run deterministic repeatability checks.
- Compare seed-only versus local-search outputs.
- Compare solver product estimates against official `diagnostics.pair_evaluations` on at least one case.
- **Check timeout/resource alignment:** document whether the benchmark envelope is realistic for the claimed method.

## Exit Criteria

- Default config is chosen and justified.
- Validation notes explain correctness, runtime, determinism, and drift from paper assumptions.
- Official smoke is valid.
- At least one reproducible validation artifact supports the README's solver-audit claims.
- Known limitations are concrete and ready for final docs.
- **Performance baseline assessment is documented:** REALISTIC, MISALIGNED, or UNKNOWN.

## Suggested Prompt

Read the CP/local-search roadmap, issue #90, Lemaitre transcript, current implementation, and official main-solver outputs. Tune and validate for solver audit: compare seed-only and local-search modes, check deterministic replay, calibrate product predicates against verifier diagnostics, assess timeout/resource realism against literature baselines, record metrics, and prepare final README notes.
