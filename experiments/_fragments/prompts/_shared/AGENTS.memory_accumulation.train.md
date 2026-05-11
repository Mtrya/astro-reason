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

- Before solving, inspect `memory/` when they exist. Use any relevant procedures, scripts, diagnostics, or skills.
- Use `memory/` for what you did: concise run notes, attempts, diagnostics, verifier observations, useful command patterns, but don't point to artifacts or scripts you created in this workspace, for only `memory/` and `.agents/skills/` will be preserved.
- Use `.agents/skills/` for what you learnt: reusable procedures, modeling patterns, parser utilities, implementation tactics, and compact skill instructions that can help on later work.
- During and after solving, update `memory/` and `.agents/skills/` with reusable and helpful knowledge. Prefer durable guidance over one-off transcripts.
- Don't prune easily. Be very cautious when deleting or replacing memory files, ensure they are stale, misleading, redundant, too verbose, or only useful for a single finished attempt before pruning.
- Preserve information that would save time later: working solution strategies, failure modes, verifier diagnostics, reusable scripts, schema notes, and decisions that changed your approach.
- Later work may use different schemas, file formats, and scoring rules. Write accumulated artifacts so they are broadly useful when possible.
- Do not rely on hidden repository paths or files outside this workspace when writing reusable artifacts.
