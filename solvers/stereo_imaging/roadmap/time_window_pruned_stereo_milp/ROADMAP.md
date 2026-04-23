# Time-Window-Pruned Stereo MILP Solver Roadmap

## Goal

Implement a runnable reproduced solver for `stereo_imaging` using Kim-style agile-satellite MILP scheduling with time-window pruning, adapted to benchmark-native stereo and tri-stereo product variables.

The solver should be the higher-quality optimization baseline: enumerate benchmark-feasible observation candidates, precompute valid stereo and tri-stereo products, solve a reduced MILP or CP-SAT model that prioritizes target coverage before product quality, and document the algorithmic validity of the adaptation: correctness of the MILP structure, benchmark contract compliance, and reasonable timeout/resource expectations.

## Source Of Truth

- Issue: `https://github.com/Mtrya/astro-reason/issues/89`
- Benchmark contract: `benchmarks/stereo_imaging/README.md`
- Solver contract: `docs/solver_contract.md`
- Main solver experiment: `experiments/main_solver/README.md`
- Literature summary: `solvers/stereo_imaging/literature/summary.md`
- Selection table: `solvers/stereo_imaging/literature/table.md`
- Kim transcript: `solvers/stereo_imaging/literature/kim-2020-stereo-milp.md`
- Research report: `solvers/stereo_imaging/literature/report.md`
- Verifier tests: `tests/benchmarks/test_stereo_imaging_verifier.py`
- Fixture notes: `tests/fixtures/stereo_imaging/README.md`
- Solver docs style reference: `solvers/aeossp_standard/mwis_conflict_graph/README.md`

## Current State

`stereo_imaging` has public cases, a verifier, generator, fixtures, visualizer, and no runnable solver. The benchmark requires same-satellite, same-target, same-access stereo products and ranks valid solutions by `coverage_ratio` before `normalized_quality`. Issue #89 asks for a standalone reproduced solver that uses Kim et al.'s MILP structure and pruning idea while replacing the paper's pitch-difference stereo condition with verifier-aligned product feasibility.

## Contract And Boundaries

- Solver path: `solvers/stereo_imaging/time_window_pruned_stereo_milp/`.
- Required entrypoints: `setup.sh` and `solve.sh <case_dir> [config_dir] [solution_dir]`.
- Public inputs:
  - `satellites.yaml`
  - `targets.yaml`
  - `mission.yaml`
- Primary output: `solution.json` with a top-level `actions` array containing only `observation` actions.
- Each observation action must include `satellite_id`, `target_id`, `start_time`, `end_time`, `off_nadir_along_deg`, and `off_nadir_across_deg`.
- Solver code may use project dependencies and an optional optimization backend, but must degrade cleanly to a documented fallback if the preferred backend is unavailable.
- Solver code must not import `benchmarks.*`, `experiments.*`, or another solver. It must not call benchmark verifiers from solver code.
- Official verification belongs to `experiments/main_solver` or explicit developer-side validation commands.

## Paper-To-Benchmark Adaptation

- Kim observation task/window variables = candidate observation windows per `(satellite_id, target_id, access_interval_id, sample_time, steering)`.
- Kim stereo selection variables = benchmark product variables for valid pairs and tri-stereo sets.
- Kim pitch-angle separation constraint = precomputed convergence, overlap, pixel-scale, same-access, and near-nadir-anchor predicates.
- Kim transition-time constraints = benchmark-style per-satellite overlap and slew/settle separation between selected actions.
- Kim priority objective = lexicographic benchmark objective: maximize covered targets, then normalized product quality, then deterministic tie-breakers.
- Kim download and onboard data capacity constraints are omitted because the benchmark explicitly excludes downlink, storage, and power.
- Kim time-window pruning = cluster dense access windows and retain candidates by target scarcity, product potential, quality, and steering similarity.

## Phase Order

1. `PHASE_1_CONTRACT_CANDIDATE_LIBRARY_AND_PRECHECKS.md`
2. `PHASE_2_PRODUCT_ENUMERATION_AND_SCORING.md`
3. `PHASE_3_TIME_WINDOW_CLUSTER_PRUNING.md`
4. `PHASE_4_MILP_MODEL_AND_BACKEND_FALLBACK.md`
5. `PHASE_5_DECODE_REPAIR_EXPERIMENT_WIRING_AND_TESTS.md`
6. `PHASE_6_VALIDATION_TUNING_AND_SOLVER_AUDIT.md`
7. `PHASE_7_DOCS_CLEANUP_AND_PROMOTION.md`

## Cross-Phase Risks

- Candidate enumeration can explode if sample spacing is too fine or steering variants are too dense.
- Simplified product prechecks may admit pairs/triples that fail official overlap, convergence, or pixel-scale checks.
- A linear objective can accidentally optimize quality before coverage unless the lexicographic scale is explicit.
- Pair and tri-stereo products create linking constraints that can make the MILP much larger than the paper's two-image stereo form.
- Optional solver backends can change results unless fallback behavior and tie-breaking are deterministic.

## Overall Exit Criteria

- Direct `setup.sh` and `solve.sh` work on the smoke case.
- `experiments/main_solver` can run the solver with `evidence_type: reproduced_solver`.
- Official verification passes at least the smoke case and preferably all public cases.
- Focused tests cover case parsing, candidate generation, product predicates, pruning, MILP decoding, deterministic fallback, and output schema.
- Debug artifacts explain candidate counts, pruned windows, product counts, model size, backend status, selected products, repair removals, official metrics, and runtime.
- Final README covers method summary, benchmark adaptation, solver contract, candidate/product generation, pruning, backend/fallback behavior, validation/tuning, known limitations, and BibTeX for Kim et al.
