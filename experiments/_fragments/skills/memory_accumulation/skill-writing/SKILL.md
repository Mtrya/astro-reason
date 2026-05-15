---
name: skill-writing
description: Write compact reusable skills for future space-agent runs. Use when preserving a general procedure, modeling pattern, parser, verifier workflow, or implementation tactic under .agents/skills instead of writing a one-off memory note.
---

# Skill Writing

Use this skill when a finding should help later cases, not just explain the current run.

## Choose The Artifact

- Put run-specific notes in `memory/`: final metrics, failed attempts, case ids, verifier diagnostics, and why the current `solution.json` works.
- Put reusable procedures in `.agents/skills/<skill-name>/SKILL.md`: parsers, solver recipes, geometry stacks, verifier workflows, modeling tricks, and compact algorithms that should transfer to future cases.
- If the guidance depends on a specific finished case id, it probably belongs in `memory/`. If it describes how to solve a family of similar cases, make or update a skill.

## Required Shape

Every accumulated skill must be a directory with a `SKILL.md` file:

```text
.agents/skills/<skill-name>/
└── SKILL.md
```

Use lowercase kebab-case for `<skill-name>`, for example `spot-cpsat` or `revisit-j2-scheduler`.

Start `SKILL.md` with YAML frontmatter:

```markdown
---
name: spot-cpsat
description: Solve SPOT-style satellite photography selection instances with CP-SAT. Use when the workspace contains a .spot case file with assignment domains and forbidden tuples.
---

# SPOT CP-SAT

## Workflow

1. Read the workspace `README.md` and confirm the `.spot` contract.
2. Parse each variable domain as allowed nonzero assignments plus reject value `0`.
3. Model forbidden tuples directly and verify with `./verifier case/ solution.json`.
```

## Writing Rules

- Keep `SKILL.md` short, procedural, and durable.
- Include trigger words in the frontmatter `description`, such as file extensions, benchmark family names, or solver method names.
- Do not paste long transcripts, final solutions, or large case-specific metrics into a skill.
- Prefer commands, schemas, and decision rules that a later run can reuse quickly.
- When updating an existing skill, preserve still-correct guidance and add the new verifier lesson as a concise bullet.
- If a reusable script is small and valuable, place it under `.agents/skills/<skill-name>/scripts/` and mention when to run it from `SKILL.md`.
