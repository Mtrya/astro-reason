# Revisit-Oriented Constellation Design And Scheduling Problem

This workspace contains one revisit-driven Earth observation planning problem.

You are given:

- a shared satellite model and satellite-count cap in `case/assets.json`
- a mission horizon and target revisit requirements in `case/mission.json`

Your job is to produce `solution.json` with both:

- a proposed constellation at mission start
- a schedule of observation actions for that constellation

The goal is to keep revisit gaps small across the targets while respecting the orbit, visibility, timing, slew, and power constraints.

This problem combines constellation design and scheduling in one case. You choose the initial states of the satellites at mission start and then schedule observations for that chosen fleet. The hardware model is fixed by the case, but the number of satellites and their initial GCRF states are part of the decision.

## What Good Solutions Do

A strong solution should:

- satisfy all hard validity rules
- reduce the worst revisit gaps first
- then reduce average revisit gaps
- use fewer satellites when the revisit targets are already being met

In practical terms, feasibility comes first. After that, the solution should drive revisit gaps down as much as possible, and efficient constellation size matters once the required revisit quality is achieved.

## Files In This Workspace

- `case/assets.json`: shared satellite model, orbit/resource limits, and maximum number of satellites
- `case/mission.json`: mission horizon plus targets and their revisit requirements
- `{example_solution_name}`: example output shape when present
- `{verifier_location}`: local validation helper when present

## Expected Output

Write one JSON document named `solution.json` at the workspace root.

It should contain two top-level arrays:

- `satellites`
- `actions`

Each satellite entry defines one solver-chosen initial state with:

- `satellite_id`
- `x_m`
- `y_m`
- `z_m`
- `vx_m_s`
- `vy_m_s`
- `vz_m_s`

Each observation action should reference:

- `action_type`
- `satellite_id`
- `target_id`
- `start`
- `end`

## Modeling Contract

Use SI units, degrees, and timezone-aware ISO 8601 timestamps. Let `H0 = case/mission.json.horizon_start` and `H1 = case/mission.json.horizon_end`. There is no public action grid, but every timestamp must include a timezone. Observation actions must satisfy:

```text
action_type = "observation"
H0 <= start < end <= H1
end - start >= target.min_duration_sec
```

Each `satellites` entry defines one initial state at `H0` using GCRF Cartesian `x_m`, `y_m`, `z_m`, `vx_m_s`, `vy_m_s`, and `vz_m_s`. `satellite_id` values must be unique, actions may reference only submitted satellites, and `len(satellites) <= case/assets.json.max_num_satellites`. All submitted satellites share the hardware limits in `assets.json.satellite_model`; do not submit per-satellite sensor, power, or attitude changes.

Every submitted state must be a bound closed Earth orbit and must satisfy both instantaneous and orbital-altitude bounds from `satellite_model.min_altitude_m` and `satellite_model.max_altitude_m`. With Earth gravitational parameter `mu`, position norm `r`, speed `v`, specific energy `epsilon = 0.5 * v^2 - mu / r`, semi-major axis `a = -mu / (2 * epsilon)`, and eccentricity `e`, validity requires:

```text
epsilon < 0
0 <= e < 1
min_altitude_m <= r - R_earth <= max_altitude_m
min_altitude_m <= a * (1 - e) - R_earth
a * (1 + e) - R_earth <= max_altitude_m
```

Propagation uses the submitted GCRF state at `H0`, UTC time, a deterministic Earth orientation convention, and a J2-only Earth gravity model. Geometry checks use Earth-fixed target positions converted from target `longitude_deg`, `latitude_deg`, and `altitude_m`.

Observation geometry is sampled every 10 seconds from `start` up to but not including `end`. At each sampled instant, the target must satisfy:

```text
elevation_deg >= target.min_elevation_deg
slant_range_m <= target.max_slant_range_m
slant_range_m <= satellite_model.sensor.max_range_m
off_nadir_deg <= satellite_model.sensor.max_off_nadir_angle_deg
```

Same-satellite actions are half-open `[start, end)` and must not overlap. For consecutive observations on the same satellite, let `theta` be the inertial angle between the previous target vector at the previous observation midpoint and the current target vector at the current observation midpoint. With `omega = max_slew_velocity_deg_per_sec` and `alpha = max_slew_acceleration_deg_per_sec2` from `satellite_model.attitude_model`:

```text
if theta <= omega^2 / alpha:
  slew_time_sec = 2 * sqrt(theta / alpha)
else:
  slew_time_sec = 2 * (omega / alpha) + (theta - omega^2 / alpha) / omega

required_gap_sec = slew_time_sec + settling_time_sec
```

The gap from the previous `end` to the current `start` must be at least `required_gap_sec`. The reserved retargeting window immediately before the current observation must not overlap any other action.

Battery feasibility is simulated for each submitted satellite over the full horizon at action boundaries, reserved retargeting-window boundaries, and 30-second grid points. Segment midpoints decide active observation, active retargeting, and sunlight. Battery starts at `resource_model.initial_battery_wh`, is capped at `resource_model.battery_capacity_wh`, and invalidates the solution if it drops below zero:

```text
discharge_w = idle_discharge_rate_w
            + obs_discharge_rate_w if inside an observation
            + maneuver_discharge_rate_w if inside a retargeting window

battery_next_wh = battery_wh + (charge_w - discharge_w) * duration_sec / 3600
```

`charge_w` is `sunlight_charge_rate_w` in sunlight and `0` in eclipse.

Revisit scoring uses only successful observation midpoints. For each target, duplicate midpoint instants count once. Let the sorted time list be `[H0, midpoint_1, ..., midpoint_n, H1]`; if `n = 0`, the only gap is `H1 - H0`. For each target:

```text
gaps_hours = consecutive differences in that list, in hours
max_revisit_gap_hours = max(gaps_hours)
mean_revisit_gap_hours = mean(gaps_hours)
observation_count = n
target_capped_gap = max(max_revisit_gap_hours, expected_revisit_period_hours)
```

The primary metric is:

```text
capped_max_revisit_gap_hours = max(target_capped_gap over targets)
```

Lower is better; `num_satellites` is a secondary metric after revisit quality. Poor revisit gaps do not invalidate an otherwise feasible solution. Residual ambiguity remains around numerical orbit and visibility boundaries; validate borderline states and contacts with the local helper.

## Validation Notes

If the workspace exposes a verifier helper, use it for local iteration:

- `{verifier_command}`

Treat it as a local correctness check while you refine `solution.json`.
