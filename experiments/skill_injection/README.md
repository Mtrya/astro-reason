# Skill Injection Ablation

This experiment family tracks issue #59: measuring whether task-specific,
repository-owned skills improve space-agent performance when benchmark,
runtime, verifier exposure, and harness settings are otherwise fixed.

The initial benchmark is `stereo_imaging`. It was selected because weak
harnesses often produce invalid or valid-but-near-zero solutions under opaque
verifier exposure, while transparent verifier exposure shows the task is
learnable when agents receive better constraint feedback.

## Conditions

- `no_skill`: control condition; no injected task-specific skills.
- `compact_domain`: one compact stereo-imaging procedural skill.
- `skill_pack`: four focused skills covering Python search performance,
  OR-Tools CP-SAT modeling, classical OR scheduling methods, and
  stereo-imaging product strategy.

Skill assembly is owned by the condition profiles under:

```text
experiments/skill_injection/conditions/
```

The copied skill payloads live under:

```text
experiments/_fragments/skills/skill_injection/
```

That fragments directory should contain only actual skill directories, not
experiment manifests.

## Running

Preview the configured matrix:

```bash
uv run python experiments/skill_injection/run.py --dry-run
```

Preview only the control condition:

```bash
uv run python experiments/skill_injection/run.py \
  --dry-run \
  --condition no_skill \
  --harness opencode_dpsk \
  --case case_0001
```

Run selected work:

```bash
uv run python experiments/skill_injection/run.py \
  --condition skill_pack \
  --harness opencode_dpsk \
  --case case_0001
```

Useful execution controls:

- `--timeout`: override `timeout_seconds` for this invocation.
- `--max-concurrency`: override `batch.max_concurrency`.
- `--rerun-status STATUS`: rerun only artifacts currently recorded with this status, or missing/malformed artifacts via `missing_artifact` / `malformed_artifact`.
- `--no-skip-completed`: ignore stored `run.json` statuses and rerun selected items.

## Aggregation And Reports

Aggregate completed and missing artifacts:

```bash
uv run python experiments/skill_injection/aggregate.py
```

This writes:

```text
results/agent_runs/experiments/skill_injection/summaries/summary.json
results/agent_runs/experiments/skill_injection/summaries/runs.csv
```

Write reader-facing markdown reports from aggregate artifacts:

```bash
uv run python experiments/skill_injection/write_reports.py
```

Reports are written under:

```text
experiments/skill_injection/reports/
```
