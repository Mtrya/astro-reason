#!/usr/bin/env python3
"""Run the prototype AstroReason experiment family."""

from __future__ import annotations

import argparse
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
from pathlib import Path, PurePosixPath
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
FAMILY_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = FAMILY_DIR / "configs" / "default.yaml"
WORKSPACE_MOUNT = Path("/app/workspace")
OUTPUT_MOUNT = Path("/app/run/output")
CONTAINER_HOME = Path("/tmp/astroreason-home")
CONTAINER_XDG_CONFIG_HOME = Path("/tmp/astroreason-xdg-config")
CONTAINER_XDG_DATA_HOME = Path("/tmp/astroreason-xdg-data")
CONTAINER_USER_NAME = "korolev"
CONTAINER_GROUP_NAME = "korolev"
RESULTS_ROOT = REPO_ROOT / "results" / "agent_runs"
INTERACTIVE_WORKSPACES_ROOT = REPO_ROOT / ".runtime" / "interactive_workspaces"
PROMPT_FILE_NAME = "PROMPT.md"
PLACEHOLDER_PATTERN = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


@dataclass(frozen=True)
class LogicalPath:
    root: str
    relative: Path


@dataclass(frozen=True)
class AssembleSpec:
    source: Path
    target: LogicalPath
    render: bool
    missing_ok: bool
    example: Path | None


@dataclass(frozen=True)
class CollectSpec:
    source: LogicalPath
    target: Path
    missing_ok: bool


@dataclass(frozen=True)
class ResourceLimits:
    cpus: str | None
    memory: str | None
    shm_size: str | None


@dataclass(frozen=True)
class FamilyConfig:
    family_name: str
    config_name: str
    benchmark: str
    runtime: str
    split: str
    case_id: str
    assemble: tuple[AssembleSpec, ...]
    collect: tuple[CollectSpec, ...]
    resources: ResourceLimits
    timeout_seconds_default: int | None
    interactive_command: tuple[str, ...]
    headless_shell_command: str
    config_path: Path


@dataclass(frozen=True)
class RuntimeManifest:
    name: str
    image: str
    dockerfile: Path
    build_context: Path
    runtime_dir: Path


@dataclass(frozen=True)
class VerifierOutcome:
    status: str
    result: dict[str, Any]


@dataclass(frozen=True)
class ContainerIdentity:
    username: str
    group_name: str
    passwd_file: Path
    group_file: Path


@dataclass(frozen=True)
class MountRoots:
    workspace: Path
    xdg_config: Path
    xdg_data: Path
    home: Path
    output: Path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the prototype AstroReason experiment")
    parser.add_argument(
        "--timeout",
        type=int,
        help="Override the experiment timeout in seconds for headless mode",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Prepare the workspace and open an interactive shell instead of running headless",
    )
    return parser.parse_args(argv)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _isoformat(value: datetime) -> str:
    return value.isoformat()


def _duration_seconds(start: datetime, end: datetime) -> float:
    return round((end - start).total_seconds(), 3)


def _load_yaml_mapping(path: Path, kind: str) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"{kind} file does not exist: {path}")

    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise SystemExit(f"Failed to parse {kind} file {path}: {exc}") from exc

    if not isinstance(data, dict):
        raise SystemExit(f"{kind} file must contain a mapping: {path}")
    return data


def _require_str(data: dict[str, Any], key: str, kind: str, path: Path) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise SystemExit(f"{kind} field '{key}' must be a non-empty string: {path}")
    return value


def _optional_bool(data: dict[str, Any], key: str, default: bool, kind: str, path: Path) -> bool:
    value = data.get(key, default)
    if not isinstance(value, bool):
        raise SystemExit(f"{kind} field '{key}' must be a boolean: {path}")
    return value


def _optional_int(
    data: dict[str, Any],
    key: str,
    default: int | None,
    kind: str,
    path: Path,
) -> int | None:
    value = data.get(key, default)
    if value is None:
        return None
    if not isinstance(value, int):
        raise SystemExit(f"{kind} field '{key}' must be an integer: {path}")
    return value


def _string_tuple(data: dict[str, Any], key: str, kind: str, path: Path) -> tuple[str, ...]:
    value = data.get(key)
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise SystemExit(f"{kind} field '{key}' must be a list of strings: {path}")
    return tuple(value)


def _optional_string(
    data: dict[str, Any],
    key: str,
    default: str | None,
    kind: str,
    path: Path,
) -> str | None:
    value = data.get(key, default)
    if value is None:
        return None
    if not isinstance(value, (str, int, float)) or value == "":
        raise SystemExit(f"{kind} field '{key}' must be a non-empty string or number: {path}")
    return str(value)


def _format_template_string(
    template: str,
    replacements: dict[str, str],
    *,
    label: str,
    path: Path,
    strict: bool = True,
) -> str:
    missing_keys: set[str] = set()

    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key in replacements:
            return replacements[key]
        if strict:
            missing_keys.add(key)
        return match.group(0)

    rendered = PLACEHOLDER_PATTERN.sub(replace, template)
    if missing_keys:
        missing = ", ".join(sorted(missing_keys))
        raise SystemExit(f"{label} contains unknown placeholder(s) {missing} in {path}")
    return rendered


def _resolve_repo_path(path_value: str) -> Path:
    candidate = Path(path_value)
    if candidate.is_absolute():
        return candidate
    return (REPO_ROOT / candidate).resolve()


def _parse_logical_path(path_value: str, *, label: str, path: Path) -> LogicalPath:
    pure = PurePosixPath(path_value)
    if pure.is_absolute():
        raise SystemExit(f"{label} must use a logical root, not an absolute path: {path}")
    if not pure.parts:
        raise SystemExit(f"{label} must be non-empty: {path}")

    root = pure.parts[0]
    if root not in {"workspace", "xdg_config", "xdg_data", "home", "output"}:
        raise SystemExit(
            f"{label} must start with one of workspace/, xdg_config/, xdg_data/, home/, output/: {path}"
        )
    relative = Path(*pure.parts[1:]) if len(pure.parts) > 1 else Path()
    return LogicalPath(root=root, relative=relative)


def _load_assemble_specs(
    data: dict[str, Any],
    config_path: Path,
    replacements: dict[str, str],
) -> tuple[AssembleSpec, ...]:
    items = data.get("assemble")
    if not isinstance(items, list) or not items:
        raise SystemExit(f"Family config field 'assemble' must be a non-empty list: {config_path}")

    specs: list[AssembleSpec] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise SystemExit(f"Family config assemble spec #{index} must be a mapping: {config_path}")

        source_value = _format_template_string(
            _require_str(item, "source", "Assemble spec", config_path),
            replacements,
            label=f"Assemble spec #{index} source",
            path=config_path,
        )
        target_value = _format_template_string(
            _require_str(item, "target", "Assemble spec", config_path),
            replacements,
            label=f"Assemble spec #{index} target",
            path=config_path,
        )
        example_value = item.get("example")
        if example_value is not None and (not isinstance(example_value, str) or not example_value):
            raise SystemExit(
                f"Assemble spec #{index} field 'example' must be a non-empty string when present: {config_path}"
            )

        specs.append(
            AssembleSpec(
                source=_resolve_repo_path(source_value),
                target=_parse_logical_path(
                    target_value,
                    label=f"Assemble spec #{index} target",
                    path=config_path,
                ),
                render=_optional_bool(item, "render", False, "Assemble spec", config_path),
                missing_ok=_optional_bool(item, "missing_ok", False, "Assemble spec", config_path),
                example=(
                    _resolve_repo_path(
                        _format_template_string(
                            example_value,
                            replacements,
                            label=f"Assemble spec #{index} example",
                            path=config_path,
                        )
                    )
                    if isinstance(example_value, str)
                    else None
                ),
            )
        )
    return tuple(specs)


def _load_collect_specs(
    data: dict[str, Any],
    config_path: Path,
    replacements: dict[str, str],
) -> tuple[CollectSpec, ...]:
    items = data.get("collect", [])
    if not isinstance(items, list):
        raise SystemExit(f"Family config field 'collect' must be a list: {config_path}")

    specs: list[CollectSpec] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise SystemExit(f"Family config collect spec #{index} must be a mapping: {config_path}")
        source_value = _format_template_string(
            _require_str(item, "source", "Collect spec", config_path),
            replacements,
            label=f"Collect spec #{index} source",
            path=config_path,
        )
        target_value = _format_template_string(
            _require_str(item, "target", "Collect spec", config_path),
            replacements,
            label=f"Collect spec #{index} target",
            path=config_path,
        )
        target = Path(PurePosixPath(target_value))
        if target.is_absolute():
            raise SystemExit(f"Collect spec #{index} target must be relative: {config_path}")

        specs.append(
            CollectSpec(
                source=_parse_logical_path(
                    source_value,
                    label=f"Collect spec #{index} source",
                    path=config_path,
                ),
                target=target,
                missing_ok=_optional_bool(item, "missing_ok", True, "Collect spec", config_path),
            )
        )
    return tuple(specs)


def _load_resource_limits(data: dict[str, Any], config_path: Path) -> ResourceLimits:
    resources = data.get("resources", {})
    if not isinstance(resources, dict):
        raise SystemExit(f"Family config field 'resources' must be a mapping: {config_path}")
    return ResourceLimits(
        cpus=_optional_string(resources, "cpus", None, "Family config resources", config_path),
        memory=_optional_string(resources, "memory", None, "Family config resources", config_path),
        shm_size=_optional_string(resources, "shm_size", None, "Family config resources", config_path),
    )


def load_family_config(config_path: Path) -> FamilyConfig:
    data = _load_yaml_mapping(config_path, "Family config")
    benchmark = _require_str(data, "benchmark", "Family config", config_path)
    split = _require_str(data, "split", "Family config", config_path)
    case_id = _require_str(data, "case", "Family config", config_path)
    replacements = {
        "benchmark": benchmark,
        "split": split,
        "case_id": case_id,
        "family": FAMILY_DIR.name,
        "config_name": config_path.stem,
    }

    return FamilyConfig(
        family_name=FAMILY_DIR.name,
        config_name=config_path.stem,
        benchmark=benchmark,
        runtime=_require_str(data, "runtime", "Family config", config_path),
        split=split,
        case_id=case_id,
        assemble=_load_assemble_specs(data, config_path, replacements),
        collect=_load_collect_specs(data, config_path, replacements),
        resources=_load_resource_limits(data, config_path),
        timeout_seconds_default=_optional_int(
            data, "timeout_seconds_default", None, "Family config", config_path
        ),
        interactive_command=_string_tuple(
            data,
            "interactive_command",
            "Family config",
            config_path,
        ),
        headless_shell_command=_require_str(
            data,
            "headless_shell_command",
            "Family config",
            config_path,
        ),
        config_path=config_path,
    )


def load_runtime(name: str) -> RuntimeManifest:
    manifest_path = REPO_ROOT / "runtimes" / name / "runtime.yaml"
    data = _load_yaml_mapping(manifest_path, "Runtime manifest")

    runtime_name = _require_str(data, "name", "Runtime manifest", manifest_path)
    if runtime_name != name:
        raise SystemExit(
            f"Runtime manifest name mismatch: expected '{name}', found '{runtime_name}' in {manifest_path}"
        )

    runtime_dir = manifest_path.parent
    dockerfile = runtime_dir / _require_str(data, "dockerfile", "Runtime manifest", manifest_path)
    build_context = runtime_dir / _require_str(
        data, "build_context", "Runtime manifest", manifest_path
    )
    if not dockerfile.exists():
        raise SystemExit(f"Runtime dockerfile does not exist: {dockerfile}")
    if not build_context.exists():
        raise SystemExit(f"Runtime build context does not exist: {build_context}")

    return RuntimeManifest(
        name=runtime_name,
        image=_require_str(data, "image", "Runtime manifest", manifest_path),
        dockerfile=dockerfile.resolve(),
        build_context=build_context.resolve(),
        runtime_dir=runtime_dir,
    )


def _benchmark_root(benchmark: str) -> Path:
    return REPO_ROOT / "benchmarks" / benchmark


def _benchmark_dir(config: FamilyConfig) -> Path:
    return _benchmark_root(config.benchmark)


def _case_dir(config: FamilyConfig) -> Path:
    return _benchmark_dir(config) / "dataset" / "cases" / config.split / config.case_id


def _family_relpath() -> Path:
    return FAMILY_DIR.relative_to(REPO_ROOT)


def _output_dir(config: FamilyConfig) -> Path:
    return RESULTS_ROOT / _family_relpath() / config.config_name / config.split / config.case_id


def _interactive_workspace_dir(config: FamilyConfig) -> Path:
    return INTERACTIVE_WORKSPACES_ROOT / _family_relpath() / config.config_name / config.split / config.case_id


def _example_solution_path(config: FamilyConfig) -> Path | None:
    dataset_dir = _benchmark_dir(config) / "dataset"
    for candidate in ("example_solution.json", "example_solution.yaml", "example_solution.yml"):
        path = dataset_dir / candidate
        if path.exists():
            return path.resolve()
    return None


def _verifier_path(config: FamilyConfig) -> Path | None:
    benchmark_dir = _benchmark_dir(config)
    verifier_dir = benchmark_dir / "verifier"
    verifier_py = benchmark_dir / "verifier.py"
    if verifier_dir.is_dir():
        return verifier_dir.resolve()
    if verifier_py.exists():
        return verifier_py.resolve()
    return None


def _logical_target_host_path(target: LogicalPath, roots: MountRoots) -> Path:
    root_map = {
        "workspace": roots.workspace,
        "xdg_config": roots.xdg_config,
        "xdg_data": roots.xdg_data,
        "home": roots.home,
        "output": roots.output,
    }
    return root_map[target.root] / target.relative


def _logical_target_container_path(target: LogicalPath) -> Path:
    root_map = {
        "workspace": WORKSPACE_MOUNT,
        "xdg_config": CONTAINER_XDG_CONFIG_HOME,
        "xdg_data": CONTAINER_XDG_DATA_HOME,
        "home": CONTAINER_HOME,
        "output": OUTPUT_MOUNT,
    }
    return root_map[target.root] / target.relative


def _logical_source_host_path(source: LogicalPath, roots: MountRoots) -> Path:
    return _logical_target_host_path(source, roots)


def _container_prompt_path() -> Path:
    return WORKSPACE_MOUNT / PROMPT_FILE_NAME


def _workspace_module_name(relative: Path) -> str:
    return ".".join(part for part in relative.parts if part)


def _workspace_example_solution_name(config: FamilyConfig) -> str:
    example_solution = _example_solution_path(config)
    if example_solution is None:
        return "No example solution is provided for this benchmark."

    for spec in config.assemble:
        if spec.source == example_solution and spec.source.exists() and spec.target.root == "workspace":
            target_name = spec.target.relative.name or example_solution.name
            return target_name
    return "No example solution is provided for this experiment."


def _workspace_verifier_info(config: FamilyConfig) -> tuple[str, str]:
    verifier = _verifier_path(config)
    if verifier is None:
        return "Verifier is not exposed in this experiment.", "No verifier helper is available in this workspace."

    for spec in config.assemble:
        if spec.source != verifier or not spec.source.exists() or spec.target.root != "workspace":
            continue

        relative = spec.target.relative
        location = relative.as_posix() + ("/" if verifier.is_dir() else "")
        if verifier.is_dir():
            module_name = _workspace_module_name(relative)
            command = f"python -m {module_name}.run case/ solution.json"
        else:
            command = f"python {relative.as_posix()} case/ solution.json"
        return location, command

    return "Verifier is not exposed in this experiment.", "No verifier helper is available in this workspace."


def _template_context(config: FamilyConfig) -> dict[str, str]:
    verifier_location, verifier_command = _workspace_verifier_info(config)
    return {
        "benchmark": config.benchmark,
        "case_id": config.case_id,
        "split": config.split,
        "example_solution_name": _workspace_example_solution_name(config),
        "verifier_location": verifier_location,
        "verifier_command": verifier_command,
    }


def _copy_file_or_directory(source: Path, destination: Path, *, render: bool, context: dict[str, str]) -> None:
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
        rendered = _format_template_string(
            source.read_text(encoding="utf-8"),
            context,
            label=f"Rendered file {source}",
            path=source,
            strict=False,
        )
        destination.write_text(rendered, encoding="utf-8")
        return
    shutil.copy2(source, destination)


def _assemble_workspace(config: FamilyConfig, roots: MountRoots) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    context = _template_context(config)

    for spec in config.assemble:
        source_exists = spec.source.exists()
        if not source_exists:
            if spec.missing_ok:
                records.append(
                    {
                        "source": spec.source.relative_to(REPO_ROOT).as_posix()
                        if spec.source.is_relative_to(REPO_ROOT)
                        else str(spec.source),
                        "target": _logical_target_container_path(spec.target).as_posix(),
                        "present": False,
                        "rendered": spec.render,
                    }
                )
                continue
            example_note = f" Copy the example file {spec.example} and fill it in." if spec.example else ""
            raise SystemExit(f"Required assemble source does not exist: {spec.source}.{example_note}")

        destination = _logical_target_host_path(spec.target, roots)
        _copy_file_or_directory(spec.source, destination, render=spec.render, context=context)
        records.append(
            {
                "source": spec.source.relative_to(REPO_ROOT).as_posix()
                if spec.source.is_relative_to(REPO_ROOT)
                else str(spec.source),
                "target": _logical_target_container_path(spec.target).as_posix(),
                "present": True,
                "rendered": spec.render,
            }
        )

    return records


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


def _build_container_script(
    config: FamilyConfig,
    timeout: int,
    *,
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
        lines.append(f"exec {shlex.join(config.interactive_command)}")
        return "\n".join(lines)

    lines.append(
        f"exec timeout --signal=TERM {timeout} /bin/bash -lc {shlex.quote(config.headless_shell_command)}"
    )
    return "\n".join(lines)


def _build_docker_command(
    runtime: RuntimeManifest,
    args: argparse.Namespace,
    roots: MountRoots,
    container_identity: ContainerIdentity,
    timeout: int,
    config: FamilyConfig,
) -> list[str]:
    cmd = ["docker", "run", "--rm", "-w", str(WORKSPACE_MOUNT)]
    cmd.extend(["--user", f"{os.getuid()}:{os.getgid()}"])
    cmd.extend(["-e", f"HOME={CONTAINER_HOME}"])
    cmd.extend(["-e", f"USER={container_identity.username}"])
    cmd.extend(["-e", f"LOGNAME={container_identity.username}"])
    cmd.extend(["-e", f"XDG_CONFIG_HOME={CONTAINER_XDG_CONFIG_HOME}"])
    cmd.extend(["-e", f"XDG_DATA_HOME={CONTAINER_XDG_DATA_HOME}"])
    if config.resources.cpus is not None:
        cmd.extend(["--cpus", config.resources.cpus])
    if config.resources.memory is not None:
        cmd.extend(["--memory", config.resources.memory])
    if config.resources.shm_size is not None:
        cmd.extend(["--shm-size", config.resources.shm_size])
    if args.interactive:
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
            f"{roots.xdg_config.resolve()}:{CONTAINER_XDG_CONFIG_HOME}",
            "-v",
            f"{roots.xdg_data.resolve()}:{CONTAINER_XDG_DATA_HOME}",
            "-v",
            f"{roots.home.resolve()}:{CONTAINER_HOME}",
            "-v",
            f"{container_identity.passwd_file.resolve()}:/etc/passwd:ro",
            "-v",
            f"{container_identity.group_file.resolve()}:/etc/group:ro",
        ]
    )

    shell_script = _build_container_script(config, timeout, interactive=args.interactive)
    cmd.append(runtime.image)
    cmd.extend(["/bin/bash", "-lc", shell_script])
    return cmd


def _check_required_paths(config: FamilyConfig) -> Path:
    benchmark_dir = _benchmark_dir(config)
    if not benchmark_dir.exists():
        raise SystemExit(f"Benchmark directory does not exist: {benchmark_dir}")

    case_dir = _case_dir(config)
    if not case_dir.exists():
        raise SystemExit(f"Case directory does not exist: {case_dir}")

    for spec in config.assemble:
        if spec.example is not None and not spec.example.exists():
            raise SystemExit(f"Example file does not exist: {spec.example}")
        if spec.source.exists():
            continue
        if spec.missing_ok:
            continue
        example_note = f" Copy the example file {spec.example} and fill it in." if spec.example else ""
        raise SystemExit(f"Required assemble source does not exist: {spec.source}.{example_note}")

    return case_dir


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _copy_solution_artifact(workspace_dir: Path, output_dir: Path) -> bool:
    solution_src = workspace_dir / "solution.json"
    solution_dst = output_dir / "solution.json"
    if not solution_src.exists():
        return False
    shutil.copy2(solution_src, solution_dst)
    return True


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
    cwd: Path | None = None,
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
                    cwd=cwd,
                )
    except FileNotFoundError as exc:
        stderr_path.write_text(f"Failed to launch process: {exc}\n", encoding="utf-8")
        if not stdout_path.exists():
            stdout_path.write_text("", encoding="utf-8")
        return 127, str(exc), False

    return result.returncode, "", True


def _collect_artifacts(config: FamilyConfig, roots: MountRoots, output_dir: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for spec in config.collect:
        source = _logical_source_host_path(spec.source, roots)
        destination = output_dir / spec.target
        if not source.exists():
            if spec.missing_ok:
                records.append(
                    {
                        "source": _logical_target_container_path(spec.source).as_posix(),
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
                "source": _logical_target_container_path(spec.source).as_posix(),
                "target": spec.target.as_posix(),
                "present": True,
            }
        )
    return records


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


def _verifier_command(config: FamilyConfig, case_dir: Path, solution_path: Path) -> list[str]:
    verifier_path = _verifier_path(config)
    if verifier_path is None:
        raise SystemExit(f"No verifier found for benchmark {config.benchmark}")

    if verifier_path.is_dir():
        return [
            "uv",
            "run",
            "python",
            "-m",
            f"benchmarks.{config.benchmark}.verifier.run",
            str(case_dir),
            str(solution_path),
        ]
    return [
        "uv",
        "run",
        "python",
        str(verifier_path),
        str(case_dir),
        str(solution_path),
    ]


def _run_external_verifier(
    config: FamilyConfig,
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
    cmd = _verifier_command(config, case_dir, solution_path)
    exit_code, stdout, stderr, launched = _run_process(
        cmd,
        capture_output=True,
        cwd=REPO_ROOT,
    )
    if not launched:
        return VerifierOutcome(
            status="error",
            result={"status": "error", "error": stderr.strip() or "Failed to launch verifier."},
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


def _write_run_metadata(
    config: FamilyConfig,
    runtime: RuntimeManifest,
    output_dir: Path,
    assembled_records: list[dict[str, Any]],
    collected_records: list[dict[str, Any]],
    start_time: datetime,
    end_time: datetime,
    agent_exit_code: int,
    agent_status: str,
    verifier_outcome: VerifierOutcome,
    *,
    interactive: bool,
) -> None:
    artifacts = {
        "solution.json": (output_dir / "solution.json").exists(),
        "agent_stdout.txt": (output_dir / "agent_stdout.txt").exists(),
        "agent_stderr.txt": (output_dir / "agent_stderr.txt").exists(),
        "run.json": True,
    }
    for record in collected_records:
        artifacts[record["target"]] = bool(record["present"])

    run_data = {
        "benchmark": config.benchmark,
        "experiment": _family_relpath().as_posix(),
        "config_name": config.config_name,
        "runtime": runtime.name,
        "case_id": config.case_id,
        "split": config.split,
        "overall_status": _overall_status(agent_status, verifier_outcome.status, interactive),
        "agent_status": agent_status,
        "verifier_status": verifier_outcome.status,
        "start_time": _isoformat(start_time),
        "end_time": _isoformat(end_time),
        "duration_seconds": _duration_seconds(start_time, end_time),
        "container_image": runtime.image,
        "agent_exit_code": agent_exit_code,
        "artifacts": artifacts,
        "assembly": {
            "family_config": config.config_path.relative_to(REPO_ROOT).as_posix(),
            "assemble": assembled_records,
            "collect": collected_records,
        },
        "verifier": verifier_outcome.result,
    }
    _write_text(output_dir / "run.json", json.dumps(run_data, indent=2, sort_keys=True) + "\n")


def _headless_exit_code(overall_status: str) -> int:
    return 0 if overall_status == "success" else 1


def _print_run_summary(output_dir: Path, overall_status: str) -> None:
    print(f"Results written to {output_dir}")
    print(f"Run status: {overall_status}")


def _prepare_mount_roots(workspace_dir: Path, runtime_state_dir: Path, output_dir: Path) -> MountRoots:
    roots = MountRoots(
        workspace=workspace_dir,
        xdg_config=runtime_state_dir / "xdg_config",
        xdg_data=runtime_state_dir / "xdg_data",
        home=runtime_state_dir / "home",
        output=output_dir,
    )
    roots.workspace.mkdir(parents=True, exist_ok=True)
    roots.xdg_config.mkdir(parents=True, exist_ok=True)
    roots.xdg_data.mkdir(parents=True, exist_ok=True)
    roots.home.mkdir(parents=True, exist_ok=True)
    roots.output.mkdir(parents=True, exist_ok=True)
    return roots


def _run_interactive(
    config: FamilyConfig,
    runtime: RuntimeManifest,
    args: argparse.Namespace,
    output_dir: Path,
) -> int:
    timeout = args.timeout or config.timeout_seconds_default or 1800
    workspace_dir = _interactive_workspace_dir(config)
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    if workspace_dir.exists():
        shutil.rmtree(workspace_dir)

    print(f"Preparing interactive workspace at {workspace_dir}")
    with tempfile.TemporaryDirectory(prefix=f"astroreason-{config.family_name}-runtime-") as runtime_tmp:
        runtime_state_dir = Path(runtime_tmp)
        roots = _prepare_mount_roots(workspace_dir, runtime_state_dir, output_dir)
        container_identity = _build_container_identity(runtime_state_dir)
        assembled_records = _assemble_workspace(config, roots)
        cmd = _build_docker_command(
            runtime,
            args,
            roots,
            container_identity,
            timeout,
            config,
        )
        print(f"Workspace ready at {workspace_dir}")
        start_time = _utc_now()
        exit_code, _, _, launched = _run_process(cmd, capture_output=False)
        end_time = _utc_now()

        solution_present = _copy_solution_artifact(workspace_dir, output_dir)
        collected_records = _collect_artifacts(config, roots, output_dir)
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
        _write_run_metadata(
            config,
            runtime,
            output_dir,
            assembled_records,
            collected_records,
            start_time,
            end_time,
            exit_code,
            agent_status,
            verifier_outcome,
            interactive=True,
        )
        overall_status = _overall_status(agent_status, verifier_outcome.status, True)
        _print_run_summary(output_dir, overall_status)
        return exit_code


def _run_headless(
    config: FamilyConfig,
    runtime: RuntimeManifest,
    args: argparse.Namespace,
    case_dir: Path,
    output_dir: Path,
) -> int:
    timeout = args.timeout or config.timeout_seconds_default or 1800
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix=f"astroreason-{config.family_name}-workspace-") as workspace_tmp:
        with tempfile.TemporaryDirectory(prefix=f"astroreason-{config.family_name}-runtime-") as runtime_tmp:
            workspace_dir = Path(workspace_tmp)
            runtime_state_dir = Path(runtime_tmp)
            roots = _prepare_mount_roots(workspace_dir, runtime_state_dir, output_dir)
            container_identity = _build_container_identity(runtime_state_dir)
            assembled_records = _assemble_workspace(config, roots)
            cmd = _build_docker_command(
                runtime,
                args,
                roots,
                container_identity,
                timeout,
                config,
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
            collected_records = _collect_artifacts(config, roots, output_dir)
            agent_status = _agent_status(exit_code, solution_present, launched)
            verifier_outcome = _run_external_verifier(
                config,
                case_dir,
                output_dir,
                solution_present=solution_present,
            )
            _write_run_metadata(
                config,
                runtime,
                output_dir,
                assembled_records,
                collected_records,
                start_time,
                end_time,
                exit_code,
                agent_status,
                verifier_outcome,
                interactive=False,
            )
            overall_status = _overall_status(agent_status, verifier_outcome.status, False)
            _print_run_summary(output_dir, overall_status)
            return _headless_exit_code(overall_status)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config = load_family_config(DEFAULT_CONFIG_PATH)
    runtime = load_runtime(config.runtime)
    case_dir = _check_required_paths(config)
    output_dir = _output_dir(config)

    if args.interactive:
        return _run_interactive(config, runtime, args, output_dir)
    return _run_headless(config, runtime, args, case_dir, output_dir)


if __name__ == "__main__":
    raise SystemExit(main())
