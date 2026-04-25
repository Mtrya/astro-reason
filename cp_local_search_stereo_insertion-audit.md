# Solver Audit: cp_local_search_stereo_insertion

## Bottom Line

- Target claim: faithful reproduction adapted to the benchmark
- Status: READY_WITH_LIMITATIONS
- Compute status: FAIR_BENCHMARK_PROFILE_WITH_REMAINING_PRODUCT_BOTTLENECK

The solver is now a benchmark-faithful adaptation of the Lemaitre CP/local-search method family for the redesigned `stereo_imaging` benchmark. It loads the current mission contract, constructs same-satellite and cross-satellite stereo products, supports tri-stereo products, schedules products atomically across per-satellite sequences, preserves deterministic smoke behavior, and exposes deterministic multi-run benchmark/profile modes.

The remaining limitation is performance competitiveness, not contract faithfulness: product construction is still the dominant wall-clock cost on the largest public case. Phase 7 documentation states this explicitly instead of presenting the solver as a fully optimized competitor.

## Current Evidence

Measured on 2026-04-25 in the shared development environment with default smoke profile (`run_profile: smoke`, `num_runs: 1`, `parallel_workers: null`), outputs under `/tmp/cp_phase7_public`.

| Case | Valid | Candidates | Products | Final coverage | Coverage ratio | Norm. quality | LS accepted | Seed s | Local-search s | Total s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| test/case_0001 | true | 7,815 | 32,570 | 142 | 0.979 | 0.958 | 1 | 0.107 | 0.813 | 47.7 |
| test/case_0002 | true | 7,611 | 33,677 | 121 | 0.992 | 0.989 | 1 | 0.104 | 0.646 | 49.7 |
| test/case_0003 | true | 6,687 | 27,959 | 118 | 0.959 | 0.957 | 5 | 0.113 | 1.180 | 65.0 |
| test/case_0004 | true | 5,871 | 21,857 | 124 | 0.944 | 0.924 | 3 | 0.170 | 1.309 | 42.3 |
| test/case_0005 | true | 7,583 | 42,434 | 139 | 0.979 | 0.975 | 7 | 0.127 | 2.038 | 220.9 |

Additional Phase 7 checks:

- Full focused solver tests: `62 passed`.
- Repeated smoke run on `test/case_0001`: byte-identical `solution.json`.
- Benchmark profile on `test/case_0001` with `run_profile: benchmark`: valid output, 5 deterministic runs, best internal coverage/quality `142 / 141.808042`, mean internal coverage/quality `142.0 / 141.620498`, total local-search time `4.34 s`.

## Literature Alignment

Implemented and adapted:

- Feasible per-satellite image sequences with fixed-window earliest/latest bookkeeping.
- Product-coupled insertion and rollback for stereo requests, extended to benchmark tri-stereo.
- Local-search moves over feasible schedules: insertion, replacement, removal/reinsertion, and swap/repair.
- Deterministic multi-run profiling that gives best/mean metrics while preserving reproducibility.

Known departures from Lemaitre et al.:

- The benchmark uses point AOIs, bounded cross-satellite products, and tri-stereo, which are benchmark-driven extensions beyond the original single-satellite strip setting.
- The greedy seed is a target-indexed coverage-first product heuristic, not the paper's sequential track-builder.
- The local search does not implement the paper's adaptive insertion probability `p_a` or 100-execution stochastic quality profile.
- The solver is not an exact CP/OPL model; it reproduces the CP/local-search method shape in benchmark-adapted Python.

## Compute Assessment

The seed bottleneck identified in the earlier audit is resolved: on `test/case_0001`, seed time is about `0.1 s` rather than tens or hundreds of seconds. Status output now separates:

- construction time (`candidate_generation + product_library + sequence_sanity`),
- selected-run seed/search/repair time,
- total multi-run seed/search/repair time,
- run profile and construction-reuse policy.

The fair benchmark profile builds candidates and products once, then runs seed/search/repair repeatedly with deterministic perturbations. This avoids multiplying construction cost across runs and makes best/mean reporting honest.

Product construction remains the main runtime bottleneck. In the Phase 7 smoke evidence it ranges from about `27 s` to `202 s` across public cases. This is documented as a limitation rather than hidden behind larger local-search budgets.

## Current Claim

It is reasonable to describe this solver as a faithful reproduction adapted to the benchmark with fair smoke and benchmark-profile evidence, deterministic replay, valid public outputs, and explicit runtime accounting.

It should not be described as a highly optimized or competitive solver. Future improvement should focus on product geometry throughput: stronger tri pruning, deterministic target-level product parallelism, or both.
