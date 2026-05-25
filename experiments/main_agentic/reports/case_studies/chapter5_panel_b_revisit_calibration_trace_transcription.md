# Panel B Trace Transcription: Implementation Calibration Against Verifier Feedback

## Summary

This report selectively transcribes the Revisit Constellation trace for `Claude Code + Claude Opus 4.6` on Revisit Constellation `case_0001`. The mechanism is implementation calibration: the evaluated system builds a private orbital and scheduling implementation, observes concrete disagreement from its own checks and then from the official verifier, diagnoses the mismatch, changes implementation details, re-runs the verifier, and eventually preserves a verifier-valid solution while reducing the constellation size.

The central finding is that the trace does not merely show "using a verifier." It shows a full calibration chain. The first private implementation looked strong by its own metric, reporting all target revisit gaps below the 6-hour capped threshold. But it also printed a 17.6 km GCRF-to-ITRF frame mismatch against Brahe, and the official verifier rejected the file with marginal off-nadir errors and slew-gap violations. The system correctly diagnosed the two causes, rewrote the implementation around Brahe J2 propagation and exact frame rotations, added verifier-facing slew safety when a later scheduler variant failed, and ended with a valid 10-satellite, 639-action solution at the capped 6-hour floor.

## Plain-English Task Contract

The official task is a joint constellation-design and scheduling problem. The evaluated system must write `solution.json` containing a proposed Earth-observation constellation at mission start and a sequence of observation actions. The case provides a satellite model, a maximum satellite count, a 48-hour mission horizon, and target revisit requirements. A solution is valid only if the proposed orbits, observation timing, line-of-sight geometry, off-nadir angle, range, slew timing, and other hard constraints satisfy the official checker.

For a cold reader, a revisit gap is the longest time a target waits between successful observations, including boundary gaps from the mission start and to the mission end. In this case, every target has an expected revisit period of 6 hours. The official scoring contract caps each target's gap at its expected requirement: if a target's actual maximum gap is below 6 hours, that target contributes exactly 6 hours to the capped score. Once all targets are below 6 hours, improving raw revisit frequency no longer improves the primary metric; the useful next step is to use fewer satellites while staying valid.

Small geometry errors matter because the official checker accepts or rejects observations at physical boundaries. A few hundredths of a degree beyond the off-nadir limit can invalidate an observation, and a same-satellite observation gap that is 60 seconds in the private model can fail if the official slew-plus-settle calculation requires roughly 62 seconds. `GCRF` is the inertial coordinate frame used for initial satellite states, while `ITRF` is the rotating Earth-fixed frame used to compare satellite positions to ground targets. `GMST` is one way to approximate Earth's rotation between those frames. A small-looking rotation mismatch can move a ground-relative satellite position by kilometers, which is enough to flip near-threshold visibility.

## Methodology

Evidence basis: the chronological beats below were checked against the event export. Workspace contract evidence comes from the README excerpts read in the trace at `seq 24` and `seq 150`; the full event-export path is listed in the appendix.

The beats below are selective rather than exhaustive and preserve the sequence needed to understand the calibration mechanism.

## Chronological Selective Transcription

### Beat 1: The evaluated system reads the official workspace contract

**Trace anchor:** `seq 23-24`, workspace README read.

**Event type:** contract acquisition.

**Exact snippet:**

```text
1 # Revisit-Oriented Constellation Design And Scheduling Problem
...
10 Your job is to produce `solution.json` with both:
12 - a proposed constellation at mission start
13 - a schedule of observation actions for that constellation
...
23 - satisfy all hard validity rules
24 - reduce average capped per-target revisit gaps
25 - then use fewer satellites when the revisit targets are already being met
```

This matters because the later private implementation is not created in a vacuum. The system has read that it must submit both constellation states and observation actions, and that satellite count is secondary only after revisit targets are met. This is different from a private-world failure: the task authority is acquired early.

### Beat 2: It checks for the local verifier and installed astrodynamics tools

**Trace anchor:** `seq 30-33`.

**Event type:** tool/environment inspection.

**Exact snippet:**

```text
verifier executable present
Python 3.13.11
...
brahe 1.4.2
numpy 2.2.6
scipy 1.17.1
sgp4 2.25
skyfield 1.54
```

The official verifier is present, but the trace does not show a `--help` probe. The system instead begins by building its own solver while knowing a local checker exists. That choice is normal for this task: the checker can reject final artifacts, but it does not search the design space.

### Beat 3: First private solver implementation commits to a Walker constellation and private propagation model

**Trace anchor:** `seq 71`, solver.py write.

**Event type:** solver code.

**Exact snippet:**

```python
#!/usr/bin/env python3
"""
Constellation design and observation scheduling solver for revisit-driven EO planning.
"""
...
# Walker constellation: use 20 satellites, 5 planes, 4 sats/plane
NUM_SATS = 20
ALT = 800e3
INC = 70.0
```

The first durable implementation is a complete private model: it chooses an architecture, propagates orbits, computes target access, schedules observations, and writes `solution.json`. It is not yet calibrated to the official checker. The important point is not that it uses private code; every serious solver must. The question is whether private code remains subordinate to official feedback.

### Beat 4: Early library/API mistakes force local calibration before benchmark calibration

**Trace anchors:** `seq 75`, `seq 80`, `seq 84`, `seq 98`.

**Event type:** command output from private solver attempts.

**Exact snippets:**

```text
TypeError: position_geodetic_to_ecef() missing 1 required positional argument: 'angle_format'
```

```text
ValueError: Input latitude out of range
```

```text
AttributeError: 'brahe._brahe.NumericalOrbitPropagator' object has no attribute 'states_gcrf'
```

These are not official benchmark failures; they are implementation calibration errors. They show the system learning the Brahe API and coordinate conventions. The `Input latitude out of range` error later leads it to infer that `position_geodetic_to_ecef` expects longitude-latitude-altitude ordering rather than the latitude-longitude-altitude ordering it first tried.

The inference appears explicitly in the trace:

```text
So the format is [longitude, latitude, altitude] not [latitude, longitude, altitude]. Let me fix that.
```

### Beat 5: The first self-check exposes a 17.6 km frame mismatch even while the private score looks excellent

**Trace anchor:** `seq 119`.

**Event type:** private solver output.

**Exact snippet:**

```text
GMST calibration: brahe=115.2379 deg, ours=113.5936 deg
GMST offset: 1.6443 deg
ITRF check at t=0: brahe=[-3017949.78588375 -6402475.5107734     17601.55107   ], ours=[-3017959.11730896 -6402495.30706745        0.        ]
Diff: 17601.56 m
ITRF check at t=24h: diff=17603.26 m
...
Mean capped max revisit gap: 6.00 hours
Worst target: Casablanca, Morocco (4.4h)
...
Solution written: 20 satellites, 942 actions
Estimated score: 6.00 hours
```

This is the first calibration-relevant mismatch. The private implementation says the case is already solved: every target's actual gap is well below the 6-hour requirement. At the same time, it prints a large Earth-fixed frame disagreement. The trace therefore contains a precise tension: a high-scoring private solution built on a geometry transform that the system itself knows is not aligned with Brahe.

### Beat 6: The evaluated system decides to let the official verifier arbitrate

**Trace anchor:** `seq 121`.

**Event type:** agent decision.

**Exact snippet:**

```text
Good - we have a solution with all gaps under 4.5 hours and a mean capped score of 6.0 (since all max gaps are below 6h, they get capped to 6.0). But there's a 17.6 km ITRF error due to my simplified rotation. Let me run the verifier to check validity, then work on matching the verifier's propagation more precisely.
```

This is the key authority move. The system does not treat its private score as final. It notices the transform discrepancy and explicitly runs the official verifier to resolve whether the private model is good enough.

### Beat 7: The official verifier rejects the first private solution with concrete geometry and slew diagnostics

**Trace anchors:** command at `seq 122`, result at `seq 123`.

**Event type:** official verifier output.

**Exact snippet:**

```text
Exit code 1
{
  "errors": [
    "Observation for target target_005 on sat_003 is infeasible at 2025-07-17T13:30:40Z: off-nadir angle 30.041 deg exceeds sensor max off-nadir angle 30.000 deg",
    "Observation for target target_028 on sat_008 is infeasible at 2025-07-18T10:39:10Z: off-nadir angle 30.349 deg exceeds sensor max off-nadir angle 30.000 deg",
    ...
    "Satellite sat_001 needs 63.507 sec between observations but only has 35.000 sec between 2025-07-17T23:42:30Z and 2025-07-17T23:43:05Z",
    "Satellite sat_010 needs 62.546 sec between observations but only has 35.000 sec between 2025-07-18T09:08:20Z and 2025-07-18T09:08:55Z"
  ],
  "is_valid": false,
  "metrics": {},
  "warnings": []
}
```

The verifier feedback is highly actionable. The off-nadir failures are just beyond the 30-degree boundary, consistent with kilometer-scale frame mismatch near access edges. The slew failures show a separate scheduling bug: same-satellite observation transitions were too tightly packed for the benchmark's slew-plus-settle model.

### Beat 8: The system diagnoses both causes and changes implementation strategy

**Trace anchors:** `seq 125-126`.

**Event type:** reasoning and agent decision.

**Exact snippet:**

```text
Off-nadir violations - my propagator doesn't match the verifier exactly. I need to add a safety margin or use brahe's propagator directly for the visibility check.
Slew constraint violations - I'm not properly checking slew constraints between consecutive observations.
...
The errors are from slight propagation/rotation mismatches and missing slew constraints. Let me use brahe's propagator directly for precision, and properly enforce slew constraints.
```

This is not a generic "try again." It is a causal diagnosis tied to the exact verifier output. It identifies two independent implementation gaps: numerical geometry and same-satellite timing.

### Beat 9: The rewrite uses Brahe J2 propagation and exact frame rotations

**Trace anchors:** exploratory timing at `seq 127-135`, rewrite at `seq 141`.

**Event type:** tool probing and solver code.

**Exact snippets:**

```text
Precomputed 17281 rotation matrices in 0.98s
Manual ITRF: [-2984634.02180352 -6331797.27595182    17407.24395275]
Brahe ITRF:  [-2984634.02180352 -6331797.27595182    17407.24395275]
Diff: 0.00 m
```

```python
"""
Constellation design and observation scheduling solver.
Uses brahe J2 propagator and exact frame rotations for verifier compatibility.
"""
...
rotations[i] = bh.rotation_gcrf_to_itrf(epc)
```

The new strategy preserves performance while matching the frame conversion authority. The system finds that direct ITRF queries are slow, but GCRF state queries and rotation matrices are fast enough. That is a real implementation calibration step: it changes the numerical model, not just a constant.

### Beat 10: The rewritten 20-satellite solution passes the official verifier

**Trace anchors:** private run `seq 144-145`, verifier `seq 146-147`.

**Event type:** private run followed by official verifier.

**Exact snippet:**

```text
Precomputing rotation matrices...
17281 rotation matrices precomputed
Created 20 satellites
All orbits valid
Propagating orbits with brahe J2...
...
Solution: 20 sats, 913 actions
Score: 6.000h
```

```json
{
  "errors": [],
  "is_valid": true,
  "metrics": {
    "capped_max_revisit_gap_hours": 6.0,
    "max_revisit_gap_hours": 4.658333333333333,
    "num_satellites": 20,
    "threshold_violation_count": 0
  },
  "warnings": []
}
```

This confirms the first calibration loop. The official checker accepts the same broad design class after the implementation is aligned with Brahe frame rotation and with explicit same-satellite constraints.

### Beat 11: The system uses the scoring formula to switch objectives

**Trace anchors:** README reread at `seq 149-150`, reasoning at `seq 151`, message at `seq 152`.

**Event type:** contract reread and objective switch.

**Exact snippet:**

```text
target_capped_gap = max(max_revisit_gap_hours, expected_revisit_period_hours)
capped_max_revisit_gap_hours = mean(target_capped_gap over targets)
```

```text
Since expected_revisit_period_hours is 6.0 for all targets, and all our max gaps are below 6.0h, every target's capped gap is exactly 6.0h, so the mean is 6.0.

The primary metric is already at the floor (6.0) which is the best possible value. The secondary metric is num_satellites (lower is better). So I should try to reduce the number of satellites while keeping all gaps under 6h.
```

The system now adapts to the case's scoring structure. More observations with 20 satellites cannot improve the primary score, so it starts searching for smaller constellations that preserve the official floor.

### Beat 12: A later 12-satellite scheduler variant fails the verifier on slew margins

**Trace anchors:** private run `seq 182-183`, official verifier `seq 185-186`.

**Event type:** private optimization and official failure.

**Exact snippet:**

```text
Created 12 satellites (Walker 12/4/1, inc=58.0, alt=700km)
...
Phase 1 scheduled: 632
Max gap: 5.944h
Solution: 12 sats, 632 actions
Score: 6.000h
```

```json
{
  "errors": [
    "Satellite sat_001 needs 63.371 sec between observations but only has 60.000 sec between 2025-07-17T12:41:50Z and 2025-07-17T12:42:50Z",
    "Satellite sat_002 needs 62.266 sec between observations but only has 60.000 sec between 2025-07-18T02:22:50Z and 2025-07-18T02:23:50Z",
    ...
  ],
  "is_valid": false,
  "metrics": {}
}
```

This is the second calibration loop. The numerical propagation is now aligned, but a modified scheduler underestimates the official slew gap by a few seconds. The failure is narrow and interpretable.

### Beat 13: The system repairs the scheduler with a verifier-facing safety margin

**Trace anchors:** `seq 187-195`.

**Event type:** diagnosis, code edit, verifier success.

**Exact snippet:**

```text
The issue is the slew constraint. The gaps between consecutive observations are 60 seconds but the required gap is ~62 seconds. This means my slew checking is slightly off - the verifier computes a different slew angle than I do.
```

```python
def compute_required_gap(theta_deg):
    return compute_slew_time(theta_deg) + settling_time_sec + 5.0  # 5s safety margin
```

```json
{
  "errors": [],
  "is_valid": true,
  "metrics": {
    "capped_max_revisit_gap_hours": 6.0,
    "max_revisit_gap_hours": 5.944444444444445,
    "num_satellites": 12,
    "threshold_violation_count": 0
  }
}
```

The repair sacrifices some scheduling density but preserves the score floor. The trace sequence is compact: the verifier says 60 seconds is not enough, the code adds a 5-second buffer, and the verifier accepts.

### Beat 14: The system searches smaller constellations and finds a 10-satellite verifier-valid solution

**Trace anchors:** `seq 216`, `seq 237`, `seq 244`, `seq 263-264`.

**Event type:** search output and final verifier.

**Exact snippets:**

```text
11sat 11: W12/4 -1 i50 a700 : max=5.936h [OK]
```

```text
All 12 satellites propagated
Precomputed 331 access window sets
  Drop (0, 1): max_gap=6.092h [FAIL]
  Drop (0, 2): max_gap=6.008h [FAIL]
  Drop (0, 11): max_gap=5.933h [OK]

Best 10-sat combo: drop (0, 11), max_gap=5.933h
```

```json
{
  "errors": [],
  "is_valid": true,
  "metrics": {
    "capped_max_revisit_gap_hours": 6.0,
    "max_revisit_gap_hours": 5.933333333333334,
    "num_satellites": 10,
    "threshold_violation_count": 0
  }
}
```

```text
Valid: True
Score: 6.0
Max gap: 5.933333333333334
Satellites: 10
Violations: 0
```

The final result is not just a fixed implementation; it is a calibrated search loop. The system preserves an official valid artifact, switches to the secondary metric only after the primary floor is reached, and confirms the compact design with the verifier.

## Findings

First, the trace supports implementation calibration because there are concrete mismatches, not just vague improvement. The private model prints a 17.6 km frame discrepancy; the official checker reports off-nadir errors such as 30.041 degrees against a 30.000-degree limit; the scheduler later fails because 60 seconds is shorter than required slew-plus-settle gaps around 62 to 63 seconds. Each mismatch is followed by a specific diagnosis and implementation change.

Second, the official verifier remains the final authority. The evaluated system uses private propagation, private scheduling, and private optimization throughout, but it repeatedly lets the verifier reject candidates. It does not conclude that its own score is enough when the checker disagrees.

Third, the search is case-adaptive but not globally proven. The final message says 10 satellites is "optimal" and that 9 cannot achieve the 6-hour requirement. The trace only proves a narrower claim: 10 satellites passed the official verifier; the tested 9-satellite removals and several 9-satellite Walker patterns failed. A figure should present the verifier-calibrated improvement, not a global optimality proof.

The tested-search evidence is concrete:

```text
Best 9-sat: drop (1, 4, 5), max_gap=6.058h
```

```text
9sat 9/3/1 i48 a700           : max_gap=7.586h [FAIL]
```

The evaluated system then claimed:

```text
9 satellites definitively can't achieve 6h revisit (best is 6.058h from dropping optimally). 10 is the minimum.
```

Those lines justify treating 10 satellites as the best trace-tested result, but not as a mathematical global optimum.

## Per-Trace Appendix

- Trace: `experiments/main_agentic/reports/traces/data/events/revisit_constellation__claude_code__test__case_0001.js`
- Evaluated system: `Claude Code + Claude Opus 4.6`
- Task family and case: Revisit Constellation, `case_0001`
- Key contract events: `seq 23-24`, `seq 149-151`
- First private implementation: `seq 71`
- First private frame mismatch: `seq 119`
- First official verifier failure: `seq 122-123`
- Main implementation rewrite: `seq 141`
- First official valid result after rewrite: `seq 146-147`
- Scheduler mismatch and repair: `seq 185-195`
- Final official valid result: `seq 262-263`

## Figure-Design Usable Snippets

1. Bridge: The official task contract is acquired before solver construction. Suggested snippet: `produce solution.json with both: a proposed constellation ... and a schedule of observation actions`. Highlight: `both`.

2. Bridge: The private implementation initially looks successful but carries a frame mismatch. Suggested snippet: `Diff: 17601.56 m` next to `Estimated score: 6.00 hours`. Highlight: `17601.56 m`.

3. Bridge: The system explicitly hands authority to the checker. Suggested snippet: `Let me run the verifier to check validity`. Highlight: `verifier`.

4. Bridge: The verifier exposes marginal geometry failure. Suggested snippet: `off-nadir angle 30.041 deg exceeds ... 30.000 deg`. Highlight: `30.041`.

5. Bridge: The verifier exposes timing failure. Suggested snippet: `needs 63.507 sec ... only has 35.000 sec`. Highlight: `needs 63.507`.

6. Bridge: The agent diagnoses the implementation, not the case. Suggested snippet: `my propagator doesn't match the verifier exactly`. Highlight: `doesn't match`.

7. Bridge: The implementation changes to verifier-compatible numerics. Suggested snippet: `Uses brahe J2 propagator and exact frame rotations for verifier compatibility`. Highlight: `verifier compatibility`.

8. Bridge: The calibrated implementation passes. Suggested snippet: `Verifier returned no errors; the 20-satellite solution kept the capped gap at 6.0 h`. Highlight: `no errors`.

9. Bridge: The same calibration pattern recurs on scheduling. Suggested snippet: `gaps ... 60 seconds but the required gap is ~62 seconds`. Highlight: `60` and `~62`.

10. Bridge: The final result is verifier-confirmed. Suggested snippet: `Score: 6.0`, `Max gap: 5.933333333333334`, `Satellites: 10`, `Violations: 0`. Highlight: `Violations: 0`.
