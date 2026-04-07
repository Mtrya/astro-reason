# Stereo imaging benchmark specification v3

This document replaces the legacy v2 spec for `stereo_imaging`.

It defines the benchmark behavior, public case schema, and verifier-side modeling standard for a planning-oriented optical stereo benchmark. Repository layout and CI rules for finished benchmarks still follow [`docs/benchmark_contract.md`](../../docs/benchmark_contract.md).

## 0. design goal

This benchmark models multi-satellite planning for realistic optical stereo acquisition, but it stays on the planning side of the problem.

The benchmark should:
- use real public orbits,
- preserve same-pass stereo geometry,
- model nonzero retargeting cost,
- require meaningful overlap and stereo geometry,
- avoid fake precision in terrain and sensor physics.

The benchmark should not pretend to be a production photogrammetry pipeline. It does not model dense matching, bundle adjustment, detailed optics, clouds, storage, or downlink.

The main modeling choice in v3 is simple:
- keep physically meaningful geometry,
- keep a compact scene abstraction for quality heuristics,
- stop encoding altitude-dependent sensor outputs as if they were fundamental sensor properties.

## 1. global unit contract

The public benchmark contract uses:
- SI units for all linear, area, time, speed, and acceleration quantities,
- `deg` for all angular quantities,
- ISO 8601 UTC strings for timestamps.

Forbidden public units:
- `km`
- `km_s`
- `km_h`
- `hour`
- `hours`
- `minute`
- `minutes`

Allowed suffixes:
- `_m`
- `_m2`
- `_s`
- `_mps`
- `_mps2`
- `_deg`
- `_deg_per_s`
- `_deg_per_s2`

Examples:
- `aoi_radius_m`
- `elevation_ref_m`
- `min_obs_duration_s`
- `max_slew_velocity_deg_per_s`
- `pixel_ifov_deg`

Internal verifier code may convert `deg` to radians for computation, but radians are not part of the public case schema.

## 2. reproducible external data sources

The v3 generator relies on two runtime external inputs and one vendored lookup table.

### 2.1 runtime external sources

1. Orbit source
   - CelesTrak Earth-resources GP/TLE entries for the selected optical satellites.

2. Urban seeding source
   - A reproducibly fetched world-cities table, following the same Kaggle Hub workflow already used elsewhere in the repository.
   - This provides candidate locations for `scene_type: urban_structured`.

### 2.2 vendored lookup tables

The generator includes precomputed lookup tables for elevation and non-urban scene classification:

1. Elevation grid
   - `generator/lookup_tables.py` contains `ELEVATION_GRID: dict[tuple[int, int], float]`
   - Keys are `(lat_index, lon_index)` at 1-degree resolution, representing cell centers at integer coordinates
   - Values are average elevation in meters for that cell
   - Missing keys indicate ocean

2. Scene grid
   - `generator/lookup_tables.py` contains `SCENE_GRID: dict[tuple[int, int], str]`
   - Values are `"vegetated"`, `"rugged"`, or `"open"`
   - Missing keys indicate ocean or invalid terrain
   - Urban areas are handled separately via the world-cities source

### 2.3 lookup semantics for continuous coordinates

Target coordinates are continuous `(lat, lon)` values, not restricted to grid centers.

For elevation:
- Query the 4 nearest grid cells surrounding the target
- If any cell is missing (ocean), treat its elevation as `0.0`
- Return the bilinear interpolation of the 4 cell values
- If the target is in an ocean cell (all 4 nearest grid cells missing), reject the target

For scene type:
- Find the nearest grid cell center (round to nearest integer lat/lon)
- Return the scene type of that cell
- If the cell is missing from `SCENE_GRID`, reject the target (ocean/invalid)

This preserves coordinate continuity while keeping the lookup tables compact.

### 2.4 lookup table derivation

The lookup tables are derived once during generator development:

1. Download ETOPO 2022 60 arc-second raster
2. Download ESA WorldCover 2021 v200 tiles
3. Run a temporary script that:
   - Aggregates ETOPO to 1-degree cells → `ELEVATION_GRID`
   - Classifies WorldCover pixels to scene types → `SCENE_GRID`
4. Write the grids to `generator/lookup_tables.py`
5. Delete the source files

The lookup tables are committed to the repository. Generator users do not need to download ETOPO or WorldCover.

### 2.5 provenance

Released datasets should record provenance in `dataset/index.json`, including:
- generator revision when available,
- generator seed,
- CelesTrak fetch URL and retrieval timestamp,
- world-cities source id and retrieval timestamp,
- lookup table version or hash,
- selected satellite NORAD ids.

## 3. benchmark scope

Default v3 scope:
- `2` to `4` satellites per case,
- `24` to `48` targets per case,
- `172800 s` planning horizon,
- continuous-time observation actions,
- same-satellite same-pass stereo enabled,
- tri-stereo enabled,
- cross-satellite stereo disabled by default,
- cross-date stereo disabled by default.

The benchmark remains centered on same-satellite same-pass stereo because that is the most defensible default product definition for a compact planning benchmark.

## 4. satellite model

Each benchmark satellite uses a real frozen TLE plus a compact public sensor and agility model.

```yaml
satellite:
  id: str
  norad_catalog_id: int
  tle_line1: str
  tle_line2: str

  pixel_ifov_deg: float
  cross_track_pixels: int
  max_off_nadir_deg: float

  max_slew_velocity_deg_per_s: float
  max_slew_acceleration_deg_per_s2: float
  settling_time_s: float

  min_obs_duration_s: float
  max_obs_duration_s: float
```

### 4.1 meaning of the sensor fields

`pixel_ifov_deg`
- angular instantaneous field of view of one pixel in the cross-track direction.
- this is a sensor property.

`cross_track_pixels`
- number of pixels across the cross-track detector dimension used by the benchmark image model.

`max_off_nadir_deg`
- maximum allowed boresight off-nadir angle.

From these fields the verifier derives:

```text
cross_track_fov_deg = cross_track_pixels * pixel_ifov_deg
half_cross_track_fov_deg = 0.5 * cross_track_fov_deg
```

This replaces the v2 use of `nominal_pan_gsd_m` and `nadir_swath_km`.

Those v2 fields are removed because they are altitude-dependent consequences, not stable sensor primitives.

### 4.2 agility fields

The agility fields remain explicit benchmark parameters:
- `max_slew_velocity_deg_per_s`
- `max_slew_acceleration_deg_per_s2`
- `settling_time_s`

These are acceptable simplifications. They model retargeting cost without pretending to reproduce proprietary attitude control logic.

### 4.3 removed v2 fields

The following v2 satellite fields are not part of the v3 benchmark-facing satellite schema:
- `source_name`
- `satellite_class`
- `imaging_mode`
- `nominal_pan_gsd_m`
- `nadir_swath_km`

If useful for provenance, generator-side source names or class labels may still live in `dataset/index.json`.

## 5. target model

Each target exposes geometry plus a compact scene abstraction.

```yaml
target:
  id: str
  latitude_deg: float
  longitude_deg: float
  aoi_radius_m: float
  elevation_ref_m: float

  scene_type: enum(
    urban_structured,
    vegetated,
    rugged,
    open
  )
```

### 5.1 role of `scene_type`

`scene_type` is a benchmark abstraction for stereo matching difficulty and occlusion behavior.

It is not a claim that the verifier knows the true terrain physics of the scene. In v3:
- hard validity does not depend on `scene_type`,
- pair and tri-stereo quality may depend on `scene_type`.

This keeps the abstraction honest.

### 5.2 generation guidance for `scene_type`

The generator should assign `scene_type` reproducibly:

- `urban_structured`
  - drawn from the world-cities pool.

- `vegetated`, `rugged`, `open`
  - lookup via `SCENE_GRID` at the target coordinates.
  - reject targets that map to ocean (missing key in grid).

The lookup tables are precomputed from ETOPO and WorldCover during generator development, but the generator itself does not depend on those large source files at runtime.

### 5.3 removed v2 target fields

The following v2 target fields are not required in the public v3 case schema:
- `terrain_type`
- `dominant_worldcover_class`
- `built_up_fraction`
- `tree_cover_fraction`
- `mean_slope_deg`
- `relief_range_m`

## 6. generator guidance

### 6.1 target sampling

Target generation should remain reproducible and benchmark-oriented.

Recommended flow:
1. build urban candidates from the world-cities source (assign `scene_type: urban_structured`),
2. sample non-urban candidates from land cells in `SCENE_GRID` (continuous coordinates within valid cells),
3. assign `elevation_ref_m` via bilinear interpolation from `ELEVATION_GRID`,
4. assign `scene_type` from the nearest cell in `SCENE_GRID` for non-urban candidates,
5. reject targets in ocean cells (missing from grids),
6. reject targets with no feasible daylight access and no potential same-pass stereo opportunity,
7. assemble each case with scene diversity and geographic spread.

### 6.2 acceptable use of lookup tables

The vendored grids are acceptable in v3 for:
- center elevation,
- coarse scene classification,
- land/ocean screening.

The grids are not the basis for:
- AOI-scale slope truth,
- fine relief estimation,
- occlusion modeling,
- high-fidelity footprint-terrain intersection.

## 7. action schema

The action schema stays minimal and agent-facing.

```yaml
action:
  type: observation
  satellite_id: str
  target_id: str
  start_time: ISO8601
  end_time: ISO8601
  off_nadir_along_deg: float
  off_nadir_across_deg: float
```

Hard action constraints:
- `end_time > start_time`
- both times must lie within the mission horizon,
- no overlapping observations on the same satellite,
- sufficient slew-plus-settle time between consecutive observations,
- total boresight off-nadir angle must not exceed `max_off_nadir_deg`,
- observation duration must lie within `[min_obs_duration_s, max_obs_duration_s]`.

The off-nadir bound applies to the combined boresight vector, not componentwise.

## 8. derived observation record

The solver does not provide these fields. The verifier derives them.

```yaml
derived_observation:
  satellite_id: str
  target_id: str
  start_time: ISO8601
  end_time: ISO8601
  midpoint_time: ISO8601

  sat_position_ecef_m: [x, y, z]
  sat_velocity_ecef_mps: [vx, vy, vz]

  boresight_off_nadir_deg: float
  boresight_azimuth_deg: float

  solar_elevation_deg: float
  solar_azimuth_deg: float

  effective_pixel_scale_m: float
  access_interval_id: str
```

The verifier may also compute diagnostic quantities such as overlap, convergence, B/H proxy, bisector elevation, asymmetry, and anchor-view diagnostics.

## 9. observation geometry

### 9.1 propagation

The verifier propagates each satellite from the frozen TLE with an SGP4-style propagator.

### 9.2 continuous access interval

For a given satellite-target pair, a continuous access interval is a maximal time interval during which:
- the target center is reachable within `max_off_nadir_deg`,
- the target-center solar elevation is at least `min_solar_elevation_deg`.

### 9.3 same-pass definition

Two observations are same-pass if they share the same `access_interval_id` for the same satellite-target pair.

### 9.4 footprint model

Each observation is modeled as a pushbroom strip in a local tangent-plane approximation:
1. propagate the satellite over `[start_time, end_time]`,
2. compute the boresight ground intercept at sampled times,
3. derive the strip half-width from the angular cross-track field of view,
4. union the sampled swaths into a strip footprint approximation.

For a sample with slant range `R_s` and half cross-track field of view `phi`, use:

```text
strip_half_width_m ≈ R_s * tan(phi)
```

where `phi` is computed from `cross_track_pixels * pixel_ifov_deg`.

This is still a planning approximation, but it is physically cleaner than v2's fixed swath field.

### 9.5 effective pixel scale

The verifier computes an effective pixel scale from slant range and angular IFOV.

A compact planning approximation is:

```text
effective_pixel_scale_m ≈ slant_range_m * pixel_ifov_deg * (pi / 180)
```

The verifier may include a local secant-style correction for off-nadir projection, but the public contract does not require a more complicated optical model.

## 10. stereo product definitions

### 10.1 valid stereo pair

Two observations `(i, j)` form a valid stereo pair iff all of the following hold:

1. same `target_id`
2. same `satellite_id`
3. same `access_interval_id`
4. AOI overlap fraction

```text
O_ij >= 0.80
```

5. convergence angle at the target center

```text
5.0 deg <= gamma_ij <= 45.0 deg
```

6. effective pixel-scale ratio satisfies

```text
max(s_i, s_j) / min(s_i, s_j) <= 1.5
```

7. all action-level feasibility constraints are satisfied

### 10.2 valid tri-stereo set

Three observations form a valid tri-stereo set iff:

1. all three share the same `target_id`, `satellite_id`, and `access_interval_id`,
2. common AOI overlap fraction is at least `0.80`,
3. at least two of the three constituent pairs are valid stereo pairs,
4. one observation acts as a near-nadir anchor with

```text
boresight_off_nadir_deg <= near_nadir_anchor_max_off_nadir_deg
```

### 10.3 disabled-by-default modes

The default release sets:

```yaml
allow_cross_satellite_stereo: false
allow_cross_date_stereo: false
```

These modes may be added later, but they are not part of the default v3 release contract.

## 11. diagnostics

For each candidate pair, the verifier should report:
- convergence angle,
- effective B/H proxy,
- bisector elevation angle,
- asymmetry angle,
- AOI overlap fraction,
- effective pixel-scale ratio.

Convergence remains the main hard-validity geometry check. The others are diagnostics and quality signals.

No hard B/H ratio threshold is part of the v3 validity contract. B/H remains a diagnostic proxy only.

## 12. quality model

### 12.1 pair quality

For a valid stereo pair:

```text
Q_pair = 0.50 * Q_geom + 0.35 * Q_overlap + 0.15 * Q_res
```

with

```text
Q_overlap = min(1, O_ij / 0.95)
Q_res = max(0, 1 - (r - 1) / 0.5)
r = max(s_i, s_j) / min(s_i, s_j)
```

Scene-dependent preferred convergence bands:
- `urban_structured`: `8.0 deg` to `18.0 deg`
- `vegetated`: `8.0 deg` to `14.0 deg`
- `rugged`: `10.0 deg` to `20.0 deg`
- `open`: `15.0 deg` to `25.0 deg`

These are benchmark heuristics. They are not claims of universal photogrammetric truth.

### 12.2 tri-stereo quality

For a valid tri-stereo set:

```text
Q_tri = min(1, max(valid_pair_qualities) + beta(scene_type) * R)
```

where `R` is a bounded redundancy-and-anchor bonus and:
- `beta(urban_structured) = 0.12`
- `beta(rugged) = 0.10`
- `beta(vegetated) = 0.08`
- `beta(open) = 0.05`

### 12.3 per-target score

Each target score is the maximum over all valid stereo or tri-stereo products covering that target.

## 13. benchmark metrics

```yaml
metrics:
  valid: bool
  coverage_ratio: float
  normalized_quality: float
```

Definitions:
- `valid`: all hard action and geometry constraints satisfied,
- `coverage_ratio`: fraction of targets with at least one valid stereo or tri-stereo product,
- `normalized_quality`: sum of per-target scores divided by the number of targets.

Primary ranking:
1. `valid = true`
2. maximize `coverage_ratio`
3. maximize `normalized_quality`

## 14. case file structure

Canonical v3 case shape:

```text
dataset/
├── example_solution.json
├── index.json
└── cases/
    └── case_0001/
        ├── satellites.yaml
        ├── targets.yaml
        └── mission.yaml
```

`mission.yaml` contains only benchmark-facing mission parameters:

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

`dataset/index.json` should record:
- source versions and retrieval timestamps,
- canonical seed,
- released case ids,
- per-case satellite and target counts,
- any generator-side metadata needed for reproducibility.

## 15. out of scope in v3

Default v3 excludes:
- cloud modeling,
- downlink and ground stations,
- onboard storage and power accounting,
- cross-date stereo,
- cross-satellite stereo,
- dense matching internals,
- bundle adjustment,
- fine terrain occlusion physics.

That boundary is intentional. The benchmark focuses on whether an agent can plan physically meaningful same-pass stereo opportunities without relying on misleading sensor or terrain shortcuts.
