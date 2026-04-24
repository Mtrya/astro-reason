# Stereo Imaging Scheduling Problem

This workspace contains one optical stereo-imaging planning problem over a fixed mission horizon.

You are given:

- a fixed set of real satellites with frozen TLEs and compact sensor/agility parameters in `case/satellites.yaml`
- a set of ground targets with scene labels in `case/targets.yaml`
- mission-level stereo validity and quality thresholds in `case/mission.yaml`

Your job is to produce `solution.json`, a schedule of observation actions that creates as many valid stereo or tri-stereo products as possible with good geometry and quality.

This problem is modeled as scheduling raw optical observations, not explicitly choosing image pairs. You submit individual observation actions with boresight steering angles, and the validator later decides which combinations form valid stereo or tri-stereo products for the same target. In other words, the solution should create a set of observations that can be paired or grouped well under the case's stereo geometry rules.

## What Good Solutions Do

A strong solution should:

- satisfy all hard validity rules
- cover as many targets as possible with at least one valid stereo or tri-stereo product
- improve the quality of the best product per target when additional choices are available

In practical terms, valid stereo coverage matters first, then geometric and quality strength.

## Files In This Workspace

- `case/satellites.yaml`: fixed satellites, TLEs, sensor field of view, pointing limits, and slew limits
- `case/targets.yaml`: target locations, AOI sizes, and scene types
- `case/mission.yaml`: mission horizon, stereo validity thresholds, and quality-model settings
- `{example_solution_name}`: example output shape when present
- `{verifier_location}`: local validation helper when present

## Expected Output

Write one JSON object named `solution.json` at the workspace root.

The required top-level field is:

- `actions`

Each action should describe one observation with:

- `type`
- `satellite_id`
- `target_id`
- `start_time`
- `end_time`
- `off_nadir_along_deg`
- `off_nadir_across_deg`

The output should schedule raw observations only. Stereo pairing, tri-stereo grouping, overlap checks, convergence checks, and quality scoring are derived during validation.

## Modeling Contract

Use SI units, degrees, and timezone-aware ISO 8601 timestamps. Naive timestamps are rejected; a trailing `Z` is the safest UTC form. `case/mission.yaml` contains a top-level `mission` mapping. Actions whose `type` is not `"observation"` are ignored; submit only observation actions. Each interpreted action must reference `satellite_id` from `case/satellites.yaml`, `target_id` from `case/targets.yaml`, and satisfy:

```text
mission.horizon_start <= start_time < end_time <= mission.horizon_end
min_obs_duration_s <= end_time - start_time <= max_obs_duration_s
```

The satellite set is fixed by TLEs in `case/satellites.yaml`; you choose only raw observation windows and two boresight steering angles. `off_nadir_along_deg` tilts along the flight direction and `off_nadir_across_deg` tilts cross-track in the satellite local frame. The boresight vector is proportional to:

```text
nadir_hat
+ tan(off_nadir_along_deg) * along_hat
+ tan(off_nadir_across_deg) * across_hat
```

with tangent inputs in radians. The combined tilt compared to `max_off_nadir_deg` is:

```text
combined_deg = degrees(atan(sqrt(tan(along_rad)^2 + tan(across_rad)^2)))
combined_deg <= max_off_nadir_deg
```

At the observation midpoint, the commanded boresight ray must intersect the WGS84 ellipsoid. Effective pixel scale is:

```text
effective_pixel_scale_m = slant_range_m * pixel_ifov_deg * pi / 180
```

Target access is derived from the target center at `longitude_deg`, `latitude_deg`, and `elevation_ref_m`; it is not a submitted claim. The full observation interval must lie inside one continuous access interval for the same satellite-target pair. Access is sampled at:

```text
access_step_s = max(0.25, min(1.0, min_obs_duration_s / 2))
```

including both action boundaries. At every sampled instant, access requires clear line of sight to the target center, target-center off-nadir no greater than `max_off_nadir_deg`, and target solar elevation at least `mission.validity_thresholds.min_solar_elevation_deg`.

Same-satellite observation intervals are half-open `[start_time, end_time)` and must not overlap. For consecutive same-satellite observations, let `theta` be the angle between the commanded boresight vector at the previous `end_time` and the commanded boresight vector at the next `start_time`. With `omega = max_slew_velocity_deg_per_s` and `alpha = max_slew_acceleration_deg_per_s2`:

```text
if theta <= omega^2 / alpha:
  slew_time_s = 2 * sqrt(theta / alpha)
else:
  slew_time_s = theta / omega + omega / alpha

required_gap_s = slew_time_s + settling_time_s
```

The gap between observations must be at least `required_gap_s`.

Validated observations can form stereo products only when they share a common `target_id` and satisfy one of the mission-allowed product modes:

- same-satellite same-pass: common `satellite_id` and membership in the same continuous access interval for that satellite-target pair
- cross-satellite: different `satellite_id` values, allowed only when `mission.allow_cross_satellite_stereo` is true

Every product pair must also satisfy the bounded temporal constraint:

```text
abs(midpoint_time_i - midpoint_time_j) <= mission.max_stereo_pair_separation_s
```

Crossing a UTC calendar-date boundary is not invalid by itself. A pair centered at 23:59 and 00:01 can still be valid if it satisfies the temporal bound and all geometry rules. Cross-satellite products do not require inter-satellite slew or non-overlap checks; same-satellite observations still obey the same-satellite overlap and slew/settle rules above. For a pair, convergence angle `gamma_deg` is the angle at the target between the two target-to-satellite midpoint directions. Pixel scale ratio is:

```text
pixel_scale_ratio = max(scale_i, scale_j) / min(scale_i, scale_j)
```

A valid stereo pair requires:

```text
overlap_fraction >= min_overlap_fraction
min_convergence_deg <= gamma_deg <= max_convergence_deg
pixel_scale_ratio <= max_pixel_scale_ratio
```

A valid tri-stereo set requires three observations of the same target, all constituent pairs satisfying the mission-allowed product mode and bounded temporal constraint, common overlap at least `min_overlap_fraction`, at least two valid constituent pairs under the same pair rules, and at least one observation with `boresight_off_nadir_deg <= near_nadir_anchor_max_off_nadir_deg`.

Overlap is a deterministic approximation inside each target's circular AOI of radius `aoi_radius_m`. Each observation footprint is a pushbroom strip in the target-centered local tangent plane. The strip centerline is sampled every 8 seconds between observation start and end using the commanded boresight, and half-width is:

```text
strip_half_width_m = slant_range_m * tan(radians(0.5 * cross_track_pixels * pixel_ifov_deg))
```

Pair overlap uses 100 deterministic Monte Carlo samples; tri common overlap uses 100 samples; pair checks inside tri-product scoring use 80 samples. Do not submit footprints, overlap fractions, product choices, or quality scores.

Coverage comes only from valid stereo or tri-stereo products. For each target, the retained score is the best valid product quality. Pair quality is:

```text
Q_pair = pair_weights.geometry * Q_geom
       + pair_weights.overlap * min(1, overlap_fraction / 0.95)
       + pair_weights.resolution * max(0, 1 - (pixel_scale_ratio - 1) / 0.5)
```

`Q_geom` is best when `gamma_deg` falls in the scene-type preference band for `scene_type` and decays outside it. Tri-stereo quality is:

```text
Q_tri = min(1, best_valid_pair_quality + tri_stereo_bonus_by_scene[scene_type] * R)
```

where `R` is `0.6` for having at least two valid pairs plus `0.4` for a near-nadir anchor, capped at `1`. Reported metrics are:

```text
coverage_ratio = number of targets with at least one valid product / number of targets
normalized_quality = sum(best target product quality over all targets) / number of targets
```

Residual ambiguity is the intentional deterministic overlap approximation: exact continuous AOI overlap is not the scored quantity, so use the local helper to check close overlap-threshold cases.

## Validation Notes

If the workspace exposes a verifier helper, use it for local iteration:

- `{verifier_command}`

Treat it as a local correctness check while you refine `solution.json`.
