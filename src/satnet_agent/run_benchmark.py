#!/usr/bin/env python3
"""SatNet Benchmark Runner.

Sets up a sandbox environment and runs an LLM agent on DSN scheduling tasks.

Usage:
    ./run_benchmark.py --week 40 --model anthropic::claude-sonnet-4-20250514
    ./run_benchmark.py --week 40 --model deepseek::deepseek-reasoner --interactive
    ./run_benchmark.py --all --model anthropic::claude-sonnet-4-20250514
    ./run_benchmark.py --week 40 --bwrap --memory-limit 4G --cpu-quota 200%

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
# Add src to python path so we can import satnet_agent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

SATNET_DIR = PROJECT_ROOT / "satnet"
SANDBOX_TEMPLATE = Path(__file__).parent / "sandbox_template"
SATNET_DATA_DIR = SATNET_DIR / "data"
MISSION_BRIEF_TEMPLATE = Path(__file__).parent / "templates" / "mission_brief.md.template"

WEEKS = [10, 20, 30, 40, 50]
DEFAULT_TIMEOUT = 3600
DEFAULT_OUTPUT_DIR = Path("/tmp/satnet_benchmark")


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
        "base_url": "https://dashscope.aliyuncs.com/apps/anthropic",
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


def get_week_stats(problems_path: Path, week: int, year: int = 2018) -> dict[str, int]:
    """Get statistics for a week's problem."""
    with open(problems_path) as f:
        data = json.load(f)

    key = f"W{week}_{year}"
    requests = data[key]
    missions = set(r["subject"] for r in requests)

    return {
        "n_requests": len(requests),
        "n_missions": len(missions),
    }


def generate_mission_brief(week: int, year: int, output_path: Path) -> None:
    """Generate the mission brief from template."""
    template = MISSION_BRIEF_TEMPLATE.read_text()
    stats = get_week_stats(SATNET_DATA_DIR / "problems.json", week, year)

    brief = template.format(
        week=week,
        year=year,
        n_requests=stats["n_requests"],
        n_missions=stats["n_missions"],
    )

    output_path.write_text(brief)


def setup_sandbox(week: int, year: int, output_dir: Path, include_related_works: bool = False) -> Path:
    """Create sandbox by copying template and generating dynamic files.
    
    Structure (after setup):
        sandbox/
        ├── .claude/           # Global settings + CLAUDE.md
        │   ├── settings.json
        │   └── CLAUDE.md
        ├── .local/            # -> symlink to ~/.local (claude CLI)
        ├── lib/               # MCP library only (via uv pip install)
        ├── data/              # -> symlink to satnet/data
        ├── state/             # Runtime state directory
        └── workspace/         # Agent's working directory
            ├── satnet_agent/  # Source code copy (agent can import/edit)
            ├── mcp_server.py  # MCP server entry point
            ├── mission_brief.md  # Generated per-week
            └── related_works/ # Optional: research papers (if include_related_works=True)
    """
    sandbox_dir = output_dir / "sandbox"

    if sandbox_dir.exists():
        shutil.rmtree(sandbox_dir)

    shutil.copytree(SANDBOX_TEMPLATE, sandbox_dir, symlinks=True)

    # Fix data symlink to be absolute, as relative links break when copied
    data_link = sandbox_dir / "data"
    if data_link.is_symlink() or data_link.exists():
        data_link.unlink()
    data_link.symlink_to(SATNET_DATA_DIR.resolve())

    generate_mission_brief(week, year, sandbox_dir / "workspace" / "mission_brief.md")
    
    # Optionally copy related works
    if include_related_works:
        related_works_src = Path(__file__).parent / "related_works"
        if related_works_src.exists():
            related_works_dst = sandbox_dir / "workspace" / "related_works"
            shutil.copytree(related_works_src, related_works_dst)
            print(f"  Copied related_works to workspace")

    return sandbox_dir


def build_bwrap_command(sandbox_dir: Path, week: int, year: int) -> list[str]:
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
        # Note: .local is bound below to preserve absolute paths
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
    # This ensures that symlinks inside .local which relying on typical home layout work
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

    cmd.extend([
        # SatNet-specific env vars
        "--setenv", "SATNET_STATE_PATH", "/sandbox/state/scenario.json",
        "--setenv", "SATNET_PROBLEMS_PATH", "/sandbox/data/problems.json",
        "--setenv", "SATNET_MAINTENANCE_PATH", "/sandbox/data/maintenance.csv",
        "--setenv", "SATNET_WEEK", str(week),
        "--setenv", "SATNET_YEAR", str(year),
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
    week: int,
    year: int,
    model: str,
    interactive: bool,
    timeout: int,
    output_dir: Path,
    use_bwrap: bool = False,
    debug: bool = False,
    memory_limit: str | None = None,
    cpu_quota: str | None = None,
    include_related_works: bool = False,
) -> int:
    """Run the agent in sandbox."""
    env = os.environ.copy()
    
    # SatNet-specific env vars
    env.update({
        "SATNET_STATE_PATH": str(sandbox_dir / "state" / "scenario.json"),
        "SATNET_PROBLEMS_PATH": str(sandbox_dir / "data" / "problems.json"),
        "SATNET_MAINTENANCE_PATH": str(sandbox_dir / "data" / "maintenance.csv"),
        "SATNET_WEEK": str(week),
        "SATNET_YEAR": str(year),
        "SATNET_OUTPUT_PATH": str(sandbox_dir / "workspace" / "plan.json"),
        "HOME": str(sandbox_dir),
        "PYTHONPATH": str(sandbox_dir / "lib"),
        "PATH": f"{sandbox_dir}/.local/bin:{os.environ.get('PATH', '')}",
    })
    
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
        bwrap_cmd = build_bwrap_command(sandbox_dir, week, year)
        base_cmd.extend(bwrap_cmd)
        base_cmd.extend(["--", "claude"])
    else:
        base_cmd.append("claude")

    if debug:
        base_cmd.append("--debug")

    # Skip permissions only when using bwrap in non-interactive mode
    # Or maybe we don't need it actually
    # if use_bwrap and not interactive:
    #     base_cmd.append("--dangerously-skip-permissions")

    prompt = "Read mission_brief.md and then create a schedule that minimizes unfairness."
    
    if include_related_works:
        prompt += " Note: The related_works/ folder contains research papers that may provide useful insights and approaches."

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


def score_result(sandbox_dir: Path, week: int, year: int) -> dict[str, Any]:
    """Score all *.json files in workspace/ and select the best one."""
    workspace_dir = sandbox_dir / "workspace"
    json_files = list(workspace_dir.glob("*.json"))
    
    if not json_files:
        return {
            "valid": False,
            "error": "No JSON files found in workspace/",
            "u_max": None,
            "u_rms": None,
        }
    
    try:
        from satnet_agent.scorer import score_plan_safe
    except ImportError:
        return {
            "valid": None,
            "error": "Scorer not available (satnet package not installed)",
            "u_max": None,
            "u_rms": None,
        }
    
    results = []
    for json_path in json_files:
        score = score_plan_safe(str(json_path), week, year)
        if score is not None:
            results.append({
                "file": json_path.name,
                "score": score,
                "u_max": score.u_max,
                "u_rms": score.u_rms,
            })
    
    if not results:
        return {
            "valid": False,
            "error": f"All {len(json_files)} JSON files are invalid",
            "u_max": None,
            "u_rms": None,
            "files_tried": [f.name for f in json_files],
        }
    
    best = min(results, key=lambda x: x["u_max"])
    score = best["score"]
    
    return {
        "valid": True,
        "u_max": score.u_max,
        "u_rms": score.u_rms,
        "u_avg": getattr(score, "u_avg", 0.0), # Safer access
        "requests_satisfied": score.requests_satisfied,
        "requests_total": score.requests_total,
        "hours_allocated": score.hours_allocated,
        "best_file": best["file"],
        "total_files_tried": len(json_files),
        "valid_files": len(results),
        "errors": score.errors[:5] if score.errors else [],
    }


def run_single_case(
    week: int,
    year: int,
    model: str,
    output_dir: Path,
    interactive: bool,
    timeout: int,
    use_bwrap: bool,
    debug: bool = False,
    memory_limit: str | None = None,
    cpu_quota: str | None = None,
    include_related_works: bool = False,
) -> dict[str, Any]:
    """Run a single benchmark case."""
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*60}")
    print(f"SatNet Benchmark: Week {week}, {year}")
    print(f"Model: {model}")
    print(f"Output: {output_dir}")
    if include_related_works:
        print(f"Related works: enabled")
    print(f"{'='*60}")

    start_time = time.time()

    print("Setting up sandbox...")
    sandbox_dir = setup_sandbox(week, year, output_dir, include_related_works=include_related_works)

    if interactive:
        print("\nLaunching interactive session...")
        print("Sandbox:", sandbox_dir)
        run_agent(
            sandbox_dir, week, year, model,
            interactive=True, timeout=timeout,
            output_dir=output_dir, use_bwrap=use_bwrap,
            debug=debug,
            memory_limit=memory_limit,
            cpu_quota=cpu_quota,
            include_related_works=include_related_works,
        )
        return {"mode": "interactive"}

    print("Running agent...")
    exit_code = run_agent(
        sandbox_dir, week, year, model,
        interactive=False, timeout=timeout,
        output_dir=output_dir, use_bwrap=use_bwrap,
        debug=debug,
        memory_limit=memory_limit,
        cpu_quota=cpu_quota,
        include_related_works=include_related_works,
    )

    elapsed = time.time() - start_time
    print(f"Agent finished in {elapsed:.1f}s with exit code {exit_code}")

    print("Scoring result...")
    score = score_result(sandbox_dir, week, year)

    result = {
        "week": week,
        "year": year,
        "model": model,
        "exit_code": exit_code,
        "elapsed_seconds": round(elapsed, 2),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **score,
    }

    metrics_path = output_dir / "metrics.json"
    with open(metrics_path, "w") as f:
        json.dump(result, f, indent=2)

    print(f"\nResults:")
    if score.get("errors"):
        print(f"  Errors: {score['errors']}")
    if score.get('best_file'):
        print(f"  Best file: {score['best_file']} ({score.get('valid_files', 0)}/{score.get('total_files_tried', 0)} valid)")
    print(f"  U_max: {score.get('u_max', 'N/A')}")
    print(f"  U_rms: {score.get('u_rms', 'N/A')}")
    print(f"  U_avg: {score.get('u_avg', 'N/A')}")
    print(f"  Valid: {score.get('valid', 'N/A')}")

    # Write localized metrics.txt
    metrics_txt_path = output_dir / "metrics.txt"
    with open(metrics_txt_path, "w") as f:
        f.write(f"U_max: {score.get('u_max', 'N/A')}\n")
        f.write(f"U_rms: {score.get('u_rms', 'N/A')}\n")
        f.write(f"U_avg: {score.get('u_avg', 'N/A')}\n")
        f.write(f"Run time: {result['elapsed_seconds']}s\n")
    
    # Append to global satnet_metrics.txt in project root
    global_metrics_path = PROJECT_ROOT / "satnet_metrics_0.txt"
    with open(global_metrics_path, "a") as f:
        f.write(f"[{result['timestamp']}] Model: {model}, Week: {week}, Year: {year}\n")
        f.write(f"U_max: {score.get('u_max', 'N/A')}\n")
        f.write(f"U_rms: {score.get('u_rms', 'N/A')}\n")
        f.write(f"U_avg: {score.get('u_avg', 'N/A')}\n")
        f.write(f"Run time: {result['elapsed_seconds']}s\n")
        f.write("-" * 40 + "\n")

    print(f"  Metrics appended to: {global_metrics_path}")

    return result


def run_experiment_batch(
    models: list[str],
    weeks: list[int] | None,
    year: int,
    output_dir: Path,
    timeout: int,
    use_bwrap: bool = False,
    debug: bool = False,
    memory_limit: str | None = None,
    cpu_quota: str | None = None,
    include_related_works: bool = False,
) -> dict[str, Any]:
    """Run experiments across multiple models and weeks."""
    
    if weeks is None:
        weeks = WEEKS
    
    print(f"\n{'#'*60}")
    print(f"EXPERIMENT BATCH")
    print(f"Models: {', '.join(models)}")
    print(f"Weeks: {weeks}")
    print(f"Total runs: {len(models) * len(weeks)}")
    print(f"{'#'*60}\n")
    
    all_results = []
    experiment_start = time.time()
    
    for model_idx, model in enumerate(models, 1):
        print(f"\n{'#'*60}")
        print(f"MODEL {model_idx}/{len(models)}: {model}")
        print(f"{'#'*60}")
        
        model_slug = model.replace("/", "__").replace("::", "__")
        model_output_dir = output_dir / model_slug
        
        model_results = []
        
        for week_idx, week in enumerate(weeks, 1):
            print(f"\n[Model {model_idx}/{len(models)}, Week {week_idx}/{len(weeks)}]")
            
            case_output = model_output_dir / f"w{week}"
            
            result = run_single_case(
                week=week,
                year=year,
                model=model,
                output_dir=case_output,
                interactive=False,
                timeout=timeout,
                use_bwrap=use_bwrap,
                debug=debug,
                memory_limit=memory_limit,
                cpu_quota=cpu_quota,
                include_related_works=include_related_works,
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
        "models": models,
        "weeks": weeks,
        "year": year,
        "total_runs": len(all_results),
        "experiment_elapsed_seconds": round(experiment_elapsed, 2),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "results": all_results,
    }
    
    summary_path = output_dir / "experiment_summary.json"
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


def load_config(config_path: Path) -> dict[str, Any]:
    """Load configuration from YAML file."""
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    
    with open(config_path) as f:
        if config_path.suffix in [".yaml", ".yml"]:
            try:
                import yaml
                config = yaml.safe_load(f)
            except ImportError:
                raise ImportError("PyYAML is required for YAML config files. Install with: pip install pyyaml")
        else:
            config = json.load(f)
    
    return config


def main():
    parser = argparse.ArgumentParser(
        description="SatNet Benchmark Runner",
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
  # Single week (new format)
  ./run_benchmark.py --week 40 --model anthropic::claude-sonnet-4-20250514
  
  # Interactive mode
  ./run_benchmark.py --week 40 --model deepseek::deepseek-reasoner --interactive
  
  # All weeks
  ./run_benchmark.py --all --model anthropic::claude-sonnet-4-20250514
  
  # With resource limits
  ./run_benchmark.py --week 40 --bwrap --memory-limit 4G --cpu-quota 200%%
  
  # From config file
  ./run_benchmark.py --config config/satnet_experiment.yaml
  
  # With related works (research papers)
  ./run_benchmark.py --week 40 --model anthropic::claude-sonnet-4-20250514 --related-works
  
  # Multiple models (all weeks)
  ./run_benchmark.py --all --models anthropic::claude-sonnet-4 deepseek::deepseek-reasoner lingleap::claude-sonnet-4
  
  # Legacy format (still works)
  ./run_benchmark.py --week 40 --model claude-sonnet-4-20250514
        """
    )
    parser.add_argument("--week", type=int, choices=WEEKS, help="Week number (10, 20, 30, 40, 50)")
    parser.add_argument("--year", type=int, default=2018, help="Year (default: 2018)")
    parser.add_argument("--model", type=str, default="anthropic::claude-sonnet-4-20250514", help="Model name (format: provider::model_id)")
    parser.add_argument("--models", nargs="+", help="Multiple models to run experiments on")
    parser.add_argument("--all", action="store_true", help="Run all 5 week cases")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="Output directory")
    parser.add_argument("--interactive", action="store_true", help="Launch interactive session")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="Timeout in seconds")
    parser.add_argument("--bwrap", action="store_true", help="Use bwrap for additional isolation")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument("--memory-limit", type=str, help="Memory limit (e.g., 4G, 2048M)")
    parser.add_argument("--cpu-quota", type=str, help="CPU quota (e.g., 50%%, 200%%)")
    parser.add_argument("--config", type=Path, help="Path to configuration file (YAML/JSON)")
    parser.add_argument("--related-works", action="store_true", help="Include related_works folder in workspace")

    args = parser.parse_args()
    
    # Mode 1: Config file
    if args.config:
        config = load_config(args.config)
        
        week = config.get("week")
        year = config.get("year", 2018)
        
        # Support both single model and multiple models
        models = config.get("models")
        if models:
            # Multi-model mode
            weeks_to_run = config.get("weeks") if config.get("weeks") else (WEEKS if config.get("all", False) else None)
            if not weeks_to_run and week:
                weeks_to_run = [week]
            
            output_dir = Path(config.get("output_dir", DEFAULT_OUTPUT_DIR))
            timeout = config.get("timeout", DEFAULT_TIMEOUT)
            use_bwrap = config.get("use_bwrap", False)
            debug = config.get("debug", False)
            memory_limit = config.get("memory_limit")
            cpu_quota = config.get("cpu_quota")
            include_related_works = config.get("related_works", False)
            
            run_experiment_batch(
                models=models,
                weeks=weeks_to_run,
                year=year,
                output_dir=output_dir,
                timeout=timeout,
                use_bwrap=use_bwrap,
                debug=debug,
                memory_limit=memory_limit,
                cpu_quota=cpu_quota,
                include_related_works=include_related_works,
            )
            return
        
        # Single model mode (backward compatibility)
        model = config["model"]
        all_weeks = config.get("all", False)
        output_dir = Path(config.get("output_dir", DEFAULT_OUTPUT_DIR))
        timeout = config.get("timeout", DEFAULT_TIMEOUT)
        use_bwrap = config.get("use_bwrap", False)
        debug = config.get("debug", False)
        memory_limit = config.get("memory_limit")
        cpu_quota = config.get("cpu_quota")
        include_related_works = config.get("related_works", False)
        
        model_slug = model.replace("/", "__").replace("::", "__")
        base_output = output_dir / model_slug
        
        if all_weeks:
            results = []
            for w in WEEKS:
                case_output = base_output / f"w{w}"
                result = run_single_case(
                    week=w,
                    year=year,
                    model=model,
                    output_dir=case_output,
                    interactive=False,
                    timeout=timeout,
                    use_bwrap=use_bwrap,
                    debug=debug,
                    memory_limit=memory_limit,
                    cpu_quota=cpu_quota,
                    include_related_works=include_related_works,
                )
                results.append(result)
            
            summary_path = base_output / "summary.json"
            with open(summary_path, "w") as f:
                json.dump(results, f, indent=2)
            print(f"\nSummary written to {summary_path}")
        else:
            if not week:
                parser.error("Config must specify 'week' or 'all: true'")
            case_output = base_output / f"w{week}"
            run_single_case(
                week=week,
                year=year,
                model=model,
                output_dir=case_output,
                interactive=False,
                timeout=timeout,
                use_bwrap=use_bwrap,
                debug=debug,
                memory_limit=memory_limit,
                cpu_quota=cpu_quota,
                include_related_works=include_related_works,
            )
        return
    
    # Mode 2: Multi-model batch execution
    if args.models:
        if not args.all:
            parser.error("--models requires --all (cannot run multiple models on a single week)")
        
        if args.interactive:
            parser.error("Cannot use --models with --interactive")
        
        run_experiment_batch(
            models=args.models,
            weeks=None,  # None means all weeks
            year=args.year,
            output_dir=args.output_dir,
            timeout=args.timeout,
            use_bwrap=args.bwrap,
            debug=args.debug,
            memory_limit=args.memory_limit,
            cpu_quota=args.cpu_quota,
            include_related_works=args.related_works,
        )
        return
    
    # Mode 3: Command-line arguments (single model)

    if not args.week and not args.all:
        parser.error("Must specify --week or --all")

    # Include model in output directory
    model_slug = args.model.replace("/", "__").replace("::", "__")
    base_output = args.output_dir / model_slug

    if args.all:
        results = []
        for week in WEEKS:
            case_output = base_output / f"w{week}"
            result = run_single_case(
                week=week,
                year=args.year,
                model=args.model,
                output_dir=case_output,
                interactive=False,
                timeout=args.timeout,
                use_bwrap=args.bwrap,
                debug=args.debug,
                memory_limit=args.memory_limit,
                cpu_quota=args.cpu_quota,
                include_related_works=args.related_works,
            )
            results.append(result)

        summary_path = base_output / "summary.json"
        with open(summary_path, "w") as f:
            json.dump(results, f, indent=2)
        print(f"\nSummary written to {summary_path}")
    else:
        case_output = base_output / f"w{args.week}"
        run_single_case(
            week=args.week,
            year=args.year,
            model=args.model,
            output_dir=case_output,
            interactive=args.interactive,
            timeout=args.timeout,
            use_bwrap=args.bwrap,
            debug=args.debug,
            memory_limit=args.memory_limit,
            cpu_quota=args.cpu_quota,
            include_related_works=args.related_works,
        )


if __name__ == "__main__":
    main()
