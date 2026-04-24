# Regional Strip-Coverage Planning Problem

This workspace contains one regional strip-imaging planning problem over a fixed mission horizon.

You are given:

- case-wide timing and scoring settings in `case/manifest.json`
- a fixed satellite set with sensor, agility, and power parameters in `case/satellites.yaml`
- polygonal regions of interest in `case/regions.geojson`
- a scoring grid in `case/coverage_grid.json`

Your job is to produce `solution.json`, a schedule of `strip_observation` actions that maximizes unique weighted regional coverage while remaining valid.

This problem is modeled as roll-only pushbroom strip imaging. Each action chooses a satellite, a start time, a duration, and a signed off-nadir roll angle. From that, the validator propagates the orbit, traces the strip centerline and strip edges against the Earth, and computes which weighted grid samples are newly covered. You are not submitting arbitrary polygons or claiming your own swath geometry; you are selecting timed strip acquisitions in the case's strip model.

## What Good Solutions Do

A strong solution should:

- satisfy all hard validity rules
- maximize covered weighted area across the regions
- avoid wasteful energy use, excessive slew, and unnecessary action count when tie-breaking matters

Repeatedly covering the same samples does not improve the coverage metrics, so broad valid coverage is usually better than redundant passes.

## Files In This Workspace

- `case/manifest.json`: mission horizon, public action grid, scoring settings, and grid metadata
- `case/satellites.yaml`: fixed satellites and their sensor/agility/power limits
- `case/regions.geojson`: weighted regions of interest
- `case/coverage_grid.json`: coverage samples used for scoring
- `{example_solution_name}`: example output shape when present
- `{verifier_location}`: local validation helper when present

## Expected Output

Write one JSON object named `solution.json` at the workspace root.

The required top-level field is:

- `actions`

Each action should describe one strip observation with:

- `type`
- `satellite_id`
- `start_time`
- `duration_s`
- `roll_deg`

Do not submit your own strip polygons, coverage claims, or access-window identifiers. Strip geometry and coverage are derived during validation.

## Modeling Contract

Use SI units, degrees, and timezone-aware ISO 8601 timestamps. Let `H0 = manifest.json.horizon_start`, `H1 = manifest.json.horizon_end`, and `dt = manifest.json.time_step_s`. A `strip_observation` action is interpreted only from these solution fields: `type`, `satellite_id`, `start_time`, `duration_s`, and `roll_deg`. It must satisfy:

```text
type = "strip_observation"
H0 <= start_time < start_time + duration_s <= H1
(start_time - H0) / dt is an integer
duration_s > 0
duration_s / dt is an integer
```

If `manifest.json.scoring.max_actions_total` is present, the number of submitted actions may not exceed it. Actions with another `type` are not strip observations and do not create coverage; use only `strip_observation` entries.

The satellite set is fixed by `case/satellites.yaml`; each `satellite_id` must reference one of those entries. Satellite TLEs are propagated with SGP4, Earth-fixed geometry uses WGS84, and the only attitude command is signed `roll_deg`, the cross-track off-nadir angle of the strip center. Positive and negative signs look to opposite sides of the ground track.

For a satellite with `sensor.cross_track_fov_deg = f`, the commanded center roll is converted to strip-edge angles:

```text
theta_inner_deg = abs(roll_deg) - 0.5 * f
theta_outer_deg = abs(roll_deg) + 0.5 * f
```

The action is sensor-valid only if:

```text
theta_inner_deg >= sensor.min_edge_off_nadir_deg
theta_outer_deg <= sensor.max_edge_off_nadir_deg
sensor.min_strip_duration_s <= duration_s <= sensor.max_strip_duration_s
```

Angle and duration comparisons allow only tiny numerical tolerance. The signed inner and outer edge rays use the same sign as `roll_deg`.

Strip geometry is derived from the propagated satellite state at `start_time`, `end_time`, and every `coverage_sample_step_s` inside the action. At each sample, the center ray and both edge rays must intersect the WGS84 ellipsoid. Consecutive inner/outer edge hits form strip segment polygons in longitude/latitude. If any ray misses Earth, fewer than two sample times exist, or a segment has zero area, the action is invalid. Coverage is not accepted from submitted polygons or claims.

Same-satellite strip intervals are half-open `[start_time, end_time)` and must not overlap. For consecutive strips on the same satellite, retargeting depends only on commanded roll change:

```text
theta = abs(current.roll_deg - previous.roll_deg)
omega = agility.max_roll_rate_deg_per_s
alpha = agility.max_roll_acceleration_deg_per_s2

if theta <= omega^2 / alpha:
  slew_time_s = 2 * sqrt(theta / alpha)
else:
  slew_time_s = theta / omega + omega / alpha

required_gap_s = slew_time_s + agility.settling_time_s
```

The gap from the previous `end_time` to the current `start_time` must be at least `required_gap_s`.

Power is simulated per satellite over the full horizon on the `coverage_sample_step_s` mesh plus action and retargeting-window boundaries. Segment midpoints decide active state. The battery starts at `power.initial_battery_wh`, is capped at `power.battery_capacity_wh`, and invalidates the solution if it becomes negative. Load is `idle_power_w`, plus `imaging_power_w` during strips, plus `slew_power_w` during retargeting; charge is `sunlit_charge_power_w` in sunlight and `0` in eclipse. If `power.imaging_duty_limit_s_per_orbit` is not null, then for each action boundary the total imaging time in the preceding one-orbit window, using the satellite TLE mean motion, must not exceed that limit.

Coverage is scored only on `case/coverage_grid.json`. A sample contributes `weight_m2` to its region once if any valid strip segment covers its point; repeated coverage increments diagnostics but adds no score. For each `region_id`:

```text
region_coverage_ratio = covered_sample_weight_m2 / total_weight_m2
```

If the matching feature in `case/regions.geojson` declares `min_required_coverage_ratio`, then `region_coverage_ratio` below that threshold invalidates the whole solution. Reported aggregate metrics are:

```text
coverage_ratio = sum(properties.weight * region_coverage_ratio) / sum(properties.weight)
weighted_coverage_ratio = sum(covered_sample_weight_m2 over all regions) / sum(total_weight_m2 over all regions)
```

The first metric is the region-weighted objective; the second is raw grid-weight coverage. Residual ambiguity is limited to numerical geometry near strip edges and the deterministic polygon/grid approximation; use the local helper for boundary cases.

## Validation Notes

If the workspace exposes a verifier helper, use it for local iteration:

- `{verifier_command}`

Treat it as a local correctness check while you refine `solution.json`.
