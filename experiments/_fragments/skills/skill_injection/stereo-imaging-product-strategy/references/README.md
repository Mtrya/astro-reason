# Stereo Imaging Product Strategy References

This skill was grounded on 2026-05-10 in the public stereo benchmark contract, both stereo prompt fragments, and the two stereo solver READMEs. It intentionally focuses on product strategy and verifier diagnosis, not performance engineering or solver modeling syntax.

## Local Sources Read

- `benchmarks/stereo_imaging/README.md`
  - Source for the solution schema, hard action constraints, verifier report fields, stereo pair and tri-stereo product definitions, quality model, scene-type convergence preferences, ranking order, and visualizer/verifier context.
- `experiments/_fragments/prompts/stereo_imaging/README.default.md`
  - Source for the workspace-facing statement that the agent submits raw observations while validation derives pair and tri-stereo products.
  - Source for the detailed same-satellite slew, access, overlap, product, and quality wording visible in default runs.
- `experiments/_fragments/prompts/stereo_imaging/README.verifier_exposure_none.md`
  - Source for the no-verifier condition phrasing and validation pseudocode. The skill uses this to stay useful when no local verifier helper exists.
- `solvers/stereo_imaging/cp_local_search_stereo_insertion/README.md`
  - Source for candidate/product-library thinking, product-atomic insertion and rollback, deterministic coverage-first seeding, tri-stereo upgrade passes, local product-level moves, and conservative repair.
- `solvers/stereo_imaging/time_window_pruned_stereo_milp/README.md`
  - Source for candidate-prune-optimize decomposition, same-satellite/cross-satellite product modes, conflict graph framing, coverage-first best-per-target-quality semantics, and product enumeration risk notes.

## Skill Mapping

- "Product mindset" comes from the benchmark distinction between raw submitted observations and derived stereo/tri products.
- "Product modes" comes from the benchmark's same-satellite same-pass, cross-satellite, and tri-stereo definitions, with solver README evidence that these modes should be represented at product level.
- "Quality strategy" comes from the benchmark quality model: scene-specific convergence preference, overlap score, pixel-scale-ratio score, and tri-stereo bonus with near-nadir anchor.
- "Verifier diagnosis loop" comes from the benchmark report structure and prompt pseudocode. The skill maps common outcomes to the fields that should explain them.
- "Repair playbook" comes from the benchmark hard constraints plus the solver README concept of conservative product-level repair.

## Deliberate Boundaries

- No solver source code, solver commands, first-party solver invocation recipes, or case-specific answers.
- No complete geometry propagation implementation.
- No Python performance guidance; that belongs to `python-optimization-for-search`.
- No OR-Tools or CP-SAT modeling guidance; that belongs to `ortools-cpsat-modeling`.
- No claim that local solver approximations exactly match the verifier in every numerical edge case.

## Diagnostic Field Names Checked

The skill references public verifier fields documented in the benchmark README:

- `valid`
- `metrics.coverage_ratio`
- `metrics.normalized_quality`
- `violations`
- `derived_observations`
- `diagnostics.pair_evaluations`
- `diagnostics.per_target_best_score`

The report-summary script accepts missing fields so it can still help with compact or hand-built verifier-like reports.

## Validation Note

The bundled script was run against `examples/synthetic_verifier_report.json`. Focused skill-injection dry-runs and tests were run after the directory was added.
