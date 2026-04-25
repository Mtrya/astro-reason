# Time-Window-Pruned Stereo MILP Solver

This solver is a runnable reproduced solver for `stereo_imaging`.

It follows the task-scheduling method described by Junhong Kim, Jaemyung Ahn, Han-Lim Choi, and Doo-Hyun Cho in "Task Scheduling of Multiple Agile Satellites with Transition Time and Stereo Imaging Constraints", adapted to the benchmark's public case and solution contract.

## Citation

```bibtex
@article{kim2020task,
  title={Task Scheduling of Multiple Agile Satellites with Transition Time and Stereo Imaging Constraints},
  author={Kim, Junhong and Ahn, Jaemyung and Choi, Han-Lim and Cho, Doo-Hyun},
  journal={Journal of Aerospace Information Systems},
  year={2020},
  doi={10.2514/1.I010775}
}
```

The solver is standalone. It reads benchmark case files and writes a benchmark solution JSON, but it does not import or execute benchmark, experiment, runtime, or other solver internals.

## Method Summary

The paper decomposes agile Earth-observation scheduling with stereo constraints into candidate generation, product pruning, and MILP optimization. This reproduction keeps that structure and adapts it to `stereo_imaging`:

- **Candidate**: one `(satellite_id, target_id, start_time, end_time, off_nadir_along_deg, off_nadir_across_deg)` observation inside a found access interval that satisfies horizon, duration, combined off-nadir, solar elevation, and LOS prechecks.
- **Stereo pair**: two candidates on the same target scored against convergence-angle, overlap-fraction, and pixel-scale-ratio thresholds, with the data model widened to represent the benchmark's same-satellite same-pass and cross-satellite product modes.
- **Tri-stereo set**: three candidates on the same target with sufficient common overlap and a near-nadir anchor requirement, with product metadata widened so later phases can model the benchmark's full constituent-pair rules.
- **Conflict graph**: edges encode same-satellite temporal overlap and insufficient slew-plus-settle gap.
- **Coverage**: each target is covered when at least one valid pair or tri-stereo set containing that target is selected.
- **Objective**: lexicographic maximize covered targets, then best-per-target stereo quality.

The solver supports exact and heuristic optimization modes:

- **Exact MILP** via OR-Tools CP-SAT or PuLP+CBC when installed.
- **Deterministic greedy heuristic** only when `optimization.backend: greedy` is set explicitly.

## Benchmark Adaptation

The benchmark differs from the paper in a few important ways:

- The benchmark ranks by valid first, then coverage ratio and normalized quality, so the solver uses coverage-first, best-per-target-quality selection rather than additive duplicate-product quality.
- Access intervals are found with a coarse time-step search rather than exact SGP4 root-finding; minor drift relative to exact propagation is expected.
- Solar elevation and LOS checks are sampled at the observation midpoint.
- Overlap fraction is estimated with a deterministic polar grid rather than Monte Carlo; values may differ by a few percent from the verifier.
- The benchmark now allows both same-satellite same-pass stereo and mission-bounded cross-satellite stereo, and the solver now enumerates those benchmark product modes directly in its product layer.
- Candidate generation is batched per satellite so one horizon propagation pass is reused across all targets for that satellite, then parallelized over satellites for speed.
- Product enumeration uses lazy strip-geometry construction and safe early rejection on convergence, pixel-scale, anchor, and constituent-pair checks before paying for overlap evaluation.

That means this solver reproduces the paper's candidate-prune-optimize pipeline, while remaining faithful to the benchmark's public validity contract.

## Solver Contract

```bash
./setup.sh
./solve.sh <case_dir> [config_dir] [solution_dir]
```

`setup.sh` creates an ignored solver-local virtual environment at `.venv/`, installs solver dependencies from `requirements.txt`, and checks that `brahe`, `numpy`, `yaml`, and `skyfield` are importable there. Override the location with `SOLVER_VENV_DIR=/path/to/env` if you want to reuse a prepared per-solver environment.

### Backend installation

The default `thorough` mode uses `optimization.backend: auto`, which requires at least one exact backend. Install one of the following PyPI packages in the solver-local environment:

```bash
./setup.sh
# or
SOLVER_VENV_DIR=/path/to/stereo-milp-env ./setup.sh
```

`requirements.txt` contains the core solver runtime dependencies. `setup.sh` then attempts both exact backend packages, `pulp>=2.9` and `ortools>=9.11`, independently in the solver-local environment. Both are PyPI packages; neither is installed into the repository workspace. With a backend installed, set `backend: auto` (default) or explicitly `backend: ortools` / `backend: pulp`. If no exact backend is importable, `auto`, `ortools`, and `pulp` fail hard instead of silently switching to greedy. Use `backend: greedy` only for intentional heuristic sweeps.

## Runtime Modes

The solver exposes two documented runtime presets through `runtime.mode`:

- `thorough`: denser benchmark-facing preset for public-case evaluation. This is the implicit default when no config is supplied.
- `fast`: lighter heuristic preset for quicker sweeps and before/after runtime comparisons.

The preset is applied first, then any user-specified knobs override it. `thorough` uses exact backend auto-discovery and fails when neither `ortools` nor `pulp` is installed. `fast` sets `optimization.backend: greedy` explicitly.

`solve.sh` writes:

- `solution.json`: primary benchmark solution
- `status.json`: solver summary, timings, reproduction notes, and backend details
- `debug/*`: optional debug artifacts when `debug: true`

The primary solution artifact is one JSON object with a top-level `actions` array of `observation` actions.

## Pipeline

The solver pipeline is:

1. Load `mission.yaml`, `satellites.yaml`, and `targets.yaml`.
2. Build batched satellite state series and find access intervals for each target with coarse time-step search.
3. Generate candidate observations by sampling start times and steering angles inside each interval, applying cheap local prechecks with cached midpoint state.
4. Enumerate stereo pairs and tri-stereo sets, using cheap rejection filters before overlap geometry where safe.
5. Optionally prune candidates with Kim-style time-window cluster capping.
6. Build an abstract MILP with observation, pair, tri, and coverage variables linked by conflict constraints.
7. Solve with OR-Tools, PuLP, or the explicitly requested deterministic greedy heuristic using coverage-first and best-per-target-quality semantics.
8. Run solver-local conservative repair to remove any remaining transition or exclusivity violations, then recompute benchmark-shaped coverage and quality metrics.

The repair stage is intentionally conservative. It keeps the solver standalone and reduces official verifier failures without claiming that all geometric approximations are exact.

## Configuration

The solver reads optional config from either:

- `<config_dir>/config.yaml`
- `<config_dir>/config.yml`
- `<config_dir>/config.json`
- `<config_dir>/time_window_pruned_stereo_milp.yaml`
- `<config_dir>/time_window_pruned_stereo_milp.yml`
- `<config_dir>/time_window_pruned_stereo_milp.json`

See [config.example.yaml](./config.example.yaml) for a commented example.

Key knobs:

- `runtime.mode`
- `time_step_s`
- `sample_stride_s`
- `max_candidates_per_interval`
- `parallel_candidate_generation`
- `steering_along_samples`
- `steering_across_samples`
- `steering_grid_spread_deg`
- `use_target_centered_steering`
- `strip_sample_step_s`
- `overlap_grid_angles`
- `overlap_grid_radii`
- `pruning.enabled`
- `optimization.backend`
- `optimization.time_limit_s`
- `debug`

`time_limit_s` only bounds the MILP or greedy solve step. It does not cap candidate generation, product enumeration, or local validation. If the time budget is reached, the solver returns the best incumbent found so far and still performs repair.

`status.json` also includes a `profiling` section with stage counters for candidate generation, product enumeration, and solve/model-build work, so runtime tuning can be compared without ad hoc logging.

## Debug Artifacts

When `debug: true`, the solver writes:

- `debug/candidate_summary.json`
- `debug/product_summary.json`
- `debug/pruning_summary.json`
- `debug/repair_log.json`

`status.json` is the primary timing artifact for Phase 4 work:

- `timing_seconds` keeps coarse wall-clock stage totals
- `profiling.runtime_mode` records which preset ran
- `profiling.candidate_generation` reports batched-state, access-search, sampling, and solar-check counts
- `profiling.product_enumeration` reports midpoint-geometry, strip-geometry, and overlap-evaluation counts
- `profiling.solve` reports conflict-graph, model-build, and backend details

These are useful for answering:

- why a target has zero candidates
- how many valid pairs and tri-stereo sets were found
- whether pruning removed viable candidates
- why a candidate was removed during repair
- which backend was selected

## Running It

Direct setup:

```bash
./solvers/stereo_imaging/time_window_pruned_stereo_milp/setup.sh
```

Direct solve on a public smoke case:

```bash
./solvers/stereo_imaging/time_window_pruned_stereo_milp/solve.sh \
  benchmarks/stereo_imaging/dataset/cases/test/case_0001
```

Direct solve with a config directory:

```bash
./solvers/stereo_imaging/time_window_pruned_stereo_milp/solve.sh \
  benchmarks/stereo_imaging/dataset/cases/test/case_0001 \
  /path/to/config_dir \
  /tmp/stereo_milp_solution
```

Official smoke verification through `main_solver`:

```bash
uv run python experiments/main_solver/run.py \
  --benchmark stereo_imaging \
  --solver stereo_imaging_time_window_pruned_stereo_milp \
  --case test/case_0001
```

Aggregate experiment results:

```bash
uv run python experiments/main_solver/aggregate.py
```

## Sanity Baseline

The paper reports MILP objective values and coverage fractions on generated instances, not benchmark coverage ratios or normalized quality scores. Treat the paper's coverage fractions as a rough sanity check for completion behavior, not as a target metric table for this benchmark.

What matters here is:

- official verification passes
- candidate counts are plausible
- repair does not collapse the schedule
- coverage remains reasonable on public cases

If raw pair/tri selection looks strong but repair removes many observations, inspect the local conflict model, transition gap logic, and candidate generation before tuning search parameters.

## Known Limitations

- This is a reproduction of the paper's candidate-prune-optimize pipeline, not a claim to reproduce every runtime or every table from the paper.
- Access intervals are found with coarse time-step search rather than exact SGP4 root-finding; minor drift relative to exact propagation is expected.
- Solar elevation and LOS checks are sampled at the observation midpoint.
- Overlap fraction is estimated with a deterministic polar grid rather than Monte Carlo; values may differ by a few percent from the verifier.
- If no valid stereo pairs or tri-stereo sets exist for a target (e.g. only one satellite accesses it, or slew time exceeds the gap between consecutive intervals), that target will remain uncovered.
- Exact MILP requires solver-local `ortools` or `pulp`; missing exact libraries are reported as errors unless `optimization.backend: greedy` is explicitly selected.

## Evidence Type

This solver is registered in `experiments/main_solver` with `evidence_type: reproduced_solver`.
