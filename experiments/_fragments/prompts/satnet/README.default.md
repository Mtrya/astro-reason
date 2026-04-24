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

## Modeling Contract

Use Unix timestamps in integer seconds. `case/problem.json` is a JSON array of requests for one week, and `case/maintenance.csv` contains downtime windows for the same week. Request fields `duration` and `duration_min` are in hours; `setup_time` and `teardown_time` are in minutes. Solution rows use absolute Unix seconds.

Each solution row is one antenna allocation with fields `RESOURCE`, `SC`, `START_TIME`, `TRACKING_ON`, `TRACKING_OFF`, `END_TIME`, and `TRACK_ID`. `TRACK_ID` must equal a request `track_id` in `problem.json`. `RESOURCE` must be an antenna ID used by the case and must appear as a component of at least one resource-combination key in that request's `resource_vp_dict`. `SC` must parse as an integer, but hard validity is driven by `TRACK_ID`, resources, timing, view periods, maintenance, and overlaps.

For the referenced request, timing must satisfy exactly:

```text
TRACKING_ON = START_TIME + 60 * setup_time
END_TIME = TRACKING_OFF + 60 * teardown_time
```

Setup and teardown consume antenna time but do not count as communication time.

Rows with the same `TRACK_ID`, `START_TIME`, `TRACKING_ON`, `TRACKING_OFF`, and `END_TIME` are grouped as one logical track. A single-antenna logical track has one row. An arrayed logical track has multiple rows, one per antenna. The antenna names in the group are sorted and joined with `_` to form the combination key, such as `DSS-34_DSS-35`; that key must exist in the request's `resource_vp_dict`. Do not submit the joined key as one row's `RESOURCE`.

View periods are the hard visibility windows. For each logical track, the communication interval must fit inside at least one view-period interval for the chosen combination key:

```text
view_period["TRX ON"] <= TRACKING_ON <= TRACKING_OFF <= view_period["TRX OFF"]
```

`RISE`/`SET` may exist in `problem.json`, but normalized `TRX ON`/`TRX OFF` bounds are the operative communication bounds. Request-level `time_window_start` and `time_window_end` are broader request metadata and are not the hard containment interval when resource view periods are present.

Antenna exclusivity uses half-open occupied intervals:

```text
[START_TIME, END_TIME)
```

Two rows on the same `RESOURCE` may not overlap, and a row may not overlap any `maintenance.csv` interval `[starttime, endtime)` for that antenna. These checks include setup and teardown.

Each logical track must meet a per-track communication minimum:

```text
track_duration_s = TRACKING_OFF - TRACKING_ON
requested_s = int(duration * 3600)
minimum_s = int(duration_min * 3600)

if requested_s >= 28800:
  per_track_min_s = min(minimum_s, 14400)
else:
  per_track_min_s = minimum_s

track_duration_s >= per_track_min_s
```

Request satisfaction is stricter than per-track validity. For each `TRACK_ID`, communication time is summed across logical tracks, counted once per logical track even if arrayed, then capped at `requested_s`:

```text
allocated_s = min(sum(TRACKING_OFF - TRACKING_ON over logical tracks), requested_s)
satisfied if allocated_s >= minimum_s
```

The main communication-hours report is antenna-time:

```text
total_hours = sum((TRACKING_OFF - TRACKING_ON) / 3600 over solution rows)
```

Arrayed contacts therefore add one row's communication time per participating antenna. Fairness metrics group requests by `subject`. For each subject:

```text
subject_requested_s = sum(int(duration * 3600) for requests with that subject)
subject_allocated_s = sum(allocated_s for those requests)
U_i = max(subject_requested_s - subject_allocated_s, 0) / subject_requested_s
```

`U_max = max(U_i)`, and `U_rms = sqrt(mean(U_i^2))`. `n_satisfied_requests` counts requests whose capped allocation reaches `duration_min`. Residual ambiguity is mostly inherited from integer truncation of hour/minute request fields; when in doubt, use the equations above and then confirm with the local helper.

## Validation Notes

If the workspace exposes a verifier helper, use it for local iteration:

- `{verifier_command}`

Treat it as a local correctness check while you refine `solution.json`.
