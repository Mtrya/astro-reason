#!/usr/bin/env python3
"""Astrox Benchmark Runner.

Sets up a sandbox environment and runs an LLM agent on satellite mission planning tasks.

Usage:
    # Single case, single model
    python -m toolkit.agents.runner --benchmark revisit-optimization --case case_0001 --model anthropic::claude-sonnet-4-20250514
    
    # All cases, single model
    python -m toolkit.agents.runner --benchmark stereo-imaging --all --model deepseek::deepseek-reasoner
    
    # All cases, multiple models
    python -m toolkit.agents.runner --benchmark revisit-optimization --all --models anthropic::claude-sonnet-4 deepseek::deepseek-reasoner
    
    # With retry on invalid plans
    python -m toolkit.agents.runner --benchmark stereo-imaging --all --model anthropic::claude-sonnet-4 --retry-on-invalid --max-retries 2
    
    # Baseline algorithm
    python -m toolkit.agents.runner --benchmark revisit-optimization --case case_0001 --baseline greedy
    
    # Interactive mode
    python -m toolkit.agents.runner --benchmark regional-coverage --case case_0001 --interactive
    
    # From experiment config file
    python -m toolkit.agents.runner --experiment-config experiments/my_experiment.json

Model routing (new format: provider::model_id):
    - anthropic::model_id    Anthropic (default provider)
    - deepseek::model_id     DeepSeek API
    - qwen::model_id         Alibaba DashScope
    - minimax::model_id      MiniMax
    - glm::model_id          Zhipu AI
    - moonshot::model_id     Moonshot AI
    - openrouter::model_id   OpenRouter
    - lingleap::model_id     LingLeap

Legacy format (still supported):
    - claude-*: Anthropic
    - deepseek*: DeepSeek
    - qwen*: Alibaba DashScope
    - minimax*: MiniMax
    - glm*: Zhipu AI
    - kimi*, moonshot*: Moonshot AI
    - */model: OpenRouter
"""

import argparse
import json
import os
import sys
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

SANDBOX_TEMPLATE = Path(__file__).parent / "sandbox_template"
BENCHMARK_DATA_DIR = PROJECT_ROOT / "benchmarks"

BENCHMARKS = ["revisit-optimization", "stereo-imaging", "latency-optimization", "regional-coverage"]
DEFAULT_TIMEOUT = 3600
DEFAULT_OUTPUT_DIR = Path("/tmp/astrox_benchmark")
DEFAULT_MAX_RETRIES = 1


PROVIDER_CONFIGS = {
    "anthropic": {
        "name": "Anthropic",
        "base_url": None,
        "api_key_env": "ANTHROPIC_API_KEY",
    },
    "deepseek": {
        "name": "DeepSeek",
        "base_url": "https://api.deepseek.com/anthropic",
        "api_key_env": "DEEPSEEK_API_KEY",
    },
    "qwen": {
        "name": "Alibaba DashScope",
        "base_url": "https://dashscope-intl.aliyuncs.com/apps/anthropic",
        "api_key_env": "DASHSCOPE_API_KEY",
    },
    "minimax": {
        "name": "MiniMax",
        "base_url": "https://api.minimax.io/anthropic",
        "api_key_env": "MINIMAX_API_KEY",
    },
    "glm": {
        "name": "Zhipu AI",
        "base_url": "https://open.bigmodel.cn/api/anthropic",
        "api_key_env": "ZHIPU_API_KEY",
    },
    "moonshot": {
        "name": "Moonshot AI",
        "base_url": "https://api.moonshot.ai/anthropic",
        "api_key_env": "MOONSHOT_API_KEY",
    },
    "openrouter": {
        "name": "OpenRouter",
        "base_url": "https://openrouter.ai/api",
        "api_key_env": "OPENROUTER_API_KEY",
    },
    "lingleap": {
        "name": "LingLeap",
        "base_url": "https://api.lingleap.com",
        "api_key_env": "LINGLEAP_API_KEY",
    },
}


def configure_model_env(model: str) -> dict[str, str]:
    """Configure environment variables for model routing.
    
    Model format: <provider>::<model_id>
    Examples:
        - anthropic::claude-sonnet-4-20250514
        - deepseek::deepseek-reasoner
        - lingleap::claude-sonnet-4-20250514
    
    For backward compatibility, models without '::' are treated as anthropic provider
    if they start with 'claude', otherwise the provider is inferred from the model name prefix.
    """
    env = {}
    
    if "::" in model:
        provider, model_id = model.split("::", 1)
        provider = provider.lower()
        
        if provider not in PROVIDER_CONFIGS:
            raise ValueError(f"Unknown provider: {provider}. Available: {', '.join(PROVIDER_CONFIGS.keys())}")
        
        config = PROVIDER_CONFIGS[provider]
        print(f"  Provider: {config['name']}")
        
        env["ANTHROPIC_MODEL"] = model_id
        
        if config["base_url"]:
            env["ANTHROPIC_BASE_URL"] = config["base_url"]
        
        api_key = os.environ.get(config["api_key_env"], "")
        if api_key:
            env["ANTHROPIC_AUTH_TOKEN"] = api_key
    
    else:
        if model.startswith("claude"):
            provider = "anthropic"
        elif model.startswith("deepseek"):
            provider = "deepseek"
        elif model.startswith("qwen"):
            provider = "qwen"
        elif model.lower().startswith("minimax"):
            provider = "minimax"
        elif model.lower().startswith("glm"):
            provider = "glm"
        elif model.startswith("kimi") or model.startswith("moonshot"):
            provider = "moonshot"
        elif "/" in model:
            provider = "openrouter"
            model = model.replace("openrouter/", "")
        else:
            print(f"  Provider: Custom (using env vars)")
            env["ANTHROPIC_MODEL"] = model
            return env
        
        config = PROVIDER_CONFIGS[provider]
        print(f"  Provider: {config['name']} (legacy format)")
        
        env["ANTHROPIC_MODEL"] = model
        
        if config["base_url"]:
            env["ANTHROPIC_BASE_URL"] = config["base_url"]
        
        api_key = os.environ.get(config["api_key_env"], "")
        if api_key:
            env["ANTHROPIC_AUTH_TOKEN"] = api_key
        
    return env


def setup_sandbox(benchmark: str, case_id: str, output_dir: Path) -> Path:
    """Create sandbox by copying template and setting up case data.
    
    Structure (after setup):
        sandbox/
        ├── .claude/           # Global settings + CLAUDE.md
        │   ├── settings.json
        │   └── CLAUDE.md
        ├── .local/            # -> symlink to ~/.local (claude CLI)
        ├── lib/               # Python dependencies
        ├── data/              # -> symlink to case data
        ├── state/             # Runtime state directory
        └── workspace/         # Agent's working directory
            ├── .claude/
            ├── .mcp.json
            ├── engine/        # From sandbox_template
            ├── planner/       # From sandbox_template
            └── mission_brief.md  # Copied from case
    """
    sandbox_dir = output_dir / "sandbox"
    
    if sandbox_dir.exists():
        shutil.rmtree(sandbox_dir)
    
    shutil.copytree(SANDBOX_TEMPLATE, sandbox_dir, symlinks=True)
    
    # Fix data symlink to point to case directory
    benchmark_slug = benchmark.replace("-", "_")
    case_data_dir = BENCHMARK_DATA_DIR / benchmark_slug / "dataset" / case_id
    
    if not case_data_dir.exists():
        raise ValueError(f"Case directory not found: {case_data_dir}")
    
    data_link = sandbox_dir / "data"
    if data_link.is_symlink() or data_link.exists():
        data_link.unlink()
    data_link.symlink_to(case_data_dir.resolve())
    
    # Copy mission brief if exists
    workspace_dir = sandbox_dir / "workspace"
    mission_brief_src = case_data_dir / "mission_brief.md"
    if mission_brief_src.exists():
        shutil.copy2(mission_brief_src, workspace_dir / "mission_brief.md")
    
    return sandbox_dir


def build_bwrap_command(sandbox_dir: Path, benchmark: str, case_id: str) -> list[str]:
    """Build bwrap command for sandboxing."""
    cmd = [
        "bwrap",
        # System binaries and libraries (read-only)
        "--ro-bind", "/usr", "/usr",
        "--ro-bind", "/lib", "/lib",
        "--ro-bind", "/lib64", "/lib64",
        # Network and system config
        "--ro-bind", "/etc/resolv.conf", "/etc/resolv.conf",
        "--ro-bind", "/etc/ssl", "/etc/ssl",
        "--ro-bind", "/etc/passwd", "/etc/passwd",
        "--ro-bind", "/etc/group", "/etc/group",
        # Sandbox contents (read-only except state and workspace)
        "--ro-bind", str(sandbox_dir / "lib"), "/sandbox/lib",
        "--ro-bind", str(sandbox_dir / "data"), "/sandbox/data",
        "--bind", str(sandbox_dir / ".claude"), "/sandbox/.claude",
        "--bind", str(sandbox_dir / "state"), "/sandbox/state",
        "--bind", str(sandbox_dir / "workspace"), "/sandbox/workspace",
        # Virtual filesystems
        "--proc", "/proc",
        "--dev", "/dev",
        "--tmpfs", "/tmp",
        # Environment
        "--chdir", "/sandbox/workspace",
        "--setenv", "HOME", "/sandbox",
        "--setenv", "PYTHONPATH", "/sandbox/lib",
    ]
    
    # Resolve .local to real path to support absolute symlinks (like claude -> .../share/...)
    local_path = (sandbox_dir / ".local").resolve()
    user_home = local_path.parent
    
    # Create the user's home directory structure and bind .local
    if user_home.parent.name:
        cmd.extend(["--dir", str(user_home.parent)])
    cmd.extend(["--dir", str(user_home)])
    cmd.extend(["--ro-bind", str(local_path), str(local_path)])
    
    # Detect Virtual Environment
    is_venv = sys.prefix != sys.base_prefix
    if is_venv:
        # Mount venv to the EXACT SAME path to preserve strict pathing in scripts
        venv_path = sys.prefix
        cmd.extend(["--ro-bind", venv_path, venv_path])
        # Prepend venv bin to PATH, and include the resolved local bin path
        cmd.extend(["--setenv", "PATH", f"{venv_path}/bin:{local_path}/bin:/usr/bin:/bin"])
    else:
        cmd.extend(["--setenv", "PATH", f"{local_path}/bin:/usr/bin:/bin"])
    
    # Get case metadata for environment variables
    benchmark_slug = benchmark.replace("-", "_")
    case_data_dir = BENCHMARK_DATA_DIR / benchmark_slug / "dataset" / case_id
    manifest_path = case_data_dir / "manifest.json"
    
    if manifest_path.exists():
        with open(manifest_path) as f:
            manifest = json.load(f)
            horizon_start = manifest.get("horizon_start", "2024-01-01T00:00:00Z")
            horizon_end = manifest.get("horizon_end", "2024-01-02T00:00:00Z")
    else:
        horizon_start = "2024-01-01T00:00:00Z"
        horizon_end = "2024-01-02T00:00:00Z"
    
    cmd.extend([
        # Astrox-specific env vars
        "--setenv", "CASE_PATH", "/sandbox/data",
        "--setenv", "ASTROX_STATE_PATH", "/sandbox/state/scenario.json",
        "--setenv", "ASTROX_CASE_PATH", "/sandbox/data",
        "--setenv", "ASTROX_OUTPUT_PATH", "/sandbox/workspace/plan.json",
        "--setenv", "ASTROX_BENCHMARK_TYPE", benchmark,
        "--setenv", "ASTROX_HORIZON_START", horizon_start,
        "--setenv", "ASTROX_HORIZON_END", horizon_end,
    ])
    
    return cmd


def build_systemd_wrapper(memory_limit: str | None = None, cpu_quota: str | None = None) -> list[str]:
    """Build systemd-run wrapper for resource limits.
    
    Args:
        memory_limit: Memory limit (e.g., "4G", "2048M")
        cpu_quota: CPU quota as percentage (e.g., "50%", "200%")
    
    Returns:
        List of systemd-run command arguments
    """
    if not memory_limit and not cpu_quota:
        return []
    
    cmd = [
        "systemd-run",
        "--user",
        "--scope",
        "--quiet",
    ]
    
    if memory_limit:
        cmd.extend(["-p", f"MemoryMax={memory_limit}"])
    
    if cpu_quota:
        cmd.extend(["-p", f"CPUQuota={cpu_quota}"])
    
    # Add reasonable task limit to prevent fork bombs
    cmd.extend(["-p", "TasksMax=1000"])
    
    return cmd


def run_agent(
    sandbox_dir: Path,
    benchmark: str,
    case_id: str,
    model: str,
    interactive: bool,
    timeout: int,
    output_dir: Path,
    use_bwrap: bool = False,
    debug: bool = False,
    memory_limit: str | None = None,
    cpu_quota: str | None = None,
) -> int:
    """Run the agent in sandbox."""
    env = os.environ.copy()
    
    # Get case metadata for environment variables
    benchmark_slug = benchmark.replace("-", "_")
    case_data_dir = BENCHMARK_DATA_DIR / benchmark_slug / "dataset" / case_id
    manifest_path = case_data_dir / "manifest.json"
    
    if manifest_path.exists():
        with open(manifest_path) as f:
            manifest = json.load(f)
            horizon_start = manifest.get("horizon_start", "2024-01-01T00:00:00Z")
            horizon_end = manifest.get("horizon_end", "2024-01-02T00:00:00Z")
    else:
        horizon_start = "2024-01-01T00:00:00Z"
        horizon_end = "2024-01-02T00:00:00Z"
    
    # Astrox-specific env vars
    env.update({
        "CASE_PATH": str(sandbox_dir / "data"),
        "ASTROX_STATE_PATH": str(sandbox_dir / "state" / "scenario.json"),
        "ASTROX_CASE_PATH": str(sandbox_dir / "data"),
        "ASTROX_OUTPUT_PATH": str(sandbox_dir / "workspace" / "plan.json"),
        "ASTROX_BENCHMARK_TYPE": benchmark,
        "ASTROX_HORIZON_START": horizon_start,
        "ASTROX_HORIZON_END": horizon_end,
        "HOME": str(sandbox_dir),
        "PYTHONPATH": str(sandbox_dir / "lib"),
    })
    
    # Set PATH to include venv if we're in one (critical for MCP server to use correct Python)
    is_venv = sys.prefix != sys.base_prefix
    if is_venv:
        env["PATH"] = f"{sys.prefix}/bin:{sandbox_dir}/.local/bin:{os.environ.get('PATH', '')}"
    else:
        env["PATH"] = f"{sandbox_dir}/.local/bin:{os.environ.get('PATH', '')}"

    
    # Model routing env vars
    print(f"Configuring model: {model}")
    model_env = configure_model_env(model)
    env.update(model_env)
    
    print(f"  ANTHROPIC_MODEL: {model_env.get('ANTHROPIC_MODEL', model)}")
    if "ANTHROPIC_BASE_URL" in model_env:
        print(f"  ANTHROPIC_BASE_URL: {model_env['ANTHROPIC_BASE_URL']}")
    
    # Resource limits
    if memory_limit or cpu_quota:
        print(f"Resource limits:")
        if memory_limit:
            print(f"  Memory: {memory_limit}")
        if cpu_quota:
            print(f"  CPU: {cpu_quota}")
    
    # Isolation
    if use_bwrap:
        print(f"Filesystem isolation: enabled (bwrap)")
    
    log_path = output_dir / "agent.log"
    cwd = sandbox_dir / "workspace"
    
    # Build command layers (outer to inner: systemd-run -> bwrap -> claude)
    base_cmd = []
    
    # Layer 1: systemd-run wrapper (resource limits)
    systemd_wrapper = build_systemd_wrapper(memory_limit, cpu_quota)
    if systemd_wrapper:
        base_cmd.extend(systemd_wrapper)
    
    # Layer 2: bwrap (filesystem isolation)
    if use_bwrap:
        bwrap_cmd = build_bwrap_command(sandbox_dir, benchmark, case_id)
        base_cmd.extend(bwrap_cmd)
        base_cmd.extend(["--", "claude"])
    else:
        base_cmd.append("claude")
    
    if debug:
        base_cmd.append("--debug")
    
    prompt = "Read mission_brief.md and start planning to satisfy the mission objectives."
    
    if interactive:
        cmd = base_cmd + [prompt]
        return subprocess.run(cmd, env=env, cwd=cwd).returncode
    else:
        cmd = base_cmd + ["-p", prompt]
        
        exit_code = 0
        with open(log_path, "w") as log_file:
            try:
                result = subprocess.run(
                    cmd,
                    env=env,
                    cwd=cwd,
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    timeout=timeout,
                )
                exit_code = result.returncode
            except subprocess.TimeoutExpired:
                log_file.write(f"\n\n--- TIMEOUT after {timeout} seconds ---\n")
                exit_code = -1
        
        # Save summary to workspace
        try:
            summary_path = sandbox_dir / "workspace" / "summary.md"
            shutil.copy2(log_path, summary_path)
        except Exception as e:
            print(f"Warning: Failed to save summary.md: {e}")
        
        return exit_code


def run_baseline(benchmark: str, case_id: str, algorithm: str, output_dir: Path) -> int:
    """Execute baseline algorithm."""
    benchmark_slug = benchmark.replace("-", "_")
    baseline_script = PROJECT_ROOT / "benchmarks" / benchmark_slug / "baselines" / f"{algorithm}.py"
    
    if not baseline_script.exists():
        print(f"ERROR: Baseline script not found: {baseline_script}")
        return 1
    
    case_data_dir = BENCHMARK_DATA_DIR / benchmark_slug / "dataset" / case_id
    plan_output = output_dir / "plan.json"
    
    cmd = [
        sys.executable,
        str(baseline_script),
        "--case-dir", str(case_data_dir),
        "--output", str(plan_output),
    ]
    
    print(f"Running baseline: {algorithm}")
    result = subprocess.run(cmd, cwd=PROJECT_ROOT)
    return result.returncode


def score_result(benchmark: str, sandbox_dir: Path, case_id: str) -> dict[str, Any]:
    """Score the plan using the benchmark-specific verifier."""
    workspace_dir = sandbox_dir / "workspace"
    plan_path = workspace_dir / "plan.json"
    
    if not plan_path.exists():
        return {
            "valid": False,
            "error": "No plan.json found in workspace/",
        }
    
    benchmark_slug = benchmark.replace("-", "_")
    verifier_module = f"benchmarks.{benchmark_slug}.verifier"
    
    try:
        import importlib
        verifier = importlib.import_module(verifier_module)
        
        benchmark_slug = benchmark.replace("-", "_")
        case_data_dir = BENCHMARK_DATA_DIR / benchmark_slug / "dataset" / case_id
        
        score = verifier.score_plan(
            plan_path=str(plan_path),
            case_dir=str(case_data_dir),
        )
        
        return {
            "valid": True,
            "score": score,
        }
    except Exception as e:
        return {
            "valid": False,
            "error": f"Verifier failed: {str(e)}",
        }


def extract_key_metrics(benchmark: str, score_data: dict) -> dict[str, Any]:
    """Extract benchmark-specific key metrics from verifier output."""
    if not score_data.get("valid"):
        return {"error": score_data.get("error", "Unknown error")}
    
    metrics = score_data.get("score", {}).get("metrics", {})
    
    if benchmark == "revisit-optimization":
        gap_stats = metrics.get("gap_statistics", {})
        max_gaps = [t["max_gap_hours"] for t in gap_stats.values() if t]
        min_gaps = [t["min_gap_hours"] for t in gap_stats.values() if t]
        avg_gaps = [t["avg_gap_hours"] for t in gap_stats.values() if t]
        
        return {
            "target_coverage_ratio": metrics.get("target_coverage", 0.0),
            "avg_max_gap_hours": sum(max_gaps) / len(max_gaps) if max_gaps else None,
            "avg_min_gap_hours": sum(min_gaps) / len(min_gaps) if min_gaps else None,
            "avg_avg_gap_hours": sum(avg_gaps) / len(avg_gaps) if avg_gaps else None,
        }
    
    elif benchmark == "stereo-imaging":
        return {
            "stereo_coverage_ratio": metrics.get("stereo_coverage", 0.0),
        }
    
    elif benchmark == "latency-optimization":
        latency_stats = metrics.get("latency_statistics", {})
        max_latencies = [s["latency_max_ms"] for s in latency_stats.values() if s and s.get("latency_max_ms") is not None]
        min_latencies = [s["latency_min_ms"] for s in latency_stats.values() if s and s.get("latency_min_ms") is not None]
        mean_latencies = [s["latency_mean_ms"] for s in latency_stats.values() if s and s.get("latency_mean_ms") is not None]
        
        return {
            "target_coverage_ratio": metrics.get("target_coverage", 0.0),
            "connection_coverage": metrics.get("connection_coverage", 0.0),
            "avg_max_latency_ms": sum(max_latencies) / len(max_latencies) if max_latencies else None,
            "avg_min_latency_ms": sum(min_latencies) / len(min_latencies) if min_latencies else None,
            "avg_mean_latency_ms": sum(mean_latencies) / len(mean_latencies) if mean_latencies else None,
        }
    
    elif benchmark == "regional-coverage":
        polygon_coverage = metrics.get("polygon_coverage", {})
        coverages = [p["coverage_percentage"] for p in polygon_coverage.values()]
        
        return {
            "mean_coverage_ratio": sum(coverages) / len(coverages) / 100.0 if coverages else 0.0,
        }
    
    return {}


def run_single_case(
    benchmark: str,
    case_id: str,
    model: str,
    output_dir: Path,
    interactive: bool,
    timeout: int,
    baseline: str | None,
    use_bwrap: bool = False,
    debug: bool = False,
    memory_limit: str | None = None,
    cpu_quota: str | None = None,
    retry_on_invalid: bool = False,
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> dict[str, Any]:
    """Run a single benchmark case with optional retry on invalid plans."""
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"\n{'='*60}")
    print(f"Astrox Benchmark: {benchmark} / {case_id}")
    print(f"Model: {model if not baseline else f'Baseline: {baseline}'}")
    print(f"Output: {output_dir}")
    if retry_on_invalid and not baseline:
        print(f"Retry on invalid: enabled (max {max_retries} retries)")
    print(f"{'='*60}")
    
    attempt = 0
    attempts_metadata = []
    
    while attempt <= max_retries:
        if attempt > 0:
            print(f"\n{'~'*60}")
            print(f"RETRY ATTEMPT {attempt}/{max_retries}")
            print(f"{'~'*60}")
        
        attempt_start = time.time()
        
        if baseline:
            exit_code = run_baseline(benchmark, case_id, baseline, output_dir)
            sandbox_dir = None
        else:
            if attempt == 0:
                print("Setting up sandbox...")
                sandbox_dir = setup_sandbox(benchmark, case_id, output_dir)
            else:
                print("Cleaning up previous attempt...")
                workspace_dir = sandbox_dir / "workspace"
                state_dir = sandbox_dir / "state"
                
                for path in [workspace_dir / "plan.json", state_dir / "scenario.json"]:
                    if path.exists():
                        path.unlink()
                
                for item in workspace_dir.iterdir():
                    if item.name not in ["mission_brief.md", "engine", "planner", ".claude", ".mcp.json"]:
                        if item.is_file():
                            item.unlink()
                        elif item.is_dir():
                            shutil.rmtree(item)
            
            if interactive:
                print("\nLaunching interactive session...")
                print("Sandbox:", sandbox_dir)
                run_agent(
                    sandbox_dir, benchmark, case_id, model,
                    interactive=True, timeout=timeout,
                    output_dir=output_dir, use_bwrap=use_bwrap,
                    debug=debug, memory_limit=memory_limit,
                    cpu_quota=cpu_quota,
                )
                return {"mode": "interactive"}
            
            print("Running agent...")
            exit_code = run_agent(
                sandbox_dir, benchmark, case_id, model,
                interactive=False, timeout=timeout,
                output_dir=output_dir, use_bwrap=use_bwrap,
                debug=debug, memory_limit=memory_limit,
                cpu_quota=cpu_quota,
            )
        
        attempt_elapsed = time.time() - attempt_start
        print(f"Attempt {attempt} finished in {attempt_elapsed:.1f}s with exit code {exit_code}")
        
        print("Scoring result...")
        score = score_result(benchmark, sandbox_dir if sandbox_dir else output_dir, case_id)
        
        attempts_metadata.append({
            "attempt": attempt,
            "exit_code": exit_code,
            "elapsed_seconds": round(attempt_elapsed, 2),
            "valid": score.get("valid", False),
        })
        
        if score.get("valid") or not retry_on_invalid or baseline or attempt >= max_retries:
            total_elapsed = time.time() - (attempt_start - attempt_elapsed + attempts_metadata[0]["elapsed_seconds"])
            break
        
        print(f"Plan is invalid. Retrying... ({attempt + 1}/{max_retries})")
        attempt += 1
    
    total_elapsed = sum(a["elapsed_seconds"] for a in attempts_metadata)
    
    total_elapsed = sum(a["elapsed_seconds"] for a in attempts_metadata)
    
    key_metrics = extract_key_metrics(benchmark, score)
    
    result = {
        "benchmark": benchmark,
        "case_id": case_id,
        "model": model if not baseline else None,
        "baseline": baseline,
        "exit_code": exit_code,
        "elapsed_seconds": round(total_elapsed, 2),
        "attempts": len(attempts_metadata),
        "attempts_metadata": attempts_metadata,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "key_metrics": key_metrics,
        **score,
    }
    
    metrics_path = output_dir / "metrics.json"
    with open(metrics_path, "w") as f:
        json.dump(result, f, indent=2)
    
    metrics_txt_path = output_dir / "metrics.txt"
    with open(metrics_txt_path, "w") as f:
        f.write(f"Benchmark: {benchmark}\n")
        f.write(f"Case: {case_id}\n")
        f.write(f"Model: {model if not baseline else f'Baseline-{baseline}'}\n")
        f.write(f"Valid: {score.get('valid', 'N/A')}\n")
        f.write(f"Run time: {result['elapsed_seconds']}s\n")
        f.write("-" * 40 + "\n")
        
        if key_metrics.get("error"):
            f.write(f"Error: {key_metrics['error']}\n")
        else:
            for key, value in key_metrics.items():
                if value is not None:
                    f.write(f"{key}: {value}\n")
    
    # Append to benchmark-specific global log
    log_name = f"{benchmark.split('-')[0]}_metrics.txt"
    global_metrics_path = PROJECT_ROOT / log_name
    with open(global_metrics_path, "a") as f:
        header = f"[{result['timestamp']}] Case: {case_id}"
        if baseline:
            header += f", Baseline: {baseline}"
        else:
            header += f", Model: {model}"
        f.write(header + "\n")
        
        f.write(f"Valid: {score.get('valid', 'N/A')}\n")
        f.write(f"Run time: {result['elapsed_seconds']}s\n")
        
        if key_metrics.get("error"):
            f.write(f"Error: {key_metrics['error']}\n")
        else:
            for key, value in key_metrics.items():
                if value is not None:
                    f.write(f"{key}: {value}\n")
        
        f.write("-" * 60 + "\n")
    
    print(f"\nResults:")
    print(f"  Benchmark: {benchmark}")
    print(f"  Case: {case_id}")
    print(f"  Valid: {score.get('valid', 'N/A')}")
    
    if score.get('error'):
        print(f"  Error: {score['error']}")
    elif key_metrics.get("error"):
        print(f"  Error: {key_metrics['error']}")
    else:
        print(f"  Runtime: {result['elapsed_seconds']}s")
        print(f"\n  Key Metrics:")
        for key, value in key_metrics.items():
            if value is not None:
                if "ratio" in key and isinstance(value, float):
                    print(f"    {key}: {value:.4f}")
                elif isinstance(value, float):
                    print(f"    {key}: {value:.2f}")
                else:
                    print(f"    {key}: {value}")
    
    if score.get('score', {}).get('violations'):
        violations = score['score']['violations']
        print(f"\n  Violations ({len(violations)}):")
        for v in violations[:3]:
            print(f"    - {v}")
        if len(violations) > 3:
            print(f"    ... and {len(violations) - 3} more")
    
    print(f"  Metrics appended to: {global_metrics_path}")
    
    return result


def load_experiment_config(config_path: Path) -> dict[str, Any]:
    """Load experiment configuration from JSON or YAML file."""
    if not config_path.exists():
        raise FileNotFoundError(f"Experiment config not found: {config_path}")
    
    with open(config_path) as f:
        if config_path.suffix in [".yaml", ".yml"]:
            try:
                import yaml
                config = yaml.safe_load(f)
            except ImportError:
                raise ImportError("PyYAML is required for YAML config files. Install with: pip install pyyaml")
        else:
            config = json.load(f)
    
    required_fields = ["benchmark", "models"]
    for field in required_fields:
        if field not in config:
            raise ValueError(f"Missing required field in experiment config: {field}")
    
    return config


def run_experiment_batch(
    benchmark: str,
    models: list[str],
    cases: list[str] | None,
    output_dir: Path,
    timeout: int,
    use_bwrap: bool = False,
    debug: bool = False,
    memory_limit: str | None = None,
    cpu_quota: str | None = None,
    retry_on_invalid: bool = False,
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> dict[str, Any]:
    """Run experiments across multiple models and cases."""
    
    benchmark_slug = benchmark.replace("-", "_")
    case_dir = BENCHMARK_DATA_DIR / benchmark_slug / "dataset"
    
    if not case_dir.exists():
        raise ValueError(f"Benchmark directory not found: {case_dir}")
    
    if cases is None:
        cases = sorted([d.name for d in case_dir.iterdir() if d.is_dir() and d.name.startswith("case_")])
    
    if not cases:
        raise ValueError(f"No cases found in {case_dir}")
    
    print(f"\n{'#'*60}")
    print(f"EXPERIMENT BATCH")
    print(f"Benchmark: {benchmark}")
    print(f"Models: {', '.join(models)}")
    print(f"Cases: {len(cases)} cases")
    print(f"Total runs: {len(models) * len(cases)}")
    print(f"{'#'*60}\n")
    
    all_results = []
    experiment_start = time.time()
    
    for model_idx, model in enumerate(models, 1):
        print(f"\n{'#'*60}")
        print(f"MODEL {model_idx}/{len(models)}: {model}")
        print(f"{'#'*60}")
        
        model_slug = model.replace("/", "__")
        model_output_dir = output_dir / benchmark / model_slug
        
        model_results = []
        
        for case_idx, case_id in enumerate(cases, 1):
            print(f"\n[Model {model_idx}/{len(models)}, Case {case_idx}/{len(cases)}]")
            
            case_output = model_output_dir / case_id
            
            result = run_single_case(
                benchmark=benchmark,
                case_id=case_id,
                model=model,
                output_dir=case_output,
                interactive=False,
                timeout=timeout,
                baseline=None,
                use_bwrap=use_bwrap,
                debug=debug,
                memory_limit=memory_limit,
                cpu_quota=cpu_quota,
                retry_on_invalid=retry_on_invalid,
                max_retries=max_retries,
            )
            
            model_results.append(result)
            all_results.append(result)
        
        model_summary_path = model_output_dir / "summary.json"
        model_summary_path.parent.mkdir(parents=True, exist_ok=True)
        with open(model_summary_path, "w") as f:
            json.dump(model_results, f, indent=2)
        
        valid_count = sum(1 for r in model_results if r.get("valid", False))
        print(f"\nModel {model} summary: {valid_count}/{len(model_results)} valid plans")
    
    experiment_elapsed = time.time() - experiment_start
    
    experiment_summary = {
        "benchmark": benchmark,
        "models": models,
        "total_cases": len(cases),
        "total_runs": len(all_results),
        "experiment_elapsed_seconds": round(experiment_elapsed, 2),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "results": all_results,
    }
    
    summary_path = output_dir / benchmark / "experiment_summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    with open(summary_path, "w") as f:
        json.dump(experiment_summary, f, indent=2)
    
    print(f"\n{'#'*60}")
    print(f"EXPERIMENT COMPLETE")
    print(f"Total time: {experiment_elapsed:.1f}s")
    print(f"Total runs: {len(all_results)}")
    print(f"Valid plans: {sum(1 for r in all_results if r.get('valid', False))}/{len(all_results)}")
    print(f"Summary: {summary_path}")
    print(f"{'#'*60}\n")
    
    return experiment_summary


def main():
    parser = argparse.ArgumentParser(
        description="Astrox Benchmark Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Model routing (new format: provider::model_id):
  anthropic::model_id    Anthropic (default, needs ANTHROPIC_API_KEY)
  deepseek::model_id     DeepSeek API (needs DEEPSEEK_API_KEY)
  qwen::model_id         Alibaba DashScope (needs DASHSCOPE_API_KEY)
  minimax::model_id      MiniMax (needs MINIMAX_API_KEY)
  glm::model_id          Zhipu AI (needs ZHIPU_API_KEY)
  moonshot::model_id     Moonshot AI (needs MOONSHOT_API_KEY)
  openrouter::model_id   OpenRouter (needs OPENROUTER_API_KEY)
  lingleap::model_id     LingLeap (needs LINGLEAP_API_KEY)

Legacy format (still supported):
  claude-*           Anthropic
  deepseek*          DeepSeek API
  qwen*              Alibaba DashScope
  minimax*           MiniMax
  glm*               Zhipu AI
  kimi*, moonshot*   Moonshot AI
  provider/model     OpenRouter

Examples:
  # Single case, single model (new format)
  python -m toolkit.agents.runner --benchmark revisit-optimization --case case_0001 --model anthropic::claude-sonnet-4-20250514
  
  # All cases, single model
  python -m toolkit.agents.runner --benchmark stereo-imaging --all --model deepseek::deepseek-reasoner
  
  # All cases, multiple models
  python -m toolkit.agents.runner --benchmark revisit-optimization --all --models anthropic::claude-sonnet-4 deepseek::deepseek-reasoner
  
  # With retry on invalid plans
  python -m toolkit.agents.runner --benchmark stereo-imaging --all --model anthropic::claude-sonnet-4 --retry-on-invalid --max-retries 2
  
  # Baseline algorithm
  python -m toolkit.agents.runner --benchmark revisit-optimization --case case_0001 --baseline greedy
  
  # From experiment config
  python -m toolkit.agents.runner --experiment-config experiments/my_experiment.json
  
  # With resource limits
  python -m toolkit.agents.runner --benchmark latency-optimization --case case_0001 --bwrap --memory-limit 4G --cpu-quota 200%%
  
  # Legacy format (still works)
  python -m toolkit.agents.runner --benchmark revisit-optimization --case case_0001 --model claude-sonnet-4-20250514
        """
    )
    parser.add_argument("--benchmark", choices=BENCHMARKS, help="Benchmark type")
    parser.add_argument("--case", help="Case ID (e.g., case_0001)")
    parser.add_argument("--all", action="store_true", help="Run all cases in the benchmark")
    parser.add_argument("--model", type=str, default="anthropic::claude-sonnet-4-20250514", help="Model name (format: provider::model_id)")
    parser.add_argument("--models", nargs="+", help="Multiple models to run experiments on")
    parser.add_argument("--baseline", help="Baseline algorithm (e.g., greedy, simulated_annealing)")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="Output directory")
    parser.add_argument("--interactive", action="store_true", help="Launch interactive session")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="Timeout in seconds")
    parser.add_argument("--bwrap", action="store_true", help="Use bwrap for additional isolation")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument("--memory-limit", type=str, help="Memory limit (e.g., 4G, 2048M)")
    parser.add_argument("--cpu-quota", type=str, help="CPU quota (e.g., 50%%, 200%%)")
    parser.add_argument("--retry-on-invalid", action="store_true", help="Retry if plan is invalid")
    parser.add_argument("--max-retries", type=int, default=DEFAULT_MAX_RETRIES, help="Maximum number of retries")
    parser.add_argument("--experiment-config", type=Path, help="Path to experiment configuration file (JSON/YAML)")
    
    args = parser.parse_args()
    
    # Mode 1: Experiment config file
    if args.experiment_config:
        config = load_experiment_config(args.experiment_config)
        
        benchmark = config["benchmark"]
        models = config["models"]
        cases = config.get("dataset")
        timeout = config.get("timeout", args.timeout)
        use_bwrap = config.get("use_bwrap", args.bwrap)
        debug = config.get("debug", args.debug)
        memory_limit = config.get("memory_limit", args.memory_limit)
        cpu_quota = config.get("cpu_quota", args.cpu_quota)
        retry_on_invalid = config.get("retry_on_invalid", args.retry_on_invalid)
        max_retries = config.get("max_retries", args.max_retries)
        output_dir = Path(config.get("output_dir", args.output_dir))
        
        run_experiment_batch(
            benchmark=benchmark,
            models=models,
            cases=cases,
            output_dir=output_dir,
            timeout=timeout,
            use_bwrap=use_bwrap,
            debug=debug,
            memory_limit=memory_limit,
            cpu_quota=cpu_quota,
            retry_on_invalid=retry_on_invalid,
            max_retries=max_retries,
        )
        return
    
    # Mode 2 & 3: Command-line arguments
    if not args.benchmark:
        parser.error("--benchmark is required when not using --experiment-config")
    
    if not args.case and not args.all:
        parser.error("Must specify --case or --all")
    
    if args.baseline and args.interactive:
        parser.error("Cannot use --baseline with --interactive")
    
    if args.models and args.interactive:
        parser.error("Cannot use --models with --interactive")
    
    if args.models and args.baseline:
        parser.error("Cannot use --models with --baseline")
    
    if args.retry_on_invalid and args.baseline:
        parser.error("Cannot use --retry-on-invalid with --baseline")
    
    # Mode 2: Multi-model batch execution
    if args.models:
        if not args.all:
            parser.error("--models requires --all (cannot run multiple models on a single case)")
        
        cases = None
        
        run_experiment_batch(
            benchmark=args.benchmark,
            models=args.models,
            cases=cases,
            output_dir=args.output_dir,
            timeout=args.timeout,
            use_bwrap=args.bwrap,
            debug=args.debug,
            memory_limit=args.memory_limit,
            cpu_quota=args.cpu_quota,
            retry_on_invalid=args.retry_on_invalid,
            max_retries=args.max_retries,
        )
        return
    
    # Mode 3: Single model execution (original behavior)
    if args.baseline:
        run_slug = f"baseline_{args.baseline}"
    else:
        model_slug = args.model.replace("/", "__")
        run_slug = model_slug
    
    base_output = args.output_dir / args.benchmark / run_slug
    
    if args.all:
        benchmark_slug = args.benchmark.replace("-", "_")
        case_dir = BENCHMARK_DATA_DIR / benchmark_slug / "dataset"
        
        if not case_dir.exists():
            print(f"ERROR: Benchmark directory not found: {case_dir}")
            sys.exit(1)
        
        cases = sorted([d.name for d in case_dir.iterdir() if d.is_dir() and d.name.startswith("case_")])
        
        if not cases:
            print(f"ERROR: No cases found in {case_dir}")
            sys.exit(1)
        
        results = []
        for case_id in cases:
            case_output = base_output / case_id
            result = run_single_case(
                benchmark=args.benchmark,
                case_id=case_id,
                model=args.model,
                output_dir=case_output,
                interactive=False,
                timeout=args.timeout,
                baseline=args.baseline,
                use_bwrap=args.bwrap,
                debug=args.debug,
                memory_limit=args.memory_limit,
                cpu_quota=args.cpu_quota,
                retry_on_invalid=args.retry_on_invalid,
                max_retries=args.max_retries,
            )
            results.append(result)
        
        summary_path = base_output / "summary.json"
        with open(summary_path, "w") as f:
            json.dump(results, f, indent=2)
        print(f"\nSummary written to {summary_path}")
    else:
        case_output = base_output / args.case
        run_single_case(
            benchmark=args.benchmark,
            case_id=args.case,
            model=args.model,
            output_dir=case_output,
            interactive=args.interactive,
            timeout=args.timeout,
            baseline=args.baseline,
            use_bwrap=args.bwrap,
            debug=args.debug,
            memory_limit=args.memory_limit,
            cpu_quota=args.cpu_quota,
            retry_on_invalid=args.retry_on_invalid,
            max_retries=args.max_retries,
        )


if __name__ == "__main__":
    main()
