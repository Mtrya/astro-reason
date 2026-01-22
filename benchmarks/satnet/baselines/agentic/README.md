# SatNet Agentic Baseline

This directory contains the agentic baseline for the SatNet DSN scheduling benchmark.

## Overview

The agentic baseline runs an LLM agent in an isolated sandbox to solve DSN (Deep Space Network) antenna scheduling problems. The agent receives a detailed mission brief explaining the scheduling constraints and uses a verifier tool to validate its solutions.

## Usage

### Single Case

```bash
python benchmarks/satnet/baselines/agentic/run.py \
    --case w10_2018 \
    --model anthropic::claude-sonnet-4-20250514
```

### All Cases

```bash
python benchmarks/satnet/baselines/agentic/run.py \
    --case all \
    --model anthropic::claude-sonnet-4-20250514
```

### With Retries

```bash
python benchmarks/satnet/baselines/agentic/run.py \
    --case w10_2018 \
    --model anthropic::claude-sonnet-4-20250514 \
    --max-retries 2
```

### Non-Interactive with Skip Permissions (Benchmark Mode)

```bash
python benchmarks/satnet/baselines/agentic/run.py \
    --case w10_2018 \
    --model anthropic::claude-sonnet-4-20250514 \
    --dangerously-skip-permissions
```

> **Note**: `--dangerously-skip-permissions` requires bwrap sandboxing.

### Interactive Mode

```bash
python benchmarks/satnet/baselines/agentic/run.py \
    --case w10_2018 \
    --model anthropic::claude-sonnet-4-20250514 \
    --interactive
```

## Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `--case` | Yes | Case ID (e.g., `w10_2018`) or `all` |
| `--model` | Yes | Model to use (e.g., `anthropic::claude-sonnet-4-20250514`) |
| `--output` | No | Output directory (default: `/tmp/satnet_benchmark`) |
| `--timeout` | No | Timeout in seconds (default: 3600) |
| `--max-retries` | No | Max retries on invalid solutions (default: 0) |
| `--no-bwrap` | No | Disable bwrap sandboxing |
| `--memory-limit` | No | Memory limit (e.g., `4G`) |
| `--cpu-quota` | No | CPU quota (e.g., `200%`) |
| `--interactive` | No | Run in interactive mode |
| `--debug` | No | Enable debug mode |
| `--dangerously-skip-permissions` | No | Skip Claude permission prompts (requires bwrap) |

## Sandbox Structure

```
sandbox/
├── workspace/
│   ├── .claude/
│   │   ├── settings.json       # Permission allowlist
│   │   └── settings.local.json
│   ├── data/
│   │   ├── problems.json       # DSN scheduling requests
│   │   └── maintenance.csv     # Antenna maintenance windows
│   ├── mission.md              # Mission brief for the agent
│   ├── verifier.py             # Solution verifier
│   ├── pixi.toml               # Pixi project (auto-generated)
│   └── solution.json           # Agent output
└── .claude/
    └── settings.json
```

## Environment Isolation

Each run creates a fresh Python environment using `pixi`:
- No host environment contamination
- Efficient caching via `rattler` and `uv`
- `bwrap` provides filesystem isolation

## Output

Results are saved to `<output>/<case>/`:
- `metrics.json`: Scoring results
- `agent.log`: Agent execution log
- `sandbox/`: Complete sandbox state

