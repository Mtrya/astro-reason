# UMCF/SRR Contact-Plan Solver

Runnable reproduced solver for `relay_constellation` based on Unsplittable Multi-Commodity Flow (UMCF) with Sequential Randomized Rounding (SRR).

The solver follows the method family described by Grislain et al. and Lamothe et al., adapted to the benchmark's public case and solution contract. It reads benchmark case files and writes benchmark solution JSON without importing benchmark, experiment, runtime, or other solver internals.

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
  author={Lamothe, Fran{\c{c}}ois and Rachelson, Emmanuel and Ha{\"i}t, Alain and Baudoin, C{\'e}dric and Dup{\'e}, Jean-Baptiste},
  journal={Computers \& Operations Research},
  volume={152},
  pages={106154},
  year={2023},
  publisher={Elsevier},
  doi={10.1016/j.cor.2023.106154}
}
```

## Method Summary

Grislain et al. use UMCF routing to assign each demand to one unsplittable path while accounting for congestion. Lamothe et al. extend UMCF to dynamic graphs with path-change penalties and SRR heuristics.

This benchmark adaptation uses UMCF/SRR as a solver-local contact-planning oracle:

- generate a deterministic candidate orbit library inside case constraints
- greedily select candidate relays by marginal routed-service potential
- propagate the backbone plus selected relays on the routing grid
- build one dynamic communication graph per sample
- enumerate a finite k-shortest path set per active demand
- solve a path-restricted LP relaxation with SciPy HiGHS
- round LP fractional path values with SRR while tracking edge and node capacities
- convert rounded paths into verifier-compatible interval link actions

The benchmark verifier owns final routing, allocation, validity checks, and metrics. The solver submits only `added_satellites` and interval `actions`.

## Benchmark Adaptation

Important adaptations from the papers:

- The papers route on fixed constellations. This solver adds a benchmark-specific candidate-generation and candidate-selection layer because `relay_constellation` asks for bounded relay augmentation.
- The papers can output routes or route choices. This benchmark accepts only link activations, so UMCF/SRR paths are converted into active link intervals and the verifier reroutes independently.
- The verifier uses unit-capacity edge-disjoint routing. The solver's LP and SRR oracle use unit edge capacities to match that allocation model.
- The benchmark enforces per-sample endpoint and satellite degree caps. The solver models those caps as node capacities inside LP/SRR and keeps post-hoc repair as a validity backstop.
- Lamothe's dynamic formulations optimize over path sequences or time blocks. The solver uses one LP per routing sample and applies path-change preference as a per-sample rounding boost.

## Solver Contract

```bash
./setup.sh
./solve.sh <case_dir> [config_dir] [solution_dir]
```

`setup.sh` verifies project-provided base dependencies and creates a solver-local `.venv` for SciPy HiGHS. Solver-specific dependencies are intentionally not added to the top-level project environment.

`solve.sh` writes:

- `solution.json`: primary benchmark solution
- `status.json`: solver summary, timings, selected profile, and compute-envelope disclosure
- `debug/*`: solver-local diagnostics

## Promoted Configuration

The canonical evaluated configuration is owned by:

```text
experiments/main_solver/solvers/relay_constellation_umcf_srr_contact_plan.yaml
```

The promoted public profile is `reproduction`:

- 64 generated candidate satellites
- deterministic SRR
- one LP solve per sample
- SciPy HiGHS path-restricted LP relaxation
- k=4 shortest simple paths per commodity
- hop-count LP path-cost epsilon `1.0e-4`
- unrestricted first/last ingress and egress satellite choice
- greedy marginal candidate selection on strided samples
- 300 second solver timeout

The larger 128-candidate stochastic quality setting was used only for calibration. It verified on `case_0001` and `case_0002`, but used about 3.6-3.8 GiB peak RSS and exceeded the practical full-matrix budget on `case_0002` when measured with harness overhead. It is not the promoted profile.

See [config.example.yaml](./config.example.yaml) for a direct-run example matching the promoted profile.

## Pipeline

1. Load `manifest.json`, `network.json`, and `demands.json`.
2. Generate a deterministic candidate relay library.
3. Propagate backbone and candidate satellites with Brahe on the routing grid.
4. Build all-candidate sample graphs.
5. Select candidates with a deterministic greedy marginal reachability proxy.
6. Rebuild sample graphs using only the selected candidates.
7. Build per-sample UMCF instances from active demands.
8. Solve path-restricted LP relaxations and run SRR.
9. Filter, repair, compact, and emit interval actions.

## Dependency And Backend Choices

- Python 3.13
- Brahe for propagation, matching the verifier's J2-only deterministic model
- NumPy for vectorized geometry
- PyYAML for config parsing
- SciPy HiGHS for LP relaxation through solver-local setup
- No external graph library

## Debug Artifacts

The solver writes debug artifacts under `<solution_dir>/debug/`, including:

- `compute_envelope.json`
- `scale_diagnostics.json`
- `selected_candidates.json`
- `routed_potential_summary.json`
- `umcf_instances.json`
- `lp_summary.json`
- `srr_summary.json`
- `rounded_paths.json`
- `active_link_summary.json`
- `action_summary.json`
- `oracle_drift_diagnostics.json`
- `reproduction_summary.json`

These artifacts disclose candidate scale, graph scale, LP size and status, SRR decisions, repair impact, oracle-versus-verifier drift risk, and the paper-component mapping.

## Running It

Direct setup:

```bash
./solvers/relay_constellation/umcf_srr_contact_plan/setup.sh
```

Direct solve on a public case:

```bash
./solvers/relay_constellation/umcf_srr_contact_plan/solve.sh \
  benchmarks/relay_constellation/dataset/cases/test/case_0001
```

Official reproduced-solver run through `main_solver`:

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

## Reported Evidence

Current reported evidence uses the experiment-owned `reproduction` profile. Fresh canonical artifacts exist for `test/case_0001` and `test/case_0002`.

| case | valid | service_fraction | worst_demand_service_fraction | mean_latency_ms | added satellites | candidates | solve_s | peak RSS |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `test/case_0001` | true | 0.9240740741 | 0.5444444444 | 165.009 | 6 | 64 | 69.245 | ~1.35 GiB |
| `test/case_0002` | true | 0.9511904762 | 0.6666666667 | 125.338 | 5 | 64 | 73.512 | ~1.46 GiB |

Backbone-only calibration was also run on all five test cases to confirm that the added relay layer materially improves service. The quality calibration verified on the first two cases, but is not promoted because its memory and wall-time profile is too heavy for the current fair full-matrix envelope.

## Reproduction Gap Summary

- **UMCF commodities and capacities**: ADAPTED. Commodities derive from benchmark demand windows; edge capacities are unit capacities matching verifier allocation.
- **Unsplittable one-path-per-commodity constraint**: IMPLEMENTED. SRR assigns at most one path per commodity per sample.
- **LP relaxation for fractional flows**: ADAPTED. SciPy HiGHS solves a finite path-restricted LP over per-sample k-shortest path sets.
- **SRR sequential rounding control flow**: IMPLEMENTED. Commodities are processed in decreasing-weight order with capacity updates after fixation.
- **Randomized rounding from LP solution**: IMPLEMENTED. LP fractional path values drive SRR probabilities; deterministic mode selects the highest-probability feasible path.
- **Node-degree cap modeling**: ADAPTED. Benchmark degree caps are consumed as node capacities inside LP/SRR and checked again during repair.
- **k-shortest path restriction**: IMPLEMENTED. The promoted profile uses k=4 shortest simple paths by hop count and distance.
- **Dynamic path-change penalty**: ADAPTED. The solver applies a per-sample previous-path probability boost rather than Lamothe's block-level objective term.
- **k-nearest first/last hop restriction**: PARTIAL. The option exists through `first_last_hop_k`, but the promoted profile leaves it unrestricted because calibration did not identify it as the strongest setting.
- **Path-sequence, arc-path, and arc-node MILP formulations**: MISSING. These are not implemented.
- **Column generation and pricing**: MISSING. The LP is path-restricted to the generated finite path set.
- **LP re-actualization during rounding**: MISSING. The solver solves once per sample before SRR.
- **Candidate orbit library and greedy marginal selection**: IMPLEMENTED as benchmark adaptations, not paper components.
- **Degree-cap repair and interval compaction**: IMPLEMENTED as benchmark adaptations.

## Known Limitations

- This is a benchmark-adapted reproduction of the UMCF/SRR method family, not a reproduction of every table, simulator assumption, or dynamic formulation in the papers.
- Candidate selection uses a reachability proxy and does not solve UMCF for every candidate marginal evaluation.
- The verifier may route differently from the solver-local SRR oracle because routes are not submitted.
- Full dynamic path-sequence optimization, column generation, and LP re-actualization remain outside the promoted profile.
- The promoted profile is the strongest currently practical full-matrix-oriented configuration. The larger quality calibration is evidence, not the public default.

## Evidence Type

This solver is registered in `experiments/main_solver` with `evidence_type: reproduced_solver`.
