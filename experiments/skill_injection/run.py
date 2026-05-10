#!/usr/bin/env python3
"""Plan the skill-injection ablation experiment."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
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
    split: str
    cases: tuple[str, ...]
    conditions: tuple[str, ...]
    harnesses: tuple[str, ...]
    timeout_seconds: int
    batch: BatchSettings
    resources: ResourceLimits
    results: ResultSettings
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
class RunItem:
    config_name: str
    benchmark: str
    split: str
    case_id: str
    condition: str
    harness: str
    timeout_seconds: int
    results_root: Path
    assemble: tuple[AssembleSpec, ...]
    collect: tuple[CollectSpec, ...]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Plan the skill-injection ablation")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="Family config path.")
    parser.add_argument("--condition", action="append", default=[], help="Limit to a condition.")
    parser.add_argument("--harness", action="append", default=[], help="Limit to a harness.")
    parser.add_argument("--case", action="append", default=[], help="Limit to a case id.")
    parser.add_argument("--dry-run", action="store_true", help="Preview the selected work.")
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


def load_family_config(path: Path) -> FamilyConfig:
    data = _load_yaml(path, "Family config")
    return FamilyConfig(
        name=_require_str(data, "name", "Family config", path),
        mode=_require_str(data, "mode", "Family config", path),
        benchmark=_require_str(data, "benchmark", "Family config", path),
        split=_require_str(data, "split", "Family config", path),
        cases=_string_tuple(data, "cases", "Family config", path),
        conditions=_string_tuple(data, "conditions", "Family config", path),
        harnesses=_string_tuple(data, "harnesses", "Family config", path),
        timeout_seconds=int(data.get("timeout_seconds", 7200)),
        batch=_batch_settings(data, path),
        resources=_resource_limits(data),
        results=_result_settings(data, path),
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


def _base_assemble_specs(benchmark: str, split: str, case_id: str) -> tuple[AssembleSpec, ...]:
    return (
        AssembleSpec(
            source=REPO_ROOT / "experiments" / "_fragments" / "prompts" / benchmark / "README.default.md",
            target=WORKSPACE_MOUNT / "README.md",
            render=True,
        ),
        AssembleSpec(
            source=REPO_ROOT / "benchmarks" / benchmark / "dataset" / "cases" / split / case_id,
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
    return (
        item.results_root
        / config.config_path.stem
        / item.condition
        / item.benchmark
        / item.harness
        / item.split
        / item.case_id
    )


def build_items(
    config: FamilyConfig,
    *,
    conditions: tuple[str, ...],
    harnesses: tuple[str, ...],
    cases: tuple[str, ...],
) -> tuple[RunItem, ...]:
    selected_conditions = _select(config.conditions, conditions, "condition")
    selected_harnesses = _select(config.harnesses, harnesses, "harness")
    selected_cases = _select(config.cases, cases, "case")
    items: list[RunItem] = []
    for condition_name in selected_conditions:
        condition = load_condition_profile(condition_name)
        for harness_name in selected_harnesses:
            harness = load_harness_profile(harness_name)
            skill_specs = _skill_assemble_specs(condition, harness)
            for case_id in selected_cases:
                assemble = (
                    *_base_assemble_specs(config.benchmark, config.split, case_id),
                    *harness.assemble,
                    *skill_specs,
                )
                items.append(
                    RunItem(
                        config_name=config.name,
                        benchmark=config.benchmark,
                        split=config.split,
                        case_id=case_id,
                        condition=condition.condition,
                        harness=harness.harness,
                        timeout_seconds=config.timeout_seconds,
                        results_root=config.results.root,
                        assemble=assemble,
                        collect=harness.collect,
                    )
                )
    return tuple(items)


def missing_assemble_sources(item: RunItem) -> tuple[AssembleSpec, ...]:
    return tuple(
        spec
        for spec in item.assemble
        if not workspace_utils.source_available(spec.source, require_nonempty_dirs=True)
        and not spec.missing_ok
    )


def _relative(path: Path) -> str:
    return workspace_utils.relative_display(path, REPO_ROOT)


def print_dry_run(config: FamilyConfig, items: tuple[RunItem, ...]) -> None:
    print(f"Config: {config.config_path}")
    print(f"Mode: {config.mode}")
    print(f"Benchmark: {config.benchmark}")
    print(f"Split: {config.split}")
    print(f"Conditions: {', '.join(dict.fromkeys(item.condition for item in items))}")
    print(f"Harnesses: {', '.join(dict.fromkeys(item.harness for item in items))}")
    print(f"Run count: {len(items)}")
    print(f"Max concurrency: {config.batch.max_concurrency}")
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
            f"- {item.condition}/{item.harness}/{item.case_id}: {state} -> "
            f"{_relative(_output_dir(config, item))}"
        )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config = load_family_config(args.config)
    items = build_items(
        config,
        conditions=tuple(args.condition),
        harnesses=tuple(args.harness),
        cases=tuple(args.case),
    )
    if args.dry_run:
        print_dry_run(config, items)
        return 0
    raise SystemExit("Only --dry-run planning is implemented before skill content is complete.")


if __name__ == "__main__":
    raise SystemExit(main())
