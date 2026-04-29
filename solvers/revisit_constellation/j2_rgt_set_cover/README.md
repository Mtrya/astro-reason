# J2 RGT Set-Cover Solver

This solver implements a J2-aware repeat-ground-track set-cover method for `revisit_constellation`. It builds repeat-ground-track orbit templates, expands them into RAAN-specific candidates, selects candidates as a satellite-cost set-cover problem, populates selected candidates with evenly spaced satellites, and emits benchmark-shaped observation schedules.

The solver is standalone. It reads benchmark case files directly and does not import benchmark, experiment, runtime, or other solver internals.

## Contract

```bash
./setup.sh
./solve.sh <case_dir> [config_dir] [solution_dir]
```

The solver writes:

- `solution.json`: satellites plus locally validated observation actions
- `status.json`: closure-search, candidate-coverage, selection, timing, and compute summaries
- `debug/closure_search.json`: accepted and rejected J2 RGT template records
- `debug/coverage_summary.json`: RAAN-specific candidates, access evidence, and deterministic target/candidate indexes
- `debug/selection_summary.json`: selected candidates, assigned targets, total satellite cost, and budget blockers
- `debug/solution_summary.json`: satellites, selected actions, target gaps, and local validation details

Experiment-owned profiles are defined in `experiments/main_solver/solvers/revisit_constellation_j2_rgt_set_cover.yaml`. The solver records `active_profile`, `compute_envelope`, and worker counts in `status.json.compute_profile`; benchmark verification is owned by `experiments/main_solver`.

## Orbit Templates And Candidates

The solver first constructs closed RGT templates. A template fixes:

- `repeat_days`
- `revolutions`
- `inclination_deg`
- corrected `semi_major_axis_m`
- corrected initial `mean_anomaly_deg`
- `eccentricity`
- `argument_of_perigee_deg`
- `repeat_period_sec`

The template `raan_deg` is `0.0` only as a canonical reference orientation for closure scoring. It is not a coverage decision.

A coverage candidate is the flattened tuple:

- all template fields above
- one concrete `raan_deg`

RAAN is part of the candidate because it rotates the repeating ground track against Earth longitudes at the mission epoch and therefore changes which targets are useful to cover.

## J2 RGT Construction

For each configured integer repeat template `(revolutions, repeat_days)` and inclination, the solver uses secular J2 repeat-ground-track equations to solve for semi-major axis. It then uses a solver-local Brouwer-Lyddane-style J2 analytical propagator to search nearby altitude and mean-anomaly corrections cheaply.

The constructor records analytical closure after `repeat_days` sidereal days. Tests compare the analytical constructor against Brahe numerical J2 propagation over a larger seed set; once those tests pass, the solver trusts the analytical constructor directly in the search path.

This is not a Keplerian integer-ratio seed. Brouwer-Lyddane J2 closure evidence is required before a template is accepted.

## Coverage And Selection

Each accepted template is expanded over a deterministic RAAN grid. The solver
samples each candidate over one repeat cycle and checks benchmark-compatible
visibility geometry solver-locally:

- target elevation above `min_elevation_deg`
- slant range within both target and sensor maximum range
- off-nadir angle within the sensor cone
- grouped visibility evidence must support target `min_duration_sec`

Selection treats each RAAN-specific candidate as a set-cover item with a satellite cost. For a target assigned to a candidate:

```text
required_satellites = ceil(candidate_repeat_period_hours / target_revisit_hours)
```

When one candidate owns multiple assigned targets, its cost is the strictest assigned target cost. Greedy selection maximizes newly covered targets per satellite cost while respecting `max_num_satellites`. Deterministic ties prefer difficult target coverage, lower closure error, shorter repeat period, stronger coverage margin, then candidate ID.

## Realization And Scheduling

Each selected RAAN-specific candidate is expanded into concrete satellites by equal ground-track phase spacing. Analytical J2 remains the architecture-search model, but final realization uses the same Brahe numerical J2 force model as the benchmark verifier for opportunity refinement, slew vectors, and local sampled visibility checks.

Repair first ranks the broad candidate pool analytically, then validates a bounded deterministic repair frontier numerically before repacking candidate sets. This keeps the repacker aligned with benchmark propagation without requiring full numerical propagation for every RAAN candidate.

The final scheduler is assigned-first. For each target assigned to a selected candidate, it fills that target's opportunity timeline until the target revisit threshold is satisfied, using deterministic gap-profile ties. Only after assigned targets are realized does it use remaining compatible opportunities for uncovered targets. Same-satellite overlap and slew/settle gaps are checked before insertion.

The solver-local validator checks benchmark-shaped references, timing, orbit bounds, sampled visibility, same-satellite overlap, conservative slew gaps, and a conservative no-charge battery risk.

## Validation

```bash
./test.sh
```
