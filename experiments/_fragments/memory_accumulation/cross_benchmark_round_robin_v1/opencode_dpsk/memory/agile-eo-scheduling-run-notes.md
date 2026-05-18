# Agile Earth-Observation Scheduling Run Notes (case_0001)

## Final Metrics
- Valid: True
- CR: 0.8135 (81.3%)
- WCR: 0.7616 (76.2%)
- TAT: 953.7s
- PC: 21201.1 Wh
- Scheduled: 1439/1769 tasks
- 0 violations

## Output Schema
```json
{
  "actions": [
    {
      "type": "observation",
      "satellite_id": "sat_001",
      "task_id": "task_0001",
      "start_time": "2026-04-14T09:43:30Z",
      "end_time": "2026-04-14T09:44:15Z"
    }
  ]
}
```
- Actions sorted by (satellite_id, start_time)
- Timestamps in ISO 8601 UTC with trailing Z

## Solver Approach That Worked

### 1. Access Computation
- Use `bh.location_accesses` with `ConstraintAll([ElevationConstraint(0), OffNadirConstraint(max_off_nadir)])`
- `AccessSearchConfig(initial_time_step=30.0, adaptive_step=True, time_tolerance=0.1, parallel=True, num_threads=4)`
- Clip windows to task release/due times
- Add 3s safety margin on each side to avoid geometry sample-point violations

### 2. Candidate Generation
- For each access window, generate candidates at 50 evenly-spaced positions within the window
- Align to 5s grid (dt)
- Deduplicate by (satellite_id, task_id, start_time)

### 3. Sunlight / Battery
- Precompute sunlit intervals per satellite at 60s resolution using `bh.eclipse_cylindrical` + `bh.sun_position`
- Battery simulation at 10s (resource_sample_step_s) granularity
- Charge = sunlit_charge_power_w if sunlit, else 0

### 4. Slew Gaps
- Compute slew angle between target vectors (sat-to-target) in GCRF frame using `bh.rotation_ecef_to_eci`
- Gap = slew_time(theta, omega, alpha) + settling_time, with 10% + 1s safety margin
- First observation on each satellite needs slew from nadir at H0
- Use `_find_neighbors` for proper chronological adjacency

### 5. Scheduling Strategy (Key Breakthrough)
- **chrono+weight**: sort candidates by (start_time asc, weight desc)
- This packs the timeline densely by processing in time order, prioritizing weight within each time slot
- Weight-desc strategy gave WCR=58% vs chrono+weight's 76%
- Two-pass (weight-5 first) was worse at 68%

## Failed Approaches
- Weight-desc sorting: only 58% WCR, poor packing
- 1s access window margin: 335 off-nadir violations
- 10s margin: too conservative, lost ~100 tasks
- Two-pass scheduling (weight-5 first, then rest): 68% WCR
- Using `bh.math.norm` (doesn't exist): all slew angles fell back to 60° default

## Key Command Patterns
- EOP init: `bh.initialize_eop()` before all brahe operations
- Epoch creation: `bh.Epoch(y, m, d, H, M, S, ns)` from datetime fields
- Epoch to seconds: `float(ep - H0)`
- Sat state: `prop.state_gcrf(ep)`, `prop.state_ecef(ep)`
- Events: SGPPropagator doesn't support SunlitEvent; use `bh.eclipse_cylindrical` instead
- Epoch.to_datetime() returns tuple `(y, m, d, H, M, S, ns)`
- Verifier: `./verifier case/ solution.json`
- Access window retrieval: windows are list of AccessWindow with `.window_open`, `.window_close` (Epochs)
