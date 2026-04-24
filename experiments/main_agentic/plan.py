#!/usr/bin/env python3
"""Plan concrete runs for the main agentic experiment family."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
FAMILY_DIR = Path(__file__).resolve().parent
DEFAULT_BATCH_CONFIG = FAMILY_DIR / "configs" / "matrix.yaml"
DEFAULT_INTERACTIVE_CONFIG = FAMILY_DIR / "configs" / "interactive.yaml"
SHARED_AGENTS_FRAGMENT = (
    REPO_ROOT / "experiments" / "_fragments" / "prompts" / "_shared" / "AGENTS.main_agentic.default.md"
)
OPAQUE_VERIFIER_ARTIFACTS_ROOT = (
    REPO_ROOT / "experiments" / "_fragments" / "opaque_verifiers" / "artifacts"
)
OPAQUE_VERIFIER_BUILD_SCRIPT = (
    REPO_ROOT / "experiments" / "_fragments" / "opaque_verifiers" / "build.py"
)
INTERACTIVE_WORKSPACES_ROOT = REPO_ROOT / ".runtime" / "interactive_workspaces"


@dataclass(frozen=True)
class AssembleTemplate:
    source_template: str
    target_template: str
    render: bool
    missing_ok: bool
    example_template: str | None


@dataclass(frozen=True)
class AssembleSpec:
    source: Path
    target: Path
    render: bool
    missing_ok: bool
    example: Path | None


@dataclass(frozen=True)
class CollectSpec:
    source: Path
    target: Path
    missing_ok: bool


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
class BatchConfig:
    name: str
    mode: str
    benchmarks: tuple[str, ...]
    harnesses: tuple[str, ...]
    split: str
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
    harnesses: tuple[str, ...]
    split: str
    case_id: str
    timeout_seconds: int
    resources: ResourceLimits
    config_path: Path


@dataclass(frozen=True)
class BenchmarkProfile:
    benchmark: str
    assemble: tuple[AssembleTemplate, ...]
    collect: tuple[CollectSpec, ...]
    verifier_kind: str
    score_metrics: tuple["MetricSpec", ...]
    flag_metrics: tuple["FlagMetricSpec", ...]
    profile_path: Path


@dataclass(frozen=True)
class MetricSpec:
    name: str
    path: str
    direction: str
    role: str


@dataclass(frozen=True)
class FlagMetricSpec:
    name: str
    path: str


@dataclass(frozen=True)
class HarnessProfile:
    harness: str
    runtime: str
    assemble: tuple[AssembleTemplate, ...]
    headless_shell_command: str
    collect: tuple[CollectSpec, ...]
    forward_env_keys: tuple[str, ...]
    profile_path: Path


@dataclass(frozen=True)
class RuntimeManifest:
    name: str
    image: str
    dockerfile: Path
    build_context: Path
    runtime_dir: Path


@dataclass(frozen=True)
class RunItem:
    config_name: str
    config_path: Path
    benchmark: str
    harness: str
    split: str
    case_id: str
    timeout_seconds: int
    resources: ResourceLimits
    results_root: Path
    benchmark_profile: BenchmarkProfile
    harness_profile: HarnessProfile


@dataclass(frozen=True)
class OpaqueVerifierArtifactStatus:
    benchmark: str
    path: Path
    state: str
    present: bool
    note: str | None


@dataclass(frozen=True)
class BatchPlan:
    config: BatchConfig
    selected_benchmarks: tuple[str, ...]
    selected_harnesses: tuple[str, ...]
    effective_split: str
    items: tuple[RunItem, ...]
    unavailable_configs: tuple[tuple[str, Path], ...]
    opaque_verifier_artifacts: tuple[OpaqueVerifierArtifactStatus, ...]


@dataclass(frozen=True)
class InteractivePlan:
    config: InteractiveConfig
    benchmark_profile: BenchmarkProfile
    harnesses: tuple[HarnessProfile, ...]
    runtime_name: str
    interactive_identity: str
    effective_split: str
    effective_case_id: str
    results_root: Path
    unavailable_configs: tuple[tuple[str, Path], ...]
    opaque_verifier_artifacts: tuple[OpaqueVerifierArtifactStatus, ...]


@dataclass(frozen=True)
class BatchSelectionOptions:
    rerun_statuses: tuple[str, ...]
    no_skip_completed: bool


@dataclass(frozen=True)
class BatchPreviewItem:
    item: RunItem
    artifact_state: str
    existing_overall_status: str | None
    action: str
    reason: str


@dataclass(frozen=True)
class BatchPreview:
    plan: BatchPlan
    selection: BatchSelectionOptions
    items: tuple[BatchPreviewItem, ...]


def family_relpath() -> Path:
    return FAMILY_DIR.relative_to(REPO_ROOT)


def opaque_verifier_benchmark(path: Path) -> str | None:
    try:
        relative = path.resolve().relative_to(OPAQUE_VERIFIER_ARTIFACTS_ROOT)
    except ValueError:
        return None
    return relative.parts[0] if relative.parts else None


def opaque_verifier_rebuild_command(benchmarks: tuple[str, ...]) -> str:
    ordered = tuple(dict.fromkeys(benchmarks))
    command = [
        "uv",
        "run",
        "python",
        OPAQUE_VERIFIER_BUILD_SCRIPT.relative_to(REPO_ROOT).as_posix(),
    ]
    for benchmark in ordered:
        command.extend(["--benchmark", benchmark])
    return " ".join(command)


def _opaque_verifier_metadata_state(path: Path) -> tuple[str, str | None]:
    metadata_path = path.parent / "build.json"
    if not metadata_path.exists():
        return "missing_metadata", f"missing metadata: {metadata_path}"
    try:
        data = yaml.safe_load(metadata_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return "malformed_metadata", f"malformed metadata: {metadata_path}: {exc}"
    if not isinstance(data, dict):
        return "malformed_metadata", f"metadata is not a mapping: {metadata_path}"
    if data.get("build_target") != "runtime_docker_image":
        return "stale_metadata", "artifact was not built inside the runtime Docker image"
    return "present", None


def _opaque_verifier_artifact_status(benchmark: str, path: Path) -> OpaqueVerifierArtifactStatus:
    if not path.exists():
        return OpaqueVerifierArtifactStatus(
            benchmark=benchmark,
            path=path,
            state="missing",
            present=False,
            note=None,
        )
    state, note = _opaque_verifier_metadata_state(path)
    return OpaqueVerifierArtifactStatus(
        benchmark=benchmark,
        path=path,
        state=state,
        present=state == "present",
        note=note,
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plan the main agentic benchmark x harness matrix"
    )
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
        help="Limit planning to a benchmark name. May be repeated.",
    )
    parser.add_argument(
        "--harness",
        action="append",
        default=[],
        help="Limit planning to a harness name. May be repeated.",
    )
    parser.add_argument(
        "--split",
        help="Override the configured split for this planning pass.",
    )
    parser.add_argument(
        "--case",
        action="append",
        default=[],
        help="Limit planning to an exact case id. May be repeated.",
    )
    parser.add_argument(
        "--max-concurrency",
        type=int,
        help="Override matrix.yaml batch.max_concurrency for this planning pass.",
    )
    parser.add_argument(
        "--rerun-status",
        action="append",
        default=[],
        help="Preview only runs whose current stored status matches this value. May be repeated.",
    )
    parser.add_argument(
        "--no-skip-completed",
        action="store_true",
        help="Preview all selected runs as executable, regardless of existing run.json status.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Accepted for compatibility; planning is always dry-run only.",
    )
    return parser.parse_args(argv)


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


def _string_tuple(data: dict[str, Any], key: str, kind: str, path: Path) -> tuple[str, ...]:
    value = data.get(key)
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise SystemExit(f"{kind} field '{key}' must be a list of strings: {path}")
    return tuple(value)


def _resolve_repo_path(path_value: str) -> Path:
    candidate = Path(path_value)
    if candidate.is_absolute():
        return candidate.resolve()
    return (REPO_ROOT / candidate).resolve()


def _parse_container_path(path_value: str, *, label: str, path: Path) -> Path:
    pure = PurePosixPath(path_value)
    if pure.is_absolute():
        return Path(pure.as_posix())
    raise SystemExit(f"{label} must be an absolute container path: {path}")


def _parse_collect_target(path_value: str, *, label: str, path: Path) -> Path:
    pure = PurePosixPath(path_value)
    if pure.is_absolute() or not pure.parts:
        raise SystemExit(
            f"{label} must start with results_root/, repo/, benchmark(s)/, or experiments/: {path}"
        )
    if pure.parts[0] not in {
        "results_root",
        "repo",
        "benchmark",
        "benchmarks",
        "experiments",
    }:
        raise SystemExit(
            f"{label} must start with results_root/, repo/, benchmark(s)/, or experiments/: {path}"
        )
    return Path(*pure.parts)


def _load_resource_limits(data: dict[str, Any], config_path: Path) -> ResourceLimits:
    resources = data.get("resources", {})
    if not isinstance(resources, dict):
        raise SystemExit(f"Config field 'resources' must be a mapping: {config_path}")
    return ResourceLimits(
        cpus=_optional_string(resources, "cpus", None, "Resources", config_path),
        memory=_optional_string(resources, "memory", None, "Resources", config_path),
        shm_size=_optional_string(resources, "shm_size", None, "Resources", config_path),
    )


def _parse_collect_specs(items: Any, config_path: Path) -> tuple[CollectSpec, ...]:
    if not isinstance(items, list):
        raise SystemExit(f"Collect field must be a list: {config_path}")

    specs: list[CollectSpec] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise SystemExit(f"Collect spec #{index} must be a mapping: {config_path}")
        source_value = _require_str(item, "source", "Collect spec", config_path)
        target_value = _require_str(item, "target", "Collect spec", config_path)
        specs.append(
            CollectSpec(
                source=_parse_container_path(
                    source_value,
                    label=f"Collect spec #{index} source",
                    path=config_path,
                ),
                target=_parse_collect_target(
                    target_value,
                    label=f"Collect spec #{index} target",
                    path=config_path,
                ),
                missing_ok=_optional_bool(item, "missing_ok", True, "Collect spec", config_path),
            )
        )
    return tuple(specs)


def _parse_assemble_templates(items: Any, config_path: Path) -> tuple[AssembleTemplate, ...]:
    if not isinstance(items, list) or not items:
        raise SystemExit(f"Assemble field must be a non-empty list: {config_path}")

    specs: list[AssembleTemplate] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise SystemExit(f"Assemble spec #{index} must be a mapping: {config_path}")
        example_value = item.get("example")
        if example_value is not None and (not isinstance(example_value, str) or not example_value):
            raise SystemExit(
                f"Assemble spec #{index} field 'example' must be a non-empty string when present: {config_path}"
            )
        specs.append(
            AssembleTemplate(
                source_template=_require_str(item, "source", "Assemble spec", config_path),
                target_template=_require_str(item, "target", "Assemble spec", config_path),
                render=_optional_bool(item, "render", False, "Assemble spec", config_path),
                missing_ok=_optional_bool(item, "missing_ok", False, "Assemble spec", config_path),
                example_template=example_value,
            )
        )
    return tuple(specs)


def _parse_metric_specs(items: Any, profile_path: Path) -> tuple[MetricSpec, ...]:
    if not isinstance(items, list):
        raise SystemExit(f"Aggregation field 'score_metrics' must be a list: {profile_path}")

    specs: list[MetricSpec] = []
    roles_seen: set[str] = set()
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise SystemExit(f"Aggregation score metric #{index} must be a mapping: {profile_path}")
        direction = _require_str(item, "direction", "Aggregation score metric", profile_path)
        if direction not in {"maximize", "minimize"}:
            raise SystemExit(
                f"Aggregation score metric #{index} field 'direction' must be maximize or minimize: {profile_path}"
            )
        role = _require_str(item, "role", "Aggregation score metric", profile_path)
        if role not in {"primary", "secondary"}:
            raise SystemExit(
                f"Aggregation score metric #{index} field 'role' must be primary or secondary: {profile_path}"
            )
        roles_seen.add(role)
        specs.append(
            MetricSpec(
                name=_require_str(item, "name", "Aggregation score metric", profile_path),
                path=_require_str(item, "path", "Aggregation score metric", profile_path),
                direction=direction,
                role=role,
            )
        )

    if items and "primary" not in roles_seen:
        raise SystemExit(
            f"Aggregation score_metrics must include one primary metric: {profile_path}"
        )
    return tuple(specs)


def _parse_flag_metric_specs(items: Any, profile_path: Path) -> tuple[FlagMetricSpec, ...]:
    if items is None:
        return ()
    if not isinstance(items, list):
        raise SystemExit(f"Aggregation field 'flag_metrics' must be a list: {profile_path}")

    specs: list[FlagMetricSpec] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise SystemExit(f"Aggregation flag metric #{index} must be a mapping: {profile_path}")
        specs.append(
            FlagMetricSpec(
                name=_require_str(item, "name", "Aggregation flag metric", profile_path),
                path=_require_str(item, "path", "Aggregation flag metric", profile_path),
            )
        )
    return tuple(specs)


def load_batch_config(config_path: Path) -> BatchConfig:
    data = _load_yaml_mapping(config_path, "Family config")
    mode = _require_str(data, "mode", "Family config", config_path)
    if mode != "batch":
        raise SystemExit(f"Expected a batch family config, found mode '{mode}': {config_path}")

    benchmarks = tuple(_string_tuple(data, "benchmarks", "Family config", config_path))
    harnesses = tuple(_string_tuple(data, "harnesses", "Family config", config_path))
    defaults = data.get("defaults")
    if not isinstance(defaults, dict):
        raise SystemExit(f"Family config field 'defaults' must be a mapping: {config_path}")
    batch = data.get("batch")
    if not isinstance(batch, dict):
        raise SystemExit(f"Family config field 'batch' must be a mapping: {config_path}")
    results = data.get("results")
    if not isinstance(results, dict):
        raise SystemExit(f"Family config field 'results' must be a mapping: {config_path}")

    max_concurrency = _optional_int(batch, "max_concurrency", None, "Batch config", config_path)
    max_retries = _optional_int(batch, "max_retries", None, "Batch config", config_path)
    if max_concurrency is None or max_concurrency <= 0:
        raise SystemExit(
            f"Batch config field 'max_concurrency' must be a positive integer: {config_path}"
        )
    if max_retries is None or max_retries < 0:
        raise SystemExit(
            f"Batch config field 'max_retries' must be a non-negative integer: {config_path}"
        )

    retry_statuses_value = batch.get("retry_statuses")
    if not isinstance(retry_statuses_value, list) or not all(
        isinstance(item, str) and item for item in retry_statuses_value
    ):
        raise SystemExit(
            f"Batch config field 'retry_statuses' must be a list of non-empty strings: {config_path}"
        )

    return BatchConfig(
        name=_require_str(data, "name", "Family config", config_path),
        mode=mode,
        benchmarks=benchmarks,
        harnesses=harnesses,
        split=_require_str(defaults, "split", "Family defaults", config_path),
        timeout_seconds=_optional_int(
            defaults, "timeout_seconds", None, "Family defaults", config_path
        )
        or 3600,
        batch=BatchSettings(
            max_concurrency=max_concurrency,
            max_retries=max_retries,
            skip_completed=_optional_bool(
                batch, "skip_completed", True, "Batch config", config_path
            ),
            retry_statuses=tuple(retry_statuses_value),
        ),
        resources=_load_resource_limits(data, config_path),
        results=ResultSettings(
            root=_resolve_repo_path(_require_str(results, "root", "Results config", config_path)),
            aggregate_dir=Path(
                _require_str(results, "aggregate_dir", "Results config", config_path)
            ),
        ),
        config_path=config_path.resolve(),
    )


def load_interactive_config(config_path: Path) -> InteractiveConfig:
    data = _load_yaml_mapping(config_path, "Family config")
    mode = _require_str(data, "mode", "Family config", config_path)
    if mode != "interactive":
        raise SystemExit(f"Expected an interactive family config, found mode '{mode}': {config_path}")

    return InteractiveConfig(
        name=_require_str(data, "name", "Family config", config_path),
        mode=mode,
        benchmark=_require_str(data, "benchmark", "Family config", config_path),
        harnesses=_string_tuple(data, "harnesses", "Family config", config_path),
        split=_require_str(data, "split", "Family config", config_path),
        case_id=_require_str(data, "case", "Family config", config_path),
        timeout_seconds=_optional_int(
            data, "timeout_seconds", None, "Family config", config_path
        )
        or 3600,
        resources=_load_resource_limits(data, config_path),
        config_path=config_path.resolve(),
    )


def load_benchmark_profile(name: str) -> BenchmarkProfile:
    profile_path = FAMILY_DIR / "benchmarks" / f"{name}.yaml"
    data = _load_yaml_mapping(profile_path, "Benchmark profile")
    benchmark = _require_str(data, "benchmark", "Benchmark profile", profile_path)
    if benchmark != name:
        raise SystemExit(
            f"Benchmark profile name mismatch: expected '{name}', found '{benchmark}' in {profile_path}"
        )

    aggregation = data.get("aggregation")
    if not isinstance(aggregation, dict):
        raise SystemExit(f"Benchmark profile field 'aggregation' must be a mapping: {profile_path}")

    return BenchmarkProfile(
        benchmark=benchmark,
        assemble=_parse_assemble_templates(data.get("assemble"), profile_path),
        collect=_parse_collect_specs(data.get("collect", []), profile_path),
        verifier_kind=_require_str(aggregation, "verifier_kind", "Aggregation config", profile_path),
        score_metrics=_parse_metric_specs(aggregation.get("score_metrics", []), profile_path),
        flag_metrics=_parse_flag_metric_specs(aggregation.get("flag_metrics"), profile_path),
        profile_path=profile_path.resolve(),
    )


def load_harness_profile(name: str) -> HarnessProfile:
    profile_path = FAMILY_DIR / "harnesses" / f"{name}.yaml"
    data = _load_yaml_mapping(profile_path, "Harness profile")
    harness = _require_str(data, "harness", "Harness profile", profile_path)
    if harness != name:
        raise SystemExit(
            f"Harness profile name mismatch: expected '{name}', found '{harness}' in {profile_path}"
        )

    commands = data.get("commands")
    if not isinstance(commands, dict):
        raise SystemExit(f"Harness profile field 'commands' must be a mapping: {profile_path}")
    forward_env_keys = data.get("forward_env_keys", [])
    if not isinstance(forward_env_keys, list) or not all(
        isinstance(item, str) and item for item in forward_env_keys
    ):
        raise SystemExit(
            f"Harness profile field 'forward_env_keys' must be a list of non-empty strings: {profile_path}"
        )

    return HarnessProfile(
        harness=harness,
        runtime=_require_str(data, "runtime", "Harness profile", profile_path),
        assemble=_parse_assemble_templates(data.get("assemble"), profile_path),
        headless_shell_command=_require_str(
            commands, "headless_shell_command", "Harness commands", profile_path
        ),
        collect=_parse_collect_specs(data.get("collect", []), profile_path),
        forward_env_keys=tuple(forward_env_keys),
        profile_path=profile_path.resolve(),
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
        runtime_dir=runtime_dir.resolve(),
    )


def format_template_string(
    template: str,
    replacements: dict[str, str],
    *,
    label: str,
    path: Path,
) -> str:
    rendered = template
    for key, value in replacements.items():
        rendered = rendered.replace(f"{{{key}}}", value)

    if "{" in rendered or "}" in rendered:
        raise SystemExit(f"{label} contains unresolved placeholders in {path}: {template}")
    return rendered


def materialize_assemble_templates(
    templates: tuple[AssembleTemplate, ...],
    replacements: dict[str, str],
    *,
    owner_path: Path,
) -> tuple[AssembleSpec, ...]:
    specs: list[AssembleSpec] = []
    for index, template in enumerate(templates):
        source_value = format_template_string(
            template.source_template,
            replacements,
            label=f"Assemble spec #{index} source",
            path=owner_path,
        )
        target_value = format_template_string(
            template.target_template,
            replacements,
            label=f"Assemble spec #{index} target",
            path=owner_path,
        )
        example_value = (
            format_template_string(
                template.example_template,
                replacements,
                label=f"Assemble spec #{index} example",
                path=owner_path,
            )
            if template.example_template is not None
            else None
        )
        specs.append(
            AssembleSpec(
                source=_resolve_repo_path(source_value),
                target=_parse_container_path(
                    target_value,
                    label=f"Assemble spec #{index} target",
                    path=owner_path,
                ),
                render=template.render,
                missing_ok=template.missing_ok,
                example=_resolve_repo_path(example_value) if example_value is not None else None,
            )
        )
    return tuple(specs)


def _select_names(
    configured: tuple[str, ...],
    requested: tuple[str, ...],
    *,
    label: str,
) -> tuple[str, ...]:
    if not requested:
        return configured

    unknown = [name for name in requested if name not in configured]
    if unknown:
        available = ", ".join(configured)
        unknown_text = ", ".join(unknown)
        raise SystemExit(f"Unknown {label}(s): {unknown_text}. Available {label}s: {available}")

    seen: set[str] = set()
    selected: list[str] = []
    requested_set = set(requested)
    for name in configured:
        if name in requested_set and name not in seen:
            selected.append(name)
            seen.add(name)
    return tuple(selected)


def _enumerate_case_ids(benchmark: str, split: str) -> tuple[str, ...]:
    cases_dir = REPO_ROOT / "benchmarks" / benchmark / "dataset" / "cases" / split
    if not cases_dir.is_dir():
        raise SystemExit(f"Case directory does not exist: {cases_dir}")
    case_ids = sorted(path.name for path in cases_dir.iterdir() if path.is_dir())
    if not case_ids:
        raise SystemExit(f"No cases found under {cases_dir}")
    return tuple(case_ids)


def _collect_missing_configs(harnesses: tuple[HarnessProfile, ...]) -> tuple[tuple[str, Path], ...]:
    missing: list[tuple[str, Path]] = []
    for harness in harnesses:
        for spec in materialize_assemble_templates(
            harness.assemble,
            {},
            owner_path=harness.profile_path,
        ):
            if spec.missing_ok:
                continue
            if spec.source.exists():
                continue
            missing.append((harness.harness, spec.source))
    return tuple(missing)


def _benchmark_assemble_replacements(
    benchmark: str,
    *,
    split: str,
    case_id: str,
    config_name: str,
) -> dict[str, str]:
    return {
        "benchmark": benchmark,
        "split": split,
        "case_id": case_id,
        "family": FAMILY_DIR.name,
        "config_name": config_name,
    }


def _opaque_verifier_artifacts_for_benchmark(
    profile: BenchmarkProfile,
    *,
    split: str,
    case_id: str,
    config_name: str,
) -> tuple[OpaqueVerifierArtifactStatus, ...]:
    assemble_specs = materialize_assemble_templates(
        profile.assemble,
        _benchmark_assemble_replacements(
            profile.benchmark,
            split=split,
            case_id=case_id,
            config_name=config_name,
        ),
        owner_path=profile.profile_path,
    )
    artifacts: list[OpaqueVerifierArtifactStatus] = []
    seen_paths: set[Path] = set()
    for spec in assemble_specs:
        benchmark = opaque_verifier_benchmark(spec.source)
        if benchmark is None or spec.source in seen_paths:
            continue
        seen_paths.add(spec.source)
        artifacts.append(_opaque_verifier_artifact_status(benchmark, spec.source))
    return tuple(sorted(artifacts, key=lambda item: (item.benchmark, item.path.as_posix())))


def _collect_opaque_verifier_artifacts_for_batch(
    benchmark_profiles: dict[str, BenchmarkProfile],
    selected_benchmarks: tuple[str, ...],
    *,
    split: str,
    case_ids_by_benchmark: dict[str, tuple[str, ...]],
    config_name: str,
) -> tuple[OpaqueVerifierArtifactStatus, ...]:
    artifacts: list[OpaqueVerifierArtifactStatus] = []
    for benchmark in selected_benchmarks:
        case_ids = case_ids_by_benchmark[benchmark]
        artifacts.extend(
            _opaque_verifier_artifacts_for_benchmark(
                benchmark_profiles[benchmark],
                split=split,
                case_id=case_ids[0],
                config_name=config_name,
            )
        )
    return tuple(artifacts)


def _collect_opaque_verifier_artifacts_for_interactive(
    benchmark_profile: BenchmarkProfile,
    *,
    split: str,
    case_id: str,
    config_name: str,
) -> tuple[OpaqueVerifierArtifactStatus, ...]:
    return _opaque_verifier_artifacts_for_benchmark(
        benchmark_profile,
        split=split,
        case_id=case_id,
        config_name=config_name,
    )


def raise_if_unusable_opaque_verifiers(
    artifacts: tuple[OpaqueVerifierArtifactStatus, ...],
) -> None:
    unusable = tuple(artifact for artifact in artifacts if not artifact.present)
    if not unusable:
        return
    benchmarks = tuple(artifact.benchmark for artifact in unusable)
    lines = ["Unusable required opaque verifier artifacts:"]
    for artifact in unusable:
        note = f" ({artifact.note})" if artifact.note else ""
        lines.append(f"- {artifact.benchmark}: {artifact.state} at {artifact.path}{note}")
    lines.append(f"Rebuild with: {opaque_verifier_rebuild_command(benchmarks)}")
    raise SystemExit("\n".join(lines))


def _append_opaque_verifier_lines(
    lines: list[str],
    artifacts: tuple[OpaqueVerifierArtifactStatus, ...],
) -> None:
    if not artifacts:
        lines.append("Opaque verifier artifacts: none")
        return
    lines.append("Opaque verifier artifacts:")
    for artifact in artifacts:
        note = f" ({artifact.note})" if artifact.note else ""
        lines.append(f"  - {artifact.benchmark}: {artifact.state} at {artifact.path}{note}")
    unusable = tuple(artifact.benchmark for artifact in artifacts if not artifact.present)
    if unusable:
        lines.append(f"Rebuild command: {opaque_verifier_rebuild_command(unusable)}")


def _unique_requested_cases(case_filters: tuple[str, ...]) -> tuple[str, ...]:
    seen: set[str] = set()
    selected: list[str] = []
    for case_id in case_filters:
        if case_id not in seen:
            selected.append(case_id)
            seen.add(case_id)
    return tuple(selected)


def _select_case_ids(
    case_ids: tuple[str, ...],
    *,
    benchmark: str,
    split: str,
    case_filters: tuple[str, ...],
) -> tuple[str, ...]:
    if not case_filters:
        return case_ids

    requested = set(case_filters)
    selected = tuple(case_id for case_id in case_ids if case_id in requested)
    if selected:
        return selected

    requested_text = ", ".join(case_filters)
    raise SystemExit(
        f"No matching cases for benchmark '{benchmark}' on split '{split}'. "
        f"Requested case id(s): {requested_text}"
    )


def _validate_rerun_statuses(statuses: tuple[str, ...]) -> tuple[str, ...]:
    allowed = {
        "success",
        "runner_error",
        "timeout",
        "agent_failed",
        "no_solution",
        "verifier_invalid",
        "verifier_error",
        "missing_artifact",
        "malformed_artifact",
    }
    unknown = sorted(status for status in statuses if status not in allowed)
    if unknown:
        raise SystemExit(
            "Unknown rerun status(es): "
            + ", ".join(unknown)
            + ". Allowed values: "
            + ", ".join(sorted(allowed))
        )
    return statuses


def _read_existing_overall_status(item: RunItem) -> tuple[str, str | None]:
    run_json_path = run_output_dir(item) / "run.json"
    if not run_json_path.exists():
        return "missing_artifact", None

    try:
        data = yaml.safe_load(run_json_path.read_text(encoding="utf-8"))
    except Exception:
        return "malformed_artifact", None

    if not isinstance(data, dict):
        return "malformed_artifact", None
    status = data.get("overall_status")
    if not isinstance(status, str) or not status:
        return "malformed_artifact", None
    return "present", status


def build_batch_preview(
    plan: BatchPlan,
    *,
    rerun_statuses: tuple[str, ...] = (),
    no_skip_completed: bool = False,
) -> BatchPreview:
    rerun_statuses = _validate_rerun_statuses(rerun_statuses)
    selection = BatchSelectionOptions(
        rerun_statuses=rerun_statuses,
        no_skip_completed=no_skip_completed,
    )

    items: list[BatchPreviewItem] = []
    for item in plan.items:
        artifact_state, existing_status = _read_existing_overall_status(item)
        if rerun_statuses:
            candidate_status = existing_status if artifact_state == "present" else artifact_state
            if candidate_status in rerun_statuses:
                action = "run"
                reason = "rerun_status_match"
            else:
                action = "skip"
                reason = "status_filter_mismatch"
        elif no_skip_completed:
            action = "run"
            reason = "forced_by_no_skip"
        elif artifact_state == "missing_artifact":
            action = "run"
            reason = "missing_artifact"
        elif artifact_state == "malformed_artifact":
            action = "run"
            reason = "malformed_artifact"
        elif existing_status in plan.config.batch.retry_statuses:
            action = "run"
            reason = "retryable_status"
        elif plan.config.batch.skip_completed:
            action = "skip"
            reason = "existing_terminal_status"
        else:
            action = "run"
            reason = "forced_by_no_skip"

        items.append(
            BatchPreviewItem(
                item=item,
                artifact_state=artifact_state,
                existing_overall_status=existing_status,
                action=action,
                reason=reason,
            )
        )

    return BatchPreview(plan=plan, selection=selection, items=tuple(items))


def runnable_preview_items(preview: BatchPreview) -> tuple[BatchPreviewItem, ...]:
    return tuple(item for item in preview.items if item.action == "run")


def build_batch_plan(
    *,
    config_path: Path,
    benchmark_filters: tuple[str, ...] = (),
    harness_filters: tuple[str, ...] = (),
    split_override: str | None = None,
    case_filters: tuple[str, ...] = (),
    max_concurrency_override: int | None = None,
    require_real_configs: bool = False,
) -> BatchPlan:
    config = load_batch_config(config_path.resolve())
    if max_concurrency_override is not None:
        if max_concurrency_override <= 0:
            raise SystemExit("--max-concurrency must be a positive integer.")
        config = replace(
            config,
            batch=replace(config.batch, max_concurrency=max_concurrency_override),
        )
    effective_split = split_override or config.split
    selected_benchmarks = _select_names(
        config.benchmarks,
        benchmark_filters,
        label="benchmark",
    )
    selected_harnesses = _select_names(
        config.harnesses,
        harness_filters,
        label="harness",
    )
    if not selected_benchmarks:
        raise SystemExit("No benchmarks selected for planning.")
    if not selected_harnesses:
        raise SystemExit("No harnesses selected for planning.")

    benchmark_profiles = {
        benchmark: load_benchmark_profile(benchmark) for benchmark in selected_benchmarks
    }
    harness_profiles = {
        harness: load_harness_profile(harness) for harness in selected_harnesses
    }
    unavailable = _collect_missing_configs(tuple(harness_profiles.values()))
    if require_real_configs and unavailable:
        lines = ["Missing required harness config files:"]
        for harness, path in unavailable:
            lines.append(f"- {harness}: {path}")
        raise SystemExit("\n".join(lines))

    items: list[RunItem] = []
    case_ids_by_benchmark: dict[str, tuple[str, ...]] = {}
    for benchmark in selected_benchmarks:
        case_ids = _select_case_ids(
            _enumerate_case_ids(benchmark, effective_split),
            benchmark=benchmark,
            split=effective_split,
            case_filters=_unique_requested_cases(case_filters),
        )
        case_ids_by_benchmark[benchmark] = case_ids
        benchmark_profile = benchmark_profiles[benchmark]
        for case_id in case_ids:
            for harness in selected_harnesses:
                harness_profile = harness_profiles[harness]
                items.append(
                    RunItem(
                        config_name=config.config_path.stem,
                        config_path=config.config_path,
                        benchmark=benchmark,
                        harness=harness,
                        split=effective_split,
                        case_id=case_id,
                        timeout_seconds=config.timeout_seconds,
                        resources=config.resources,
                        results_root=config.results.root,
                        benchmark_profile=benchmark_profile,
                        harness_profile=harness_profile,
                    )
                )
    opaque_verifier_artifacts = _collect_opaque_verifier_artifacts_for_batch(
        benchmark_profiles,
        selected_benchmarks,
        split=effective_split,
        case_ids_by_benchmark=case_ids_by_benchmark,
        config_name=config.config_path.stem,
    )
    if require_real_configs:
        raise_if_unusable_opaque_verifiers(opaque_verifier_artifacts)

    return BatchPlan(
        config=config,
        selected_benchmarks=selected_benchmarks,
        selected_harnesses=selected_harnesses,
        effective_split=effective_split,
        items=tuple(items),
        unavailable_configs=unavailable,
        opaque_verifier_artifacts=opaque_verifier_artifacts,
    )


def build_interactive_plan(
    *,
    config_path: Path,
    benchmark_filters: tuple[str, ...] = (),
    harness_filters: tuple[str, ...] = (),
    split_override: str | None = None,
    case_filters: tuple[str, ...] = (),
    require_real_configs: bool = False,
) -> InteractivePlan:
    config = load_interactive_config(config_path.resolve())
    if benchmark_filters:
        filtered = _select_names((config.benchmark,), benchmark_filters, label="benchmark")
        if filtered != (config.benchmark,):
            raise SystemExit("Interactive planning requires exactly one selected benchmark.")

    selected_harness_names = _select_names(
        config.harnesses,
        harness_filters,
        label="harness",
    )
    if not selected_harness_names:
        raise SystemExit("No harnesses selected for interactive planning.")

    benchmark_profile = load_benchmark_profile(config.benchmark)
    harnesses = tuple(load_harness_profile(name) for name in selected_harness_names)
    unavailable = _collect_missing_configs(harnesses)
    if require_real_configs and unavailable:
        lines = ["Missing required harness config files:"]
        for harness, path in unavailable:
            lines.append(f"- {harness}: {path}")
        raise SystemExit("\n".join(lines))

    runtimes = {harness.runtime for harness in harnesses}
    if len(runtimes) != 1:
        runtime_list = ", ".join(sorted(runtimes))
        raise SystemExit(
            "Interactive mode currently requires all selected harnesses to share one runtime. "
            f"Found: {runtime_list}"
        )

    runtime_name = next(iter(runtimes))
    interactive_identity = harnesses[0].harness if len(harnesses) == 1 else "all_harnesses"
    effective_split = split_override or config.split
    requested_cases = _unique_requested_cases(case_filters)
    if len(requested_cases) > 1:
        raise SystemExit(
            "Interactive planning requires exactly one effective case. "
            f"Requested multiple case ids: {', '.join(requested_cases)}"
        )
    effective_case_id = requested_cases[0] if requested_cases else config.case_id
    case_dir = REPO_ROOT / "benchmarks" / config.benchmark / "dataset" / "cases" / effective_split / effective_case_id
    if not case_dir.is_dir():
        raise SystemExit(f"Case directory does not exist: {case_dir}")
    opaque_verifier_artifacts = _collect_opaque_verifier_artifacts_for_interactive(
        benchmark_profile,
        split=effective_split,
        case_id=effective_case_id,
        config_name=config.config_path.stem,
    )
    if require_real_configs:
        raise_if_unusable_opaque_verifiers(opaque_verifier_artifacts)
    return InteractivePlan(
        config=config,
        benchmark_profile=benchmark_profile,
        harnesses=harnesses,
        runtime_name=runtime_name,
        interactive_identity=interactive_identity,
        effective_split=effective_split,
        effective_case_id=effective_case_id,
        results_root=REPO_ROOT / "results" / "agent_runs" / family_relpath(),
        unavailable_configs=unavailable,
        opaque_verifier_artifacts=opaque_verifier_artifacts,
    )


def run_output_dir(item: RunItem) -> Path:
    return (
        item.results_root
        / item.config_name
        / item.benchmark
        / item.harness
        / item.split
        / item.case_id
    )


def interactive_workspace_dir(plan: InteractivePlan) -> Path:
    return (
        INTERACTIVE_WORKSPACES_ROOT
        / family_relpath()
        / plan.config.config_path.stem
        / plan.config.benchmark
        / plan.interactive_identity
        / plan.effective_split
        / plan.effective_case_id
    )


def interactive_output_dir(plan: InteractivePlan) -> Path:
    return (
        plan.results_root
        / plan.config.config_path.stem
        / plan.config.benchmark
        / plan.interactive_identity
        / plan.effective_split
        / plan.effective_case_id
    )


def _count_strings(values: tuple[str, ...] | list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def describe_batch_preview(preview: BatchPreview, *, include_items: bool = True) -> str:
    plan = preview.plan
    runnable_items = runnable_preview_items(preview)
    benchmark_case_counts = {
        benchmark: len(
            {preview_item.item.case_id for preview_item in preview.items if preview_item.item.benchmark == benchmark}
        )
        for benchmark in plan.selected_benchmarks
    }
    runnable_count = sum(1 for item in preview.items if item.action == "run")
    skipped_count = len(preview.items) - runnable_count
    reason_counts = _count_strings([item.reason for item in preview.items])
    artifact_counts = _count_strings([item.artifact_state for item in preview.items])
    existing_status_counts = _count_strings(
        [item.existing_overall_status for item in preview.items if item.existing_overall_status is not None]
    )
    lines = [
        f"Config: {plan.config.config_path}",
        "Mode: batch",
        f"Benchmarks: {', '.join(plan.selected_benchmarks)}",
        f"Harnesses: {', '.join(plan.selected_harnesses)}",
        f"Split: {plan.effective_split}",
        "Selection mode: "
        + (
            "force all selected runs"
            if preview.selection.no_skip_completed
            else (
                "rerun matching statuses: " + ", ".join(preview.selection.rerun_statuses)
                if preview.selection.rerun_statuses
                else "default artifact-first resume"
            )
        ),
        f"Cases per benchmark: "
        + ", ".join(f"{benchmark}={benchmark_case_counts[benchmark]}" for benchmark in plan.selected_benchmarks),
        f"Total candidate runs: {len(preview.items)}",
        f"Runs to execute: {runnable_count}",
        f"Runs to skip: {skipped_count}",
        f"Runnable queue length: {len(runnable_items)}",
        f"Max concurrency: {plan.config.batch.max_concurrency}",
        f"Max retries: {plan.config.batch.max_retries}",
    ]
    if plan.unavailable_configs:
        lines.append("Unavailable harness configs:")
        for harness, path in plan.unavailable_configs:
            lines.append(f"  - {harness}: {path}")
    else:
        lines.append("Unavailable harness configs: none")
    _append_opaque_verifier_lines(lines, plan.opaque_verifier_artifacts)
    lines.append(
        "Artifact states: "
        + ", ".join(f"{key}={value}" for key, value in artifact_counts.items())
    )
    if existing_status_counts:
        lines.append(
            "Existing statuses: "
            + ", ".join(f"{key}={value}" for key, value in existing_status_counts.items())
        )
    else:
        lines.append("Existing statuses: none")
    lines.append("Selection reasons: " + ", ".join(f"{key}={value}" for key, value in reason_counts.items()))
    if include_items:
        lines.append("Concrete runs:")
        for preview_item in preview.items:
            item = preview_item.item
            status_text = preview_item.existing_overall_status or preview_item.artifact_state
            lines.append(
                f"  - {preview_item.action.upper()} [{preview_item.reason}] "
                f"{item.benchmark} / {item.harness} / {item.split} / {item.case_id} "
                f"(current={status_text}) -> {run_output_dir(item)}"
            )
    return "\n".join(lines)


def describe_interactive_plan(plan: InteractivePlan) -> str:
    lines = [
        f"Config: {plan.config.config_path}",
        "Mode: interactive",
        f"Benchmark: {plan.config.benchmark}",
        f"Harnesses: {', '.join(harness.harness for harness in plan.harnesses)}",
        f"Runtime: {plan.runtime_name}",
        f"Split: {plan.effective_split}",
        f"Case: {plan.effective_case_id}",
        f"Interactive identity: {plan.interactive_identity}",
        f"Workspace path: {interactive_workspace_dir(plan)}",
        f"Result path: {interactive_output_dir(plan)}",
    ]
    if plan.unavailable_configs:
        lines.append("Unavailable harness configs:")
        for harness, path in plan.unavailable_configs:
            lines.append(f"  - {harness}: {path}")
    else:
        lines.append("Unavailable harness configs: none")
    _append_opaque_verifier_lines(lines, plan.opaque_verifier_artifacts)
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.rerun_status and args.no_skip_completed:
        raise SystemExit("--rerun-status and --no-skip-completed cannot be used together.")
    default_config = DEFAULT_INTERACTIVE_CONFIG if args.interactive else DEFAULT_BATCH_CONFIG
    config_path = (args.config or default_config).resolve()
    benchmark_filters = tuple(args.benchmark)
    harness_filters = tuple(args.harness)
    case_filters = tuple(args.case)

    if args.interactive:
        if args.rerun_status or args.no_skip_completed or args.max_concurrency is not None:
            raise SystemExit(
                "--rerun-status, --no-skip-completed, and --max-concurrency are batch-only controls and cannot be used with --interactive."
            )
        plan = build_interactive_plan(
            config_path=config_path,
            benchmark_filters=benchmark_filters,
            harness_filters=harness_filters,
            split_override=args.split,
            case_filters=case_filters,
            require_real_configs=False,
        )
        print(describe_interactive_plan(plan))
        return 0

    plan = build_batch_plan(
        config_path=config_path,
        benchmark_filters=benchmark_filters,
        harness_filters=harness_filters,
        split_override=args.split,
        case_filters=case_filters,
        max_concurrency_override=args.max_concurrency,
        require_real_configs=False,
    )
    preview = build_batch_preview(
        plan,
        rerun_statuses=tuple(args.rerun_status),
        no_skip_completed=args.no_skip_completed,
    )
    print(describe_batch_preview(preview))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
