# Temporal Robustness

`temporal_robustness` compares AEOSSP performance across two benchmark-owned epoch families while keeping the solving surface otherwise fixed.

The default matrix runs:

- benchmark: `aeossp_standard`
- splits: `test`, `test_horizon_2022`
- harnesses: `codex`, `opencode_dpsk`
- cases: `case_0001` through `case_0005`

Both split families expose the same problem description, prompt, Brahe skill, opaque verifier helper, runtime image, and harness-specific config style. The official verifier still runs outside the solving workspace.

## Run

Preview the default 20-run matrix:

```bash
uv run python experiments/temporal_robustness/run.py --dry-run
```

Run one smoke-sized selection:

```bash
uv run python experiments/temporal_robustness/run.py \
  --harness codex \
  --split test_horizon_2022 \
  --case case_0001
```

Prepare one interactive workspace:

```bash
uv run python experiments/temporal_robustness/run.py --interactive
```

Aggregate completed runs:

```bash
uv run python experiments/temporal_robustness/aggregate.py
```

## Results

Batch artifacts live under:

```text
results/agent_runs/experiments/temporal_robustness/<config>/<split>/aeossp_standard/<harness>/<case>/
```

Aggregation writes `summary.json`, `runs.csv`, and `paired_deltas.csv` under the configured summaries directory.
