# Harness Ablation

`harness_ablation` compares three configured agentic-system harness profiles on the same AEOSSP cases. In this experiment family, a harness is the full `harness x model/config` profile, so the ablation intentionally varies the configured agentic system while holding benchmark, split, prompt surface, opaque verifier helper, and official evaluation protocol fixed.

The default matrix runs:

- benchmark: `aeossp_standard`
- split: `test`
- harnesses: `claude_code_kimi`, `kimi_cli`, `opencode_kimi`
- cases: `case_0001` through `case_0005`

The three default harnesses are Kimi-flavored profiles using different CLI substrates. Real credentials and gateway endpoints live in ignored local config directories under `experiments/_fragments/configs/`.

## Run

Preview the default 15-run matrix:

```bash
uv run python experiments/harness_ablation/run.py --dry-run
```

Run one smoke-sized selection:

```bash
uv run python experiments/harness_ablation/run.py \
  --harness kimi_cli \
  --case case_0001
```

Prepare one interactive workspace:

```bash
uv run python experiments/harness_ablation/run.py --interactive
```

Use `--force` to replace an existing interactive workspace or output directory.

Aggregate completed runs:

```bash
uv run python experiments/harness_ablation/aggregate.py
```

## Results

Batch artifacts live under:

```text
<results.root>/<config>/<split>/<benchmark>/<harness>/<case>/
```

`results.root`, `split`, and `benchmark` come from `configs/default.yaml`; the default root is `results/agent_runs/experiments/harness_ablation`. Aggregation writes `summary.json`, `runs.csv`, and `harness_case_summary.csv` under the configured summaries directory.
