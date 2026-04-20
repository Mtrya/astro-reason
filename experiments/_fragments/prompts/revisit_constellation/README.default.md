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

## Important Task Semantics

- You are choosing the initial satellite states, not redesigning the satellite hardware model.
- The number of satellites cannot exceed the case limit.
- Initial states must satisfy the orbit constraints.
- The visibility model is intentionally simple: a target is observable when its line of sight stays inside the sensor's nadir-centered pointing cone and range/elevation bounds.
- Observation geometry, power feasibility, and required maneuver gaps are enforced during validation.
- Revisit quality is computed from the midpoints of successful observations, with mission start and mission end treated as boundary times when gaps are measured.
- Poor revisit performance does not automatically invalidate the solution, but invalid geometry, timing, or resource use still does.

## Validation Notes

If the workspace exposes a verifier helper, use it for local iteration:

- `{verifier_command}`

Treat it as a local correctness check while you refine `solution.json`.
