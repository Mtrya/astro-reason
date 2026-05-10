# Skill 1: Compact Stereo Procedure

## Goal

Write `stereo-imaging-compact-procedure`, the single compact skill used by the
`compact_domain` condition. It should be short enough for weak harnesses to use
under time pressure while still teaching the candidate-product-schedule-repair
decomposition.

## Inputs To Read

- `benchmarks/stereo_imaging/README.md`
- `experiments/_fragments/prompts/stereo_imaging/README.default.md`
- `solvers/stereo_imaging/cp_local_search_stereo_insertion/README.md`
- `solvers/stereo_imaging/time_window_pruned_stereo_milp/README.md`
- `experiments/_fragments/skills/skill_injection/compact_domain.yaml`

## In Scope

- Create:
  - `experiments/_fragments/skills/skill_injection/stereo-imaging-compact-procedure/SKILL.md`
  - `.../references/README.md`
  - `.../examples/product_first_workflow.md`
- Teach a compact recipe:
  - preserve a valid `solution.json` early
  - generate candidate observations inside access windows
  - pair/triple observations by target before scheduling
  - insert products atomically into per-satellite sequences
  - repair conflicts by removing low-value products
  - improve coverage first, then quality among covered targets

## Out Of Scope

- Full geometry derivations already present in the benchmark README.
- OR-Tools details.
- Python multiprocessing/performance details.
- Solver command usage or solver source excerpts.

## Implementation Notes

- Keep `SKILL.md` under roughly 1000 words.
- Use imperative, procedural sections rather than dense exposition.
- Include a "valid but zero score" diagnosis: observations are likely not
  forming valid stereo/tri-stereo products.
- Include a "do not ride thresholds" warning for access, off-nadir, slew,
  convergence, overlap, and pixel-scale ratio.
- `references/README.md` should map each major recipe point to local sources:
  benchmark README for validity/scoring, CP solver README for atomic product
  insertion/local search, MILP README for candidate-product-conflict structure.

## Validation

- Read `SKILL.md` alongside the current stereo prompt and remove duplicated
  benchmark-contract boilerplate.
- Confirm no solver execution commands appear.
- Run:
  - `uv run python experiments/skill_injection/run.py --dry-run --condition compact_domain --case case_0001`
  - focused bundle tests after updating expected missing-source behavior.

## Exit Criteria

- The compact bundle has exactly one skill directory and it exists.
- The skill teaches a usable workflow without requiring any additional skill.
- The dry-run planner no longer reports the compact skill directory as missing.

## Suggested Prompt

Read `experiments/skill_injection/roadmaps/SKILL_WRITING_ROADMAP.md`, issue #59,
and this phase doc. Inspect the current stereo README, prompt fragment, and both
stereo solver READMEs. Implement only the `stereo-imaging-compact-procedure`
skill directory with `SKILL.md`, `references/README.md`, and
`examples/product_first_workflow.md`. Do not write the other four skills.
Run the skill-injection dry-run and focused tests before committing.

