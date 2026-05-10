# Skill 4: Classical OR Scheduling Methods

## Goal

Write `classical-or-scheduling-methods`, a skill-pack skill that teaches the
method ideas behind candidate generation, conflict graphs, greedy seeding,
insertion/local search, repair, and lexicographic scheduling objectives.

## Inputs To Read

- Local solver READMEs:
  - `solvers/stereo_imaging/cp_local_search_stereo_insertion/README.md`
  - `solvers/stereo_imaging/time_window_pruned_stereo_milp/README.md`
- Paper sources cited by those READMEs:
  - Lemaître et al. 2002, DOI `10.1016/S1270-9638(02)01173-2`
  - Kim et al. 2020, DOI `10.2514/1.I010775`
  - Vasquez and Hao 2001, DOI `10.1023/A:1012300271919`

## In Scope

- Create:
  - `experiments/_fragments/skills/skill_injection/classical-or-scheduling-methods/SKILL.md`
  - `.../references/README.md`
  - `.../examples/conflict_graph_and_insertion.md`
  - optionally `.../examples/greedy_seed_pseudocode.py`
- Cover:
  - candidate/action layer versus product/job layer
  - conflict graph construction
  - coverage-first greedy seed
  - atomic insertion and rollback
  - remove/replace/swap neighborhoods
  - conservative repair and why repair should remove low-value conflicts
  - deterministic tie-breaking

## Out Of Scope

- OR-Tools syntax.
- Python multiprocessing implementation details.
- Stereo geometry specifics beyond generic product feasibility.
- Claims of paper-faithful reproduction.

## Implementation Notes

- This skill should be reusable beyond stereo imaging.
- Make it clear that classical OR methods are design patterns, not permission to
  call repository solvers.
- Examples should use neutral terms such as jobs, resources, conflicts, and
  products.
- The references file should summarize what each cited paper contributes at a
  high level and what the benchmark adaptation intentionally changes.

## Validation

- Cross-check method names and adaptation caveats against the two solver READMEs.
- Confirm no solver command lines or source paths encourage direct solver use.
- If a pseudocode example is included, run it or keep it explicitly non-runnable.
- Run focused skill-injection tests.

## Exit Criteria

- The skill gives a concrete method playbook for scheduling/search tasks.
- The skill is not tied to one benchmark but remains grounded in the cited
  stereo solver adaptations.
- `references/README.md` includes local and DOI source mapping.

## Suggested Prompt

Read `experiments/skill_injection/roadmaps/SKILL_WRITING_ROADMAP.md`, this phase
doc, and both stereo solver READMEs. Use the cited papers only for method
grounding and adaptation notes. Create only the `classical-or-scheduling-methods`
skill directory with references and a neutral example. Avoid OR-Tools syntax and
stereo-specific geometry formulas. Run focused tests before committing.

