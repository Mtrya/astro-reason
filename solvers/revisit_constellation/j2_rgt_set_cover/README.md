# J2 RGT Set-Cover Solver

This solver implements a certified J2-aware repeat-ground-track set-cover method for `revisit_constellation`. It builds repeat-ground-track orbit templates, expands them into RAAN-specific candidates, ranks analytical candidate-target claims, numerically certifies a bounded frontier of those claims with the same J2 refinement model used for final scheduling, selects only certified assignments, and emits benchmark-shaped observation schedules.

The solver is standalone. It reads benchmark case files directly and does not import benchmark, experiment, runtime, or other solver internals.

## Contract

```bash
./setup.sh
./solve.sh <case_dir> [config_dir] [solution_dir]
```

The solver writes:

- `solution.json`: satellites plus locally validated observation actions
- `status.json`: closure-search, analytical coverage, numerical certification, selection, timing, and compute summaries
- `debug/closure_search.json`: accepted and rejected J2 RGT template records
- `debug/coverage_summary.json`: RAAN-specific candidates, analytical access evidence, and ranked analytical claims
- `debug/certification_summary.json`: numerically refined candidate-target certification records and rejection reasons
- `debug/selection_summary.json`: selected certified assignments, total satellite cost, uncovered targets, and budget blockers
- `debug/solution_summary.json`: satellites, emitted selected-assignment actions, target gaps, local validation, and retry history

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

## Coverage, Certification, And Selection

Each accepted template is expanded over a deterministic RAAN grid. The solver samples each candidate over one repeat cycle and checks  enchmark-compatible visibility geometry solver-locally:

- target elevation above `min_elevation_deg`
- slant range within both target and sensor maximum range
- off-nadir angle within the sensor cone
- grouped visibility evidence must support target `min_duration_sec`

This analytical pass is not final coverage truth. It only produces ranked `candidate,target` claims. Per target, claims are ranked by required satellite count, analytical capped/max gap, geometry margin, repeat period, closure error, and candidate ID.

Numerical certification then refines a bounded frontier:

```yaml
certification:
  max_claims_per_target: 8
  min_passing_claims_per_target: 2
  worker_count: 8
  max_selection_retries: 8
```

Geometry and sampling defaults are inherited from `scheduling` unless overridden in `certification`. The per-target frontier interleaves the best cheap analytical claims with coarse set-cover-efficient claims, so numerical certification checks both low-satellite records and globally useful multi-target candidates. A target can be selected only through a certified candidate-target record whose refined opportunities satisfy the target revisit period.

Selection treats deterministic candidate variants as set-cover items. A variant is one RAAN-specific candidate with a concrete satellite count, and it can cover every certified target record for that candidate whose required satellite count is no larger than the variant count. For a target certified on a candidate:

```text
required_satellites = ceil(candidate_repeat_period_hours / target_revisit_hours)
```

The deterministic objective is to cover as many certified targets as possible, then minimize satellites, mean certified capped gap, worst certified gap, selected candidate count, and lexicographic variant IDs. If full certified coverage is impossible within the satellite budget, the solver emits the best valid partial solution and reports uncovered targets.

## Realization And Scheduling

Each selected RAAN-specific candidate is expanded into concrete satellites by equal ground-track phase spacing. Analytical J2 remains the architecture-search model, but final realization uses the same Brahe numerical J2 force model as the benchmark verifier for opportunity refinement, slew vectors, and local sampled visibility checks.

The final scheduler is assigned-only. For each target assigned to a selected certified candidate record, it fills that target's opportunity timeline until the target revisit threshold is satisfied, using deterministic gap-profile ties. It does not schedule opportunistic observations for merely visible or uncovered targets. Same-satellite overlap and slew/settle gaps are checked before insertion.

If final emission cannot satisfy a selected certificate because of cross-target action conflicts, the solver blacklists the failed certificate or candidate variant, reruns certified selection, and retries up to `certification.max_selection_retries`. If retries exhaust, the best locally valid partial solution is emitted and unresolved targets are reported in debug/status artifacts.

The solver-local validator checks benchmark-shaped references, timing, orbit bounds, sampled visibility, same-satellite overlap, conservative slew gaps, and a conservative no-charge battery risk.

## Validation

```bash
./test.sh
```
