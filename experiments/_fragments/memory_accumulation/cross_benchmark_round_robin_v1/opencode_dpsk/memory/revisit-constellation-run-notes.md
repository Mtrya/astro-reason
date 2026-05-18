# Revisit Constellation Run Notes

## Final Metrics
- Valid: True
- capped_max_revisit_gap_hours: 8.000 (minimum)
- num_satellites: 12 (out of max 16)
- Max actual revisit gap across targets: ~6.43 hours (target_012 Khartoum)
- All 25 targets have max gaps under 8.0 hours

## Output Schema
```json
{
  "satellites": [
    {
      "satellite_id": "0",
      "x_m": ..., "y_m": ..., "z_m": ...,
      "vx_m_s": ..., "vy_m_s": ..., "vz_m_s": ...
    }
  ],
  "actions": [
    {
      "action_type": "observation",
      "satellite_id": "0",
      "target_id": "target_001",
      "start": "2025-07-17T12:09:09Z",
      "end": "2025-07-17T12:10:39Z"
    }
  ]
}
```

## Solver Approach That Works

### 1. Accurate Propagation (Critical)
- MUST use NumericalOrbitPropagator with J2 gravity (spherical harmonic degree=2, order=0)
- KeplerianPropagator does NOT match the verifier's J2 propagation
- RAAN precession of ~1 deg/day causes ~23° off-nadir error over 48h
- Access windows computed with Keplerian were completely wrong
- Use `bh.par_propagate_to()` for fast parallel propagation of all satellites

### 2. Access Computation
- Use `bh.location_accesses()` with batch processing (all locations × 4 props per batch)
- Constraint: `ConstraintAll([ElevationConstraint(min=25.5), OffNadirConstraint(max=29.5)])`
- 0.5° margin on both elevation and off-nadir needed for numerical differences
- Range check with 2% margin at window midpoint
- Pass satellite IDs via `prop.with_id(int)` and target names via `loc.with_name(str)`
- AccessSearchConfig with initial_time_step=30s

### 3. Constellation Design
- Best: 4 planes × 3 satellites at 800 km sun-synchronous (~97.6° inclination)
- Walker delta pattern with F=1 phasing
- 12 satellites provides full global coverage for the 25 targets
- Altitude 800 km gives wider swath (longer access windows) than 600 km
- More planes (4) better than fewer planes with more sats-per-plane (3×4)

### 4. Scheduling
- Balanced scheduler: process in 30-min time bins, prioritize targets with longest time since last observation
- Same-target minimum gap: 30 minutes (too short causes clustering, too long misses opportunities)
- Max observation duration: 90s (window center, safest for off-nadir)
- Slew gap computation using ECI inertial angle between target vectors at observation midpoints

### 5. Timestamp Formatting
- Use `epoch.to_pydatetime().timestamp()` and reconstruct with `datetime.fromtimestamp(tz=utc)` 
- brahe's `isostring()` has a bug where seconds near 59.999 display as "60"
- satellite_id and target_id must be STRINGS in the JSON output

### 6. Force Model Configuration
```python
force_config = bh.ForceModelConfig(
    gravity=GravityConfiguration.spherical_harmonic(degree=2, order=0, model_type=GravityModelType.EGM2008_360),
    mass=ParameterSource.value(100.0),
)
```

## Failed Approaches
- KeplerianPropagator: off-nadir errors of 30-45° due to J2 RAAN precession
- Single-call location_accesses with all 16 props: unknown issues, use batches of 4
- Default ForceModelConfig: requires space weather data (NRLMSISE-00 drag model)
- Too-short same-target minimum gap (5 min): causes observation clustering and larger gaps elsewhere
- isostring() for timestamps: produces :60Z which is invalid ISO 8601

## What Didn't Work Well
- < 10 satellite configurations: cannot maintain < 8h revisit gaps for all 25 targets
- 9 satellite configs (3p×3s): metric ~8.3, close but not 8.0
- 2-plane configurations: poor longitudinal coverage

## Command Patterns
```bash
./verifier case/ solution.json
python3 solver.py
```
