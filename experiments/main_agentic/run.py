#!/usr/bin/env python3
"""Run the main agentic experiment family."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import plan as family_plan  # type: ignore[no-redef]
else:
    from . import plan as family_plan


WORKSPACE_MOUNT = Path("/app/workspace")
OUTPUT_MOUNT = Path("/app/run/output")
CONTAINER_HOME = Path("/home/korolev")
CONTAINER_XDG_CONFIG_HOME = CONTAINER_HOME / ".config"
CONTAINER_XDG_DATA_HOME = CONTAINER_HOME / ".local" / "share"
CONTAINER_USER_NAME = "korolev"
CONTAINER_GROUP_NAME = "korolev"
PROMPT_FILE_NAME = "PROMPT.md"
PLACEHOLDER_PATTERN = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")
SATNET_COMPACT_PATTERN = re.compile(
    r"(VALID|INVALID):\s+(?:total_hours|score)=([+-]?(?:\d+(?:\.\d*)?|\.\d+))h,\s+tracks=(\d+)"
)
SPOT5_COMPACT_PATTERN = re.compile(
    r"(VALID|INVALID):\s+profit=(\d+),\s+weight=(\d+)"
)
STATUS_PATTERN = re.compile(r"^Status:\s+(VALID|INVALID)\s*$", re.MULTILINE)


@dataclass(frozen=True)
class MountRoots:
    workspace: Path
    home: Path
    output: Path


@dataclass(frozen=True)
class ContainerIdentity:
    username: str
    group_name: str
    passwd_file: Path
    group_file: Path


@dataclass(frozen=True)
class VerifierOutcome:
    status: str
    result: dict[str, Any]


@dataclass(frozen=True)
class RunExecutionResult:
    overall_status: str
    skipped: bool
    output_dir: Path
    exit_code: int


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the main agentic experiment family")
    parser.add_argument(
        "--config",
        type=Path,
        help="Override the family config path. Defaults to matrix.yaml or interactive.yaml.",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Use interactive defaults instead of the batch matrix defaults.",
    )
    parser.add_argument(
        "--benchmark",
        action="append",
        default=[],
        help="Limit execution to a benchmark name. May be repeated.",
    )
    parser.add_argument(
        "--harness",
        action="append",
        default=[],
        help="Limit execution to a harness name. May be repeated.",
    )
    parser.add_argument(
        "--split",
        help="Override the configured split for this execution pass.",
    )
    parser.add_argument(
        "--case",
        action="append",
        default=[],
        help="Limit execution to an exact case id. May be repeated.",
    )
    parser.add_argument(
        "--rerun-status",
        action="append",
        default=[],
        help="Execute only runs whose current stored status matches this value. May be repeated.",
    )
    parser.add_argument(
        "--no-skip-completed",
        action="store_true",
        help="Execute all selected runs regardless of existing run.json status.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview the effective selection and exit without executing anything.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        help="Override the configured timeout in seconds.",
    )
    parser.add_argument(
        "--max-concurrency",
        type=int,
        help="Override matrix.yaml batch.max_concurrency for this batch execution.",
    )
    return parser.parse_args(argv)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _isoformat(value: datetime) -> str:
    return value.isoformat()


def _duration_seconds(start: datetime, end: datetime) -> float:
    return round((end - start).total_seconds(), 3)


def _container_path_to_host_path(container_path: Path, roots: MountRoots) -> Path:
    for prefix, host_root in (
        (WORKSPACE_MOUNT, roots.workspace),
        (CONTAINER_HOME, roots.home),
        (OUTPUT_MOUNT, roots.output),
    ):
        try:
            relative = container_path.relative_to(prefix)
        except ValueError:
            continue
        return host_root / relative
    raise SystemExit(f"Container path is outside mounted roots: {container_path}")


def _collect_target_host_path(target: Path, output_dir: Path) -> Path:
    if not target.parts:
        raise SystemExit(
            f"Collect target must start with results_root/, repo/, benchmark(s)/, or experiments/: {target}"
        )
    root = target.parts[0]
    relative = Path(*target.parts[1:]) if len(target.parts) > 1 else Path()
    if root == "results_root":
        return output_dir / relative
    if root == "repo":
        return family_plan.REPO_ROOT / relative
    if root == "benchmark":
        return family_plan.REPO_ROOT / "benchmarks" / relative
    if root in {"experiments", "benchmarks"}:
        return family_plan.REPO_ROOT / target
    raise SystemExit(
        f"Collect target must start with results_root/, repo/, benchmark(s)/, or experiments/: {target}"
    )


def _relative_display(path: Path) -> str:
    if path.is_relative_to(family_plan.REPO_ROOT):
        return path.relative_to(family_plan.REPO_ROOT).as_posix()
    return str(path)


def _format_rendered_text(template: str, replacements: dict[str, str]) -> str:
    missing_keys: set[str] = set()

    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key in replacements:
            return replacements[key]
        missing_keys.add(key)
        return match.group(0)

    rendered = PLACEHOLDER_PATTERN.sub(replace, template)
    if missing_keys:
        # Leave unknown braces untouched so JSON/code/math examples survive.
        for key in missing_keys:
            rendered = rendered.replace(f"{{{key}}}", f"{{{key}}}")
    return rendered


def _copy_file_or_directory(
    source: Path,
    destination: Path,
    *,
    render: bool,
    context: dict[str, str],
) -> None:
    if destination.exists():
        if destination.is_dir():
            shutil.rmtree(destination)
        else:
            destination.unlink()

    if source.is_dir():
        if render:
            raise SystemExit(f"Cannot render a directory source: {source}")
        shutil.copytree(source, destination)
        return

    destination.parent.mkdir(parents=True, exist_ok=True)
    if render:
        rendered = _format_rendered_text(source.read_text(encoding="utf-8"), context)
        destination.write_text(rendered, encoding="utf-8")
        return
    shutil.copy2(source, destination)


def _build_container_identity(temp_dir: Path) -> ContainerIdentity:
    uid = os.getuid()
    gid = os.getgid()
    passwd_file = temp_dir / "passwd"
    group_file = temp_dir / "group"

    passwd_file.write_text(
        "\n".join(
            [
                "root:x:0:0:root:/root:/bin/bash",
                f"{CONTAINER_USER_NAME}:x:{uid}:{gid}:AstroReason User:{CONTAINER_HOME}:/bin/bash",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    group_file.write_text(
        "\n".join(
            [
                "root:x:0:",
                f"{CONTAINER_GROUP_NAME}:x:{gid}:",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return ContainerIdentity(
        username=CONTAINER_USER_NAME,
        group_name=CONTAINER_GROUP_NAME,
        passwd_file=passwd_file,
        group_file=group_file,
    )


def _prepare_mount_roots(workspace_dir: Path, runtime_state_dir: Path, output_dir: Path) -> MountRoots:
    roots = MountRoots(
        workspace=workspace_dir,
        home=runtime_state_dir / "home",
        output=output_dir,
    )
    roots.workspace.mkdir(parents=True, exist_ok=True)
    roots.home.mkdir(parents=True, exist_ok=True)
    roots.output.mkdir(parents=True, exist_ok=True)
    return roots


def _case_dir(benchmark: str, split: str, case_id: str) -> Path:
    return (
        family_plan.REPO_ROOT / "benchmarks" / benchmark / "dataset" / "cases" / split / case_id
    )


def _verifier_repo_path(benchmark: str) -> Path | None:
    benchmark_dir = family_plan.REPO_ROOT / "benchmarks" / benchmark
    verifier_dir = benchmark_dir / "verifier"
    verifier_py = benchmark_dir / "verifier.py"
    if verifier_dir.is_dir():
        return verifier_dir.resolve()
    if verifier_py.exists():
        return verifier_py.resolve()
    return None


def _example_solution_repo_path(benchmark: str) -> Path | None:
    dataset_dir = family_plan.REPO_ROOT / "benchmarks" / benchmark / "dataset"
    for candidate in ("example_solution.json", "example_solution.yaml", "example_solution.yml"):
        path = dataset_dir / candidate
        if path.exists():
            return path.resolve()
    return None


def _workspace_example_solution_name(
    benchmark: str,
    assemble_specs: tuple[family_plan.AssembleSpec, ...],
) -> str:
    example_solution = _example_solution_repo_path(benchmark)
    if example_solution is None:
        return "No example solution is provided for this workspace."

    for spec in assemble_specs:
        if spec.source != example_solution:
            continue
        try:
            relative = spec.target.relative_to(WORKSPACE_MOUNT)
        except ValueError:
            continue
        target_name = relative.name or example_solution.name
        return target_name
    return "No example solution is provided for this workspace."


def _workspace_module_name(relative: Path) -> str:
    return ".".join(part for part in relative.parts if part)


def _workspace_verifier_info(
    benchmark: str,
    assemble_specs: tuple[family_plan.AssembleSpec, ...],
) -> tuple[str, str]:
    verifier = _verifier_repo_path(benchmark)
    if verifier is None:
        return (
            "Verifier is not exposed in this workspace.",
            "No verifier helper is available in this workspace.",
        )

    for spec in assemble_specs:
        if spec.source != verifier:
            continue
        try:
            relative = spec.target.relative_to(WORKSPACE_MOUNT)
        except ValueError:
            continue

        location = relative.as_posix() + ("/" if verifier.is_dir() else "")
        if verifier.is_dir():
            module_name = _workspace_module_name(relative)
            command = f"python -m {module_name}.run case/ solution.json"
        else:
            command = f"python {relative.as_posix()} case/ solution.json"
        return location, command

    return (
        "Verifier is not exposed in this workspace.",
        "No verifier helper is available in this workspace.",
    )


def _template_context(
    benchmark: str,
    split: str,
    case_id: str,
    assemble_specs: tuple[family_plan.AssembleSpec, ...],
) -> dict[str, str]:
    verifier_location, verifier_command = _workspace_verifier_info(benchmark, assemble_specs)
    return {
        "benchmark": benchmark,
        "split": split,
        "case_id": case_id,
        "example_solution_name": _workspace_example_solution_name(benchmark, assemble_specs),
        "verifier_location": verifier_location,
        "verifier_command": verifier_command,
    }


def _materialized_benchmark_assemble_specs(item: family_plan.RunItem) -> tuple[family_plan.AssembleSpec, ...]:
    replacements = {
        "benchmark": item.benchmark,
        "split": item.split,
        "case_id": item.case_id,
        "family": family_plan.FAMILY_DIR.name,
        "config_name": item.config_name,
    }
    return family_plan.materialize_assemble_templates(
        item.benchmark_profile.assemble,
        replacements,
        owner_path=item.benchmark_profile.profile_path,
    )


def _assemble_specs_for_batch_item(item: family_plan.RunItem) -> tuple[family_plan.AssembleSpec, ...]:
    return (
        _materialized_benchmark_assemble_specs(item)
        + (
            family_plan.AssembleSpec(
                source=family_plan.SHARED_AGENTS_FRAGMENT,
                target=WORKSPACE_MOUNT / "AGENTS.md",
                render=True,
                missing_ok=False,
                example=None,
            ),
        )
        + family_plan.materialize_assemble_templates(
            item.harness_profile.assemble,
            {},
            owner_path=item.harness_profile.profile_path,
        )
    )


def _assemble_specs_for_interactive(
    plan: family_plan.InteractivePlan,
) -> tuple[family_plan.AssembleSpec, ...]:
    replacements = {
        "benchmark": plan.config.benchmark,
        "split": plan.effective_split,
        "case_id": plan.effective_case_id,
        "family": family_plan.FAMILY_DIR.name,
        "config_name": plan.config.config_path.stem,
    }
    specs = list(
        family_plan.materialize_assemble_templates(
            plan.benchmark_profile.assemble,
            replacements,
            owner_path=plan.benchmark_profile.profile_path,
        )
    )
    specs.append(
        family_plan.AssembleSpec(
            source=family_plan.SHARED_AGENTS_FRAGMENT,
            target=WORKSPACE_MOUNT / "AGENTS.md",
            render=True,
            missing_ok=False,
            example=None,
        )
    )
    seen_targets: set[str] = {str(WORKSPACE_MOUNT / "AGENTS.md")}
    for harness in plan.harnesses:
        for assemble_spec in family_plan.materialize_assemble_templates(
            harness.assemble,
            {},
            owner_path=harness.profile_path,
        ):
            target_key = assemble_spec.target.as_posix()
            if target_key in seen_targets:
                continue
            seen_targets.add(target_key)
            specs.append(assemble_spec)
    return tuple(specs)


def _namespace_collect_target(target: Path, harness_name: str) -> Path:
    parts = target.parts
    if not parts:
        return Path(harness_name)
    if parts[0] == "results_root" and len(parts) > 1:
        return Path(parts[0]) / parts[1] / harness_name / Path(*parts[2:])
    if len(parts) == 1:
        return Path(parts[0]) / harness_name
    return Path(parts[0]) / harness_name / Path(*parts[1:])


def _collect_specs_for_harnesses(
    benchmark_collect: tuple[family_plan.CollectSpec, ...],
    harnesses: tuple[family_plan.HarnessProfile, ...],
    *,
    namespace: bool,
) -> tuple[family_plan.CollectSpec, ...]:
    specs: list[family_plan.CollectSpec] = list(benchmark_collect)
    for harness in harnesses:
        for spec in harness.collect:
            target = _namespace_collect_target(spec.target, harness.harness) if namespace else spec.target
            specs.append(
                family_plan.CollectSpec(
                    source=spec.source,
                    target=target,
                    missing_ok=spec.missing_ok,
                )
            )
    return tuple(specs)


def _assemble_workspace(
    assemble_specs: tuple[family_plan.AssembleSpec, ...],
    roots: MountRoots,
    *,
    benchmark: str,
    split: str,
    case_id: str,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    context = _template_context(benchmark, split, case_id, assemble_specs)

    for spec in assemble_specs:
        source_exists = spec.source.exists()
        if not source_exists:
            if spec.missing_ok:
                records.append(
                    {
                        "source": _relative_display(spec.source),
                        "target": spec.target.as_posix(),
                        "present": False,
                        "rendered": spec.render,
                    }
                )
                continue
            example_note = f" Copy the example file {spec.example} and fill it in." if spec.example else ""
            raise SystemExit(f"Required assemble source does not exist: {spec.source}.{example_note}")

        destination = _container_path_to_host_path(spec.target, roots)
        _copy_file_or_directory(spec.source, destination, render=spec.render, context=context)
        records.append(
            {
                "source": _relative_display(spec.source),
                "target": spec.target.as_posix(),
                "present": True,
                "rendered": spec.render,
            }
        )

    return records


def _collect_artifacts(
    collect_specs: tuple[family_plan.CollectSpec, ...],
    roots: MountRoots,
    output_dir: Path,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for spec in collect_specs:
        source = _container_path_to_host_path(spec.source, roots)
        destination = _collect_target_host_path(spec.target, output_dir)
        if not source.exists():
            if spec.missing_ok:
                records.append(
                    {
                        "source": spec.source.as_posix(),
                        "target": spec.target.as_posix(),
                        "present": False,
                    }
                )
                continue
            raise SystemExit(f"Required collected source does not exist: {source}")

        if destination.exists():
            if destination.is_dir():
                shutil.rmtree(destination)
            else:
                destination.unlink()
        destination.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.copytree(source, destination)
        else:
            shutil.copy2(source, destination)

        records.append(
            {
                "source": spec.source.as_posix(),
                "target": spec.target.as_posix(),
                "present": True,
            }
        )
    return records


def _build_container_script(
    *,
    timeout_seconds: int,
    headless_shell_command: str | None,
    interactive: bool,
) -> str:
    lines = [
        "set -euo pipefail",
        f"mkdir -p {shlex.quote(str(CONTAINER_HOME))}",
        f"mkdir -p {shlex.quote(str(CONTAINER_XDG_CONFIG_HOME))}",
        f"mkdir -p {shlex.quote(str(CONTAINER_XDG_DATA_HOME))}",
        f"cd {shlex.quote(str(WORKSPACE_MOUNT))}",
    ]
    if interactive:
        lines.append("exec /bin/bash -i")
        return "\n".join(lines)
    if headless_shell_command is None:
        raise SystemExit("Headless execution requires a shell command.")
    lines.append(
        f"exec timeout --signal=TERM {timeout_seconds} /bin/bash -lc {shlex.quote(headless_shell_command)}"
    )
    return "\n".join(lines)


def _build_docker_command(
    *,
    runtime: family_plan.RuntimeManifest,
    roots: MountRoots,
    container_identity: ContainerIdentity,
    resources: family_plan.ResourceLimits,
    forward_env_keys: tuple[str, ...],
    timeout_seconds: int,
    headless_shell_command: str | None,
    interactive: bool,
) -> list[str]:
    cmd = ["docker", "run", "--rm", "-w", str(WORKSPACE_MOUNT)]
    cmd.extend(["--user", f"{os.getuid()}:{os.getgid()}"])
    cmd.extend(["-e", f"HOME={CONTAINER_HOME}"])
    cmd.extend(["-e", f"USER={container_identity.username}"])
    cmd.extend(["-e", f"LOGNAME={container_identity.username}"])
    cmd.extend(["-e", f"XDG_CONFIG_HOME={CONTAINER_XDG_CONFIG_HOME}"])
    cmd.extend(["-e", f"XDG_DATA_HOME={CONTAINER_XDG_DATA_HOME}"])
    for env_key in forward_env_keys:
        env_value = os.environ.get(env_key)
        if env_value is not None:
            cmd.extend(["-e", f"{env_key}={env_value}"])
    if resources.cpus is not None:
        cmd.extend(["--cpus", resources.cpus])
    if resources.memory is not None:
        cmd.extend(["--memory", resources.memory])
    if resources.shm_size is not None:
        cmd.extend(["--shm-size", resources.shm_size])
    if interactive:
        cmd.append("-i")
        if sys.stdin.isatty() and sys.stdout.isatty():
            cmd.append("-t")

    cmd.extend(
        [
            "-v",
            f"{roots.workspace.resolve()}:{WORKSPACE_MOUNT}",
            "-v",
            f"{roots.output.resolve()}:{OUTPUT_MOUNT}",
            "-v",
            f"{roots.home.resolve()}:{CONTAINER_HOME}",
            "-v",
            f"{container_identity.passwd_file.resolve()}:/etc/passwd:ro",
            "-v",
            f"{container_identity.group_file.resolve()}:/etc/group:ro",
        ]
    )

    shell_script = _build_container_script(
        timeout_seconds=timeout_seconds,
        headless_shell_command=headless_shell_command,
        interactive=interactive,
    )
    cmd.append(runtime.image)
    cmd.extend(["/bin/bash", "-lc", shell_script])
    return cmd


def _run_process(
    cmd: list[str],
    *,
    capture_output: bool,
    cwd: Path | None = None,
) -> tuple[int, str, str, bool]:
    try:
        result = subprocess.run(
            cmd,
            capture_output=capture_output,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            cwd=cwd,
        )
    except FileNotFoundError as exc:
        return 127, "", f"Failed to launch process: {exc}", False

    if capture_output:
        return result.returncode, result.stdout or "", result.stderr or "", True
    return result.returncode, "", "", True


def _run_process_to_files(
    cmd: list[str],
    *,
    stdout_path: Path,
    stderr_path: Path,
) -> tuple[int, str, bool]:
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    stderr_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with stdout_path.open("w", encoding="utf-8") as stdout_handle:
            with stderr_path.open("w", encoding="utf-8") as stderr_handle:
                result = subprocess.run(
                    cmd,
                    stdout=stdout_handle,
                    stderr=stderr_handle,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    check=False,
                )
    except FileNotFoundError as exc:
        stderr_path.write_text(f"Failed to launch process: {exc}\n", encoding="utf-8")
        if not stdout_path.exists():
            stdout_path.write_text("", encoding="utf-8")
        return 127, str(exc), False

    return result.returncode, "", True


def _copy_solution_artifact(workspace_dir: Path, output_dir: Path) -> bool:
    solution_src = workspace_dir / "solution.json"
    solution_dst = output_dir / "solution.json"
    if not solution_src.exists():
        return False
    shutil.copy2(solution_src, solution_dst)
    return True


def _agent_status(agent_exit_code: int, solution_present: bool, launched: bool) -> str:
    if not launched:
        return "runner_error"
    if agent_exit_code == 124:
        return "timeout"
    if agent_exit_code != 0:
        return "agent_failed"
    if not solution_present:
        return "no_solution"
    return "success"


def _verifier_command(benchmark: str, case_dir: Path, solution_path: Path) -> list[str]:
    verifier_path = _verifier_repo_path(benchmark)
    if verifier_path is None:
        raise SystemExit(f"No verifier found for benchmark {benchmark}")

    if verifier_path.is_dir():
        return [
            "uv",
            "run",
            "python",
            "-m",
            f"benchmarks.{benchmark}.verifier.run",
            str(case_dir),
            str(solution_path),
        ]
    cmd = [
        "uv",
        "run",
        "python",
        str(verifier_path),
        str(case_dir),
        str(solution_path),
    ]
    if benchmark in {"satnet", "spot5"}:
        cmd.append("--verbose")
    return cmd


def _normalized_verifier_valid(parsed: dict[str, Any]) -> bool | None:
    valid = parsed.get("valid")
    if isinstance(valid, bool):
        return valid
    is_valid = parsed.get("is_valid")
    if isinstance(is_valid, bool):
        return is_valid
    return None


def _normalize_cli_verifier_payload(benchmark: str, parsed: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(parsed)
    valid = _normalized_verifier_valid(normalized)
    if isinstance(valid, bool):
        normalized["valid"] = valid
    return normalized


def _float_line(label: str, text: str) -> float | None:
    match = re.search(rf"^{re.escape(label)}:\s+([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*$", text, re.MULTILINE)
    return float(match.group(1)) if match else None


def _int_line(label: str, text: str) -> int | None:
    match = re.search(rf"^{re.escape(label)}:\s+(\d+)\s*$", text, re.MULTILINE)
    return int(match.group(1)) if match else None


def _status_valid(text: str) -> bool | None:
    match = STATUS_PATTERN.search(text)
    if match:
        return match.group(1) == "VALID"
    return None


def _cli_section_items(text: str, section: str) -> list[str]:
    pattern = re.compile(
        rf"^{re.escape(section)}:\s*$((?:\n\s+- .*)*)",
        re.MULTILINE,
    )
    match = pattern.search(text)
    if not match:
        return []
    items: list[str] = []
    for line in match.group(1).splitlines():
        stripped = line.strip()
        if stripped.startswith("- "):
            items.append(stripped[2:])
    return items


def _parse_satnet_cli_payload(stdout: str, exit_code: int) -> dict[str, Any]:
    valid = _status_valid(stdout)
    score_hours = _float_line("Total tracking hours", stdout)
    if score_hours is None:
        score_hours = _float_line("Score (hours)", stdout)
    n_tracks = _int_line("Tracks", stdout)
    n_satisfied_requests = _int_line("Satisfied requests", stdout)
    u_rms = _float_line("U_rms", stdout)
    u_max = _float_line("U_max", stdout)

    if valid is None:
        compact_match = SATNET_COMPACT_PATTERN.search(stdout)
        if compact_match is not None:
            valid = compact_match.group(1) == "VALID"
            score_hours = float(compact_match.group(2))
            n_tracks = int(compact_match.group(3))

    if valid is None or score_hours is None or n_tracks is None:
        return {
            "status": "error",
            "error": "SatNet verifier output did not match expected CLI schema.",
            "exit_code": exit_code,
        }
    payload = {
        "valid": valid,
        "metrics": {
            "score_hours": score_hours,
            "n_tracks": n_tracks,
            "n_satisfied_requests": n_satisfied_requests,
            "u_rms": u_rms,
            "u_max": u_max,
        },
        "diagnostics": {},
        "errors": _cli_section_items(stdout, "Errors"),
        "warnings": _cli_section_items(stdout, "Warnings"),
    }
    return payload


def _parse_spot5_cli_payload(stdout: str, exit_code: int) -> dict[str, Any]:
    valid = _status_valid(stdout)
    computed_profit = _int_line("Computed Profit", stdout)
    computed_weight = _int_line("Computed Weight", stdout)
    computed_selected = _int_line("Selected Photos", stdout)

    if valid is None:
        compact_match = SPOT5_COMPACT_PATTERN.search(stdout)
        if compact_match is not None:
            valid = compact_match.group(1) == "VALID"
            computed_profit = int(compact_match.group(2))
            computed_weight = int(compact_match.group(3))

    if valid is None or computed_profit is None or computed_weight is None:
        return {
            "status": "error",
            "error": "SPOT-5 verifier output did not match expected CLI schema.",
            "exit_code": exit_code,
        }
    payload = {
        "valid": valid,
        "metrics": {
            "computed_profit": computed_profit,
            "computed_weight": computed_weight,
            "computed_selected": computed_selected,
        },
        "diagnostics": {},
        "errors": _cli_section_items(stdout, "Errors"),
        "warnings": _cli_section_items(stdout, "Warnings"),
    }
    return payload


def _parse_compact_cli_verifier_payload(
    benchmark: str,
    stdout: str,
    exit_code: int,
) -> dict[str, Any] | None:
    if benchmark == "satnet":
        return _parse_satnet_cli_payload(stdout, exit_code)
    if benchmark == "spot5":
        return _parse_spot5_cli_payload(stdout, exit_code)
    return None


def _run_external_verifier(
    benchmark: str,
    case_dir: Path,
    output_dir: Path,
    *,
    solution_present: bool,
) -> VerifierOutcome:
    if not solution_present:
        return VerifierOutcome(
            status="no_solution",
            result={"present": False, "status": "no_solution"},
        )

    solution_path = output_dir / "solution.json"
    cmd = _verifier_command(benchmark, case_dir, solution_path)
    exit_code, stdout, stderr, launched = _run_process(
        cmd,
        capture_output=True,
        cwd=family_plan.REPO_ROOT,
    )
    if not launched:
        return VerifierOutcome(
            status="error",
            result={"status": "error", "error": stderr.strip() or "Failed to launch verifier."},
        )

    compact_payload = _parse_compact_cli_verifier_payload(benchmark, stdout, exit_code)
    if compact_payload is not None:
        valid = compact_payload.get("valid")
        if isinstance(valid, bool) and exit_code in (0, 1):
            return VerifierOutcome(
                status="valid" if valid else "invalid",
                result=compact_payload,
            )
        return VerifierOutcome(
            status="error",
            result={
                **compact_payload,
                "stderr": stderr.strip(),
            },
        )

    try:
        parsed = json.loads(stdout) if stdout.strip() else {}
    except json.JSONDecodeError as exc:
        return VerifierOutcome(
            status="error",
            result={
                "status": "error",
                "error": f"Verifier output was not valid JSON: {exc}",
                "exit_code": exit_code,
            },
        )

    if not isinstance(parsed, dict):
        return VerifierOutcome(
            status="error",
            result={
                "status": "error",
                "error": "Verifier output JSON must be an object.",
                "exit_code": exit_code,
            },
        )

    parsed = _normalize_cli_verifier_payload(benchmark, parsed)
    valid = parsed.get("valid")
    if not isinstance(valid, bool):
        error = "Verifier output JSON must include a boolean 'valid' field."
        if stderr.strip():
            error = f"{error} {stderr.strip()}"
        return VerifierOutcome(
            status="error",
            result={
                "status": "error",
                "error": error,
                "exit_code": exit_code,
            },
        )

    if exit_code in (0, 1):
        return VerifierOutcome(
            status="valid" if valid else "invalid",
            result=parsed,
        )

    return VerifierOutcome(
        status="error",
        result={
            "status": "error",
            "exit_code": exit_code,
            "error": stderr.strip() or "Verifier exited unexpectedly.",
        },
    )


def _overall_status(agent_status: str, verifier_status: str, interactive: bool) -> str:
    if interactive:
        if agent_status == "interactive_failed":
            return "interactive_failed"
        if agent_status == "interactive_no_solution":
            return "interactive_no_solution"
        return "interactive_completed"

    if agent_status != "success":
        return agent_status
    if verifier_status == "valid":
        return "success"
    if verifier_status == "invalid":
        return "verifier_invalid"
    return "verifier_error"


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _write_run_metadata(
    *,
    mode: str,
    config_path: Path,
    benchmark: str,
    harness_identity: str,
    selected_harnesses: tuple[str, ...],
    runtime: family_plan.RuntimeManifest,
    output_dir: Path,
    split: str,
    case_id: str,
    assembled_records: list[dict[str, Any]],
    collected_records: list[dict[str, Any]],
    start_time: datetime,
    end_time: datetime,
    agent_exit_code: int,
    agent_status: str,
    verifier_outcome: VerifierOutcome,
    benchmark_profile_path: Path,
    harness_profile_paths: tuple[Path, ...],
    interactive: bool,
) -> str:
    artifacts = {
        "solution.json": (output_dir / "solution.json").exists(),
        "agent_stdout.txt": (output_dir / "agent_stdout.txt").exists(),
        "agent_stderr.txt": (output_dir / "agent_stderr.txt").exists(),
        "run.json": True,
    }
    for record in collected_records:
        artifacts[record["target"]] = bool(record["present"])

    overall_status = _overall_status(agent_status, verifier_outcome.status, interactive)
    run_data = {
        "mode": mode,
        "benchmark": benchmark,
        "experiment": family_plan.family_relpath().as_posix(),
        "config_name": config_path.stem,
        "harness": harness_identity,
        "selected_harnesses": list(selected_harnesses),
        "runtime": runtime.name,
        "case_id": case_id,
        "split": split,
        "overall_status": overall_status,
        "agent_status": agent_status,
        "verifier_status": verifier_outcome.status,
        "start_time": _isoformat(start_time),
        "end_time": _isoformat(end_time),
        "duration_seconds": _duration_seconds(start_time, end_time),
        "container_image": runtime.image,
        "agent_exit_code": agent_exit_code,
        "artifacts": artifacts,
        "assembly": {
            "family_config": _relative_display(config_path),
            "benchmark_profile": _relative_display(benchmark_profile_path),
            "harness_profiles": [_relative_display(path) for path in harness_profile_paths],
            "assemble": assembled_records,
            "collect": collected_records,
        },
        "verifier": verifier_outcome.result,
    }
    _write_text(output_dir / "run.json", json.dumps(run_data, indent=2, sort_keys=True) + "\n")
    return overall_status


def _print_run_summary(output_dir: Path, overall_status: str) -> None:
    print(f"Results written to {output_dir}")
    print(f"Run status: {overall_status}")


def _print_batch_preview(preview: family_plan.BatchPreview) -> None:
    print(family_plan.describe_batch_preview(preview, include_items=False))


def _print_progress_line(
    *,
    index: int,
    total: int,
    preview_item: family_plan.BatchPreviewItem,
    result: RunExecutionResult,
    executed_count: int,
    skipped_count: int,
    status_counts: dict[str, int],
) -> None:
    item = preview_item.item
    counts_text = ", ".join(f"{status}={count}" for status, count in sorted(status_counts.items()))
    action = "skipped" if result.skipped else "executed"
    print(
        f"[{index}/{total}] {item.benchmark}/{item.harness}/{item.case_id} "
        f"-> {result.overall_status} ({action}; executed={executed_count}, skipped={skipped_count}; {counts_text})"
    )


def _run_headless_once(
    item: family_plan.RunItem,
    *,
    timeout_override: int | None,
) -> RunExecutionResult:
    runtime = family_plan.load_runtime(item.harness_profile.runtime)
    case_dir = _case_dir(item.benchmark, item.split, item.case_id)
    if not case_dir.exists():
        raise SystemExit(f"Case directory does not exist: {case_dir}")

    assemble_specs = _assemble_specs_for_batch_item(item)
    output_dir = family_plan.run_output_dir(item)
    timeout_seconds = timeout_override or item.timeout_seconds
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix=f"astroreason-{family_plan.FAMILY_DIR.name}-workspace-") as workspace_tmp:
        with tempfile.TemporaryDirectory(prefix=f"astroreason-{family_plan.FAMILY_DIR.name}-runtime-") as runtime_tmp:
            workspace_dir = Path(workspace_tmp)
            runtime_state_dir = Path(runtime_tmp)
            roots = _prepare_mount_roots(workspace_dir, runtime_state_dir, output_dir)
            container_identity = _build_container_identity(runtime_state_dir)
            assembled_records = _assemble_workspace(
                assemble_specs,
                roots,
                benchmark=item.benchmark,
                split=item.split,
                case_id=item.case_id,
            )
            cmd = _build_docker_command(
                runtime=runtime,
                roots=roots,
                container_identity=container_identity,
                resources=item.resources,
                forward_env_keys=item.harness_profile.forward_env_keys,
                timeout_seconds=timeout_seconds,
                headless_shell_command=item.harness_profile.headless_shell_command,
                interactive=False,
            )

            start_time = _utc_now()
            exit_code, launch_error, launched = _run_process_to_files(
                cmd,
                stdout_path=output_dir / "agent_stdout.txt",
                stderr_path=output_dir / "agent_stderr.txt",
            )
            end_time = _utc_now()
            if not launched and launch_error:
                _write_text(output_dir / "agent_stderr.txt", f"Failed to launch process: {launch_error}\n")

            solution_present = _copy_solution_artifact(workspace_dir, output_dir)
            collected_records = _collect_artifacts(
                _collect_specs_for_harnesses(
                    item.benchmark_profile.collect,
                    (item.harness_profile,),
                    namespace=False,
                ),
                roots,
                output_dir,
            )
            agent_status = _agent_status(exit_code, solution_present, launched)
            verifier_outcome = _run_external_verifier(
                item.benchmark,
                case_dir,
                output_dir,
                solution_present=solution_present,
            )
            overall_status = _write_run_metadata(
                mode="batch",
                config_path=item.config_path,
                benchmark=item.benchmark,
                harness_identity=item.harness,
                selected_harnesses=(item.harness,),
                runtime=runtime,
                output_dir=output_dir,
                split=item.split,
                case_id=item.case_id,
                assembled_records=assembled_records,
                collected_records=collected_records,
                start_time=start_time,
                end_time=end_time,
                agent_exit_code=exit_code,
                agent_status=agent_status,
                verifier_outcome=verifier_outcome,
                benchmark_profile_path=item.benchmark_profile.profile_path,
                harness_profile_paths=(item.harness_profile.profile_path,),
                interactive=False,
            )
            _print_run_summary(output_dir, overall_status)
            return RunExecutionResult(
                overall_status=overall_status,
                skipped=False,
                output_dir=output_dir,
                exit_code=0 if overall_status == "success" else 1,
            )


def _execute_run_item(
    preview_item: family_plan.BatchPreviewItem,
    *,
    batch_settings: family_plan.BatchSettings,
    timeout_override: int | None,
) -> RunExecutionResult:
    item = preview_item.item
    output_dir = family_plan.run_output_dir(item)
    if preview_item.action == "skip":
        return RunExecutionResult(
            overall_status=preview_item.existing_overall_status or preview_item.artifact_state,
            skipped=True,
            output_dir=output_dir,
            exit_code=0 if preview_item.existing_overall_status == "success" else 1,
        )

    last_result: RunExecutionResult | None = None
    attempts = batch_settings.max_retries + 1
    for attempt in range(1, attempts + 1):
        print(
            f"Running {item.benchmark}/{item.harness}/{item.case_id} "
            f"(attempt {attempt}/{attempts})"
        )
        last_result = _run_headless_once(item, timeout_override=timeout_override)
        if last_result.overall_status not in batch_settings.retry_statuses:
            return last_result
        if attempt < attempts:
            print(
                f"Retrying {item.benchmark}/{item.harness}/{item.case_id} "
                f"after retryable status {last_result.overall_status}"
            )

    if last_result is None:
        raise SystemExit("Internal error: no run result was produced.")
    return last_result


def _run_batch(
    args: argparse.Namespace,
    preview: family_plan.BatchPreview,
) -> int:
    runnable_items = family_plan.runnable_preview_items(preview)
    results: list[RunExecutionResult] = []
    total_items = len(preview.items)
    completed = 0
    executed_count = 0
    skipped_count = 0
    status_counts: dict[str, int] = {}
    batch_start = _utc_now()
    max_workers = min(preview.plan.config.batch.max_concurrency, len(runnable_items))
    print(
        f"Starting batch worker pool "
        f"(runnable={len(runnable_items)}, max_concurrency={max_workers or 0})"
    )

    if max_workers <= 1:
        for preview_item in runnable_items:
            result = _execute_run_item(
                preview_item,
                batch_settings=preview.plan.config.batch,
                timeout_override=args.timeout,
            )
            results.append(result)
            completed += 1
            if result.skipped:
                skipped_count += 1
            else:
                executed_count += 1
            status_counts[result.overall_status] = status_counts.get(result.overall_status, 0) + 1
            _print_progress_line(
                index=completed,
                total=total_items,
                preview_item=preview_item,
                result=result,
                executed_count=executed_count,
                skipped_count=skipped_count,
                status_counts=status_counts,
            )
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {
                executor.submit(
                    _execute_run_item,
                    preview_item,
                    batch_settings=preview.plan.config.batch,
                    timeout_override=args.timeout,
                ): preview_item
                for preview_item in runnable_items
            }
            for future in concurrent.futures.as_completed(future_map):
                preview_item = future_map[future]
                result = future.result()
                results.append(result)
                completed += 1
                if result.skipped:
                    skipped_count += 1
                else:
                    executed_count += 1
                status_counts[result.overall_status] = status_counts.get(result.overall_status, 0) + 1
                _print_progress_line(
                    index=completed,
                    total=total_items,
                    preview_item=preview_item,
                    result=result,
                    executed_count=executed_count,
                    skipped_count=skipped_count,
                    status_counts=status_counts,
                )

    for preview_item in preview.items:
        if preview_item.action != "skip":
            continue
        result = RunExecutionResult(
            overall_status=preview_item.existing_overall_status or preview_item.artifact_state,
            skipped=True,
            output_dir=family_plan.run_output_dir(preview_item.item),
            exit_code=0 if preview_item.existing_overall_status == "success" else 1,
        )
        results.append(result)
        completed += 1
        skipped_count += 1
        status_counts[result.overall_status] = status_counts.get(result.overall_status, 0) + 1
        _print_progress_line(
            index=completed,
            total=total_items,
            preview_item=preview_item,
            result=result,
            executed_count=executed_count,
            skipped_count=skipped_count,
            status_counts=status_counts,
        )

    exit_code = 0
    for result in results:
        if not result.skipped and result.overall_status != "success":
            exit_code = 1

    batch_end = _utc_now()
    print("Batch summary:")
    print(f"  Total runs considered: {len(results)}")
    print(f"  Executed runs: {executed_count}")
    print(f"  Skipped runs: {skipped_count}")
    print(f"  Wall-clock seconds: {_duration_seconds(batch_start, batch_end)}")
    for status in sorted(status_counts):
        print(f"  {status}: {status_counts[status]}")
    return exit_code


def _run_interactive(
    args: argparse.Namespace,
    plan: family_plan.InteractivePlan,
) -> int:
    runtime = family_plan.load_runtime(plan.runtime_name)
    case_dir = _case_dir(plan.config.benchmark, plan.effective_split, plan.effective_case_id)
    if not case_dir.exists():
        raise SystemExit(f"Case directory does not exist: {case_dir}")

    assemble_specs = _assemble_specs_for_interactive(plan)
    collect_specs = _collect_specs_for_harnesses(
        plan.benchmark_profile.collect,
        plan.harnesses,
        namespace=len(plan.harnesses) > 1,
    )
    output_dir = family_plan.interactive_output_dir(plan)
    workspace_dir = family_plan.interactive_workspace_dir(plan)
    timeout_seconds = args.timeout or plan.config.timeout_seconds

    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    if workspace_dir.exists():
        shutil.rmtree(workspace_dir)

    print(f"Preparing interactive workspace at {workspace_dir}")
    with tempfile.TemporaryDirectory(prefix=f"astroreason-{family_plan.FAMILY_DIR.name}-runtime-") as runtime_tmp:
        runtime_state_dir = Path(runtime_tmp)
        roots = _prepare_mount_roots(workspace_dir, runtime_state_dir, output_dir)
        container_identity = _build_container_identity(runtime_state_dir)
        assembled_records = _assemble_workspace(
            assemble_specs,
            roots,
            benchmark=plan.config.benchmark,
            split=plan.effective_split,
            case_id=plan.effective_case_id,
        )
        cmd = _build_docker_command(
            runtime=runtime,
            roots=roots,
            container_identity=container_identity,
            resources=plan.config.resources,
            forward_env_keys=tuple(
                dict.fromkeys(
                    key
                    for harness in plan.harnesses
                    for key in harness.forward_env_keys
                )
            ),
            timeout_seconds=timeout_seconds,
            headless_shell_command=None,
            interactive=True,
        )
        print(f"Workspace ready at {workspace_dir}")
        start_time = _utc_now()
        exit_code, _, _, launched = _run_process(cmd, capture_output=False)
        end_time = _utc_now()

        solution_present = _copy_solution_artifact(workspace_dir, output_dir)
        collected_records = _collect_artifacts(collect_specs, roots, output_dir)
        if launched:
            if exit_code != 0:
                agent_status = "interactive_failed"
            elif solution_present:
                agent_status = "interactive_completed"
            else:
                agent_status = "interactive_no_solution"
        else:
            agent_status = "interactive_failed"

        verifier_outcome = VerifierOutcome(
            status="manual",
            result={"status": "manual", "present": solution_present},
        )
        overall_status = _write_run_metadata(
            mode="interactive",
            config_path=plan.config.config_path,
            benchmark=plan.config.benchmark,
            harness_identity=plan.interactive_identity,
            selected_harnesses=tuple(harness.harness for harness in plan.harnesses),
            runtime=runtime,
            output_dir=output_dir,
            split=plan.effective_split,
            case_id=plan.effective_case_id,
            assembled_records=assembled_records,
            collected_records=collected_records,
            start_time=start_time,
            end_time=end_time,
            agent_exit_code=exit_code,
            agent_status=agent_status,
            verifier_outcome=verifier_outcome,
            benchmark_profile_path=plan.benchmark_profile.profile_path,
            harness_profile_paths=tuple(harness.profile_path for harness in plan.harnesses),
            interactive=True,
        )
        _print_run_summary(output_dir, overall_status)
        return exit_code


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.rerun_status and args.no_skip_completed:
        raise SystemExit("--rerun-status and --no-skip-completed cannot be used together.")
    default_config = (
        family_plan.DEFAULT_INTERACTIVE_CONFIG if args.interactive else family_plan.DEFAULT_BATCH_CONFIG
    )
    config_path = (args.config or default_config).resolve()
    benchmark_filters = tuple(args.benchmark)
    harness_filters = tuple(args.harness)
    case_filters = tuple(args.case)

    if args.interactive:
        if args.rerun_status or args.no_skip_completed or args.max_concurrency is not None:
            raise SystemExit(
                "--rerun-status, --no-skip-completed, and --max-concurrency are batch-only controls and cannot be used with --interactive."
            )
        plan = family_plan.build_interactive_plan(
            config_path=config_path,
            benchmark_filters=benchmark_filters,
            harness_filters=harness_filters,
            split_override=args.split,
            case_filters=case_filters,
            require_real_configs=not args.dry_run,
        )
        if args.dry_run:
            print(family_plan.describe_interactive_plan(plan))
            return 0
        return _run_interactive(args, plan)

    plan = family_plan.build_batch_plan(
        config_path=config_path,
        benchmark_filters=benchmark_filters,
        harness_filters=harness_filters,
        split_override=args.split,
        case_filters=case_filters,
        max_concurrency_override=args.max_concurrency,
        require_real_configs=False,
    )
    preview = family_plan.build_batch_preview(
        plan,
        rerun_statuses=tuple(args.rerun_status),
        no_skip_completed=args.no_skip_completed,
    )
    _print_batch_preview(preview)
    if args.dry_run:
        return 0
    if plan.unavailable_configs:
        lines = ["Missing required harness config files:"]
        for harness, path in plan.unavailable_configs:
            lines.append(f"- {harness}: {path}")
        raise SystemExit("\n".join(lines))
    return _run_batch(args, preview)


if __name__ == "__main__":
    raise SystemExit(main())
