# UMCF/SRR Contact-Plan Solver

This solver implements an internal oracle based on the Unsplittable Multi-Commodity Flow (UMCF) problem with Sequential Randomized Rounding (SRR) for the `relay_constellation` benchmark.

## Method Overview

The solver follows a three-stage pipeline:

1. **Candidate Selection** — Greedy marginal scoring with a Union-Find reachability proxy selects added satellites from a deterministic orbit library.
2. **Internal UMCF/SRR Oracle** — For each routing sample, an internal UMCF instance is built from the dynamic communication graph. The SRR heuristic assigns one unsplittable path per active demand commodity, tracking unit edge capacities.
3. **Action Generation** — SRR paths are converted into interval-based link actions. A deterministic repair step enforces per-sample degree caps, and a geometry filter tightens ground links against the exact verifier elevation model before compaction.

## Execution Model

- **Language**: Pure Python 3.13, single-threaded.
- **Geometry**: Vectorised NumPy for orbital propagation, link geometry, and graph construction.
- **Path Generation**: Custom Dijkstra + DFS enumeration (no external graph library).
- **Rounding**: Sequential, demand-sorted, capacity-tracking heuristic.
- **Parallelism**: ProcessPoolExecutor used only for candidate evaluation and orbit propagation. The UMCF/SRR oracle and action generation are sequential per sample.
- **No compiled extensions or external solvers** are used in the oracle.

## Action Generation Pipeline

After the SRR oracle produces per-sample path assignments:

1. **Extract** — Collect all canonical edges used by SRR paths and the samples at which they are active.
2. **Geometry Filter** — Remove ground-link samples that fail the exact brahe elevation check (the fast vectorised approximation used during graph construction can differ at boundary samples).
3. **Repair** — For each sample, count per-node active degree. If a node exceeds its cap (`max_links_per_satellite` or `max_links_per_endpoint`), drop the lowest-importance incident edges until the cap is satisfied. Importance is the maximum commodity weight of any demand whose path uses that edge.
4. **Compact** — Merge consecutive samples for each edge into interval actions with grid-aligned `start_time` and `end_time`.
5. **Emit** — Convert actions to the benchmark JSON schema and write `solution.json`.

## Approximation & Reproduction Gaps

| Component | Status | Notes |
|-----------|--------|-------|
| LP relaxation for fractional flows | **MISSING** | Heuristic uniform probabilities used instead of an LP solver. Room left for an optional LP backend. |
| Path-set restriction | **IMPLEMENTED** | k-shortest simple paths by hop count then distance (default k=4). |
| SRR control flow | **IMPLEMENTED** | Commodities sorted by decreasing demand; sequential rounding with capacity updates. |
| Dynamic path-change penalty | **ADAPTED** | Per-sample boost to previous path; Lamothe formulation uses per-block penalties. |
| Node-degree modeling in oracle | **PARTIAL** | Degree caps tracked as node capacities but not consumed during internal rounding (they are action-level constraints). |
| Action geometry pre-validation | **IMPLEMENTED** | Exact brahe elevation filter removes boundary-mismatch samples before compaction. |

## Debug Artifacts

Written to `<solution_dir>/debug/`:

- `umcf_instances.json` — Summary of UMCF instances (commodities per sample, edges, nodes).
- `srr_summary.json` — Served/dropped commodities, path changes, seed, timing, approximation disclosure.
- `selected_candidates.json` — Candidate selection scores and policy.
- `routed_potential_summary.json` — Full candidate selection debug.
- `action_summary.json` — Repair and compaction statistics.

## Configuration

The solver reads `config.yaml` from the optional `config_dir`. Candidate selection policy and SRR parameters can be exposed there in future iterations.

## Entry Points

- `setup.sh` — Validates dependencies (`brahe`, `numpy`, `yaml`).
- `solve.sh <case_dir> [config_dir] [solution_dir]` — Runs the solver.
