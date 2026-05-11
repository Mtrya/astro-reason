---
name: satnet-cpsat-scheduler
description: Use for SatNet/deep-space communication scheduling cases where solution.json schedules antenna tracks under view periods, setup/teardown, maintenance, non-overlap, request satisfaction, and fairness-oriented scoring.
---

For SatNet, a good strategy to try is a small CP-SAT interval scheduler over feasible request/view-period/resource candidates. It is not the only possible approach, but it often beats hand-built greedy schedules because the verifier rules are mostly integer timing and no-overlap constraints.

## Quick Start

1. Read `README.md`, `case/problem.json`, `case/metadata.json`, and `case/maintenance.csv`.
2. Write an initial valid fallback `solution.json`, often `[]`, and verify it.
3. Try importing OR-Tools with `from ortools.sat.python import cp_model`.

If OR-Tools is not available or the model gets too large, keep a deterministic greedy fallback and preserve the best verifier-valid `solution.json`.

## Candidate Shape

Build candidates before creating solver variables. A useful candidate is `request + resource_vp_dict key + one view period`.

For each request, compute integer seconds: `req_s`, `min_s`, `setup_s`, `teardown_s`, and `per_track_min_s = min(min_s, 14400) if req_s >= 28800 else min_s`.

Keep only candidates whose view period can hold `per_track_min_s`. For array keys such as `DSS-34_DSS-35`, model one logical track with multiple antennas, then emit one output row per antenna.

## Optional Interval Model

When start time or duration can vary, optional intervals are a natural fit:

- `present`: whether the candidate is selected
- `tx_on`, `tx_off`, `dur`: integer variables inside the view-period bounds
- `tx_off == tx_on + dur`
- `dur` between `per_track_min_s` and `min(req_s, view_length)`
- `eff_dur == dur` if present, else `0`

Create occupied antenna intervals that include setup and teardown: `occ_start = tx_on - setup_s`, `occ_end = tx_off + teardown_s`, and `occ_size = dur + setup_s + teardown_s`.

For each antenna, add `NoOverlap` over selected occupied intervals plus maintenance fixed intervals. For each request, consider adding `total_alloc <= req_s` and no-overlap among that request's transmission intervals.

## Objective Hints

SatNet's normalized score cares about `u_rms` and `u_max`, so do not chase raw tracking hours alone. A practical objective can combine:

```text
antenna communication seconds weighted by len(antennas)
+ satisfied request count
- subject/mission residual penalties
```

If modeling exact `u_rms` is awkward, use a simple proxy: compute subject requested seconds, allocated seconds, and penalize remaining demand. Let the verifier decide which incumbent is actually better.

## Iteration Pattern

Use bounded solves and keep `solution.json` valid while improving:

1. Run a short CP-SAT pass, such as 60-120 seconds.
2. Write and verify the emitted schedule.
3. Keep the best verifier-valid file.
4. Rerun with a larger time limit or warm-start hints from the current schedule.

For warm starts, group existing rows by `(TRACK_ID, START_TIME, TRACKING_ON, TRACKING_OFF, END_TIME)`. Match each group back to a candidate with the same sorted antenna tuple and compatible view period, then hint `present`, `tx_on`, `tx_off`, and `dur`.

## Output And Verification

Each selected logical track becomes one row per antenna with:

```text
TRACKING_ON = START_TIME + setup_s
END_TIME = TRACKING_OFF + teardown_s
TRX_ON <= TRACKING_ON <= TRACKING_OFF <= TRX_OFF
```

Sort rows deterministically, for example by `(START_TIME, RESOURCE, TRACK_ID)`, and run:

```bash
./verifier -v case/ solution.json
```

If a newer schedule is invalid, restore the previous valid file and fix the model or candidate generation before continuing.
