# MCLP+TEG Contact Plan Solver

Deterministic reproduced solver for `relay_constellation` that combines a Rogers-style maximal covering location problem (MCLP) candidate-selection layer with a Gerard-style time-expanded graph (TEG) contact scheduler.

The solver follows the repository solver contract:

```bash
./setup.sh
./solve.sh <case_dir> <config_dir> <solution_dir>
```

It reads benchmark case files and writes `solution.json`, `status.json`, and solver-local debug artifacts. It does not import benchmark Python modules or call benchmark verifiers.

## Recommended configuration

The canonical configuration is owned by `experiments/main_solver/solvers/relay_constellation_mclp_teg_contact_plan.yaml`. That experiment profile is the configuration used for reproduced-solver reporting.

Direct no-config runs use a small built-in smoke configuration for local contract checks only. Smoke output should not be reported as the solver's reproduction result.

## Method

### Candidate selection

The Rogers layer is adapted as follows:

- Generate a deterministic finite library of feasible orbital slots inside the case altitude, inclination, eccentricity, and RAAN bounds.
- Treat the benchmark `max_added_satellites` value as an upper-bound cardinality constraint.
- Score candidates by marginal demand-window service potential: a demand sample is covered when the active constellation can connect the source and destination endpoints through ground links and ISLs.
- Select candidates with deterministic indexed greedy MCLP scoring. A small PuLP/CBC MILP path remains available for very small candidate sets, but public cases use greedy selection.

The experiment-owned reproduction configuration generates roughly 300 candidates on the current public cases.

### Contact scheduling

The Gerard layer is adapted as follows:

- Build time-expanded link feasibility on the benchmark routing grid.
- Use a two-stage link cache: MCLP selection uses ground visibility plus backbone-touching ISLs; final scheduling rebuilds an exact cache for the backbone plus selected candidates.
- Use route-aware per-sample scheduling for the reported configuration. It greedily selects complete endpoint-to-endpoint paths while respecting `max_links_per_satellite` and `max_links_per_endpoint`.
- Compact consecutive selected samples into verifier-compatible interval actions.

The bounded per-sample scheduler MILP remains available for small cases, but the public cases use the scalable route-aware path.

## Paper-to-benchmark adaptations

| Paper concept | Benchmark adaptation |
|---|---|
| Rogers target coverage reward | Demand-window service-potential reward over endpoint pairs |
| Rogers exact fixed cardinality | Benchmark upper bound `<= max_added_satellites` |
| Rogers full candidate-set MILP | Deterministic greedy MCLP, with bounded MILP only for small cases |
| Gerard TEG link activation | `ground_link` and `inter_satellite_link` interval actions |
| Gerard full-horizon MILP | Bounded per-sample MILP with route-aware fallback |
| Gerard route tables and forwarding | Not submitted; benchmark verifier owns routing and allocation |
| Optical retargeting delay | Not modeled because the benchmark does not model pointing delay |

## Reported evidence

Current reported evidence uses the experiment-owned reproduction configuration and reports `case_0001` and `case_0002` performance. A final all-case canonical run can be rerun through `experiments/main_solver` when all solvers are ready.

| case | valid | service_fraction | worst_demand_service_fraction | added satellites | actions | solve_s | verifier_s | candidates |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `test/case_0001` | true | 0.9259259259 | 0.5555555556 | 3 | 74 | 467.394 | 84.013 | 300 |
| `test/case_0002` | true | 0.9523809524 | 0.6666666667 | 3 | 78 | 470.848 | 98.408 | 300 |

For these runs, MCLP marginal evaluation is no longer the dominant cost; propagation over the 96-hour horizon dominates runtime.

## Configuration fields

`solve.sh` receives a config directory from the experiment runner. The solver reads `config.yaml` first and falls back to `config.json` for ad hoc local use.

Important keys:

| Key | Purpose |
|---|---|
| `mclp_mode` | `auto`, `greedy`, `milp`, or `none` candidate selection. |
| `scheduler_mode` | `auto`, `greedy`, `route_aware`, or `milp` contact scheduling. |
| `parallel_mode` | `auto`, `parallel`, or `sequential` process execution. |
| `max_parallel_workers` | Upper bound on process-pool workers. |
| `time_budget_s` | Informational per-case budget recorded in `status.json`. |
| `orbit_grid` | Candidate library density. |
| `mclp_milp_config` | Small-instance MCLP MILP bounds. |
| `milp_config` | Small-instance scheduler MILP bounds and fallback choice. |

## Outputs

`solution.json` contains benchmark-submitted `added_satellites` and `actions`.

`status.json` records the compute envelope, candidate count, selected candidates, scheduler mode, timing breakdowns, parallel execution model, cache diagnostics, and fallback reasons.

`debug/` contains summaries for generated candidates, link caches, MCLP scoring, selected orbits, and scheduler behavior.

## Limitations

- The solver reproduces method families, not every table or mission assumption from the papers.
- Public cases are too large for the exact full candidate-set Rogers MILP and Gerard full-horizon MILP paths.
- The route-aware scheduler is a benchmark-adapted scalable fallback, not a full temporal-capacity MILP.
- The benchmark verifier owns routing and latency scoring, so the solver submits link activations rather than routes.
- Larger candidate grids remain propagation-heavy; the reported configuration is the strongest practical current envelope.
