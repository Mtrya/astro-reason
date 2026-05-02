# J2 RGT Set-Cover Solver

This solver implements a certified J2-aware repeat-ground-track set-cover method for `revisit_constellation`. It builds repeat-ground-track orbit templates, expands them into RAAN-specific candidates, ranks candidates on a global leaderboard, numerically checks candidate-target pairs for the leading candidates with the same J2 refinement model used for final scheduling, selects only confirmed assignments, and emits benchmark-shaped observation schedules.

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
- `debug/coverage_summary.json`: RAAN-specific candidates, analytical access evidence, and analytical candidate-target claims
- `debug/certification_summary.json`: candidate leaderboard, numerically checked candidate-target records, and rejection reasons
- `debug/selection_summary.json`: selected confirmed assignments, total satellite cost, uncovered targets, and budget blockers
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

Each accepted template is expanded over a deterministic RAAN grid. The solver samples each candidate over one repeat cycle and checks benchmark-compatible visibility geometry solver-locally:

- target elevation above `min_elevation_deg`
- slant range within both target and sensor maximum range
- off-nadir angle within the sensor cone
- grouped visibility evidence must support target `min_duration_sec`

This analytical pass is not final coverage truth. It produces candidate-target claims: candidate X may cover target Y. Those rows are evidence for a candidate, not the primary Step 2 control structure.

Step 1 builds a global candidate leaderboard. A leaderboard entry is one candidate with a concrete satellite count and the set of targets it claims to cover. The priority balances:

- weighted target count, where targets claimed by fewer candidates are worth more
- absolute target count
- rare target count
- value per satellite
- analytical gap, geometry margin, closure error, and deterministic candidate ID ties

Step 2 consumes the leaderboard in order and numerically checks candidate-target pairs for the leading candidates:

```yaml
strategy:
  one_day_first: true
  deepen_max_candidates_to_check: 96
rgt_search:
  max_repeat_days: 1
certification:
  max_candidates_to_check: 48
  worker_count: 8
  max_selection_retries: 8
```

The default strategy checks one-day repeat-track candidates only. It starts with the top 48 candidates from a denser RAAN grid, and reruns the same one-day grid with 96 candidates only if the first pass leaves high-gap or uncovered targets. That keeps compute focused on one-day candidates instead of spending time on costlier two-day variants.

Geometry and sampling defaults are inherited from `scheduling` unless overridden in `certification`. A target can be selected only through a confirmed candidate-target record whose refined opportunities satisfy the target revisit period.

Selection treats deterministic candidate variants as set-cover items. A variant is one RAAN-specific candidate with a concrete satellite count, and it can cover every target record numerically confirmed at that same satellite count. The selector uses an exact bitset branch-and-bound search over candidate variants: it maximizes confirmed target coverage under the satellite budget, prunes states whose remaining optimistic target gain cannot beat the incumbent, and then applies deterministic tie-breaks. For a target claimed on a candidate, the minimum satellite count starts from:

```text
required_satellites = ceil(candidate_repeat_period_hours / target_revisit_hours)
```

The deterministic objective is to cover as many confirmed targets as possible, then minimize satellites, mean confirmed capped gap, worst confirmed gap, selected candidate count, and lexicographic variant IDs. If full confirmed coverage is impossible within the satellite budget, the solver emits the best valid partial solution and reports uncovered targets.

## Realization And Scheduling

Each selected RAAN-specific candidate is expanded into concrete satellites by equal ground-track phase spacing. Analytical J2 remains the architecture-search model, but final realization uses the same Brahe numerical J2 force model as the benchmark verifier for opportunity refinement, slew vectors, and local sampled visibility checks.

The final scheduler is assigned-only. For each target assigned to a selected confirmed candidate record, it fills that target's opportunity timeline until the target revisit threshold is satisfied, using deterministic gap-profile ties. It does not schedule opportunistic observations for merely visible or uncovered targets. Same-satellite overlap and slew/settle gaps are checked before insertion.

If final emission cannot satisfy a selected certificate because of cross-target action conflicts, the solver blacklists the failed certificate or candidate variant, reruns certified selection, and retries up to `certification.max_selection_retries`. If retries exhaust, the best locally valid partial solution is emitted and unresolved targets are reported in debug/status artifacts.

The solver-local validator checks benchmark-shaped references, timing, orbit bounds, sampled visibility, same-satellite overlap, conservative slew gaps, and a conservative no-charge battery risk.

## Validation

```bash
./test.sh
```
