# Regional Coverage Benchmark

## Problem Description

Plan satellite observations to maximize area coverage over specified geographic regions.
The agent must schedule strip observations (continuous ground tracks) to cover polygonal 
regions with overlapping swaths.

## Dataset Format

See `datasets/case_0001/` for example structure:
- `satellites.yaml` - Satellite definitions with TLE data and swath widths
- `targets.yaml` - Target locations (if applicable)
- `stations.yaml` - Ground station positions
- `requirements.yaml` - Polygon regions and coverage requirements
- `manifest.json` - Case metadata including planning horizon

## Metrics

See `verifier.py` for scoring details.

Key metrics:
- `coverage_percentage` - Fraction of each polygon area covered by observations
- `mean_coverage_ratio` - Average coverage across all regions

## Baselines

- `baselines/greedy.py` - Greedy heuristic baseline
- `baselines/simulated_annealing.py` - Simulated annealing baseline

## Toolkit Compatibility

✓ Compatible with universal toolkit (`toolkit/`)
