# AEOSSP Greedy-LNS Solver

This solver is a runnable reproduced solver for `aeossp_standard`.

It follows the acquisition-planning method described by Vincent Antuori, Damien Wojtowicz, and Emmanuel Hebrard in "Solving the Agile Earth Observation Satellite Scheduling Problem with CP and Local Search", adapted to the benchmark's public case and solution contract.

## Citation

```bibtex
@inproceedings{antuori2025solving,
  title={Solving the Agile Earth Observation Satellite Scheduling Problem with CP and Local Search},
  author={Antuori, Vincent and Wojtowicz, Damien and Hebrard, Emmanuel},
  booktitle={31st International Conference on Principles and Practice of Constraint Programming (CP 2025)},
  series={Leibniz International Proceedings in Informatics},
  volume={340},
  pages={3:1--3:18},
  year={2025},
  doi={10.4230/LIPIcs.CP.2025.3}
}
```

The solver is standalone. It reads benchmark case files and writes a benchmark solution JSON, but it does not import or execute benchmark, experiment, runtime, or other solver internals.

## Method Summary

The paper decomposes agile Earth-observation scheduling into acquisition planning and download planning. This reproduction keeps the acquisition side and adapts it to `aeossp_standard`:

- **Candidate**: one grid-aligned `(satellite_id, task_id, start_time, end_time)` observation that satisfies sensor matching, task window, geometry, and initial slew feasibility.
- **Utility**: task `weight / duration` by default, with deterministic tie-breaks for higher weight, earlier due time, lower transition increment, and candidate id.
- **Greedy insertion**: candidates are processed in descending utility order; each candidate is inserted into its satellite's schedule if it does not overlap an existing action, violate transition gaps, or duplicate an already scheduled task.
- **Connected-component local search**: the solver builds a same-satellite dependence graph from overlap and transition edges, extracts connected components, and repeatedly attempts to improve the incumbent by removing all selected candidates in one component and reinserting them via marginal-profit greedy ordering against the current global selection.
- **Repair**: solver-local validation checks the final schedule for overlap, transition, initial slew, duplicate task, and battery issues; any violations are resolved by iteratively removing the lowest-utility violating candidate.

## Benchmark Adaptation

The benchmark differs from the paper in a few important ways:

- The benchmark ranks by valid first, then `WCR`, `CR`, `TAT`, and `PC`, so the solver uses weighted selection rather than pure collect count.
- Observation actions must be exactly aligned to the public action grid and must match each task's exact duration.
- Slew feasibility uses the benchmark's scalar bang-coast-bang plus settling semantics rather than the paper's time-independent transition matrix.
- Battery is not naturally pairwise, so it is not encoded in the dependence graph. Instead, the solver performs solver-local validation and bounded repair after greedy insertion and local search.
- The benchmark is observation-only; download and memory planning are out of scope.

That means this solver reproduces the paper's greedy construction and connected-component local-search approach, while remaining faithful to the benchmark's public validity contract.

## Solver Contract

```bash
./setup.sh
./solve.sh <case_dir> [config_dir] [solution_dir]
```

`setup.sh` is effectively a no-op when using the project environment.

`solve.sh` writes:

- `solution.json`: primary benchmark solution
- `status.json`: solver summary, timings, reproduction notes, and local validation details
- `debug/*`: optional debug artifacts when `debug: true`

The primary solution artifact is one JSON object with a top-level `actions` array of `observation` actions.

## Pipeline

The solver pipeline is:

1. Load `mission.yaml`, `satellites.yaml`, and `tasks.yaml`.
2. Generate grid-aligned observation candidates that satisfy sensor matching, task windows, observation geometry, and first-action slew feasibility.
3. Build a deterministic greedy schedule by inserting candidates in descending utility order.
4. Improve the schedule with first-improving connected-component local search using marginal-profit recomputation.
5. Run solver-local validation and bounded repair to remove any remaining issues, especially battery depletion risk.

The repair stage is intentionally conservative. It keeps the solver standalone and reduces official verifier failures without claiming that battery feasibility is fully proven by the greedy/LNS core.

## Configuration

The solver reads optional config from either:

- `<config_dir>/config.yaml`
- `<config_dir>/config.yml`
- `<config_dir>/config.json`
- `<config_dir>/greedy_lns.yaml`
- `<config_dir>/greedy_lns.yml`
- `<config_dir>/greedy_lns.json`

See [config.example.yaml](./config.example.yaml) for a commented example.

Key knobs:

- `candidate_stride_multiplier`
- `max_candidates`
- `max_candidates_per_task`
- `minimize_transition_increment`
- `max_local_search_iterations`
- `max_local_search_time_s`
- `restart_count`
- `random_seed`
- `stochastic_ordering`
- `max_repair_iterations`
- `debug`

`max_local_search_time_s` only bounds the local-search loop. It does not cap candidate generation or local validation. If the time budget is reached, the solver returns the best incumbent found so far and still performs local validation and repair.

## Debug Artifacts

When `debug: true`, the solver writes:

- `debug/candidate_summary.json`
- `debug/candidates.json`
- `debug/insertion_stats.json`
- `debug/local_search_stats.json`
- `debug/component_summary.json`
- `debug/validation_summary.json`
- `debug/repair_log.json`
- `debug/repaired_candidates.json`

These are useful for answering:

- why a task has zero candidates
- how many candidates were greedily inserted and why others were skipped
- how dense the per-satellite dependence graph is
- which local-search moves were accepted or rejected
- whether a time budget stopped search
- why a candidate was removed during local repair
- how local validity changed from pre-repair to post-repair

## Running It

Direct setup:

```bash
./solvers/aeossp_standard/greedy_lns/setup.sh
```

Direct solve on a public smoke case:

```bash
./solvers/aeossp_standard/greedy_lns/solve.sh \
  benchmarks/aeossp_standard/dataset/cases/test/case_0001
```

Direct solve with a config directory:

```bash
./solvers/aeossp_standard/greedy_lns/solve.sh \
  benchmarks/aeossp_standard/dataset/cases/test/case_0001 \
  /path/to/config_dir \
  /tmp/aeossp_greedy_lns_solution
```

Official smoke verification through `main_solver`:

```bash
uv run python experiments/main_solver/run.py \
  --benchmark aeossp_standard \
  --solver aeossp_standard_greedy_lns \
  --case test/case_0001
```

Aggregate experiment results:

```bash
uv run python experiments/main_solver/aggregate.py
```

## Sanity Baseline

The paper reports profit gaps against upper bounds, not benchmark `WCR`, `CR`, `TAT`, or `PC`. Acquisition-only Greedy/LS-tempo averaged roughly a 0.115 gap on the authors' generated instances. For this benchmark, the closest sanity check
is whether the solver produces valid solutions with plausible candidate counts and weighted completion ratios.

What matters here is:

- official verification passes
- candidate counts are plausible
- repair does not collapse the schedule
- weighted completion remains reasonable on public cases

If raw greedy/local-search selection looks strong but repair removes many actions, inspect the local battery model, transition gap logic, and candidate generation before tuning search parameters.

## Known Limitations

- This is a reproduction of the paper's acquisition-planning method, not a claim to reproduce every runtime or every table from the paper.
- The solver does not include the paper's Tempo CP-SAT TSPTW fallback, which is a proprietary dependency.
- Battery feasibility is handled by solver-local validation and repair instead of being fully encoded inside the greedy/LNS core.
- Candidate generation is currently unoptimized and dominates runtime on larger cases. A future issue may address efficiency.
- Download and memory scheduling are omitted because the benchmark is observation-only.

## Evidence Type

This solver is registered in `experiments/main_solver` with `evidence_type: reproduced_solver`.
