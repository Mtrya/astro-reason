#!/usr/bin/env python3
"""Run the skill-injection ablation experiment."""

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
if __package__ in (None, ""):
    sys.path.insert(0, str(REPO_ROOT))

from experiments._shared import workspace as workspace_utils


FAMILY_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG = FAMILY_DIR / "configs" / "default.yaml"
INTERACTIVE_CONFIG = FAMILY_DIR / "configs" / "interactive.yaml"
WORKSPACE_MOUNT = Path("/app/workspace")
OUTPUT_MOUNT = Path("/app/run/output")
CONTAINER_HOME = Path("/home/korolev")
INTERACTIVE_WORKSPACES_ROOT = REPO_ROOT / ".runtime" / "interactive_workspaces"
SATNET_COMPACT_PATTERN = re.compile(
    r"(VALID|INVALID):\s+total_hours=([+-]?(?:\d+(?:\.\d*)?|\.\d+))h,\s+tracks=(\d+)"
)
STATUS_PATTERN = re.compile(r"^Status:\s+(VALID|INVALID)\s*$", re.MULTILINE)


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
class BenchmarkSelection:
    benchmark: str
    split: str
    cases: tuple[str, ...]
    conditions: tuple[str, ...]
    harnesses: tuple[str, ...]


@dataclass(frozen=True)
class FamilyConfig:
    name: str
    mode: str
    benchmark: str
    split: str
    cases: tuple[str, ...]
    conditions: tuple[str, ...]
    harnesses: tuple[str, ...]
    benchmarks: tuple[BenchmarkSelection, ...]
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
    condition: str
    harnesses: tuple[str, ...]
    timeout_seconds: int
    resources: ResourceLimits
    results_root: Path
    config_path: Path


@dataclass(frozen=True)
class SkillSpec:
    name: str
    source: Path


@dataclass(frozen=True)
class ConditionProfile:
    condition: str
    description: str
    skills: tuple[SkillSpec, ...]
    profile_path: Path


@dataclass(frozen=True)
class HarnessProfile:
    harness: str
    runtime: str
    skill_target_root: Path
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
    condition: str
    harness: str
    runtime: str
    timeout_seconds: int
    resources: ResourceLimits
    results_root: Path
    assemble: tuple[AssembleSpec, ...]
    collect: tuple[CollectSpec, ...]
    forward_env_keys: tuple[str, ...]
    headless_shell_command: str


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
    parser = argparse.ArgumentParser(description="Run the skill-injection ablation")
    parser.add_argument("--config", type=Path, help="Family config path.")
    parser.add_argument("--interactive", action="store_true", help="Prepare one interactive workspace.")
    parser.add_argument("--benchmark", action="append", default=[], help="Limit to a benchmark.")
    parser.add_argument("--condition", action="append", default=[], help="Limit to a condition.")
    parser.add_argument("--harness", action="append", default=[], help="Limit to a harness.")
    parser.add_argument("--case", action="append", default=[], help="Limit to a case id.")
    parser.add_argument("--timeout", type=int, help="Override timeout_seconds.")
    parser.add_argument("--max-concurrency", type=int, help="Override batch.max_concurrency.")
    parser.add_argument("--rerun-status", action="append", default=[], help="Rerun stored statuses.")
    parser.add_argument("--no-skip-completed", action="store_true", help="Run selected items regardless of stored status.")
    parser.add_argument("--dry-run", action="store_true", help="Preview the selected work.")
    parser.add_argument("--force", action="store_true", help="Replace an existing interactive workspace/runtime.")
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
    retry_statuses = raw.get("retry_statuses", [])
    if not isinstance(retry_statuses, list):
        raise SystemExit(f"batch.retry_statuses must be a list: {path}")
    return BatchSettings(
        max_concurrency=int(raw.get("max_concurrency", 1)),
        max_retries=int(raw.get("max_retries", 0)),
        skip_completed=bool(raw.get("skip_completed", True)),
        retry_statuses=tuple(str(item) for item in retry_statuses),
    )


def _positive_int(value: Any, field: str, path: Path | None = None) -> int:
    suffix = f": {path}" if path is not None else ""
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise SystemExit(f"{field} must be a positive integer{suffix}") from exc
    if parsed <= 0:
        raise SystemExit(f"{field} must be a positive integer{suffix}")
    return parsed


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
                missing_ok=bool(item.get("missing_ok", False)),
            )
        )
    return tuple(specs)


def _parse_skill_specs(items: Any, path: Path) -> tuple[SkillSpec, ...]:
    if items is None:
        return ()
    if not isinstance(items, list):
        raise SystemExit(f"skills must be a list: {path}")
    specs: list[SkillSpec] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise SystemExit(f"skills[{index}] must be a mapping: {path}")
        specs.append(
            SkillSpec(
                name=_require_str(item, "name", f"skills[{index}]", path),
                source=_repo_path(_require_str(item, "source", f"skills[{index}]", path)),
            )
        )
    return tuple(specs)


def _parse_benchmark_selections(data: dict[str, Any], path: Path) -> tuple[BenchmarkSelection, ...]:
    raw = data.get("benchmarks")
    if raw is None:
        return (
            BenchmarkSelection(
                benchmark=_require_str(data, "benchmark", "Family config", path),
                split=_require_str(data, "split", "Family config", path),
                cases=_string_tuple(data, "cases", "Family config", path),
                conditions=_string_tuple(data, "conditions", "Family config", path),
                harnesses=_string_tuple(data, "harnesses", "Family config", path),
            ),
        )
    if not isinstance(raw, list) or not raw:
        raise SystemExit(f"Family config benchmarks must be a non-empty list: {path}")
    default_split = data.get("split")
    default_cases = data.get("cases")
    default_conditions = data.get("conditions")
    default_harnesses = data.get("harnesses")
    selections: list[BenchmarkSelection] = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise SystemExit(f"benchmarks[{index}] must be a mapping: {path}")
        selection_data = {
            "split": item.get("split", default_split),
            "cases": item.get("cases", default_cases),
            "conditions": item.get("conditions", default_conditions),
            "harnesses": item.get("harnesses", default_harnesses),
        }
        label = f"benchmarks[{index}]"
        selections.append(
            BenchmarkSelection(
                benchmark=_require_str(item, "benchmark", label, path),
                split=_require_str(selection_data, "split", label, path),
                cases=_string_tuple(selection_data, "cases", label, path),
                conditions=_string_tuple(selection_data, "conditions", label, path),
                harnesses=_string_tuple(selection_data, "harnesses", label, path),
            )
        )
    return tuple(selections)


def load_family_config(path: Path) -> FamilyConfig:
    data = _load_yaml(path, "Family config")
    benchmark_selections = _parse_benchmark_selections(data, path)
    first = benchmark_selections[0]
    all_cases = tuple(dict.fromkeys(case for selection in benchmark_selections for case in selection.cases))
    all_conditions = tuple(
        dict.fromkeys(condition for selection in benchmark_selections for condition in selection.conditions)
    )
    all_harnesses = tuple(dict.fromkeys(harness for selection in benchmark_selections for harness in selection.harnesses))
    return FamilyConfig(
        name=_require_str(data, "name", "Family config", path),
        mode=_require_str(data, "mode", "Family config", path),
        benchmark=first.benchmark,
        split=first.split,
        cases=all_cases,
        conditions=all_conditions,
        harnesses=all_harnesses,
        benchmarks=benchmark_selections,
        timeout_seconds=int(data.get("timeout_seconds", 7200)),
        batch=_batch_settings(data, path),
        resources=_resource_limits(data),
        results=_result_settings(data, path),
        config_path=path.resolve(),
    )


def load_interactive_config(path: Path) -> InteractiveConfig:
    data = _load_yaml(path, "Interactive config")
    return InteractiveConfig(
        name=_require_str(data, "name", "Interactive config", path),
        mode=_require_str(data, "mode", "Interactive config", path),
        benchmark=_require_str(data, "benchmark", "Interactive config", path),
        split=_require_str(data, "split", "Interactive config", path),
        case_id=_require_str(data, "case", "Interactive config", path),
        condition=_require_str(data, "condition", "Interactive config", path),
        harnesses=_string_tuple(data, "harnesses", "Interactive config", path),
        timeout_seconds=_positive_int(data.get("timeout_seconds", 3600), "timeout_seconds", path),
        resources=_resource_limits(data),
        results_root=_result_settings(data, path).root,
        config_path=path.resolve(),
    )


def load_condition_profile(condition: str) -> ConditionProfile:
    path = FAMILY_DIR / "conditions" / f"{condition}.yaml"
    data = _load_yaml(path, "Condition profile")
    profile_condition = _require_str(data, "condition", "Condition profile", path)
    if profile_condition != condition:
        raise SystemExit(f"Condition profile mismatch in {path}: {profile_condition}")
    return ConditionProfile(
        condition=condition,
        description=str(data.get("description", "")),
        skills=_parse_skill_specs(data.get("skills", []), path),
        profile_path=path.resolve(),
    )


def load_harness_profile(harness: str) -> HarnessProfile:
    path = FAMILY_DIR / "harnesses" / f"{harness}.yaml"
    data = _load_yaml(path, "Harness profile")
    profile_harness = _require_str(data, "harness", "Harness profile", path)
    if profile_harness != harness:
        raise SystemExit(f"Harness profile mismatch in {path}: {profile_harness}")
    commands = data.get("commands")
    if not isinstance(commands, dict):
        raise SystemExit(f"commands must be a mapping: {path}")
    forward_env_keys = data.get("forward_env_keys", [])
    if not isinstance(forward_env_keys, list):
        raise SystemExit(f"forward_env_keys must be a list: {path}")
    return HarnessProfile(
        harness=harness,
        runtime=_require_str(data, "runtime", "Harness profile", path),
        skill_target_root=_container_path(_require_str(data, "skill_target_root", "Harness profile", path)),
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


def _skill_assemble_specs(condition: ConditionProfile, harness: HarnessProfile) -> tuple[AssembleSpec, ...]:
    return tuple(
        AssembleSpec(
            source=skill.source,
            target=harness.skill_target_root / skill.name,
            render=False,
            missing_ok=False,
            example=None,
        )
        for skill in condition.skills
    )


def _select(configured: tuple[str, ...], requested: tuple[str, ...], label: str) -> tuple[str, ...]:
    if not requested:
        return configured
    unknown = [item for item in requested if item not in configured]
    if unknown:
        raise SystemExit(f"Unknown {label}(s): {', '.join(unknown)}")
    return tuple(item for item in configured if item in set(requested))


def _select_intersection(configured: tuple[str, ...], requested: tuple[str, ...]) -> tuple[str, ...]:
    if not requested:
        return configured
    requested_set = set(requested)
    return tuple(item for item in configured if item in requested_set)


def _case_dir(benchmark: str, split: str, case_id: str) -> Path:
    return REPO_ROOT / "benchmarks" / benchmark / "dataset" / "cases" / split / case_id


def _base_assemble_specs(benchmark: str, split: str, case_id: str) -> tuple[AssembleSpec, ...]:
    return (
        AssembleSpec(
            source=REPO_ROOT / "experiments" / "_fragments" / "prompts" / benchmark / "README.default.md",
            target=WORKSPACE_MOUNT / "README.md",
            render=True,
        ),
        AssembleSpec(
            source=_case_dir(benchmark, split, case_id),
            target=WORKSPACE_MOUNT / "case",
        ),
        AssembleSpec(
            source=REPO_ROOT / "experiments" / "_fragments" / "opaque_verifiers" / "artifacts" / benchmark / "verifier",
            target=WORKSPACE_MOUNT / "verifier",
        ),
        AssembleSpec(
            source=REPO_ROOT / "experiments" / "_fragments" / "prompts" / benchmark / "PROMPT.default.md",
            target=CONTAINER_HOME / "PROMPT.md",
            render=True,
        ),
        AssembleSpec(
            source=REPO_ROOT / "experiments" / "_fragments" / "prompts" / "_shared" / "AGENTS.main_agentic.default.md",
            target=WORKSPACE_MOUNT / "AGENTS.md",
            render=True,
        ),
    )


def _output_dir(config: FamilyConfig, item: RunItem) -> Path:
    return _output_dir_for_item(item)


def _output_dir_for_item(item: RunItem) -> Path:
    return (
        item.results_root
        / item.config_path.stem
        / item.condition
        / item.benchmark
        / item.harness
        / item.split
        / item.case_id
    )


def _interactive_workspace_dir(item: RunItem) -> Path:
    return (
        INTERACTIVE_WORKSPACES_ROOT
        / "experiments"
        / "skill_injection"
        / item.condition
        / item.benchmark
        / item.harness
        / item.split
        / item.case_id
    )


def build_items(
    config: FamilyConfig,
    *,
    benchmarks: tuple[str, ...] = (),
    conditions: tuple[str, ...],
    harnesses: tuple[str, ...],
    cases: tuple[str, ...],
) -> tuple[RunItem, ...]:
    selected_benchmarks = _select(tuple(selection.benchmark for selection in config.benchmarks), benchmarks, "benchmark")
    _select(config.conditions, conditions, "condition")
    _select(config.harnesses, harnesses, "harness")
    _select(config.cases, cases, "case")
    items: list[RunItem] = []
    for selection in config.benchmarks:
        if selection.benchmark not in selected_benchmarks:
            continue
        selected_conditions = _select_intersection(selection.conditions, conditions)
        selected_harnesses = _select_intersection(selection.harnesses, harnesses)
        selected_cases = _select_intersection(selection.cases, cases)
        for condition_name in selected_conditions:
            condition = load_condition_profile(condition_name)
            for harness_name in selected_harnesses:
                harness = load_harness_profile(harness_name)
                skill_specs = _skill_assemble_specs(condition, harness)
                for case_id in selected_cases:
                    assemble = (
                        *_base_assemble_specs(selection.benchmark, selection.split, case_id),
                        *harness.assemble,
                        *skill_specs,
                    )
                    items.append(
                        RunItem(
                            config_name=config.name,
                            config_path=config.config_path,
                            benchmark=selection.benchmark,
                            split=selection.split,
                            case_id=case_id,
                            condition=condition.condition,
                            harness=harness.harness,
                            runtime=harness.runtime,
                            timeout_seconds=config.timeout_seconds,
                            resources=config.resources,
                            results_root=config.results.root,
                            assemble=assemble,
                            collect=harness.collect,
                            forward_env_keys=harness.forward_env_keys,
                            headless_shell_command=harness.headless_shell_command,
                        )
                    )
    return tuple(items)


def _build_item(
    *,
    config_name: str,
    config_path: Path,
    benchmark: str,
    split: str,
    case_id: str,
    condition_name: str,
    harness_name: str,
    timeout_seconds: int,
    resources: ResourceLimits,
    results_root: Path,
) -> RunItem:
    condition = load_condition_profile(condition_name)
    harness = load_harness_profile(harness_name)
    skill_specs = _skill_assemble_specs(condition, harness)
    assemble = (
        *_base_assemble_specs(benchmark, split, case_id),
        *harness.assemble,
        *skill_specs,
    )
    return RunItem(
        config_name=config_name,
        config_path=config_path,
        benchmark=benchmark,
        split=split,
        case_id=case_id,
        condition=condition.condition,
        harness=harness.harness,
        runtime=harness.runtime,
        timeout_seconds=timeout_seconds,
        resources=resources,
        results_root=results_root,
        assemble=assemble,
        collect=harness.collect,
        forward_env_keys=harness.forward_env_keys,
        headless_shell_command=harness.headless_shell_command,
    )


def missing_assemble_sources(item: RunItem) -> tuple[AssembleSpec, ...]:
    return tuple(
        spec
        for spec in item.assemble
        if not workspace_utils.source_available(spec.source, require_nonempty_dirs=True)
        and not spec.missing_ok
    )


def _relative(path: Path) -> str:
    return workspace_utils.relative_display(path, REPO_ROOT)


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
    artifact_state, status = _existing_status(_output_dir_for_item(item))
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


def _template_context(item: RunItem) -> dict[str, str]:
    dataset_dir = REPO_ROOT / "benchmarks" / item.benchmark / "dataset"
    example_name = "No example solution is provided for this workspace."
    for candidate in ("example_solution.json", "example_solution.yaml", "example_solution.yml"):
        if (dataset_dir / candidate).exists():
            example_name = candidate
            break
    return {
        "benchmark": item.benchmark,
        "split": item.split,
        "case_id": item.case_id,
        "example_solution_name": example_name,
        "verifier_location": "verifier",
        "verifier_command": "./verifier case/ solution.json",
    }


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


def _assemble_workspace(item: RunItem, roots: MountRoots) -> list[dict[str, Any]]:
    def missing_source_message(spec: AssembleSpec) -> str:
        example_note = f" Copy {spec.example} into place first." if spec.example else ""
        return f"Required assemble source does not exist: {spec.source}.{example_note}"

    return workspace_utils.assemble_workspace(
        item.assemble,
        roots,
        context=_template_context(item),
        repo_root=REPO_ROOT,
        workspace_mount=WORKSPACE_MOUNT,
        home_mount=CONTAINER_HOME,
        output_mount=OUTPUT_MOUNT,
        require_nonempty_dirs=True,
        missing_source_message=missing_source_message,
        record_rendered_for_missing=False,
    )


def _collect_artifacts(item: RunItem, roots: MountRoots, output_dir: Path) -> list[dict[str, Any]]:
    return workspace_utils.collect_artifacts(
        item.collect,
        roots,
        output_dir,
        repo_root=REPO_ROOT,
        workspace_mount=WORKSPACE_MOUNT,
        home_mount=CONTAINER_HOME,
        output_mount=OUTPUT_MOUNT,
    )


def _build_docker_command(
    item: RunItem,
    runtime: RuntimeManifest,
    roots: MountRoots,
    identity: ContainerIdentity,
    *,
    interactive: bool = False,
) -> list[str]:
    cmd = ["docker", "run", "--rm", "-w", str(WORKSPACE_MOUNT)]
    cmd.extend(["--user", f"{os.getuid()}:{os.getgid()}"])
    cmd.extend(["-e", f"HOME={CONTAINER_HOME}"])
    cmd.extend(["-e", "USER=korolev"])
    cmd.extend(["-e", "LOGNAME=korolev"])
    cmd.extend(["-e", f"XDG_CONFIG_HOME={CONTAINER_HOME / '.config'}"])
    cmd.extend(["-e", f"XDG_DATA_HOME={CONTAINER_HOME / '.local' / 'share'}"])
    for env_key in item.forward_env_keys:
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
            f"{shlex.quote(item.headless_shell_command)}"
        )
    shell_script = "\n".join(lines)
    cmd.extend(["/bin/bash", "-lc", shell_script])
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


def _copy_solution(workspace_dir: Path, output_dir: Path) -> bool:
    source = workspace_dir / "solution.json"
    if not source.exists():
        return False
    shutil.copy2(source, output_dir / "solution.json")
    return True


def _verifier_command(benchmark: str, case_dir: Path, solution: Path) -> list[str]:
    package_verifier = REPO_ROOT / "benchmarks" / benchmark / "verifier"
    if package_verifier.exists():
        return [
            "uv",
            "run",
            "python",
            "-m",
            f"benchmarks.{benchmark}.verifier.run",
            str(case_dir),
            str(solution),
        ]
    script_verifier = REPO_ROOT / "benchmarks" / benchmark / "verifier.py"
    if not script_verifier.exists():
        raise SystemExit(f"No verifier found for benchmark {benchmark}")
    cmd = ["uv", "run", "python", str(script_verifier), str(case_dir), str(solution)]
    if benchmark == "satnet":
        cmd.append("--verbose")
    return cmd


def _float_line(label: str, text: str) -> float | None:
    match = re.search(rf"^{re.escape(label)}:\s+([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*$", text, re.MULTILINE)
    return float(match.group(1)) if match else None


def _int_line(label: str, text: str) -> int | None:
    match = re.search(rf"^{re.escape(label)}:\s+(\d+)\s*$", text, re.MULTILINE)
    return int(match.group(1)) if match else None


def _status_valid(text: str) -> bool | None:
    match = STATUS_PATTERN.search(text)
    return (match.group(1) == "VALID") if match else None


def _cli_section_items(text: str, section: str) -> list[str]:
    pattern = re.compile(rf"^{re.escape(section)}:\s*$((?:\n\s+- .*)*)", re.MULTILINE)
    match = pattern.search(text)
    if not match:
        return []
    return [line.strip()[2:] for line in match.group(1).splitlines() if line.strip().startswith("- ")]


def _parse_satnet_cli_payload(stdout: str, exit_code: int) -> dict[str, Any]:
    valid = _status_valid(stdout)
    score_hours = _float_line("Total tracking hours", stdout)
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
            "valid": False,
            "error": "SatNet verifier output did not match expected CLI schema.",
            "exit_code": exit_code,
        }
    return {
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


def _parse_cli_verifier_payload(benchmark: str, stdout: str, exit_code: int) -> dict[str, Any] | None:
    if benchmark == "satnet":
        return _parse_satnet_cli_payload(stdout, exit_code)
    return None


def _external_verifier(item: RunItem, output_dir: Path, solution_present: bool) -> tuple[str, dict[str, Any]]:
    if not solution_present:
        return "no_solution", {"valid": False, "error": "No solution.json was produced."}
    cmd = _verifier_command(
        item.benchmark,
        _case_dir(item.benchmark, item.split, item.case_id),
        output_dir / "solution.json",
    )
    exit_code, stdout, stderr, launched = _run_capture(cmd, cwd=REPO_ROOT)
    (output_dir / "verifier_stdout.txt").write_text(stdout, encoding="utf-8")
    (output_dir / "verifier_stderr.txt").write_text(stderr, encoding="utf-8")
    if not launched:
        return "error", {"valid": False, "error": stderr}
    cli_payload = _parse_cli_verifier_payload(item.benchmark, stdout, exit_code)
    if cli_payload is not None:
        valid = cli_payload.get("valid")
        if isinstance(valid, bool) and exit_code in (0, 1):
            return ("valid" if valid else "invalid"), cli_payload
        return "error", {**cli_payload, "stderr": stderr.strip()}
    try:
        parsed = json.loads(stdout) if stdout.strip() else {}
    except json.JSONDecodeError:
        return "error", {"valid": False, "error": "Verifier emitted malformed JSON.", "exit_code": exit_code}
    if not isinstance(parsed, dict) or not isinstance(parsed.get("valid"), bool):
        return "error", {"valid": False, "error": "Verifier JSON did not contain boolean valid.", "raw": parsed}
    if exit_code not in (0, 1):
        return "error", {"valid": False, "error": stderr.strip() or "Verifier exited unexpectedly.", "raw": parsed}
    return ("valid" if parsed["valid"] else "invalid"), parsed


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


def _overall_status(agent_status: str, verifier_status: str) -> str:
    if agent_status != "success":
        return agent_status
    if verifier_status == "valid":
        return "success"
    if verifier_status == "invalid":
        return "verifier_invalid"
    return "verifier_error"


def _skill_names(item: RunItem) -> list[str]:
    return [
        spec.target.name
        for spec in item.assemble
        if "experiments/_fragments/skills/skill_injection" in spec.source.as_posix()
    ]


def _write_run_json(
    item: RunItem,
    output_dir: Path,
    *,
    mode: str = "batch",
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
        "experiment": "skill_injection",
        "mode": mode,
        "config": _relative(item.config_path),
        "benchmark": item.benchmark,
        "split": item.split,
        "case_id": item.case_id,
        "condition": item.condition,
        "harness": item.harness,
        "runtime": item.runtime,
        "skills": _skill_names(item),
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


def _run_item(item: RunItem) -> RunResult:
    output_dir = _output_dir_for_item(item)
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    runtime = load_runtime(item.runtime)
    with tempfile.TemporaryDirectory(prefix="astroreason-skill-injection-workspace-") as workspace_tmp:
        with tempfile.TemporaryDirectory(prefix="astroreason-skill-injection-runtime-") as runtime_tmp:
            workspace_dir = Path(workspace_tmp)
            runtime_dir = Path(runtime_tmp)
            roots = _prepare_roots(workspace_dir, runtime_dir, output_dir)
            identity = _build_container_identity(runtime_dir)
            assembled = _assemble_workspace(item, roots)
            cmd = _build_docker_command(item, runtime, roots, identity)
            start = datetime.now(timezone.utc)
            exit_code, launched = _run_to_files(cmd, output_dir / "agent_stdout.txt", output_dir / "agent_stderr.txt")
            end = datetime.now(timezone.utc)
            solution_present = _copy_solution(workspace_dir, output_dir)
            collected = _collect_artifacts(item, roots, output_dir)
            agent_status = _agent_status(exit_code, launched, solution_present)
            verifier_status, verifier_result = _external_verifier(item, output_dir, solution_present)
            overall = _overall_status(agent_status, verifier_status)
            _write_run_json(
                item,
                output_dir,
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
        except Exception as exc:
            output_dir = _output_dir_for_item(item)
            _write_runner_error(item, output_dir, exc)
            result = RunResult(overall_status="runner_error", skipped=False, output_dir=output_dir)
        last_result = result
        if result.overall_status not in batch.retry_statuses:
            return result
        if attempt < attempts:
            print(
                f"retry {item.condition}/{item.harness}/{item.case_id}: "
                f"{result.overall_status} (attempt {attempt}/{attempts})"
            )
    if last_result is None:
        raise RuntimeError("Run finished without a result.")
    return last_result


def _run_batch(config: FamilyConfig, items: tuple[RunItem, ...], args: argparse.Namespace) -> int:
    selected: list[RunItem] = []
    skipped_results: list[RunResult] = []
    rerun_statuses = tuple(args.rerun_status)
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
            artifact_state, status = _existing_status(_output_dir_for_item(item))
            skipped_results.append(
                RunResult(overall_status=status or artifact_state, skipped=True, output_dir=_output_dir_for_item(item))
            )
            print(f"skip {item.condition}/{item.harness}/{item.case_id}: {reason}")

    missing: list[AssembleSpec] = []
    seen: set[Path] = set()
    for item in selected:
        for spec in missing_assemble_sources(item):
            if spec.source not in seen:
                missing.append(spec)
                seen.add(spec.source)
    if missing:
        lines = ["Missing required assemble sources:"]
        for spec in missing:
            example_note = f" Copy {_relative(spec.example)} into place first." if spec.example else ""
            lines.append(f"- {_relative(spec.source)}{example_note}")
        raise SystemExit("\n".join(lines))

    status_counts: dict[str, int] = {}
    executed_statuses: list[str] = []
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
            except Exception as exc:
                output_dir = _output_dir_for_item(item)
                _write_runner_error(item, output_dir, exc)
                result = RunResult(overall_status="runner_error", skipped=False, output_dir=output_dir)
            executed_statuses.append(result.overall_status)
            status_counts[result.overall_status] = status_counts.get(result.overall_status, 0) + 1
            action = "skipped" if result.skipped else "executed"
            print(
                f"[{completed}/{len(selected)}] {item.condition}/{item.harness}/{item.case_id} "
                f"-> {result.overall_status} ({action}; {_relative(result.output_dir)})"
            )
    print("Status counts: " + ", ".join(f"{key}={value}" for key, value in sorted(status_counts.items())))
    return 0 if all(status == "success" for status in executed_statuses) else 1


def _run_interactive(args: argparse.Namespace) -> int:
    config_path = (args.config or INTERACTIVE_CONFIG).resolve()
    config = load_interactive_config(config_path)
    benchmark = args.benchmark[-1] if args.benchmark else config.benchmark
    condition = args.condition[-1] if args.condition else config.condition
    harness = args.harness[-1] if args.harness else config.harnesses[0]
    case_id = args.case[-1] if args.case else config.case_id
    if config.harnesses and harness not in config.harnesses:
        raise SystemExit(f"Unknown harness for interactive config: {harness}")
    item = _build_item(
        config_name=config.config_path.stem,
        config_path=config.config_path,
        benchmark=benchmark,
        split=config.split,
        case_id=case_id,
        condition_name=condition,
        harness_name=harness,
        timeout_seconds=(
            _positive_int(args.timeout, "--timeout")
            if args.timeout is not None
            else config.timeout_seconds
        ),
        resources=config.resources,
        results_root=config.results_root,
    )
    output_dir = _output_dir_for_item(item)
    workspace_dir = _interactive_workspace_dir(item)
    runtime_dir = output_dir / "interactive_runtime"

    if args.dry_run:
        print(f"Interactive benchmark: {item.benchmark}")
        print(f"Interactive condition: {item.condition}")
        print(f"Interactive harness: {item.harness}")
        print(f"Interactive case: {item.split}/{item.case_id}")
        print(f"Workspace: {_relative(workspace_dir)}")
        print(f"Output: {_relative(output_dir)}")
        print(f"Prompt: {CONTAINER_HOME / 'PROMPT.md'}")
        print("Inside the shell, run the harness command manually when ready:")
        print(f"  {item.headless_shell_command}")
        missing = missing_assemble_sources(item)
        if missing:
            print("Missing assemble sources:")
            for spec in missing:
                print(f"  - {_relative(spec.source)}")
        else:
            print("Missing assemble sources: none")
        return 0

    existing_paths = [path for path in (workspace_dir, runtime_dir) if path.exists()]
    if existing_paths and not args.force:
        lines = ["Interactive workspace/runtime already exists. Re-run with --force to replace:"]
        lines.extend(f"- {_relative(path)}" for path in existing_paths)
        raise SystemExit("\n".join(lines))
    for path in existing_paths:
        shutil.rmtree(path)

    output_dir.mkdir(parents=True, exist_ok=True)
    runtime_dir.mkdir(parents=True, exist_ok=True)
    roots = _prepare_roots(workspace_dir, runtime_dir, output_dir)
    identity = _build_container_identity(runtime_dir)
    assembled = _assemble_workspace(item, roots)
    runtime = load_runtime(item.runtime)
    cmd = _build_docker_command(item, runtime, roots, identity, interactive=True)
    start = datetime.now(timezone.utc)
    try:
        exit_code = subprocess.run(cmd, check=False).returncode
        launched = True
    except FileNotFoundError as exc:
        (output_dir / "agent_stderr.txt").write_text(f"Failed to launch process: {exc}\n", encoding="utf-8")
        exit_code = 127
        launched = False
    end = datetime.now(timezone.utc)
    solution_present = _copy_solution(workspace_dir, output_dir)
    collected = _collect_artifacts(item, roots, output_dir)
    agent_status = _agent_status(exit_code, launched, solution_present)
    verifier_status, verifier_result = _external_verifier(item, output_dir, solution_present)
    _write_run_json(
        item,
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
        overall_status="interactive_exit",
    )
    print(f"Interactive workspace: {_relative(workspace_dir)}")
    print(f"Run metadata: {_relative(output_dir / 'run.json')}")
    return 0


def print_dry_run(
    config: FamilyConfig,
    items: tuple[RunItem, ...],
    *,
    rerun_statuses: tuple[str, ...] = (),
    no_skip_completed: bool = False,
) -> None:
    print(f"Config: {config.config_path}")
    print(f"Mode: {config.mode}")
    print(f"Benchmarks: {', '.join(dict.fromkeys(item.benchmark for item in items))}")
    print(f"Splits: {', '.join(dict.fromkeys(item.split for item in items))}")
    print(f"Conditions: {', '.join(dict.fromkeys(item.condition for item in items))}")
    print(f"Harnesses: {', '.join(dict.fromkeys(item.harness for item in items))}")
    print(f"Run count: {len(items)}")
    print(f"Max concurrency: {config.batch.max_concurrency}")
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
    print(f"Runnable now: {runnable}")
    print(f"Skipped now: {skipped}")
    missing_by_source: dict[str, int] = {}
    for item in items:
        for spec in missing_assemble_sources(item):
            missing_by_source[_relative(spec.source)] = missing_by_source.get(_relative(spec.source), 0) + 1
    if missing_by_source:
        print("Missing assemble sources:")
        for source, count in sorted(missing_by_source.items()):
            print(f"  - {source} ({count} run(s))")
    else:
        print("Missing assemble sources: none")
    for item in items:
        missing = missing_assemble_sources(item)
        state = "ready" if not missing else f"missing_sources={len(missing)}"
        print(
            f"- {item.benchmark}/{item.condition}/{item.harness}/{item.case_id}: {state} -> "
            f"{_relative(_output_dir(config, item))}"
        )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.interactive:
        return _run_interactive(args)
    config = load_family_config((args.config or DEFAULT_CONFIG).resolve())
    if args.timeout is not None:
        if args.timeout <= 0:
            raise SystemExit("--timeout must be positive")
        config = replace(config, timeout_seconds=args.timeout)
    if args.max_concurrency is not None:
        if args.max_concurrency <= 0:
            raise SystemExit("--max-concurrency must be positive")
        config = replace(config, batch=replace(config.batch, max_concurrency=args.max_concurrency))
    items = build_items(
        config,
        benchmarks=tuple(args.benchmark),
        conditions=tuple(args.condition),
        harnesses=tuple(args.harness),
        cases=tuple(args.case),
    )
    if args.dry_run:
        print_dry_run(
            config,
            items,
            rerun_statuses=tuple(args.rerun_status),
            no_skip_completed=args.no_skip_completed,
        )
        return 0
    return _run_batch(config, items, args)


if __name__ == "__main__":
    raise SystemExit(main())
