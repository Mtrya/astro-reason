# Skill Injection Ablation

This experiment family tracks issue #59: measuring whether task-specific,
repository-owned skills improve space-agent performance when benchmark,
runtime, verifier exposure, and harness settings are otherwise fixed.

The initial benchmark was `stereo_imaging`. It was selected because weak
harnesses often produce invalid or valid-but-near-zero solutions under opaque
verifier exposure, while transparent verifier exposure shows the task is
learnable when agents receive better constraint feedback. The matrix now also
includes `satnet` on `codex` for a narrower test of whether a standalone
SatNet CP-SAT scheduling skill improves a resource-scheduling task.

## Conditions

- `no_skill`: control condition; no injected task-specific skills. This is the `main_agentic` default and is collected from existing `main_agentic/matrix` artifacts instead of rerun in this family.
- `compact_domain`: one compact stereo-imaging procedural skill.
- `skill_pack`: four focused skills covering Python search performance,
  OR-Tools CP-SAT modeling, classical OR scheduling methods, and
  stereo-imaging product strategy.
- `satnet_ortools_python`: one standalone SatNet CP-SAT scheduling skill.

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

Preview one stereo skill condition:

```bash
uv run python experiments/skill_injection/run.py \
  --dry-run \
  --condition compact_domain \
  --harness opencode_dpsk \
  --case case_0001
```

Preview the SatNet skill condition:

```bash
uv run python experiments/skill_injection/run.py \
  --dry-run \
  --benchmark satnet \
  --condition satnet_ortools_python \
  --harness codex \
  --case W10_2018
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

## Interactive Workspaces

Prepare an interactive Docker workspace matching one skill-injection condition:

```bash
uv run python experiments/skill_injection/run.py \
  --interactive \
  --condition satnet_ortools_python \
  --benchmark satnet \
  --harness codex \
  --case W10_2018
```

The interactive shell starts in `/app/workspace` with the same prompt, case files,
opaque verifier helper, harness config, and injected skills that the batch run
would expose. Inside the shell, run the printed harness command manually when
ready. Re-run with `--force` to replace an existing interactive workspace.

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

Aggregation always includes `no_skill` rows by reading:

```text
results/agent_runs/experiments/main_agentic/matrix/
```

Write reader-facing markdown reports from aggregate artifacts:

```bash
uv run python experiments/skill_injection/write_reports.py
```

Reports and plots are written under:

```text
experiments/skill_injection/reports/
```

The score plot artifacts are:

```text
experiments/skill_injection/reports/stereo_imaging_opencode_dpsk_scores.png
experiments/skill_injection/reports/stereo_imaging_opencode_minimax_scores.png
experiments/skill_injection/reports/satnet_codex_scores.png
```

Refresh only the score plots:

```bash
uv run python experiments/skill_injection/plot_scores.py
```
