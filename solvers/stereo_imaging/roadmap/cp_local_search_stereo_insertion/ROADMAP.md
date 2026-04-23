# CP/Local-Search Stereo Insertion Solver Roadmap

## Goal

Implement a runnable reproduced solver for `stereo_imaging` using Lemaitre-style constraint-propagated local search over same-pass stereo and tri-stereo products.

The solver should be the fast reproducible baseline: enumerate benchmark-valid product candidates, build a deterministic coverage-first seed, maintain per-satellite sequences with earliest/latest propagation, and improve schedules by inserting, removing, and replacing whole products while documenting algorithmic validity, benchmark contract compliance, and reasonable timeout/resource expectations.

## Source Of Truth

- Issue: `https://github.com/Mtrya/astro-reason/issues/90`
- Benchmark contract: `benchmarks/stereo_imaging/README.md`
- Solver contract: `docs/solver_contract.md`
- Main solver experiment: `experiments/main_solver/README.md`
- Literature summary: `solvers/stereo_imaging/literature/summary.md`
- Selection table: `solvers/stereo_imaging/literature/table.md`
- Lemaitre transcript: `solvers/stereo_imaging/literature/lemaitre-2002-cp-local-search.md`
- Vasquez support reference: `solvers/stereo_imaging/literature/vasquez-2001-logic-knapsack-tabu.md`
- Research report: `solvers/stereo_imaging/literature/report.md`
- Verifier tests: `tests/benchmarks/test_stereo_imaging_verifier.py`
- Fixture notes: `tests/fixtures/stereo_imaging/README.md`
- Solver docs style reference: `solvers/aeossp_standard/mwis_conflict_graph/README.md`

## Current State

`stereo_imaging` has public cases, a verifier, generator, fixtures, visualizer, and no runnable solver. Issue #90 (`gh issue view 90 --repo Mtrya/astro-reason`) asks for a standalone reproduced solver that treats stereo and tri-stereo products as coupled scheduling moves, keeps fixed seeds and deterministic tie-breaking, and uses CP-style earliest/latest feasibility propagation plus local insertion/removal moves.

## Contract And Boundaries

- Solver path: `solvers/stereo_imaging/cp_local_search_stereo_insertion/`.
- Required entrypoints: `setup.sh` and `solve.sh <case_dir> [config_dir] [solution_dir]`.
- Public inputs:
  - `satellites.yaml`
  - `targets.yaml`
  - `mission.yaml`
- Primary output: `solution.json` with a top-level `actions` array containing only `observation` actions.
- Solver code may use project dependencies and optional OR-Tools for small repair subproblems, but the default path should be Python-only and deterministic.
- Solver code must not import `benchmarks.*`, `experiments.*`, or another solver. It must not call benchmark verifiers from solver code.
- Official verification belongs to `experiments/main_solver` or explicit developer-side validation commands.

## Paper-To-Benchmark Adaptation

- Lemaitre candidate image = benchmark candidate observation action.
- Lemaitre stereoscopic coupling `x_i = x_j` = product-level insertion/removal of all observations required by a pair or tri-stereo set.
- Lemaitre image sequence = per-satellite action sequence.
- Lemaitre earliest/latest propagation = feasible timing interval propagation around fixed candidate windows and benchmark slew/settle gaps.
- Lemaitre local insertion/removal = insert, remove, or replace whole products, with rollback if any partner observation or tri-stereo anchor cannot be placed.
- Vasquez binary/ternary logic ideas may be used for repair bookkeeping, but not as a separate solver identity.
- Benchmark scoring replaces request weight with coverage-first and normalized-quality objectives.

## Phase Order

1. `PHASE_1_CONTRACT_CANDIDATES_AND_PRODUCT_LIBRARY.md`
2. `PHASE_2_SEQUENCE_PROPAGATION_AND_FEASIBILITY.md`
3. `PHASE_3_DETERMINISTIC_GREEDY_SEED.md`
4. `PHASE_4_LOCAL_SEARCH_PRODUCT_MOVES.md`
5. `PHASE_5_REPAIR_EXPERIMENT_WIRING_AND_TESTS.md`
6. `PHASE_6_VALIDATION_TUNING_AND_SOLVER_AUDIT.md`
7. `PHASE_7_AUDIT_REMEDIATION_TRI_STEREO_AND_SEARCH.md`
8. `PHASE_8_DOCS_CLEANUP_AND_PROMOTION.md`

## Cross-Phase Risks

- Product-level moves can hide action-level conflicts unless sequence propagation is exact enough.
- A stochastic local search would be hard to reproduce without fixed seeds and stable tie-breakers.
- Tri-stereo insertion can score well only if near-nadir anchors are preserved.
- Greedy coverage can block higher-quality products unless replacement moves are strong.
- Solver-local product predicates may drift from verifier geometry and Monte Carlo overlap estimates.

## Overall Exit Criteria

- Direct `setup.sh` and `solve.sh` work on the smoke case.
- `experiments/main_solver` can run the solver with `evidence_type: reproduced_solver`.
- Official verification passes at least the smoke case and preferably all public cases.
- Focused tests cover product enumeration, sequence propagation, insertion rollback, removal/replacement moves, deterministic repeatability, repair, and output schema.
- Debug artifacts explain product candidates, seed choices, propagation failures, accepted/rejected moves, repair removals, official metrics, and runtime.
- Final README covers method summary, benchmark adaptation, solver contract, product insertion search, optional Vasquez-inspired repair, validation/tuning, known limitations, and BibTeX for Lemaitre and Vasquez.
