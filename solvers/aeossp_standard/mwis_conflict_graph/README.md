# AEOSSP MWIS Conflict-Graph Solver

This solver is a runnable reproduced solver for `aeossp_standard`.

It follows the method family described by Duncan Eddy and Mykel J.Kochenderfer in "A Maximum Independent Set Method for Scheduling Earth Observing Satellite Constellations", adapted to the benchmark's public case and solution contract.

The solver is standalone. It reads benchmark case files and writes a benchmark
solution JSON, but it does not import or execute benchmark, experiment, runtime, or other solver internals.

## Method Summary

The paper models candidate image collects as vertices in a sparse infeasibility
graph:

- each vertex is one candidate observation
- each edge means the two observations cannot both appear in the schedule
- a schedule is an independent set of non-adjacent vertices

This reproduction keeps that structure and adapts it to `aeossp_standard`:

- vertex: one grid-aligned `(satellite_id, task_id, start_time, end_time)`  observation candidate
- vertex weight: task weight
- duplicate-task edge: any pair of candidates with the same `task_id`, including across satellites
- same-satellite overlap edge: two observations overlap in time
- same-satellite transition edge: the later observation does not leave enough slew-plus-settle time after the earlier one

For small connected components, the solver searches exactly. For larger components, it builds deterministic greedy seeds, improves them with bounded local search, and refines the best incumbents with bounded recombination.

## Benchmark Adaptation

The benchmark differs from the paper in a few important ways:

- The benchmark ranks by valid first, then `WCR`, `CR`, `TAT`, and `PC`, so the solver uses weighted selection rather than pure collect count.
- Observation actions must be exactly aligned to the public action grid and must match each task's exact duration.
- Slew feasibility uses the benchmark's scalar bang-coast-bang plus settling semantics rather than the paper's simpler constant-rate picture.
- Battery is not naturally pairwise, so it is not encoded as graph edges. Instead, the solver performs solver-local validation and bounded repair after graph selection.

That means this solver reproduces the paper's graph-and-search approach, while remaining faithful to the benchmark's public validity contract.

## Solver Contract

```bash
./setup.sh
./solve.sh <case_dir> [config_dir] [solution_dir]
```

`setup.sh` is effectively a no-op when using the project environment.

`solve.sh` writes:

- `solution.json`: primary benchmark solution
- `status.json`: solver summary, timings, and local validation details
- `debug/*`: optional debug artifacts when `debug: true`

The primary solution artifact is one JSON object with a top-level `actions` array of `observation` actions.

## Search And Repair

The solver pipeline is:

1. Load `mission.yaml`, `satellites.yaml`, and `tasks.yaml`.
2. Generate grid-aligned observation candidates that satisfy sensor matching, task windows, observation geometry, and first-action slew feasibility.
3. Build a sparse conflict graph from duplicate-task, overlap, and transition conflicts.
4. Solve each connected component:
   - exact search on small components
   - deterministic greedy seeding on larger components
   - bounded local improvement with insertions and weighted 2-swaps
   - bounded recombination of incumbents on larger components
5. Decode the selected candidates into observation actions.
6. Run solver-local validation and bounded repair to remove any remaining local issues, especially battery depletion risk.

The repair stage is intentionally conservative. It keeps the solver standalone and reduces official verifier failures without claiming that battery feasibility is fully proven by the graph itself.

## Configuration

The solver reads optional config from either:

- `<config_dir>/config.yaml`
- `<config_dir>/config.yml`
- `<config_dir>/config.json`
- `<config_dir>/mwis_conflict_graph.yaml`
- `<config_dir>/mwis_conflict_graph.yml`
- `<config_dir>/mwis_conflict_graph.json`

See [config.example.yaml](./config.example.yaml) for a commented example.

Key knobs:

- `candidate_stride_multiplier`
- `max_candidates`
- `max_candidates_per_task`
- `selection_policy`
- `max_exact_component_size`
- `max_local_passes`
- `population_size`
- `recombination_rounds`
- `time_limit_s`
- `max_repair_iterations`
- `debug`

`time_limit_s` only bounds the incumbent-refinement search on large components. It does not cap candidate generation, graph construction, or local validation. If the time budget is reached, the solver returns the best incumbent found so far and still performs local validation and repair.

## Debug Artifacts

When `debug: true`, the solver writes:

- `debug/candidate_summary.json`
- `debug/graph_summary.json`
- `debug/solver_summary.json`
- `debug/component_search.json`
- `debug/repair_log.json`
- `debug/candidates.json`
- `debug/selected_candidates.json`
- `debug/repaired_candidates.json`

These are useful for answering:

- why a task has zero candidates
- how dense the conflict graph is
- which search path produced the incumbent
- whether a time budget stopped refinement
- why a candidate was removed during local repair

## Running It

Direct setup:

```bash
./solvers/aeossp_standard/mwis_conflict_graph/setup.sh
```

Direct solve on a public smoke case:

```bash
./solvers/aeossp_standard/mwis_conflict_graph/solve.sh \
  benchmarks/aeossp_standard/dataset/cases/test/case_0001
```

Direct solve with a config directory:

```bash
./solvers/aeossp_standard/mwis_conflict_graph/solve.sh \
  benchmarks/aeossp_standard/dataset/cases/test/case_0001 \
  /path/to/config_dir \
  /tmp/aeossp_mwis_solution
```

Official smoke verification through `main_solver`:

```bash
uv run python experiments/main_solver/run.py \
  --benchmark aeossp_standard \
  --solver aeossp_standard_mwis_conflict_graph \
  --case test/case_0001
```

Aggregate experiment results:

```bash
uv run python experiments/main_solver/aggregate.py
```

## Sanity Baseline

The paper reports scheduled-collect counts, not benchmark `WCR`, `CR`, `TAT`, or `PC`. Treat the paper's collect fractions as a rough sanity check for completion behavior, not as a target metric table for this benchmark.

What matters here is:

- official verification passes
- candidate counts are plausible
- repair does not collapse the schedule
- weighted completion remains strong on public cases

If raw graph selection looks strong but repair removes many actions, inspect the local battery model, transition gap logic, and candidate generation before tuning the search policy.

## Known Limitations

- This is a reproduction of the paper's method family, not a claim to reproduce every runtime or every table from the paper.
- The solver does not call an external ReduMIS binary and does not implement the paper's reduction rules.
- Battery feasibility is handled by solver-local validation and repair instead of being fully encoded as graph conflicts.
- Full multi-case tuning may be more practical on a server than on a development laptop.

## Evidence Type

This solver is registered in `experiments/main_solver` with `evidence_type: reproduced_solver`.
