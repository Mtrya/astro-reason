# Stereo Imaging Benchmark

## Problem Description

Plan optical satellite observations to acquire same-pass stereo or tri-stereo imagery for 3D terrain reconstruction.
The planning problem focuses on physically meaningful observation geometry, retargeting cost, and overlap quality rather than photogrammetry internals.

## Dataset Format

See [`SPEC_v3.md`](SPEC_v3.md) for the canonical public contract.

Each case lives under `dataset/cases/<case_id>/` and contains:
- `satellites.yaml` - Real Earth-observation satellites with frozen TLEs and compact public sensor/agility fields
- `targets.yaml` - Continuous target coordinates with `aoi_radius_m`, `elevation_ref_m`, and `scene_type`
- `mission.yaml` - Planning horizon plus stereo validity and quality thresholds

Dataset-level artifacts:
- `dataset/index.json` - Canonical case inventory and source provenance
- `dataset/example_solution.json` - Minimal runnable verifier smoke-test actions

## Metrics

See [`SPEC_v3.md`](SPEC_v3.md) and [`verifier/run.py`](verifier/run.py) for scoring details.

Key metrics:
- `valid` - Whether all hard action and geometry constraints are satisfied
- `coverage_ratio` - Fraction of targets with at least one valid stereo or tri-stereo product
- `normalized_quality` - Mean best-per-target stereo quality across the case

## Generator Notes

The canonical generator uses:
- runtime downloads for CelesTrak Earth-resources TLEs and the reproducible world-cities table
- vendored 1-degree lookup tables for elevation and non-urban scene classification

Large terrain and land-cover inputs are used only during lookup-table derivation, not during normal dataset generation or CI.
