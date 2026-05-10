# Skill 5: Stereo Imaging Product Strategy

## Goal

Write `stereo-imaging-product-strategy`, the detailed domain skill in the `skill_pack` condition. It should teach stereo-specific product construction, quality improvement, verifier diagnosis, and failure repair without becoming a copy of the benchmark README.

## Inputs To Read

- `benchmarks/stereo_imaging/README.md`
- `experiments/_fragments/prompts/stereo_imaging/README.default.md`
- `experiments/_fragments/prompts/stereo_imaging/README.verifier_exposure_none.md`
- `solvers/stereo_imaging/cp_local_search_stereo_insertion/README.md`
- `solvers/stereo_imaging/time_window_pruned_stereo_milp/README.md`
- Optional visual inspection source:
  - `benchmarks/stereo_imaging/visualizer/` docs or CLI help if needed.

## In Scope

- Create:
  - `experiments/_fragments/skills/skill_injection/stereo-imaging-product-strategy/SKILL.md`
  - `.../references/README.md`
  - `.../examples/verifier_diagnosis_checklist.md`
  - `.../examples/product_ranking_table.md`
  - optionally `.../scripts/summarize_verifier_report.py`
- Cover:
  - valid observation is not enough; valid product coverage is the objective
  - scene-specific convergence preferences
  - overlap and pixel-scale-ratio risk management
  - same-satellite same-pass versus cross-satellite product modes
  - tri-stereo near-nadir anchor logic
  - use of verifier `violations`, `derived_observations`, `pair_evaluations`, and `per_target_best_score`
  - diagnosing invalid, valid-zero, low-coverage, and low-quality outcomes

## Out Of Scope

- Complete implementation of geometry propagation.
- Solver commands, solver source code, or case-specific answers.
- General Python performance or OR-Tools modeling content.
- Any non-public benchmark internals.

## Implementation Notes

- This skill can be longer than the compact skill but should still be sectioned for scanning.
- Prefer checklists and decision tables over formula dumps.
- Include caution around exact thresholds and boundary times.
- The optional script should consume a verifier JSON report and print summary counts; it must not import benchmark internals.
- The skill should explicitly tell agents to keep improving `solution.json` in place after preserving a valid version.

## Validation

- Run the optional report-summary script on a small synthetic verifier-like JSON fixture if included.
- Compare every diagnostic field name against the benchmark README.
- Confirm no content duplicates large prompt sections verbatim.
- Run skill-injection dry-run after the directory exists.

## Exit Criteria

- The skill helps an agent decide what to do after a verifier report, not merely understand the task statement.
- It complements rather than duplicates the compact skill.
- It includes at least one example artifact that a future agent can consult during debugging.

## Suggested Prompt

Read `experiments/skill_injection/roadmaps/SKILL_WRITING_ROADMAP.md`, this phase doc, the stereo benchmark README, both stereo prompt fragments, and both stereo solver READMEs. Create only the `stereo-imaging-product-strategy` skill directory with references and examples. Focus on product strategy and verifier diagnosis, not Python performance or OR-Tools. Run any included script examples and focused tests before committing.
