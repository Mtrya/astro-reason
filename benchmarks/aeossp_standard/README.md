# AEOSSP Standard Benchmark

## Status

This benchmark is implemented and is the canonical finished AEOSSP benchmark in this repository.

It replaces the earlier public `aeosbench` benchmark surface.

## Problem Summary

`aeossp_standard` is a planning-oriented agile Earth-observation satellite scheduling benchmark.

For each case, the space agent receives:

- a fixed 12-hour planning horizon
- a fixed constellation of real Earth-observation satellites expressed through
  frozen TLEs and benchmark-owned subsystem parameters
- a set of time-windowed point-imaging tasks
- hard observation, battery, and slew constraints

The space agent must return:

- an event-based schedule of `observation` actions

The benchmark is scheduling-focused, not constellation-design-focused. The solver does not add satellites, choose orbits, redesign the fleet, or submit low-level attitude commands.

Out of scope:

- constellation design
- downlink and data-delivery planning
- onboard storage modeling
- cloud cover and stochastic weather
- detailed radiometry or image quality scoring
- full rigid-body attitude propagation

## Dataset Layout

The canonical dataset lives under:

```text
dataset/
├── example_solution.json
├── index.json
└── cases/
    └── <split>/
        └── <case_id>/
            ├── mission.yaml
            ├── satellites.yaml
            └── tasks.yaml
```

`dataset/example_solution.json` is one real solution object with the same schema as normal submissions. `dataset/index.json` records case metadata and the smoke pairing through split-relative `example_smoke_case`, and the benchmark-owned construction contract lives in `benchmarks/aeossp_standard/splits.yaml`.

## Case Inputs

Each case directory contains exactly three machine-readable files.

### `mission.yaml`

`mission.yaml` defines the planning horizon, public time grids, propagation model, and scoring metadata.

Important fields:

- `case_id`
- `horizon_start`
- `horizon_end`
- `action_time_step_s`
- `geometry_sample_step_s`
- `resource_sample_step_s`
- `propagation`
  - `model`
  - `frame_inertial`
  - `frame_fixed`
  - `earth_shape`
- `scoring`
  - `ranking_order`
  - `reported_metrics`

All timestamps are ISO 8601 in UTC. The horizon must be exactly divisible by the action, geometry, and resource steps.

### `satellites.yaml`

`satellites.yaml` contains the fixed constellation for the case.

Each satellite entry includes:

- `satellite_id`
- `norad_catalog_id`
- `tle_line1`
- `tle_line2`
- `sensor`
  - `sensor_type`
- `attitude_model`
  - `max_slew_velocity_deg_per_s`
  - `max_slew_acceleration_deg_per_s2`
  - `settling_time_s`
  - `max_off_nadir_deg`
- `resource_model`
  - `battery_capacity_wh`
  - `initial_battery_wh`
  - `idle_power_w`
  - `imaging_power_w`
  - `slew_power_w`
  - `sunlit_charge_power_w`

The public dataset uses benchmark-owned visible and infrared sensor templates.

### `tasks.yaml`

`tasks.yaml` contains the imaging requests for the horizon.

Each task includes:

- `task_id`
- `name`
- `latitude_deg`
- `longitude_deg`
- `altitude_m`
- `release_time`
- `due_time`
- `required_duration_s`
- `required_sensor_type`
- `weight`

Frozen task semantics:

- `release_time`, `due_time`, and `required_duration_s` must align to the public action grid
- a task is binary-complete, not partially creditable
- the target must be observed continuously for exactly `required_duration_s` inside its time window

## Solution Contract

A valid submission is one JSON object with one top-level array:

- `actions`

Each action is:

```json
{
  "type": "observation",
  "satellite_id": "sat_001",
  "task_id": "task_0001",
  "start_time": "2025-07-17T04:12:00Z",
  "end_time": "2025-07-17T04:12:20Z"
}
```

Supported action types:

- `observation`

The solver does not submit:

- visibility claims
- power claims
- maneuver intervals
- attitude trajectories
- completion claims

Those are all verifier-owned.

## Validity Rules

The verifier rejects a solution if any hard rule is violated, including:

- malformed case or solution structure
- duplicate task or satellite identifiers inside the case
- unknown satellite or task references in the solution
- unsupported action types
- zero-duration, off-grid, or out-of-horizon actions
- actions outside the task window
- action durations that do not match `required_duration_s`
- sensor-type mismatch
- geometry-invalid observations
- same-satellite observation overlap
- insufficient slew-plus-settle gap
- battery depletion below zero

Any hard violation makes the whole solution invalid. Invalid solutions return:

- `valid = false`
- zeroed metrics:
  - `CR = 0`
  - `WCR = 0`
  - `TAT = null`
  - `PC = 0`

## Geometry, Attitude, And Power Semantics

The verifier owns orbit propagation and observation geometry.

Propagation model:

- Brahe `SGPPropagator` from the case TLEs
- GCRF inertial frame
- ITRF Earth-fixed frame
- WGS84 Earth model
- static zero-valued EOP provider for deterministic offline verification

Observation geometry:

- visibility is checked on the public geometry grid plus action boundaries
- the target must remain continuously visible across the action interval
- the required off-nadir angle must remain within `attitude_model.max_off_nadir_deg`

Attitude / slew model:

- the solver schedules only observation intervals
- the verifier derives a nominal pointing strategy from the geometry
- maneuver windows are reserved immediately before the later observation
- slew feasibility uses a scalar bang-coast-bang model with:
  - `max_slew_velocity_deg_per_s`
  - `max_slew_acceleration_deg_per_s2`
  - `settling_time_s`
- the public solution visualizer renders a schematic off-nadir curve that:
  - tracks instantaneous off-nadir during observation
  - uses the same scalar bang-coast-bang maneuver shape during reserved slew windows
  - holds the previous observation's terminal pointing between observations
  - holds nadir before the first reserved maneuver

Power model:

- battery is simulated across the full horizon on explicit integration segments
- gross electrical load is:
  - `idle_power_w`
  - plus `imaging_power_w` during observation
  - plus `slew_power_w` during maneuver windows
- solar charging applies whenever the satellite is sunlit
- `PC` reports gross electrical consumption only; it does not subtract solar charging

## Metrics And Ranking

The verifier reports:

- `CR`
- `WCR`
- `TAT`
- `PC`

Metric meanings:

- `CR`: completed task fraction
- `WCR`: completed weight fraction
- `TAT`: mean `(completion_time - release_time)` over completed tasks, or `null` if nothing completes
- `PC`: total gross watt-hours consumed over the horizon

Task completion semantics:

- a task is complete if at least one valid observation satisfies it
- duplicate valid observations do not add extra credit
- the earliest valid completion time determines `TAT`

Intended ranking order:

1. valid solutions beat invalid solutions
2. maximize `WCR`
3. maximize `CR`
4. minimize `TAT`
5. minimize `PC`

## Public Entrypoints

Generator:

```bash
uv run python -m benchmarks.aeossp_standard.generator.run \
  benchmarks/aeossp_standard/splits.yaml
```

Verifier:

```bash
uv run python -m benchmarks.aeossp_standard.verifier.run \
  benchmarks/aeossp_standard/dataset/cases/test_medium/case_0001 \
  benchmarks/aeossp_standard/dataset/example_solution.json
```

Case visualizer:

```bash
uv run python -m benchmarks.aeossp_standard.visualizer.run case \
  --case-dir benchmarks/aeossp_standard/dataset/cases/test_medium/case_0001
```

Solution visualizer:

```bash
uv run python -m benchmarks.aeossp_standard.visualizer.run solution \
  --case-dir benchmarks/aeossp_standard/dataset/cases/test_medium/case_0001 \
  --solution-path benchmarks/aeossp_standard/dataset/example_solution.json
```

Visualizer artifact interpretation:

- case `access_off_nadir_curves.png` is geometry-only:
  - it shows representative access/off-nadir demand curves
  - it is not a nominal attitude strategy plot
- solution `attitude_curves.png` is schematic but verifier-aligned:
  - it is derived from verifier-backed observation intervals and maneuver windows
  - it uses the benchmark's scalar bang-coast-bang slew profile rather than linear angle interpolation

The canonical generator requires the committed `splits.yaml` path and reproduces the benchmark-owned dataset outputs under `dataset/cases/` and `dataset/index.json`.

## Generator And Canonical Dataset

The generator builds cases from benchmark-owned rules rather than hand-authored case lists.

Current split decision:

- `test_medium` is the primary medium-difficulty evaluation split
- `test_medium_horizon_2022` keeps the same medium controls and uses the vendored 2022 historical TLE cache so the mission horizons move to April 2022
- `train` mirrors `test_medium` controls with `10` cases
- `test_easy` and `test_hard` are temporarily deferred while split design and generator performance are being improved

Current canonical medium family:

- 5 canonical cases
- 20 to 28 satellites per case
- 1600 to 2000 tasks per case
- mixed visible / infrared task requirements
- mixed city / land-background target sources
- task windows derived from real access opportunities

Public source workflow:

- vendored CelesTrak Earth-resources TLE snapshots (`generator/cached_tles.py` and `generator/cached_tles_2022.py`)
- GeoNames city data
- Natural Earth land polygons

Runtime source data for GeoNames and Natural Earth may be cached under `dataset/source_data/`, but that directory is not tracked and is not required to exist before running the generator. The CelesTrak TLE snapshots used for canonical reproduction are tracked in the generator package and staged into normalized CSVs without network access.

`splits.yaml` carries the benchmark-owned generation parameters for the canonical splits, including mission timing, per-split CelesTrak snapshot selection, satellite-pool filtering, subsystem templates, and task-sampling controls. The retained operational flags `--download-dir`, `--output-dir`, and `--force-download` only affect where source data is staged or refreshed; they are not alternate canonical dataset contracts.

## Tests And Fixtures

The verifier is locked by focused fixture-driven tests under:

- `tests/fixtures/aeossp_standard/`
- `tests/benchmarks/test_aeossp_standard_verifier.py`

These fixtures cover:

- exact valid scoring
- zero-completion semantics
- duplicate observation no-bonus semantics
- sensor mismatch
- visibility invalidation
- overlap invalidation
- slew-gap invalidation
- battery invalidation

## Lineage

`aeossp_standard` is informed by standard AEOSSP formulations and by prior benchmark work such as AEOS-Bench, but it is not a reproduction of any single legacy benchmark or simulator stack.
