# Revisit Constellation Benchmark

## Status

This benchmark is implemented and is the canonical revisit-focused constellation-design benchmark in this repository.

It replaces the earlier `revisit_optimization` benchmark.

## Problem Summary

Design an Earth observation constellation and an operating schedule that keeps target revisit gaps as small as possible over a mission horizon.

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

The architecture-design part of the benchmark means defining the initial states of satellites at mission start time. At a high level, a solver chooses how many satellites to deploy, up to the case-specific cap, and specifies each satellite's initial state in the GCRF frame.

The scheduling part of the benchmark means producing a feasible action sequence for that constellation over the mission horizon.

Launch design, launch cost, and deployment operations are out of scope. The benchmark assumes that the proposed satellites already exist in their initial states at the mission start time.

## Case Inputs

Each canonical case contains exactly two machine-readable files:

- `assets.json`
- `mission.json`

### `assets.json`

`assets.json` contains the shared satellite model and satellite-count cap for the case.

- `satellite_model`
  - `model_name`
  - `sensor`
    - `max_off_nadir_angle_deg`
    - `max_range_m`
    - `obs_discharge_rate_w`
  - `resource_model`
    - `battery_capacity_wh`
    - `initial_battery_wh`
    - `idle_discharge_rate_w`
    - `sunlight_charge_rate_w`
  - `attitude_model`
    - `max_slew_velocity_deg_per_sec`
    - `max_slew_acceleration_deg_per_sec2`
    - `settling_time_sec`
    - `maneuver_discharge_rate_w`
  - `min_altitude_m`
  - `max_altitude_m`
- `max_num_satellites`

### `mission.json`

`mission.json` contains the mission horizon and target-specific revisit requirements:

- `horizon_start`
- `horizon_end`
- `targets[]`
  - `id`
  - `name`
  - `latitude_deg`
  - `longitude_deg`
  - `altitude_m`
  - `expected_revisit_period_hours` (required revisit cadence as a period in hours)
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

Each action includes:

- `action_type`
- `satellite_id`
- `start`
- `end`

Observation actions also include:

- `target_id`

## Validity Rules

Constraint violations should invalidate a solution immediately. In other words, metrics are only meaningful for solutions that satisfy all hard constraints.

The verifier is expected to reject a solution if any of the following occur:

- malformed solution structure
- more satellites than the case permits
- satellite initial states that violate orbit constraints
- infeasible observation geometry
- power constraint violations
- inconsistent action timing
- overlapping action timing
- references to unknown satellites or targets

Additional hard-validity checks may be added as the schema becomes more concrete.

## Metrics And Ranking

The legacy mapping-coverage branch is intentionally removed from this benchmark.
The new benchmark is purely revisit-driven.

The verifier reports these metrics for valid solutions:

- `capped_max_revisit_gap_hours`: per-target max revisit gap floored at that target's expected revisit period, then aggregated by maximum
- `num_satellites`
- `target_gap_summary`: per-target breakdown with `expected_revisit_period_hours`, `max_revisit_gap_hours`, `mean_revisit_gap_hours`, and `observation_count`

The intended ranking logic is:

1. Valid solutions beat invalid solutions.
2. Minimize `capped_max_revisit_gap_hours`.
3. Minimize `num_satellites`.

## Revisit Interpretation

The benchmark treats poor revisit performance as poor scoring, not as an automatic validity failure.

Successful observations are represented by their midpoint times. Revisit gaps include the mission start and mission end as boundary times:

- zero successful observations: the revisit gap is the full mission horizon
- one successful observation: gaps are start-to-observation and observation-to-end
- multiple successful observations: gaps are computed between consecutive observation midpoints plus the mission boundaries

## Simulation Scenario

This section describes the physics and resource models used by the verifier.

### Orbital Propagation

Satellite states are propagated using `brahe.NumericalOrbitPropagator`:

- **Force model**: J2-only gravity (`spherical_harmonic(2, 0)` in `brahe`)
- **Frame**: GCRF/ECI for propagation, ECEF for geometry checks
- **Time system**: UTC
- **EOP**: Zero-valued static EOP provider for deterministic, offline-friendly verification

The verifier validates initial satellite states against case-specific altitude bounds (min/max). Initial states must form closed elliptic orbits (perigee and apogee within bounds).

### Visibility Computation

Observation geometry is validated at 10-second intervals during actions:

**Target visibility constraints**:
- Elevation angle above target's minimum (local ENU frame)
- Slant range within target's maximum and sensor maximum
- Off-nadir angle within the sensor's maximum off-nadir pointing limit

The current sensor model is a nadir-centered pointing cone, not a full imaging footprint model. A target is observable only when its line of sight stays within `max_off_nadir_angle_deg` of nadir.

All geometric checks use the instantaneous satellite position propagated to the sample time. The fixed 10-second sampling balances correctness with runtime; brief violations between samples may not be detected.

### Onboard Resources

Resource accounting simulates battery state at discrete time points:

**Power model**:
- Sunlight detection via `brahe` eclipse calculation
- Charging when sunlit at `sunlight_charge_rate_w`
- Discharging components:
  - Idle: `idle_discharge_rate_w`
  - Observation: +`obs_discharge_rate_w`
  - Maneuver: +`maneuver_discharge_rate_w` during slew/settling windows

Resource checks occur at action boundaries, maneuver window boundaries, and 30-second intervals. Battery level is clamped to the capacity upper bound, and only depletion below zero invalidates the solution.

### Attitude and Maneuver Windows

Between consecutive observations, the verifier computes required slew time using a bang-coast-bang slew profile:

- Maximum slew velocity and acceleration limits from `attitude_model`
- Settling time added after slew completes
- Maneuver windows must not overlap with any other action
- Computed slew angle uses target vectors at observation midpoints

The verifier does not validate pointing during the observation itself—only that the geometry allows acquisition and that sufficient time exists to slew between consecutive targets.

## Verifier Output

The verifier returns a JSON object with:

- `is_valid`
- `metrics`
- `errors`
- `warnings`

CLI entry:

```bash
uv run python -m benchmarks.revisit_constellation.verifier.run <case_dir> <solution.json>
```

## Canonical Benchmark Shape

The repository structure is:

```text
benchmarks/revisit_constellation/
├── dataset/
│   ├── README.md
│   ├── index.json
│   ├── example_solution.json
│   └── cases/
│       └── <split>/<case_id>/{assets.json,mission.json}
├── splits.yaml
├── generator/
│   ├── __init__.py
│   ├── build.py
│   ├── sources.py
│   └── run.py
├── verifier/
│   ├── __init__.py
│   ├── models.py
│   ├── io.py
│   ├── engine.py
│   └── run.py
└── README.md
```

Associated test-side artifacts live under:

```text
tests/fixtures/
tests/benchmarks/
```

## Canonical Dataset

The committed dataset lives under `dataset/cases/<split>/` and includes dataset-level metadata in `dataset/index.json`. The current canonical dataset publishes five `test` cases: `case_0001` through `case_0005`.

The canonical generator entry point is:

```bash
uv run python -m benchmarks.revisit_constellation.generator.run \
  benchmarks/revisit_constellation/splits.yaml
```

Downloaded raw source CSVs are stored under the dataset directory by default at `dataset/source_data/`. The committed dataset-construction parameters live in `benchmarks/revisit_constellation/splits.yaml`; runtime source-management controls such as `--download-dir` and `--force-download` remain optional CLI overrides around the documented Kaggle download step.
