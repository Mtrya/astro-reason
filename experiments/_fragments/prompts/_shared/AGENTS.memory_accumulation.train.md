# Workspace Rules

- Work only with the files that are present in this prepared workspace.
- Keep helper scripts, notes, and temporary files inside this workspace.
- Edit files in this workspace freely when it helps you solve the case.
- Treat `solution.json` as the required final deliverable unless the workspace says otherwise.
- Use scripts or direct case-specific work as appropriate for the task.
- If the workspace exposes a verifier helper, use it for local iteration when helpful.
- Use any example solution only to understand the expected output shape, not as a finished answer.
- The run may be stopped after 2 hours. As soon as you have any valid or likely-valid answer, write it to `solution.json` and keep that file valid while you continue improving it.
- Prefer incremental improvement: preserve the best working `solution.json` you have, and only replace it after the replacement is written completely and is at least as likely to verify.
- Avoid depending on repository files or tools that are not part of the prepared workspace.

# Memory And Skills

- Before solving, inspect `memory/` and `.agents/skills/` when they exist. Read any relevant prior run notes, reusable procedures, scripts, diagnostics, or skills.
- Treat memory and skills as guidance, not authority. Check them against the current `README.md`, case files, and verifier behavior.
- Use `memory/` for what you did in this run: concise run notes, attempts, diagnostics, verifier observations, useful command patterns, and final metrics.
- Use `.agents/skills/` only for reusable procedures that should transfer to later cases: modeling patterns, parser utilities, verifier workflows, implementation tactics, and compact solver recipes.
- Do not put loose markdown notes directly under `.agents/skills/`. Every accumulated skill must be a directory named in lowercase kebab-case with a `SKILL.md` file, such as `.agents/skills/spot-cpsat/SKILL.md`.
- If you create or update a skill, use the skill-writing guidance when available at `/home/korolev/.codex/skills/skill-writing/SKILL.md` or `/home/korolev/.config/opencode/skills/skill-writing/SKILL.md`.
- During and after solving, update `memory/` and, when there is a genuinely reusable method, `.agents/skills/<skill-name>/SKILL.md`. Prefer durable guidance over one-off transcripts.
- Don't prune easily. Be very cautious when deleting or replacing memory files, ensure they are stale, misleading, redundant, too verbose, or only useful for a single finished attempt before pruning.
- Preserve information that would save time later: working solution strategies, failure modes, verifier diagnostics, reusable scripts, schema notes, and decisions that changed your approach.
- Later work may use different schemas, file formats, and scoring rules. Write accumulated artifacts so they are broadly useful when possible.
- Do not rely on hidden repository paths or files outside this workspace when writing reusable artifacts.

## Accumulated Skill Template

When creating a new skill, use this minimal shape:

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
```
