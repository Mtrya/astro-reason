# Revisit Constellation Benchmark

## Status

This benchmark is in active design and migration.

It is intended to replace `benchmarks/revisit_optimization/` after the new
benchmark is fully implemented, tested, and documented. Until then,
`revisit_optimization` remains as a reference for legacy dataset structure and
benchmark-side tooling ideas.

## Problem Summary

Design an Earth observation constellation and an operating schedule that keeps
target revisit gaps as small as possible over a mission horizon.

For each case, the space agent receives a problem instance describing:

- a satellite model
- target locations
- hard mission and orbit constraints
- mission start and end times
- an expected revisit gap threshold

The space agent must return:

- a constellation definition
- a sequence of scheduled actions

The benchmark combines two decisions in a single task:

1. constellation architecture design
2. mission scheduling

## Intended Benchmark Scope

The architecture-design part of the benchmark means defining the initial states
of satellites at mission start time. At a high level, a solver chooses how many
satellites to deploy, up to the case-specific cap, and specifies each
satellite's initial state in the GCRF frame.

The scheduling part of the benchmark means producing a feasible action sequence
for that constellation over the mission horizon.

Launch design, launch cost, and deployment operations are out of scope. The
benchmark assumes that the proposed satellites already exist in their initial
states at the mission start time.

## Case Inputs

Each canonical case contains exactly two machine-readable files:

- `assets.json`
- `mission.json`

### `assets.json`

`assets.json` contains the shared satellite model, satellite-count cap, and
ground-station assets for the case.

The satellite model includes:

- `model_name`
- `sensor`
  - `field_of_view_half_angle_deg`
  - `max_range_m`
  - `obs_discharge_rate_w`
  - `obs_store_rate_mbps`
- `terminals[]`
  - `downlink_release_rate_mbps`
  - `downlink_discharge_rate_w`
- `resource_model`
  - `battery_capacity_wh`
  - `storage_capacity_mb`
  - `initial_battery_wh`
  - `initial_storage_mb`
  - `idle_discharge_rate_w`
  - `sunlight_charge_rate_w`
- `attitude_model`
  - `max_slew_velocity_deg_per_sec`
  - `max_slew_acceleration_deg_per_sec2`
  - `settling_time_sec`
  - `maneuver_discharge_rate_w`
- `min_altitude_m`
- `max_altitude_m`

The file also includes:

- `max_num_satellites`
- `ground_stations[]`
  - `id`
  - `name`
  - `latitude_deg`
  - `longitude_deg`
  - `altitude_m`
  - `min_elevation_deg`
  - `min_duration_sec`

### `mission.json`

`mission.json` contains the mission horizon and target-specific revisit
requirements:

- `horizon_start`
- `horizon_end`
- `targets[]`
  - `id`
  - `name`
  - `latitude_deg`
  - `longitude_deg`
  - `altitude_m`
  - `expected_revisit_period_hours`
  - `min_elevation_deg`
  - `max_slant_range_m`
  - `min_duration_sec`

The initial benchmark target is a `48h` mission horizon.

## Solution Contract

A valid solution is a single JSON document with two top-level arrays:

- `satellites`
- `actions`

### `satellites`

Each satellite entry defines one solver-chosen satellite at mission start:

- `satellite_id`
- `x_m`
- `y_m`
- `z_m`
- `vx_m_s`
- `vy_m_s`
- `vz_m_s`

All states are interpreted as GCRF Cartesian states in SI units.

### `actions`

The action list defines the mission schedule for the proposed constellation.
Supported action types are:

- `observation`
- `downlink`

Each action includes:

- `action_type`
- `satellite_id`
- `start`
- `end`

Observation actions also include:

- `target_id`

Downlink actions also include:

- `station_id`

## Validity Rules

Constraint violations should invalidate a solution immediately. In other words,
metrics are only meaningful for solutions that satisfy all hard constraints.

The verifier is expected to reject a solution if any of the following occur:

- malformed solution structure
- more satellites than the case permits
- satellite initial states that violate orbit constraints
- infeasible observation geometry
- infeasible downlink geometry
- power constraint violations
- storage constraint violations
- inconsistent action timing
- overlapping observation timing
- references to unknown satellites, targets, or stations

Additional hard-validity checks may be added as the schema becomes more
concrete.

## Metrics And Ranking

The legacy mapping-coverage branch is intentionally removed from this benchmark.
The new benchmark is purely revisit-driven.

The intended metrics for valid solutions are:

- `mean_revisit_gap_hours`
- `max_revisit_gap_hours`
- `satellite_count`
- `threshold_satisfied`

The intended ranking logic is:

1. Valid solutions beat invalid solutions.
2. If not all targets achieve revisit gaps below the expected threshold, prefer
   lower `max_revisit_gap_hours`, then lower `mean_revisit_gap_hours`.
3. If all targets achieve revisit gaps below the expected threshold, prefer the
   solution that uses fewer satellites, then use
   `mean_revisit_gap_hours` as a tie-break.

## Revisit Interpretation

The benchmark treats poor revisit performance as poor scoring, not as an
automatic validity failure.

Successful observations are represented by their midpoint times. Revisit gaps
include the mission start and mission end as boundary times:

- zero successful observations: the revisit gap is the full mission horizon
- one successful observation: gaps are start-to-observation and
  observation-to-end
- multiple successful observations: gaps are computed between consecutive
  observation midpoints plus the mission boundaries

## Canonical Benchmark Shape

The intended repository structure is:

```text
benchmarks/revisit_constellation/
├── dataset/
├── generator.py
├── verifier/
│   ├── __init__.py
│   ├── models.py
│   ├── io.py
│   ├── engine.py
│   └── run.py
└── README.md
```

Current CLI entry:

```bash
uv run python -m benchmarks.revisit_constellation.verifier.run <case_dir> <solution.json>
```

Associated test-side artifacts are expected under:

```text
tests/fixtures/
tests/benchmarks/
```

## Near-Term Design Questions

The following details may still evolve as the generator and canonical dataset
are built:

- the exact canonical dataset cases
- whether any additional orbit admissibility constraints should be added later
- whether the public verifier should keep its phase-1 sampled interval checks or
  move to more exact event handling
- whether any golden metric fixtures should be added beyond small corner cases

## Implementation Direction

This benchmark should be built as a new standalone benchmark, even if parts of
`revisit_optimization` are reused as raw ingredients or migration references.

The expected implementation sequence is:

1. implement the verifier around the settled contract
2. create fixtures and focused tests
3. add a generator and generate the canonical dataset
4. retire `revisit_optimization` once the replacement is complete
