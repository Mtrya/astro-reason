# Relay Constellation Run Notes

## Final Metrics
- service_fraction: 0.9813
- worst_demand_service_fraction: 0.8917 (demand_001: 107/120)
- mean_latency_ms: 183.77
- latency_p95_ms: 359.14
- num_added_satellites: 0
- num_actions: 207 (39 ground, 168 ISL)
- Valid: true, 0 violations

## Case Summary
- 8 backbone satellites at ~10000km altitude (MEO)
- 5 ground endpoints across the globe
- 7 demanded communication windows, total weight 7.0
- 4-day horizon, 60s routing step
- Hard constraints: max_links_per_satellite=3, max_links_per_endpoint=1

## Effective Approach

### Solver Strategy
1. Propagate backbone satellites with J2-only gravity (brahe NumericalOrbitPropagator, degree=2 order=0 spherical harmonics)
2. For each 60s timestep, build a degree-constrained graph:
   - Select best ground link per active endpoint (shortest range, min 10° elevation)
   - Build spanning tree connecting ground-linked satellites via ISLs
   - Fill remaining degree budget (up to 3 per satellite) with extra ISL edges (shortest first)
3. Convert per-timestep selections to contiguous action intervals (merge adjacent identical links)
4. Write solution.json

### Key Insight
The fundamental bottleneck is max_links_per_endpoint=1. During overlapping demand windows sharing a ground endpoint (e.g., demand_001 and demand_007 both need ground_003 at samples 4240-4250), at most one demand can use that endpoint's link per sample (unit capacity). This causes ~5-8 unavoidably unserved samples for demand_001.

ISL competition costs another ~10-12 unserved samples during demand_001/demand_002 overlap (samples 4130-4195), despite providing ~11 ISL edges per timestep. Cannot eliminate entirely with degree-3 constraint.

### Failed Approaches
- Adding LEO satellites (500-1500km) made service WORSE (96.8% vs 98.1%). The verifier's routing through LEO sats causes more contention due to rapidly changing ISL topology.
- Ring topology with extra edges caused degree violations (some satellites at degree 4).
- Attempting edge-disjoint path provisioning gave same metrics (98.1%) with slightly worse latency.

### Propagation Setup
```python
gravity = bh.GravityConfiguration.spherical_harmonic(degree=2, order=0, model_type=bh.GravityModelType.EGM2008_360)
force = bh.ForceModelConfig(gravity=gravity, mass=bh.ParameterSource.value(1000.0))
config = bh.NumericalPropagationConfig.default()
prop = bh.NumericalOrbitPropagator(epoch, state, config, force, np.array([1000.0]))
prop.set_trajectory_mode(bh.TrajectoryMode.ALL_STEPS)
prop.propagate_to(end_epoch)
```

### Coordinate Transformations
- `bh.position_gcrf_to_itrf(epoch, pos_gcrf)` for GCRF→ITRF (epoch FIRST, then position)
- `bh.relative_position_ecef_to_enz(gnd_pos, sat_pos, bh.EllipsoidalConversionType.GEODETIC)` for elevation
- `bh.position_enz_to_azel(rel, bh.AngleFormat.DEGREES)[1]` for elevation angle

### Verifier Usage
- `./verifier case/ solution.json` returns validity + metrics
- Valid actions first, then metrics matter
- Action failures = 0 needed for valid

## Output Schema
```json
{
  "added_satellites": [],
  "actions": [
    {"action_type": "ground_link", "start_time": "ISO", "end_time": "ISO",
     "endpoint_id": "...", "satellite_id": "..."},
    {"action_type": "inter_satellite_link", "start_time": "ISO", "end_time": "ISO",
     "satellite_id_1": "...", "satellite_id_2": "..."}
  ]
}
```

## Command Pattern
```bash
python3 scratch/solver_v6.py  # Generate solution
./verifier case/ solution.json  # Verify
```
