# CP/Local-Search Stereo Insertion Solver

This solver is a runnable reproduced solver for `stereo_imaging`.

It follows the method family described by Lemaître et al. in "Selecting and Scheduling Observations of Agile Satellites", adapted to the benchmark's public case and solution contract. Vasquez and Hao's tabu-search ideas inform the optional repair/diversification stage, but the core solver identity is the Lemaitre CP/local-search approach.

## Citation

```bibtex
@article{lemaitre2002selecting,
  title = {Selecting and Scheduling Observations of Agile Satellites},
  author = {Lema{\^i}tre, Michel and Verfaillie, G{\'e}rard and Jouhaud, Frank and Lachiver, Jean-Michel and Bataille, Nicolas},
  journal = {Aerospace Science and Technology},
  volume = {6},
  number = {5},
  pages = {367--381},
  year = {2002},
  doi = {10.1016/S1270-9638(02)01173-2}
}
```

Related reference for repair and diversification ideas:

```bibtex
@article{vasquez2001logic,
  title = {A Logic-Constrained Knapsack Formulation and a Tabu Algorithm for the Daily Photograph Scheduling of an Earth Observation Satellite},
  author = {Vasquez, Michel and Hao, Jin-Kao},
  journal = {Computational Optimization and Applications},
  volume = {20},
  number = {2},
  pages = {137--157},
  year = {2001},
  doi = {10.1023/A:1012300271919}
}
```

The solver is standalone. It reads benchmark case files and writes a benchmark solution JSON, but it does not import or execute benchmark, experiment, runtime, or other solver internals.

## Method Summary

Lemaître et al. maintain feasible per-satellite image sequences, propagate earliest/latest feasible positions, and perform insertion/removal moves that handle stereoscopic observations as coupled products.

This reproduction keeps that structure and adapts it to `stereo_imaging`:

1. **Candidate generation** — for each satellite–target pair, discover access intervals and sample candidate observation windows that satisfy geometry, solar elevation, off-nadir, and boresight constraints.
2. **Product library** — enumerate feasible pair-stereo and tri-stereo products from candidates that satisfy convergence, overlap fraction, pixel-scale ratio, and near-nadir-anchor constraints.
3. **Greedy seed** — build a deterministic coverage-first seed from target-indexed ranked product queues, avoiding repeated full-pool rescans. Products are inserted atomically into per-satellite sequences, and a tri-stereo upgrade pass attempts higher-quality replacements where they fit.
4. **Local search** — improve the seed via product-level moves: insert uncovered targets, replace covered targets with higher-quality products, remove low-quality products to free capacity for better alternatives, and swap/remove-then-repair fallback moves. All moves are atomic and roll back on failure. Seeded multi-run profiles perturb move order deterministically while reusing the candidate and product library once.
5. **Repair** — scan sequences for overlap or gap violations and remove the least-valuable conflicting product. This is a conservative defensive step (Vasquez-inspired) rather than the core Lemaitre method.

## Benchmark Adaptation

The benchmark differs from the paper in several important ways:

- **Point AOI products instead of strips.** The benchmark uses fixed candidate observation windows (not continuous time windows), so the solver samples discrete start times within access intervals rather than optimizing window boundaries.
- **Tri-stereo extension.** The benchmark adds tri-stereo products (three near-simultaneous observations). The solver handles these as coupled three-observation products with the same atomic insertion/rollback logic as pairs.
- **Benchmark-native stereo feasibility.** Convergence angle, overlap fraction, pixel-scale ratio, and near-nadir-anchor constraints are evaluated exactly per the benchmark verifier, not via the paper's simplified stereo model.
- **Coverage-first lexicographic objective.** The benchmark ranks by `valid > coverage_ratio > normalized_quality`. The solver optimizes coverage first, then quality, instead of the paper's linear/non-linear weighted sum.
- **Deterministic evaluation.** The repository requires reproducible runs, so the solver uses deterministic tie-breaking and seeded random perturbation (via the `num_runs` harness) rather than unbounded stochastic profiling.
- **No memory, energy, weather, or downlink constraints.** The benchmark omits these, so the solver does not model them.

That means this solver reproduces the paper's CP/local-search approach while remaining faithful to the benchmark's public validity contract.

## Solver Contract

```bash
./setup.sh
./solve.sh <case_dir> [config_dir] [solution_dir]
```

`setup.sh` is effectively a no-op when using the project environment.

`solve.sh` writes:

- `solution.json`: primary benchmark solution with an `actions` array of `observation` actions
- `status.json`: solver summary, timings split into construction/seed/search/repair phases, candidate/product library details, run-policy metadata, and multi-run aggregate statistics when `num_runs > 1`
- `debug/*`: optional debug artifacts when `debug: true`

The primary solution artifact is one JSON object with a top-level `actions` array of `observation` actions.

## Search And Repair

The solver pipeline is:

1. Load `mission.yaml`, `satellites.yaml`, and `targets.yaml`.
2. Generate candidate observation windows per satellite–target pair, filtered by access geometry.
3. Build a product library of feasible pair-stereo and tri-stereo products.
4. Construct a deterministic coverage-first greedy seed with tri-stereo upgrade pass.
5. Run bounded local search with insert/replace/remove/swap moves.
6. Run conservative repair to remove any remaining sequence conflicts.

The repair stage is intentionally conservative. It keeps the solver standalone and reduces official verifier failures without claiming that the solver-local sequence model is provably exact in all edge cases.

## Configuration

The solver reads optional config from either:

- `<config_dir>/config.yaml`
- `<config_dir>/config.yml`
- `<config_dir>/config.json`
- `<config_dir>/cp_local_search_stereo_insertion.yaml`
- `<config_dir>/cp_local_search_stereo_insertion.yml`
- `<config_dir>/cp_local_search_stereo_insertion.json`

See [config.example.yaml](./config.example.yaml) for a commented example.

Key knobs:

- `observation_duration_s` — fixed observation window duration
- `candidate_stride_s` — sampling stride within access intervals
- `access_discovery_step_s` — coarse step for discovering access intervals
- `max_candidates_per_target_per_sat` — cap candidates per target (default: none)
- `seed_only` — emit seed solution directly, skip local search
- `tri_stereo_seed_phase` — enable tri-stereo upgrade pass after pair seed
- `pair_weight` / `tri_weight` — weight multipliers for seed ranking
- `run_profile` — `smoke`, `benchmark`, or `profile`
- `max_passes` / `max_moves_per_pass` / `max_time_seconds` — local search budget
- `remove_move_enabled` — enable dedicated remove-then-re-insert moves
- `num_runs` — override the profile's number of independent deterministic-perturbed runs
- `random_seed` — base seed for multi-run randomization
- `parallel_workers` — parallel candidate generation across satellites (`null` = auto, `0` = disable)
- `debug` — write detailed debug artifacts

`num_runs` runs seed + local search + repair multiple times with different deterministic RNG perturbations and keeps the best result. Candidate generation and product construction are done once and reused across runs. Aggregate best/mean/min statistics and per-run timing details are written to `status.json`.

## Run Profiles

The solver has three explicit runtime profiles:

| Profile | Default runs | Per-run local-search budget | Intended use |
|---|---:|---:|---|
| `smoke` | 1 | 30 s | deterministic validation and CI-oriented replay |
| `benchmark` | 5 | 120 s | fair public evidence with best/mean multi-run metrics |
| `profile` | 10 | 120 s | longer diagnostic profiling |

The default profile is `smoke` to keep single-run behavior deterministic and easy to reproduce. For benchmark evidence, use a config directory containing:

```yaml
run_profile: benchmark
```

The benchmark profile is not a paper-literal 100-execution quality profile; it is a benchmark-adapted, deterministic multi-run compromise. It preserves reproducibility while reporting best and mean outcomes honestly.

## Debug Artifacts

When `debug: true`, the solver writes:

- `debug/candidate_summary.json`
- `debug/product_summary.json`
- `debug/seed_log.json`
- `debug/local_search_log.json`
- `debug/repair_log.json`

These are useful for answering:

- why a target has zero candidates or products
- which products were accepted/rejected during seed construction and why
- which local-search moves were attempted and accepted
- whether repair removed any products due to sequence conflicts
- runtime breakdown across phases

## Running It

Direct setup:

```bash
./solvers/stereo_imaging/cp_local_search_stereo_insertion/setup.sh
```

Direct solve on a public smoke case:

```bash
./solvers/stereo_imaging/cp_local_search_stereo_insertion/solve.sh \
  benchmarks/stereo_imaging/dataset/cases/test/case_0001
```

Direct solve with a config directory:

```bash
./solvers/stereo_imaging/cp_local_search_stereo_insertion/solve.sh \
  benchmarks/stereo_imaging/dataset/cases/test/case_0001 \
  /path/to/config_dir \
  /tmp/stereo_cp_solution
```

Official smoke verification through `main_solver`:

```bash
uv run python experiments/main_solver/run.py \
  --benchmark stereo_imaging \
  --solver stereo_imaging_cp_local_search_stereo_insertion \
  --case test/case_0001
```

Solver-local tests:

```bash
./solvers/stereo_imaging/cp_local_search_stereo_insertion/test.sh
```

Aggregate experiment results:

```bash
uv run python experiments/main_solver/aggregate.py
```

## Sanity Baseline

The paper reports scheduled-image counts and quality profiles, not benchmark `coverage_ratio` or `normalized_quality`. Treat the paper's profiles as a rough sanity check for completion behavior, not as a target metric table for this benchmark.

What matters here is:

- official verification passes (`valid=true`, zero violations)
- candidate and product counts are plausible
- repair does not collapse the schedule
- coverage and quality remain strong on public cases
- seed construction is not quadratic at public-case scale
- `status.json` makes construction time distinct from search time

If the seed looks strong but local search finds few improving moves, inspect the move log to verify that insert/replace/remove moves are being attempted. The public cases currently show modest but real local-search improvements on several cases; most of the remaining wall-clock cost is product construction rather than search.

## Validation

All 5 public test cases pass the benchmark verifier on the redesigned benchmark. These smoke-profile timings were measured on 2026-04-25 in the shared development environment with default config (`run_profile: smoke`, `num_runs: 1`, `parallel_workers: null`) and outputs under `/tmp/cp_phase7_public`.

| Case | Valid | Candidates | Products | Final coverage | Coverage ratio | Norm. quality | LS accepted | Seed s | Local-search s | Total s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| test/case_0001 | true | 7,815 | 32,570 | 142 | 0.979 | 0.958 | 1 | 0.107 | 0.813 | 47.7 |
| test/case_0002 | true | 7,611 | 33,677 | 121 | 0.992 | 0.989 | 1 | 0.104 | 0.646 | 49.7 |
| test/case_0003 | true | 6,687 | 27,959 | 118 | 0.959 | 0.957 | 5 | 0.113 | 1.180 | 65.0 |
| test/case_0004 | true | 5,871 | 21,857 | 124 | 0.944 | 0.924 | 3 | 0.170 | 1.309 | 42.3 |
| test/case_0005 | true | 7,583 | 42,434 | 139 | 0.979 | 0.975 | 7 | 0.127 | 2.038 | 220.9 |

Benchmark-profile evidence on `test/case_0001` with `run_profile: benchmark` (`num_runs: 5`, construction reused once) produced a valid solution with best internal coverage/quality `142 / 141.808042`, mean internal coverage/quality `142.0 / 141.620498`, verifier coverage ratio `0.971831`, verifier normalized quality `0.960582`, total runtime `52.2 s`, and total local-search time `4.34 s`.

**Determinism:** a repeated smoke run on `test/case_0001` produced a byte-identical `solution.json`.

**Repair:** the conservative repair pass removed 0 products on all public smoke cases.

**Tri-stereo:** tri-stereo products are generated and scheduled through the same product-atomic sequence path as stereo pairs. Public smoke runs retain thousands of feasible tri products in the product library on every case.

## Known Limitations

- This is a reproduction of the paper's method family, not a claim to reproduce every runtime or every table from the paper.
- The greedy seed algorithm is a pool-based coverage-first heuristic invented for this implementation, not the sequential track-builder described in Lemaitre §3.1.
- Local search does improve several public cases, but the current neighborhoods remain modest compared with the paper's adaptive stochastic insertion/removal procedure.
- The solver does not implement the paper's adaptive acceptance probability `p_a` or full stochastic profiling regime.
- Candidate generation can be parallelized across satellites; product construction, seed, and local search remain single-process Python.
- Product construction is now the main remaining runtime bottleneck, especially on `test/case_0005`. The run policy reports this explicitly; the solver is benchmark-faithful and reproducible, but not a claim of competitive optimized performance.
- Solver-local product predicates are designed to match the verifier geometry, but minor drift is possible due to floating-point ordering.

## Evidence Type

This solver is registered in `experiments/main_solver` with `evidence_type: reproduced_solver`.
