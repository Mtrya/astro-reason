# J2 RGT Set-Cover Solver

This solver is being built for `revisit_constellation` issue #133.

Phase 3 implements the foundation for architecture search: J2-aware
repeat-ground-track orbit-template construction, RAAN-phased candidate coverage
envelopes, and satellite-cost set-cover selection. Equal-phase satellite
population and scheduling are intentionally left for later phases.

The solver is standalone. It reads benchmark case files directly and does not
import benchmark, experiment, runtime, or other solver internals.

## Contract

```bash
./setup.sh
./solve.sh <case_dir> [config_dir] [solution_dir]
```

Phase 3 writes:

- `solution.json`: an empty benchmark-shaped solution placeholder
- `status.json`: closure-search, candidate-coverage, and selection summaries
- `debug/closure_search.json`: accepted and rejected J2 RGT template records
- `debug/coverage_summary.json`: RAAN-phased candidates, access windows, and deterministic target/candidate indexes
- `debug/selection_summary.json`: selected candidates, assigned targets, total satellite cost, and budget blockers

## Terminology

Phase 1 intentionally constructs **RGT templates**, not final coverage
candidates.

A template fixes:

- `repeat_days`
- `revolutions`
- `inclination_deg`
- corrected `semi_major_axis_m`
- corrected initial `mean_anomaly_deg`
- `eccentricity`
- `argument_of_perigee_deg`
- `repeat_period_sec`

The template `raan_deg` is currently `0.0` only as a canonical reference
orientation for closure scoring. It is not a coverage decision.

A coverage candidate in later phases should be the flattened tuple:

- all template fields above
- one concrete `raan_deg`

RAAN is part of the candidate because it rotates the repeating ground track
against Earth longitudes at the mission epoch and therefore changes which
targets are useful to cover.

Satellite placement then expands a selected candidate into Cartesian initial
states. For `k` satellites on one candidate, choose one deterministic phase
offset `phase0_deg`, then place satellites at:

```text
satellite_mean_anomaly_deg[j] = phase0_deg + template.mean_anomaly_deg + 360 * j / k
```

for `j = 0..k-1`, all sharing the candidate's RAAN and template shell
parameters. Each satellite state is produced by evaluating the
Brouwer-Lyddane/J2 state conversion at the benchmark horizon start. Coverage
and scheduling phases should work with these concrete Cartesian states, not
with the un-RAANed template alone.

## Phase 1 Method

For each configured integer repeat template `(revolutions, repeat_days)` and
inclination, the solver uses secular J2 repeat-ground-track equations to solve
for semi-major axis. It then uses a solver-local Brouwer-Lyddane-style J2
analytical propagator to search nearby altitude/phase corrections cheaply. The
constructor records analytical closure after `repeat_days` sidereal days and
does not run numerical propagation in the solver path.

Tests compare the analytical constructor against Brahe numerical J2 propagation
over a larger seed set. Once those tests pass, the solver trusts the analytical
constructor directly.

This is not a Keplerian integer-ratio seed. Brouwer-Lyddane J2 closure evidence
is required before a template is accepted.

## Phase 2 Method

Each accepted template is expanded over a deterministic RAAN grid. One flattened
candidate is:

```text
candidate = template fields + concrete raan_deg
```

The solver samples each candidate over one repeat cycle and checks the benchmark
visibility geometry solver-locally:

- target elevation above `min_elevation_deg`
- slant range within both target and sensor maximum range
- off-nadir angle within the sensor cone
- grouped visibility windows must satisfy target `min_duration_sec`

The coverage debug summary records access windows, candidate-to-target indexes,
target-to-candidate indexes, and uncovered targets. It does not select
candidates or emit scheduled observations yet.

## Phase 3 Method

Selection treats each RAAN-phased candidate as a set-cover item with a satellite
cost. For a target assigned to a candidate:

```text
required_satellites = ceil(candidate_repeat_period_hours / target_revisit_hours)
```

When one candidate owns multiple assigned targets, its cost is the strictest
assigned target cost. Greedy selection maximizes newly covered targets per
satellite cost while respecting `max_num_satellites`. Deterministic ties prefer
difficult target coverage, lower closure error, shorter repeat period, stronger
coverage margin, then candidate ID.

The selection summary assigns covered targets to selected candidates and reports
budget blockers, but it still emits no final satellites or observation actions.

## Validation

```bash
./test.sh
```
