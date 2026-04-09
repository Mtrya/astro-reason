# Regional Coverage Verifier Test Fixtures

This directory contains committed end-to-end fixtures for the
`regional_coverage` verifier.

## Purpose

The fixture suite complements the focused unit-style verifier tests in
[`tests/benchmarks/test_regional_coverage_verifier.py`](../../benchmarks/test_regional_coverage_verifier.py).
These fixtures exercise the current benchmark contract through real
`manifest.json`, `satellites.yaml`, `regions.geojson`, `coverage_grid.json`,
and `solution.json` inputs.

The goal is not to exhaustively cover every verifier branch. The goal is to pin
a small set of representative end-to-end outcomes:

- a valid case with one successful strip
- a valid weighted-scoring case
- a valid repeated-coverage case with no revisit bonus
- invalid cases for slew, off-nadir bounds, battery depletion, and imaging duty

## Fixtures

### `single_strip_valid/`

Valid solution with one strip that fully covers one weighted sample.

### `weighted_region_scoring_valid/`

Valid solution where only the higher-weight region is covered. This pins the
global weighted `coverage_ratio`.

### `repeat_coverage_no_bonus_valid/`

Valid solution where two satellites cover the same sample set. Unique covered
weight must not increase after the second pass.

### `slew_gap_invalid/`

Invalid solution with two same-satellite strips that do not leave enough time
to slew and settle.

### `edge_band_invalid/`

Invalid solution whose roll angle violates the sensor off-nadir edge band.

### `battery_depletion_invalid/`

Invalid solution with geometrically valid imaging but infeasible battery state.

### `imaging_duty_limit_invalid/`

Invalid solution that exceeds the per-orbit imaging duty limit.

## Fixture Shape

Each fixture directory contains:

```text
fixture_name/
├── manifest.json
├── satellites.yaml
├── regions.geojson
├── coverage_grid.json
├── solution.json
└── expected.json
```

All fixtures use a minimal synthetic dataset built around one pinned ICEYE TLE,
small square regions, and tiny weighted grids that are easy to reason about.

## `expected.json` Contract

The verifier tests treat `expected.json` as a partial assertion contract:

- `valid` is required.
- `metrics` is compared as a recursive subset, with floating-point values using
  approximate comparison.
- `violations_contain` may be provided as a list of substrings that must each
  appear in at least one violation string.
- `violation_count` may be provided to pin the exact number of violations.

This keeps invalid-fixture expectations stable even when wording shifts
slightly, while still preserving end-to-end verdict coverage.
