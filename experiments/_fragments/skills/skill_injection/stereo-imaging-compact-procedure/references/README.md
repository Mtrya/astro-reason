# Source Grounding

This compact skill is grounded in the public stereo-imaging contract and the two repository solver writeups. It intentionally avoids solver commands, solver source excerpts, and case-specific answers.

## Local Sources Used

- `benchmarks/stereo_imaging/README.md`: source for the public solution schema, hard action constraints, stereo-pair and tri-stereo definitions, scoring semantics, and the ranking order of validity, coverage, then normalized quality.
- `experiments/_fragments/prompts/stereo_imaging/README.default.md`: source for the workspace-facing phrasing that agents see, including the reminder that submitted actions are raw observations and products are derived by validation.
- `solvers/stereo_imaging/cp_local_search_stereo_insertion/README.md`: source for the candidate generation, product-library, coverage-first seed, atomic product insertion, rollback, local-search, and conservative repair concepts.
- `solvers/stereo_imaging/time_window_pruned_stereo_milp/README.md`: source for the candidate/product/conflict decomposition, coverage variables, and lexicographic covered-target then best-per-target-quality objective.

## Recipe Mapping

- "First make a valid skeleton" comes from the public solution schema and the benchmark ranking rule that invalid schedules lose before any metric matters.
- "Think in products before scheduling" comes from the benchmark's derived stereo-pair/tri-stereo definitions and both solver writeups' use of explicit candidate products before final schedule selection.
- "Insert products atomically" comes from the CP/local-search writeup's product-level insertion, rollback, and repair strategy, combined with the benchmark same-satellite overlap and slew-plus-settle constraints.
- "Coverage first, quality second" comes from the benchmark primary ranking and the MILP writeup's coverage-first, best-per-target-quality objective.
- "Valid but zero score" follows from the benchmark distinction between valid individual observations and valid stereo or tri-stereo products: legal single images alone do not cover a target.

## Validation Note

The skill was checked against the current stereo prompt to avoid repeating the full benchmark contract. It contains no setup, solve, verification, or other solver execution command recipes, and it does not reference private case answers.
