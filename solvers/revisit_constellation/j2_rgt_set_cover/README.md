# J2 RGT Set-Cover Solver

This solver is being built for `revisit_constellation` issue #133.

Phase 1 implements only the foundation: J2-aware repeat-ground-track orbit-template
construction and analytical closure diagnostics. Coverage, set-cover selection,
equal-phase satellite population, and scheduling are intentionally left for
later phases.

The solver is standalone. It reads benchmark case files directly and does not
import benchmark, experiment, runtime, or other solver internals.

## Contract

```bash
./setup.sh
./solve.sh <case_dir> [config_dir] [solution_dir]
```

Phase 1 writes:

- `solution.json`: an empty benchmark-shaped solution placeholder
- `status.json`: closure-search summary and phase status
- `debug/closure_search.json`: accepted and rejected J2 RGT template records

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

## Validation

```bash
./test.sh
```
