# Regional Coverage SPEC

Status: tracked development spec for the `regional_coverage` benchmark redesign.

This document is a temporary tracked benchmark-development artifact. The intended end-state is that its stable public content will be absorbed into [`benchmarks/regional_coverage/README.md`](/home/betelgeuse/Developments/AstroReason-Bench/benchmarks/regional_coverage/README.md) once the benchmark is finished.

This spec is written with the repository benchmark contract as a hard design constraint. See [`docs/benchmark_contract.md`](/home/betelgeuse/Developments/AstroReason-Bench/docs/benchmark_contract.md).

## 1. Purpose

`regional_coverage` is a regional strip-imaging planning benchmark.

The space agent receives:

- a fixed planning horizon
- a set of frozen Earth-observation satellites
- a set of geographic polygon regions of interest
- per-satellite sensing, agility, and power limits

The space agent must return a schedule of strip-observation actions that maximizes unique regional coverage while satisfying hard physical constraints.

This redesign intentionally removes storage and downlink modeling. Power remains in scope.

## 2. Design Goals

The redesign must satisfy the following repository-level goals:

- Benchmark-core, not solution-core.
- Standalone verifier and generator owned by this repository.
- Algorithm-agnostic public interface.
- Deterministic and offline-friendly evaluation.
- Hard to game through user-authored geometry.
- Physically meaningful without becoming a full mission operations simulator.

## 3. Contract Alignment

The finished benchmark must conform to [`docs/benchmark_contract.md`](/home/betelgeuse/Developments/AstroReason-Bench/docs/benchmark_contract.md).

The intended finished shape is:

```text
benchmarks/regional_coverage/
├── README.md
├── generator/
│   └── run.py
├── verifier.py
├── SPEC.md                  # temporary tracked development artifact
└── dataset/
    ├── example_solution.json
    ├── index.json
    └── cases/
        └── case_0001/
            ├── manifest.json
            ├── satellites.yaml
            ├── regions.geojson
            └── coverage_grid.json
```

Notes:

- `generator/run.py` is the canonical public generator entrypoint.
- `verifier.py` is the canonical public verifier entrypoint.
- The verifier public CLI accepts `case_dir` and `solution_path` as positional arguments.
- `dataset/example_solution.json` is a single per-case solution object, not a mapping.
- `dataset/index.json` is optional by contract, but this benchmark will provide it.
- The generator owns only generator-owned dataset artifacts. It must not write `dataset/README.md`.
- `SPEC.md` is temporary and should be absorbed into the public README before promotion to finished status.

Intended finished-benchmark metadata once promoted:

- `repro_ci: true`
- `generated_paths`:
  - `dataset/cases`
  - `dataset/index.json`
  - `dataset/example_solution.json`

## 4. Benchmark Summary

### 4.1 Core formulation

The canonical formulation is:

- timed strip-observation actions proposed by the solver
- verifier-derived strip geometry
- benchmark-owned coverage discretization
- hard feasibility constraints on timing, agility, and power

This benchmark does not accept solver-authored strip polylines, strip polygons, or declared covered areas.

### 4.2 Default sensing posture

The benchmark uses a generic angular strip-sensor abstraction with SAR-like operational defaults.

This means:

- the geometric model is generic and not tied to a single real sensor family
- the canonical public cases do not require daylight gating
- the canonical public cases do not model cloud cover
- the power model remains important and binding

This preserves deterministic evaluation while still giving a strong reason for power-aware scheduling.

### 4.3 What this benchmark is and is not

In scope:

- orbital visibility and strip geometry
- roll-limited strip imaging
- same-satellite retargeting / slew feasibility
- battery state-of-charge feasibility
- unique regional coverage scoring

Out of scope:

- storage
- downlink and ground stations
- cloud cover
- radiometry, image quality, and SAR processing details
- thermal submodels
- reaction wheel momentum dumping
- solver-side access windows

## 5. Canonical Physical Abstraction

### 5.1 Propagation and frames

The verifier uses one pinned astrodynamics stack consistently, following the frame guidance in [`docs/benchmark_contract.md`](/home/betelgeuse/Developments/AstroReason-Bench/docs/benchmark_contract.md):

- TLE input
- `brahe`-based SGP4 propagation
- GCRF as the inertial frame
- ITRF as the Earth-fixed frame

All geometry, sunlight, and coverage behavior must be produced from this one stack. The final public README and tests must explicitly document the pinned conventions used by the implementation.

### 5.1.1 Earth shape for geometry

Earth-intersection and geodetic conversions use the WGS84 ellipsoid in ITRF coordinates.

This is the intended public geometry convention for:

- ray/ellipsoid intersection
- region sample coordinates
- derived strip footprints

### 5.2 Sensor model

The benchmark uses a generic angular strip sensor.

Each satellite exposes:

- `min_edge_off_nadir_deg`
- `max_edge_off_nadir_deg`
- `cross_track_fov_deg`
- `min_strip_duration_s`
- `max_strip_duration_s`

Interpretation:

- A strip observation holds a constant strip-center pointing during the action.
- The action's `roll_deg` is the signed center off-nadir look angle.
- Let `f = cross_track_fov_deg`.
- Let `r = abs(roll_deg)`.
- The strip's inner and outer edge look angles are:
  - `theta_inner_deg = r - 0.5 * f`
  - `theta_outer_deg = r + 0.5 * f`
- Hard validity requires:
  - `theta_inner_deg >= min_edge_off_nadir_deg`
  - `theta_outer_deg <= max_edge_off_nadir_deg`

Ground width is derived from orbit geometry and attitude, not stored as a constant swath width.

This deliberately replaces the transitional benchmark's fixed `swath_width_km` model.

### 5.3 Attitude model

The canonical public benchmark uses a roll-only strip pointing model:

- no free yaw choice
- no arbitrary strip azimuth choice
- strip axis follows the satellite ground-track direction during the action

This keeps the task focused on regional coverage planning rather than full three-axis attitude design.

### 5.4 Strip geometry

For each sample time `t` during an action:

1. Propagate the satellite state to obtain satellite position in GCRF and ITRF.
2. Construct the spacecraft local frame needed for nadir-relative roll pointing.
3. Construct three boresight rays:
   - center ray at `roll_deg`
   - inner edge ray at `sign(roll_deg) * theta_inner_deg`
   - outer edge ray at `sign(roll_deg) * theta_outer_deg`
4. Intersect those rays with Earth.
5. Sweep the edge intersections through time to form the strip footprint.

The implementation may represent the swept strip as:

- a sequence of adjacent quadrilateral segments between consecutive sample times, or
- an equivalent deterministic footprint representation

The public semantics are that strip geometry is verifier-owned and derived from time, orbit, and attitude.

## 6. Regions and coverage model

### 6.1 Regions

Each case contains polygonal regions of interest in WGS84 longitude/latitude via `regions.geojson`.

Each region has:

- `region_id`
- polygon geometry
- optional `weight`
- optional `min_required_coverage_ratio`

Canonical public cases should avoid antimeridian crossing and polar edge cases unless explicitly introduced as dedicated robustness cases.

### 6.2 Authoritative coverage scoring

Coverage is scored on a benchmark-owned fine coverage grid, not on exact footprint polygon union.

The public regions remain polygons. The scoring path is:

1. verifier derives physical strip geometry from actions
2. verifier maps those strips onto benchmark-owned coverage samples
3. unique covered sample weight determines the score

This is the authoritative metric path.

### 6.3 Coverage grid

Each case contains `coverage_grid.json`, derived by the generator from the public region polygons.

The grid contains weighted sample cells or weighted sample points, all owned by the benchmark. The exact storage format can be finalized during implementation, but the public semantics are:

- each sample belongs to one region
- each sample has a fixed coverage weight
- total region weight approximates region area
- coverage credit is awarded once by default

Grid resolution is part of the benchmark design, not an implementation accident. The generator must keep the grid comfortably finer than the minimum effective strip width in the case family.

Default target:

- nominal sample spacing around `min_effective_strip_width / 5` to `min_effective_strip_width / 8`

Generator validation must include a stability check so benchmark scores are not materially changed by a modest refinement of the grid on validation fixtures.

### 6.3.1 Canonical `coverage_grid.json` schema

Phase 1 freezes the default public schema as weighted sample points.

Canonical logical shape:

```json
{
  "grid_version": 1,
  "sample_spacing_m": 4000.0,
  "regions": [
    {
      "region_id": "region_001",
      "total_weight_m2": 123456789.0,
      "samples": [
        {
          "sample_id": "region_001_s000001",
          "longitude_deg": -120.5,
          "latitude_deg": 37.2,
          "weight_m2": 16000000.0
        }
      ]
    }
  ]
}
```

Frozen field names:

- `grid_version`
- `sample_spacing_m`
- `regions`
- `region_id`
- `total_weight_m2`
- `samples`
- `sample_id`
- `longitude_deg`
- `latitude_deg`
- `weight_m2`

### 6.4 Optional future refinement

If `coverage_grid.json` proves too bulky in practice, the benchmark may move to a deterministic verifier-derived grid generated from `regions.geojson` and manifest grid parameters. That change must be made before finished-benchmark promotion, not after.

## 7. Canonical dataset shape and release targets

### 7.1 Canonical public release target

The first canonical public release should target:

- `5` canonical cases
- one canonical dataset split only
- one dataset-level `example_solution.json`

### 7.1.1 Example solution convention

The dataset-level example solution is a minimal runnable solution object:

```json
{
  "actions": []
}
```

This benchmark intentionally uses an empty action list as its default smoke-test example unless later implementation discovers a stronger reason to prefer a single valid strip action.

### 7.2 Planning horizon

Recommended release target:

- default horizon per case: `72 h`

Allowed case-family range during generation experiments:

- `48 h` to `96 h`

### 7.3 Satellite counts and classes

Recommended release target per case:

- `6` to `12` satellites
- `1` or `2` satellite classes per case

Class philosophy:

- mild heterogeneity only
- same core sensor/attitude/power semantics across all satellites
- parameter differences should create planning tradeoffs without creating a type-system benchmark

### 7.4 TLE pool

The generator should sample from a curated vendored pool of real high-inclination LEO satellites.

Recommended initial source strategy:

- seed the pool from the current transitional `ICEYE`-family satellites
- expand to roughly `12` to `16` real near-polar satellites if needed
- do not mix `SKYSAT` optical-style satellites into the canonical SAR-like public release

This keeps continuity with the current benchmark while aligning the public task with its new SAR-like operational assumptions.

### 7.5 Region counts and sizes

Recommended release target per case:

- `2` to `4` regions
- `4` to `12` vertices per region
- per-region area roughly `25,000` to `180,000 km^2`
- total case target area roughly `100,000` to `450,000 km^2`

These ranges are chosen so:

- one strip never solves a region
- multiple strips per region are necessary
- the full case is not trivially coverable under power and agility constraints

### 7.6 Coverage grid size

Recommended target:

- approximately `5,000` to `20,000` weighted samples per case

This is intended to keep scoring stable without making fixtures or verifier runtime unwieldy.

### 7.7 Generator-side parameter ranges

Recommended release-time parameter bands:

Sensor:

- `cross_track_fov_deg`: `2.0` to `6.0`
- `min_edge_off_nadir_deg`: `15.0` to `25.0`
- `max_edge_off_nadir_deg`: `30.0` to `45.0`
- `min_strip_duration_s`: `20` to `30`
- `max_strip_duration_s`: `120` to `240`

Agility:

- `max_roll_rate_deg_per_s`: `1.0` to `2.5`
- `max_roll_acceleration_deg_per_s2`: `0.3` to `1.2`
- `settling_time_s`: `1.0` to `4.0`

Power:

- `battery_capacity_wh`: `600` to `1800`
- `initial_battery_wh`: `0.4` to `0.8` of capacity
- `idle_power_w`: `60` to `140`
- `imaging_power_w`: `180` to `500`
- `slew_power_w`: `20` to `80`
- `sunlit_charge_power_w`: `120` to `320`
- optional `imaging_duty_limit_s_per_orbit`: `600` to `1800`

These are release-target bands, not promises that every final case uses the full range.

## 8. Solution contract

### 8.1 Solution file shape

The canonical solution is a single JSON object:

```json
{
  "actions": [
    {
      "type": "strip_observation",
      "satellite_id": "sat_001",
      "start_time": "2026-01-01T08:16:00Z",
      "duration_s": 120,
      "roll_deg": 22.5
    }
  ]
}
```

The verifier ignores unknown action types, but the public benchmark only defines `"strip_observation"`.

### 8.2 Action fields

Each strip observation action includes:

- `type`
- `satellite_id`
- `start_time`
- `duration_s`
- `roll_deg`

No geometry is accepted from the solver.

Rejected solution features:

- user-authored strip centerlines
- user-authored strip polygons
- user-authored registered strips
- user-authored coverage claims
- any access-window identifier as a required canonical field

### 8.3 Time conventions

Public timestamps use ISO 8601 with `Z` or explicit UTC offset.

Verifier rules:

- timestamps must be timezone-aware
- all action start times must lie on the case time grid
- `duration_s` must be an integer multiple of `time_step_s`

This keeps the public contract human-readable while preserving deterministic sampling.

Additional hard validity rules:

- `duration_s > 0`
- `duration_s >= min_strip_duration_s`
- `duration_s <= max_strip_duration_s`
- `len(actions) <= max_actions_total` if that limit is present in the case manifest

## 9. Case file contract

### 9.1 `manifest.json`

`manifest.json` holds case-level metadata and verifier configuration:

- `case_id`
- `benchmark`
- `spec_version`
- `seed`
- `horizon_start`
- `horizon_end`
- `time_step_s`
- `coverage_sample_step_s`
- `earth_model`
- `grid_parameters`
- `scoring`
- optional `difficulty_tags`

The `scoring` block includes:

- `primary_metric`
- `revisit_bonus_alpha`
- `max_actions_total`

Recommended defaults:

- `time_step_s = 10`
- `coverage_sample_step_s = 5`
- `primary_metric = "coverage_ratio"`
- `revisit_bonus_alpha = 0.0`

Canonical logical shape:

```json
{
  "case_id": "case_0001",
  "benchmark": "regional_coverage",
  "spec_version": "v1",
  "seed": 20260408,
  "horizon_start": "2026-01-01T00:00:00Z",
  "horizon_end": "2026-01-04T00:00:00Z",
  "time_step_s": 10,
  "coverage_sample_step_s": 5,
  "earth_model": {
    "shape": "wgs84"
  },
  "grid_parameters": {
    "sample_spacing_m": 4000.0
  },
  "scoring": {
    "primary_metric": "coverage_ratio",
    "revisit_bonus_alpha": 0.0,
    "max_actions_total": 64
  }
}
```

### 9.2 `satellites.yaml`

A YAML sequence. Each satellite entry includes:

- `satellite_id`
- `tle_line1`
- `tle_line2`
- `tle_epoch`
- `sensor`
  - `min_edge_off_nadir_deg`
  - `max_edge_off_nadir_deg`
  - `cross_track_fov_deg`
  - `min_strip_duration_s`
  - `max_strip_duration_s`
- `agility`
  - `max_roll_rate_deg_per_s`
  - `max_roll_acceleration_deg_per_s2`
  - `settling_time_s`
- `power`
  - `battery_capacity_wh`
  - `initial_battery_wh`
  - `idle_power_w`
  - `imaging_power_w`
  - `slew_power_w`
  - `sunlit_charge_power_w`
  - optional `imaging_duty_limit_s_per_orbit`

Mild heterogeneity is allowed, but the public case family should remain limited to one or two satellite classes per case.

### 9.3 `regions.geojson`

`regions.geojson` is the human-readable region definition file.

Each feature must contain:

- `region_id`
- `weight` defaulting to `1.0`
- optional `min_required_coverage_ratio`

Coordinates follow RFC 7946 ordering:

- `[longitude, latitude]`

This intentionally removes the transitional benchmark's `[lat, lon]` polygon ordering.

### 9.4 `coverage_grid.json`

`coverage_grid.json` is benchmark-owned machine-readable scoring support data.

Each entry must be sufficient to map derived strips onto weighted coverage samples. Exact storage layout may be optimized during implementation, but the public semantics must remain stable.

Expected logical fields:

- `region_id`
- sample coordinates
- per-sample weight
- optional precomputed region total weight

The canonical Phase 1 decision is that `coverage_grid.json` remains a public generator-owned per-case artifact.

### 9.5 `dataset/index.json`

The benchmark will provide `dataset/index.json` and use it as dataset metadata, not as a second source of truth for benchmark completion.

Canonical logical shape:

```json
{
  "benchmark": "regional_coverage",
  "spec_version": "v1",
  "generator_seed": 20260408,
  "example_smoke_case_id": "case_0001",
  "cases": [
    {
      "case_id": "case_0001",
      "path": "cases/case_0001",
      "horizon_hours": 72,
      "num_satellites": 8,
      "num_regions": 3,
      "total_region_area_m2": 210000000000.0,
      "satellite_class_ids": ["sar_narrow", "sar_wide"]
    }
  ]
}
```

Frozen field names:

- `benchmark`
- `spec_version`
- `generator_seed`
- `example_smoke_case_id`
- `cases`
- `case_id`
- `path`
- `horizon_hours`
- `num_satellites`
- `num_regions`
- `total_region_area_m2`
- `satellite_class_ids`

## 10. Verifier semantics

### 10.1 Verifier ownership

The verifier owns:

- orbit propagation
- frame conversion
- strip registration
- strip footprint derivation
- action timing validity
- same-satellite slew feasibility
- battery state-of-charge feasibility
- mapping strips onto the coverage grid
- score computation

The solver owns only the action list.

### 10.1.1 Verifier output schema

Canonical logical shape:

```json
{
  "valid": true,
  "metrics": {
    "coverage_ratio": 0.0,
    "covered_weight_m2_equivalent": 0.0,
    "num_actions": 0,
    "total_imaging_time_s": 0.0,
    "total_imaging_energy_wh": 0.0,
    "total_slew_angle_deg": 0.0,
    "min_battery_wh": 0.0,
    "region_coverages": {
      "region_001": {
        "covered_weight_m2_equivalent": 0.0,
        "total_weight_m2": 0.0,
        "coverage_ratio": 0.0
      }
    }
  },
  "violations": [],
  "diagnostics": {
    "actions": []
  }
}
```

Frozen top-level fields:

- `valid`
- `metrics`
- `violations`
- `diagnostics`

### 10.2 Strip derivation

For each valid action:

1. propagate the satellite state over the action interval
2. construct the strip-center viewing direction from `roll_deg`
3. derive inner and outer edge rays from the cross-track FOV
4. intersect those rays with Earth
5. build the swept strip geometry over the action interval
6. mark covered grid samples using benchmark-owned rules

The verifier may emit derived strip polygons or centerlines in diagnostics, but these are outputs only.

### 10.3 Accessibility model

There are no public precomputed access windows in canonical cases.

Accessibility is evaluated by the verifier from:

- the action time
- the satellite orbital state
- the sensor off-nadir bounds
- the attitude model
- Earth intersection feasibility
- same-satellite timing and power feasibility

An action that is physically valid but covers no benchmark-owned sample points is allowed but has zero marginal score.

### 10.4 Slew model

The verifier reuses the same bang-coast-bang / trapezoidal minimum-slew-time model already used in [`benchmarks/revisit_constellation`](/home/betelgeuse/Developments/AstroReason-Bench/benchmarks/revisit_constellation/README.md)
and [`benchmarks/stereo_imaging`](/home/betelgeuse/Developments/AstroReason-Bench/benchmarks/stereo_imaging/README.md).

Given:

- `d = abs(delta_roll_deg)`
- `omega = max_roll_rate_deg_per_s`
- `alpha = max_roll_acceleration_deg_per_s2`

Define:

- `d_tri = omega^2 / alpha`

Then:

- if `d <= d_tri`, `t_slew = 2 * sqrt(d / alpha)`
- else, `t_slew = d / omega + omega / alpha`

Required same-satellite gap:

- `t_required_gap = t_slew + settling_time_s`

Same-satellite action overlap is invalid.

### 10.5 Power model

The canonical power model is a single battery state-of-charge with binary sunlit/eclipsed charging and piecewise-constant loads.

Energy state:

- `E(t)` measured in Wh
- clamped to `[0, battery_capacity_wh]`

Generation:

- `sunlit_charge_power_w` when sunlit
- `0` when eclipsed

Loads:

- `idle_power_w` continuously
- `imaging_power_w` while a strip observation is active
- `slew_power_w` during required retargeting intervals

Recommended integration rule:

- event-driven exact integration over intervals where sunlight state and action
  state are constant

Equivalent discrete formula over a constant-power interval of duration
`delta_t_s`:

```text
E_next = clamp(E_curr + (P_charge_w - P_load_w) * delta_t_s / 3600, 0, E_max)
```

Feasibility rule:

- a solution is invalid if battery state becomes negative at any time

Optional extension:

- `imaging_duty_limit_s_per_orbit`

This can be used as a compact SAR-like duty-cycle proxy without introducing a full thermal model.

### 10.6 Sunlight rule

Sunlight status is derived by the verifier from the pinned `brahe` propagation and solar geometry stack.

The intended behavior matches the repository's existing minimal sunlight logic:

- the satellite charges when not in Earth shadow
- no penumbra or detailed panel-attitude submodel is introduced

### 10.7 Coverage scoring

Primary score:

- weighted unique coverage ratio over all regions

For each sample `i` with weight `w_i` and coverage count `c_i`:

- default unique credit `u_i = 1` if `c_i >= 1`, else `0`

For each region `r`:

- `coverage_ratio_r = sum_i(w_i * u_i) / sum_i(w_i)` over samples in region `r`

Global metric:

- `coverage_ratio = sum_r(region_weight_r * coverage_ratio_r) / sum_r(region_weight_r)`

Default revisit policy:

- first coverage receives full credit
- repeat coverage receives no extra credit

Optional future extension:

- small diminishing-return revisit bonus controlled by
  `revisit_bonus_alpha`, default `0.0`

One acceptable future form is:

- extra revisit credit proportional to `1 - 2^(-(c_i - 1))`, applied only when
  `c_i >= 2`

but this is disabled by default.

### 10.8 Ranking

Deterministic ranking order:

1. `valid = true`
2. maximize `coverage_ratio`
3. maximize `covered_weight_m2_equivalent` or equivalent total covered weight
4. minimize `total_imaging_energy_wh`
5. minimize `total_slew_angle_deg`
6. minimize `num_actions`

The exact metric names can be finalized during implementation, but the ordering above is the intended policy.

Phase 1 now freezes `covered_weight_m2_equivalent` as the preferred metric name for total covered weight.

## 11. Verifier output contract

The verifier returns a JSON report with at least:

```json
{
  "valid": true,
  "metrics": {
    "coverage_ratio": 0.0
  },
  "violations": [],
  "diagnostics": {}
}
```

Expected metric fields:

- `coverage_ratio`
- `covered_weight_m2_equivalent`
- `region_coverages`
- `num_actions`
- `total_imaging_time_s`
- `total_imaging_energy_wh`
- `total_slew_angle_deg`
- `min_battery_wh`

Expected diagnostics:

- per-action derived geometry summary
- per-satellite energy summary
- optional coverage debug summaries

## 12. Generator requirements

The generator must:

- build canonical dataset cases under `dataset/cases/`
- write `dataset/example_solution.json`
- write `dataset/index.json`
- derive regions and benchmark-owned coverage grids deterministically
- choose frozen TLEs close enough to horizon start for stable propagation
- generate cases where power and agility are binding
- avoid trivial full-coverage cases unless intentionally labeled easy

The generator must not:

- write solver-authored geometry templates
- write required public access windows
- write hidden solution hints disguised as opportunities

### 12.0.1 Generator-owned public artifacts

Phase 1 freezes the following as generator-owned canonical outputs:

- `dataset/cases/`
- `dataset/index.json`
- `dataset/example_solution.json`
- per-case `manifest.json`
- per-case `satellites.yaml`
- per-case `regions.geojson`
- per-case `coverage_grid.json`

### 12.1 Generator-side case construction rules

The generator should:

- sample `2` to `4` regions from a curated public region library
- sample `6` to `12` satellites from the vendored TLE pool
- assign one or two satellite classes per case
- target cases where a greedy all-first-pass plan is resource-constrained before
  full coverage
- reject candidate cases whose achievable coverage under basic feasibility
  heuristics is near `0%` or near `100%`

## 13. Tests and fixtures

The redesign must add focused tests under `tests/benchmarks/` and case-local fixtures under `tests/fixtures/`.

Minimum test categories:

- parser / schema validation
- timestamp and grid alignment rejection
- invalid unknown satellite references
- duration bound rejection
- same-satellite overlap rejection
- slew-boundary valid/invalid cases
- power-boundary valid/invalid cases
- off-nadir band valid/invalid cases
- deterministic coverage regression cases
- empty solution smoke case

Fixture philosophy:

- small exact cases for geometric and power regressions
- a few golden end-to-end cases for canonical dataset behavior

## 14. Migration from transitional benchmark

The transitional benchmark artifacts are not part of the target spec.

They should be removed from canonical public cases during the rebuild:

- `stations.yaml`
- `targets.yaml`
- `initial_plan.json`
- `mission_brief.md`
- solver-provided `registered_strips`
- fixed `swath_width_km` as the authoritative strip model

The new benchmark is not a patch over the transitional planner interface. It is a new canonical interface.

## 15. Open implementation notes

These are implementation notes, not unresolved product decisions:

- The exact public storage format of `coverage_grid.json` may be optimized if a large JSON becomes unwieldy, but benchmark-owned grid semantics are fixed by this spec.
- The final `brahe` propagation and frame-conversion implementation must be pinned in code and tests before benchmark promotion.
- The final public README should describe the strip-geometry model with enough detail that space agents can reason about it without reading verifier code.

## 16. Frozen design decisions

The following design choices are intentionally frozen by this spec:

- SAR-like default operating assumptions
- generic angular strip sensor, not fixed swath width
- geometry-free solver contract
- verifier-owned strip registration and accessibility checks
- no public precomputed access windows in canonical cases
- benchmark-owned fine grid scoring as the authoritative coverage metric
- power yes, storage no, downlink no
- unique coverage as the default scoring objective
- `brahe` + TLE + GCRF/ITRF as the pinned astrodynamics/frame direction
- reuse of the existing repository bang-coast-bang slew-time model
