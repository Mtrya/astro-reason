# Main Solver Experiment

`main_solver` is the first non-agentic experiment scaffold. It is responsible
for selecting runnable method profiles, executing them through the public
solver contract, verifying outputs, and aggregating result rows.

It runs benchmark-grouped solvers through the public solver contract:

```bash
./setup.sh
./solve.sh <case_dir> <config_dir> <solution_dir>
```

The experiment owns run selection, result layout, verification, and aggregation. Solvers own implementation details and may use any language behind their shell entrypoints.

Unlike agentic runs, traditional solver entries are benchmark-specific. The
experiment therefore keeps one profile registry and one or more run-selection
configs:

```text
experiments/main_solver/
├── config.yaml
├── config_*.yaml
└── solvers/
```

Each profile carries the benchmark name, case list or reported metrics,
executable verifier command when the method is runnable, and optional
method-owned config written to each job's `config/config.yaml`.

Experiment profiles own evidence metadata such as `evidence_type`. The hardened solver-contract registry at `solvers/finished_solvers.json` owns only `repro_ci` metadata and case/fixture paths.

## Evidence Types

Rows keep an explicit `evidence_type`:

- `reproduced_solver`: runnable solver output verified by a benchmark verifier
- `fixture_backed_lookup`: runnable lookup output verified by a benchmark verifier
- `citation_reported`: non-runnable metrics copied from cited literature

Do not merge these categories in reporting without preserving the label.

## Usage

Preview selected jobs:

```bash
uv run python experiments/main_solver/run.py --dry-run
```

Run a smoke case:

```bash
uv run python experiments/main_solver/run.py \
    --benchmark spot5 \
    --solver spot5_reference_lookup \
    --case test/8
```

Run one solver case:

```bash
uv run python experiments/main_solver/run.py \
    --benchmark <benchmark_id> \
    --solver <solver_id> \
    --case <case_id>
```

Run a named solver policy:

```bash
uv run python experiments/main_solver/run.py \
    --benchmark <benchmark_id> \
    --solver <solver_id> \
    --policy <policy_id>
```

Policy metadata is recorded in `run.json`. Solver-specific quality interpretation belongs in solver documentation and solver profile metadata, not in the shared experiment runner.

Materialize SatNet citation-backed rows:

```bash
uv run python experiments/main_solver/run.py \
    --benchmark satnet \
    --solver satnet_milp_claudet2022
```

Run a named experiment selection:

```bash
uv run python experiments/main_solver/run.py \
    --config experiments/main_solver/config.yaml
```

Aggregate results:

```bash
uv run python experiments/main_solver/aggregate.py
```

Aggregate CSV metric columns are declared by solver profiles under
`experiments/main_solver/solvers/`:

```yaml
aggregate_metrics:
  - name: service_fraction
    source: verifier.metrics.service_fraction
  - name: solver_timing_total_s
    source: solver_status.timing_seconds.total
```

`source` must be a direct dot path into `run.json`. The aggregator always emits stable run metadata columns such as benchmark, solver, case id, status, validity, evidence type, durations, compact verifier/solver-status JSON fields, and `run_json`; solver-owned declarations add benchmark or method metrics without editing the shared aggregator. Derived metrics should be emitted into `run.json` by the verifier or solver before aggregation.

## Main Result Matrix

The tables below summarize the configured `main_solver` matrix from commit `e07f0161ea5d4bb83099ac68131f1a31124c8698`. The run used `experiments/main_solver/config.yaml`, produced 65 selected rows, verified all 55 runnable rows with `valid=true`, and kept the 10 SatNet rows as `citation_reported` evidence.

Metric abbreviations follow each benchmark verifier or cited metric schema. `solve_s` is runner wall time for runnable rows, while `solver_s` is the solver-reported internal total when the solver emits it.

### SPOT5

| method | case | valid | profit | weight | solve_s |
| --- | --- | --- | --- | --- | --- |
| spot5_reference_lookup | test/1021 | true | 169243 | 200 | 0.0282 |
| spot5_reference_lookup | test/1403 | true | 172143 | 199 | 0.0295 |
| spot5_reference_lookup | test/1506 | true | 164241 | 200 | 0.0311 |
| spot5_reference_lookup | test/28 | true | 56053 | 0 | 0.0277 |
| spot5_reference_lookup | test/8 | true | 10 | 0 | 0.0262 |

### SatNet

| method | case | evidence | total_h | satisfied | u_rms | u_max | run_h | train_h |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| satnet_milp_claudet2022 | W10_2018 | citation_reported | 822 | 203 | 0.26 | 0.479 | 18 | - |
| satnet_milp_claudet2022 | W20_2018 | citation_reported | 1059 | 249 | 0.21 | 0.641 | 10.500 | - |
| satnet_milp_claudet2022 | W30_2018 | citation_reported | 983 | 231 | 0.29 | 0.643 | 13.500 | - |
| satnet_milp_claudet2022 | W40_2018 | citation_reported | 949 | 223 | 0.4 | 1 | 22.500 | - |
| satnet_milp_claudet2022 | W50_2018 | citation_reported | 816 | 197 | 0.35 | 0.6 | 7.5 | - |
| satnet_rl_ppo_goh2021 | W10_2018 | citation_reported | 886 | 204 | 0.28 | 0.71 | - | 4 |
| satnet_rl_ppo_goh2021 | W20_2018 | citation_reported | 1000 | 223 | 0.27 | 0.81 | - | 18 |
| satnet_rl_ppo_goh2021 | W30_2018 | citation_reported | 1100 | 229 | 0.28 | 0.85 | - | 13 |
| satnet_rl_ppo_goh2021 | W40_2018 | citation_reported | 1058 | 216 | 0.39 | 0.82 | - | 6 |
| satnet_rl_ppo_goh2021 | W50_2018 | citation_reported | 879 | 185 | 0.36 | 0.67 | - | 25 |

### AEOSSP Standard

| method | case | valid | CR | WCR | PC | TAT | solve_s |
| --- | --- | --- | --- | --- | --- | --- | --- |
| aeossp_standard_greedy_lns | test/case_0001 | true | 0.6662 | 0.6183 | 17313.3 | 1118.2 | 75.456 |
| aeossp_standard_greedy_lns | test/case_0002 | true | 0.7393 | 0.6978 | 18804.4 | 1120.8 | 82.712 |
| aeossp_standard_greedy_lns | test/case_0003 | true | 0.7324 | 0.6988 | 17408.7 | 1150.9 | 73.521 |
| aeossp_standard_greedy_lns | test/case_0004 | true | 0.7094 | 0.6706 | 17715.6 | 1140.3 | 77.502 |
| aeossp_standard_greedy_lns | test/case_0005 | true | 0.7589 | 0.7227 | 21240.9 | 1111.2 | 104.31 |
| aeossp_standard_mwis_conflict_graph | test/case_0001 | true | 0.7432 | 0.7057 | 18773.7 | 1051.1 | 107.43 |
| aeossp_standard_mwis_conflict_graph | test/case_0002 | true | 0.8057 | 0.7763 | 20150.9 | 1013.3 | 144.54 |
| aeossp_standard_mwis_conflict_graph | test/case_0003 | true | 0.8063 | 0.7837 | 18710.1 | 1021.9 | 64.606 |
| aeossp_standard_mwis_conflict_graph | test/case_0004 | true | 0.7757 | 0.7395 | 18966.2 | 1036.2 | 98.094 |
| aeossp_standard_mwis_conflict_graph | test/case_0005 | true | 0.8168 | 0.7858 | 22374.9 | 966.60 | 186.04 |

### Stereo Imaging

| method | case | valid | coverage | quality | solve_s |
| --- | --- | --- | --- | --- | --- |
| stereo_imaging_cp_local_search_stereo_insertion | test/case_0001 | true | 0.9789 | 0.9581 | 67.004 |
| stereo_imaging_cp_local_search_stereo_insertion | test/case_0002 | true | 0.9917 | 0.9887 | 77.642 |
| stereo_imaging_cp_local_search_stereo_insertion | test/case_0003 | true | 0.9587 | 0.9572 | 100.67 |
| stereo_imaging_cp_local_search_stereo_insertion | test/case_0004 | true | 0.9444 | 0.9238 | 63.700 |
| stereo_imaging_cp_local_search_stereo_insertion | test/case_0005 | true | 0.9787 | 0.9747 | 317.79 |
| stereo_imaging_time_window_pruned_stereo_milp | test/case_0001 | true | 0.9296 | 0.913 | 100.82 |
| stereo_imaging_time_window_pruned_stereo_milp | test/case_0002 | true | 0.9917 | 0.9772 | 83.624 |
| stereo_imaging_time_window_pruned_stereo_milp | test/case_0003 | true | 0.9421 | 0.9176 | 88.634 |
| stereo_imaging_time_window_pruned_stereo_milp | test/case_0004 | true | 0.8968 | 0.8532 | 83.311 |
| stereo_imaging_time_window_pruned_stereo_milp | test/case_0005 | true | 0.9574 | 0.9388 | 88.511 |

### Relay Constellation

| method | case | valid | service | worst_service | mean_ms | p95_ms | added | solve_s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| relay_constellation_mclp_teg_contact_plan | test/case_0001 | true | 0.9259 | 0.5556 | 158.96 | 289.55 | 3 | 503.04 |
| relay_constellation_mclp_teg_contact_plan | test/case_0002 | true | 0.9524 | 0.6667 | 123.49 | 220.87 | 3 | 514.57 |
| relay_constellation_mclp_teg_contact_plan | test/case_0003 | true | 0.93 | 0.65 | 101.51 | 177.11 | 2 | 521.76 |
| relay_constellation_mclp_teg_contact_plan | test/case_0004 | true | 0.9444 | 0.6667 | 100.39 | 166.51 | 3 | 506.59 |
| relay_constellation_mclp_teg_contact_plan | test/case_0005 | true | 0.9111 | 0.625 | 151.25 | 232.03 | 4 | 503.74 |
| relay_constellation_umcf_srr_contact_plan | test/case_0001 | true | 0.9241 | 0.5444 | 156.93 | 298.10 | 3 | 68.750 |
| relay_constellation_umcf_srr_contact_plan | test/case_0002 | true | 0.9393 | 0.6667 | 133.96 | 234.08 | 2 | 71.955 |
| relay_constellation_umcf_srr_contact_plan | test/case_0003 | true | 0.9911 | 0.9667 | 108.60 | 191.60 | 2 | 70.903 |
| relay_constellation_umcf_srr_contact_plan | test/case_0004 | true | 0.8893 | 0.4133 | 109.27 | 191.25 | 2 | 71.102 |
| relay_constellation_umcf_srr_contact_plan | test/case_0005 | true | 0.8941 | 0.625 | 169.92 | 342.66 | 4 | 72.663 |

### Revisit Constellation

| method | case | valid | sats | actions | capped_gap_h | high_gap_targets | violations | solver_s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| revisit_constellation_j2_rgt_set_cover | test/case_0001 | true | 18 | 156 | 8 | 0 | - | 342.13 |
| revisit_constellation_j2_rgt_set_cover | test/case_0002 | true | 15 | 130 | 8 | 0 | - | 311.03 |
| revisit_constellation_j2_rgt_set_cover | test/case_0003 | true | 9 | 137 | 12.464 | 6 | - | 333.74 |
| revisit_constellation_j2_rgt_set_cover | test/case_0004 | true | 10 | 81 | 12.000 | 0 | - | 236.03 |
| revisit_constellation_j2_rgt_set_cover | test/case_0005 | true | 12 | 73 | 13.895 | 1 | - | 241.75 |
| revisit_constellation_rgt_apc_gap_constructive | test/case_0001 | true | 18 | - | 9.9899 | - | 17 | 543.83 |
| revisit_constellation_rgt_apc_gap_constructive | test/case_0002 | true | 16 | - | 9.9475 | - | 14 | 525.68 |
| revisit_constellation_rgt_apc_gap_constructive | test/case_0003 | true | 12 | - | 14.431 | - | 24 | 508.24 |
| revisit_constellation_rgt_apc_gap_constructive | test/case_0004 | true | 17 | - | 12.410 | - | 4 | 546.40 |
| revisit_constellation_rgt_apc_gap_constructive | test/case_0005 | true | 17 | - | 12.000 | - | 0 | 540.70 |

### Regional Coverage

| method | case | valid | coverage | weighted_coverage | actions | min_battery_wh | solver_s |
| --- | --- | --- | --- | --- | --- | --- | --- |
| regional_coverage_celf_submodular | test/case_0001 | true | 0.9055 | 0.8978 | 64 | 492.90 | 112.29 |
| regional_coverage_celf_submodular | test/case_0002 | true | 0.9976 | 0.9979 | 64 | 496.67 | 118.34 |
| regional_coverage_celf_submodular | test/case_0003 | true | 0.9471 | 0.9481 | 61 | 493.13 | 85.044 |
| regional_coverage_celf_submodular | test/case_0004 | true | 1 | 1 | 39 | 496.56 | 127.94 |
| regional_coverage_celf_submodular | test/case_0005 | true | 0.9978 | 0.9976 | 44 | 491.63 | 122.31 |
| regional_coverage_cp_local_search | test/case_0001 | true | 1 | 1 | 16 | 492.90 | 133.23 |
| regional_coverage_cp_local_search | test/case_0002 | true | 0.9986 | 0.9989 | 19 | 496.67 | 149.99 |
| regional_coverage_cp_local_search | test/case_0003 | true | 0.9781 | 0.9776 | 39 | 493.13 | 181.53 |
| regional_coverage_cp_local_search | test/case_0004 | true | 1 | 1 | 12 | 496.56 | 113.01 |
| regional_coverage_cp_local_search | test/case_0005 | true | 1 | 1 | 9 | 497.26 | 87.464 |

## Result Layout

```text
results/main_solver/<benchmark>/<solver>/<case_slug>/
├── config/
├── solution/
├── logs/
└── run.json
```

Named solver policies append the policy id to the case slug, for example `suite__case_001__large_policy`, so policy artifacts do not overwrite one another.

Benchmark verifiers are consumed as executables. The runner does not import benchmark-internal functions, classes, or modules.

## Solver Status Reporting

For runnable solvers that write `status.json`, aggregation preserves official
verifier metrics while also surfacing selected solver-status fields such as
execution mode, solve/verifier durations, phase timings, candidate counts,
search seeds, local-search move counts, and CP backend/call/timing summaries.
These fields are supplemental audit data; official validity and benchmark
scores remain the verifier-owned fields in `run.json`.
