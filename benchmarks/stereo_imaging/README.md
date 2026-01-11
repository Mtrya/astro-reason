# Stereo Imaging Benchmark

## Problem Description

Plan satellite observations to acquire stereo image pairs for 3D terrain reconstruction.
The agent must schedule observations of targets from different viewing angles (azimuth separation)
that meet stereo geometry constraints.

## Dataset Format

See `datasets/case_0001/` for example structure:
- `satellites.yaml` - Satellite definitions with TLE data
- `targets.yaml` - Target locations requiring stereo imaging
- `stations.yaml` - Ground station positions for downlinks
- `requirements.yaml` - Stereo geometry requirements (min/max azimuth separation)
- `manifest.json` - Case metadata including planning horizon

## Metrics

See `verifier.py` for scoring details.

Key metrics:
- `stereo_coverage` - Fraction of targets with valid stereo pairs
- `num_stereo_targets` - Count of targets with stereo coverage
- `target_coverage` - Overall observation requirements coverage

## Baselines

- `baselines/greedy.py` - Greedy heuristic baseline
- `baselines/simulated_annealing.py` - Simulated annealing baseline

## Toolkit Compatibility

✓ Compatible with universal toolkit (`toolkit/`)
