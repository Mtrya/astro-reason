# Agile Earth Observation Scheduling Problem

This workspace contains one agile Earth-observation scheduling problem over a fixed mission horizon.

You are given:

- a mission description in `case/mission.yaml`
- a fixed constellation with frozen orbital elements and subsystem limits in `case/satellites.yaml`
- a set of time-windowed imaging tasks in `case/tasks.yaml`

Your job is to produce `solution.json`, an event schedule of `observation` actions that completes as many high-value tasks as possible without violating hard timing, geometry, slew, or battery constraints.

This problem is modeled as point-imaging scheduling on a fixed fleet. You are choosing when each satellite should spend a continuous interval observing a target, not redesigning the satellites, not changing their orbits, and not submitting low-level attitude trajectories. An action in the solution means "this satellite continuously observes this target over this interval," and the geometry, maneuver windows, and battery evolution are derived from that commitment during validation.

## What Good Solutions Do

A strong solution should:

- satisfy all hard validity rules
- complete as many high-weight tasks as possible
- also improve overall completion rate when possible
- avoid unnecessary lateness and wasteful power use when tie-breaking matters

In practical terms, valid task completion matters first, especially on higher-weight tasks.

## Files In This Workspace

- `case/mission.yaml`: mission horizon, public time grids, and reported metric metadata
- `case/satellites.yaml`: fixed satellites, TLEs, sensor limits, slew limits, and battery/power parameters
- `case/tasks.yaml`: imaging requests with time windows, durations, sensor requirements, and weights
- `{example_solution_name}`: example output shape when present
- `{verifier_location}`: local validation helper when present

## Expected Output

Write one JSON object named `solution.json` at the workspace root.

The required top-level field is:

- `actions`

Each action should represent one observation interval with:

- `type`
- `satellite_id`
- `task_id`
- `start_time`
- `end_time`

Do not submit visibility claims, maneuver windows, power traces, or completion claims. Those are derived during validation.

## Modeling Contract

Use SI units, degrees, and timezone-aware ISO 8601 timestamps. A trailing `Z` is the safest UTC form. `case/mission.yaml` is a top-level `mission` mapping. Let `H0 = mission.horizon_start`, `H1 = mission.horizon_end`, and `dt = mission.action_time_step_s`. Every action `start_time` and `end_time` must satisfy:

```text
H0 <= start_time < end_time <= H1
(start_time - H0) / dt is an integer
(end_time - H0) / dt is an integer
```

Each task in `case/tasks.yaml` has `release_time`, `due_time`, and `required_duration_s` on the same grid. A valid observation action must use `type: "observation"`, reference a known `satellite_id` and `task_id`, satisfy `release_time <= start_time` and `end_time <= due_time`, and have:

```text
end_time - start_time = required_duration_s
```

Longer or shorter observations do not partially complete the task. The satellite's `sensor.sensor_type` must exactly equal the task's `required_sensor_type`.

The constellation is fixed by `case/satellites.yaml`. Satellite states are propagated only from each satellite's `tle_line1` and `tle_line2`; do not add satellites, change TLEs, or submit attitude trajectories. Inertial quantities use the case's GCRF convention, Earth-fixed geometry uses ITRF/ECEF, target coordinates use WGS84 geodetic `longitude_deg`, `latitude_deg`, and `altitude_m`, and Earth orientation is deterministic for a given case.

Observation visibility is checked at `start_time`, `end_time`, and every `geometry_sample_step_s` grid instant strictly inside the action. At every checked instant, the target line of sight must be above the target local horizon and the off-nadir angle from satellite nadir to target line of sight must be no greater than `attitude_model.max_off_nadir_deg`, allowing only tiny numerical tolerance at the boundary.

For a satellite, observation intervals are half-open for overlap purposes: `[start_time, end_time)`. Same-satellite actions must not overlap. For consecutive same-satellite observations, the required retargeting gap is computed from the angle `theta` between the previous target vector at the previous `end_time` and the next target vector at the next `start_time`, both in the inertial frame. With `omega = max_slew_velocity_deg_per_s` and `alpha = max_slew_acceleration_deg_per_s2`:

```text
if theta <= omega^2 / alpha:
  slew_time_s = 2 * sqrt(theta / alpha)
else:
  slew_time_s = 2 * (omega / alpha) + (theta - omega^2 / alpha) / omega

required_gap_s = slew_time_s + settling_time_s
```

The required gap is reserved immediately before the later observation. The solution is invalid if the available idle gap is shorter than `required_gap_s`.

Battery feasibility is simulated for each satellite over the full mission horizon using `resource_sample_step_s` grid points plus all action and retargeting-window boundaries. Each segment uses its midpoint to decide whether an observation, retargeting window, and sunlight are active. Battery starts at `resource_model.initial_battery_wh`, is capped after each segment at `battery_capacity_wh`, and invalidates the solution if it drops below zero. Segment load is:

```text
load_power_w = idle_power_w
             + imaging_power_w if the segment midpoint is inside an observation
             + slew_power_w if the segment midpoint is inside a retargeting window

battery_next_wh = battery_wh + (charge_power_w - load_power_w) * duration_s / 3600
```

`charge_power_w` is `sunlit_charge_power_w` in sunlight and `0` in eclipse. `PC` is gross consumed watt-hours summed over satellites that pass the battery check.

Task completion is binary. For each `task_id`, the earliest valid completing observation by `end_time` counts once; duplicates do not add credit. For valid solutions:

```text
CR  = completed_task_count / total_task_count
WCR = sum(weight for completed tasks) / sum(weight for all tasks)
TAT = mean(completion_time - release_time) over completed tasks, in seconds, or null if none complete
PC  = gross consumed watt-hours
```

Validity is the hard gate before these metrics matter. Residual ambiguity remains only for borderline propagation, geometry, and battery cases at numerical tolerances; use the local helper for final checks rather than treating this prose as a replacement for full validation.

## Validation Notes

If the workspace exposes a verifier helper, use it for local iteration:

- `{verifier_command}`

Treat it as a local correctness check while you refine `solution.json`.
