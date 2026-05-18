# Regional Strip-Coverage Run Notes

## Final Metrics (case_0002)
- Valid: True
- coverage_ratio: 0.6309 (63.09%)
- weighted_coverage_ratio: 0.5748 (57.48%)
- num_actions: 31 (29 covering, 2 non-covering)
- min_battery_wh: 722.56 (well above 0)
- Zero violations

### Per-Region Coverage
- great_lakes: 0.8586 (85.86%) — 91.0B / 106.0B weight_m2
- indonesia_east: 0.4031 (40.31%) — 70.7B / 175.3B weight_m2

## Output Schema
```json
{
  "actions": [
    {
      "type": "strip_observation",
      "satellite_id": "sat_iceye-x43",
      "start_time": "2025-07-17T13:45:10Z",
      "duration_s": 60,
      "roll_deg": 18.4
    }
  ]
}
```
- type must be "strip_observation"
- start_time ISO 8601, aligned to 10s grid from horizon_start
- duration_s positive integer multiple of 10s, in [20, 180]
- roll_deg signed, abs(roll) in [18.4, 37.6] for this case

## Solver Approach

### Multi-Target Pass Detection
- Subsample coverage grid samples (~8 targets per region) as target points
- SGP4 propagation at 30s intervals
- For each (satellite, target_point): compute off-nadir angle, cross-track sign
- Proximity filter: sub-point within ~28°/48° lat/lon of target
- Merge overlapping passes (gap < 120s) on same satellite+region

### Candidate Generation
- Roll range: best_off_nadir ± 8°, step 1.5°, both signs
- Duration: 20–min(180, pass_dur) in 10s steps
- Start time: up to 8 positions within pass window

### Multi-Sort Greedy Selection
1. Duration-descending sort: picks longest strips first → 61.7% with 27 actions
2. Keep only covering actions (from verifier feedback)
3. Fill remaining slots with time-sorted candidates
4. Iterative prune non-covering + refill (5 rounds)

### Key Insight
- Duration-descending sort produces highest per-action coverage because longer strips cover more ground
- The fill passes add fewer actions but also tend to be non-covering
- Great Lakes coverage plateaus at ~86%; indonesia_east at ~40% due to limited pass coverage

## Verifier Feedback
- `./verifier case/ solution.json` returns JSON with valid, metrics, diagnostics.actions[*] (covered_sample_count, covered_region_ids)
- Use verifier to identify and remove non-covering actions

## Failed Approaches
- Pure time-sorted selection: early poor candidates block better later ones → ~0.5% coverage
- Blacklisting approach (v6): too aggressive pruning collapses the candidate pool
- IE-focused injection (v13): no improvement — unused IE passes don't intersect grid
- Batch verification (v11): too slow, verification of individual strips doesn't scale

## Key Command Patterns (brahe)
```python
bh.initialize_eop()
prop = bh.propagators.SGPPropagator.from_tle(line1, line2, step).with_name(sid)
prop.propagate_to(H1_EPOCH)
traj = prop.trajectory
epochs = traj.epochs()
itrf_states = traj.to_itrf().states()
ecef = bh.coordinates.position_geodetic_to_ecef([lon, lat, 0], bh.AngleFormat.DEGREES)
lonlat = bh.coordinates.position_ecef_to_geodetic(pos, bh.AngleFormat.DEGREES)
ep = bh.Epoch.from_string("2025-07-17T12:00:00Z")
epoch_diff_s = ep2 - ep1  # float seconds
```

## Working Solver
- `solve9.py` in workspace root is the working solver
