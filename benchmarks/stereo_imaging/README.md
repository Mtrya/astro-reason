# Stereo Imaging Benchmark

## Problem

Plan optical satellite observations to acquire same-pass stereo or tri-stereo imagery over a set of ground targets.

The benchmark focuses on physically meaningful observation geometry and retargeting cost. It does not model photogrammetry internals, cloud cover, downlink, storage, or onboard power.

Given a set of real Earth-observation satellites with frozen TLEs and compact sensor and agility parameters, and a set of geo-referenced ground targets, the agent must produce a schedule of timed observation actions that maximizes stereo coverage and quality over a fixed planning horizon.

## Unit contract

All public quantities use SI units or degrees:

| Quantity | Unit | Suffix |
|---|---|---|
| distance, radius, altitude | meters | `_m` |
| area | square meters | `_m2` |
| time, duration | seconds | `_s` |
| speed | m/s | `_mps` |
| acceleration | m/s² | `_mps2` |
| angle | degrees | `_deg` |
| angular rate | deg/s | `_deg_per_s` |
| angular acceleration | deg/s² | `_deg_per_s2` |
| timestamps | ISO 8601 UTC strings | — |

## Dataset structure

```text
dataset/
├── index.json              # Case inventory and source provenance
├── example_solution.json   # Minimal actions for verifier smoke testing
└── cases/
    └── case_NNNN/
        ├── satellites.yaml
        ├── targets.yaml
        └── mission.yaml
```

Each case is self-contained. The verifier reads one case directory and one solution file.

## Case file formats

### `satellites.yaml`

A YAML sequence. Each entry defines one satellite:

```yaml
- id: str
  norad_catalog_id: int
  tle_line1: str
  tle_line2: str

  pixel_ifov_deg: float          # angular IFOV of one pixel, cross-track direction
  cross_track_pixels: int        # number of cross-track detector pixels
  max_off_nadir_deg: float       # max tilt from nadir; see combined-angle formula in Hard action constraints

  max_slew_velocity_deg_per_s: float
  max_slew_acceleration_deg_per_s2: float
  settling_time_s: float

  min_obs_duration_s: float
  max_obs_duration_s: float
```

The verifier derives swath geometry from the angular sensor model:

```text
cross_track_fov_deg    = cross_track_pixels * pixel_ifov_deg
half_cross_track_fov_deg = 0.5 * cross_track_fov_deg
strip_half_width_m     ≈ slant_range_m * tan(half_cross_track_fov_deg)
```

### `targets.yaml`

A YAML sequence. Each entry defines one ground target:

```yaml
- id: str
  latitude_deg: float
  longitude_deg: float
  aoi_radius_m: float       # radius of the area of interest around the target center
  elevation_ref_m: float    # reference terrain elevation

  scene_type: urban_structured | vegetated | rugged | open
```

`scene_type` captures stereo matching difficulty and occlusion behavior as a planning abstraction. Hard validity does not depend on `scene_type`; stereo quality scores do.

### `mission.yaml`

```yaml
mission:
  horizon_start: ISO8601
  horizon_end: ISO8601

  allow_cross_satellite_stereo: false
  allow_cross_date_stereo: false

  validity_thresholds:
    min_overlap_fraction: 0.80
    min_convergence_deg: 5.0
    max_convergence_deg: 45.0
    max_pixel_scale_ratio: 1.5
    min_solar_elevation_deg: 10.0
    near_nadir_anchor_max_off_nadir_deg: 10.0

  quality_model:
    pair_weights:
      geometry: 0.50
      overlap: 0.35
      resolution: 0.15
    tri_stereo_bonus_by_scene:
      urban_structured: 0.12
      rugged: 0.10
      vegetated: 0.08
      open: 0.05
```

## Solution format

The agent submits a JSON file. The file may be a single-case object or a multi-case mapping:

**Single-case:**
```json
{
  "actions": [
    {
      "type": "observation",
      "satellite_id": "sat_pleiades_1a",
      "target_id": "urban_paris_01",
      "start_time": "2026-06-18T10:00:00Z",
      "end_time": "2026-06-18T10:00:08Z",
      "off_nadir_along_deg": 5.0,
      "off_nadir_across_deg": -2.0
    }
  ]
}
```

Each action specifies the satellite, target, time window, and boresight steering angles in the satellite local frame. The verifier ignores actions with `type` values other than `"observation"`.

## Hard action constraints

The verifier rejects a solution as invalid if any of the following hold:

- `end_time` is not strictly after `start_time`
- the observation window falls outside the mission horizon
- observation duration is outside `[min_obs_duration_s, max_obs_duration_s]`
- combined boresight off-nadir angle exceeds `max_off_nadir_deg`, where the angle (in degrees) is $\arctan\sqrt{\tan^2\alpha + \tan^2\beta}$ with $\alpha$ = `off_nadir_along_deg` and $\beta$ = `off_nadir_across_deg` (tangents use radians). This is the same geometric tilt from nadir the verifier uses when forming the boresight ray from those steering angles.
- the boresight ray does not intersect the Earth surface
- two observations on the same satellite overlap in time
- the slew-plus-settle time between consecutive observations on the same satellite is insufficient
- an unknown `satellite_id` or `target_id` is referenced
- the solar elevation at the target center at observation midpoint is below `min_solar_elevation_deg`

## Verifier outputs

The verifier returns a JSON report:

```json
{
  "valid": true,
  "metrics": {
    "coverage_ratio": 0.0,
    "normalized_quality": 0.0
  },
  "violations": [],
  "derived_observations": [...],
  "diagnostics": {...}
}
```

**`valid`**: all hard constraints satisfied.

**`coverage_ratio`**: fraction of targets with at least one valid stereo or tri-stereo product.

**`normalized_quality`**: mean best-per-target stereo quality score across all targets.

**`derived_observations`**: per-action geometry computed by the verifier, including satellite ECEF state, boresight angles, solar angles, effective pixel scale, and access interval id.

**`diagnostics`**: per-valid-product details including convergence angle, B/H proxy, overlap fraction, pixel scale ratio, bisector elevation, and asymmetry.

## Stereo product definitions

### Valid stereo pair

Two observations `(i, j)` form a valid stereo pair when all of the following hold:

1. same `target_id`, `satellite_id`, and `access_interval_id`
2. AOI overlap fraction `>= min_overlap_fraction` (default 0.80)
3. convergence angle `min_convergence_deg <= gamma <= max_convergence_deg` (default 5–45 deg)
4. pixel scale ratio `max(s_i, s_j) / min(s_i, s_j) <= max_pixel_scale_ratio` (default 1.5)
5. all action-level hard constraints satisfied

### Valid tri-stereo set

Three observations form a valid tri-stereo set when:

1. all three share the same `target_id`, `satellite_id`, and `access_interval_id`
2. common AOI overlap fraction `>= min_overlap_fraction`
3. at least two of the three constituent pairs are valid stereo pairs
4. one observation has `boresight_off_nadir_deg <= near_nadir_anchor_max_off_nadir_deg` (the near-nadir anchor)

## Quality model

### Pair quality

For a valid stereo pair:

```
Q_pair = 0.50 * Q_geom + 0.35 * Q_overlap + 0.15 * Q_res
```

where:

```
Q_overlap = min(1, overlap_fraction / 0.95)
Q_res     = max(0, 1 - (pixel_scale_ratio - 1) / 0.5)
```

`Q_geom` depends on the scene-type preferred convergence band:

| `scene_type` | preferred band |
|---|---|
| `urban_structured` | 8–18 deg |
| `vegetated` | 8–14 deg |
| `rugged` | 10–20 deg |
| `open` | 15–25 deg |

`Q_geom = 1.0` inside the band, `0.5` at the band edges, and falls linearly to `0.0` outside. These are planning heuristics, not claims of universal photogrammetric truth.

### Tri-stereo quality

```
Q_tri = min(1, max(valid_pair_qualities) + beta(scene_type) * R)
```

`R` is a bounded redundancy-and-anchor bonus. `beta` values are read from `mission.yaml` under `tri_stereo_bonus_by_scene`.

### Per-target score

Each target's score is the maximum quality over all valid stereo and tri-stereo products covering that target.

## Primary ranking

Solutions are ranked first by validity, then by coverage, then by quality:

1. `valid = true`
2. maximize `coverage_ratio`
3. maximize `normalized_quality`

## Observation geometry model

The verifier propagates satellites with an SGP4-style propagator from the frozen TLEs.

**Access interval**: a maximal time window during which the target center is within `max_off_nadir_deg` and the solar elevation at the target is at least `min_solar_elevation_deg`. Two observations share the same `access_interval_id` when they fall within the same continuous access window.

**Effective pixel scale**:

```
effective_pixel_scale_m ≈ slant_range_m * pixel_ifov_deg * (pi / 180)
```

A local secant correction for off-nadir projection is applied.

**Footprint**: modeled as a pushbroom strip in a local tangent-plane approximation. The strip half-width at each sample is `slant_range_m * tan(half_cross_track_fov_deg)`.

**Overlap**: estimated by Monte Carlo sampling within the circular AOI.

## What is intentionally out of scope

- cloud and weather modeling
- downlink, ground stations, contact windows
- onboard storage and power accounting
- cross-satellite stereo (disabled by default)
- cross-date stereo (disabled by default)
- dense image matching internals
- bundle adjustment
- fine terrain occlusion or slope physics

## Running the tools

### Verifier

```bash
uv run python benchmarks/stereo_imaging/verifier/run.py \
    benchmarks/stereo_imaging/dataset/cases/case_0001 \
    path/to/solution.json

# Compact output (valid flag, metrics, violations only):
uv run python benchmarks/stereo_imaging/verifier/run.py \
    benchmarks/stereo_imaging/dataset/cases/case_0001 \
    path/to/solution.json \
    --compact
```

The verifier exits with code `0` when valid, `1` when invalid.

### Generator

```bash
# Re-generate the canonical dataset (requires network for CelesTrak and world-cities):
uv run python benchmarks/stereo_imaging/generator/run.py

# Fetch and cache runtime sources only (skip case generation):
uv run python benchmarks/stereo_imaging/generator/run.py --sources-only

# Force re-download even when cached:
uv run python benchmarks/stereo_imaging/generator/run.py --force-download
```

The generator writes cases under `dataset/cases/`, updates `dataset/index.json`, and writes `dataset/example_solution.json`. Runtime sources are cached under `dataset/source_data/`.

### Visualizer

```bash
# Case overview (ground tracks and target scatter map):
uv run python benchmarks/stereo_imaging/visualizer/run.py overview \
    benchmarks/stereo_imaging/dataset/cases/case_0001

# Batch ECEF geometry plots for all stereo candidates in a solution:
uv run python benchmarks/stereo_imaging/visualizer/run.py batch \
    benchmarks/stereo_imaging/dataset/cases/case_0001 \
    path/to/solution.json
```

Default outputs go to `benchmarks/stereo_imaging/visualizer/plots/<case_id>/`.

### Tests

```bash
uv run pytest tests/benchmarks/test_stereo_imaging_verifier.py
```
