# Main Solver Experiment

`main_solver` runs benchmark-grouped solvers through the public solver contract:

```bash
./setup.sh
./solve.sh <case_dir> <config_dir> <solution_dir>
```

The experiment owns run selection, result layout, verification, and aggregation. Solvers own implementation details and may use any language behind their shell entrypoints.

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

Aggregate CSV metric columns are declared by solver profiles under `experiments/main_solver/solvers/`:

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

| method | case | valid | profit | weight |
| --- | --- | --- | --- | --- |
| spot5_reference_lookup | test/1021 | true | 169243 | 200 |
| spot5_reference_lookup | test/1403 | true | 172143 | 199 |
| spot5_reference_lookup | test/1506 | true | 164241 | 200 |
| spot5_reference_lookup | test/28 | true | 56053 | 0 |
| spot5_reference_lookup | test/8 | true | 10 | 0 |

Metric notes:
- `profit` is the verifier-computed imaging profit; higher is better.
- `weight` is the verifier-computed plan resource weight; it is mainly a feasibility/resource-use check and should stay within benchmark limits (200 or 0).

### SatNet

| method | case | evidence | u_rms | u_max | total_h | satisfied | run_h | train_h |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| satnet_milp_claudet2022 | W10_2018 | citation_reported | 0.26 | 0.479 | 822 | 203 | 18 | - |
| satnet_milp_claudet2022 | W20_2018 | citation_reported | 0.21 | 0.641 | 1059 | 249 | 10.500 | - |
| satnet_milp_claudet2022 | W30_2018 | citation_reported | 0.29 | 0.643 | 983 | 231 | 13.500 | - |
| satnet_milp_claudet2022 | W40_2018 | citation_reported | 0.4 | 1 | 949 | 223 | 22.500 | - |
| satnet_milp_claudet2022 | W50_2018 | citation_reported | 0.35 | 0.6 | 816 | 197 | 7.5 | - |
| satnet_rl_ppo_goh2021 | W10_2018 | citation_reported | 0.28 | 0.71 | 886 | 204 | - | 4 |
| satnet_rl_ppo_goh2021 | W20_2018 | citation_reported | 0.27 | 0.81 | 1000 | 223 | - | 18 |
| satnet_rl_ppo_goh2021 | W30_2018 | citation_reported | 0.28 | 0.85 | 1100 | 229 | - | 13 |
| satnet_rl_ppo_goh2021 | W40_2018 | citation_reported | 0.39 | 0.82 | 1058 | 216 | - | 6 |
| satnet_rl_ppo_goh2021 | W50_2018 | citation_reported | 0.36 | 0.67 | 879 | 185 | - | 25 |

Metric notes:
- `u_rms` and `u_max` are the RMS unsatisfied ratio and the max unsatisfied ratio among requests / missions, lower values indicate better request satisfaction.
- `total_h` and `satisfied` report scheduled service volume; higher values indicate more delivered request-hours and requests.
- `run_h` is MILP solve time in hours when reported, and `train_h` is RL training time in hours when reported.

### AEOSSP Standard

| method | case | valid | WCR | CR | TAT | PC | solve_s |
| --- | --- | --- | --- | --- | --- | --- | --- |
| aeossp_standard_greedy_lns | test/case_0001 | true | 0.6183 | 0.6662 | 1118.2 | 17313.3 | 75.456 |
| aeossp_standard_greedy_lns | test/case_0002 | true | 0.6978 | 0.7393 | 1120.8 | 18804.4 | 82.712 |
| aeossp_standard_greedy_lns | test/case_0003 | true | 0.6988 | 0.7324 | 1150.9 | 17408.7 | 73.521 |
| aeossp_standard_greedy_lns | test/case_0004 | true | 0.6706 | 0.7094 | 1140.3 | 17715.6 | 77.502 |
| aeossp_standard_greedy_lns | test/case_0005 | true | 0.7227 | 0.7589 | 1111.2 | 21240.9 | 104.31 |
| aeossp_standard_mwis_conflict_graph | test/case_0001 | true | 0.7057 | 0.7432 | 1051.1 | 18773.7 | 107.43 |
| aeossp_standard_mwis_conflict_graph | test/case_0002 | true | 0.7763 | 0.8057 | 1013.3 | 20150.9 | 144.54 |
| aeossp_standard_mwis_conflict_graph | test/case_0003 | true | 0.7837 | 0.8063 | 1021.9 | 18710.1 | 64.606 |
| aeossp_standard_mwis_conflict_graph | test/case_0004 | true | 0.7395 | 0.7757 | 1036.2 | 18966.2 | 98.094 |
| aeossp_standard_mwis_conflict_graph | test/case_0005 | true | 0.7858 | 0.8168 | 966.60 | 22374.9 | 186.04 |

Metric notes:
- `WCR` is weighted completion ratio and `CR` is completion ratio; higher is better.
- `TAT` is mean `(completion_time - release_time)` over completed tasks, and `PC` is power consumption; lower is better.
- `solve_s` is runner wall time in seconds and is an audit/runtime field, not a benchmark score.

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

Metric notes:
- `coverage` is `coverage_ratio`, the fraction of targets with at least one valid stereo or tri-stereo imaging product; higher is better.
- `quality` is `normalized_quality`, the mean best per-target stereo quality score; higher is better.
- `solve_s` is runner wall time in seconds and is used for audit rather than scoring.

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

Metric notes:
- `service` is `service_fraction` and `worst_service` is `worst_demand_service_fraction`; higher is better.
- `mean_ms` and `p95_ms` are mean and 95th-percentile service latency in milliseconds; lower is better after service metrics.
- `added` is the number of added relay satellites, and fewer additions are preferred when service metrics are comparable. `solve_s` is runtime.

### Revisit Constellation

| method | case | valid | sats | actions | capped_gap_h | solver_s |
| --- | --- | --- | --- | --- | --- | --- |
| revisit_constellation_j2_rgt_set_cover | test/case_0001 | true | 18 | 156 | 8 | 342.13 |
| revisit_constellation_j2_rgt_set_cover | test/case_0002 | true | 15 | 130 | 8 | 311.03 |
| revisit_constellation_j2_rgt_set_cover | test/case_0003 | true | 9 | 137 | 12.464 | 333.74 |
| revisit_constellation_j2_rgt_set_cover | test/case_0004 | true | 10 | 81 | 12.000 | 236.03 |
| revisit_constellation_j2_rgt_set_cover | test/case_0005 | true | 12 | 73 | 13.895 | 241.75 |
| revisit_constellation_rgt_apc_gap_constructive | test/case_0001 | true | 18 | - | 9.9899 | 543.83 |
| revisit_constellation_rgt_apc_gap_constructive | test/case_0002 | true | 16 | - | 9.9475 | 525.68 |
| revisit_constellation_rgt_apc_gap_constructive | test/case_0003 | true | 12 | - | 14.431 | 508.24 |
| revisit_constellation_rgt_apc_gap_constructive | test/case_0004 | true | 17 | - | 12.410 | 546.40 |
| revisit_constellation_rgt_apc_gap_constructive | test/case_0005 | true | 17 | - | 12.000 | 540.70 |

Metric notes:
- `sats` is the submitted constellation size and `actions` is the number of scheduled observations when the solver reports it.
- `capped_gap_h` is mean capped maximum revisit gap in hours; lower is better.
- `solver_s` is solver-reported runtime in seconds and is used for audit rather than scoring.

### Regional Coverage

| method | case | valid | coverage | weighted_coverage | min_battery_wh | solver_s |
| --- | --- | --- | --- | --- | --- | --- |
| regional_coverage_celf_submodular | test/case_0001 | true | 0.9055 | 0.8978 | 492.90 | 112.29 |
| regional_coverage_celf_submodular | test/case_0002 | true | 0.9976 | 0.9979 | 496.67 | 118.34 |
| regional_coverage_celf_submodular | test/case_0003 | true | 0.9471 | 0.9481 | 493.13 | 85.044 |
| regional_coverage_celf_submodular | test/case_0004 | true | 1 | 1 | 496.56 | 127.94 |
| regional_coverage_celf_submodular | test/case_0005 | true | 0.9978 | 0.9976 | 491.63 | 122.31 |
| regional_coverage_cp_local_search | test/case_0001 | true | 1 | 1 | 492.90 | 133.23 |
| regional_coverage_cp_local_search | test/case_0002 | true | 0.9986 | 0.9989 | 496.67 | 149.99 |
| regional_coverage_cp_local_search | test/case_0003 | true | 0.9781 | 0.9776 | 493.13 | 181.53 |
| regional_coverage_cp_local_search | test/case_0004 | true | 1 | 1 | 496.56 | 113.01 |
| regional_coverage_cp_local_search | test/case_0005 | true | 1 | 1 | 497.26 | 87.464 |

Metric notes:
- `coverage` is the overall `coverage_ratio`, and `weighted_coverage` is the region-weighted coverage ratio; higher is better.
- `min_battery_wh` is the minimum remaining battery margin in watt-hours; higher indicates more energy slack.
- `solver_s` is solver-reported runtime in seconds and is used for audit rather than scoring.

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

For runnable solvers that write `status.json`, aggregation preserves official verifier metrics while also surfacing selected solver-status fields such as execution mode, solve/verifier durations, phase timings, candidate counts, search seeds, local-search move counts, and CP backend/call/timing summaries. These fields are supplemental audit data; official validity and benchmark scores remain the verifier-owned fields in `run.json`.
