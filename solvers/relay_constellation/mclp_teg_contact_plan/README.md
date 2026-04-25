# MCLP+TEG Relay Solver

A deterministic solver for the `relay_constellation` benchmark that combines:

1. **MCLP candidate selection** — selects additional relay satellites from a finite orbit library to maximize demand-window coverage potential.
2. **TEG contact scheduling** — per-sample link selection with interval compaction, producing `ground_link` and `inter_satellite_link` actions.

The solver is standalone. It reads benchmark case files and writes a benchmark solution JSON, but it does not import or execute benchmark, experiment, runtime, or other solver internals.

## Citation

This solver reproduces methods from two paper families:

**Rogers et al.** — constellation configuration design via the Maximal Covering Location Problem (MCLP):

```bibtex
@misc{rogers2026optimalsatelliteconstellationconfiguration,
  title={Optimal Satellite Constellation Configuration Design: A Collection of Mixed Integer Linear Programs},
  author={David O. Williams Rogers and Dongshik Won and Dongwook Koh and Kyungwoo Hong and Hang Woon Lee},
  year={2026},
  eprint={2507.09855},
  archivePrefix={arXiv},
  primaryClass={math.OC},
  doi={https://doi.org/10.2514/1.A36518},
  url={https://arxiv.org/abs/2507.09855},
}
```

**Gerard et al.** — time-expanded graph (TEG) contact-plan scheduling for optical networks:

```bibtex
@misc{gerard2026contactplandesignoptical,
  title={Contact Plan Design For Optical Interplanetary Communications},
  author={Jason Gerard and Juan A. Fraire and Sandra Cespedes},
  year={2026},
  eprint={2601.18148},
  archivePrefix={arXiv},
  primaryClass={cs.NI},
  url={https://arxiv.org/abs/2601.18148},
}
```

## Method Summary

### Rogers layer — MCLP candidate selection

The paper formulates constellation configuration as a family of MILPs. The MCLP variant selects a fixed number of orbital slots to maximize observation rewards over targets.

This reproduction keeps that structure and adapts it to `relay_constellation`:

- **Finite orbital slot library** (`orbit_library.py`) — deterministic grid of candidate orbits within case altitude, inclination, eccentricity, and RAAN bounds. Default: 2 altitude shells × 2 inclination bands × 3 RAAN planes × 2 phase slots = 24 candidates.
- **Cardinality constraint** — selects up to `max_added_satellites` (benchmark upper bound), not an exact fixed number.
- **Coverage reward scoring** — each candidate is scored by its marginal contribution to demand-window service potential (the set of demand-samples that become reachable when the candidate is added).
- **Greedy selection** — iterative marginal-gain heuristic that adds the highest-scoring candidate until the budget is exhausted or marginal gain drops to zero.
- **Optional small MILP** — when candidates ≤ 20 and `max_added_satellites` ≤ 5, a PuLP/CBC MILP solves the exact MCLP over the simplified coverage matrix. Falls back to greedy if the MILP is too large or fails.

### Gerard layer — TEG contact scheduling

The paper introduces a time-expanded graph contact-plan scheduler for optical interplanetary networks, with per-sample link selection, degree-cap constraints, and both greedy and MILP solvers.

This reproduction keeps that structure and adapts it to `relay_constellation`:

- **Time-expanded graph representation** — feasibility of every ground link and inter-satellite link is precomputed at every routing sample (default 60 s step) over the full horizon.
- **Per-sample greedy max-weight matching** — at each sample, feasible links are scored by active demand weight, then selected greedily respecting per-satellite and per-endpoint degree caps.
- **Interval compaction** — consecutive samples with the same link selected are merged into compact interval actions.
- **Bounded per-sample MILP** — for small problems (≤ 50 samples with links, ≤ 500 total binary variables), a PuLP/CBC MILP selects links at each sample to maximize total utility. Falls back to greedy if bounds are exceeded or the solver fails.
- **Degree-cap enforcement** — both greedy and MILP respect `max_links_per_satellite` and `max_links_per_endpoint`.

## Benchmark Adaptation

The original papers target different mission contexts. The following adaptations bridge paper methods to the benchmark contract:

| Paper Concept | Benchmark Adaptation |
|---------------|----------------------|
| Rogers observation reward (coverage over targets) | Demand-window service-potential score (path diversity via ground + ISL connectivity) |
| Rogers fixed cardinality N (exactly N satellites) | `max_added_satellites` upper bound (`<= K`) |
| Gerard capacity objective (maximize temporal flow) | Action-interval generator (ground_link and inter_satellite_link intervals) |
| Gerard retargeting delay (pointing/acquisition overhead) | **Not modeled** — benchmark assumes instant link switching |
| Gerard route tables and DTN forwarding | **Not modeled** — benchmark verifier owns route allocation and latency scoring |
| Rogers MILP over full candidate set | Greedy marginal-gain heuristic with optional small MILP for ≤20 candidates |
| Gerard full-horizon MILP scheduler | Bounded per-sample MILP with deterministic greedy fallback |

## Solver Contract

```bash
./setup.sh
./solve.sh <case_dir> [config_dir] [solution_dir]
```

`setup.sh` prepares the solver-local virtual environment (effectively a no-op when dependencies are already present).

`solve.sh` writes:

- `solution.json`: primary benchmark solution (`added_satellites`, `actions`)
- `status.json`: solver summary, stage timings, execution model, and compute budget
- `debug/*`: optional debug artifacts

The primary solution artifact is one JSON object with top-level `added_satellites` and `actions` arrays.

## Configuration

The solver reads optional config from `<config_dir>/config.json`. See [config.example.json](./config.example.json) for a commented example.

Key knobs:

| Key | Values | Default | Description |
|-----|--------|---------|-------------|
| `mclp_mode` | `"auto"`, `"greedy"`, `"milp"`, `"none"` | `"auto"` | Candidate selection strategy. `"none"` skips MCLP and uses backbone only. `"auto"` tries MILP for small problems and falls back to greedy. |
| `scheduler_mode` | `"auto"`, `"greedy"`, `"milp"` | `"auto"` | Contact scheduling strategy. `"auto"` tries MILP within bounds, falls back to greedy. |
| `parallel_mode` | `"auto"`, `"parallel"`, `"sequential"` | `"auto"` | Execution model. `"auto"` uses process parallelism when there are multiple satellites or >1000 samples. |
| `time_budget_s` | positive number | `300` | Expected per-case compute budget in seconds. Informational; the solver does not hard-cut at this limit. |
| `orbit_grid.altitude_step_m` | number or `null` | `null` | Altitude grid step in meters. `null` uses min and max altitude only (2 shells). |
| `orbit_grid.inclination_step_deg` | number or `null` | `null` | Inclination grid step in degrees. `null` uses min and max inclination only (2 bands). |
| `orbit_grid.num_raan_planes` | integer | `3` | Number of RAAN planes to distribute candidates across. |
| `orbit_grid.num_phase_slots` | integer | `2` | Number of phase slots per RAAN plane. |
| `milp_config.max_total_variables` | integer | `500` | Maximum total binary variables across all samples for scheduler MILP. |
| `milp_config.max_samples` | integer | `50` | Maximum number of samples that may use MILP in scheduler. |
| `milp_config.milp_time_limit_per_sample` | number | `5.0` | Time limit in seconds per sample for scheduler MILP. |

`time_budget_s` is informational and does not hard-cut the solver. It is recorded in `status.json` for reproducibility tracking.

Parallel execution does not change algorithmic results; it only reduces wall-clock time.

## Debug Artifacts

When `debug: true` (or when the solver encounters an error), the solver writes:

- `debug/candidates.json` — orbital elements of all generated candidates
- `debug/link_cache_summary.json` — counts of feasible links by type and endpoint
- `debug/mclp_summary.json` — reward scores and selection decisions
- `debug/teg_summary.json` — scheduler statistics (samples processed, links selected, intervals created)
- `debug/milp_summary.json` — MILP solver logs when MILP modes are active
- `debug/reproduction_summary.json` — paper component mapping and benchmark adaptation notes

These are useful for answering:

- why a candidate was selected or skipped
- whether the link cache covers expected demand windows
- why MILP modes fell back to greedy
- whether parallel execution was used and if any fallback occurred
- how paper methods map to solver components

## Running It

Direct setup:

```bash
./solvers/relay_constellation/mclp_teg_contact_plan/setup.sh
```

Direct solve on a public smoke case:

```bash
./solvers/relay_constellation/mclp_teg_contact_plan/solve.sh \
  benchmarks/relay_constellation/dataset/cases/test/case_0001
```

Direct solve with a config directory:

```bash
./solvers/relay_constellation/mclp_teg_contact_plan/solve.sh \
  benchmarks/relay_constellation/dataset/cases/test/case_0001 \
  /path/to/config_dir \
  /tmp/relay_mclp_solution
```

Official smoke verification through `main_solver`:

```bash
uv run python experiments/main_solver/run.py \
  --benchmark relay_constellation \
  --solver relay_mclp_teg \
  --case test/case_0001
```

Aggregate experiment results:

```bash
uv run python experiments/main_solver/aggregate.py
```

## Compute Envelope

This solver is a planning method that propagates satellites over a 96-hour horizon and evaluates link feasibility at 60-second granularity. A fair evaluation should allow **at least 5 minutes (300 s) per case**.

With `parallel_mode=auto` the solver uses all available CPU cores for:

- **Satellite propagation** — embarrassingly parallel across satellites (dominant stage, ~4 s per satellite sequentially).
- **Link-feasibility cache** — chunked by sample index across worker processes.

## Sanity Baseline

The Rogers paper reports coverage fractions over target sets; the Gerard paper reports network capacity and duty cycle for optical interplanetary networks. Neither paper reports benchmark `service_fraction`, `worst_demand_service_fraction`, or `mean_latency_ms`. Treat the paper metrics as rough sanity checks for method behavior, not as target metric tables for this benchmark.

What matters here is:

- official verification passes
- greedy MCLP improves over the no-added backbone baseline
- candidate counts are plausible
- MILP fallback is deterministic and well-documented

If greedy MCLP does not improve over no-added, inspect:
- whether the candidate grid covers the orbital regions the verifier expects
- whether degree-cap repair or overlap issues are present
- whether the reward construction matches verifier route rules

## Known Limitations

- This is a reproduction of the papers' method families, not a claim to reproduce every runtime or every table.
- **Coarse candidate grid**: default 24 candidates is much smaller than Rogers' hundreds-to-thousands. This is configurable via `orbit_grid` but trades fidelity for compute time.
- **Greedy MCLP**: the default greedy selector is not guaranteed optimal. The optional MILP mode is exact but bounded to small instances.
- **Per-sample MILP scheduler**: solves each sample independently, not a full-horizon MILP as in Gerard. This is a scalability adaptation.
- **No retargeting delay**: benchmark does not model optical PAT overhead, so the solver does not account for it.
- **Verifier-owned routing**: the solver cannot influence which routes the verifier chooses. High link utility does not guarantee high verifier service fraction if the verifier selects different paths.
- **MILP scheduler scaling**: the bounded MILP scheduler falls back to greedy on all public cases because the problem exceeds the default variable/sample bounds. This is expected behavior consistent with Gerard's observation that MILP hits timeout around 16 nodes.

## Evidence Type

This solver is registered in `experiments/main_solver` with `evidence_type: reproduced_solver`.
