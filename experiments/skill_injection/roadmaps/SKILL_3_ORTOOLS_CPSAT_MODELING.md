# Skill 3: OR-Tools CP-SAT Modeling

## Goal

Write `ortools-cpsat-modeling`, a skill-pack skill that teaches agents how to
model binary selection, conflicts, coverage, lexicographic objectives, time
limits, and fallback behavior with OR-Tools CP-SAT.

## Inputs To Read

- Official OR-Tools docs:
  - `https://developers.google.com/optimization/cp/cp_solver`
  - `https://developers.google.com/optimization/cp/cp_tasks`
  - `https://or-tools.github.io/docs/pdoc/ortools/sat/python/cp_model.html`
- Local source anchors:
  - `solvers/stereo_imaging/time_window_pruned_stereo_milp/README.md`
  - `solvers/stereo_imaging/time_window_pruned_stereo_milp/config.example.yaml`
    if present when this phase starts.

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
  - when to fall back to greedy construction

## Out Of Scope

- Installing OR-Tools.
- Reproducing the repository MILP solver.
- Large benchmark-specific models.
- Any claim that CP-SAT is always better than greedy/local search.

## Implementation Notes

- The example should be a tiny synthetic product-selection model, not a
  stereo-imaging case.
- Include a warning: do not start with CP-SAT until candidate/product data and
  conflict edges are clean.
- Show how to inspect solver status and still emit a best feasible incumbent
  when available.
- The skill should mention exact mode as an option, but also explain that model
  construction can dominate runtime.

## Validation

- If OR-Tools is installed in the current environment, run the example.
- If OR-Tools is not installed, the example must fail with a clear import message
  and the validation note must record that.
- Check all API claims against the official docs listed above.
- Run focused tests for bundle expansion.

## Exit Criteria

- A future agent can write a small product-selection CP-SAT model from the skill
  without reading the full OR-Tools docs.
- `references/README.md` maps every API pattern to official OR-Tools docs.
- The skill discourages premature modeling when a greedy seed is more robust.

## Suggested Prompt

Read `experiments/skill_injection/roadmaps/SKILL_WRITING_ROADMAP.md` and this
phase doc. Verify the current OR-Tools Python API from official docs before
writing. Create only the `ortools-cpsat-modeling` skill directory with source
references and a tiny synthetic CP-SAT example. Do not copy solver code or add
stereo-imaging-specific product formulas. Run the example if OR-Tools is
available and record validation.

