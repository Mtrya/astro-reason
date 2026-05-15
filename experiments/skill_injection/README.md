# Skill Injection Ablation

This experiment family tracks issue #59: measuring whether task-specific,
repository-owned skills improve space-agent performance when benchmark,
runtime, verifier exposure, and harness settings are otherwise fixed.

The initial benchmark was `stereo_imaging`. The configured matrix now also
covers `regional_coverage` and `relay_constellation` to test whether weaker
harnesses improve on additional mission-design tasks when given
benchmark-scoped skills.

## Conditions

- `no_skill`: control condition; no injected task-specific skills. This is the `main_agentic` default and is collected from existing `main_agentic/matrix` artifacts instead of rerun in this family.
- `compact_domain`: one compact benchmark-scoped procedural skill.
- `skill_pack`: benchmark-scoped strategy skills plus the shared optimization
  skills useful for that benchmark.

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

Preview the regional and relay Phase 6 expansion only:

```bash
uv run python experiments/skill_injection/run.py \
  --dry-run \
  --benchmark regional_coverage \
  --benchmark relay_constellation
```

Preview one stereo skill condition:

```bash
uv run python experiments/skill_injection/run.py \
  --dry-run \
  --condition compact_domain \
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

## Interactive Workspaces

Prepare an interactive Docker workspace matching one skill-injection condition:

```bash
uv run python experiments/skill_injection/run.py \
  --interactive \
  --condition compact_domain \
  --benchmark stereo_imaging \
  --harness opencode_dpsk \
  --case case_0001
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

The benchmark reports are:

```text
experiments/skill_injection/reports/stereo_imaging.md
experiments/skill_injection/reports/regional_coverage.md
experiments/skill_injection/reports/relay_constellation.md
```

The score plot artifacts are:

```text
experiments/skill_injection/reports/stereo_imaging_opencode_dpsk_scores.png
experiments/skill_injection/reports/stereo_imaging_opencode_minimax_scores.png
experiments/skill_injection/reports/regional_coverage_opencode_dpsk_scores.png
experiments/skill_injection/reports/regional_coverage_opencode_minimax_scores.png
experiments/skill_injection/reports/relay_constellation_opencode_dpsk_scores.png
experiments/skill_injection/reports/relay_constellation_opencode_minimax_scores.png
```

Refresh only the score plots:

```bash
uv run python experiments/skill_injection/plot_scores.py
```
