# Difficulty Ablation

`difficulty_ablation` compares AEOSSP agent performance across benchmark-owned difficulty splits while keeping the runtime image, harnesses, prompt surface, opaque verifier helper, and official evaluation protocol fixed.

The default matrix runs:

- benchmark: `aeossp_standard`
- splits: `test_easy`, `test`, `test_hard`
- harnesses: `codex`, `opencode_dpsk`
- cases: `case_0001` through `case_0005`

Interpret summaries by difficulty first, then by harness. `test` is the benchmark-owned medium split. Large drops from easy to medium or hard should be inspected case-by-case before interpretation, since they may reflect scale, congestion, brittle solution strategies, or missing artifacts rather than one single failure mode.

## Run

Preview the default 30-run matrix:

```bash
uv run python experiments/difficulty_ablation/run.py --dry-run
```

Run one smoke-sized selection:

```bash
uv run python experiments/difficulty_ablation/run.py \
  --harness codex \
  --split test_easy \
  --case case_0001
```

Prepare one interactive workspace:

```bash
uv run python experiments/difficulty_ablation/run.py --interactive
```

Use `--force` to replace an existing interactive workspace or output directory.

Aggregate completed runs:

```bash
uv run python experiments/difficulty_ablation/aggregate.py
```

## Results

Batch artifacts live under:

```text
<results.root>/<config>/<split>/<benchmark>/<harness>/<case>/
```

`results.root`, `split`, and `benchmark` come from `configs/default.yaml`; the default root is `results/agent_runs/experiments/difficulty_ablation`. Aggregation writes `summary.json`, `runs.csv`, and `difficulty_progression.csv` under the configured summaries directory.
