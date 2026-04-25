# Rogers MMRT/MART Binary Scheduler

This is the Phase 2 scaffold for a reproduced `revisit_constellation` solver based on Rogers MMRT/MART constellation-design models followed by a later binary observation scheduler.

The current implementation is intentionally limited to standalone design preprocessing:

- parse public `assets.json` and `mission.json`
- build a deterministic finite circular-orbit slot library
- propagate slots with Brahe J2 dynamics
- generate a sparse visibility matrix `V[t,j,p]`
- select design slots with bounded MMRT, MART, threshold-first, or hybrid policies
- enumerate feasible Cho-style observation windows for selected slots
- write a benchmark-shaped `solution.json` with selected satellites and no actions
- write `status.json` and `model_prep/*` summaries

It does not import benchmark internals and does not implement observation scheduling yet.

The design models operate on access timelines, following Rogers' MMRT/MART layer before
the later Cho-style action scheduler. If PuLP is available and the model is within
configured size limits, the solver can use it for bounded MILP design models. Otherwise
it falls back deterministically to exact enumeration for tiny cases and greedy objective
matching for larger cases.

## Contract

```bash
./setup.sh
./solve.sh <case_dir> [config_dir] [solution_dir]
```

`solve.sh` writes:

- `solution.json`
- `status.json`
- `model_prep/slots.json`
- `model_prep/time_grid.json`
- `model_prep/visibility_matrix.json`
- `debug/design_model_summary.json`
- `debug/selected_slots.json`
- `debug/window_summary.json`
- `debug/observation_windows.jsonl` when `write_observation_windows: true`

Optional configuration can be provided with `config.yaml`, `config.yml`, or `config.json` in the config directory. Supported keys are:

- `sample_step_sec` (default `7200`)
- `altitude_count` (default `1`)
- `inclination_deg` (default `[55.0, 97.6]`)
- `raan_count` (default `4`)
- `phase_count` (default `2`)
- `max_slots` (default `16`)
- `write_visibility_matrix`
- `design_mode` (`hybrid`, `threshold_first`, `mmrt`, or `mart`)
- `design_backend` (`auto`, `pulp`, or `fallback`)
- `design_threshold_metric` (`mmrt` or `mart`)
- `design_satellite_count`
- `design_max_selected_slots`
- `design_time_limit_sec`
- `design_max_backend_slots`
- `design_max_backend_time_samples`
- `design_max_backend_variables`
- `design_max_backend_constraints`
- `fallback_exhaustive_max_combinations`
- `window_stride_sec`
- `window_geometry_sample_step_sec`
- `max_observation_windows`
- `max_windows_per_satellite_target`
- `write_observation_windows`
- `debug`
