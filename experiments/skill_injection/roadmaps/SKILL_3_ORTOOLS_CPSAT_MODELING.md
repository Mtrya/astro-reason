# Skill 3: OR-Tools CP-SAT Modeling

## Goal

Write `ortools-cpsat-modeling`, a generic skill-pack skill that teaches agents how to model binary selection, conflicts, coverage, lexicographic objectives, time limits, and fallback behavior with OR-Tools CP-SAT. The skill must be grounded in current official docs and executable code, not memory.

## Inputs To Read

- Official OR-Tools docs:
  - `https://developers.google.com/optimization/cp/cp_solver`
  - `https://developers.google.com/optimization/cp/cp_tasks`
  - `https://developers.google.com/optimization/install/python`
  - `https://or-tools.github.io/docs/pdoc/ortools/sat/python/cp_model.html`
- Local source anchors:
  - `solvers/stereo_imaging/time_window_pruned_stereo_milp/README.md`
  - `solvers/stereo_imaging/time_window_pruned_stereo_milp/config.example.yaml` if present when this phase starts.

## Required Temporary Environment

- Create an isolated throwaway environment outside the repository or under `/tmp`, for example `/tmp/astroreason-ortools-cpsat-skill-env`.
- Install OR-Tools into that temporary environment only; do not install packages system-wide and do not modify the repository environment.
- Use the environment's Python to run every example snippet that the skill claims is runnable.
- Record the Python version, OR-Tools package version, install command, and execution result in `references/README.md`.
- If OR-Tools installation is impossible in the current sandbox, stop and record the blocker instead of writing unverified API snippets.

## In Scope

- Create:
  - `experiments/_fragments/skills/skill_injection/ortools-cpsat-modeling/SKILL.md`
  - `.../references/README.md`
  - `.../examples/binary_coverage_cp_sat.py`
  - optionally `.../examples/sequential_lexicographic_solve.py`
- Cover:
  - Boolean variables for candidate/product selection
  - pairwise conflict constraints
  - coverage variables linked to selected products
  - sequential lexicographic optimization when weights are risky
  - solver time limits and incumbent handling
  - checking `CpSolverStatus` values and objective bounds with current APIs
  - when to fall back to greedy construction

## Out Of Scope

- Benchmark-specific stereo formulas.
- Reproducing the repository MILP solver.
- Large benchmark-specific models.
- Any claim that CP-SAT is always better than greedy/local search.

## Implementation Notes

- The example should be a tiny synthetic product-selection model, not a stereo-imaging case.
- Keep the skill generic to OR-Tools CP-SAT and CP-style product selection; do not connect it to stereo imaging except in `references/README.md` as a local evidence anchor for why product/conflict decompositions matter.
- Include a warning: do not start with CP-SAT until candidate/product data and conflict edges are clean.
- Show how to inspect solver status and still emit a best feasible incumbent when available.
- The skill should mention exact mode as an option, but also explain that model construction can dominate runtime.

## Validation

- Run every example with the temporary OR-Tools environment and commit only examples that execute successfully there.
- Add a small expected-output assertion or printed solution check to each runnable example.
- Check all API claims against the official docs listed above and the installed package behavior.
- Run focused tests for bundle expansion.

## Exit Criteria

- A future agent can write a small product-selection CP-SAT model from the skill without reading the full OR-Tools docs.
- `references/README.md` maps every API pattern to official OR-Tools docs and records the temporary environment validation.
- The skill discourages premature modeling when a greedy seed is more robust.

## Suggested Prompt

Read `experiments/skill_injection/roadmaps/SKILL_WRITING_ROADMAP.md` and this phase doc. Verify the current OR-Tools Python API from official docs, create a throwaway `/tmp` environment with OR-Tools installed, and run every example snippet there before committing it. Create only the `ortools-cpsat-modeling` skill directory with source references and tiny synthetic CP-SAT examples. Keep the skill generic to OR-Tools CP-SAT and do not copy solver code or add stereo-imaging-specific product formulas. Record the environment/version/API validation in `references/README.md`, run the examples, and run focused tests.
