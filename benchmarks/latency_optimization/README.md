# Latency Optimization Benchmark

## Problem Description

Design a satellite relay network to minimize communication latency between ground stations. 
The agent must establish inter-satellite links (ISL) and downlinks to create low-latency paths
for data relay between geographically separated ground stations.

## Dataset Format

See `datasets/case_0001/` for example structure:
- `satellites.yaml` - Satellite definitions with TLE data
- `targets.yaml` - Target locations (if applicable)
- `stations.yaml` - Ground station positions
- `requirements.yaml` - Station pairs and latency requirements
- `manifest.json` - Case metadata including planning horizon

## Metrics

See `verifier.py` for scoring details.

Key metrics:
- `connection_coverage` - Fraction of requested time windows with connectivity
- `latency_min/max/mean_ms` - Signal propagation latency statistics
- `target_coverage` - Observation requirements coverage (if applicable)

## Baselines

- `baselines/greedy.py` - Greedy heuristic baseline
- `baselines/simulated_annealing.py` - Simulated annealing baseline

## Toolkit Compatibility

✓ Compatible with universal toolkit (`toolkit/`)
