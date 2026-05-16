# Satellite Photography Selection Run Notes

- Case: `case/54.spot`
- Final verified `solution.json`:
  - `VALID: profit=70, weight=0`
  - `n_candidates: 67`
  - `n_selected: 45`
- Effective workflow:
  - Parsed the `.spot` file directly from the workspace contract in `README.md`.
  - Modeled each photograph as one integer variable over `{0} U domain_i`, where `0` means reject.
  - Added each binary or ternary forbidden tuple line directly as a CP-SAT forbidden-assignment constraint, preserving multiple tuples per line.
  - Maximized `sum(profit_i)` over selected photographs only; case `54` is not one of the weighted multi-orbit instances, so computed weight remained `0`.
  - OR-Tools CP-SAT returned `OPTIMAL` immediately for this instance.

- Case: `case/507.spot`
- Final verified `solution.json`:
  - `VALID: profit=15137, weight=0`
  - `n_candidates: 311`
  - `n_selected: 89`
- Effective workflow:
  - Parsed the `.spot` file directly from the workspace contract in `README.md`.
  - Modeled each photograph as one integer variable over `{0} U domain_i`, where `0` means reject.
  - Added the listed binary and ternary forbidden tuples directly as CP-SAT forbidden assignments.
  - Maximized `sum(profit_i)` over selected photographs only; for this instance, no recorder-capacity constraint applied because case `507` is not one of the multi-orbit weighted cases.
  - OR-Tools CP-SAT proved optimality essentially immediately, so no heuristic improvement phase was needed.
