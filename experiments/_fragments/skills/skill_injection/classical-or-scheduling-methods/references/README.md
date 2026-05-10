# Classical OR Scheduling Methods References

Method reminders for product-style scheduling and local search.

## Useful Literature

- Lemaître, Verfaillie, Jouhaud, Lachiver, and Bataille, "Selecting and scheduling observations of agile satellites", Aerospace Science and Technology, 2002. DOI: https://doi.org/10.1016/S1270-9638(02)01173-2
- Kim, Ahn, Choi, and Cho, "Task Scheduling of Multiple Agile Satellites with Transition Time and Stereo Imaging Constraints", Journal of Aerospace Information Systems, 2020. DOI: https://doi.org/10.2514/1.I010775
- Vasquez and Hao, "A Logic-Constrained Knapsack Formulation and a Tabu Algorithm for the Daily Photograph Scheduling of an Earth Observation Satellite", Computational Optimization and Applications, 2001. DOI: https://doi.org/10.1023/A:1011203002719

The task's scoring and validity contract remains the authority.

## Pattern Glossary

- **Candidate/action:** one concrete schedulable action with a resource and time.
- **Product/job:** the thing that earns score, often made from one or more actions.
- **Conflict graph:** a set of "cannot select both" edges between actions or products.
- **Coverage variable:** a Boolean or score entry saying whether a job has at least one valid selected product.
- **Atomic move:** a move that inserts, removes, or replaces a whole product and rolls back completely on failure.
- **Repair:** a conservative pass that removes low-value conflicting products until hard constraints pass.

## Search Patterns

- Generate candidates with cheap feasibility filters before expensive scoring.
- Build products from compatible candidates and rank by new coverage first.
- Seed a broad feasible schedule before polishing quality.
- Use insert, replace, remove-then-insert, and swap neighborhoods.
- When adding a product creates conflicts, compare the added value with the value lost by removing conflicting products.
- Recompute the task score after accepted moves to avoid stale incremental accounting.

## Repair Patterns

- Repair hard validity before optimizing score.
- Prefer removing the lowest-value product in a conflict set.
- If a conflict has several repair choices, choose the one with the smallest lexicographic loss.
- Avoid leaving orphan actions that cannot contribute to any selected product.
- If repair removes too much, go back to the last valid schedule and add products more cautiously.

## Deterministic Tie-Breaking

Use stable ordering after score fields:

1. More newly covered jobs.
2. Higher objective contribution.
3. Fewer conflicts or lower resource cost.
4. Earlier or more central time if useful for the task.
5. Stable product ID.

This keeps debugging reproducible and makes verifier feedback easier to connect to a specific move.
