# Revisit Optimization Benchmark

## Problem Description

Optimize satellite observation schedules to minimize the maximum revisit gap for monitoring targets.
The agent must schedule repeat observations to maintain coverage frequency while satisfying satellite 
resource constraints (power, storage, slew rates).

## Dataset Format

See `datasets/case_0001/` for example structure:
- `satellites.yaml` - Satellite definitions with TLE data
- `targets.yaml` - Monitoring and mapping target locations
- `stations.yaml` - Ground station positions for downlinks
- `requirements.yaml` - Target observation requirements
- `manifest.json` - Case metadata including planning horizon

## Metrics

See `verifier.py` for scoring details.

Key metrics:
- `target_coverage` - Fraction of required observations completed
- `max_gap_hours` - Maximum gap between consecutive observations per target
- `avg_gap_hours` - Average gap between consecutive observations

## Baselines

- `baselines/greedy.py` - Greedy heuristic baseline
- `baselines/simulated_annealing.py` - Simulated annealing baseline

## Toolkit Compatibility

✓ Compatible with universal toolkit (`toolkit/`)
