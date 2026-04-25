# Rogers MMRT/MART Binary Scheduler

This solver is a runnable reproduced solver for `revisit_constellation`.

It follows the constellation-design formulations from Rogers et al.,
"Optimal Satellite Constellation Configuration Design: A Collection of Mixed
Integer Linear Programs", and adapts them to benchmark observation actions with
a Cho-style binary observation scheduler.

## Citation

```bibtex
@article{rogers2026milpconstellation,
  title={Optimal Satellite Constellation Configuration Design: A Collection of Mixed Integer Linear Programs},
  author={Rogers, David O. Williams and Won, Dongshik and Koh, Dongwook and Hong, Kyungwoo and Lee, Hang Woon},
  journal={Journal of Spacecraft and Rockets},
  year={2026},
  doi={10.2514/1.A36518},
  eprint={2507.09855},
  archivePrefix={arXiv}
}

@article{cho2018twostep,
  title={Optimization-Based Scheduling Method for Agile Earth-Observing Satellite Constellation},
  author={Cho, Doo-Hyun and Kim, Jun-Hong and Choi, Han-Lim and Ahn, Jaemyung},
  journal={Journal of Aerospace Information Systems},
  volume={15},
  number={12},
  pages={611--626},
  year={2018},
  doi={10.2514/1.I010620}
}
```

The source issue for this solver is
[`#88`](https://github.com/Mtrya/astro-reason/issues/88). It was rechecked as
open before promotion.

The solver is standalone. It reads public benchmark case files and writes a
benchmark solution JSON, but it does not import or execute benchmark,
experiment, runtime, or other solver internals.

## Method Summary

Rogers et al. formulate constellation configuration as a slot-selection MILP
over a sampled visibility tensor:

- orbital slot `j`: one candidate initial satellite state at mission start
- visibility `V[t,j,p]`: whether slot `j` can view target `p` at sample `t`
- MMRT objective: minimize the longest uncovered run over all targets
- MART objective: minimize the average uncovered-run proxy over targets
- constrained variants: reduce satellite count once revisit thresholds are met

This reproduction keeps that design structure and adapts it to the benchmark:

- slot library: deterministic circular candidate states inside the case altitude bounds
- visibility: Brahe J2 propagation plus target elevation, off-nadir, and range filters
- default design mode: `mmrt`, because the benchmark ranks maximum revisit gap first
- alternate design modes: `mart`, `threshold_first`, and `hybrid`
- scheduler candidate: one feasible `(satellite, target, start, end)` observation window
- scheduler profit: marginal benchmark revisit-gap reduction, not a generic priority score
- scheduler decision: binary selection of non-conflicting observation windows

The resulting `solution.json` contains selected initial satellite states and
scheduled `observation` actions.

## Benchmark Adaptation

The benchmark combines constellation design and observation scheduling, while
Rogers' MMRT/MART layer optimizes access timelines before action-level
resources. The adaptation is therefore explicit:

- Rogers `x_j` becomes a chosen initial GCRF state emitted in `satellites`.
- Rogers coverage state `y[t,p]` is used as a design proxy before scheduling.
- Cho-style feasible task windows become benchmark observation actions.
- Same-satellite overlaps are encoded as scheduler conflicts.
- Optional transition-gap conflicts can be added with `scheduler_min_transition_gap_sec`.
- Slew, sampled geometry, and a conservative battery approximation are checked again in solver-local validation and repair.
- Official validity and final metrics are still determined only by the benchmark verifier through `experiments/main_solver`.

This means the solver reproduces the Rogers MMRT/MART design family and the
Cho two-step scheduling shape, while documenting where benchmark resource
semantics are added after the paper-to-benchmark translation.

## Solver Contract

```bash
./setup.sh
./solve.sh <case_dir> [config_dir] [solution_dir]
```

`setup.sh` is a no-op when using the project environment.

`solve.sh` reads:

- `assets.json`
- `mission.json`

`solve.sh` writes:

- `solution.json`: primary benchmark solution
- `status.json`: compact run status and model summaries
- `model_prep/slots.json`
- `model_prep/time_grid.json`
- `model_prep/visibility_matrix.json`
- `debug/design_model_summary.json`
- `debug/selected_slots.json`
- `debug/window_summary.json`
- `debug/observation_windows.jsonl` when `write_observation_windows: true`
- `debug/scheduler_model_summary.json`
- `debug/selected_windows.json`
- `debug/rounding_or_fallback_summary.json`
- `debug/validation_summary.json`
- `debug/reproduction_summary.json`

## Backend And Fallback Behavior

The solver has optional PuLP-backed bounded models. PuLP is not required.

Design backend behavior:

- `design_backend: auto` tries the bounded PuLP design backend when available and within size limits.
- `design_backend: pulp` requires the PuLP path subject to the same size guards.
- `design_backend: fallback` skips PuLP.
- Tiny bounded cases use exact deterministic enumeration when the backend is unavailable.
- Larger cases use deterministic greedy objective matching.

Scheduler backend behavior:

- `scheduler_backend: auto` tries PuLP binary scheduling first.
- If binary scheduling is unavailable, bounded exact enumeration is tried.
- If exact enumeration exceeds `scheduler_max_exact_combinations`, PuLP relaxed rounding is tried when available.
- The final bounded fallback is deterministic greedy insertion by revisit-gap improvement.

Debug summaries report `backend_report`, `fallback_reason`, exact-combination
counts, and whether exact, relaxed, or greedy fallback was used. Fallbacks are
part of the reproduced solver contract; they are not hidden as exact MILP runs.

## Configuration

The solver reads optional config from either:

- `<config_dir>/config.yaml`
- `<config_dir>/config.yml`
- `<config_dir>/config.json`
- `<config_dir>/rogers_mmrt_mart_binary_scheduler.yaml`
- `<config_dir>/rogers_mmrt_mart_binary_scheduler.yml`
- `<config_dir>/rogers_mmrt_mart_binary_scheduler.json`

See [config.example.yaml](./config.example.yaml) for a complete example.

Key knobs:

- slot grid and caps: `altitude_count`, `inclination_deg`, `raan_count`, `phase_count`, `max_slots`
- visibility grid: `sample_step_sec`, `write_visibility_matrix`
- design: `design_mode`, `design_backend`, `design_satellite_count`, `design_max_selected_slots`
- design bounds: `design_max_backend_slots`, `design_max_backend_time_samples`, `design_max_backend_variables`, `design_max_backend_constraints`
- window enumeration: `window_stride_sec`, `window_geometry_sample_step_sec`, `max_observation_windows`, `max_windows_per_satellite_target`
- scheduling: `scheduler_backend`, `scheduler_time_limit_sec`, `scheduler_max_exact_combinations`, `scheduler_max_selected_windows`
- local validation: `local_repair_enabled`, `local_validation_geometry_sample_step_sec`, `local_battery_margin_wh`
- diagnostics: `write_observation_windows`, `debug`

## Debug Artifacts

The most useful reproduction artifact is `debug/reproduction_summary.json`. It records:

- source-to-implementation mapping for Rogers and Cho components
- active design and scheduler backend choices
- issue `#88` status metadata
- MMRT, MART, threshold-first, and hybrid design comparisons
- no-op, current, bounded-exact, and greedy scheduler comparisons
- local validation and repair outcomes
- metric drift from design proxy to scheduled windows after repair

These files are intended to answer whether a run was exact, bounded exact,
relaxed, or greedy, and why.

## Running It

Direct setup:

```bash
./solvers/revisit_constellation/rogers_mmrt_mart_binary_scheduler/setup.sh
```

Direct solve on a public smoke case:

```bash
./solvers/revisit_constellation/rogers_mmrt_mart_binary_scheduler/solve.sh \
  benchmarks/revisit_constellation/dataset/cases/test/case_0001
```

Direct solve with a config directory:

```bash
./solvers/revisit_constellation/rogers_mmrt_mart_binary_scheduler/solve.sh \
  benchmarks/revisit_constellation/dataset/cases/test/case_0001 \
  /path/to/config_dir \
  /tmp/rogers_revisit_solution
```

Official smoke verification through `main_solver`:

```bash
uv run python experiments/main_solver/run.py \
  --benchmark revisit_constellation \
  --solver revisit_constellation_rogers_mmrt_mart_binary_scheduler \
  --case test/case_0001
```

Aggregate experiment results:

```bash
uv run python experiments/main_solver/aggregate.py
```

## Sanity Baseline

On the public smoke case, official verification should pass before considering
the solver promotable. In the promotion smoke run, the tuned default selected
four satellites, scheduled 19 observation actions, required no local repair
drops, and the official verifier reported `is_valid: true`.

Useful checks:

- official verification passes
- `debug/reproduction_summary.json` records issue `#88`, backend choices, and fallback behavior
- MMRT/MART comparisons are deterministic
- repair does not collapse the selected schedule
- scheduled estimates and official verifier metrics agree qualitatively

## Known Limitations

- This is a reproduced solver adapted to the benchmark, not a claim to reproduce every Rogers table or runtime.
- The finite slot library is a bounded circular-orbit library, not the full common-RGT/APC construction from the Rogers examples.
- Cho evidence is limited to public paper metadata and summary notes; no clean full transcript was available.
- PuLP is optional and absent in the default project environment used for smoke verification, so debug artifacts may show exact or greedy fallback rather than MILP solves.
- The design-stage MMRT/MART objective optimizes access timelines, while final benchmark metrics depend on scheduled actions after slew and battery checks.
- Battery feasibility is handled by conservative local validation and repair rather than a full integrated energy MILP.
- Public smoke cases can remain max-gap limited by targets with no feasible windows under the current bounded slot grid.

## Evidence Type

This solver is registered in `experiments/main_solver` with
`evidence_type: reproduced_solver`.
