# Prompt

Read `README.md` and `AGENTS.md` before making changes.

Your job is to produce a valid `solution.json` for the current case.

Suggested approach:

1. Inspect `case/` to understand the problem data and constraints.
2. Inspect `{example_solution_name}` if it exists so your output matches the expected schema.
3. Write a solver such as `solve.py`.
4. Run your solver to generate `solution.json`.
5. Validate with `{verifier_command}`.
6. If validation fails, fix the solver and repeat until it passes.

Leave the final answer in `solution.json` at the workspace root.
