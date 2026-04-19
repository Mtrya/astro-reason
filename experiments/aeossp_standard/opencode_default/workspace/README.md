# Problem Workspace

You are solving one structured planning or optimization case.

Case label: `{case_id}`
Problem family: `{benchmark}`

## Available Files

- `case/` contains the machine-readable input files for this case.
- `{example_solution_name}` is an example of the required output schema when present.
- `{verifier_location}` validates a candidate `solution.json` against the current case.
- `AGENTS.md` describes the working rules for this workspace.
- `TASK.md` gives the immediate objective.

## Recommended Loop

1. Read the files in `case/` closely.
2. Inspect `{example_solution_name}` if it exists.
3. Write helper code such as `solve.py`.
4. Run your solver to produce `solution.json`.
5. Validate with `{verifier_command}`.
6. Iterate until the verifier passes.

Keep all work inside this workspace.
