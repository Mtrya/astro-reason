# Regional Strip-Coverage Planning Problem

This workspace contains one regional strip-imaging planning problem over a fixed mission horizon.

You are given:

- case-wide timing and scoring settings in `case/manifest.json`
- a fixed satellite set with sensor, agility, and power parameters in `case/satellites.yaml`
- polygonal regions of interest in `case/regions.geojson`
- a scoring grid in `case/coverage_grid.json`

Your job is to produce `solution.json`, a schedule of `strip_observation` actions that maximizes unique weighted regional coverage while remaining valid.

This problem is modeled as roll-only pushbroom strip imaging. Each action chooses a satellite, a start time, a duration, and a signed off-nadir roll angle. From that, the validator propagates the orbit, traces the strip centerline and strip edges against the Earth, and computes which weighted grid samples are newly covered. You are not submitting arbitrary polygons or claiming your own swath geometry; you are selecting timed strip acquisitions in the benchmark's strip model.

## What Good Solutions Do

A strong solution should:

- satisfy all hard validity rules
- maximize covered weighted area across the regions
- avoid wasteful energy use, excessive slew, and unnecessary action count when tie-breaking matters

Repeatedly covering the same samples does not help much in the current canonical setting, so broad valid coverage is usually better than redundant passes.

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

## Important Task Semantics

- `start_time` must align to the public action grid.
- `duration_s` must be a positive integer multiple of the public time step.
- `roll_deg` is the signed strip-center off-nadir angle, so it controls where the pushbroom strip is pointed cross-track rather than naming a region directly.
- The sensor is valid only when the strip's inner and outer edges both stay within the allowed off-nadir band implied by `roll_deg` and the sensor field of view.
- Strip validity depends on the sensor off-nadir band, slew feasibility, battery feasibility, and successful Earth intersection of the strip rays.
- The workspace does not expose precomputed access windows; visibility is derived during validation.
- Coverage is computed on the weighted sample grid in `case/coverage_grid.json`, and repeated coverage of the same samples does not create equal new value.
- Region polygons define where samples live, while the coverage grid defines what is actually scored.
- If a region declares a minimum required coverage ratio, failing it makes the whole solution invalid.
- Some cases also enforce per-orbit imaging duty limits in addition to battery limits, so very aggressive strip usage on one satellite may become invalid even if time windows appear open.

## Validation Notes

If the workspace exposes a verifier helper, use it for local iteration:

- `{verifier_command}`

Treat it as a local correctness check while you refine `solution.json`.
