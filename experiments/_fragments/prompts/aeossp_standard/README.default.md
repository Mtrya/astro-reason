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

## Important Task Semantics

- Each task is a point target with one required sensor type, one release time, one due time, and one exact required dwell time.
- Observation windows must stay inside the mission horizon and task time windows.
- Observation duration must match the requested duration exactly.
- A task is binary-complete rather than partially creditable.
- The schedule should contain only observation actions.
- The constellation is fixed for this problem. Do not add satellites or redesign orbits.
- The verifier propagates the frozen TLEs, checks continuous target visibility through the whole interval, and inserts required slew-plus-settle windows between same-satellite observations.
- Battery feasibility is judged over the full horizon from idle load, imaging load, slew load, and sunlit charging. You do not need to submit any of those internal traces, but the timing you choose must make them feasible.

## Validation Notes

If the workspace exposes a verifier helper, use it for local iteration:

- `{verifier_command}`

Treat it as a local correctness check while you refine `solution.json`.
