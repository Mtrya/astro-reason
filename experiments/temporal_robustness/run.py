#!/usr/bin/env python3
"""Run the AEOSSP temporal robustness ablation."""

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
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
FAMILY_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG = FAMILY_DIR / "configs" / "default.yaml"
INTERACTIVE_CONFIG = FAMILY_DIR / "configs" / "interactive.yaml"
WORKSPACE_MOUNT = Path("/app/workspace")
OUTPUT_MOUNT = Path("/app/run/output")
CONTAINER_HOME = Path("/home/korolev")
INTERACTIVE_WORKSPACES_ROOT = REPO_ROOT / ".runtime" / "interactive_workspaces"
OPAQUE_ARTIFACT_ROOT = REPO_ROOT / "experiments" / "_fragments" / "opaque_verifiers" / "artifacts"
OPAQUE_BUILD_SCRIPT = REPO_ROOT / "experiments" / "_fragments" / "opaque_verifiers" / "build.py"
PLACEHOLDER_PATTERN = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


@dataclass(frozen=True)
class AssembleSpec:
    source: Path
    target: Path
    render: bool = False
    missing_ok: bool = False
    example: Path | None = None


@dataclass(frozen=True)
class CollectSpec:
    source: Path
    target: Path
    missing_ok: bool = True


@dataclass(frozen=True)
class ResourceLimits:
    cpus: str | None
    memory: str | None
    shm_size: str | None


@dataclass(frozen=True)
class BatchSettings:
    max_concurrency: int
    max_retries: int
    skip_completed: bool
    retry_statuses: tuple[str, ...]


@dataclass(frozen=True)
class ResultSettings:
    root: Path
    aggregate_dir: Path


@dataclass(frozen=True)
class FamilyConfig:
    name: str
    mode: str
    benchmark: str
    splits: tuple[str, ...]
    cases: tuple[str, ...]
    harnesses: tuple[str, ...]
    timeout_seconds: int
    batch: BatchSettings
    resources: ResourceLimits
    results: ResultSettings
    config_path: Path


@dataclass(frozen=True)
class InteractiveConfig:
    name: str
    mode: str
    benchmark: str
    split: str
    case_id: str
    harnesses: tuple[str, ...]
    timeout_seconds: int
    resources: ResourceLimits
    results: ResultSettings
    config_path: Path


@dataclass(frozen=True)
class HarnessProfile:
    harness: str
    runtime: str
    assemble: tuple[AssembleSpec, ...]
    collect: tuple[CollectSpec, ...]
    forward_env_keys: tuple[str, ...]
    headless_shell_command: str
    profile_path: Path


@dataclass(frozen=True)
class RuntimeManifest:
    name: str
    image: str


@dataclass(frozen=True)
class RunItem:
    config_name: str
    config_path: Path
    benchmark: str
    split: str
    case_id: str
    harness: str
    profile: HarnessProfile
    timeout_seconds: int
    resources: ResourceLimits
    results_root: Path


@dataclass(frozen=True)
class MountRoots:
    workspace: Path
    home: Path
    output: Path


@dataclass(frozen=True)
class ContainerIdentity:
    passwd_file: Path
    group_file: Path


@dataclass(frozen=True)
class RunResult:
    overall_status: str
    skipped: bool
    output_dir: Path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the temporal robustness ablation")
    parser.add_argument("--config", type=Path, help="Override the family config path.")
    parser.add_argument("--interactive", action="store_true", help="Prepare one interactive workspace.")
    parser.add_argument("--split", action="append", default=[], help="Limit to a split. May be repeated.")
    parser.add_argument("--case", action="append", default=[], help="Limit to a case id. May be repeated.")
    parser.add_argument("--harness", action="append", default=[], help="Limit to a harness. May be repeated.")
    parser.add_argument("--timeout", type=int, help="Override configured timeout seconds.")
    parser.add_argument("--max-concurrency", type=int, help="Override batch.max_concurrency.")
    parser.add_argument("--rerun-status", action="append", default=[], help="Rerun stored statuses.")
    parser.add_argument("--no-skip-completed", action="store_true", help="Run selected items regardless of status.")
    parser.add_argument("--dry-run", action="store_true", help="Preview selected work without executing it.")
    return parser.parse_args(argv)


def _load_yaml(path: Path, label: str) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"{label} does not exist: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit(f"{label} must be a mapping: {path}")
    return data


def _require_str(data: dict[str, Any], key: str, label: str, path: Path) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise SystemExit(f"{label}.{key} must be a non-empty string: {path}")
    return value


def _string_tuple(data: dict[str, Any], key: str, label: str, path: Path) -> tuple[str, ...]:
    value = data.get(key)
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        raise SystemExit(f"{label}.{key} must be a list of non-empty strings: {path}")
    return tuple(value)


def _repo_path(path_text: str) -> Path:
    path = Path(path_text)
    return path.resolve() if path.is_absolute() else (REPO_ROOT / path).resolve()


def _container_path(path_text: str) -> Path:
    path = Path(path_text)
    if not path.is_absolute():
        raise SystemExit(f"Container path must be absolute: {path_text}")
    return path


def _resource_limits(data: dict[str, Any]) -> ResourceLimits:
    raw = data.get("resources", {})
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise SystemExit("resources must be a mapping")
    return ResourceLimits(
        cpus=str(raw["cpus"]) if raw.get("cpus") is not None else None,
        memory=str(raw["memory"]) if raw.get("memory") is not None else None,
        shm_size=str(raw["shm_size"]) if raw.get("shm_size") is not None else None,
    )


def _result_settings(data: dict[str, Any], path: Path) -> ResultSettings:
    raw = data.get("results")
    if not isinstance(raw, dict):
        raise SystemExit(f"results must be a mapping: {path}")
    root = _repo_path(_require_str(raw, "root", "results", path))
    aggregate_text = raw.get("aggregate_dir", "summaries")
    if not isinstance(aggregate_text, str) or not aggregate_text:
        raise SystemExit(f"results.aggregate_dir must be a non-empty string: {path}")
    aggregate_dir = Path(aggregate_text)
    if not aggregate_dir.is_absolute():
        aggregate_dir = root / aggregate_dir
    return ResultSettings(root=root, aggregate_dir=aggregate_dir.resolve())


def _batch_settings(data: dict[str, Any], path: Path) -> BatchSettings:
    raw = data.get("batch", {})
    if not isinstance(raw, dict):
        raise SystemExit(f"batch must be a mapping: {path}")
    max_concurrency = int(raw.get("max_concurrency", 1))
    max_retries = int(raw.get("max_retries", 0))
    if max_concurrency <= 0:
        raise SystemExit("batch.max_concurrency must be positive")
    if max_retries < 0:
        raise SystemExit("batch.max_retries must be non-negative")
    retry_statuses = raw.get("retry_statuses", [])
    if not isinstance(retry_statuses, list):
        raise SystemExit("batch.retry_statuses must be a list")
    return BatchSettings(
        max_concurrency=max_concurrency,
        max_retries=max_retries,
        skip_completed=bool(raw.get("skip_completed", True)),
        retry_statuses=tuple(str(item) for item in retry_statuses),
    )


def load_family_config(path: Path) -> FamilyConfig:
    data = _load_yaml(path, "Family config")
    mode = _require_str(data, "mode", "Family config", path)
    if mode != "batch":
        raise SystemExit(f"Expected batch config, found mode={mode!r}: {path}")
    return FamilyConfig(
        name=_require_str(data, "name", "Family config", path),
        mode=mode,
        benchmark=_require_str(data, "benchmark", "Family config", path),
        splits=_string_tuple(data, "splits", "Family config", path),
        cases=_string_tuple(data, "cases", "Family config", path),
        harnesses=_string_tuple(data, "harnesses", "Family config", path),
        timeout_seconds=int(data.get("timeout_seconds", 7200)),
        batch=_batch_settings(data, path),
        resources=_resource_limits(data),
        results=_result_settings(data, path),
        config_path=path.resolve(),
    )


def load_interactive_config(path: Path) -> InteractiveConfig:
    data = _load_yaml(path, "Interactive config")
    mode = _require_str(data, "mode", "Interactive config", path)
    if mode != "interactive":
        raise SystemExit(f"Expected interactive config, found mode={mode!r}: {path}")
    return InteractiveConfig(
        name=_require_str(data, "name", "Interactive config", path),
        mode=mode,
        benchmark=_require_str(data, "benchmark", "Interactive config", path),
        split=_require_str(data, "split", "Interactive config", path),
        case_id=_require_str(data, "case", "Interactive config", path),
        harnesses=_string_tuple(data, "harnesses", "Interactive config", path),
        timeout_seconds=int(data.get("timeout_seconds", 7200)),
        resources=_resource_limits(data),
        results=_result_settings(data, path),
        config_path=path.resolve(),
    )


def _parse_assemble(items: Any, path: Path) -> tuple[AssembleSpec, ...]:
    if not isinstance(items, list):
        raise SystemExit(f"assemble must be a list: {path}")
    specs: list[AssembleSpec] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise SystemExit(f"assemble[{index}] must be a mapping: {path}")
        example_text = item.get("example")
        specs.append(
            AssembleSpec(
                source=_repo_path(_require_str(item, "source", "assemble", path)),
                target=_container_path(_require_str(item, "target", "assemble", path)),
                render=bool(item.get("render", False)),
                missing_ok=bool(item.get("missing_ok", False)),
                example=_repo_path(example_text) if isinstance(example_text, str) else None,
            )
        )
    return tuple(specs)


def _parse_collect(items: Any, path: Path) -> tuple[CollectSpec, ...]:
    if not isinstance(items, list):
        raise SystemExit(f"collect must be a list: {path}")
    specs: list[CollectSpec] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise SystemExit(f"collect[{index}] must be a mapping: {path}")
        specs.append(
            CollectSpec(
                source=_container_path(_require_str(item, "source", "collect", path)),
                target=Path(_require_str(item, "target", "collect", path)),
                missing_ok=bool(item.get("missing_ok", True)),
            )
        )
    return tuple(specs)


def load_harness_profile(name: str) -> HarnessProfile:
    path = FAMILY_DIR / "harnesses" / f"{name}.yaml"
    data = _load_yaml(path, "Harness profile")
    harness = _require_str(data, "harness", "Harness profile", path)
    if harness != name:
        raise SystemExit(f"Harness profile mismatch in {path}: {harness}")
    commands = data.get("commands")
    if not isinstance(commands, dict):
        raise SystemExit(f"commands must be a mapping: {path}")
    forward_env_keys = data.get("forward_env_keys", [])
    if not isinstance(forward_env_keys, list):
        raise SystemExit(f"forward_env_keys must be a list: {path}")
    return HarnessProfile(
        harness=harness,
        runtime=_require_str(data, "runtime", "Harness profile", path),
        assemble=_parse_assemble(data.get("assemble"), path),
        collect=_parse_collect(data.get("collect", []), path),
        forward_env_keys=tuple(str(item) for item in forward_env_keys),
        headless_shell_command=_require_str(commands, "headless_shell_command", "commands", path),
        profile_path=path.resolve(),
    )


def load_runtime(name: str) -> RuntimeManifest:
    path = REPO_ROOT / "runtimes" / name / "runtime.yaml"
    data = _load_yaml(path, "Runtime manifest")
    runtime_name = _require_str(data, "name", "Runtime manifest", path)
    if runtime_name != name:
        raise SystemExit(f"Runtime manifest mismatch in {path}: {runtime_name}")
    return RuntimeManifest(name=runtime_name, image=_require_str(data, "image", "Runtime manifest", path))


def _select(configured: tuple[str, ...], requested: tuple[str, ...], label: str) -> tuple[str, ...]:
    if not requested:
        return configured
    unknown = [item for item in requested if item not in configured]
    if unknown:
        raise SystemExit(f"Unknown {label}(s): {', '.join(unknown)}")
    requested_set = set(requested)
    return tuple(item for item in configured if item in requested_set)


def _case_dir(benchmark: str, split: str, case_id: str) -> Path:
    return REPO_ROOT / "benchmarks" / benchmark / "dataset" / "cases" / split / case_id


def _validate_cases(benchmark: str, splits: tuple[str, ...], cases: tuple[str, ...]) -> None:
    for split in splits:
        for case_id in cases:
            case_dir = _case_dir(benchmark, split, case_id)
            if not case_dir.is_dir():
                raise SystemExit(f"Case directory does not exist: {case_dir}")


def _benchmark_assemble_specs(benchmark: str, split: str, case_id: str) -> tuple[AssembleSpec, ...]:
    return (
        AssembleSpec(
            source=REPO_ROOT / "experiments" / "_fragments" / "prompts" / benchmark / "README.default.md",
            target=WORKSPACE_MOUNT / "README.md",
            render=True,
        ),
        AssembleSpec(source=_case_dir(benchmark, split, case_id), target=WORKSPACE_MOUNT / "case"),
        AssembleSpec(
            source=OPAQUE_ARTIFACT_ROOT / benchmark / "verifier",
            target=WORKSPACE_MOUNT / "verifier",
        ),
        AssembleSpec(
            source=REPO_ROOT / "experiments" / "_fragments" / "prompts" / benchmark / "PROMPT.default.md",
            target=CONTAINER_HOME / "PROMPT.md",
            render=True,
        ),
        AssembleSpec(
            source=REPO_ROOT
            / "experiments"
            / "_fragments"
            / "prompts"
            / "_shared"
            / "AGENTS.main_agentic.default.md",
            target=WORKSPACE_MOUNT / "AGENTS.md",
            render=True,
        ),
    )


def _output_dir(item: RunItem) -> Path:
    return item.results_root / item.config_name / item.split / item.benchmark / item.harness / item.case_id


def _interactive_workspace_dir(config: InteractiveConfig, harness_identity: str, split: str, case_id: str) -> Path:
    return (
        INTERACTIVE_WORKSPACES_ROOT
        / "experiments"
        / "temporal_robustness"
        / config.config_path.stem
        / config.benchmark
        / harness_identity
        / split
        / case_id
    )


def _interactive_output_dir(config: InteractiveConfig, harness_identity: str, split: str, case_id: str) -> Path:
    return config.results.root / config.config_path.stem / split / config.benchmark / harness_identity / case_id


def _relative(path: Path) -> str:
    if path.is_relative_to(REPO_ROOT):
        return path.relative_to(REPO_ROOT).as_posix()
    return path.as_posix()


def _opaque_benchmark(path: Path) -> str | None:
    try:
        relative = path.resolve().relative_to(OPAQUE_ARTIFACT_ROOT)
    except ValueError:
        return None
    return relative.parts[0] if relative.parts else None


def _opaque_rebuild_command(benchmark: str) -> str:
    return (
        "uv run python "
        f"{OPAQUE_BUILD_SCRIPT.relative_to(REPO_ROOT).as_posix()} --benchmark {benchmark}"
    )


def _validate_opaque_artifact(path: Path) -> None:
    benchmark = _opaque_benchmark(path)
    if benchmark is None:
        return
    metadata_path = path.parent / "build.json"
    if not metadata_path.exists():
        raise SystemExit(
            f"Opaque verifier metadata is missing: {metadata_path}. "
            f"Rebuild it with: {_opaque_rebuild_command(benchmark)}"
        )
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(
            f"Opaque verifier metadata is malformed: {metadata_path}. "
            f"Rebuild it with: {_opaque_rebuild_command(benchmark)}"
        ) from exc
    if not isinstance(metadata, dict) or metadata.get("build_target") != "runtime_docker_image":
        raise SystemExit(
            f"Opaque verifier artifact is stale or host-built: {path}. "
            f"Rebuild it with: {_opaque_rebuild_command(benchmark)}"
        )


def _example_solution_name(benchmark: str) -> str:
    dataset_dir = REPO_ROOT / "benchmarks" / benchmark / "dataset"
    for candidate in ("example_solution.json", "example_solution.yaml", "example_solution.yml"):
        if (dataset_dir / candidate).exists():
            return candidate
    return "No example solution is provided for this workspace."


def _template_context(item: RunItem) -> dict[str, str]:
    return {
        "benchmark": item.benchmark,
        "split": item.split,
        "case_id": item.case_id,
        "example_solution_name": _example_solution_name(item.benchmark),
        "verifier_location": "verifier",
        "verifier_command": "./verifier case/ solution.json",
    }


def _safe_render(text: str, replacements: dict[str, str]) -> str:
    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        return replacements.get(key, match.group(0))

    return PLACEHOLDER_PATTERN.sub(replace, text)


def _copy_file_or_directory(source: Path, destination: Path, *, render: bool, context: dict[str, str]) -> None:
    if destination.exists():
        if destination.is_dir():
            shutil.rmtree(destination)
        else:
            destination.unlink()
    if source.is_dir():
        if render:
            raise SystemExit(f"Cannot render directory source: {source}")
        shutil.copytree(source, destination)
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    if render:
        destination.write_text(_safe_render(source.read_text(encoding="utf-8"), context), encoding="utf-8")
    else:
        shutil.copy2(source, destination)


def _source_available(source: Path) -> bool:
    if not source.exists():
        return False
    if source.is_dir():
        return any(source.iterdir())
    return True


def _prepare_roots(workspace_dir: Path, runtime_dir: Path, output_dir: Path) -> MountRoots:
    roots = MountRoots(workspace=workspace_dir, home=runtime_dir / "home", output=output_dir)
    roots.workspace.mkdir(parents=True, exist_ok=True)
    roots.home.mkdir(parents=True, exist_ok=True)
    roots.output.mkdir(parents=True, exist_ok=True)
    return roots


def _build_container_identity(runtime_dir: Path) -> ContainerIdentity:
    passwd_file = runtime_dir / "passwd"
    group_file = runtime_dir / "group"
    uid = os.getuid()
    gid = os.getgid()
    passwd_file.write_text(
        "\n".join(
            [
                "root:x:0:0:root:/root:/bin/bash",
                f"korolev:x:{uid}:{gid}:AstroReason User:{CONTAINER_HOME}:/bin/bash",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    group_file.write_text(f"root:x:0:\nkorolev:x:{gid}:\n", encoding="utf-8")
    return ContainerIdentity(passwd_file=passwd_file, group_file=group_file)


def _container_to_host(container_path: Path, roots: MountRoots) -> Path:
    for prefix, root in (
        (WORKSPACE_MOUNT, roots.workspace),
        (CONTAINER_HOME, roots.home),
        (OUTPUT_MOUNT, roots.output),
    ):
        try:
            return root / container_path.relative_to(prefix)
        except ValueError:
            continue
    raise SystemExit(f"Container path is outside mounted roots: {container_path}")


def _collect_target(target: Path, output_dir: Path) -> Path:
    if not target.parts:
        raise SystemExit(f"Collect target is empty: {target}")
    root = target.parts[0]
    rest = Path(*target.parts[1:]) if len(target.parts) > 1 else Path()
    if root == "results_root":
        return output_dir / rest
    if root == "repo":
        return REPO_ROOT / rest
    if root in {"experiments", "benchmarks"}:
        return REPO_ROOT / target
    raise SystemExit(f"Unsupported collect target root: {target}")


def _assemble_workspace(item: RunItem, roots: MountRoots, extra_specs: tuple[AssembleSpec, ...] = ()) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    context = _template_context(item)
    specs = (*_benchmark_assemble_specs(item.benchmark, item.split, item.case_id), *item.profile.assemble, *extra_specs)
    for spec in specs:
        if not _source_available(spec.source):
            if spec.missing_ok:
                records.append({"source": _relative(spec.source), "target": spec.target.as_posix(), "present": False})
                continue
            opaque_benchmark = _opaque_benchmark(spec.source)
            if opaque_benchmark:
                raise SystemExit(
                    f"Required opaque verifier artifact does not exist: {spec.source}. "
                    f"Rebuild it with: {_opaque_rebuild_command(opaque_benchmark)}"
                )
            example_note = f" Copy {spec.example} into place first." if spec.example else ""
            raise SystemExit(f"Required assemble source does not exist: {spec.source}.{example_note}")
        _validate_opaque_artifact(spec.source)
        destination = _container_to_host(spec.target, roots)
        _copy_file_or_directory(spec.source, destination, render=spec.render, context=context)
        records.append(
            {
                "source": _relative(spec.source),
                "target": spec.target.as_posix(),
                "present": True,
                "rendered": spec.render,
            }
        )
    return records


def _collect_artifacts(profile: HarnessProfile, roots: MountRoots, output_dir: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for spec in profile.collect:
        source = _container_to_host(spec.source, roots)
        target = _collect_target(spec.target, output_dir)
        if not source.exists():
            if spec.missing_ok:
                records.append({"source": spec.source.as_posix(), "target": spec.target.as_posix(), "present": False})
                continue
            raise SystemExit(f"Required collected source does not exist: {source}")
        if target.exists():
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink()
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.copytree(source, target)
        else:
            shutil.copy2(source, target)
        records.append({"source": spec.source.as_posix(), "target": spec.target.as_posix(), "present": True})
    return records


def _build_docker_command(
    item: RunItem,
    runtime: RuntimeManifest,
    roots: MountRoots,
    identity: ContainerIdentity,
    *,
    interactive: bool,
) -> list[str]:
    cmd = ["docker", "run", "--rm", "-w", str(WORKSPACE_MOUNT)]
    cmd.extend(["--user", f"{os.getuid()}:{os.getgid()}"])
    cmd.extend(["-e", f"HOME={CONTAINER_HOME}"])
    cmd.extend(["-e", "USER=korolev"])
    cmd.extend(["-e", "LOGNAME=korolev"])
    cmd.extend(["-e", f"XDG_CONFIG_HOME={CONTAINER_HOME / '.config'}"])
    cmd.extend(["-e", f"XDG_DATA_HOME={CONTAINER_HOME / '.local' / 'share'}"])
    for env_key in item.profile.forward_env_keys:
        env_value = os.environ.get(env_key)
        if env_value is not None:
            cmd.extend(["-e", f"{env_key}={env_value}"])
    if item.resources.cpus:
        cmd.extend(["--cpus", item.resources.cpus])
    if item.resources.memory:
        cmd.extend(["--memory", item.resources.memory])
    if item.resources.shm_size:
        cmd.extend(["--shm-size", item.resources.shm_size])
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
            f"{identity.passwd_file.resolve()}:/etc/passwd:ro",
            "-v",
            f"{identity.group_file.resolve()}:/etc/group:ro",
            runtime.image,
        ]
    )
    lines = [
        "set -euo pipefail",
        f"mkdir -p {shlex.quote(str(CONTAINER_HOME))}",
        f"mkdir -p {shlex.quote(str(CONTAINER_HOME / '.config'))}",
        f"mkdir -p {shlex.quote(str(CONTAINER_HOME / '.local' / 'share'))}",
        f"cd {shlex.quote(str(WORKSPACE_MOUNT))}",
    ]
    if interactive:
        lines.append("exec /bin/bash -i")
    else:
        lines.append(
            f"exec timeout --signal=TERM {item.timeout_seconds} /bin/bash -lc "
            f"{shlex.quote(item.profile.headless_shell_command)}"
        )
    cmd.extend(["/bin/bash", "-lc", "\n".join(lines)])
    return cmd


def _run_to_files(cmd: list[str], stdout_path: Path, stderr_path: Path) -> tuple[int, bool]:
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
        return 127, False
    return result.returncode, True


def _run_capture(cmd: list[str], *, cwd: Path | None = None) -> tuple[int, str, str, bool]:
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=cwd,
            check=False,
        )
    except FileNotFoundError as exc:
        return 127, "", f"Failed to launch process: {exc}", False
    return result.returncode, result.stdout or "", result.stderr or "", True


def _external_verifier(item: RunItem, output_dir: Path, solution_present: bool) -> tuple[str, dict[str, Any]]:
    if not solution_present:
        return "no_solution", {"valid": False, "error": "No solution.json was produced."}
    case_dir = _case_dir(item.benchmark, item.split, item.case_id)
    solution = output_dir / "solution.json"
    cmd = ["uv", "run", "python", "-m", f"benchmarks.{item.benchmark}.verifier.run", str(case_dir), str(solution)]
    exit_code, stdout, stderr, launched = _run_capture(cmd, cwd=REPO_ROOT)
    (output_dir / "verifier_stdout.txt").write_text(stdout, encoding="utf-8")
    (output_dir / "verifier_stderr.txt").write_text(stderr, encoding="utf-8")
    if not launched:
        return "error", {"valid": False, "error": stderr}
    try:
        parsed = json.loads(stdout) if stdout.strip() else {}
    except json.JSONDecodeError:
        return "error", {"valid": False, "error": "Verifier emitted malformed JSON.", "exit_code": exit_code}
    if not isinstance(parsed, dict) or not isinstance(parsed.get("valid"), bool):
        return "error", {"valid": False, "error": "Verifier JSON did not contain boolean valid.", "raw": parsed}
    if exit_code not in (0, 1):
        return "error", {"valid": False, "error": stderr.strip() or "Verifier exited unexpectedly.", "raw": parsed}
    if parsed["valid"]:
        return "valid", parsed
    return "invalid", parsed


def _copy_solution(workspace_dir: Path, output_dir: Path) -> bool:
    source = workspace_dir / "solution.json"
    if not source.exists():
        return False
    shutil.copy2(source, output_dir / "solution.json")
    return True


def _agent_status(exit_code: int, launched: bool, solution_present: bool) -> str:
    if not launched:
        return "runner_error"
    if exit_code == 124:
        return "timeout"
    if exit_code != 0:
        return "agent_failed"
    if not solution_present:
        return "no_solution"
    return "success"


def _overall_status(agent_status: str, verifier_status: str, interactive: bool) -> str:
    if interactive:
        return "interactive_exit"
    if agent_status != "success":
        return agent_status
    if verifier_status == "valid":
        return "success"
    if verifier_status == "invalid":
        return "verifier_invalid"
    return "verifier_error"


def _write_run_json(
    item: RunItem,
    output_dir: Path,
    *,
    mode: str,
    assembled: list[dict[str, Any]],
    collected: list[dict[str, Any]],
    start_time: datetime,
    end_time: datetime,
    agent_exit_code: int,
    agent_status: str,
    verifier_status: str,
    verifier_result: dict[str, Any],
    overall_status: str,
) -> None:
    payload = {
        "schema_version": 1,
        "experiment": "temporal_robustness",
        "mode": mode,
        "config": _relative(item.config_path),
        "benchmark": item.benchmark,
        "split": item.split,
        "case_id": item.case_id,
        "harness": item.harness,
        "runtime": item.profile.runtime,
        "workspace_verifier": {
            "exposed": True,
            "kind": "opaque_binary",
            "location": "verifier",
            "command": "./verifier case/ solution.json",
        },
        "start_time": start_time.isoformat(),
        "end_time": end_time.isoformat(),
        "duration_seconds": round((end_time - start_time).total_seconds(), 3),
        "agent_exit_code": agent_exit_code,
        "agent_status": agent_status,
        "verifier_status": verifier_status,
        "overall_status": overall_status,
        "artifacts": {"assemble": assembled, "collect": collected},
        "verifier": verifier_result,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "run.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_runner_error(item: RunItem, output_dir: Path, exc: BaseException) -> None:
    now = datetime.now(timezone.utc)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "runner_error.txt").write_text(f"{type(exc).__name__}: {exc}\n", encoding="utf-8")
    _write_run_json(
        item,
        output_dir,
        mode="batch",
        assembled=[],
        collected=[],
        start_time=now,
        end_time=now,
        agent_exit_code=127,
        agent_status="runner_error",
        verifier_status="error",
        verifier_result={"valid": False, "error": f"{type(exc).__name__}: {exc}"},
        overall_status="runner_error",
    )


def _existing_status(output_dir: Path) -> tuple[str, str | None]:
    run_json = output_dir / "run.json"
    if not run_json.exists():
        return "missing_artifact", None
    try:
        payload = json.loads(run_json.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return "malformed_artifact", None
    if not isinstance(payload, dict) or not isinstance(payload.get("overall_status"), str):
        return "malformed_artifact", None
    return "present", payload["overall_status"]


def _should_run(
    item: RunItem,
    *,
    rerun_statuses: tuple[str, ...],
    no_skip_completed: bool,
    skip_completed: bool,
    retry_statuses: tuple[str, ...],
) -> tuple[bool, str]:
    artifact_state, status = _existing_status(_output_dir(item))
    candidate = status if artifact_state == "present" else artifact_state
    if rerun_statuses:
        return candidate in rerun_statuses, f"status={candidate}"
    if no_skip_completed:
        return True, "forced"
    if artifact_state != "present":
        return True, artifact_state
    if status in retry_statuses:
        return True, f"retryable={status}"
    if skip_completed:
        return False, f"existing={status}"
    return True, "configured"


def _run_item(item: RunItem) -> RunResult:
    output_dir = _output_dir(item)
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    runtime = load_runtime(item.profile.runtime)
    with tempfile.TemporaryDirectory(prefix="astroreason-temporal-workspace-") as workspace_tmp:
        with tempfile.TemporaryDirectory(prefix="astroreason-temporal-runtime-") as runtime_tmp:
            workspace_dir = Path(workspace_tmp)
            runtime_dir = Path(runtime_tmp)
            roots = _prepare_roots(workspace_dir, runtime_dir, output_dir)
            identity = _build_container_identity(runtime_dir)
            assembled = _assemble_workspace(item, roots)
            cmd = _build_docker_command(item, runtime, roots, identity, interactive=False)
            start = datetime.now(timezone.utc)
            exit_code, launched = _run_to_files(cmd, output_dir / "agent_stdout.txt", output_dir / "agent_stderr.txt")
            end = datetime.now(timezone.utc)
            solution_present = _copy_solution(workspace_dir, output_dir)
            collected = _collect_artifacts(item.profile, roots, output_dir)
            agent_status = _agent_status(exit_code, launched, solution_present)
            verifier_status, verifier_result = _external_verifier(item, output_dir, solution_present)
            overall = _overall_status(agent_status, verifier_status, interactive=False)
            _write_run_json(
                item,
                output_dir,
                mode="batch",
                assembled=assembled,
                collected=collected,
                start_time=start,
                end_time=end,
                agent_exit_code=exit_code,
                agent_status=agent_status,
                verifier_status=verifier_status,
                verifier_result=verifier_result,
                overall_status=overall,
            )
    return RunResult(overall_status=overall, skipped=False, output_dir=output_dir)


def _run_item_with_retries(item: RunItem, batch: BatchSettings) -> RunResult:
    attempts = batch.max_retries + 1
    last_result: RunResult | None = None
    for attempt in range(1, attempts + 1):
        try:
            result = _run_item(item)
        except BaseException as exc:
            output_dir = _output_dir(item)
            _write_runner_error(item, output_dir, exc)
            result = RunResult(overall_status="runner_error", skipped=False, output_dir=output_dir)
        last_result = result
        if result.overall_status not in batch.retry_statuses:
            return result
        if attempt < attempts:
            print(
                f"retry {item.split}/{item.harness}/{item.case_id}: "
                f"{result.overall_status} (attempt {attempt}/{attempts})"
            )
    if last_result is None:
        raise RuntimeError("Run finished without a result.")
    return last_result


def _build_items(
    config: FamilyConfig,
    *,
    splits: tuple[str, ...],
    cases: tuple[str, ...],
    harnesses: tuple[str, ...],
    timeout_override: int | None,
    max_concurrency_override: int | None,
) -> tuple[FamilyConfig, tuple[RunItem, ...]]:
    if max_concurrency_override is not None:
        if max_concurrency_override <= 0:
            raise SystemExit("--max-concurrency must be positive")
        config = replace(config, batch=replace(config.batch, max_concurrency=max_concurrency_override))
    effective_timeout = timeout_override or config.timeout_seconds
    selected_splits = _select(config.splits, splits, "split")
    selected_cases = _select(config.cases, cases, "case")
    selected_harnesses = _select(config.harnesses, harnesses, "harness")
    _validate_cases(config.benchmark, selected_splits, selected_cases)
    profiles = {harness: load_harness_profile(harness) for harness in selected_harnesses}
    items: list[RunItem] = []
    for split in selected_splits:
        for harness in selected_harnesses:
            for case_id in selected_cases:
                items.append(
                    RunItem(
                        config_name=config.config_path.stem,
                        config_path=config.config_path,
                        benchmark=config.benchmark,
                        split=split,
                        case_id=case_id,
                        harness=harness,
                        profile=profiles[harness],
                        timeout_seconds=effective_timeout,
                        resources=config.resources,
                        results_root=config.results.root,
                    )
                )
    return config, tuple(items)


def _missing_sources(items: tuple[RunItem, ...]) -> list[tuple[str, Path, Path | None]]:
    missing: list[tuple[str, Path, Path | None]] = []
    seen: set[Path] = set()
    for item in items:
        for spec in (*_benchmark_assemble_specs(item.benchmark, item.split, item.case_id), *item.profile.assemble):
            if spec.source in seen or _source_available(spec.source) or spec.missing_ok:
                continue
            seen.add(spec.source)
            missing.append((item.harness, spec.source, spec.example))
    return missing


def _print_preview(config: FamilyConfig, items: tuple[RunItem, ...], *, rerun_statuses: tuple[str, ...], no_skip_completed: bool) -> None:
    runnable = 0
    skipped = 0
    for item in items:
        should_run, _ = _should_run(
            item,
            rerun_statuses=rerun_statuses,
            no_skip_completed=no_skip_completed,
            skip_completed=config.batch.skip_completed,
            retry_statuses=config.batch.retry_statuses,
        )
        if should_run:
            runnable += 1
        else:
            skipped += 1
    print(f"Config: {_relative(config.config_path)}")
    print("Mode: batch")
    print(f"Benchmark: {config.benchmark}")
    print(f"Splits: {', '.join(sorted({item.split for item in items}))}")
    print(f"Harnesses: {', '.join(sorted({item.harness for item in items}))}")
    print(f"Cases: {', '.join(sorted({item.case_id for item in items}))}")
    print(f"Total planned items: {len(items)}")
    print(f"Runnable now: {runnable}")
    print(f"Skipped now: {skipped}")
    print(f"Max concurrency: {config.batch.max_concurrency}")
    missing = _missing_sources(items)
    if missing:
        print("Missing assemble sources:")
        for harness, source, example in missing:
            suffix = f" (example: {_relative(example)})" if example else ""
            print(f"  - {harness}: {_relative(source)}{suffix}")
    else:
        print("Missing assemble sources: none")
    for item in items:
        should_run, reason = _should_run(
            item,
            rerun_statuses=rerun_statuses,
            no_skip_completed=no_skip_completed,
            skip_completed=config.batch.skip_completed,
            retry_statuses=config.batch.retry_statuses,
        )
        action = "run" if should_run else "skip"
        print(f"  - {action}: {item.split}/{item.harness}/{item.case_id} ({reason})")


def _run_batch(args: argparse.Namespace) -> int:
    config_path = (args.config or DEFAULT_CONFIG).resolve()
    config = load_family_config(config_path)
    config, items = _build_items(
        config,
        splits=tuple(args.split),
        cases=tuple(args.case),
        harnesses=tuple(args.harness),
        timeout_override=args.timeout,
        max_concurrency_override=args.max_concurrency,
    )
    rerun_statuses = tuple(args.rerun_status)
    if args.dry_run:
        _print_preview(config, items, rerun_statuses=rerun_statuses, no_skip_completed=args.no_skip_completed)
        return 0

    missing = _missing_sources(items)
    if missing:
        lines = ["Missing required assemble sources:"]
        for harness, source, example in missing:
            suffix = f" Copy {_relative(example)} into place first." if example else ""
            lines.append(f"- {harness}: {source}{suffix}")
        raise SystemExit("\n".join(lines))

    selected: list[RunItem] = []
    skipped_results: list[RunResult] = []
    for item in items:
        should_run, reason = _should_run(
            item,
            rerun_statuses=rerun_statuses,
            no_skip_completed=args.no_skip_completed,
            skip_completed=config.batch.skip_completed,
            retry_statuses=config.batch.retry_statuses,
        )
        if should_run:
            selected.append(item)
        else:
            artifact_state, status = _existing_status(_output_dir(item))
            skipped_results.append(RunResult(overall_status=status or artifact_state, skipped=True, output_dir=_output_dir(item)))
            print(f"skip {item.split}/{item.harness}/{item.case_id}: {reason}")

    status_counts: dict[str, int] = {}
    for result in skipped_results:
        status_counts[result.overall_status] = status_counts.get(result.overall_status, 0) + 1

    with concurrent.futures.ThreadPoolExecutor(max_workers=config.batch.max_concurrency) as executor:
        futures = {executor.submit(_run_item_with_retries, item, config.batch): item for item in selected}
        completed = 0
        for future in concurrent.futures.as_completed(futures):
            item = futures[future]
            completed += 1
            try:
                result = future.result()
            except BaseException as exc:
                output_dir = _output_dir(item)
                _write_runner_error(item, output_dir, exc)
                result = RunResult(overall_status="runner_error", skipped=False, output_dir=output_dir)
            status_counts[result.overall_status] = status_counts.get(result.overall_status, 0) + 1
            print(
                f"[{completed}/{len(selected)}] {item.split}/{item.harness}/{item.case_id} "
                f"-> {result.overall_status} ({_relative(result.output_dir)})"
            )
    print("Status counts: " + ", ".join(f"{key}={value}" for key, value in sorted(status_counts.items())))
    return 0


def _run_interactive(args: argparse.Namespace) -> int:
    config_path = (args.config or INTERACTIVE_CONFIG).resolve()
    config = load_interactive_config(config_path)
    split = args.split[0] if args.split else config.split
    if len(args.split) > 1:
        raise SystemExit("Interactive mode accepts at most one --split.")
    case_id = args.case[0] if args.case else config.case_id
    if len(args.case) > 1:
        raise SystemExit("Interactive mode accepts at most one --case.")
    harnesses = _select(config.harnesses, tuple(args.harness), "harness")
    profiles = tuple(load_harness_profile(harness) for harness in harnesses)
    runtimes = {profile.runtime for profile in profiles}
    if len(runtimes) != 1:
        raise SystemExit("Interactive mode requires selected harnesses to share one runtime.")
    harness_identity = profiles[0].harness if len(profiles) == 1 else "all_harnesses"
    _validate_cases(config.benchmark, (split,), (case_id,))
    representative = RunItem(
        config_name=config.config_path.stem,
        config_path=config.config_path,
        benchmark=config.benchmark,
        split=split,
        case_id=case_id,
        harness=harness_identity,
        profile=profiles[0],
        timeout_seconds=args.timeout or config.timeout_seconds,
        resources=config.resources,
        results_root=config.results.root,
    )
    extra_specs = tuple(spec for profile in profiles[1:] for spec in profile.assemble)
    output_dir = _interactive_output_dir(config, harness_identity, split, case_id)
    workspace_dir = _interactive_workspace_dir(config, harness_identity, split, case_id)
    runtime_dir = workspace_dir.parent / f"{workspace_dir.name}.runtime"
    if args.dry_run:
        print(f"Interactive workspace: {_relative(workspace_dir)}")
        print(f"Interactive output: {_relative(output_dir)}")
        print(f"Harness configs assembled: {', '.join(harnesses)}")
        return 0
    if workspace_dir.exists():
        shutil.rmtree(workspace_dir)
    if runtime_dir.exists():
        shutil.rmtree(runtime_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    roots = _prepare_roots(workspace_dir, runtime_dir, output_dir)
    identity = _build_container_identity(runtime_dir)
    assembled = _assemble_workspace(representative, roots, extra_specs=extra_specs)
    runtime = load_runtime(next(iter(runtimes)))
    cmd = _build_docker_command(representative, runtime, roots, identity, interactive=True)
    start = datetime.now(timezone.utc)
    try:
        result = subprocess.run(cmd, check=False)
        exit_code = result.returncode
        launched = True
    except FileNotFoundError as exc:
        (output_dir / "agent_stderr.txt").write_text(f"Failed to launch process: {exc}\n", encoding="utf-8")
        exit_code = 127
        launched = False
    end = datetime.now(timezone.utc)
    solution_present = _copy_solution(workspace_dir, output_dir)
    collected: list[dict[str, Any]] = []
    for profile in profiles:
        collected.extend(_collect_artifacts(profile, roots, output_dir))
    agent_status = _agent_status(exit_code, launched, solution_present)
    verifier_status, verifier_result = _external_verifier(representative, output_dir, solution_present)
    overall = _overall_status(agent_status, verifier_status, interactive=True)
    _write_run_json(
        representative,
        output_dir,
        mode="interactive",
        assembled=assembled,
        collected=collected,
        start_time=start,
        end_time=end,
        agent_exit_code=exit_code,
        agent_status=agent_status,
        verifier_status=verifier_status,
        verifier_result=verifier_result,
        overall_status=overall,
    )
    print(f"Interactive workspace: {_relative(workspace_dir)}")
    print(f"Results written to {_relative(output_dir)}")
    print(f"Run status: {overall}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.interactive:
        return _run_interactive(args)
    return _run_batch(args)


if __name__ == "__main__":
    raise SystemExit(main())
