# Phase 4: MILP Model And Backend Fallback

## Goal

Build the optimization model that chooses observation and product variables, enforces per-satellite feasibility, and returns a deterministic incumbent even when the preferred backend is unavailable or times out.

## Inputs To Read

- `solvers/stereo_imaging/roadmap/time_window_pruned_stereo_milp/ROADMAP.md`
- Phase 3 implementation
- Issue #89
- `solvers/stereo_imaging/literature/kim-2020-stereo-milp.md`
- `experiments/main_solver/README.md`

## In Scope

- Add binary variables for candidate observations.
- Add binary variables for stereo pair and tri-stereo products.
- Link product variables to their required observation variables.
- Limit each target to objective credit from selected valid products, preferably by explicit covered-target and best-quality proxy variables.
- Enforce same-satellite temporal feasibility:
  - non-overlap
  - sequence/order constraints or pairwise conflict cuts
  - slew/settle separation for conflicting selected observations
- Use a lexicographic objective:
  - maximize number of covered targets
  - maximize normalized product quality
  - minimize action count or use stable deterministic tie-breakers
- Provide a documented deterministic fallback such as greedy product selection plus conflict repair.
- Write `status.json` with backend, model size, objective components, runtime, and optimality/time-limit status.

## Out Of Scope

- Official experiment registration.
- Large-case tuning.
- Full exact proof of optimality on dense cases.

## Implementation Notes

- Prefer an available repo-compatible backend. If OR-Tools, SciPy MILP, PuLP, CBC, HiGHS, or another backend is absent, the solver must still emit a valid fallback solution.
- Big-M timing constraints are acceptable only if numerically bounded by mission horizon seconds.
- Pairwise conflict cuts are simpler and may better match the finite candidate library than continuous start variables.
- Product variables should make the paper's stereo coupling visible in the code and debug artifacts.

## Validation

- Add focused tests for product-observation linking and conflict exclusion.
- Run direct smoke with a tiny candidate cap so model construction is quick.
- Force fallback mode through config and verify deterministic output.
- Check that `status.json` reports objective components and backend state.

## Exit Criteria

- Solver selects observations through explicit product-linked optimization variables.
- Incompatible observations cannot both be selected by the model or fallback.
- Backend absence or timeout does not crash the solver.
- Direct smoke emits `solution.json`, `status.json`, and optional debug artifacts.

## Suggested Prompt

Read the stereo MILP roadmap, Phase 3 code, Kim formulation, and this phase doc. Implement the product-linked MILP or CP-SAT model plus deterministic fallback. Preserve coverage-first objective semantics, write model/status diagnostics, and run direct smoke with both optimized and forced-fallback modes.
