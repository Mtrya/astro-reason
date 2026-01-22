#!/usr/bin/env python3
"""SatNet Agentic Baseline Runner.

Sets up an isolated sandbox environment and runs an LLM agent on DSN scheduling tasks.

Usage:
    # Single case
    python benchmarks/satnet/baselines/agentic/run.py --case w10_2018 --model anthropic::claude-sonnet-4-20250514

    # All cases
    python benchmarks/satnet/baselines/agentic/run.py --case all --model anthropic::claude-sonnet-4-20250514

    # With retries
    python benchmarks/satnet/baselines/agentic/run.py --case w10_2018 --model anthropic::claude-sonnet-4-20250514 --max-retries 2

    # Non-interactive with dangerous skip (requires bwrap)
    python benchmarks/satnet/baselines/agentic/run.py --case w10_2018 --model anthropic::claude-sonnet-4-20250514 --dangerously-skip-permissions
"""

import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Project paths
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.parent
BENCHMARK_DIR = PROJECT_ROOT / "benchmarks" / "satnet"
DATASET_DIR = BENCHMARK_DIR / "dataset"
VERIFIER_PATH = BENCHMARK_DIR / "verifier.py"
AGENTIC_DIR = Path(__file__).parent

DEFAULT_TIMEOUT = 3600
DEFAULT_MAX_RETRIES = 0


# ---------------------------------------------------------------------------
# Provider configuration (simplified from mission_planner/runner.py)
# ---------------------------------------------------------------------------

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
    "openrouter": {
        "name": "OpenRouter",
        "base_url": "https://openrouter.ai/api",
        "api_key_env": "OPENROUTER_API_KEY",
    },
}


def configure_model_env(model: str) -> dict[str, str]:
    """Configure environment variables for model routing."""
    env = {}

    if "::" in model:
        provider, model_id = model.split("::", 1)
        provider = provider.lower()

        if provider not in PROVIDER_CONFIGS:
            raise ValueError(f"Unknown provider: {provider}")

        config = PROVIDER_CONFIGS[provider]
        env["ANTHROPIC_MODEL"] = model_id

        if config["base_url"]:
            env["ANTHROPIC_BASE_URL"] = config["base_url"]

        api_key = os.environ.get(config["api_key_env"], "")
        if api_key:
            env["ANTHROPIC_AUTH_TOKEN"] = api_key
    else:
        # Legacy format
        env["ANTHROPIC_MODEL"] = model

    return env


# ---------------------------------------------------------------------------
# Case parsing
# ---------------------------------------------------------------------------


def parse_case_id(case_str: str) -> tuple[int, int]:
    """Parse case string like 'w10_2018' into (week, year)."""
    case_str = case_str.lower()
    if not case_str.startswith("w"):
        raise ValueError(f"Invalid case format: {case_str}. Expected 'w{{week}}_{{year}}'")

    parts = case_str[1:].split("_")
    if len(parts) != 2:
        raise ValueError(f"Invalid case format: {case_str}. Expected 'w{{week}}_{{year}}'")

    try:
        week = int(parts[0])
        year = int(parts[1])
    except ValueError:
        raise ValueError(f"Invalid case format: {case_str}. Week and year must be integers.")

    return week, year


def get_all_cases() -> list[str]:
    """Get all case IDs from problems.json."""
    problems_path = DATASET_DIR / "problems.json"
    with open(problems_path) as f:
        data = json.load(f)

    cases = []
    for key in data.keys():
        # Convert W10_2018 -> w10_2018
        cases.append(key.lower())
    return sorted(cases)


# ---------------------------------------------------------------------------
# Prompt generation
# ---------------------------------------------------------------------------

def load_template(filename: str) -> str:
    """Load a template file from the agentic directory."""
    template_path = AGENTIC_DIR / filename
    return template_path.read_text()


def generate_mission_brief(week: int, year: int) -> str:
    """Generate the mission brief for the agent."""
    template = load_template("mission_brief_template.txt")
    return template.format(week=week, year=year)


# ---------------------------------------------------------------------------
# Sandbox setup
# ---------------------------------------------------------------------------


def setup_sandbox(week: int, year: int, output_dir: Path) -> Path:
    """Create sandbox directory with data and environment.

    Structure:
        sandbox/
        ├── workspace/
        │   ├── data/
        │   │   ├── problems.json
        │   │   └── maintenance.csv
        │   ├── mission.md
        │   └── verifier.py
        └── .claude/
            └── settings.json
    """
    sandbox_dir = output_dir / "sandbox"

    if sandbox_dir.exists():
        shutil.rmtree(sandbox_dir)

    sandbox_dir.mkdir(parents=True)

    # Create subdirectories
    workspace_dir = sandbox_dir / "workspace"
    data_dir = workspace_dir / "data"
    claude_dir = sandbox_dir / ".claude"

    workspace_dir.mkdir()
    data_dir.mkdir()
    claude_dir.mkdir()

    # Extract only the relevant case data from problems.json (not the full 3.5MB file)
    case_key = f"W{week}_{year}"
    with open(DATASET_DIR / "problems.json") as f:
        all_problems = json.load(f)

    if case_key not in all_problems:
        raise ValueError(f"Case key {case_key!r} not found in problems.json")

    case_problems = {case_key: all_problems[case_key]}
    (data_dir / "problems.json").write_text(json.dumps(case_problems, indent=2))

    # Filter maintenance.csv for the relevant week/year
    import csv
    maintenance_rows = []
    with open(DATASET_DIR / "maintenance.csv", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        for row in reader:
            try:
                row_week = int(float(row["week"]))
                row_year = int(row["year"])
                if row_week == week and row_year == year:
                    maintenance_rows.append(row)
            except (KeyError, ValueError):
                continue

    with open(data_dir / "maintenance.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(maintenance_rows)

    # Copy verifier
    shutil.copy2(VERIFIER_PATH, workspace_dir / "verifier.py")

    # Generate mission brief
    mission_brief = generate_mission_brief(week, year)
    (workspace_dir / "mission.md").write_text(mission_brief)

    # Create Claude settings in workspace/.claude/ (project-level settings)
    workspace_claude_dir = workspace_dir / ".claude"
    workspace_claude_dir.mkdir()

    # Permission allowlist for the agent
    claude_settings = {
        "permissions": {
            "allow": [
                "Read",
                "Write",
                "Edit",
                "LS",
                "Grep",
                "Glob",
                "Bash"
            ]
        }
    }
    (workspace_claude_dir / "settings.json").write_text(json.dumps(claude_settings, indent=2))
    (workspace_claude_dir / "settings.local.json").write_text(json.dumps(claude_settings, indent=2))
    (claude_dir / "settings.json").write_text(json.dumps(claude_settings, indent=2))
    (claude_dir / "settings.local.json").write_text(json.dumps(claude_settings, indent=2))

    # Also create global .claude settings at sandbox root
    (claude_dir / "settings.json").write_text(json.dumps(claude_settings, indent=2))

    return sandbox_dir


def setup_pixi_environment(sandbox_dir: Path) -> None:
    """Initialize pixi environment in the sandbox workspace."""
    workspace_dir = sandbox_dir / "workspace"

    # Initialize pixi project with pixi format (simpler, no src/ structure)
    subprocess.run(
        ["pixi", "init", "--format", "pixi"],
        cwd=workspace_dir,
        check=True,
        capture_output=True,
    )

    # Add Python
    subprocess.run(
        ["pixi", "add", "python>=3.11"],
        cwd=workspace_dir,
        check=True,
        capture_output=True,
    )

    print("  Pixi environment initialized")


# ---------------------------------------------------------------------------
# Sandbox execution
# ---------------------------------------------------------------------------


def build_bwrap_command(sandbox_dir: Path) -> list[str]:
    """Build bwrap command for sandboxing."""
    home_dir = Path.home()

    # Build PATH - start with standard paths
    path_components = ["/sandbox/workspace/.pixi/envs/default/bin", "/usr/bin", "/bin"]

    # Add ~/.local/bin if it exists
    local_bin = home_dir / ".local" / "bin"
    if local_bin.exists():
        path_components.insert(0, str(local_bin))

    path_value = ":".join(path_components)

    cmd = [
        "bwrap",
        # System binaries and libraries (read-only)
        "--ro-bind", "/usr", "/usr",
        "--ro-bind", "/lib", "/lib",
        "--ro-bind", "/lib64", "/lib64",
        "--ro-bind", "/bin", "/bin",
        # Network and system config
        "--ro-bind", "/etc/resolv.conf", "/etc/resolv.conf",
        "--ro-bind", "/etc/ssl", "/etc/ssl",
        "--ro-bind", "/etc/passwd", "/etc/passwd",
        "--ro-bind", "/etc/group", "/etc/group",
        # Sandbox contents (workspace includes data/)
        "--bind", str(sandbox_dir / "workspace"), "/sandbox/workspace",
        "--bind", str(sandbox_dir / ".claude"), "/sandbox/.claude",
        # Virtual filesystems
        "--proc", "/proc",
        "--dev", "/dev",
        "--tmpfs", "/tmp",
        # Environment
        "--chdir", "/sandbox/workspace",
        "--setenv", "HOME", "/sandbox",
        "--setenv", "PATH", path_value,
    ]

    # Bind mount pixi/uv caches for efficiency
    cache_dirs = [
        (home_dir / ".cache" / "rattler", "/root/.cache/rattler"),
        (home_dir / ".cache" / "uv", "/root/.cache/uv"),
        (home_dir / ".pixi", "/root/.pixi"),
    ]

    for src, dst in cache_dirs:
        if src.exists():
            cmd.extend(["--ro-bind", str(src), dst])

    # Bind mount claude CLI and its actual location (it's a symlink)
    if local_bin.exists():
        cmd.extend(["--ro-bind", str(local_bin), str(local_bin)])

    # Also bind the actual claude installation directory
    local_share = home_dir / ".local" / "share"
    if local_share.exists():
        cmd.extend(["--ro-bind", str(local_share), str(local_share)])

    return cmd


def build_systemd_wrapper(memory_limit: str | None = None, cpu_quota: str | None = None) -> list[str]:
    """Build systemd-run wrapper for resource limits."""
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

    cmd.extend(["-p", "TasksMax=1000"])

    return cmd


def run_agent(
    sandbox_dir: Path,
    week: int,
    year: int,
    model: str,
    timeout: int,
    output_dir: Path,
    use_bwrap: bool = True,
    memory_limit: str | None = None,
    cpu_quota: str | None = None,
    interactive: bool = False,
    debug: bool = False,
    skip_permissions: bool = False,
) -> int:
    """Run the agent in the sandbox."""
    env = os.environ.copy()

    # Model routing
    model_env = configure_model_env(model)
    env.update(model_env)

    print(f"  Model: {model_env.get('ANTHROPIC_MODEL', model)}")

    workspace_dir = sandbox_dir / "workspace"
    log_path = output_dir / "agent.log"

    # Build command
    base_cmd = []

    # Resource limits
    systemd_wrapper = build_systemd_wrapper(memory_limit, cpu_quota)
    if systemd_wrapper:
        base_cmd.extend(systemd_wrapper)

    # Sandboxing
    if use_bwrap:
        bwrap_cmd = build_bwrap_command(sandbox_dir)
        base_cmd.extend(bwrap_cmd)
        base_cmd.extend(["--", "claude"])
    else:
        base_cmd.append("claude")

    if debug:
        base_cmd.append("--debug")

    if skip_permissions:
        base_cmd.append("--dangerously-skip-permissions")

    prompt = load_template("prompt.txt").strip()

    if interactive:
        cmd = base_cmd + [prompt]
        return subprocess.run(cmd, env=env, cwd=workspace_dir).returncode
    else:
        cmd = base_cmd + ["-p", prompt]

        with open(log_path, "w") as log_file:
            try:
                result = subprocess.run(
                    cmd,
                    env=env,
                    cwd=workspace_dir,
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    timeout=timeout,
                )
                return result.returncode
            except subprocess.TimeoutExpired:
                log_file.write(f"\n\n--- TIMEOUT after {timeout} seconds ---\n")
                return -1


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def score_solution(sandbox_dir: Path, week: int, year: int) -> dict[str, Any]:
    """Score the solution using the verifier."""
    workspace_dir = sandbox_dir / "workspace"
    solution_path = workspace_dir / "solution.json"

    if not solution_path.exists():
        return {
            "valid": False,
            "error": "No solution.json found in workspace/",
        }

    # Import verifier
    sys.path.insert(0, str(BENCHMARK_DIR))
    try:
        from verifier import verify_files

        result = verify_files(
            problems_path=str(DATASET_DIR / "problems.json"),
            maintenance_path=str(DATASET_DIR / "maintenance.csv"),
            solution_path=str(solution_path),
            week=week,
            year=year,
        )

        return {
            "valid": result.is_valid,
            "score": result.score,
            "n_tracks": result.n_tracks,
            "n_satisfied_requests": result.n_satisfied_requests,
            "u_rms": result.u_rms,
            "u_max": result.u_max,
            "errors": result.errors,
            "warnings": result.warnings,
        }
    except Exception as e:
        return {
            "valid": False,
            "error": f"Verifier failed: {str(e)}",
        }
    finally:
        sys.path.pop(0)


# ---------------------------------------------------------------------------
# Single case runner
# ---------------------------------------------------------------------------


def run_single_case(
    case_id: str,
    model: str,
    output_dir: Path,
    timeout: int = DEFAULT_TIMEOUT,
    max_retries: int = DEFAULT_MAX_RETRIES,
    use_bwrap: bool = True,
    memory_limit: str | None = None,
    cpu_quota: str | None = None,
    interactive: bool = False,
    debug: bool = False,
    skip_permissions: bool = False,
) -> dict[str, Any]:
    """Run a single benchmark case."""
    week, year = parse_case_id(case_id)

    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*60}")
    print(f"SatNet Benchmark: Week {week}, Year {year}")
    print(f"Case: {case_id}")
    print(f"Model: {model}")
    print(f"Output: {output_dir}")
    print(f"{'='*60}")

    attempt = 0
    attempts_metadata = []

    while attempt <= max_retries:
        if attempt > 0:
            print(f"\n{'~'*60}")
            print(f"RETRY ATTEMPT {attempt}/{max_retries}")
            print(f"{'~'*60}")

        attempt_start = time.time()

        # Setup sandbox
        print("Setting up sandbox...")
        sandbox_dir = setup_sandbox(week, year, output_dir)

        # Initialize pixi environment
        print("Initializing Python environment...")
        try:
            setup_pixi_environment(sandbox_dir)
        except subprocess.CalledProcessError as e:
            print(f"  Warning: pixi setup failed: {e}")

        # Run agent
        print("Running agent...")
        exit_code = run_agent(
            sandbox_dir=sandbox_dir,
            week=week,
            year=year,
            model=model,
            timeout=timeout,
            output_dir=output_dir,
            use_bwrap=use_bwrap,
            memory_limit=memory_limit,
            cpu_quota=cpu_quota,
            interactive=interactive,
            debug=debug,
            skip_permissions=skip_permissions,
        )

        attempt_elapsed = time.time() - attempt_start
        print(f"Attempt {attempt} finished in {attempt_elapsed:.1f}s with exit code {exit_code}")

        # Score result
        print("Scoring solution...")
        score = score_solution(sandbox_dir, week, year)

        attempts_metadata.append({
            "attempt": attempt,
            "exit_code": exit_code,
            "elapsed_seconds": round(attempt_elapsed, 2),
            "valid": score.get("valid", False),
        })

        if score.get("valid") or attempt >= max_retries:
            break

        print(f"Solution is invalid. Retrying... ({attempt + 1}/{max_retries})")
        attempt += 1

    total_elapsed = sum(a["elapsed_seconds"] for a in attempts_metadata)

    result = {
        "benchmark": "satnet",
        "case_id": case_id,
        "week": week,
        "year": year,
        "model": model,
        "exit_code": exit_code,
        "elapsed_seconds": round(total_elapsed, 2),
        "attempts": len(attempts_metadata),
        "attempts_metadata": attempts_metadata,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **score,
    }

    # Save metrics
    metrics_path = output_dir / "metrics.json"
    with open(metrics_path, "w") as f:
        json.dump(result, f, indent=2)

    # Print summary
    print(f"\nResults:")
    print(f"  Case: {case_id}")
    print(f"  Valid: {score.get('valid', 'N/A')}")
    if score.get("valid"):
        print(f"  Score (hours): {score.get('score'):.4f}")
        print(f"  U_rms: {score.get('u_rms'):.4f}")
        print(f"  U_max: {score.get('u_max'):.4f}")
        print(f"  Tracks: {score.get('n_tracks')}")
        print(f"  Satisfied Requests: {score.get('n_satisfied_requests')}")
    else:
        print(f"  Error: {score.get('error', 'Unknown')}")
        if score.get("errors"):
            for err in score["errors"][:3]:
                print(f"    - {err}")

    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run SatNet agentic baseline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "--case",
        required=True,
        help="Case ID (e.g., 'w10_2018') or 'all' for all cases",
    )
    parser.add_argument(
        "--model",
        required=True,
        help="Model to use (e.g., 'anthropic::claude-sonnet-4-20250514')",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("/tmp/satnet_benchmark"),
        help="Output directory (default: /tmp/satnet_benchmark)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        help=f"Timeout in seconds (default: {DEFAULT_TIMEOUT})",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=DEFAULT_MAX_RETRIES,
        help=f"Max retries on invalid solutions (default: {DEFAULT_MAX_RETRIES})",
    )
    parser.add_argument(
        "--no-bwrap",
        action="store_true",
        help="Disable bwrap sandboxing",
    )
    parser.add_argument(
        "--memory-limit",
        help="Memory limit (e.g., '4G')",
    )
    parser.add_argument(
        "--cpu-quota",
        help="CPU quota (e.g., '200%%')",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Run in interactive mode",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug mode",
    )
    parser.add_argument(
        "--dangerously-skip-permissions",
        action="store_true",
        dest="skip_permissions",
        help="Skip Claude permission prompts (requires bwrap)",
    )

    args = parser.parse_args()

    # Safety validation for --dangerously-skip-permissions
    if args.skip_permissions:
        if args.no_bwrap:
            parser.error("--dangerously-skip-permissions requires bwrap sandboxing (cannot use --no-bwrap)")

    if args.case.lower() == "all":
        cases = get_all_cases()
        print(f"Running all {len(cases)} cases...")

        results = []
        for case_id in cases:
            case_output = args.output / case_id
            result = run_single_case(
                case_id=case_id,
                model=args.model,
                output_dir=case_output,
                timeout=args.timeout,
                max_retries=args.max_retries,
                use_bwrap=not args.no_bwrap,
                memory_limit=args.memory_limit,
                cpu_quota=args.cpu_quota,
                interactive=args.interactive,
                debug=args.debug,
                skip_permissions=args.skip_permissions,
            )
            results.append(result)

        # Save aggregate results
        aggregate_path = args.output / "aggregate.json"
        with open(aggregate_path, "w") as f:
            json.dump(results, f, indent=2)

        print(f"\nAggregate results saved to: {aggregate_path}")

        valid_count = sum(1 for r in results if r.get("valid"))
        print(f"Valid solutions: {valid_count}/{len(results)}")

        return 0 if valid_count == len(results) else 1
    else:
        case_output = args.output / args.case.lower()
        result = run_single_case(
            case_id=args.case,
            model=args.model,
            output_dir=case_output,
            timeout=args.timeout,
            max_retries=args.max_retries,
            use_bwrap=not args.no_bwrap,
            memory_limit=args.memory_limit,
            cpu_quota=args.cpu_quota,
            interactive=args.interactive,
            debug=args.debug,
            skip_permissions=args.skip_permissions,
        )

        return 0 if result.get("valid") else 1


if __name__ == "__main__":
    raise SystemExit(main())
