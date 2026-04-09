# Regional Coverage Benchmark

## Problem

Plan strip observations over polygonal regions of interest to maximize unique regional coverage over a fixed planning horizon.

The benchmark models a compact SAR-like regional imaging problem:

- real satellites with frozen TLEs
- verifier-owned strip geometry derived from timed roll-only actions
- same-satellite retargeting limits
- battery feasibility with sunlit charging
- benchmark-owned fine-grid coverage scoring

The benchmark intentionally does **not** model storage, downlink, ground stations, cloud cover, or detailed SAR processing.

## Unit contract

All public quantities use SI units or degrees:

| Quantity | Unit | Suffix |
|---|---|---|
| distance, altitude | meters | `_m` |
| area | square meters | `_m2` |
| time, duration | seconds | `_s` |
| angle | degrees | `_deg` |
| angular rate | deg/s | `_deg_per_s` |
| angular acceleration | deg/s² | `_deg_per_s2` |
| energy | watt-hours | `_wh` |
| power | watts | `_w` |
| timestamps | ISO 8601 with `Z` or explicit offset | — |

## Dataset structure

```text
dataset/
├── index.json
├── example_solution.json
└── cases/
    └── case_0001/
        ├── manifest.json
        ├── satellites.yaml
        ├── regions.geojson
        └── coverage_grid.json
```

The current canonical release contains 5 cases. Each case is self-contained.
The verifier reads one case directory and one per-case solution file.

The dataset-level `example_solution.json` is a minimal runnable example:

```json
{
  "actions": []
}
```

`dataset/index.json` includes `example_smoke_case_id`, which currently points to `case_0001`.

## Canonical case family

The generator currently emits:

- 5 canonical cases
- 72 hour horizons
- 6 to 12 satellites per case
- 2 to 3 regions per case in the current release
- 1 or 2 satellite classes per case
- approximately 5,000 to 20,000 weighted coverage samples per case

The current public cases use a mild two-class family:

- `sar_narrow`
- `sar_wide`

These are benchmark abstractions, not claims that the benchmark reproduces a specific flight program.

## Case file formats

### `manifest.json`

Case-level metadata and verifier configuration:

```json
{
  "case_id": "case_0001",
  "benchmark": "regional_coverage",
  "spec_version": "v1",
  "seed": 20260408,
  "horizon_start": "2025-07-17T00:00:00Z",
  "horizon_end": "2025-07-20T00:00:00Z",
  "time_step_s": 10,
  "coverage_sample_step_s": 5,
  "earth_model": {
    "shape": "wgs84"
  },
  "grid_parameters": {
    "sample_spacing_m": 5000.0
  },
  "scoring": {
    "primary_metric": "coverage_ratio",
    "revisit_bonus_alpha": 0.0,
    "max_actions_total": 64
  }
}
```

`time_step_s` is the public action grid. `coverage_sample_step_s` is the verifier sampling step for strip geometry and the current power integration mesh.

### `satellites.yaml`

A YAML sequence. Each satellite entry defines:

```yaml
- satellite_id: sat_iceye-x2
  tle_line1: str
  tle_line2: str
  tle_epoch: ISO8601

  sensor:
    min_edge_off_nadir_deg: float
    max_edge_off_nadir_deg: float
    cross_track_fov_deg: float
    min_strip_duration_s: float
    max_strip_duration_s: float

  agility:
    max_roll_rate_deg_per_s: float
    max_roll_acceleration_deg_per_s2: float
    settling_time_s: float

  power:
    battery_capacity_wh: float
    initial_battery_wh: float
    idle_power_w: float
    imaging_power_w: float
    slew_power_w: float
    sunlit_charge_power_w: float
    imaging_duty_limit_s_per_orbit: float | null
```

The verifier uses:

- TLE + Brahe SGP4 propagation
- GCRF as the inertial frame
- ITRF as the Earth-fixed frame
- WGS84 for Earth intersection and geodetic conversion

### `regions.geojson`

Human-readable region definitions in RFC 7946 GeoJSON.

Each feature contains:

```json
{
  "type": "Feature",
  "properties": {
    "region_id": "region_001",
    "weight": 1.0,
    "min_required_coverage_ratio": 0.25
  },
  "geometry": {
    "type": "Polygon",
    "coordinates": [[[lon, lat], ...]]
  }
}
```

`min_required_coverage_ratio` is optional.

### `coverage_grid.json`

Machine-readable scoring support data owned by the benchmark.

The current canonical schema is weighted sample points:

```json
{
  "grid_version": 1,
  "sample_spacing_m": 5000.0,
  "regions": [
    {
      "region_id": "region_001",
      "total_weight_m2": 123456789.0,
      "samples": [
        {
          "sample_id": "region_001_s000001",
          "longitude_deg": 90.0,
          "latitude_deg": 1.0,
          "weight_m2": 25000000.0
        }
      ]
    }
  ]
}
```

Each sample belongs to exactly one region and contributes unique coverage weight once by default.

## Solution format

The public solution is a single JSON object:

```json
{
  "actions": [
    {
      "type": "strip_observation",
      "satellite_id": "sat_iceye-x2",
      "start_time": "2025-07-17T03:31:00Z",
      "duration_s": 20,
      "roll_deg": 20.0
    }
  ]
}
```

Only one action type is defined publicly: `"strip_observation"`.

The verifier ignores unknown action types, but benchmark users should only submit `strip_observation` actions.

The solution must not include:

- user-authored strip polygons
- user-authored strip centerlines
- user-authored coverage claims
- precomputed access-window identifiers

## Strip and attitude model

The benchmark uses a generic angular strip sensor with a roll-only pointing model.

For an action:

- `roll_deg` is the signed strip-center off-nadir look angle
- `cross_track_fov_deg` is the full cross-track angular field of view

Define:

```text
r = abs(roll_deg)
f = cross_track_fov_deg
theta_inner_deg = r - 0.5 * f
theta_outer_deg = r + 0.5 * f
```

The action is sensor-valid only when:

```text
theta_inner_deg >= min_edge_off_nadir_deg
theta_outer_deg <= max_edge_off_nadir_deg
```

The verifier derives strip geometry by propagating the satellite through the action interval, intersecting the center, inner-edge, and outer-edge rays with the WGS84 ellipsoid, and sweeping those edge hits through time into strip segments.

Ground width is therefore derived from orbit geometry and attitude. The benchmark does not use a fixed stored swath width.

## Hard validity rules

The verifier rejects a solution as invalid if any of the following hold:

- `satellite_id` is unknown
- `start_time` is outside the case horizon
- `duration_s <= 0`
- `duration_s` is not an integer multiple of `time_step_s`
- `start_time` is not aligned to the `time_step_s` grid
- `duration_s` is outside the satellite sensor bounds
- `theta_inner_deg` or `theta_outer_deg` violates the sensor off-nadir band
- a strip ray fails to intersect the Earth
- two same-satellite strip observations overlap in time
- the same-satellite gap is smaller than required slew time plus settling time
- battery state falls below zero
- `imaging_duty_limit_s_per_orbit` is exceeded when present
- a region-level `min_required_coverage_ratio` is not met when present

The benchmark does **not** expose public precomputed access windows. Strip accessibility is owned by the verifier.

## Slew model

Same-satellite retargeting uses the repository bang-coast-bang / trapezoidal minimum-slew-time model.

For two consecutive same-satellite actions:

```text
d = abs(current.roll_deg - previous.roll_deg)
omega = max_roll_rate_deg_per_s
alpha = max_roll_acceleration_deg_per_s2
d_tri = omega^2 / alpha

if d <= d_tri:
    t_slew = 2 * sqrt(d / alpha)
else:
    t_slew = d / omega + omega / alpha

t_required_gap = t_slew + settling_time_s
```

The benchmark measures slew from commanded roll delta, not from passive ground-track drift.

## Power model

The benchmark uses one battery state-of-charge per satellite with binary sunlit/eclipsed charging and piecewise-constant loads.

Generation:

- `sunlit_charge_power_w` when sunlit
- `0` when eclipsed

Loads:

- `idle_power_w` continuously
- `imaging_power_w` while imaging
- `slew_power_w` during required retargeting windows

Current implementation rule:

- deterministic fixed-step integration on the verifier-owned 5 second mesh used by canonical cases
- sunlight is evaluated at interval midpoints

Discrete update:

```text
E_next = clamp(E_curr + (P_charge_w - P_load_w) * delta_t_s / 3600, 0, E_max)
```

A solution is invalid if battery state becomes negative at any time.

## Coverage scoring

Coverage is scored on the benchmark-owned fine grid in `coverage_grid.json`, not on exact polygon union.

For each sample `i` with weight `w_i` and coverage count `c_i`:

```text
u_i = 1 if c_i >= 1 else 0
```

Per-region coverage:

```text
coverage_ratio_r = sum_i(w_i * u_i) / sum_i(w_i)
```

Global coverage:

```text
coverage_ratio =
    sum_r(region_weight_r * coverage_ratio_r) / sum_r(region_weight_r)
```

Default revisit behavior:

- first-time coverage gets full credit
- repeated coverage gets no extra credit
- `revisit_bonus_alpha` is present in the schema but is `0.0` in the canonical release

## Verifier output

The verifier returns a JSON report with this top-level structure:

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
    "region_coverages": {}
  },
  "violations": [],
  "diagnostics": {}
}
```

Important metric fields:

- `coverage_ratio`
- `covered_weight_m2_equivalent`
- `num_actions`
- `total_imaging_time_s`
- `total_imaging_energy_wh`
- `total_slew_angle_deg`
- `min_battery_wh`
- `region_coverages`

The primary ranking order is:

1. `valid = true`
2. maximize `coverage_ratio`
3. maximize `covered_weight_m2_equivalent`
4. minimize `total_imaging_energy_wh`
5. minimize `total_slew_angle_deg`
6. minimize `num_actions`

## What is intentionally out of scope

- storage
- downlink and ground stations
- cloud cover and daylight gating
- radiometry and SAR image formation
- thermal submodels
- reaction wheel momentum dumping
- solver-side access windows

## Running the tools

### Verifier

```bash
uv run python benchmarks/regional_coverage/verifier.py \
    benchmarks/regional_coverage/dataset/cases/case_0001 \
    benchmarks/regional_coverage/dataset/example_solution.json
```

The verifier exits with code `0` when valid and `1` when invalid.

### Generator

```bash
# Rebuild the canonical dataset in-place.
uv run python -m benchmarks.regional_coverage.generator.run

# Write the dataset to another directory.
uv run python -m benchmarks.regional_coverage.generator.run \
    --dataset-dir /tmp/regional_coverage_dataset
```

Running the generator with no flags rewrites the canonical dataset under `benchmarks/regional_coverage/dataset/`, including:

- `dataset/cases/`
- `dataset/index.json`
- `dataset/example_solution.json`

### Visualizer

The visualizer is intended for benchmark inspection and fixture authoring.

```bash
# 2D case overview PNG.
uv run python -m benchmarks.regional_coverage.visualizer.run overview \
    benchmarks/regional_coverage/dataset/cases/case_0001

# Solution inspection bundle with 3D strip geometry HTML and region-scale PNGs.
uv run python -m benchmarks.regional_coverage.visualizer.run inspect \
    benchmarks/regional_coverage/dataset/cases/case_0001 \
    path/to/solution.json
```

Generated visualizer artifacts are written under `benchmarks/regional_coverage/visualizer/plots/`.
