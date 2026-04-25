# UMCF/SRR Contact-Plan Solver

This solver is a runnable reproduced solver for `relay_constellation`.

It follows the method family described by Grislain et al. and Lamothe et al. for unsplittable multi-commodity flow routing with sequential randomized rounding, adapted to the benchmark's public case and solution contract.

## Citation

```bibtex
@inproceedings{grislain2022rethinking,
  title={Rethinking {LEO} Constellations Routing with the Unsplittable Multi-Commodity Flows Problem},
  author={Grislain, Paul and Pelissier, Nicolas and Lamothe, Fran{\c{c}}ois and Hotescu, Oana and Lacan, J{\'e}r{\^o}me and Lochin, Emmanuel and Radzik, Jos{\'e}},
  booktitle={2022 11th Advanced Satellite Multimedia Systems Conference and 17th Signal Processing for Space Communications Workshop (ASMS/SPSC)},
  pages={1--8},
  year={2022},
  organization={IEEE},
  doi={10.1109/ASMS/SPSC55670.2022.9914743}
}

@article{lamothe2023dynamic,
  title={Dynamic unsplittable flows with path-change penalties: New formulations and solution schemes for large instances},
  author={Lamothe, Fran{\c{c}}ois and Rachelson, Emmanuel and Ha{\¨\i}t, Alain and Baudoin, C{\'e}dric and Dup{\'e}, Jean-Baptiste},
  journal={Computers \& Operations Research},
  volume={152},
  pages={106154},
  year={2023},
  publisher={Elsevier},
  doi={10.1016/j.cor.2023.106154}
}
```

The solver is standalone. It reads benchmark case files and writes a benchmark solution JSON, but it does not import or execute benchmark, experiment, runtime, or other solver internals.

## Method Summary

The Grislain paper introduces a routing protocol for LEO constellations based on the Unsplittable Multi-Commodity Flow (UMCF) problem. Instead of shortest-path latency minimization, it maximizes the total traffic crossing the constellation by assigning each commodity (source-destination pair) to a single unsplittable path. The assignment is computed via Sequential Randomized Rounding (SRR): solve a fractional LP relaxation, then repeatedly sample paths for commodities in decreasing-demand order, updating capacities after each fixation.

The Lamothe paper extends this to the dynamic setting with path-change penalties. When a commodity changes its path between consecutive time steps, a penalty is incurred. The paper presents several MILP formulations (path-sequence, arc-path, arc-node), column-generation pricing schemes, and SRR heuristics that alternate between LP updates and rounding steps.

This reproduction keeps the core UMCF/SRR structure and adapts it to `relay_constellation`:

- The solver generates a deterministic orbit library of candidate relay satellites.
- A greedy marginal selection step chooses which candidates to add.
- For each routing-sample instant, it builds a dynamic communication graph from propagated positions.
- An internal UMCF instance is formed from active demands and feasible paths.
- A path-restricted LP relaxation computes fractional path values over the finite per-sample path set.
- The SRR heuristic assigns one path per commodity from those LP values, tracking unit edge capacities and benchmark-adapted node degree capacities.
- Paths are converted into interval-based link actions, repaired for degree caps, and compacted.

## Benchmark Adaptation

The benchmark differs from the papers in several important ways:

- **No solver-submitted routes**: The benchmark verifier owns routing and allocation. The solver submits only interval-based link activations (`ground_link` and `inter_satellite_link` actions). The internal UMCF/SRR paths are an oracle for deciding which links to activate, not claims about actual end-to-end routes. The verifier may route differently than the oracle expected, especially after repair drops edges or compaction creates intervals where interior samples differ geometrically.
- **Unit edge capacities**: The verifier allocates routes under unit-capacity edge usage (edge-disjoint). The solver's internal oracle uses the same unit-capacity model, so capacity reasoning is aligned, but the verifier's deterministic shortest-path allocation may choose different paths than SRR's randomized rounding.
- **Per-sample graphs, not per-block**: The Lamothe paper optimizes over sequences of time steps (blocks) with path-change penalties aggregated across blocks. The benchmark evaluates each sample independently, so the solver applies path-change penalties per-sample instead. This is a necessary adaptation because the benchmark's validity and scoring are per-sample.
- **Added satellites, not fixed constellations**: The papers assume a known fixed constellation. The benchmark provides a MEO backbone and asks the solver to augment it with LEO relays. The solver therefore adds a candidate-generation and candidate-selection stage that does not exist in the literature.
- **Node-degree caps are benchmark constraints**: The papers model arc capacities. The benchmark also enforces per-sample limits on how many links a satellite or endpoint may maintain. The solver adapts these as per-sample node capacities inside the SRR oracle, while retaining post-hoc repair as a defensive validity backstop.

## Solver Contract

```bash
./setup.sh
./solve.sh <case_dir> [config_dir] [solution_dir]
```

`setup.sh` validates that `brahe`, `numpy`, `yaml`, and SciPy HiGHS are available. Solver-local environment isolation is the intended deployment model; see [ENVIRONMENT_HANDOFF.md](./ENVIRONMENT_HANDOFF.md) for the remaining setup/solve script work.

`solve.sh` writes:

- `solution.json`: primary benchmark solution
- `status.json`: solver summary, timings, and reproduction disclosure
- `debug/*`: debug artifacts

The primary solution artifact is one JSON object with top-level `added_satellites` and `actions` arrays.

## Pipeline

The solver pipeline is:

1. **Load case** — Parse `manifest.json`, `network.json`, and `demands.json`.
2. **Generate candidates** — Build a deterministic orbit library from manifest constraints (altitude, inclination, RAAN, mean-anomaly grid).
3. **Propagate and build graphs** — Propagate all satellites (backbone + candidates) to routing-sample epochs using `brahe.NumericalOrbitPropagator`. Build per-sample communication graphs from ISL range, Earth occlusion, and ground-elevation geometry.
4. **Select candidates** — Evaluate each candidate's marginal contribution to demand connectivity using a Union-Find reachability proxy on a strided subset of samples. Select greedily up to the manifest limit.
5. **Rebuild graphs** — Rebuild per-sample graphs using only the selected satellites so that routing does not traverse unselected candidates.
6. **Build UMCF instances** — For each sample, enumerate k-shortest simple paths per commodity and build a UMCF instance with unit edge capacities plus endpoint/satellite node degree capacities.
7. **Solve path-restricted LP** — For each sample, solve a finite-path LP relaxation with per-commodity, edge-capacity, and node-degree constraints using SciPy HiGHS.
8. **Run SRR oracle** — For each sample, sort commodities by decreasing demand weight, assign paths via sequential randomized rounding from LP fractional values (or deterministic highest-probability selection), and track remaining edge and node capacities.
9. **Generate actions** — Extract edges from assigned paths, filter ground links against exact verifier elevation geometry, defensively repair any remaining per-sample degree-cap violations, compact consecutive samples into interval actions, and emit the benchmark JSON schema.

## Dependency And Backend Choices

- **Python 3.13** — The solver is intended to run from a solver-local environment managed behind `setup.sh` and `solve.sh`.
- **brahe** — Astrodynamics propagation (`NumericalOrbitPropagator`, J2 gravity, GCRF/ITRF frames, deterministic zero-valued static EOP provider). This matches the verifier's propagation model exactly.
- **NumPy** — Vectorized geometry for link feasibility, distance matrices, and elevation checks.
- **PyYAML** — Config parsing.
- **SciPy HiGHS** — Path-restricted LP relaxation backend via `scipy.optimize.linprog(method="highs")`.
- **No external graph library** — Path enumeration uses a custom Dijkstra + DFS implementation.

The solver intentionally does not add SciPy to the top-level project dependencies. The Phase 2 LP code is complete, but final solver-local environment wiring is tracked in [ENVIRONMENT_HANDOFF.md](./ENVIRONMENT_HANDOFF.md).

## Configuration

The solver reads optional config from `<config_dir>/config.yaml`.

See [config.example.yaml](./config.example.yaml) for a commented example.

Key knobs:

- `srr.deterministic` — When `true`, pick the highest-probability path deterministically instead of sampling. Makes the solver fully reproducible without multi-run aggregation.
- `srr.multi_run_count` — Number of independent seeded SRR runs. Keeps the assignment set with the highest total served commodity weight. Ignored when `deterministic` is `true`.
- `srr.seed` — Random seed base for stochastic rounding.
- `srr.k_paths` — Maximum number of shortest simple paths to consider per commodity.
- `srr.max_path_hops` — Maximum hop count for path enumeration.
- `srr.probability_source` — `"lp"` by default for reproduction mode; `"heuristic"` is available only as an ablation/fallback experiment.
- `srr.lp_backend` — LP backend identifier. The supported value is `"scipy-highs"`.
- `srr.lp_tolerance` — Numerical tolerance for interpreting LP fractional values.
- `srr.lp_path_cost_epsilon` — Optional small path-cost penalty in the LP objective; default `0.0`.
- `srr.path_change_penalty` — Boost factor for sticking with the same path across consecutive samples. Higher values reduce interval churn.
- `candidate_selection.policy` — `"greedy_marginal"`, `"no-added"`, or `"fixed"`.
- `candidate_selection.evaluation_sample_stride` — Sample stride for marginal evaluation (1 = every sample, 10 = every 10th).
- `candidate_selection.parallel_eval` — Opt-in flag for process-pool candidate evaluation. Not recommended at current scale because per-candidate work is too small to amortize fork/pickle/join overhead.

## Debug Artifacts

Written to `<solution_dir>/debug/`:

- `reproduction_summary.json` — Explicit mapping of paper components to implementation status (IMPLEMENTED, ADAPTED, PARTIAL, MISSING) with drift notes.
- `selected_candidates.json` — Candidate selection scores, policy, and per-iteration marginal contributions.
- `routed_potential_summary.json` — Full candidate selection debug.
- `umcf_instances.json` — Summary of UMCF instances per sample (commodities, edges, nodes).
- `lp_summary.json` — LP status counts, objective values, variable/constraint counts, solve time, and fractional-value diagnostics per sample.
- `srr_summary.json` — Served/dropped commodities, path changes, seed, probability source, timing, LP summary, node/edge capacity rejection counters, and approximation disclosure.
- `rounded_paths.json` — Per-sample, per-demand path chosen by SRR.
- `active_link_summary.json` — Edge counts before and after degree-cap repair for each sample.
- `action_summary.json` — Repair and compaction statistics.

These are useful for answering:

- why a particular candidate was selected or rejected
- how many commodities were dropped per sample
- whether path-change penalties reduced interval churn
- how much repair altered the edge set
- which paper components are approximated or omitted

## Running It

Direct setup:

```bash
./solvers/relay_constellation/umcf_srr_contact_plan/setup.sh
```

Direct solve on a public smoke case:

```bash
./solvers/relay_constellation/umcf_srr_contact_plan/solve.sh \
  benchmarks/relay_constellation/dataset/cases/test/case_0001
```

Direct solve with a config directory:

```bash
./solvers/relay_constellation/umcf_srr_contact_plan/solve.sh \
  benchmarks/relay_constellation/dataset/cases/test/case_0001 \
  /path/to/config_dir \
  /tmp/relay_umcf_solution
```

Official smoke verification through `main_solver`:

```bash
uv run python experiments/main_solver/run.py \
  --benchmark relay_constellation \
  --solver relay_constellation_umcf_srr_contact_plan \
  --case test/case_0001
```

Aggregate experiment results:

```bash
uv run python experiments/main_solver/aggregate.py
```

## Sanity Baseline

The papers report packet-loss and congestion metrics over simulated Telesat constellations, not the benchmark's `service_fraction`, `worst_demand_service_fraction`, and latency metrics. Treat the paper's performance claims as a rough sanity check for behavior, not as a target metric table for this benchmark.

What matters here is:

- official verification passes
- candidate counts are plausible
- repair does not collapse the link set
- service fraction improves over the backbone-only baseline
- randomized multi-run sometimes improves and sometimes degrades relative to deterministic mode

If service fraction looks unexpectedly low, inspect:

- candidate selection (are good candidates being filtered out?)
- SRR dropped commodities (are demands unservable due to graph sparsity?)
- repair aggressiveness (is degree-cap repair dropping too many edges?)
- ground-link geometry filter (are boundary samples being incorrectly removed?)

## Known Limitations

- This is a reproduction of the paper's method family, not a claim to reproduce every runtime or every table from the papers.
- LP relaxation is path-restricted to the finite k-shortest path set generated per sample. Column generation and dynamic LP recomputation are not yet implemented.
- Node-degree caps (`max_links_per_satellite`, `max_links_per_endpoint`) are modeled inside the oracle as per-sample node capacities, but this remains a benchmark adaptation rather than a direct paper component. Post-hoc repair is retained as a final validity backstop.
- The solver processes each sample independently. The Lamothe paper's path-sequence and block-based formulations, which optimize over sequences of time steps, are not implemented.
- Column generation and the associated pricing schemes are not implemented.
- The k-nearest first/last hop restriction studied in Grislain is not implemented.

## Compute Notes

- **Typical runtime**: approximately 13 seconds end-to-end on the smoke case (test/case_0001, 24 satellites, ~5760 routing samples).
- **Dominant stage**: orbit propagation at roughly 70% of runtime. Propagation is parallelized across satellites via `ProcessPoolExecutor`, yielding about a 9x speedup over single-threaded propagation.
- **Graph construction**: roughly 18% of runtime. Vectorized NumPy within each sample, sequential across samples.
- **Candidate selection**: roughly 9% of runtime after an optimization that replaced process-pool evaluation with a sequential loop. Process-pool candidate evaluation is available via config but not recommended at current scale.
- **SRR + action generation**: roughly 3% of runtime.
- **Recommended timeout**: 60 seconds for a single deterministic run; 300 seconds allows roughly 20 seeds for the randomized multi-run mode. The current 300-second experiment timeout is generous and fair.
- **LP backend**: SciPy HiGHS runs from the solver-local `.venv`. Re-profile before changing the registered timeout after dynamic/column-generation work.

## Reproduction Gap Summary

The following table maps paper components to their status in this solver. `IMPLEMENTED` means the element is present closely enough for the target claim. `ADAPTED` means it changed for benchmark reasons but still supports the claim. `PARTIAL` means it exists in simplified form. `MISSING` means it is absent and blocks full reproduction.

- **UMCF commodities and capacities**: ADAPTED — Commodities derived from benchmark demand windows. Edge capacities fixed to 1 (unit edge-disjoint), matching verifier allocation rather than flow-based capacities from the paper.
- **Unsplittable one-path-per-commodity constraint**: IMPLEMENTED — SRR assigns exactly one path per commodity per sample.
- **LP relaxation for fractional flows**: ADAPTED — SciPy HiGHS solves a path-restricted LP over each sample's finite k-shortest path set. Column generation is deferred.
- **SRR sequential rounding control flow**: IMPLEMENTED — Commodities processed in decreasing-weight order with edge-capacity updates plus benchmark-adapted node degree-cap updates.
- **Randomized rounding from LP solution**: IMPLEMENTED — Probabilities are normalized from LP relaxation values over currently feasible paths; heuristic mode remains only as an explicit ablation.
- **Node-degree cap modeling**: ADAPTED — Benchmark endpoint and satellite link limits are consumed as per-sample node capacities during SRR path feasibility and rounding. Post-hoc repair remains as a validity backstop.
- **k-shortest path restriction**: IMPLEMENTED — k=4 shortest simple paths by hop count then distance.
- **Dynamic path-change penalty**: ADAPTED — Per-sample boost to the previous path instead of the paper's per-block MILP objective term.
- **k-nearest first/last hop restriction**: MISSING — Not implemented.
- **Path-sequence / arc-path / arc-node formulations**: MISSING — None of the MILP formulations from Lamothe are implemented.
- **Column generation pricing**: MISSING — No column generation or pricing schemes are used.
- **Candidate orbit library**: IMPLEMENTED — Deterministic grid generated from manifest constraints. Solver-local addition, not from the papers.
- **Greedy marginal candidate selection**: IMPLEMENTED — Union-Find reachability proxy. Solver-local heuristic, not from the papers.
- **Degree-cap repair and interval compaction**: IMPLEMENTED — Defensive post-hoc repair and compaction are benchmark adaptations.

## Evidence Type

This solver is registered in `experiments/main_solver` with `evidence_type: reproduced_solver`.
