# Stereo Imaging Scheduling Problem

This workspace contains one optical stereo-imaging planning problem over a fixed mission horizon.

You are given:

- a fixed set of real satellites with frozen TLEs and compact sensor/agility parameters in `case/satellites.yaml`
- a set of ground targets with scene labels in `case/targets.yaml`
- mission-level stereo validity and quality thresholds in `case/mission.yaml`

Your job is to produce `solution.json`, a schedule of observation actions that creates as many valid stereo or tri-stereo products as possible with good geometry and quality.

This problem is modeled as scheduling raw optical observations, not explicitly choosing image pairs. You submit individual observation actions with boresight steering angles, and the validator later decides which combinations form valid stereo or tri-stereo products for the same target. In other words, the solution should create a set of observations that can be paired or grouped well under the benchmark's stereo geometry rules.

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

The output should schedule raw observations only. Stereo pairing, tri-stereo grouping, overlap checks, convergence checks, and quality evaluation are derived during validation.

## Important Task Semantics

- Each action chooses one target, one time interval, and two boresight steering angles in the satellite local frame.
- The underlying footprint model is a pushbroom strip approximation. Target access, overlap, and pixel-scale quality are derived from propagated geometry rather than from solver-submitted footprints.
- Two observations only count as a valid stereo pair when they satisfy the shared-target, shared-satellite, access-window, overlap, convergence, and pixel-scale conditions.
- Tri-stereo needs three compatible observations and a near-nadir anchor.
- Same-pass consistency matters: by default the products are expected to come from the same satellite and the same continuous access interval.
- Same-satellite overlap and insufficient slew-plus-settle gaps invalidate the solution.
- Observation geometry and solar-elevation constraints are enforced during validation.
- Coverage comes from valid stereo or tri-stereo products, not from single isolated observations alone.
- Quality depends on the benchmark's geometry heuristics, especially overlap, convergence angle, and pixel-scale compatibility, so it is usually better to create a few strong compatible looks than many isolated ones.

## Validation Notes

If the workspace exposes a verifier helper, use it for local iteration:

- `{verifier_command}`

Treat it as a local correctness check while you refine `solution.json`.
