# Classical OR Scheduling Methods References

This skill is grounded in local solver adaptation notes and external scheduling literature checked on 2026-05-10. It intentionally turns the sources into neutral method patterns rather than benchmark- or solver-specific instructions.

## Local Sources Read

- `solvers/stereo_imaging/cp_local_search_stereo_insertion/README.md`
  - Used for the repository's benchmark-adapted CP/local-search pipeline: candidate generation, product library construction, deterministic coverage-first greedy seed, product-atomic insertion/rollback, local insert/replace/remove/swap moves, seeded deterministic perturbations, and conservative repair.
  - Also used for adaptation caveats: the benchmark uses point products, tri-stereo products, coverage-first lexicographic ranking, deterministic evaluation, and omits paper constraints such as memory, energy, weather, and downlink.
- `solvers/stereo_imaging/time_window_pruned_stereo_milp/README.md`
  - Used for candidate-prune-optimize structure, conflict graph framing, coverage variables, pruning caution, lexicographic coverage/quality semantics, and conservative repair after optimization.
  - Used only as method evidence, not as a source of solver commands or solver implementation details.

## Paper Sources Actually Read

- Lemaître, Verfaillie, Jouhaud, Lachiver, and Bataille, "Selecting and scheduling observations of agile satellites", Aerospace Science and Technology 6(5), 367-381, 2002.
  - DOI resolver / publisher: https://doi.org/10.1016/S1270-9638(02)01173-2 and https://www.sciencedirect.com/science/article/pii/S1270963802011732
  - Access read: ScienceDirect publisher landing page and abstract only. The full text was behind institutional/purchase access in this environment.
  - Claims used: the agile observation selection/scheduling problem is highly combinatorial; the paper presents greedy, dynamic programming, constraint programming, and local-search methods for a simplified version. Deeper local-search mechanics in the skill are grounded in the repository solver README adaptation rather than unread full text.
- Kim, Ahn, Choi, and Cho, "Task Scheduling of Multiple Agile Satellites with Transition Time and Stereo Imaging Constraints", arXiv preprint / later Journal of Aerospace Information Systems article, 2020.
  - DOI resolver / publisher metadata: https://doi.org/10.2514/1.I010775, KAIST Pure metadata at https://pure.kaist.ac.kr/en/publications/task-scheduling-of-agile-satellites-with-transition-time-and-ster/, and KOASAS metadata at https://koasas.kaist.ac.kr/handle/10203/275358
  - Full text read: legally accessible arXiv version https://arxiv.org/abs/1912.00374 and PDF https://arxiv.org/pdf/1912.00374
  - Claims used: candidate/time-window formulation, explicit transition-time and overlap constraints, MILP formulation, priority-based time-window pruning, and the conclusion that pruning can accelerate computation while remaining near optimal on their scenarios.
  - Access note: KAIST metadata lists no associated files; arXiv supplies the accessible full text. The journal title in local README says "Multiple Agile Satellites..." while KAIST metadata presents "Task scheduling of agile satellites..."; DOI and page metadata match.
- Vasquez and Hao, "A Logic-Constrained Knapsack Formulation and a Tabu Algorithm for the Daily Photograph Scheduling of an Earth Observation Satellite", Computational Optimization and Applications 20(2), 137-157, 2001.
  - DOI / publisher metadata checked: Ovid publisher-style abstract page https://www.ovid.com/journals/coap/abstract/00023364-200120020-00002~a-logic-constrained-knapsack-formulation-and-a-tabu
  - Full text read: author-hosted PDF from Jin-Kao Hao's university page https://leria-info.univ-angers.fr/~jinkao.hao/papers/JCOAP.pdf
  - Claims used: model as a generalized knapsack with binary and ternary logic constraints; tabu/local search over a partially constrained space; add-and-repair neighborhood; incremental move evaluation; dynamic tabu tenure; and repair choices that remove lower-profit conflicts or use limited lookahead.
  - DOI discrepancy: public search results and later citations consistently report `10.1023/A:1011203002719`; the local CP solver README currently lists `10.1023/A:1012300271919`. The skill records the discrepancy and does not rely on the README DOI.

## Method Mapping

- **Candidate/action layer versus product/job layer:** from Kim's formulation structure and both local solver READMEs. The skill generalizes this to actions and products.
- **Conflict graph:** from the time-window-pruned solver README and Vasquez/Hao's binary/ternary logic constraint framing. The skill uses a graph abstraction because it is easier for a space agent to implement and audit than a full mathematical model.
- **Greedy seed:** from the local CP/local-search README's deterministic coverage-first seed. This is a repository adaptation, not a paper-faithful claim.
- **Insertion and rollback:** from the local CP/local-search README and Vasquez/Hao add-and-repair neighborhoods. The skill phrases it as an implementation discipline.
- **Remove/replace/swap neighborhoods and repair:** from local README adaptation notes and Vasquez/Hao repair discussion. The skill keeps repair conservative and deterministic.
- **Lexicographic objective:** from the local solver READMEs' benchmark adaptation notes. The papers use profit-style objectives; the skill says to follow the task's actual score ordering.

## Deliberate Omissions

- No OR-Tools or solver-specific syntax; that belongs to a separate skill.
- No stereo geometry formulas; that belongs to stereo-specific skills.
- No solver command lines, internal source code, or instructions to call repository solvers.
- No claim that the skill reproduces any paper exactly. It extracts reusable scheduling patterns for writing an independent solution.

## Validation Note

The skill was cross-checked against the two stereo solver READMEs and the accessible paper sources above. The example is intentionally non-runnable pseudocode in neutral scheduling terms, so there is no executable example test for this skill.
