# Revisit Constellation Benchmark

## Status

This benchmark is in active design and migration.

It is intended to replace `benchmarks/revisit_optimization/` after the new
benchmark is fully implemented, tested, and documented. Until then,
`revisit_optimization` remains as a reference for legacy dataset structure and
benchmark-side tooling ideas.

## Problem Summary

Design an Earth observation constellation and an operating schedule that keeps
target revisit gaps as small as possible over a mission horizon.

For each case, the space agent receives a problem instance describing:

- a satellite model
- target locations
- hard mission and orbit constraints
- mission start and end times
- an expected revisit gap threshold

The space agent must return:

- a constellation definition
- a sequence of scheduled actions

The benchmark combines two decisions in a single task:

1. constellation architecture design
2. mission scheduling

## Intended Benchmark Scope

The architecture-design part of the benchmark means defining the initial states
of satellites at mission start time. At a high level, a solver chooses how many
satellites to deploy, up to the case-specific cap, and specifies each
satellite's initial state in the GCRF frame.

The scheduling part of the benchmark means producing a feasible action sequence
for that constellation over the mission horizon.

Launch design, launch cost, and deployment operations are out of scope. The
benchmark assumes that the proposed satellites already exist in their initial
states at the mission start time.

## Case Inputs

The exact file schema is still being refined, but each canonical case is
expected to include inputs equivalent to:

- `satellite_model.*`
  A benchmark-defined satellite model or model family. This will describe the
  resource and operational properties shared by satellites in the case.
- `targets.*`
  Target identities and locations.
- `stations.*`
  Ground station identities and locations for downlink opportunities.
- `constraints.*`
  Hard case constraints, including at least:
  - maximum number of satellites
  - orbit admissibility constraints
  - observation-success conditions such as elevation and distance rules
  - onboard resource limits such as power and storage
- `mission.*`
  Mission horizon with start and end times.
- `requirements.*`
  Revisit-oriented mission requirements, including an expected revisit gap
  threshold.
- `manifest.json`
  Case metadata and summary values used for identification and inspection.

The final file names and field-level schema are intentionally left open for now.

## Solution Contract

A valid solution is expected to contain two top-level parts:

- `constellation`
- `actions`

### Constellation

The constellation section defines the satellites present at mission start. Each
satellite entry is expected to include:

- a solver-chosen satellite identifier
- a state epoch matching the case horizon start
- a reference frame of `GCRF`
- initial position
- initial velocity

At a high level, the solver is designing the constellation by choosing the
initial states of satellites, subject to the benchmark's orbit and count
constraints.

### Actions

The action list defines the mission schedule for the proposed constellation.

The intended initial action types are:

- `observation`
- `downlink`

Each action is expected to identify the satellite involved and the action start
and end times. Observation actions also identify a target, and downlink actions
also identify a ground station.

The exact action schema is still to be finalized.

## Validity Rules

Constraint violations should invalidate a solution immediately. In other words,
metrics are only meaningful for solutions that satisfy all hard constraints.

The verifier is expected to reject a solution if any of the following occur:

- malformed solution structure
- more satellites than the case permits
- satellite initial states that violate orbit constraints
- infeasible observation geometry
- infeasible downlink geometry
- power constraint violations
- storage constraint violations
- inconsistent or overlapping action timing
- references to unknown satellites, targets, or stations

Additional hard-validity checks may be added as the schema becomes more
concrete.

## Metrics And Ranking

The legacy mapping-coverage branch is intentionally removed from this benchmark.
The new benchmark is purely revisit-driven.

The intended metrics for valid solutions are:

- `mean_revisit_gap`
- `satellite_count`

The intended ranking logic is:

1. If not all targets achieve revisit gaps below the expected revisit gap
   threshold, prefer the solution with better revisit performance.
2. If all targets achieve revisit gaps below the expected revisit gap
   threshold, prefer the solution that uses fewer satellites.
3. Use revisit performance as a tie-break among solutions with the same
   satellite count.

The exact tie-break details and any derived summary metrics are still open for
refinement.

## Revisit Interpretation

The benchmark should treat poor revisit performance as poor scoring, not as an
automatic validity failure.

In particular:

- missing observations should degrade revisit metrics
- sparse observations should degrade revisit metrics
- only hard physical, temporal, geometric, and resource violations should make
  a solution invalid

The precise definition of revisit gap, especially at mission boundaries or for
targets with zero or one successful observation, is still to be finalized.

## Canonical Benchmark Shape

The intended repository structure is:

```text
benchmarks/revisit_constellation/
├── dataset/
├── generator.py
├── verifier.py
└── README.md
```

Associated test-side artifacts are expected under:

```text
tests/fixtures/
tests/benchmarks/
```

## Near-Term Design Questions

The following details are intentionally still open and should be settled before
full implementation:

- the exact satellite model schema
- the exact case file names and formats
- the exact solution JSON schema
- the exact orbit admissibility rules
- the exact observation and downlink geometry rules
- the exact resource propagation model
- the exact revisit-gap computation at mission boundaries
- the exact tie-break rule once all targets meet the threshold

## Implementation Direction

This benchmark should be built as a new standalone benchmark, even if parts of
`revisit_optimization` are reused as raw ingredients or migration references.

The expected implementation sequence is:

1. finalize the benchmark spec
2. define one pilot case and solution schema
3. implement the verifier around that contract
4. create fixtures and focused tests
5. add a generator and generate the canonical dataset
6. retire `revisit_optimization` once the replacement is complete
