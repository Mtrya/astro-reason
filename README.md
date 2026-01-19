# AstroReason-Bench

Official implementation of **AstroReason-Bench: Evaluating Unified Agentic Planning across Heterogeneous Space Planning Problems**.

AstroReason-Bench is a comprehensive benchmark for evaluating agentic planning in astronautics mission design and planning. It integrates multiple scheduling regimes under a unified agent-oriented interface with strict physical constraints.

## Overview

Five distinct planning challenges enforcing orbital mechanics, power budgets, data storage, and slew kinematics:

1. **SatNet** - Deep Space Network resource allocation
2. **Revisit Optimization** - Minimize time gaps for continuous target monitoring
3. **Regional Coverage** - Maximize area coverage using strip-imaging satellites
4. **Stereo Imaging** - Schedule synchronized observation pairs for 3D reconstruction
5. **Latency Optimization** - Manage LEO constellation for integrated sensing and communications

## Installation

### Prerequisites

- **Python 3.12+**
- **[Claude Code](https://claude.com/claude-code)** (required - agentic LLM interface)
- **[uv](https://docs.astral.sh/uv/)** (required - manages environments and builds sandboxes)
- **bubblewrap** (optional, enables filesystem isolation):
  ```bash
  # Debian/Ubuntu
  sudo apt install bubblewrap

  # Arch Linux
  sudo pacman -S bubblewrap

  # Fedora
  sudo dnf install bubblewrap
  ```

### Setup

```bash
# Clone the repository with submodules
git clone --recurse-submodules https://github.com/your-org/astro-reason.git
cd astro-reason

# If you already cloned without submodules, initialize them:
# git submodule update --init --recursive

# Create virtual environment and install dependencies
uv sync --all-groups

# Activate the environment (required for all subsequent commands)
source .venv/bin/activate  # bash/zsh
# or: source .venv/bin/activate.fish  # fish

# Build sandbox environments (required before running benchmarks)
bash src/benchmark/build_sandbox.sh
bash src/satnet_agent/build_sandbox.sh
```

**Note:** The build scripts use `uv pip install --python` to install dependencies with shebangs pointing to `.venv/bin/python3`. Always activate the virtual environment before building or running benchmarks.

### API Keys

```bash
export ANTHROPIC_API_KEY="..."      # Claude
export DEEPSEEK_API_KEY="..."       # DeepSeek
export DASHSCOPE_API_KEY="..."      # Qwen
```

## How to Run

### Running For Novel Benchmarks

Evaluate agentic LLM systems on benchmarks:

```bash
# Single case evaluation
python src/benchmark/run_benchmark.py \
  --benchmark revisit-optimization \
  --case case_0001 \
  --model anthropic::claude-sonnet-4-5-20250929

# All cases in benchmark
python src/benchmark/run_benchmark.py \
  --benchmark stereo-imaging \
  --all \
  --model anthropic::claude-sonnet-4-5-20250929

# Interactive mode (for close inspection and observation)
python src/benchmark/run_benchmark.py \
  --benchmark regional-coverage \
  --case case_0001 \
  --model anthropic::claude-sonnet-4-5-20250929 \
  --interactive

# File system isolation and resource limits
python src/benchmark/run_benchmark.py \
  --benchmark latency-optimization \
  --case case_0001 \
  --bwrap \
  --cpu-quota 800% \
  --memory-limit 16G \
  --model deepsee::deepseek-chat
```

**Available benchmarks:** `revisit-optimization`, `stereo-imaging`, `latency-optimization`, `regional-coverage`

### Running SatNet (DSN Scheduling) Benchmark

SatNet uses a separate runner:

```bash
# Run SatNet Week 40
python src/satnet_agent/run_benchmark.py \
  --week 40 \
  --model anthropic::claude-sonnet-4-5-20250929

# Run all weeks
python src/satnet_agent/run_benchmark.py \
  --all \
  --model anthropic::claude-sonnet-4-5-20250929

# Interactive mode
python src/satnet_agent/run_benchmark.py \
  --week 40 \
  --model anthropic::claude-sonnet-4-5-20250929 \
  --interactive

# File isolation and resource limits
python src/satnet_agent/run_benchmark.py \
  --week 40
  --model anthropic::claude-sonnet-4-5-2025-0929 \
  --bwrap \
  --memory-limit 16G \
  --cpu-quota 800%
```

**Available weeks:** 10, 20, 30, 40, 50

### Running Tests

Run the test suite to verify installation and environment setup:

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_mcp_server.py

# Run with verbose output
pytest -v

# Run specific benchmark tests
pytest tests/test_scenario_satnet.py
```

### Reproducing Paper Results

```bash
# Run all benchmarks with Claude Sonnet 4.5
for benchmark in revisit-optimization stereo-imaging latency-optimization regional-coverage; do
  python src/benchmark/run_benchmark.py \
  --benchmark $benchmark \
  --bwrap --memory-limit 16G --cpu-quota 800% \
  --all \
  --model anthropic::claude-sonnet-4-5-20250929 \
  --timeout 7200
done

# Run SatNet weeks
python src/satnet_agent/run_benchmark.py \
--bwrap --memory-limit 16G --cpu-quota 800% \
--all \
--model anthropic::claude-sonnet-4-5-20250929 \
--timeout 7200
```

## Dataset Structure

Each benchmark case includes:

```
src/dataset/<benchmark>/cases/<case_id>/
├── mission_brief.md      # Natural language task description
├── manifest.json         # Case metadata and configuration
├── requirements.yaml     # Mission-specific requirements
├── satellites.yaml       # Satellite constellation definition
├── stations.yaml         # Ground station locations
├── targets.yaml          # Observation targets
└── initial_plan.json     # Empty/template plan
```

## Architecture

Four-layer design:

1. **Physics Layer** - SGP4 propagation, slew kinematics, resource modeling (stateless)
2. **Scenario Layer** - State management, action registry, persistence (stateful)
3. **Interface Layer** - MCP tools + Python API
4. **Cognitive Layer** - LLM agent (ReAct loop via Claude Code)

Agents use MCP tools for exploration and Python scripts for bulk optimization.

## Citation

If you use AstroReason-Bench in your research, please cite:

```bibtex
@article{wang2026astroreason,
      title={AstroReason-Bench: Evaluating Unified Agentic Planning across Heterogeneous Space Planning Problems}, 
      author={Weiyi Wang and Xinchi Chen and Jingjing Gong and Xuanjing Huang and Xipeng Qiu},
      year={2026},
      eprint={2601.11354},
      archivePrefix={arXiv},
      primaryClass={cs.AI},
      url={https://arxiv.org/abs/2601.11354}, 
}
```

## References

This benchmark integrates the SatNet scheduling problem:

```bibtex
@inproceedings{goh2021satnet,
  title={SatNet: A benchmark for satellite scheduling optimization},
  author={Goh, Edwin and Venkataram, Hamsa Shwetha and Balaji, Bharathan and Wilson, Brian D and Johnston, Mark D},
  booktitle={AAAI-22 Workshop on Machine Learning for Operations Research (ML4OR)},
  year={2021}
}
```

## Data Sources

Benchmark datasets are derived from the following sources:

- **TLE orbital data**: [CelesTrak](https://celestrak.org/)
- **City locations**: [World cities database](https://www.kaggle.com/datasets/juanmah/world-cities) (CC BY 4.0)
- **Ground stations**: [Ground Station Dataset](https://www.kaggle.com/datasets/pratiksharm/ground-station-dataset) (MIT License)

**Note:** Satellite parameters other than orbital elements (e.g., power budgets, data storage, slew rates) are fictional or represent typical values for benchmark purposes.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.