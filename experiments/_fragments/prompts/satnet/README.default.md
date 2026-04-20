# Deep-Space Communication Scheduling Problem

This workspace contains one deep-space communication scheduling problem over a one-week horizon.

You are given:

- a set of communication requests in `case/problem.json`
- an antenna maintenance schedule in `case/maintenance.csv`

Each request describes one communication opportunity for a spacecraft, including compatible antennas, valid view periods, setup and teardown requirements, and requested duration.

Your job is to produce `solution.json`, a JSON array of scheduled tracks that allocates antenna time effectively while respecting view periods, maintenance, setup/teardown timing, and non-overlap constraints.

This problem is modeled as week-long antenna-track scheduling. Each scheduled track consumes one antenna timeline from setup start through teardown end, while only the inner transmission interval counts as communication time. Requests may be partially satisfied across one or more scheduled tracks as long as each individual scheduled track is valid.

## What Good Solutions Do

A strong solution should:

- satisfy all hard validity rules
- maximize actual communication time
- satisfy as many requests as possible
- reduce the amount of unsatisfied demand across requests

In practical terms, only transmission time counts toward the main objective. Setup and teardown consume antenna time but do not contribute to communication hours.

## Files In This Workspace

- `case/problem.json`: the requests for this planning week, including compatible resources and view periods
- `case/maintenance.csv`: antenna downtime windows that must be respected
- `{example_solution_name}`: example output shape when present
- `{verifier_location}`: local validation helper when present

## Expected Output

Write `solution.json` at the workspace root.

For this problem, `solution.json` should be a JSON array, not an object.

Each array element should describe one scheduled track with:

- `RESOURCE`
- `SC`
- `START_TIME`
- `TRACKING_ON`
- `TRACKING_OFF`
- `END_TIME`
- `TRACK_ID`

The verifier checks timing consistency between setup, transmission, and teardown, so those fields must align exactly with the request parameters.

## Important Task Semantics

- `START_TIME -> TRACKING_ON -> TRACKING_OFF -> END_TIME` is a strict timing chain: setup occupies the first segment, actual communication occupies the middle segment, and teardown occupies the last segment.
- A scheduled transmission must fit fully inside at least one valid view period for the chosen antenna.
- Tracks on the same antenna cannot overlap, including setup and teardown time.
- Tracks cannot overlap with maintenance windows on the same antenna.
- `TRACK_ID` must refer to a real request.
- The chosen `RESOURCE` must be compatible with that request.
- Some requests allow arrayed resources, so the resource key must match the request's allowed resource combinations rather than an arbitrary antenna label.
- Communication hours come only from `TRACKING_ON` to `TRACKING_OFF`; setup and teardown help validity but add no direct objective value.
- For very long requests, the verifier allows a single scheduled track to satisfy a capped per-track minimum of 4 hours instead of the full original minimum duration.

## Validation Notes

If the workspace exposes a verifier helper, use it for local iteration:

- `{verifier_command}`

Treat it as a local correctness check while you refine `solution.json`.
