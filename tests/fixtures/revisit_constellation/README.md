# Revisit Constellation Test Fixtures

This directory contains committed end-to-end fixtures for the
`revisit_constellation` verifier.

## Purpose

The fixture suite complements the focused unit-style verifier tests in
[`tests/benchmarks/test_revisit_constellation_verifier.py`](/home/betelgeuse/Developments/AstroReason-Bench/tests/benchmarks/test_revisit_constellation_verifier.py).
These fixtures exercise the current benchmark contract through real
`assets.json`, `mission.json`, and `solution.json` inputs.

The goal is not to exhaustively cover every verifier branch. The goal is to
pin a small set of representative end-to-end outcomes:

- a valid case with no observations
- a valid case with one successful observation
- an invalid overlap case
- an invalid maneuver-timing case
- an invalid resource-accounting case

The suite is intentionally aligned with the current fixed-sampling verifier. It
does not try to specify future event-based geometry behavior.

## Fixtures

### `zero_observation/`

Valid solution with one satellite and no scheduled actions. The verifier should
return full-horizon revisit gaps.

### `single_observation_valid/`

Valid solution with one successful observation. This anchors the one-observation
metric path in a committed fixture.

### `downlink_overlap_invalid/`

Invalid solution with overlapping downlink actions on the same satellite. This
anchors the single-terminal overlap rule.

### `maneuver_conflict_invalid/`

Invalid solution with two observations scheduled too closely together for the
attitude model to slew and settle.

### `storage_underflow_invalid/`

Invalid solution where a downlink depletes storage below zero.

## Fixture Shape

Each fixture directory contains:

```text
fixture_name/
├── assets.json
├── mission.json
├── solution.json
└── expected.json
```

## `expected.json` Contract

The verifier tests treat `expected.json` as a partial assertion contract:

- `is_valid` is required.
- `metrics` is compared as a recursive subset, with floating-point values using
  approximate comparison.
- `errors` and `warnings` may be provided for exact matching.
- `errors_contain` and `warnings_contain` may be provided as substring checks.
- `error_count` and `warning_count` may be provided to pin list lengths.

This keeps invalid-fixture expectations stable even when error wording changes
slightly, while still preserving end-to-end verdict coverage.
