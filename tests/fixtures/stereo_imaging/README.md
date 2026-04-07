# Stereo Imaging Verifier Test Fixtures

This directory contains committed end-to-end fixtures for the
`stereo_imaging` verifier.

## Purpose

The fixture suite complements the focused unit-style verifier tests in
[`tests/benchmarks/test_stereo_imaging_verifier.py`](../../benchmarks/test_stereo_imaging_verifier.py).
These fixtures exercise the current benchmark contract through real
`mission.yaml`, `satellites.yaml`, `targets.yaml`, and `solution.json` inputs.

The goal is not to exhaustively cover every verifier branch. The goal is to
pin a small set of representative end-to-end outcomes:

- a valid case with no observations
- an invalid case with overlapping observations
- an invalid case with insufficient slew/settle gap

## Fixtures

### `empty_solution/`

Valid solution with zero actions. The verifier should return zero coverage and
zero quality.

### `time_overlap_invalid/`

Invalid solution with two observations that overlap temporally on the same
satellite.

### `slew_too_fast_invalid/`

Invalid solution where two observations targeting different locations have zero
gap, which is far too short for the satellite to slew and settle.

## Fixture Shape

Each fixture directory contains:

```text
fixture_name/
├── mission.yaml
├── satellites.yaml
├── targets.yaml
├── solution.json
└── expected.json
```

All fixtures use a minimal synthetic dataset: one satellite (Pleiades-1A TLE),
one or two equatorial targets, and a six-hour horizon.

## `expected.json` Contract

The verifier tests treat `expected.json` as a partial assertion contract:

- `valid` is required.
- `metrics` is compared as a recursive subset, with floating-point values
  using approximate comparison.
- `violations_contain` may be provided as a list of substrings that must
  each appear in at least one violation string.
- `violation_count` may be provided to pin the exact number of violations.

This keeps invalid-fixture expectations stable even when error wording changes
slightly, while still preserving end-to-end verdict coverage.
