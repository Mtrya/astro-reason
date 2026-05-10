# Skill Injection Skill Writing Roadmap

## Goal

Create five repository-owned skills for the `skill_injection` ablation without
collapsing them into one oversized task note. Each skill must be source-grounded
and must ship more than `SKILL.md`: at minimum it needs either `references/`,
`examples/`, or `scripts/` artifacts that make the guidance auditable and useful
inside a solving workspace.

## Source Of Truth

- Issue #59: skill injection with task-specific guidance.
- Experiment scaffold: `experiments/skill_injection/`.
- Bundle manifests:
  - `experiments/_fragments/skills/skill_injection/compact_domain.yaml`
  - `experiments/_fragments/skills/skill_injection/skill_pack.yaml`
- Benchmark contract:
  - `benchmarks/stereo_imaging/README.md`
  - `experiments/_fragments/prompts/stereo_imaging/README.default.md`
- Solver evidence:
  - `solvers/stereo_imaging/cp_local_search_stereo_insertion/README.md`
  - `solvers/stereo_imaging/time_window_pruned_stereo_milp/README.md`
- External source anchors:
  - Python standard-library docs for `multiprocessing`, `concurrent.futures`, and `cProfile`.
  - OR-Tools official CP-SAT documentation and Python API reference.
  - Lemaître et al. 2002, Kim et al. 2020, and Vasquez/Hao 2001 via DOI links in solver READMEs.

## Current State

The experiment family can plan the matrix but does not execute non-control
conditions yet. The referenced skill directories are intentionally missing.
This keeps placeholder content out of agent workspaces until the skill-writing
phases below are complete.

Expected final skill directories:

```text
experiments/_fragments/skills/skill_injection/
├── stereo-imaging-compact-procedure/
├── python-optimization-for-search/
├── ortools-cpsat-modeling/
├── classical-or-scheduling-methods/
└── stereo-imaging-product-strategy/
```

## Contract And Boundaries

- Skills are experiment-owned artifacts under `experiments/_fragments/skills/`.
- Skills may cite benchmark README content and solver README ideas, but must not
  expose solver source code, solver commands, private benchmark internals, or
  held-out case-specific answers to space agents.
- Skills may include small examples and scripts, but examples must be synthetic
  or schema-level unless explicitly drawn from public benchmark documentation.
- Skills should help agents write their own `solution.json`, not tell them to
  run first-party solvers.
- Each skill must include:
  - `SKILL.md`
  - `references/README.md` summarizing source grounding and links
  - at least one `examples/` or `scripts/` artifact
  - a short validation note describing how the skill was checked

## Phase Order

1. `SKILL_1_COMPACT_STEREO_PROCEDURE.md`
   - Writes the single compact lossy domain skill used by `compact_domain`.
2. `SKILL_2_PYTHON_OPTIMIZATION_FOR_SEARCH.md`
   - Writes general Python search-performance guidance for `skill_pack`.
3. `SKILL_3_ORTOOLS_CPSAT_MODELING.md`
   - Writes OR-Tools CP-SAT modeling guidance for `skill_pack`.
4. `SKILL_4_CLASSICAL_OR_SCHEDULING_METHODS.md`
   - Writes method-level scheduling/search guidance for `skill_pack`.
5. `SKILL_5_STEREO_IMAGING_PRODUCT_STRATEGY.md`
   - Writes detailed stereo-imaging product strategy for `skill_pack`.

The compact domain skill should be written first because it defines the minimal
guidance baseline. The four skill-pack skills can then stay focused and avoid
duplicating that compact content.

## Cross-Phase Risks

- Overlap risk: the compact and stereo-specific skills can duplicate each other.
  Keep the compact skill recipe-like and the stereo strategy skill diagnostic
  and geometry-heavy.
- Overwhelm risk: weak harnesses may perform worse if the skill pack is too
  long. Each skill should be skimmable and action-oriented.
- Leakage risk: do not include solver implementation files or command recipes
  that effectively ask the agent to run a repository solver.
- Source drift risk: external APIs such as OR-Tools may change. Pin roadmap
  source links and mention the docs version/date used in `references/README.md`.

## Overall Exit Criteria

- All five skill directories exist and are referenced by bundle manifests.
- Each directory contains `SKILL.md`, `references/README.md`, and at least one
  useful `examples/` or `scripts/` artifact.
- `uv run python experiments/skill_injection/run.py --dry-run` reports no
  missing skill directories for `compact_domain` or `skill_pack`.
- Focused tests verify bundle expansion and source availability.
- A human reviewer can trace every major claim in the skills to either the
  benchmark README, solver README, official docs, or a cited paper/source.

