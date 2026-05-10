# Skill 4: Classical OR Scheduling Methods

## Goal

Write `classical-or-scheduling-methods`, a skill-pack skill that teaches the method ideas behind candidate generation, conflict graphs, greedy seeding, insertion/local search, repair, and lexicographic scheduling objectives. The skill must be grounded in the papers themselves where available, not only in local solver summaries.

## Inputs To Read

- Local solver READMEs:
  - `solvers/stereo_imaging/cp_local_search_stereo_insertion/README.md`
  - `solvers/stereo_imaging/time_window_pruned_stereo_milp/README.md`
- Paper source paths to fetch and read:
  - Lemaître, Verfaillie, Jouhaud, Lachiver, and Bataille, "Selecting and scheduling observations of agile satellites", Aerospace Science and Technology 6(5), 367-381, 2002. DOI resolver: `https://doi.org/10.1016/S1270-9638(02)01173-2`. Publisher landing page: `https://www.sciencedirect.com/science/article/pii/S1270963802011732`.
  - Kim, Ahn, Choi, and Cho, "Task scheduling of agile satellites with transition time and stereoscopic imaging constraints", Journal of Aerospace Information Systems 17(6), 285-293, 2020. DOI resolver: `https://doi.org/10.2514/1.I010775`. Publisher landing page should be reached through AIAA or the DOI resolver; KAIST metadata is also available at `https://pure.kaist.ac.kr/en/publications/task-scheduling-of-agile-satellites-with-transition-time-and-ster` and `https://koasas.kaist.ac.kr/handle/10203/275358`.
  - Vasquez and Hao, "A Logic-Constrained Knapsack Formulation and a Tabu Algorithm for the Daily Photograph Scheduling of an Earth Observation Satellite", Computational Optimization and Applications 20(2), 137-157, 2001. DOI metadata found publicly as `https://doi.org/10.1023/A:1011203002719`; verify this against publisher metadata because the local CP solver README currently lists a different DOI.
- If the full text is paywalled or unavailable, read the DOI/publisher abstract plus any legally accessible author, institutional, or preprint copy; record exactly which source was used and do not invent details beyond what was read.

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
- Make it clear that classical OR methods are design patterns, not permission to call repository solvers.
- Examples should use neutral terms such as jobs, resources, conflicts, and products.
- The references file should summarize what each cited paper contributes at a high level, what source was actually read, and what the benchmark adaptation intentionally changes.
- If a paper source cannot be read beyond abstract/metadata, say that in `references/README.md` and limit claims to the accessible material plus local solver adaptation notes.

## Validation

- Cross-check method names and adaptation caveats against the two solver READMEs and the paper sources that were actually read.
- Confirm no solver command lines or source paths encourage direct solver use.
- If a pseudocode example is included, run it or keep it explicitly non-runnable.
- Run focused skill-injection tests.

## Exit Criteria

- The skill gives a concrete method playbook for scheduling/search tasks.
- The skill is not tied to one benchmark but remains grounded in the cited papers and the local stereo solver adaptations.
- `references/README.md` includes local source mapping, paper source links, access notes, and any citation discrepancy discovered during fetch.

## Suggested Prompt

Read `experiments/skill_injection/roadmaps/SKILL_WRITING_ROADMAP.md`, this phase doc, and both stereo solver READMEs. Fetch and read the cited paper sources through the DOI resolver, publisher landing pages, or legally accessible author/institutional copies before writing the skill; record which sources were actually read, including any paywall or DOI discrepancy. Create only the `classical-or-scheduling-methods` skill directory with references and a neutral example. Avoid OR-Tools syntax and stereo-specific geometry formulas. Run focused tests before committing.
