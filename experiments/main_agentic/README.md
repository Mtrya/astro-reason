# Main Agentic

`main_agentic` is the canonical experiment family for running the current finished benchmark set across agentic harnesses.

The tracked family shape is about benchmarks, harnesses, prompts, execution, and aggregation. Exact model names, provider accounts, and gateway endpoints belong in ignored local harness config directories under `experiments/_fragments/configs/`.

## Layout

```text
experiments/main_agentic/
├── run.py              # execute batch runs or prepare an interactive workspace
├── plan.py             # preview matrix expansion and skip/rerun decisions
├── aggregate.py        # summarize completed batch artifacts
├── configs/
│   ├── matrix.yaml      # canonical batch matrix
│   └── interactive.yaml # local interactive debugging defaults
├── benchmarks/         # benchmark assembly and aggregation profiles
└── harnesses/          # harness assembly, command, env, and collection profiles
```

Reusable prompt and config assets live outside the family:

```text
experiments/_fragments/
├── prompts/<benchmark>/
└── configs/<harness>/
```

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

Override the configured batch concurrency for one invocation:

```bash
uv run python experiments/main_agentic/run.py --max-concurrency 2
uv run python experiments/main_agentic/plan.py --max-concurrency 2
```

`--max-concurrency` is batch-only. The run queue is case-major within each benchmark, so concurrent workers are less likely to start several jobs from the same harness at once.

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

When multiple harnesses assemble files to the same container target in interactive mode, the first selected harness wins. This keeps all-harness debugging usable for harnesses that share one config path.

## Assembly Model

Each concrete run is assembled from benchmark and harness profiles.

Benchmark profiles own:

- case and verifier workspace assembly
- benchmark-facing `README.md` and `PROMPT.md` fragments
- benchmark-native aggregation metadata

Harness profiles own:

- runtime choice
- local harness config assembly
- headless shell command
- collected session/log artifacts
- explicit environment-variable allowlists

`assemble` sources are repo-relative paths. `assemble` targets are absolute container paths.

`collect` sources are absolute container paths. `collect` targets may start with:

- `results_root/`
- `repo/`
- `benchmark/` or `benchmarks/`
- `experiments/`

## Prompt Shape

Benchmark-facing prompt fragments should feel like a real engineering handoff, not an evaluation package.

- `README.md` is the substantive problem brief. It may be comprehensive and should explain the problem model, expected solution artifact, available files, and useful local verifier helper when present.
- `PROMPT.md` is the thin tasking note. It should be concise, direct, and operational.
- shared `AGENTS.md` is the benchmark-neutral working-style layer. It should stay minimal and avoid benchmark, harness, Docker, or matrix-specific content.

Prompt fragments should avoid words like `benchmark`, `split`, `leaderboard`, and testing/interview framing when addressing the space agent.

## Results

Batch run artifacts live under:

```text
results/agent_runs/experiments/main_agentic/<config>/<benchmark>/<harness>/<split>/<case>/
```

Interactive workspaces live under:

```text
.runtime/interactive_workspaces/experiments/main_agentic/<config>/<benchmark>/<harness>/<split>/<case>/
```

Every concrete run writes one `run.json`. Aggregation reads `run.json` artifacts, not raw session logs.

External verification is performed through benchmark-owned verifier executable entrypoints. `main_agentic` does not import benchmark-internal verifier APIs.
Most verifiers emit JSON; SatNet and SPOT5 currently emit text CLI reports, so the runner parses their verbose output into the same `run.json` verifier section used by aggregation.

## Aggregation

Summarize completed batch artifacts:

```bash
uv run python experiments/main_agentic/aggregate.py
```

This writes matrix-level and benchmark-level summaries under:

```text
results/agent_runs/experiments/main_agentic/matrix/summaries/
```

No cross-benchmark universal score is invented; metric summaries stay benchmark-native.

## Current Limits

- Case filtering is exact-match only; no glob, prefix, or range selection is supported.
- Interactive aggregation is not supported.
- The YAML schemas are family-owned runner configs, not public cross-family contracts yet.
