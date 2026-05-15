#!/usr/bin/env python3
"""Run the cross-benchmark memory-accumulation ablation."""

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
WORKSPACE_MOUNT = Path("/app/workspace")
OUTPUT_MOUNT = Path("/app/run/output")
CONTAINER_HOME = Path("/home/korolev")
MEMORY_MOUNT = WORKSPACE_MOUNT / "memory"
WORKSPACE_SKILLS_MOUNT = WORKSPACE_MOUNT / ".agents" / "skills"
SATNET_COMPACT_PATTERN = re.compile(
    r"(VALID|INVALID):\s+(?:total_hours|score)=([+-]?(?:\d+(?:\.\d*)?|\.\d+))h,\s+tracks=(\d+)"
)
SPOT5_COMPACT_PATTERN = re.compile(r"(VALID|INVALID):\s+profit=(\d+),\s+weight=(\d+)")
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
class CaseRef:
    benchmark: str
    split: str
    case_id: str


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
class ResultSettings:
    root: Path
    aggregate_dir: Path


@dataclass(frozen=True)
class EvaluationSelection:
    benchmark: str
    split: str
    cases: tuple[str, ...]


@dataclass(frozen=True)
class FamilyConfig:
    name: str
    mode: str
    condition: str
    train_harnesses: tuple[str, ...]
    train_cases: tuple[CaseRef, ...]
    memory_sources: tuple[str, ...]
    eval_harnesses: tuple[str, ...]
    eval_benchmarks: tuple[EvaluationSelection, ...]
    timeout_seconds: int
    batch: BatchSettings
    resources: ResourceLimits
    results: ResultSettings
    fragments_root: Path
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
class MemoryRunItem:
    phase: str
    condition: str
    memory_source: str
    benchmark: str
    split: str
    case_id: str
    harness: str
    sequence_index: int | None
    base_item: RunItem
    output_dir: Path
    state_dir: Path | None
    fragment_dir: Path


@dataclass(frozen=True)
class RunResult:
    overall_status: str
    skipped: bool
    output_dir: Path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the memory-accumulation ablation")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--phase", choices=("all", "train", "eval", "promote"), default="all")
    parser.add_argument("--benchmark", action="append", default=[], help="Limit eval to benchmark(s).")
    parser.add_argument("--harness", action="append", default=[], help="Limit train/eval harness(es).")
    parser.add_argument("--memory-source", action="append", default=[], help="Limit eval memory source harness(es).")
    parser.add_argument("--case", action="append", default=[], help="Limit eval to case id(s).")
    parser.add_argument("--timeout", type=int)
    parser.add_argument("--max-concurrency", type=int)
    parser.add_argument("--rerun-status", action="append", default=[])
    parser.add_argument("--no-skip-completed", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true", help="Replace existing train state and promoted fragments.")
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


def _runner_resources(resources: ResourceLimits) -> ResourceLimits:
    return resources


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


def _parse_case_ref(value: str, path: Path) -> CaseRef:
    parts = value.split("/")
    if len(parts) != 3 or any(not part for part in parts):
        raise SystemExit(f"Train case must be benchmark/split/case_id: {value!r} in {path}")
    return CaseRef(benchmark=parts[0], split=parts[1], case_id=parts[2])


def _parse_eval_benchmarks(raw: Any, path: Path) -> tuple[EvaluationSelection, ...]:
    if not isinstance(raw, list) or not raw:
        raise SystemExit(f"evaluation.benchmarks must be a non-empty list: {path}")
    selections: list[EvaluationSelection] = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise SystemExit(f"evaluation.benchmarks[{index}] must be a mapping: {path}")
        label = f"evaluation.benchmarks[{index}]"
        selections.append(
            EvaluationSelection(
                benchmark=_require_str(item, "benchmark", label, path),
                split=_require_str(item, "split", label, path),
                cases=_string_tuple(item, "cases", label, path),
            )
        )
    return tuple(selections)


def load_family_config(path: Path) -> FamilyConfig:
    data = _load_yaml(path, "Family config")
    accumulation = data.get("accumulation")
    evaluation = data.get("evaluation")
    fragments = data.get("fragments", {})
    if not isinstance(accumulation, dict):
        raise SystemExit(f"accumulation must be a mapping: {path}")
    if not isinstance(evaluation, dict):
        raise SystemExit(f"evaluation must be a mapping: {path}")
    if not isinstance(fragments, dict):
        raise SystemExit(f"fragments must be a mapping: {path}")
    train_cases = _string_tuple(accumulation, "train_cases", "accumulation", path)
    train_harnesses = _string_tuple(accumulation, "harnesses", "accumulation", path)
    memory_sources = evaluation.get("memory_sources", list(train_harnesses))
    if not isinstance(memory_sources, list) or any(not isinstance(item, str) or not item for item in memory_sources):
        raise SystemExit(f"evaluation.memory_sources must be a list of non-empty strings: {path}")
    return FamilyConfig(
        name=_require_str(data, "name", "Family config", path),
        mode=_require_str(data, "mode", "Family config", path),
        condition=_require_str(data, "condition", "Family config", path),
        train_harnesses=train_harnesses,
        train_cases=tuple(_parse_case_ref(case, path) for case in train_cases),
        memory_sources=tuple(memory_sources),
        eval_harnesses=_string_tuple(evaluation, "harnesses", "evaluation", path),
        eval_benchmarks=_parse_eval_benchmarks(evaluation.get("benchmarks"), path),
        timeout_seconds=int(data.get("timeout_seconds", 7200)),
        batch=_batch_settings(data, path),
        resources=_resource_limits(data),
        results=_result_settings(data, path),
        fragments_root=_repo_path(_require_str(fragments, "root", "fragments", path)),
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
                missing_ok=bool(item.get("missing_ok", False)),
            )
        )
    return tuple(specs)


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
        assemble=_parse_assemble(data.get("assemble"), path),
        collect=_parse_collect(data.get("collect", []), path),
        forward_env_keys=tuple(str(item) for item in forward_env_keys),
        headless_shell_command=_require_str(commands, "headless_shell_command", "commands", path),
        profile_path=path.resolve(),
    )


def _relative(path: Path) -> str:
    return workspace_utils.relative_display(path, REPO_ROOT)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _duration_seconds(start: datetime, end: datetime) -> float:
    return round((end - start).total_seconds(), 3)


def _status_counts_text(status_counts: dict[str, int]) -> str:
    return ", ".join(f"{key}={value}" for key, value in sorted(status_counts.items())) or "-"


def _item_label(item: MemoryRunItem) -> str:
    if item.phase == "train":
        sequence = f"#{item.sequence_index}" if item.sequence_index is not None else "#-"
        return f"train {item.memory_source} {sequence} {item.benchmark}/{item.split}/{item.case_id}"
    return f"eval {item.memory_source}->{item.harness} {item.benchmark}/{item.split}/{item.case_id}"


def _case_dir(benchmark: str, split: str, case_id: str) -> Path:
    return REPO_ROOT / "benchmarks" / benchmark / "dataset" / "cases" / split / case_id


def _state_dir(config: FamilyConfig, source_harness: str) -> Path:
    return config.results.root / config.config_path.stem / "train_state" / config.condition / source_harness


def _fragment_dir(config: FamilyConfig, source_harness: str) -> Path:
    return config.fragments_root / config.condition / source_harness


def _train_output_dir(config: FamilyConfig, source_harness: str, index: int, case_ref: CaseRef) -> Path:
    case_token = f"{index:03d}__{case_ref.benchmark}__{case_ref.split}__{case_ref.case_id}"
    return config.results.root / config.config_path.stem / "train" / config.condition / source_harness / case_token


def _eval_output_dir(
    config: FamilyConfig,
    *,
    memory_source: str,
    benchmark: str,
    harness: str,
    split: str,
    case_id: str,
) -> Path:
    return (
        config.results.root
        / config.config_path.stem
        / "eval"
        / config.condition
        / memory_source
        / benchmark
        / harness
        / split
        / case_id
    )


def _agents_fragment_for_phase(phase: str) -> Path:
    if phase == "train":
        return REPO_ROOT / "experiments" / "_fragments" / "prompts" / "_shared" / "AGENTS.memory_accumulation.train.md"
    if phase == "eval":
        return REPO_ROOT / "experiments" / "_fragments" / "prompts" / "_shared" / "AGENTS.memory_accumulation.eval.md"
    raise SystemExit(f"Unknown memory accumulation phase: {phase}")


def _base_assemble_specs(
    benchmark: str,
    split: str,
    case_id: str,
    *,
    phase: str,
) -> tuple[AssembleSpec, ...]:
    return (
        AssembleSpec(
            source=REPO_ROOT / "experiments" / "_fragments" / "prompts" / benchmark / "README.default.md",
            target=WORKSPACE_MOUNT / "README.md",
            render=True,
        ),
        AssembleSpec(source=_case_dir(benchmark, split, case_id), target=WORKSPACE_MOUNT / "case"),
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
            source=_agents_fragment_for_phase(phase),
            target=WORKSPACE_MOUNT / "AGENTS.md",
            render=True,
        ),
    )


def _memory_assemble_specs(source_dir: Path, *, required: bool) -> tuple[AssembleSpec, ...]:
    return (
        AssembleSpec(
            source=source_dir / "memory",
            target=MEMORY_MOUNT,
            missing_ok=not required,
        ),
        AssembleSpec(
            source=source_dir / ".agents" / "skills",
            target=WORKSPACE_SKILLS_MOUNT,
            missing_ok=not required,
        ),
    )


def _memory_collect_specs() -> tuple[CollectSpec, ...]:
    return (
        CollectSpec(source=MEMORY_MOUNT, target=Path("results_root/memory"), missing_ok=True),
        CollectSpec(
            source=WORKSPACE_SKILLS_MOUNT,
            target=Path("results_root/.agents/skills"),
            missing_ok=True,
        ),
    )


def _build_base_item(
    *,
    config: FamilyConfig,
    harness_name: str,
    benchmark: str,
    split: str,
    case_id: str,
    assemble: tuple[AssembleSpec, ...],
) -> RunItem:
    harness = load_harness_profile(harness_name)
    return RunItem(
        config_name=config.name,
        config_path=config.config_path,
        benchmark=benchmark,
        split=split,
        case_id=case_id,
        condition=config.condition,
        harness=harness.harness,
        runtime=harness.runtime,
        timeout_seconds=config.timeout_seconds,
        resources=_runner_resources(config.resources),
        results_root=config.results.root,
        assemble=assemble,
        collect=harness.collect,
        forward_env_keys=harness.forward_env_keys,
        headless_shell_command=harness.headless_shell_command,
    )


def build_train_items(config: FamilyConfig, *, harnesses: tuple[str, ...] = ()) -> tuple[MemoryRunItem, ...]:
    selected_harnesses = _select(config.train_harnesses, harnesses, "harness")
    items: list[MemoryRunItem] = []
    for source_harness in selected_harnesses:
        state_dir = _state_dir(config, source_harness)
        fragment_dir = _fragment_dir(config, source_harness)
        harness = load_harness_profile(source_harness)
        for index, case_ref in enumerate(config.train_cases, start=1):
            assemble = (
                *_base_assemble_specs(case_ref.benchmark, case_ref.split, case_ref.case_id, phase="train"),
                *harness.assemble,
                *_memory_assemble_specs(state_dir, required=False),
            )
            base_item = _build_base_item(
                config=config,
                harness_name=source_harness,
                benchmark=case_ref.benchmark,
                split=case_ref.split,
                case_id=case_ref.case_id,
                assemble=assemble,
            )
            items.append(
                MemoryRunItem(
                    phase="train",
                    condition=config.condition,
                    memory_source=source_harness,
                    benchmark=case_ref.benchmark,
                    split=case_ref.split,
                    case_id=case_ref.case_id,
                    harness=source_harness,
                    sequence_index=index,
                    base_item=base_item,
                    output_dir=_train_output_dir(config, source_harness, index, case_ref),
                    state_dir=state_dir,
                    fragment_dir=fragment_dir,
                )
            )
    return tuple(items)


def build_eval_items(
    config: FamilyConfig,
    *,
    benchmarks: tuple[str, ...] = (),
    memory_sources: tuple[str, ...] = (),
    harnesses: tuple[str, ...] = (),
    cases: tuple[str, ...] = (),
) -> tuple[MemoryRunItem, ...]:
    selected_memory_sources = _select(config.memory_sources, memory_sources, "memory source")
    selected_harnesses = _select(config.eval_harnesses, harnesses, "harness")
    selected_benchmarks = _select(tuple(item.benchmark for item in config.eval_benchmarks), benchmarks, "benchmark")
    all_eval_cases = tuple(dict.fromkeys(case for selection in config.eval_benchmarks for case in selection.cases))
    _select(all_eval_cases, cases, "case")
    items: list[MemoryRunItem] = []
    for selection in config.eval_benchmarks:
        if selection.benchmark not in selected_benchmarks:
            continue
        selected_cases = _select_intersection(selection.cases, cases)
        for source_harness in selected_memory_sources:
            fragment_dir = _fragment_dir(config, source_harness)
            for harness_name in selected_harnesses:
                for case_id in selected_cases:
                    assemble = (
                        *_base_assemble_specs(selection.benchmark, selection.split, case_id, phase="eval"),
                        *load_harness_profile(harness_name).assemble,
                        *_memory_assemble_specs(fragment_dir, required=True),
                    )
                    base_item = _build_base_item(
                        config=config,
                        harness_name=harness_name,
                        benchmark=selection.benchmark,
                        split=selection.split,
                        case_id=case_id,
                        assemble=assemble,
                    )
                    items.append(
                        MemoryRunItem(
                            phase="eval",
                            condition=config.condition,
                            memory_source=source_harness,
                            benchmark=selection.benchmark,
                            split=selection.split,
                            case_id=case_id,
                            harness=harness_name,
                            sequence_index=None,
                            base_item=base_item,
                            output_dir=_eval_output_dir(
                                config,
                                memory_source=source_harness,
                                benchmark=selection.benchmark,
                                harness=harness_name,
                                split=selection.split,
                                case_id=case_id,
                            ),
                            state_dir=None,
                            fragment_dir=fragment_dir,
                        )
                    )
    return tuple(items)


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


def missing_assemble_sources(item: MemoryRunItem) -> tuple[AssembleSpec, ...]:
    return tuple(
        spec
        for spec in item.base_item.assemble
        if not workspace_utils.source_available(spec.source, require_nonempty_dirs=True)
        and not spec.missing_ok
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
    item: MemoryRunItem,
    *,
    rerun_statuses: tuple[str, ...],
    no_skip_completed: bool,
    skip_completed: bool,
    retry_statuses: tuple[str, ...],
) -> tuple[bool, str]:
    artifact_state, status = _existing_status(item.output_dir)
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


def _collect_memory_state(item: MemoryRunItem, roots: MountRoots) -> list[dict[str, Any]]:
    if item.state_dir is None:
        return []
    item.state_dir.mkdir(parents=True, exist_ok=True)
    return workspace_utils.collect_artifacts(
        _memory_collect_specs(),
        roots,
        item.state_dir,
        repo_root=REPO_ROOT,
        workspace_mount=WORKSPACE_MOUNT,
        home_mount=CONTAINER_HOME,
        output_mount=OUTPUT_MOUNT,
    )


def _ensure_memory_dirs(roots: MountRoots) -> None:
    for path in (roots.workspace / "memory", roots.workspace / ".agents" / "skills"):
        path.mkdir(parents=True, exist_ok=True)
        keep = path / ".gitkeep"
        if not keep.exists():
            keep.write_text("", encoding="utf-8")


def load_runtime(name: str) -> RuntimeManifest:
    path = REPO_ROOT / "runtimes" / name / "runtime.yaml"
    data = _load_yaml(path, "Runtime manifest")
    runtime_name = _require_str(data, "name", "Runtime manifest", path)
    image = _require_str(data, "image", "Runtime manifest", path)
    return RuntimeManifest(name=runtime_name, image=image)


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
    shell_script = "\n".join(
        [
            "set -euo pipefail",
            f"mkdir -p {shlex.quote(str(CONTAINER_HOME))}",
            f"mkdir -p {shlex.quote(str(CONTAINER_HOME / '.config'))}",
            f"mkdir -p {shlex.quote(str(CONTAINER_HOME / '.local' / 'share'))}",
            f"cd {shlex.quote(str(WORKSPACE_MOUNT))}",
            f"exec timeout --signal=TERM {item.timeout_seconds} /bin/bash -lc "
            f"{shlex.quote(item.headless_shell_command)}",
        ]
    )
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
    return ["uv", "run", "python", str(script_verifier), str(case_dir), str(solution)]


def _normalized_verifier_valid(parsed: dict[str, Any]) -> bool | None:
    valid = parsed.get("valid")
    if isinstance(valid, bool):
        return valid
    is_valid = parsed.get("is_valid")
    if isinstance(is_valid, bool):
        return is_valid
    return None


def _normalize_cli_verifier_payload(parsed: dict[str, Any]) -> dict[str, Any]:
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
    pattern = re.compile(rf"^{re.escape(section)}:\s*$((?:\n\s+- .*)*)", re.MULTILINE)
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
    return {
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

    compact_payload = _parse_compact_cli_verifier_payload(item.benchmark, stdout, exit_code)
    if compact_payload is not None:
        valid = compact_payload.get("valid")
        if isinstance(valid, bool) and exit_code in (0, 1):
            return ("valid" if valid else "invalid"), compact_payload
        return "error", {**compact_payload, "valid": False, "stderr": stderr.strip()}

    try:
        parsed = json.loads(stdout) if stdout.strip() else {}
    except json.JSONDecodeError as exc:
        return "error", {
            "valid": False,
            "error": f"Verifier output was not valid JSON: {exc}",
            "exit_code": exit_code,
        }
    if not isinstance(parsed, dict):
        return "error", {"valid": False, "error": "Verifier output JSON must be an object.", "exit_code": exit_code}
    parsed = _normalize_cli_verifier_payload(parsed)
    if not isinstance(parsed.get("valid"), bool):
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
    if verifier_status == "valid":
        return "success"
    if agent_status != "success":
        return agent_status
    if verifier_status == "invalid":
        return "verifier_invalid"
    return "verifier_error"


def _write_run_json(
    item: MemoryRunItem,
    output_dir: Path,
    *,
    assembled: list[dict[str, Any]],
    collected: list[dict[str, Any]],
    memory_collected: list[dict[str, Any]],
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
        "experiment": "memory_accumulation",
        "phase": item.phase,
        "config": _relative(item.base_item.config_path),
        "condition": item.condition,
        "memory_source": item.memory_source,
        "benchmark": item.benchmark,
        "split": item.split,
        "case_id": item.case_id,
        "harness": item.harness,
        "runtime": item.base_item.runtime,
        "sequence_index": item.sequence_index,
        "workspace_memory": {
            "memory": "memory",
            "skills": ".agents/skills",
        },
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
        "artifacts": {
            "assemble": assembled,
            "collect": collected,
            "memory_collect": memory_collected,
        },
        "verifier": verifier_result,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "run.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_runner_error(item: MemoryRunItem, exc: BaseException) -> None:
    now = datetime.now(timezone.utc)
    item.output_dir.mkdir(parents=True, exist_ok=True)
    (item.output_dir / "runner_error.txt").write_text(f"{type(exc).__name__}: {exc}\n", encoding="utf-8")
    _write_run_json(
        item,
        item.output_dir,
        assembled=[],
        collected=[],
        memory_collected=[],
        start_time=now,
        end_time=now,
        agent_exit_code=127,
        agent_status="runner_error",
        verifier_status="error",
        verifier_result={"valid": False, "error": f"{type(exc).__name__}: {exc}"},
        overall_status="runner_error",
    )


def _run_item(item: MemoryRunItem) -> RunResult:
    if item.output_dir.exists():
        shutil.rmtree(item.output_dir)
    item.output_dir.mkdir(parents=True, exist_ok=True)
    runtime = load_runtime(item.base_item.runtime)
    with tempfile.TemporaryDirectory(prefix="astroreason-memory-workspace-") as workspace_tmp:
        with tempfile.TemporaryDirectory(prefix="astroreason-memory-runtime-") as runtime_tmp:
            roots = _prepare_roots(Path(workspace_tmp), Path(runtime_tmp), item.output_dir)
            identity = _build_container_identity(Path(runtime_tmp))
            assembled = _assemble_workspace(item.base_item, roots)
            _ensure_memory_dirs(roots)
            cmd = _build_docker_command(item.base_item, runtime, roots, identity)
            start = datetime.now(timezone.utc)
            exit_code, launched = _run_to_files(
                cmd,
                item.output_dir / "agent_stdout.txt",
                item.output_dir / "agent_stderr.txt",
            )
            end = datetime.now(timezone.utc)
            solution_present = _copy_solution(roots.workspace, item.output_dir)
            collected = _collect_artifacts(item.base_item, roots, item.output_dir)
            memory_collected = _collect_memory_state(item, roots)
            agent_status = _agent_status(exit_code, launched, solution_present)
            verifier_status, verifier_result = _external_verifier(
                item.base_item,
                item.output_dir,
                solution_present,
            )
            overall = _overall_status(agent_status, verifier_status)
            _write_run_json(
                item,
                item.output_dir,
                assembled=assembled,
                collected=collected,
                memory_collected=memory_collected,
                start_time=start,
                end_time=end,
                agent_exit_code=exit_code,
                agent_status=agent_status,
                verifier_status=verifier_status,
                verifier_result=verifier_result,
                overall_status=overall,
            )
    return RunResult(overall_status=overall, skipped=False, output_dir=item.output_dir)


def _run_item_with_retries(item: MemoryRunItem, batch: BatchSettings) -> RunResult:
    attempts = batch.max_retries + 1
    last_result: RunResult | None = None
    agentic_batch = BatchSettings(
        max_concurrency=batch.max_concurrency,
        max_retries=batch.max_retries,
        skip_completed=batch.skip_completed,
        retry_statuses=batch.retry_statuses,
    )
    for attempt in range(1, attempts + 1):
        print(f"Running {_item_label(item)} (attempt {attempt}/{attempts})")
        try:
            result = _run_item(item)
        except Exception as exc:
            _write_runner_error(item, exc)
            result = RunResult(overall_status="runner_error", skipped=False, output_dir=item.output_dir)
        last_result = result
        if result.overall_status not in agentic_batch.retry_statuses:
            return result
        if attempt < attempts:
            print(
                f"Retrying {_item_label(item)} after retryable status "
                f"{result.overall_status} (attempt {attempt}/{attempts})"
            )
    if last_result is None:
        raise RuntimeError("Run finished without a result.")
    return last_result


def _check_missing(items: tuple[MemoryRunItem, ...]) -> None:
    missing: list[AssembleSpec] = []
    seen: set[Path] = set()
    for item in items:
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


def _reset_train_destinations(config: FamilyConfig, harnesses: tuple[str, ...], *, force: bool) -> None:
    existing: list[Path] = []
    for harness in harnesses:
        for path in (_state_dir(config, harness), _fragment_dir(config, harness)):
            if path.exists():
                existing.append(path)
    if existing and not force:
        lines = ["Train state or promoted fragments already exist. Re-run with --force to replace:"]
        lines.extend(f"- {_relative(path)}" for path in existing)
        raise SystemExit("\n".join(lines))
    for path in existing:
        shutil.rmtree(path)


def promote_fragments(config: FamilyConfig, *, harnesses: tuple[str, ...] = (), force: bool = False) -> None:
    selected_harnesses = _select(config.train_harnesses, harnesses, "harness")
    existing = [path for harness in selected_harnesses if (path := _fragment_dir(config, harness)).exists()]
    if existing and not force:
        lines = ["Promoted fragments already exist. Re-run with --force to replace:"]
        lines.extend(f"- {_relative(path)}" for path in existing)
        raise SystemExit("\n".join(lines))
    for harness in selected_harnesses:
        source = _state_dir(config, harness)
        if not source.exists():
            raise SystemExit(f"Missing train state for {harness}: {_relative(source)}")
        target = _fragment_dir(config, harness)
        if target.exists():
            shutil.rmtree(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, target)
        manifest = {
            "schema_version": 1,
            "experiment": "memory_accumulation",
            "condition": config.condition,
            "source_harness": harness,
            "train_cases": [f"{case.benchmark}/{case.split}/{case.case_id}" for case in config.train_cases],
            "promoted_at": datetime.now(timezone.utc).isoformat(),
        }
        (target / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"promoted {harness}: {_relative(target)}")


def _run_train(config: FamilyConfig, args: argparse.Namespace) -> int:
    train_harnesses = _select(config.train_harnesses, tuple(args.harness), "harness")
    items = build_train_items(config, harnesses=train_harnesses)
    if args.dry_run:
        print_dry_run(config, train_items=items, eval_items=(), phase="train")
        return 0
    _reset_train_destinations(config, train_harnesses, force=args.force)
    _check_missing(items)
    statuses: list[str] = []
    status_counts: dict[str, int] = {}
    train_start = _utc_now()
    print(
        f"Starting train phase "
        f"(harnesses={len(train_harnesses)}, cases_per_harness={len(config.train_cases)}, runs={len(items)})"
    )
    for index, item in enumerate(items, start=1):
        result = _run_item_with_retries(item, config.batch)
        statuses.append(result.overall_status)
        status_counts[result.overall_status] = status_counts.get(result.overall_status, 0) + 1
        print(
            f"[{index}/{len(items)} train] {item.memory_source} "
            f"[{item.sequence_index}/{len(config.train_cases)}] "
            f"{item.benchmark}/{item.split}/{item.case_id} -> {result.overall_status} "
            f"({_relative(result.output_dir)}; counts={_status_counts_text(status_counts)})"
        )
    promote_fragments(config, harnesses=train_harnesses, force=True)
    train_end = _utc_now()
    print("Train summary:")
    print(f"  Total runs: {len(items)}")
    print(f"  Harnesses: {', '.join(train_harnesses) or '-'}")
    print(f"  Wall-clock seconds: {_duration_seconds(train_start, train_end)}")
    for status in sorted(status_counts):
        print(f"  {status}: {status_counts[status]}")
    return 0 if all(status == "success" for status in statuses) else 1


def _run_eval(config: FamilyConfig, args: argparse.Namespace) -> int:
    items = build_eval_items(
        config,
        benchmarks=tuple(args.benchmark),
        memory_sources=tuple(args.memory_source),
        harnesses=tuple(args.harness),
        cases=tuple(args.case),
    )
    if args.dry_run:
        print_dry_run(config, train_items=(), eval_items=items, phase="eval")
        return 0
    _check_missing(items)
    selected: list[MemoryRunItem] = []
    skipped_results: list[RunResult] = []
    for item in items:
        should_run, reason = _should_run(
            item,
            rerun_statuses=tuple(args.rerun_status),
            no_skip_completed=args.no_skip_completed,
            skip_completed=config.batch.skip_completed,
            retry_statuses=config.batch.retry_statuses,
        )
        if should_run:
            selected.append(item)
        else:
            artifact_state, status = _existing_status(item.output_dir)
            skipped_results.append(RunResult(status or artifact_state, True, item.output_dir))
            print(f"skip eval {item.memory_source}/{item.benchmark}/{item.harness}/{item.case_id}: {reason}")
    status_counts: dict[str, int] = {}
    executed_statuses: list[str] = []
    for result in skipped_results:
        status_counts[result.overall_status] = status_counts.get(result.overall_status, 0) + 1
    eval_start = _utc_now()
    max_workers = min(config.batch.max_concurrency, len(selected))
    print(
        f"Starting eval worker pool "
        f"(selected={len(selected)}, skipped={len(skipped_results)}, max_concurrency={max_workers or 0})"
    )
    with concurrent.futures.ThreadPoolExecutor(max_workers=config.batch.max_concurrency) as executor:
        futures = {executor.submit(_run_item_with_retries, item, config.batch): item for item in selected}
        completed = 0
        for future in concurrent.futures.as_completed(futures):
            item = futures[future]
            completed += 1
            try:
                result = future.result()
            except Exception as exc:
                _write_runner_error(item, exc)
                result = RunResult("runner_error", False, item.output_dir)
            executed_statuses.append(result.overall_status)
            status_counts[result.overall_status] = status_counts.get(result.overall_status, 0) + 1
            print(
                f"[{completed}/{len(selected)}] eval {item.memory_source}->{item.harness} "
                f"{item.benchmark}/{item.case_id} -> {result.overall_status} "
                f"({_relative(result.output_dir)}; executed={completed}, skipped={len(skipped_results)}; "
                f"counts={_status_counts_text(status_counts)})"
            )
    eval_end = _utc_now()
    print("Eval summary:")
    print(f"  Total runs considered: {len(selected) + len(skipped_results)}")
    print(f"  Executed runs: {len(executed_statuses)}")
    print(f"  Skipped runs: {len(skipped_results)}")
    print(f"  Wall-clock seconds: {_duration_seconds(eval_start, eval_end)}")
    for status in sorted(status_counts):
        print(f"  {status}: {status_counts[status]}")
    return 0 if all(status == "success" for status in executed_statuses) else 1


def print_dry_run(
    config: FamilyConfig,
    *,
    train_items: tuple[MemoryRunItem, ...],
    eval_items: tuple[MemoryRunItem, ...],
    phase: str,
) -> None:
    items = (*train_items, *eval_items)
    print(f"Config: {config.config_path}")
    print(f"Mode: {config.mode}")
    print(f"Phase: {phase}")
    print(f"Condition: {config.condition}")
    print(f"Train count: {len(train_items)}")
    print(f"Eval count: {len(eval_items)}")
    print(f"Train harnesses: {', '.join(dict.fromkeys(item.harness for item in train_items)) or '-'}")
    print(f"Memory sources: {', '.join(dict.fromkeys(item.memory_source for item in eval_items)) or '-'}")
    print(f"Eval harnesses: {', '.join(dict.fromkeys(item.harness for item in eval_items)) or '-'}")
    missing_by_source: dict[str, int] = {}
    for item in items:
        for spec in missing_assemble_sources(item):
            if phase == "all" and item.phase == "eval" and spec.source.is_relative_to(item.fragment_dir):
                continue
            missing_by_source[_relative(spec.source)] = missing_by_source.get(_relative(spec.source), 0) + 1
    if missing_by_source:
        print("Missing assemble sources:")
        for source, count in sorted(missing_by_source.items()):
            print(f"  - {source} ({count} run(s))")
    else:
        print("Missing assemble sources: none")
    for item in items:
        index = f"{item.sequence_index:03d} " if item.sequence_index is not None else ""
        print(
            f"- {item.phase} {index}{item.memory_source}->{item.harness} "
            f"{item.benchmark}/{item.split}/{item.case_id} -> {_relative(item.output_dir)}"
        )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config = load_family_config(args.config.resolve())
    if args.timeout is not None:
        if args.timeout <= 0:
            raise SystemExit("--timeout must be positive")
        config = replace(config, timeout_seconds=args.timeout)
    if args.max_concurrency is not None:
        if args.max_concurrency <= 0:
            raise SystemExit("--max-concurrency must be positive")
        config = replace(
            config,
            batch=replace(config.batch, max_concurrency=args.max_concurrency),
        )
    if args.phase == "promote":
        if args.dry_run:
            for harness in _select(config.train_harnesses, tuple(args.harness), "harness"):
                print(f"promote {harness}: {_relative(_state_dir(config, harness))} -> {_relative(_fragment_dir(config, harness))}")
            return 0
        promote_fragments(config, harnesses=tuple(args.harness), force=args.force)
        return 0
    if args.phase == "train":
        return _run_train(config, args)
    if args.phase == "eval":
        return _run_eval(config, args)
    train_items = build_train_items(config, harnesses=tuple(args.harness))
    eval_items = build_eval_items(
        config,
        benchmarks=tuple(args.benchmark),
        memory_sources=tuple(args.memory_source),
        harnesses=tuple(args.harness),
        cases=tuple(args.case),
    )
    if args.dry_run:
        print_dry_run(config, train_items=train_items, eval_items=eval_items, phase="all")
        return 0
    train_status = _run_train(config, args)
    eval_status = _run_eval(config, args)
    return 0 if train_status == 0 and eval_status == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
