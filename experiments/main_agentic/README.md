# Main Agentic

`main_agentic` is the canonical experiment family for running the current benchmark x harness matrix across the finished benchmark set.

The family has three entrypoints:

- `run.py`: execute the matrix or an interactive workspace
- `plan.py`: preview the effective selection and skip/rerun decisions
- `aggregate.py`: summarize completed batch artifacts

## Batch Runs

Run the default batch matrix:

```bash
uv run python experiments/main_agentic/run.py
```

Preview the effective batch selection without executing anything:

```bash
uv run python experiments/main_agentic/run.py --dry-run
uv run python experiments/main_agentic/plan.py
```

Filter by benchmark, harness, split, or exact case id:

```bash
uv run python experiments/main_agentic/run.py \
  --benchmark aeossp_standard \
  --harness opencode_glm \
  --split test \
  --case case_0001
```

`--benchmark`, `--harness`, and `--case` may be repeated.

## Resume And Rerun Controls

Default batch behavior is artifact-first:

- missing `run.json` artifacts are executed
- malformed `run.json` artifacts are executed
- existing runs whose `overall_status` is in `matrix.yaml` `retry_statuses` are executed
- other completed runs are skipped

Preview or rerun only specific stored statuses:

```bash
uv run python experiments/main_agentic/run.py \
  --benchmark aeossp_standard \
  --harness opencode_glm \
  --rerun-status timeout
```

Force all selected runs to execute again:

```bash
uv run python experiments/main_agentic/run.py \
  --benchmark aeossp_standard \
  --harness opencode_glm \
  --no-skip-completed
```

`--rerun-status` and `--no-skip-completed` are mutually exclusive.

## Interactive Debugging

Prepare the interactive workspace and enter the container shell without auto-launching any harness:

```bash
uv run python experiments/main_agentic/run.py --interactive
```

Override the default interactive case:

```bash
uv run python experiments/main_agentic/run.py \
  --interactive \
  --benchmark aeossp_standard \
  --harness opencode_glm \
  --split test \
  --case case_0001
```

Use `--dry-run` with `--interactive` to preview the workspace and output paths without starting the container.

## Aggregation

Summarize completed batch artifacts:

```bash
uv run python experiments/main_agentic/aggregate.py
```

This writes matrix-level and benchmark-level summaries under:

```text
results/agent_runs/experiments/main_agentic/matrix/summaries/
```

## Current Limits

- Phase 7 adds console-based live progress, not a separate persisted batch-status file.
- Case filtering is exact-match only; no glob, prefix, or range selection is supported.
- Interactive aggregation is not supported.
