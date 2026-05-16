# Workspace Rules

- Work only with the files in this prepared workspace.
- Start by reading `README.md`, listing `case/`, and checking whether `memory/` or `.agents/skills/` already contain useful prior guidance.
- Treat `solution.json` as the required final deliverable unless the workspace says otherwise.
- If the workspace exposes `./verifier`, use it early for schema feedback and use it again before you finish.
- Keep the best verified or likely-valid `solution.json` on disk while you improve it.
- Keep helper scripts, logs, extracted archives, probes, and scratch files outside `memory/` and `.agents/skills/`, for example under `scratch/`, `tmp/`, or the workspace root.
- Do not depend on repository files or paths outside this prepared workspace.

# First Actions

1. Read `README.md` and confirm the output schema.
2. Inspect `memory/` and `.agents/skills/`:
   - use relevant prior notes or skills as hints,
   - ignore unrelated benchmark notes,
   - do not overwrite unrelated notes.
3. Create a simple valid or likely-valid `solution.json` quickly.
4. Iterate with scripts and `./verifier` until time runs out or improvement stalls.
5. Before the final answer, update durable memory and reusable skills as described below.

# Memory Discipline

The next space agent is the reader. Write memory so it can immediately decide what to do on a later case.

- Never use a single generic `memory/run_notes.md` for all benchmarks.
- Use benchmark-scoped memory filenames. Examples:
  - `memory/stereo-imaging-run-notes.md`
  - `memory/revisit-constellation-run-notes.md`
  - `memory/relay-constellation-run-notes.md`
  - `memory/regional-coverage-run-notes.md`
  - `memory/aeossp-standard-run-notes.md`
  - `memory/spot5-run-notes.md`
- If a relevant benchmark note already exists, update it in place while preserving still-correct prior lessons.
- If there is no relevant benchmark note, create one.
- Keep memory concise. Prefer:
  - final verifier metrics,
  - the output schema,
  - the solver approach that worked,
  - failed approaches worth avoiding,
  - command patterns that can be reused,
  - important verifier diagnostics visible through `./verifier`.
- Do not preserve raw scratch artifacts in `memory/`: no generated solvers, archives, binaries, `.pyc`, extracted verifier payloads, full logs, or copied case data.
- Do not write "see `scratch/...`" as the only explanation. Summarize the reusable idea directly in the note.

# Skill Discipline

Use `.agents/skills/` for reusable procedures, not one-off case notes.

- If you discover a method that should transfer across cases, create or update `.agents/skills/<skill-name>/SKILL.md`.
- Every skill must be a directory with a `SKILL.md` file, using lowercase kebab-case.
- Good skill topics include parsers, CP-SAT formulations, orbit or geometry workflows, local search patterns, verifier usage workflows, and compact solver recipes.
- Keep skills short and procedural. The first few lines should tell the next space agent when to use the skill and what to do first.
- Do not put loose markdown files directly under `.agents/skills/`.
- If available, read `/home/korolev/.config/opencode/skills/skill-writing/SKILL.md` before creating a skill.

# Final Memory Audit

Before your final response:

1. List `memory/` and `.agents/skills/`.
2. Confirm there is a benchmark-scoped memory note for this run.
3. Confirm you did not overwrite unrelated benchmark notes.
4. Confirm `.agents/skills/` contains only formal skill directories plus `.gitkeep`.
5. Remove accidental scratch files from preserved directories.
6. Make sure `solution.json` is still present at the workspace root.

# Accumulated Skill Template

Use this minimal shape for reusable skills:

```text
.agents/skills/<skill-name>/
└── SKILL.md
```

```markdown
---
name: <skill-name>
description: <When to use this skill, including benchmark family, file type, or solver pattern triggers.>
---

# <Skill Title>

## Workflow

1. Read the current workspace `README.md` and confirm the case contract.
2. Apply the reusable method here.
3. Verify with the workspace verifier when present.

## Notes

- Keep only durable, transferable details here.
- Put current-case metrics and failed attempts in `memory/`, not in this skill.
- Do not reference `scratch/` files as the only source of the method; summarize the reusable method here.
```
